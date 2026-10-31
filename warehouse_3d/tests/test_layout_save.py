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

    def _save(self, create=(), write=(), delete=(), areas=None):
        changes = {'create': list(create), 'write': list(write), 'delete': list(delete)}
        if areas is not None:
            changes['areas'] = areas
        return self.Row.wh3d_save_layout(self.warehouse.id, changes)

    def _area(self, **overrides):
        vals = {'name': 'Receiving', 'kind': 'area', 'x': 25.0, 'y': 25.0, 'width': 5.0, 'depth': 5.0,
                'warehouse_id': self.warehouse.id}
        vals.update(overrides)
        return self.env['warehouse.layout.area'].create(vals)

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
        slot = self.env['stock.location'].search([('name', '=', 'P05-07-1-A'), ('warehouse_id', '=', self.warehouse.id)])
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

    # --- areas and dock doors ride in the same save (changes['areas'])

    def test_area_create_write_delete_in_one_save(self):
        keep, drop = self._area(name='Keep'), self._area(name='Drop', x=35.0)
        result = self._save(areas={
            'create': [{'tmp_id': -1, 'vals': {'name': 'Packing', 'kind': 'area', 'x': 40.0, 'y': 25.0,
                                               'width': 6.0, 'depth': 4.0, 'color': '#aabbcc'}},
                       {'tmp_id': -2, 'vals': {'name': 'Door 1', 'kind': 'dock', 'x': 3.0, 'y': 38.4,
                                               'width': 3.0, 'depth': 1.6}}],
            'write': [{'id': keep.id, 'vals': {'x': 26.0, 'name': 'Moved'}}],
            'delete': [drop.id]})
        Area = self.env['warehouse.layout.area']
        self.assertEqual((keep.x, keep.name), (26.0, 'Moved'))
        self.assertFalse(drop.exists())
        self.assertEqual(Area.browse(result['created_areas'][-1]).color, '#aabbcc')
        self.assertEqual(Area.browse(result['created_areas'][-2]).kind, 'dock')
        self.assertEqual({a['name'] for a in result['layout']['areas']}, {'Moved', 'Packing', 'Door 1'})
        self.assertTrue(all('color' in a for a in result['layout']['areas']))

    def test_rows_and_areas_save_together(self):
        result = self._save(write=[{'id': self.p05.id, 'vals': {'x': 11.0}}],
                            areas={'create': [{'tmp_id': -1, 'vals': {
                                'name': 'Office', 'kind': 'area', 'x': 5.0, 'y': 5.0, 'width': 3.0, 'depth': 3.0}}]})
        self.assertEqual(self.p05.x, 11.0)
        self.assertEqual(len(result['created_areas']), 1)

    def test_area_overlapping_a_row_refuses_everything(self):
        area = self._area()
        with self.assertRaisesRegex(ValidationError, 'overlap'):
            self._save(write=[{'id': self.p06.id, 'vals': {'y': 5.0}}],        # valid on its own
                       areas={'write': [{'id': area.id, 'vals': {'x': 20.0, 'y': 5.0}}]})  # lands on P06
        self.assertEqual((area.x, self.p06.y), (25.0, 1.0))

    def test_moving_a_row_onto_an_area_refuses_everything(self):
        area = self._area(x=30.0, y=5.0)
        with self.assertRaisesRegex(ValidationError, 'overlap'):
            self._save(write=[{'id': self.p06.id, 'vals': {'x': 29.5}}],
                       areas={'write': [{'id': area.id, 'vals': {'name': 'Renamed'}}]})
        self.assertEqual((self.p06.x, area.name), (20.5, 'Receiving'))

    def test_swapping_a_row_and_an_area_is_allowed(self):
        # Only the end state is checked: the row moves into the area's spot as the area moves out.
        area = self._area(x=40.0, y=1.0, width=1.1, depth=5.0)
        self._save(write=[{'id': self.p06.id, 'vals': {'x': 40.0}}],
                   areas={'write': [{'id': area.id, 'vals': {'x': 20.5}}]})
        self.assertEqual((self.p06.x, area.x), (40.0, 20.5))

    def test_floating_dock_refuses_everything(self):
        with self.assertRaisesRegex(ValidationError, 'wall'):
            self._save(write=[{'id': self.p05.id, 'vals': {'x': 11.0}}],
                       areas={'create': [{'tmp_id': -1, 'vals': {
                           'name': 'Door', 'kind': 'dock', 'x': 10.0, 'y': 10.0, 'width': 3.0, 'depth': 1.6}}]})
        self.assertEqual(self.p05.x, 9.7)

    def test_area_outside_building_refuses_everything(self):
        with self.assertRaisesRegex(ValidationError, 'inside'):
            self._save(areas={'create': [{'tmp_id': -1, 'vals': {
                'name': 'Big', 'kind': 'area', 'x': 50.0, 'y': 25.0, 'width': 20.0, 'depth': 5.0}}]})

    def test_only_area_fields_are_accepted(self):
        area = self._area()
        for field, value in (('warehouse_id', self.warehouse.id), ('create_uid', 1), ('company_id', 1)):
            with self.subTest(field=field), self.assertRaisesRegex(UserError, field):
                self._save(areas={'write': [{'id': area.id, 'vals': {field: value}}]})

    def test_areas_of_another_warehouse_are_refused(self):
        other = self.env['stock.warehouse'].create({'name': 'Second', 'code': 'WH2'})
        foreign = self._area(warehouse_id=other.id)
        with self.assertRaises(UserError):
            self._save(areas={'write': [{'id': foreign.id, 'vals': {'x': 1.0}}]})
        with self.assertRaises(UserError):
            self._save(areas={'delete': [foreign.id]})
        self.assertTrue(foreign.exists())

    def test_stock_user_cannot_save_areas(self):
        area = self._area()
        user = new_test_user(self.env, login='wh3d_area_user', groups='stock.group_stock_user')
        with self.assertRaises(AccessError):
            self.Row.with_user(user).wh3d_save_layout(self.warehouse.id, {
                'create': [], 'write': [], 'delete': [], 'areas': {'delete': [area.id]}})
