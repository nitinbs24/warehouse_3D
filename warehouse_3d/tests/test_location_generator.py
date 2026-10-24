import time

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestLocationGenerator(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')
        cls.stock = cls.warehouse.lot_stock_id
        Location = cls.env['stock.location']
        cls.pr = Location.create({'name': 'PR', 'usage': 'internal', 'location_id': cls.stock.id})
        cls.sh = Location.create({'name': 'SH', 'usage': 'internal', 'location_id': cls.stock.id})
        cls.pallet_cat = cls.env['stock.storage.category'].create({'name': 'Pallet rack – bulk'})
        cls.Row = cls.env['warehouse.rack.row']

    def _pallet(self, **overrides):
        vals = {
            'code': 'P05', 'kind': 'pallet', 'x': 9.7, 'y': 1.0, 'bays': 7, 'bay_width': 2.7,
            'depth': 1.1, 'levels': 5, 'level_height': 1.8, 'slots_per_level': 2,
            'warehouse_id': self.warehouse.id, 'location_id': self.pr.id,
            'storage_category_id': self.pallet_cat.id,
        }
        vals.update(overrides)
        return self.Row.create(vals)

    def _shelf(self, **overrides):
        vals = {
            'code': 'S04', 'kind': 'shelf', 'x': 41.0, 'y': 2.0, 'bays': 16, 'bay_width': 1.0,
            'depth': 0.6, 'levels': 5, 'level_height': 0.4, 'slots_per_level': 1,
            'warehouse_id': self.warehouse.id, 'location_id': self.sh.id,
        }
        vals.update(overrides)
        return self.Row.create(vals)

    def _nodes(self, row, node):
        return self.env['stock.location'].search([('wh3d_rack_row_id', '=', row.id), ('wh3d_node', '=', node)])

    def test_pallet_row_creates_70_slots(self):
        row = self._pallet()
        slots = self._nodes(row, 'slot')
        self.assertEqual(len(slots), 70)
        names = set(slots.mapped('name'))
        self.assertIn('P05-01-1-A', names)
        self.assertIn('P05-07-5-B', names)
        self.assertEqual(row.slot_count, 70)

    def test_pallet_tree_shape(self):
        row = self._pallet()
        self.assertEqual(len(self._nodes(row, 'row')), 1)
        self.assertEqual(len(self._nodes(row, 'bay')), 7)
        self.assertEqual(len(self._nodes(row, 'level')), 35)

    def test_pallet_slot_full_path_and_indices(self):
        row = self._pallet()
        slot = self.env['stock.location'].search([('wh3d_rack_row_id', '=', row.id), ('name', '=', 'P05-03-2-A')])
        self.assertEqual(slot.complete_name, 'WH/Stock/PR/P05/P05-03/P05-03-2/P05-03-2-A')
        self.assertEqual((slot.wh3d_bay, slot.wh3d_level, slot.wh3d_position), (3, 2, 1))
        self.assertEqual(slot.usage, 'internal')
        self.assertEqual(slot.storage_category_id, self.pallet_cat)

    def test_only_slots_carry_storage_category(self):
        row = self._pallet()
        for node in ('row', 'bay', 'level'):
            with self.subTest(node=node):
                nodes = self._nodes(row, node)
                self.assertFalse(nodes.storage_category_id)
                self.assertEqual(set(nodes.mapped('usage')), {'internal'})

    def test_shelf_row_creates_80_bins_without_level_nodes(self):
        row = self._shelf()
        slots = self._nodes(row, 'slot')
        self.assertEqual(len(slots), 80)
        self.assertFalse(self._nodes(row, 'level'))
        slot = slots.filtered(lambda s: s.name == 'S04-10-3')
        self.assertEqual(slot.complete_name, 'WH/Stock/SH/S04/S04-10/S04-10-3')
        self.assertEqual((slot.wh3d_bay, slot.wh3d_level, slot.wh3d_position), (10, 3, 1))

    def test_generating_twice_creates_no_duplicates(self):
        row = self._pallet()
        before = self.env['stock.location'].search_count([('wh3d_rack_row_id', '=', row.id)])
        row.action_generate_locations()
        after = self.env['stock.location'].search_count([('wh3d_rack_row_id', '=', row.id)])
        self.assertEqual(before, after)
        self.assertEqual(before, 1 + 7 + 35 + 70)

    def test_regenerate_recreates_missing_slot(self):
        row = self._pallet()
        slot = self._nodes(row, 'slot').filtered(lambda s: s.name == 'P05-03-2-A')
        slot.unlink()
        row.action_generate_locations()
        self.assertEqual(len(self._nodes(row, 'slot')), 70)

    def test_zone_location_must_be_internal(self):
        # A Virtual (view) zone would cut every generated path short.
        virtual = self.env['stock.location'].create({'name': 'VZ', 'usage': 'view', 'location_id': self.stock.id})
        with self.assertRaises(ValidationError):
            self._pallet(location_id=virtual.id)

    def test_closest_putaway_lands_in_a_slot(self):
        row = self._pallet()
        product = self.env['product.product'].create({'name': 'Rice 25 kg', 'is_storable': True})
        self.env['stock.putaway.rule'].create({
            'location_in_id': self.stock.id, 'location_out_id': self.pr.id, 'product_id': product.id,
            'sublocation': 'closest_location', 'storage_category_id': self.pallet_cat.id,
        })
        dest = self.stock._get_putaway_strategy(product, quantity=1)
        self.assertEqual(dest.wh3d_rack_row_id, row)
        self.assertEqual(dest.wh3d_node, 'slot')

    def test_fourteen_pallet_rows_generate_quickly(self):
        start = time.time()
        for i in range(14):
            self._pallet(code=f'P{i + 1:02d}', x=i * 2.6)
        elapsed = time.time() - start
        self.assertEqual(self.env['stock.location'].search_count(
            [('wh3d_node', '=', 'slot'), ('warehouse_id', '=', self.warehouse.id)]), 980)
        self.assertLess(elapsed, 30, f"generation took {elapsed:.1f}s")
