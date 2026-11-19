from odoo.exceptions import ValidationError
from odoo.tests import Form, TransactionCase

from .common import create_p05, create_zone

GOODS_KEYS = {'temp_band', 'temp_min', 'temp_max', 'hazard_gas', 'hazard_flammable_liquid',
              'hazard_flammable_solid', 'hazard_oxidiser', 'hazard_toxic', 'hazard_corrosive',
              'purpose', 'inspection_status', 'last_inspection'}


class TestSpecialGoodsFields(TransactionCase):
    """T24: what products need (temperature, hazard, fragile) and what rack rows offer."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')
        cls.zone = create_zone(cls.env, cls.warehouse)
        cls.Product = cls.env['product.template']

    # --- products ---

    def test_product_defaults_mean_no_requirement(self):
        product = self.Product.create({'name': 'Rice'})
        self.assertEqual(product.wh3d_temp_band, 'none')
        self.assertEqual(product.wh3d_hazard_class, 'none')
        self.assertFalse(product.wh3d_fragile)

    def test_product_preset_fills_the_range(self):
        product = self.Product.create({'name': 'Vaccine', 'wh3d_temp_band': 'pharma_fridge'})
        self.assertEqual((product.wh3d_temp_min, product.wh3d_temp_max), (2.0, 8.0))
        product.wh3d_temp_band = 'frozen'
        self.assertEqual(product.wh3d_temp_max, -18.0)
        self.assertLess(product.wh3d_temp_min, -18.0)

    def test_product_chilled_starts_at_zero_degrees(self):
        # 0 °C is a real bound here, which is why "no requirement" is a band and not an empty float.
        product = self.Product.create({'name': 'Milk', 'wh3d_temp_band': 'chilled'})
        self.assertEqual((product.wh3d_temp_min, product.wh3d_temp_max), (0.0, 5.0))

    def test_product_custom_range_is_kept(self):
        product = self.Product.create({'name': 'Wine', 'wh3d_temp_band': 'custom',
                                       'wh3d_temp_min': 10.0, 'wh3d_temp_max': 14.0})
        self.assertEqual((product.wh3d_temp_min, product.wh3d_temp_max), (10.0, 14.0))

    def test_switching_to_custom_keeps_the_preset_values(self):
        product = self.Product.create({'name': 'Cheese', 'wh3d_temp_band': 'cool'})
        product.wh3d_temp_band = 'custom'
        self.assertEqual((product.wh3d_temp_min, product.wh3d_temp_max), (8.0, 15.0))

    def test_product_preset_in_form(self):
        with Form(self.Product) as form:
            form.name = 'Ice cream'
            form.wh3d_temp_band = 'frozen'
            self.assertEqual(form.wh3d_temp_max, -18.0)

    def test_product_min_above_max_refused(self):
        with self.assertRaises(ValidationError):
            self.Product.create({'name': 'Odd', 'wh3d_temp_band': 'custom',
                                 'wh3d_temp_min': 9.0, 'wh3d_temp_max': 3.0})

    # --- rack rows ---

    def test_row_defaults(self):
        row = create_p05(self.env, self.warehouse, self.zone)
        self.assertEqual(row.temp_band, 'ambient')
        self.assertEqual(row.purpose, 'normal')
        self.assertEqual(row.inspection_status, 'green')
        self.assertFalse(row.last_inspection)
        self.assertFalse(any(row[f] for f in GOODS_KEYS if f.startswith('hazard_')))

    def test_row_preset_fills_the_range(self):
        row = create_p05(self.env, self.warehouse, self.zone, temp_band='cool')
        self.assertEqual((row.temp_min, row.temp_max), (8.0, 15.0))

    def test_row_min_above_max_refused(self):
        with self.assertRaises(ValidationError):
            create_p05(self.env, self.warehouse, self.zone, temp_band='custom', temp_min=5.0, temp_max=-5.0)

    def test_editor_save_round_trip(self):
        row = create_p05(self.env, self.warehouse, self.zone)
        result = self.env['warehouse.rack.row'].wh3d_save_layout(self.warehouse.id, {'write': [{'id': row.id, 'vals': {
            'temp_band': 'pharma_freezer', 'hazard_toxic': True, 'purpose': 'quarantine',
            'inspection_status': 'amber', 'last_inspection': '2026-11-01',
        }}]})
        saved = next(r for r in result['layout']['rows'] if r['id'] == row.id)
        self.assertEqual((saved['temp_band'], saved['temp_min'], saved['temp_max']), ('pharma_freezer', -25.0, -10.0))
        self.assertTrue(saved['hazard_toxic'])
        self.assertFalse(saved['hazard_gas'])
        self.assertEqual((saved['purpose'], saved['inspection_status']), ('quarantine', 'amber'))
        self.assertEqual(str(saved['last_inspection']), '2026-11-01')

    def test_editor_custom_negative_range(self):
        row = create_p05(self.env, self.warehouse, self.zone)
        self.env['warehouse.rack.row'].wh3d_save_layout(self.warehouse.id, {'write': [{'id': row.id, 'vals': {
            'temp_band': 'custom', 'temp_min': -30.0, 'temp_max': -20.0}}]})
        self.assertEqual((row.temp_min, row.temp_max), (-30.0, -20.0))

    def test_scene_rows_carry_goods_keys(self):
        create_p05(self.env, self.warehouse, self.zone)
        rows = self.warehouse.wh3d_get_scene()['rows']
        self.assertLessEqual(GOODS_KEYS, set(rows[0]))
