from odoo.tests import TransactionCase

from ..putaway.rules import HEAVY_KG, allowed
from .common import create_p05, create_zone


def product(**kw):
    """An ordinary ambient product: 1.2 × 1.0 × 1.1 m, 100 kg."""
    return {'id': 1, 'temp_band': 'none', 'temp_min': 0.0, 'temp_max': 0.0, 'hazard': 'none', 'fragile': False,
            'weight': 100.0, 'dims': (1.2, 1.0, 1.1)} | kw


def goods(*products, qty=1.0, **kw):
    products = products or (product(),)
    return {'products': list(products), 'qty': qty, 'purpose': 'normal', 'dest_path': '1/7/'} | kw


def row(**kw):
    return {'temp_band': 'ambient', 'temp_min': 0.0, 'temp_max': 0.0, 'hazards': set(), 'purpose': 'normal',
            'inspection_status': 'green', 'zone_path': '1/7/30/'} | kw


def slot(**kw):
    """A P05 pallet slot: 1.35 × 1.1 × 1.8 m, no storage category, nothing above or below."""
    return {'id': 100, 'row': row(), 'size': (1.35, 1.1, 1.8), 'capacity_m3': 2.673, 'category': None,
            'forecast_weight': 0.0, 'location_qty': 0.0, 'above': [], 'below': []} | kw


def content(qty=1.0, on_hand=None, **kw):
    """What a slot holds: a product dict plus its quantity (on hand + incoming) and the on-hand part."""
    return product(**kw) | {'qty': qty, 'on_hand': qty if on_hand is None else on_hand}


