import json

from odoo.tests import HttpCase, TransactionCase, tagged

from .common import template_warehouse


class TestInventoryFlow(TransactionCase):
    """The module inside Inventory's normal work, on the template warehouse (demo data):
    receipt → Smart putaway into an allowed pallet slot → 3D data → delivery → empty again."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = template_warehouse(cls.env)
        cls.product = cls.env['product.product'].search(
            [('categ_id', '=', cls.env.ref('warehouse_3d.categ_bulk').id)], order='default_code', limit=1)
        cls.supplier = cls.env.ref('stock.stock_location_suppliers')
        cls.customer = cls.env.ref('stock.stock_location_customers')

    def _validate(self, picking, qty):
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids:
            move.quantity = qty
            move.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, 'done')

    def _scene_slot(self, location):
        return next(s for s in self.warehouse.wh3d_get_slots([location.id]))

    def test_receipt_putaway_3d_and_delivery(self):
        expected_slot = self.warehouse.lot_stock_id._get_putaway_strategy(self.product, 10)  # the Smart rule's pick
        self.assertEqual(expected_slot.wh3d_node, 'slot')
        bus_before = self.env['bus.bus'].sudo().search_count([])

        # 1. Receipt into WHV/Stock: the Smart putaway rule sends it to the best allowed pallet slot.
        receipt = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'location_id': self.supplier.id, 'location_dest_id': self.warehouse.lot_stock_id.id,
            'move_ids': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 10,
                                 'location_id': self.supplier.id,
                                 'location_dest_id': self.warehouse.lot_stock_id.id})],
        })
        self._validate(receipt, 10)
        slot = receipt.move_ids.move_line_ids.location_dest_id
        self.assertEqual(slot, expected_slot)

        # 2. The 3D view's data shows it, and the live channel was told.
        stock = self._scene_slot(slot)['stock']
        self.assertEqual((stock['product_id'], stock['qty']), (self.product.id, 10))
        self.env.cr.precommit.run()
        messages = [json.loads(b.message) for b in self.env['bus.bus'].sudo().search([], offset=bus_before)]
        self.assertIn(slot.id, [i for m in messages if m['type'] == 'warehouse_3d/stock'
                                for i in m['payload']['location_ids']])

        # 3. Delivery out of that slot: it's empty again, in Inventory and in the 3D data.
        delivery = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.out_type_id.id,
            'location_id': slot.id, 'location_dest_id': self.customer.id,
            'move_ids': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': 10,
                                 'location_id': slot.id, 'location_dest_id': self.customer.id})],
        })
        self._validate(delivery, 10)
        self.assertIsNone(self._scene_slot(slot)['stock'])
        self.assertEqual(self.warehouse.lot_stock_id._get_putaway_strategy(self.product, 10), slot)  # free again


@tagged('post_install', '-at_install')
class TestInventoryFlowTour(HttpCase):

    def test_receipt_and_delivery_seen_live_in_3d(self):
        template_warehouse(self.env)
        self.start_tour('/odoo', 'warehouse_3d_inventory_flow', login='admin')
