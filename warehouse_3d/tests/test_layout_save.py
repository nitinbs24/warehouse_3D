from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user

from .common import create_p05, create_zone


class TestLayoutSave(TransactionCase):
    """warehouse.rack.row.wh3d_save_layout(): the editor's one Save call — all or nothing."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')
        cls.zone = create_zone(cls.env, cls.warehouse)
        cls.Row = cls.env['warehouse.rack.row']

    def setUp(self):
        super().setUp()
        self.p05 = create_p05(self.env, self.warehouse, self.zone)                        # x 9.7–10.8
        self.p06 = create_p05(self.env, self.warehouse, self.zone, code='P06', x=20.5)    # x 20.5–21.6

    def _save(self, create=(), write=(), delete=()):
        return self.Row.wh3d_save_layout(self.warehouse.id, {
            'create': list(create), 'write': list(write), 'delete': list(delete)})

    def _slots(self, row):
        return self.env['stock.location'].search_count([('wh3d_rack_row_id', '=', row.id), ('wh3d_node', '=', 'slot')])

    def test_move_and_edit(self):
        self._save(write=[{'id': self.p05.id, 'vals': {'x': 10.2, 'y': 2.0, 'bays': 8}}])
        self.assertEqual((self.p05.x, self.p05.y, self.p05.bays), (10.2, 2.0, 8))
        self.assertEqual(self._slots(self.p05), 80)  # locations follow (T3)

    def test_create_returns_new_ids_and_builds_locations(self):
        result = self._save(create=[{'tmp_id': -1, 'vals': {
            'code': 'P07', 'kind': 'pallet', 'x': 30.0, 'y': 1.0, 'bays': 7, 'bay_width': 2.7, 'depth': 1.1,
            'levels': 5, 'level_height': 1.8, 'slots_per_level': 2}}])
        new_row = self.Row.browse(result['created'][-1])
        self.assertEqual(new_row.code, 'P07')
        self.assertEqual(new_row.location_id, self.zone)  # zone taken from the existing pallet rows
        self.assertEqual(self._slots(new_row), 70)
        self.assertEqual({r['code'] for r in result['layout']['rows']}, {'P05', 'P06', 'P07'})

    def test_new_shelf_row_without_a_shelf_zone_goes_under_stock(self):
        result = self._save(create=[{'tmp_id': -1, 'vals': {
            'code': 'S01', 'kind': 'shelf', 'x': 40.0, 'y': 2.0, 'bays': 16, 'bay_width': 1.0, 'depth': 0.6,
            'levels': 5, 'level_height': 0.4, 'slots_per_level': 1}}])
        self.assertEqual(self.Row.browse(result['created'][-1]).location_id, self.warehouse.lot_stock_id)

    def test_delete(self):
        self._save(delete=[self.p06.id])
        self.assertFalse(self.p06.exists())

    def test_swapping_two_rows_is_allowed(self):
        # Each intermediate write would overlap the other row; only the end state is checked.
        self._save(write=[{'id': self.p05.id, 'vals': {'x': 20.5}}, {'id': self.p06.id, 'vals': {'x': 9.7}}])
        self.assertEqual((self.p05.x, self.p06.x), (20.5, 9.7))

    def test_overlap_refuses_everything(self):
        with self.assertRaisesRegex(ValidationError, 'overlap'):
            self._save(write=[{'id': self.p06.id, 'vals': {'y': 5.0}},          # valid on its own
                              {'id': self.p05.id, 'vals': {'x': 20.0}}])       # overlaps P06
        self.assertEqual(self.p06.y, 1.0)  # the valid part wasn't kept either
        self.assertEqual(self.p05.x, 9.7)

    def test_stock_guard_refuses_everything(self):
        slot = self.env['stock.location'].search([('name', '=', 'P05-07-1-A')])
        product = self.env['product.product'].create({'name': 'Rice', 'is_storable': True})
        self.env['stock.quant']._update_available_quantity(product, slot, 3)
        with self.assertRaisesRegex(UserError, 'P05-07-1-A'):
            self._save(write=[{'id': self.p06.id, 'vals': {'x': 30.0}},
                              {'id': self.p05.id, 'vals': {'bays': 6}}])
        self.assertEqual(self.p06.x, 20.5)
        self.assertEqual(self.p05.bays, 7)

    def test_only_layout_fields_are_accepted(self):
        for field, value in (('warehouse_id', self.warehouse.id), ('active', False),
                             ('storage_category_id', False), ('create_uid', 1)):
            with self.subTest(field=field), self.assertRaisesRegex(UserError, field):
                self._save(write=[{'id': self.p05.id, 'vals': {field: value}}])

    def test_rows_of_another_warehouse_are_refused(self):
        other = self.env['stock.warehouse'].create({'name': 'Second', 'code': 'WH2'})
        foreign = create_p05(self.env, other)
        with self.assertRaises(UserError):
            self._save(write=[{'id': foreign.id, 'vals': {'x': 1.0}}])
        with self.assertRaises(UserError):
            self._save(delete=[foreign.id])
        self.assertTrue(foreign.exists())

    def test_stock_user_cannot_save(self):
        user = new_test_user(self.env, login='wh3d_editor_user', groups='stock.group_stock_user')
        with self.assertRaises(AccessError):
            self.Row.with_user(user).wh3d_save_layout(self.warehouse.id, {
                'create': [], 'write': [{'id': self.p05.id, 'vals': {'x': 10.0}}], 'delete': []})