class TestPutawayRules(TransactionCase):
    """T25: putaway.rules.allowed(), the pure hard-rule filter. One test per rule, both outcomes."""

    def assertRefused(self, result, code):
        ok, reason = result
        self.assertFalse(ok)
        self.assertEqual(reason.code, code, reason.text)
        self.assertTrue(reason.text)

    def assertAllowed(self, result):
        ok, reason = result
        self.assertTrue(ok, reason and reason.text)
        self.assertIsNone(reason)

    def test_ordinary_goods_in_a_normal_row_pass_every_rule(self):
        self.assertAllowed(allowed(goods(), slot(), []))

    # temperature
    def test_temperature_zone_inside_product_range(self):
        fridge = product(temp_band='pharma_fridge', temp_min=2.0, temp_max=8.0)
        self.assertAllowed(allowed(goods(fridge), slot(row=row(temp_band='custom', temp_min=3.0, temp_max=6.0)), []))
        self.assertRefused(allowed(goods(fridge), slot(row=row(temp_band='cool', temp_min=8.0, temp_max=15.0)), []),
                           'temperature')

    def test_temperature_uncontrolled_zone_only_without_requirement(self):
        fridge = product(temp_band='pharma_fridge', temp_min=2.0, temp_max=8.0)
        self.assertRefused(allowed(goods(fridge), slot(), []), 'temperature')

    def test_temperature_controlled_rows_are_kept_for_goods_that_need_them(self):
        # Decided 20 Nov: cold space is scarce and ambient goods can be harmed by cold, so no-requirement goods stay out.
        cold = slot(row=row(temp_band='chilled', temp_min=0.0, temp_max=5.0))
        self.assertRefused(allowed(goods(), cold, []), 'temperature')

    def test_temperature_frozen_takes_a_deep_freeze_row(self):
        # Frozen is stored as −60…−18 °C (no lower bound in the sources), so a −40…−20 °C row is fine.
        frozen = product(temp_band='frozen', temp_min=-60.0, temp_max=-18.0)
        deep = slot(row=row(temp_band='custom', temp_min=-40.0, temp_max=-20.0))
        self.assertAllowed(allowed(goods(frozen), deep, []))

    # hazard
    def test_hazard_class_must_be_approved_on_the_row(self):
        toxic = product(hazard='toxic')
        self.assertAllowed(allowed(goods(toxic), slot(row=row(hazards={'toxic'})), []))
        self.assertRefused(allowed(goods(toxic), slot(row=row(hazards={'corrosive'})), []), 'hazard')

    def test_hazard_one_class_per_slot(self):
        both = slot(row=row(hazards={'toxic', 'corrosive'}))
        self.assertRefused(allowed(goods(product(hazard='toxic')), both, [content(id=2, hazard='corrosive')]), 'hazard')
        self.assertAllowed(allowed(goods(product(hazard='toxic')), both, [content(id=2, hazard='toxic', dims=(0.1,) * 3)]))

    # purpose
    def test_purpose_normal_goods_only_in_normal_rows(self):
        quarantine = slot(row=row(purpose='quarantine', zone_path='1/7/40/'))
        self.assertRefused(allowed(goods(), quarantine, []), 'purpose')

    def test_purpose_special_row_only_when_sent_into_its_zone(self):
        quarantine = slot(row=row(purpose='quarantine', zone_path='1/7/40/'))
        self.assertAllowed(allowed(goods(purpose='quarantine', dest_path='1/7/40/'), quarantine, []))
        # A sibling whose id starts with the same digits is not inside the zone.
        self.assertRefused(allowed(goods(purpose='quarantine', dest_path='1/7/401/'), quarantine, []), 'purpose')
        # Quarantined goods don't go to a normal row either.
        self.assertRefused(allowed(goods(purpose='quarantine', dest_path='1/7/40/'), slot(), []), 'purpose')

    # inspection
    def test_inspection_amber_and_red_excluded(self):
        for status in ('amber', 'red'):
            self.assertRefused(allowed(goods(), slot(row=row(inspection_status=status)), []), 'inspection')

    # physical fit
    def test_fit_any_rotation_in_the_horizontal_plane(self):
        long = product(dims=(1.1, 1.3, 1.0))  # fits only turned: 1.3 along the 1.35 m width
        self.assertAllowed(allowed(goods(long), slot(), []))
        self.assertRefused(allowed(goods(product(dims=(1.4, 1.2, 1.0))), slot(), []), 'fit')

    def test_fit_too_tall(self):
        self.assertRefused(allowed(goods(product(dims=(1.0, 1.0, 1.9))), slot(), []), 'fit')

    def test_fit_remaining_volume(self):
        # 1.32 m³ per unit in a 2.673 m³ slot: two fit, three don't; one already there leaves room for one.
        self.assertAllowed(allowed(goods(qty=2), slot(), []))
        self.assertRefused(allowed(goods(qty=3), slot(), []), 'fit')
        self.assertRefused(allowed(goods(qty=2), slot(), [content()]), 'fit')

    def test_fit_quantity_zero_checks_one_unit(self):
        # Odoo asks with quantity 0 for a new line; a full slot must not be suggested.
        self.assertRefused(allowed(goods(qty=0), slot(), [content(qty=2)]), 'fit')

    def test_fit_unknown_dimensions_are_not_checked(self):
        self.assertAllowed(allowed(goods(product(dims=(0.0, 0.0, 0.0)), qty=50), slot(), []))
        self.assertAllowed(allowed(goods(qty=2), slot(), [content(dims=(0.0, 0.0, 0.0), id=2)]))

    # fragile
    def test_fragile_never_below_heavy(self):
        fragile = product(fragile=True, weight=5.0, dims=(0.5, 0.5, 0.5))
        self.assertRefused(allowed(goods(fragile), slot(above=[content(weight=HEAVY_KG + 1)]), []), 'fragile')
        self.assertAllowed(allowed(goods(fragile), slot(above=[content(weight=HEAVY_KG)]), []))

    def test_heavy_never_above_fragile(self):
        self.assertRefused(allowed(goods(), slot(below=[content(fragile=True, weight=5.0)]), []), 'fragile')
        light = product(weight=HEAVY_KG)
        self.assertAllowed(allowed(goods(light), slot(below=[content(fragile=True, weight=5.0)]), []))

    # Odoo's storage category (same semantics as stock.location._check_can_be_used)
    def test_odoo_max_weight(self):
        category = {'max_weight': 250.0, 'allow_new_product': 'mixed', 'product_capacity': None, 'package_capacity': None}
        self.assertAllowed(allowed(goods(qty=2), slot(category=category, forecast_weight=50.0), []))
        self.assertRefused(allowed(goods(qty=2), slot(category=category, forecast_weight=51.0), []), 'odoo_capacity')

    def test_odoo_empty_only(self):
        category = {'max_weight': 1000.0, 'allow_new_product': 'empty', 'product_capacity': None, 'package_capacity': None}
        self.assertRefused(allowed(goods(), slot(category=category), [content(dims=(0.1,) * 3)]), 'odoo_capacity')
        # Only stock on hand counts, as in Odoo: an incoming line doesn't make the slot "not empty".
        self.assertAllowed(allowed(goods(), slot(category=category), [content(on_hand=0.0, dims=(0.1,) * 3)]))

    def test_odoo_same_product_only(self):
        category = {'max_weight': 1000.0, 'allow_new_product': 'same', 'product_capacity': None, 'package_capacity': None}
        small = {'dims': (0.1,) * 3}
        self.assertAllowed(allowed(goods(), slot(category=category), [content(**small)]))
        self.assertRefused(allowed(goods(), slot(category=category), [content(id=2, **small)]), 'odoo_capacity')
        self.assertRefused(allowed(goods(), slot(category=category), [content(id=2, on_hand=0.0, **small)]), 'odoo_capacity')
        self.assertRefused(allowed(goods(product(), product(id=2)), slot(category=category), []), 'odoo_capacity')

    def test_odoo_product_capacity(self):
        category = {'max_weight': 1000.0, 'allow_new_product': 'mixed', 'product_capacity': 2.0, 'package_capacity': None}
        small = product(dims=(0.1,) * 3, weight=1.0)
        self.assertAllowed(allowed(goods(small, qty=1), slot(category=category, location_qty=1.0), []))
        self.assertRefused(allowed(goods(small, qty=2), slot(category=category, location_qty=1.0), []), 'odoo_capacity')
        self.assertRefused(allowed(goods(small, qty=0), slot(category=category, location_qty=2.0), []), 'odoo_capacity')

    def test_odoo_package_capacity(self):
        category = {'max_weight': 1000.0, 'allow_new_product': 'mixed', 'product_capacity': None, 'package_capacity': 1.0}
        package = goods(package=True, weight=100.0)
        self.assertAllowed(allowed(package, slot(category=category, location_qty=0.0), []))
        self.assertRefused(allowed(package, slot(category=category, location_qty=1.0), []), 'odoo_capacity')


