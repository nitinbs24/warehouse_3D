from odoo.tests import Form, TransactionCase

from .common import create_p05, template_rows, template_warehouse


class TestTemplateCatalogue(TransactionCase):
    """The template warehouse's catalogue, loaded as demo data (databases created with --with-demo)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = template_warehouse(cls.env)
        cls.bulk =cls.env.ref('warehouse_3d.categ_bulk')
        cls.small = cls.env.ref('warehouse_3d.categ_small_parts')
        cls.products = cls.env['product.template'].search([('categ_id', 'in', (cls.bulk | cls.small).ids)])

    def test_about_120_products_split_between_bulk_and_small_parts(self):
        self.assertTrue(100 <= len(self.products) <= 200, len(self.products))
        bulk = self.products.filtered(lambda p: p.categ_id == self.bulk)
        self.assertTrue(40 <= len(bulk) <= len(self.products) - 40, f"{len(bulk)} bulk products")

    def test_every_product_has_dimensions_weight_volume_and_class(self):
        for product in self.products:
            with self.subTest(product=product.default_code):
                self.assertTrue(product.is_storable)
                self.assertTrue(product.default_code)
                self.assertGreater(min(product.wh3d_length, product.wh3d_width, product.wh3d_height), 0)
                self.assertGreater(product.weight, 0)
                # Odoo keeps volume to 2 decimals (decimal.precision "Volume"): small parts read 0.00 m³,
                # which is why fill % uses the wh3d_ dimensions instead.
                self.assertAlmostEqual(
                    product.volume, product.wh3d_length * product.wh3d_width * product.wh3d_height, delta=0.006)
                self.assertIn(product.wh3d_abc_class, ('A', 'B', 'C'))

    def test_codes_are_unique(self):
        codes = self.products.mapped('default_code')
        self.assertEqual(len(codes), len(set(codes)))

    def test_about_a_fifth_are_fast_movers(self):
        share = len(self.products.filtered(lambda p: p.wh3d_abc_class == 'A')) / len(self.products)
        self.assertTrue(0.15 <= share <= 0.25, f"A share {share:.2f}")

    def test_package_types(self):
        pallet = self.env.ref('warehouse_3d.package_pallet')
        self.assertEqual((pallet.packaging_length, pallet.width, pallet.height), (1200, 1000, 1500))  # mm
        self.assertGreater(pallet.max_weight, 0)
        for xmlid in ('warehouse_3d.package_carton', 'warehouse_3d.package_tote'):
            self.assertGreater(self.env.ref(xmlid).max_weight, 0)

    def test_storage_categories(self):
        rack = self.env.ref('warehouse_3d.storcat_pallet_bulk')
        self.assertEqual(rack.allow_new_product, 'empty')
        self.assertEqual(rack.package_capacity_ids.package_type_id, self.env.ref('warehouse_3d.package_pallet'))
        self.assertEqual(rack.package_capacity_ids.quantity, 1)
        shelf = self.env.ref('warehouse_3d.storcat_shelf_small')
        self.assertEqual(shelf.allow_new_product, 'mixed')
        self.assertGreater(shelf.max_weight, 0)
        self.assertTrue(self.env.ref('warehouse_3d.storcat_golden_zone'))

    def test_zones_are_internal_under_stock(self):
        for xmlid, name in (('warehouse_3d.zone_pr', 'WHV/Stock/PR'), ('warehouse_3d.zone_sh', 'WHV/Stock/SH')):
            zone = self.env.ref(xmlid)
            self.assertEqual((zone.complete_name, zone.usage), (name, 'internal'))

    def test_putaway_rules(self):
        rules = self.env['stock.putaway.rule'].search([('location_in_id', '=', self.warehouse.lot_stock_id.id)])
        by_categ = {r.category_id: r for r in rules}
        self.assertEqual(by_categ[self.bulk].location_out_id, self.env.ref('warehouse_3d.zone_pr'))
        self.assertEqual(by_categ[self.bulk].sublocation, 'closest_location')
        self.assertEqual(by_categ[self.small].location_out_id, self.env.ref('warehouse_3d.zone_sh'))

    def test_standard_putaway_fills_empty_pallet_slots_in_order(self):
        # Odoo's own putaway on the template data: bulk goods go to the first empty pallet slot
        # (slots are tried in name order; T14's opening stock already fills some).
        product = self.products.filtered(lambda p: p.categ_id == self.bulk)[:1].product_variant_id
        stock = self.warehouse.lot_stock_id
        first = stock._get_putaway_strategy(product, quantity=1)
        self.assertEqual(first.wh3d_node, 'slot')
        self.assertFalse(first.quant_ids.filtered(lambda q: q.quantity > 0), "putaway chose a slot with stock")
        empty_slots = self.env['stock.location'].search(
            [('location_id', 'child_of', self.env.ref('warehouse_3d.zone_pr').id), ('wh3d_node', '=', 'slot')],
            order='complete_name').filtered(lambda loc: not loc.quant_ids.filtered(lambda q: q.quantity > 0))
        self.assertEqual(first, empty_slots[0])
        self.env['stock.quant']._update_available_quantity(product, first, 1)
        self.assertEqual(stock._get_putaway_strategy(product, quantity=1), empty_slots[1])  # first one is taken

    def test_abc_class_on_product_form(self):
        form = Form(self.env['product.template'])
        form.name = 'Test product'
        form.wh3d_abc_class = 'B'
        self.assertEqual(form.save().wh3d_abc_class, 'B')


class TestTemplateLayout(TransactionCase):
    """The template warehouse "Warehaven DC" (WHV): layout from docs/CLAUDE.md and ~65 % opening stock."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = template_warehouse(cls.env)
        cls.scene =cls.warehouse.wh3d_get_scene()
        cls.row_kind = {r['id']: r['kind'] for r in cls.scene['rows']}

    def _slots(self, kind):
        return [s for s in self.scene['slots'] if self.row_kind[s['row_id']] == kind]

    def test_building_and_rows_match_the_handoff(self):
        self.assertEqual((self.warehouse.code, self.warehouse.name), ('WHV', 'Warehaven DC'))
        self.assertEqual(self.scene['building'], {'length': 60.0, 'width': 40.0, 'height': 10.0})
        expected = {r['code']: (r['kind'], r['x'], r['y']) for r in template_rows()}
        actual = {r['code']: (r['kind'], r['x'], r['y']) for r in self.scene['rows']}
        self.assertEqual(actual, expected)

    def test_slot_counts(self):
        self.assertEqual(len(self._slots('pallet')), 980)
        self.assertEqual(len(self._slots('shelf')), 1360)

    def test_areas_and_docks(self):
        areas = [a['name'] for a in self.scene['areas'] if a['kind'] == 'area']
        self.assertEqual(sorted(areas), ['Charging', 'Office', 'Packing', 'Receiving', 'Shipping'])
        self.assertEqual(len([a for a in self.scene['areas'] if a['kind'] == 'dock']), 6)

    def test_areas_have_their_own_colours_in_the_editor_palette(self):
        colours = {a['name']: a['color'] for a in self.scene['areas'] if a['kind'] == 'area'}
        self.assertEqual(colours, {'Receiving': '#8fb8de', 'Charging': '#f2d27a', 'Office': '#c9c9c9',
                                   'Packing': '#e8a79c', 'Shipping': '#a8d5a2'})

    def test_slots_use_the_template_storage_categories(self):
        pallet = self.env.ref('warehouse_3d.storcat_pallet_bulk')
        shelf = self.env.ref('warehouse_3d.storcat_shelf_small')
        rows = self.env['warehouse.rack.row'].search([('warehouse_id', '=', self.warehouse.id)])
        for row in rows:
            with self.subTest(row=row.code):
                self.assertEqual(row.storage_category_id, pallet if row.kind == 'pallet' else shelf)

    def test_about_two_thirds_of_slots_are_stocked(self):
        for kind in ('pallet', 'shelf'):
            with self.subTest(kind=kind):
                slots = self._slots(kind)
                share = len([s for s in slots if s['stock']]) / len(slots)
                self.assertTrue(0.60 <= share <= 0.70, f"{kind} occupancy {share:.2f}")

    def test_each_fill_band_is_well_represented(self):
        # So "Colour by occupancy" shows all three colours in the demo.
        fills = [s['stock']['fill'] for s in self.scene['slots'] if s['stock']]
        bands = {'low': [f for f in fills if f < 0.5], 'mid': [f for f in fills if 0.5 <= f <= 0.9],
                 'high': [f for f in fills if f > 0.9]}
        for band, members in bands.items():
            with self.subTest(band=band):
                self.assertGreaterEqual(len(members) / len(fills), 0.15, f"{band}: {len(members)} of {len(fills)}")
        self.assertTrue(all(f <= 1.0 for f in fills), "no slot is stocked beyond its volume")

    def test_one_product_per_slot_of_the_right_kind(self):
        bulk = self.env.ref('warehouse_3d.categ_bulk')
        small = self.env.ref('warehouse_3d.categ_small_parts')
        products = self.env['product.product'].browse(
            {s['stock']['product_id'] for s in self.scene['slots'] if s['stock']})
        categ = {p.id: p.categ_id for p in products}
        for kind, expected in (('pallet', bulk), ('shelf', small)):
            stocked = [s for s in self._slots(kind) if s['stock']]
            with self.subTest(kind=kind):
                self.assertFalse([s for s in stocked if s['stock']['mixed']])
                self.assertEqual({categ[s['stock']['product_id']] for s in stocked}, {expected})

    def test_fast_movers_are_over_represented(self):
        stocked = [s['stock']['product_id'] for s in self.scene['slots'] if s['stock']]
        classes = {p.id: p.wh3d_abc_class for p in self.env['product.product'].browse(set(stocked))}
        share = sum(classes[p] == 'A' for p in stocked) / len(stocked)
        self.assertGreater(share, 0.30, f"A share among stocked slots {share:.2f} (catalogue: 0.20)")

    def test_opening_stock_plan_is_deterministic(self):
        Warehouse = self.env['stock.warehouse']
        first = Warehouse._wh3d_plan_template_stock(self.warehouse, seed=7)
        second = Warehouse._wh3d_plan_template_stock(self.warehouse, seed=7)
        self.assertEqual([(loc.id, p.id, q) for loc, p, q in first], [(loc.id, p.id, q) for loc, p, q in second])
        other = Warehouse._wh3d_plan_template_stock(self.warehouse, seed=8)
        self.assertNotEqual([(loc.id, p.id) for loc, p, q in first], [(loc.id, p.id) for loc, p, q in other])

    def test_3d_view_opens_the_warehouse_that_has_a_layout(self):
        # WH (the default warehouse) has no rack rows in this database; the template warehouse has.
        self.assertFalse(self.env['warehouse.rack.row'].search_count([('warehouse_id', '=', self.env.ref('stock.warehouse0').id)]))
        self.assertEqual(self.env['stock.warehouse'].wh3d_default_warehouse_id(), self.warehouse.id)

    def test_the_first_warehouse_with_rows_wins(self):
        wh = self.env.ref('stock.warehouse0')
        create_p05(self.env, wh)
        self.assertEqual(self.env['stock.warehouse'].wh3d_default_warehouse_id(), wh.id)
