from odoo.tests import Form, TransactionCase

from .common import create_p05


class TestTemplateCatalogue(TransactionCase):
    """The template warehouse's catalogue, loaded as demo data (databases created with --with-demo)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')
        cls.bulk = cls.env.ref('warehouse_3d.categ_bulk')
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
        for xmlid, name in (('warehouse_3d.zone_pr', 'WH/Stock/PR'), ('warehouse_3d.zone_sh', 'WH/Stock/SH')):
            zone = self.env.ref(xmlid)
            self.assertEqual((zone.complete_name, zone.usage), (name, 'internal'))

    def test_putaway_rules(self):
        rules = self.env['stock.putaway.rule'].search([('location_in_id', '=', self.warehouse.lot_stock_id.id)])
        by_categ = {r.category_id: r for r in rules}
        self.assertEqual(by_categ[self.bulk].location_out_id, self.env.ref('warehouse_3d.zone_pr'))
        self.assertEqual(by_categ[self.bulk].sublocation, 'closest_location')
        self.assertEqual(by_categ[self.small].location_out_id, self.env.ref('warehouse_3d.zone_sh'))

    def test_standard_putaway_fills_empty_pallet_slots_in_order(self):
        # Odoo's own putaway on the template data: bulk goods go to the first empty pallet slot.
        create_p05(self.env, self.warehouse, self.env.ref('warehouse_3d.zone_pr'),
                   code='P90', x=50.0, y=20.5, storage_category_id=self.env.ref('warehouse_3d.storcat_pallet_bulk').id)
        product = self.products.filtered(lambda p: p.categ_id == self.bulk)[:1].product_variant_id
        stock = self.warehouse.lot_stock_id
        first = stock._get_putaway_strategy(product, quantity=1)
        self.assertEqual(first.name, 'P90-01-1-A')
        self.env['stock.quant']._update_available_quantity(product, first, 1)
        self.assertEqual(stock._get_putaway_strategy(product, quantity=1).name, 'P90-01-1-B')  # A is taken

    def test_abc_class_on_product_form(self):
        form = Form(self.env['product.template'])
        form.name = 'Test product'
        form.wh3d_abc_class = 'B'
        self.assertEqual(form.save().wh3d_abc_class, 'B')