class TestPutawayRulesGlue(TransactionCase):
    """T25: stock.putaway.rule._wh3d_check_slots(), the Odoo data behind allowed()."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')
        cls.stock = cls.warehouse.lot_stock_id
        cls.zone = create_zone(cls.env, cls.warehouse)
        cls.p05 = create_p05(cls.env, cls.warehouse, cls.zone)
        cls.Rule = cls.env['stock.putaway.rule']
        cls.Location = cls.env['stock.location']
        cls.Product = cls.env['product.product']
        cls.rice = cls.Product.create({'name': 'Rice', 'is_storable': True, 'weight': 100.0,
                                       'wh3d_length': 1.2, 'wh3d_width': 1.0, 'wh3d_height': 1.1})
        cls.glass = cls.Product.create({'name': 'Glass', 'is_storable': True, 'weight': 5.0, 'wh3d_fragile': True,
                                        'wh3d_length': 0.5, 'wh3d_width': 0.5, 'wh3d_height': 0.5})
        cls.acid = cls.Product.create({'name': 'Acid', 'is_storable': True, 'weight': 20.0, 'wh3d_hazard_class': 'corrosive',
                                       'wh3d_length': 0.3, 'wh3d_width': 0.3, 'wh3d_height': 0.3})
        cls.bleach = cls.Product.create({'name': 'Bleach', 'is_storable': True, 'weight': 20.0, 'wh3d_hazard_class': 'oxidiser',
                                         'wh3d_length': 0.3, 'wh3d_width': 0.3, 'wh3d_height': 0.3})

    def slot(self, name):
        return self.Location.search([('name', '=', name), ('warehouse_id', '=', self.warehouse.id)])

    def check(self, product, qty, slots, dest=None, **kw):
        return self.Rule._wh3d_check_slots(product, qty, slots, dest or self.stock, **kw)

    def incoming(self, product, slot, qty):
        """A receipt line on its way to ``slot`` (assigned, not done)."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id, 'location_dest_id': self.stock.id,
            'move_ids': [(0, 0, {'product_id': product.id, 'product_uom_qty': qty,
                                 'location_id': self.env.ref('stock.stock_location_suppliers').id,
                                 'location_dest_id': self.stock.id})],
        })
        picking.action_confirm()
        picking.move_ids.move_line_ids.location_dest_id = slot
        return picking

    def test_ordinary_product_allowed_everywhere_in_a_normal_row(self):
        result = self.check(self.rice, 1, self.p05.slot_location_ids)
        self.assertEqual(len(result), 70)
        self.assertTrue(all(ok for ok, _r in result.values()))

    def test_row_settings_reach_the_rule(self):
        self.p05.inspection_status = 'amber'
        ok, reason = self.check(self.rice, 1, self.slot('P05-01-1-A'))[self.slot('P05-01-1-A').id]
        self.assertFalse(ok)
        self.assertEqual(reason.code, 'inspection')

    def test_neighbour_above_is_read_from_stock(self):
        self.env['stock.quant']._update_available_quantity(self.rice, self.slot('P05-01-2-A'), 1)
        result = self.check(self.glass, 1, self.slot('P05-01-1-A') | self.slot('P05-01-1-B'))
        self.assertEqual(result[self.slot('P05-01-1-A').id][1].code, 'fragile')
        self.assertTrue(result[self.slot('P05-01-1-B').id][0])

    def test_incoming_stock_counts_as_contents(self):
        # Two receipt lines planned before either is done must not mix hazard classes in one slot.
        self.p05.write({'hazard_corrosive': True, 'hazard_oxidiser': True})
        target = self.slot('P05-02-1-A')
        self.incoming(self.acid, target, 1)
        ok, reason = self.check(self.bleach, 1, target)[target.id]
        self.assertFalse(ok)
        self.assertEqual(reason.code, 'hazard')

    def test_purpose_from_the_destination(self):
        quarantine_zone = create_zone(self.env, self.warehouse, name='QUAR')
        q01 = create_p05(self.env, self.warehouse, quarantine_zone, code='Q01', x=20.5, purpose='quarantine')
        slot = q01.slot_location_ids[:1]
        self.assertEqual(self.check(self.rice, 1, slot)[slot.id][1].code, 'purpose')
        self.assertTrue(self.check(self.rice, 1, slot, dest=quarantine_zone)[slot.id][0])
        normal = self.slot('P05-01-1-A')
        self.assertEqual(self.check(self.rice, 1, normal, dest=quarantine_zone)[normal.id][1].code, 'purpose')

    def test_odoo_capacity_matches_check_can_be_used(self):
        category = self.env['stock.storage.category'].create({
            'name': 'Same, 300 kg', 'allow_new_product': 'same', 'max_weight': 300.0,
            'product_capacity_ids': [(0, 0, {'product_id': self.rice.id, 'quantity': 2})]})
        self.p05.storage_category_id = category
        self.rice.wh3d_length = 0.0  # unknown size: only Odoo's rule can refuse, so the answers are comparable
        Quant = self.env['stock.quant']
        slots = {name: self.slot(name) for name in ('P05-01-1-A', 'P05-01-1-B', 'P05-02-1-A', 'P05-02-1-B', 'P05-03-1-A')}
        Quant._update_available_quantity(self.rice, slots['P05-01-1-B'], 2)    # at capacity
        Quant._update_available_quantity(self.glass, slots['P05-02-1-A'], 1)   # another product
        Quant._update_available_quantity(self.rice, slots['P05-02-1-B'], 1)    # room for one more
        self.incoming(self.glass, slots['P05-03-1-A'], 1)                      # another product on its way
        for qty in (1, 2):
            result = self.check(self.rice, qty, self.Location.union(*slots.values()))
            for name, loc in slots.items():
                location_qty = sum(Quant.search([('location_id', '=', loc.id), ('product_id', '=', self.rice.id)]).mapped('quantity'))
                expected = loc._check_can_be_used(self.rice, qty, location_qty=location_qty)
                ok, reason = result[loc.id]
                self.assertIn(reason and reason.code, (None, 'odoo_capacity'))
                self.assertEqual(ok, expected, f'{name}, qty {qty}: {reason and reason.text}')

    def test_package_weight_matches_check_can_be_used(self):
        # A received package has no quants yet: Odoo weighs it by its open move lines.
        pallet = self.env['stock.package.type'].create({'name': 'Pallet'})
        category = self.env['stock.storage.category'].create({
            'name': 'Light', 'allow_new_product': 'mixed', 'max_weight': 250.0,
            'package_capacity_ids': [(0, 0, {'package_type_id': pallet.id, 'quantity': 4})]})
        self.p05.storage_category_id = category
        self.rice.wh3d_length = 0.0  # only Odoo's rule can refuse
        target = self.slot('P05-04-1-A')
        for qty, expected in ((2, True), (3, False)):  # 200 kg fits under 250 kg, 300 kg doesn't
            package = self.env['stock.package'].create({'package_type_id': pallet.id})
            picking = self.incoming(self.rice, self.stock, qty)
            picking.move_ids.move_line_ids.result_package_id = package
            self.assertEqual(target._check_can_be_used(self.env['product.product'], package=package), expected)
            ok, reason = self.Rule.with_context(products=self.rice)._wh3d_check_slots(
                self.env['product.product'], 0, target, self.stock, package=package)[target.id]
            self.assertEqual(ok, expected, reason and reason.text)
            picking.action_cancel()

    def test_fixed_number_of_queries(self):
        def queries(slots):
            self.env.invalidate_all()
            start = self.env.cr.sql_log_count
            self.check(self.rice, 1, slots)
            return self.env.cr.sql_log_count - start

        Category = self.env['stock.storage.category']
        bulk = Category.create({'name': 'Bulk', 'allow_new_product': 'empty', 'max_weight': 1000.0})
        capped = Category.create({'name': 'Capped', 'allow_new_product': 'same', 'max_weight': 500.0,
                                  'product_capacity_ids': [(0, 0, {'product_id': self.rice.id, 'quantity': 2})]})
        self.p05.storage_category_id = capped
        Quant = self.env['stock.quant']
        Quant._update_available_quantity(self.glass, self.slot('P05-01-2-A'), 1)
        queries(self.p05.slot_location_ids)  # warm-up: one-time lookups (access rules, metadata)
        one_row = queries(self.p05.slot_location_ids)
        p06 = create_p05(self.env, self.warehouse, self.zone, code='P06', x=20.5)
        p07 = create_p05(self.env, self.warehouse, self.zone, code='P07', x=30.0, storage_category_id=bulk.id)
        p06.storage_category_id = capped
        Quant._update_available_quantity(self.glass, p07.slot_location_ids[5], 1)
        three_rows = queries(self.p05.slot_location_ids | p06.slot_location_ids | p07.slot_location_ids)
        self.assertEqual(one_row, three_rows)
        self.assertLessEqual(three_rows, 18)  # 16 when written (19 Nov): a jump means a per-slot query crept in
