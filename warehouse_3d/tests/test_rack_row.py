from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, new_test_user
from odoo.tools import mute_logger
from odoo.tools.convert import convert_file
from odoo.tools.safe_eval import safe_eval

from .common import create_p05, create_zone, template_rows


class TestRackRow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')
        cls.zone = cls.env['stock.location'].create({
            'name': 'PR', 'usage': 'internal', 'location_id': cls.warehouse.lot_stock_id.id,
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

    def test_module_update_keeps_storage_locations_off(self):
        # CodeRabbit review: the setting is switched on at install only; an admin's later "off" survives -u.
        group = self.env.ref('stock.group_stock_multi_locations')
        user_group = self.env.ref('base.group_user')
        user_group.implied_ids = [Command.unlink(group.id)]
        convert_file(self.env, 'warehouse_3d', 'data/res_groups.xml', {}, mode='update')
        self.assertNotIn(group, user_group.implied_ids)

    def test_zone_dropdown_offers_internal_locations_only(self):
        # CodeRabbit review: Virtual locations were offered although _check_location_internal refuses them.
        virtual = self.env['stock.location'].create(
            {'name': 'VZ', 'usage': 'view', 'location_id': self.warehouse.lot_stock_id.id})
        domain = safe_eval(self.Row._fields['location_id'].domain, {'warehouse_id': self.warehouse.id})
        offered = self.env['stock.location'].search(domain)
        self.assertIn(self.zone, offered)
        self.assertNotIn(virtual, offered)
        self.assertEqual(set(offered.mapped('usage')), {'internal'})

    def test_stock_manager_can_write(self):
        row = self.Row.create(self._vals())
        manager = new_test_user(self.env, login='wh3d_manager', groups='stock.group_stock_manager')
        row.with_user(manager).write({'bays': 8})
        self.assertEqual(row.bays, 8)


class TestRackRowLayout(TransactionCase):
    """Rack rows stay inside the building and don't overlap (the editor relies on this)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')  # 60 × 40 m by default
        cls.zone = create_zone(cls.env, cls.warehouse)

    def _row(self, **overrides):
        return create_p05(self.env, self.warehouse, self.zone, **overrides)

    def test_row_must_lie_inside_the_building(self):
        # P05 is 1.1 m deep (along x) and 7 × 2.7 = 18.9 m long (along y).
        # (Negative x/y is already refused by the database rule tested in TestRackRow.)
        cases = {'past the right wall': {'x': 59.0}, 'past the far wall': {'y': 22.0}}
        for label, overrides in cases.items():
            # savepoint: a refused create must not leave its row behind for the next case
            with self.subTest(label), self.assertRaisesRegex(ValidationError, 'inside'), self.cr.savepoint():
                self._row(**overrides)

    def test_row_touching_the_walls_is_allowed(self):
        self._row(x=60 - 1.1, y=40 - 18.9)

    def test_growing_a_row_through_the_wall_is_refused(self):
        row = self._row(y=20.0)
        with self.assertRaises(ValidationError):
            row.bays = 8  # 20 + 21.6 > 40

    def test_overlapping_rows_are_refused_naming_both(self):
        self._row()
        with self.assertRaisesRegex(ValidationError, r'(?s)P06.*P05|P05.*P06'):
            self._row(code='P06', x=10.2)  # 0.5 m into P05

    def test_rows_touching_back_to_back_are_allowed(self):
        self._row()
        self._row(code='P06', x=9.7 + 1.1)

    def test_rows_in_different_stretches_of_floor_dont_clash(self):
        self._row()
        self._row(code='P06', y=20.0)  # P05 ends at y 19.9

    def test_moving_a_row_onto_another_is_refused(self):
        self._row()
        p06 = self._row(code='P06', x=20.5)
        with self.assertRaises(ValidationError):
            p06.x = 9.9

    def test_archived_rows_dont_block(self):
        self._row().action_archive()
        self._row(code='P06')

    def test_reactivating_onto_a_newer_row_is_refused(self):
        p05 = self._row()
        p05.action_archive()
        self._row(code='P06')
        with self.assertRaises(ValidationError):
            p05.action_unarchive()

    def test_rows_in_other_warehouses_dont_clash(self):
        self._row()
        other = self.env['stock.warehouse'].create({'name': 'Second', 'code': 'WH2'})
        create_p05(self.env, other)

    def test_shrinking_the_building_below_a_row_is_refused(self):
        self._row(x=36.7)
        with self.assertRaisesRegex(ValidationError, 'P05'):
            self.warehouse.wh3d_length = 37.0

    def test_all_31_template_rows_are_valid(self):
        Row = self.env['warehouse.rack.row']
        sh = create_zone(self.env, self.warehouse, 'SH')
        rows = Row.create([dict(r, warehouse_id=self.warehouse.id,
                                location_id=(self.zone if r['kind'] == 'pallet' else sh).id)
                           for r in template_rows()])
        self.assertEqual(len(rows), 31)
