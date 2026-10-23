from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestLocationSync(TransactionCase):
    """Editing, archiving or deleting a rack row keeps its locations in step, never losing stock."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')
        cls.stock = cls.warehouse.lot_stock_id
        cls.pr = cls.env['stock.location'].create({'name': 'PR', 'usage': 'internal', 'location_id': cls.stock.id})
        cls.pallet_cat = cls.env['stock.storage.category'].create({'name': 'Pallet rack – bulk'})
        cls.product = cls.env['product.product'].create({'name': 'Rice 25 kg', 'is_storable': True})

    def setUp(self):
        super().setUp()
        self.row = self.env['warehouse.rack.row'].create({
            'code': 'P05', 'kind': 'pallet', 'x': 9.7, 'y': 1.0, 'bays': 7, 'bay_width': 2.7,
            'depth': 1.1, 'levels': 5, 'level_height': 1.8, 'slots_per_level': 2,
            'warehouse_id': self.warehouse.id, 'location_id': self.pr.id,
        })

    def _locations(self, node=None, active=True):
        domain = [('wh3d_rack_row_id', '=', self.row.id), ('active', '=', active)]
        if node:
            domain.append(('wh3d_node', '=', node))
        return self.env['stock.location'].with_context(active_test=False).search(domain)

    def _slot(self, name):
        return self.env['stock.location'].with_context(active_test=False).search(
            [('wh3d_rack_row_id', '=', self.row.id), ('name', '=', name)])

    def _put_stock(self, location, qty=10):
        self.env['stock.quant']._update_available_quantity(self.product, location, qty)

    def test_rename_keeps_records_and_stock(self):
        slot = self._slot('P05-03-2-A')
        self._put_stock(slot)
        ids_before = self._locations().ids
        self.row.code = 'P15'
        self.assertEqual(self._locations().ids, ids_before)
        self.assertEqual(slot.name, 'P15-03-2-A')
        self.assertEqual(slot.complete_name, 'WH/Stock/PR/P15/P15-03/P15-03-2/P15-03-2-A')
        self.assertEqual(slot.quant_ids.quantity, 10)

    def test_moving_on_floor_plan_leaves_locations_alone(self):
        names_before = self._locations().mapped('complete_name')
        self.row.write({'x': 20.5, 'y': 2.0, 'bay_width': 2.8, 'depth': 1.2, 'level_height': 1.9})
        self.assertEqual(self._locations().mapped('complete_name'), names_before)

    def test_growing_adds_slots(self):
        self.row.bays = 8
        self.assertEqual(len(self._locations('slot')), 80)
        self.assertTrue(self._slot('P05-08-5-B').active)

    def test_shrinking_empty_row_archives_removed_slots(self):
        self.row.bays = 6
        self.assertEqual(len(self._locations('slot')), 60)
        archived = self._locations(active=False)
        self.assertEqual(len(archived), 1 + 5 + 10)  # bay P05-07, its 5 levels, 10 slots
        self.assertFalse(self._slot('P05-07-1-A').active)

    def test_shrinking_over_stock_is_refused(self):
        self._put_stock(self._slot('P05-07-1-A'))
        with self.assertRaisesRegex(UserError, 'P05-07-1-A'):
            self.row.bays = 6
        self.assertEqual(len(self._locations('slot')), 70)

    def test_shrinking_over_reserved_or_incoming_stock_is_refused(self):
        slot = self._slot('P05-07-1-A')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': slot.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id, 'product_uom_qty': 5,
                'location_id': self.env.ref('stock.stock_location_suppliers').id, 'location_dest_id': slot.id,
            })],
        })
        picking.action_confirm()
        with self.assertRaisesRegex(UserError, 'P05-07-1-A'):
            self.row.bays = 6

    def test_regrowing_reuses_archived_slots(self):
        slot = self._slot('P05-07-1-A')
        self.row.bays = 6
        self.row.bays = 7
        self.assertTrue(slot.active)
        self.assertEqual(len(self._locations('slot')), 70)
        self.assertFalse(self._locations(active=False))

    def test_fewer_levels_archives_top_levels(self):
        self.row.levels = 4
        self.assertEqual(len(self._locations('slot')), 56)
        self.assertEqual(len(self._locations('level')), 28)

    def test_storage_category_change_reaches_slots_only(self):
        self.row.storage_category_id = self.pallet_cat
        self.assertEqual(self._locations('slot').storage_category_id, self.pallet_cat)
        self.assertFalse(self._locations('bay').storage_category_id)

    def test_pallet_to_shelf_restructures_tree(self):
        self.row.write({'kind': 'shelf', 'slots_per_level': 1})
        self.assertEqual(len(self._locations('slot')), 35)
        self.assertFalse(self._locations('level'))
        # The archived level node P05-03-2 shares the new slot's name, so look among active slots.
        slot = self._locations('slot').filtered(lambda s: s.name == 'P05-03-2')
        self.assertEqual(slot.complete_name, 'WH/Stock/PR/P05/P05-03/P05-03-2')

    def test_moving_to_another_zone_moves_the_subtree(self):
        zone = self.env['stock.location'].create({'name': 'PR2', 'usage': 'internal', 'location_id': self.stock.id})
        self.row.location_id = zone
        self.assertEqual(self._slot('P05-03-2-A').complete_name, 'WH/Stock/PR2/P05/P05-03/P05-03-2/P05-03-2-A')

    def test_archiving_row_archives_its_locations(self):
        self.row.action_archive()
        self.assertFalse(self._locations())
        self.row.action_unarchive()
        self.assertEqual(len(self._locations('slot')), 70)
        self.assertFalse(self._locations(active=False))

    def test_archiving_row_with_stock_is_refused(self):
        self._put_stock(self._slot('P05-01-1-A'))
        with self.assertRaisesRegex(UserError, 'P05-01-1-A'):
            self.row.action_archive()
        self.assertTrue(self.row.active)

    def test_deleting_row_archives_its_locations(self):
        ids = self._locations().ids
        self.row.unlink()
        locations = self.env['stock.location'].with_context(active_test=False).browse(ids)
        self.assertEqual(len(locations.exists()), len(ids))
        self.assertFalse(any(locations.mapped('active')))

    def test_deleting_row_with_stock_is_refused(self):
        self._put_stock(self._slot('P05-01-1-A'))
        with self.assertRaisesRegex(UserError, 'P05-01-1-A'):
            self.row.unlink()
        self.assertTrue(self.row.exists())

    # --- Code-review fixes (T3c) ---

    def _confirmed_receipt_into(self, location):
        supplier = self.env.ref('stock.stock_location_suppliers')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'location_id': supplier.id, 'location_dest_id': location.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id, 'product_uom_qty': 5,
                'location_id': supplier.id, 'location_dest_id': location.id,
            })],
        })
        picking.action_confirm()
        return picking

    def test_pallet_to_shelf_keeps_stock_in_surviving_slot(self):
        # Review #1: slot A survives (renamed, re-parented), so its stock must not block the change.
        slot = self._slot('P05-03-2-A')
        self._put_stock(slot)
        self.row.write({'kind': 'shelf', 'slots_per_level': 1})
        self.assertTrue(slot.active)
        self.assertEqual(slot.name, 'P05-03-2')
        self.assertEqual(slot.quant_ids.quantity, 10)

    def test_shrinking_over_transfer_into_user_sublocation_is_refused(self):
        # Review #2: a hand-made bin below a removed slot counts too.
        left = self.env['stock.location'].create({
            'name': 'Left', 'usage': 'internal', 'location_id': self._slot('P05-07-1-A').id})
        self._confirmed_receipt_into(left)
        with self.assertRaisesRegex(UserError, 'Left'):
            self.row.bays = 6
        self.assertTrue(left.active)

    def test_falsy_active_value_still_checks_transfers(self):
        # Review #4: write({'active': 0}) must be checked like write({'active': False}).
        self._confirmed_receipt_into(self._slot('P05-01-1-A'))
        with self.assertRaisesRegex(UserError, 'P05-01-1-A'):
            self.row.write({'active': 0})
        self.assertTrue(self.row.active)

    def test_regenerate_checks_transfers_before_archiving_extras(self):
        # Review #5: a stray node (bay 9 of a 7-bay row) with an open receipt must not be archived silently.
        stray = self.env['stock.location'].create({
            'name': 'P05-09-1-A', 'usage': 'internal', 'location_id': self._slot('P05-01-1-A').location_id.id,
            'wh3d_rack_row_id': self.row.id, 'wh3d_node': 'slot', 'wh3d_bay': 9, 'wh3d_level': 1, 'wh3d_position': 1,
        })
        self._confirmed_receipt_into(stray)
        with self.assertRaisesRegex(UserError, 'P05-09-1-A'):
            self.row.action_generate_locations()
        self.assertTrue(stray.active)

    def test_changing_warehouse_of_a_row_with_locations_is_refused(self):
        # Review #6: locations can't change company, so moving a row between warehouses is not supported.
        other = self.env['stock.warehouse'].create({'name': 'Second', 'code': 'WH2'})
        zone = self.env['stock.location'].create({'name': 'PR', 'usage': 'internal', 'location_id': other.lot_stock_id.id})
        with self.assertRaisesRegex(UserError, 'warehouse'):
            self.row.write({'warehouse_id': other.id, 'location_id': zone.id})
