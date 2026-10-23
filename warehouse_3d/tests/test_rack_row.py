from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user
from odoo.tools import mute_logger


class TestRackRow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')
        cls.zone = cls.env['stock.location'].create({
            'name': 'PR', 'usage': 'view', 'location_id': cls.warehouse.lot_stock_id.id,
        })
        cls.Row = cls.env['warehouse.rack.row']

    def _vals(self, **overrides):
        # The handoff's P05 record.
        vals = {
            'code': 'P05', 'kind': 'pallet', 'x': 9.7, 'y': 1.0, 'bays': 7, 'bay_width': 2.7,
            'depth': 1.1, 'levels': 5, 'level_height': 1.8, 'slots_per_level': 2,
            'warehouse_id': self.warehouse.id, 'location_id': self.zone.id,
        }
        vals.update(overrides)
        return vals

    def test_create_handoff_record(self):
        row = self.Row.create(self._vals())
        self.assertEqual(row.display_name, 'P05')
        self.assertEqual((row.bays, row.levels, row.slots_per_level), (7, 5, 2))

    def test_rejects_non_positive_dimensions(self):
        for field in ('bays', 'bay_width', 'depth', 'levels', 'level_height', 'slots_per_level'):
            with self.subTest(field=field), self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
                self.Row.create(self._vals(**{field: 0}))

    def test_rejects_negative_position(self):
        for field in ('x', 'y'):
            with self.subTest(field=field), self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
                self.Row.create(self._vals(**{field: -0.1}))

    def test_rejects_bad_code_format(self):
        for code in ('P5', 'p05', 'P005', 'PX5', '05'):
            with self.subTest(code=code), self.assertRaises(ValidationError):
                self.Row.create(self._vals(code=code))

    def test_rejects_duplicate_code_in_warehouse(self):
        self.Row.create(self._vals())
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            self.Row.create(self._vals(x=20.0))

    def test_shelf_has_one_slot_per_level(self):
        with self.assertRaises(ValidationError):
            self.Row.create(self._vals(code='S01', kind='shelf', slots_per_level=2))
        row = self.Row.create(self._vals(code='S01', kind='shelf', slots_per_level=1))
        self.assertEqual(row.kind, 'shelf')

    def test_at_most_26_slots_per_level(self):
        # Positions are lettered A..Z.
        with self.assertRaises(ValidationError):
            self.Row.create(self._vals(slots_per_level=27))

    def test_zone_location_must_be_in_warehouse_stock(self):
        outside = self.env['stock.location'].create({'name': 'Elsewhere', 'usage': 'view'})
        with self.assertRaises(ValidationError):
            self.Row.create(self._vals(location_id=outside.id))

    def test_stock_user_reads_but_cannot_write(self):
        row = self.Row.create(self._vals())
        user = new_test_user(self.env, login='wh3d_user', groups='stock.group_stock_user')
        self.assertEqual(row.with_user(user).code, 'P05')
        with self.assertRaises(AccessError):
            row.with_user(user).write({'bays': 8})

    def test_storage_locations_setting_enabled_like_settings_page(self):
        # Ticking the setting also re-enables the "New" button on Locations by archiving these views.
        self.assertIn(self.env.ref('stock.group_stock_multi_locations'), self.env.ref('base.group_user').implied_ids)
        self.assertFalse(self.env.ref('stock.stock_location_view_tree2_editable').active)
        self.assertFalse(self.env.ref('stock.stock_location_view_form_editable').active)

    def test_stock_manager_can_write(self):
        row = self.Row.create(self._vals())
        manager = new_test_user(self.env, login='wh3d_manager', groups='stock.group_stock_manager')
        row.with_user(manager).write({'bays': 8})
        self.assertEqual(row.bays, 8)
