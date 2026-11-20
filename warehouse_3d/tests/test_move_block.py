from odoo.exceptions import UserError
from odoo.tests import TransactionCase
from odoo.tests.common import new_test_user

from .common import create_p05, create_zone

OVERRIDE = {'wh3d_override_hard_rules': True}


class TestMoveBlock(TransactionCase):
    """T28: validating a move line into a generated slot that breaks a hard rule raises a UserError."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')
        cls.stock = cls.warehouse.lot_stock_id
        cls.supplier = cls.env.ref('stock.stock_location_suppliers')
        cls.p05 = create_p05(cls.env, cls.warehouse, create_zone(cls.env, cls.warehouse))
        Product = cls.env['product.product']
        dims = {'wh3d_length': 0.4, 'wh3d_width': 0.4, 'wh3d_height': 0.4}
        cls.peas = Product.create({'name': 'Frozen peas', 'is_storable': True, 'weight': 10.0,
                                   'wh3d_temp_band': 'frozen', **dims})
        cls.acid = Product.create({'name': 'Acid', 'is_storable': True, 'weight': 10.0,
                                   'wh3d_hazard_class': 'corrosive', **dims})
        cls.glass = Product.create({'name': 'Glass', 'is_storable': True, 'weight': 5.0, 'wh3d_fragile': True, **dims})
        cls.rice = Product.create({'name': 'Rice', 'is_storable': True, 'weight': 100.0, **dims})
        cls.tall = Product.create({'name': 'Mast', 'is_storable': True, 'weight': 10.0,
                                   'wh3d_length': 0.4, 'wh3d_width': 0.4, 'wh3d_height': 3.0})
        cls.manager = new_test_user(cls.env, 'wh3d_mgr', groups='stock.group_stock_manager')
        cls.clerk = new_test_user(cls.env, 'wh3d_clerk', groups='stock.group_stock_user')

    def slot(self, level=1, bay=1, position=1):
        return self.env['stock.location'].search([
            ('wh3d_rack_row_id', '=', self.p05.id), ('wh3d_bay', '=', bay), ('wh3d_level', '=', level),
            ('wh3d_position', '=', position)])

    def receipt(self, product, slot, qty=1, dest=None):
        """A receipt, ready to validate, whose line is sent to ``slot`` (``dest`` = the move's own destination)."""
        dest = dest or self.stock
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id, 'location_id': self.supplier.id,
            'location_dest_id': dest.id,
            'move_ids': [(0, 0, {'product_id': product.id, 'product_uom_qty': qty, 'location_id': self.supplier.id,
                                 'location_dest_id': dest.id})]})
        picking.action_confirm()
        picking.move_ids.move_line_ids.location_dest_id = slot
        picking.move_ids.quantity = qty
        picking.move_ids.picked = True
        return picking

    def assertBlocked(self, picking, text, slot):
        with self.assertRaises(UserError) as cm:
            picking.button_validate()
        self.assertIn(slot.name, str(cm.exception))
        self.assertIn(text, str(cm.exception))

    def test_temperature(self):
        slot = self.slot()
        self.assertBlocked(self.receipt(self.peas, slot), 'Frozen peas', slot)
        self.assertBlocked(self.receipt(self.peas, slot), 'needs -60…-18 °C', slot)

    def test_hazard(self):
        self.assertBlocked(self.receipt(self.acid, self.slot()), 'not approved for corrosive', self.slot())

    def test_inspection(self):
        self.p05.inspection_status = 'amber'
        self.assertBlocked(self.receipt(self.rice, self.slot()), 'inspection', self.slot())

    def test_purpose(self):
        zone = create_zone(self.env, self.warehouse, name='QUAR')
        q01 = create_p05(self.env, self.warehouse, zone, code='Q01', x=20.5, purpose='quarantine')
        slot = q01.slot_location_ids[0]
        self.assertBlocked(self.receipt(self.rice, slot), 'only for goods sent into its zone', slot)
        self.receipt(self.rice, slot, dest=zone).button_validate()  # sent into the zone: fine

    def test_fit(self):
        self.assertBlocked(self.receipt(self.tall, self.slot()), "doesn't fit", self.slot())

    def test_fragile(self):
        self.receipt(self.rice, self.slot(level=2)).button_validate()
        self.assertBlocked(self.receipt(self.glass, self.slot(level=1)), 'below a heavy', self.slot(level=1))

    def test_odoo_capacity(self):
        self.p05.slot_location_ids.storage_category_id = self.env['stock.storage.category'].create(
            {'name': 'Light', 'max_weight': 50.0})
        self.assertBlocked(self.receipt(self.rice, self.slot()), 'kg limit', self.slot())

    def test_allowed_move_passes(self):
        picking = self.receipt(self.rice, self.slot(), qty=2)
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        self.assertEqual(self.slot().quant_ids.quantity, 2)

    def test_inventory_adjustment_blocked(self):
        slot = self.slot()
        quant = self.env['stock.quant'].with_context(inventory_mode=True).create(
            {'product_id': self.acid.id, 'location_id': slot.id, 'inventory_quantity': 1})
        with self.assertRaises(UserError) as cm:
            quant.action_apply_inventory()
        self.assertIn(slot.name, str(cm.exception))
        self.assertIn('corrosive', str(cm.exception))

    def test_internal_transfer_blocked(self):
        self.env['stock.quant']._update_available_quantity(self.peas, self.stock, 1)
        slot = self.slot()
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.int_type_id.id, 'location_id': self.stock.id,
            'location_dest_id': self.stock.id,
            'move_ids': [(0, 0, {'product_id': self.peas.id, 'product_uom_qty': 1, 'location_id': self.stock.id,
                                 'location_dest_id': self.stock.id})]})
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.move_line_ids.location_dest_id = slot
        picking.move_ids.picked = True
        self.assertBlocked(picking, 'Frozen peas', slot)

    def test_locations_outside_rack_rows_are_untouched(self):
        picking = self.receipt(self.peas, self.stock)
        picking.button_validate()
        self.assertEqual(picking.state, 'done')

    def test_manager_override_works_and_is_logged(self):
        slot = self.slot()
        picking = self.receipt(self.acid, slot)
        picking.with_user(self.manager).with_context(**OVERRIDE).button_validate()
        self.assertEqual(picking.state, 'done')
        log = [str(b) for b in picking.message_ids.mapped('body')]
        self.assertTrue(any(slot.name in b and 'hazard' in b and self.manager.name in b for b in log), log)

    def test_override_ignored_for_non_manager(self):
        picking = self.receipt(self.acid, self.slot())
        with self.assertRaises(UserError):
            picking.with_user(self.clerk).with_context(**OVERRIDE).button_validate()

    def test_inventory_override_by_manager_is_logged_on_the_product(self):
        slot = self.slot()
        quant = self.env['stock.quant'].with_context(inventory_mode=True).create(
            {'product_id': self.acid.id, 'location_id': slot.id, 'inventory_quantity': 1})
        quant.with_user(self.manager).with_context(**OVERRIDE).action_apply_inventory()
        self.assertTrue(any(slot.name in str(b) for b in self.acid.product_tmpl_id.message_ids.mapped('body')))
