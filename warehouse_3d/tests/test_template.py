from collections import defaultdict
from contextlib import closing

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

    def test_putaway_rules_are_smart_and_the_closest_location_ones_are_kept_inactive(self):
        Rule = self.env['stock.putaway.rule'].with_context(active_test=False)
        stock = self.warehouse.lot_stock_id
        smart = Rule.search([('location_in_id', '=', stock.id), ('sublocation', '=', 'wh3d_smart')])
        self.assertEqual({r.category_id: r.location_out_id for r in smart},
                         {self.bulk: self.env.ref('warehouse_3d.zone_pr'), self.small: self.env.ref('warehouse_3d.zone_sh')})
        self.assertTrue(all(smart.mapped('active')))
        closest = Rule.search([('location_in_id', '=', stock.id), ('sublocation', '=', 'closest_location')])
        self.assertEqual(len(closest), 2)
        self.assertFalse(any(closest.mapped('active')))  # kept for the experiment (T32)

    def test_smart_putaway_sends_bulk_goods_to_an_empty_allowed_pallet_slot(self):
        product = self.products.filtered(lambda p: p.default_code == 'PR-1001').product_variant_id
        slot = self.warehouse.lot_stock_id._get_putaway_strategy(product, quantity=1)
        self.assertEqual(slot.wh3d_node, 'slot')
        self.assertEqual(slot.wh3d_rack_row_id.kind, 'pallet')
        self.assertFalse(slot.quant_ids.filtered(lambda q: q.quantity > 0), "putaway chose a slot with stock")

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

    def _stockable_slots(self, kind):
        """Slots of rows that take putaway: not quarantine/returns, not amber."""
        closed = {r['id'] for r in self.scene['rows'] if r['purpose'] != 'normal' or r['inspection_status'] != 'green'}
        return [s for s in self._slots(kind) if s['row_id'] not in closed]

    def test_building_and_rows_match_the_handoff(self):
        self.assertEqual((self.warehouse.code, self.warehouse.name), ('WHV', 'Warehaven DC'))
        self.assertEqual(self.scene['building'], {'length': 60.0, 'width': 40.0, 'height': 10.0})
        expected = {r['code']: (r['kind'], r['x'], r['y']) for r in template_rows()}
        actual = {r['code']: (r['kind'], r['x'], r['y']) for r in self.scene['rows']}
        self.assertEqual(actual, expected)

    def test_slot_counts(self):
        self.assertEqual(len(self._slots('pallet')), 896)  # 980 less two levels of the 3 cold rows
        self.assertEqual(len(self._slots('shelf')), 1360)

    def test_areas_and_docks(self):
        areas = [a['name'] for a in self.scene['areas'] if a['kind'] == 'area']
        self.assertEqual(sorted(areas), ['Charging', 'Office', 'Packing', 'Receiving', 'Shipping'])
        self.assertEqual(len([a for a in self.scene['areas'] if a['kind'] == 'dock']), 6)

    def test_areas_have_their_own_colours_in_the_editor_palette(self):
        colours = {a['name']: a['color'] for a in self.scene['areas'] if a['kind'] == 'area'}
        self.assertEqual({n: colours[n] for n in ('Receiving', 'Charging', 'Office', 'Packing', 'Shipping')},
                         {'Receiving': '#8fb8de', 'Charging': '#f2d27a', 'Office': '#c9c9c9',
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
                slots = self._stockable_slots(kind)
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

    def test_a_product_without_weight_does_not_break_the_planner(self):
        self.env['product.product'].create({
            'name': 'Weightless', 'default_code': 'ZZ-0', 'is_storable': True, 'weight': 0.0,
            'categ_id': self.env.ref('warehouse_3d.categ_bulk').id,
            'wh3d_length': 1.0, 'wh3d_width': 1.0, 'wh3d_height': 1.0})
        plan = self.env['stock.warehouse']._wh3d_plan_template_stock(self.warehouse)
        self.assertTrue(plan)
        self.assertTrue(all(qty >= 1 for _slot, _product, qty in plan))

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


class TestTemplateSpecialZones(TransactionCase):
    """T30: cold room, hazardous rows, quarantine/returns and an amber row in Warehaven DC; the special products."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = template_warehouse(cls.env)
        cls.rows = {r.code: r for r in cls.env['warehouse.rack.row'].search([('warehouse_id', '=', cls.warehouse.id)])}
        cls.special = cls.env['product.product'].search([('default_code', '=like', 'SP-%')])

    def test_cold_room_has_chilled_frozen_and_pharma_rows(self):
        self.assertEqual(self.rows['P01'].temp_band, 'frozen')
        self.assertEqual(self.rows['P02'].temp_band, 'chilled')
        self.assertEqual(self.rows['P03'].temp_band, 'pharma_fridge')

    def test_hazard_rows_approve_their_classes(self):
        flammable = self.rows['P14']
        self.assertTrue(flammable.hazard_flammable_liquid and flammable.hazard_flammable_solid)
        corrosive = self.rows['P13']
        self.assertTrue(corrosive.hazard_corrosive and not corrosive.hazard_flammable_liquid)

    def test_quarantine_and_returns_rows_have_their_own_zone(self):
        for code, purpose in (('P10', 'quarantine'), ('P11', 'returns')):
            row = self.rows[code]
            self.assertEqual(row.purpose, purpose)
            self.assertEqual(row.location_id.location_id, self.warehouse.lot_stock_id)
            self.assertNotEqual(row.location_id, self.env.ref('warehouse_3d.zone_pr'))
        self.assertNotEqual(self.rows['P10'].location_id, self.rows['P11'].location_id)

    def test_exactly_one_amber_row(self):
        amber = [c for c, r in self.rows.items() if r.inspection_status != 'green']
        self.assertEqual(len(amber), 1)
        self.assertEqual(self.rows[amber[0]].inspection_status, 'amber')
        self.assertTrue(self.rows[amber[0]].last_inspection)

    def test_cold_room_is_lower_than_the_bulk_racking(self):
        for code in ('P01', 'P02', 'P03'):
            self.assertEqual((self.rows[code].levels, self.rows[code].level_height), (3, 2.0), code)
        self.assertEqual((self.rows['P04'].levels, self.rows['P04'].level_height), (5, 1.8))

    def test_special_zones_are_rows_not_floor_areas(self):
        # The rows themselves are coloured in the editor and 3D view (rowZone); no separate floor patches.
        names = set(self.warehouse.wh3d_area_ids.mapped('name'))
        self.assertFalse({'Cold room', 'Hazardous goods', 'Quarantine and returns'} & names)

    def test_about_twenty_special_products_of_each_kind(self):
        self.assertTrue(18 <= len(self.special) <= 22, len(self.special))
        self.assertTrue(self.special.filtered(lambda p: p.wh3d_temp_band == 'chilled'))
        self.assertTrue(self.special.filtered(lambda p: p.wh3d_temp_band == 'frozen'))
        self.assertTrue(self.special.filtered(lambda p: p.wh3d_temp_band == 'pharma_fridge'))
        self.assertTrue(self.special.filtered(lambda p: p.wh3d_hazard_class == 'flammable_liquid'))
        self.assertTrue(self.special.filtered(lambda p: p.wh3d_hazard_class == 'corrosive'))
        self.assertTrue(self.special.filtered(lambda p: p.wh3d_fragile))
        self.assertTrue(self.special.filtered(lambda p: p.weight > 25))

    def test_opening_stock_holds_special_goods_only_in_matching_rows(self):
        quants = self.env['stock.quant'].search(
            [('product_id', 'in', self.special.ids), ('location_id.wh3d_node', '=', 'slot'), ('quantity', '>', 0)])
        self.assertTrue(quants)
        for quant in quants:
            row, product = quant.location_id.wh3d_rack_row_id, quant.product_id
            if product.wh3d_temp_band != 'none':
                self.assertNotEqual(row.temp_band, 'ambient', product.default_code)
            if product.wh3d_hazard_class != 'none':
                self.assertTrue(row['hazard_' + product.wh3d_hazard_class], product.default_code)

    def test_opening_stock_passes_every_hard_rule(self):
        # Take a product's own stock away (rolled back afterwards), then ask the hard rules whether that
        # stock would be allowed where it is. The largest quantity stands for all slots of the product.
        Rule = self.env['stock.putaway.rule']
        quants = self.env['stock.quant'].search([
            ('location_id.wh3d_node', '=', 'slot'), ('quantity', '>', 0),
            ('location_id.wh3d_rack_row_id.warehouse_id', '=', self.warehouse.id)])
        self.assertTrue(quants)
        by_product = defaultdict(lambda: self.env['stock.quant'])
        for quant in quants:
            by_product[quant.product_id] |= quant
        failures = []
        for product, own in by_product.items():
            slots, qty, ids = own.location_id, max(own.mapped('quantity')), tuple(own.ids)
            with closing(self.env.cr.savepoint()):
                self.env.cr.execute('DELETE FROM stock_quant WHERE id IN %s', (ids,))
                self.env.invalidate_all()
                result = Rule._wh3d_check_slots(product, qty, slots, self.warehouse.lot_stock_id)
                failures += [(product.default_code, loc.name, reason.code, reason.text)
                             for loc in slots for ok, reason in [result[loc.id]] if not ok]
            self.env.invalidate_all()
        self.assertFalse(failures, failures[:5])
