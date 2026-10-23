import json

from odoo.tests import TransactionCase

from .common import create_p05


class TestStockBus(TransactionCase):
    """Stock changes in rack slots are announced on the bus, once per transaction."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env.ref('stock.warehouse0')
        cls.stock = cls.warehouse.lot_stock_id
        create_p05(cls.env, cls.warehouse)
        cls.slots = cls.env['stock.location'].search(
            [('name', 'in', ['P05-01-1-A', 'P05-01-1-B', 'P05-02-1-A'])], order='name')
        cls.product = cls.env['product.product'].create({'name': 'Rice 25 kg', 'is_storable': True})
        cls.supplier = cls.env.ref('stock.stock_location_suppliers')

    def _stock_notifications(self):
        """Run the commit hooks (as a real commit would) and return our bus messages."""
        self.env.cr.precommit.run()
        messages = []
        for notif in self.env['bus.bus'].sudo().search([]):
            message = json.loads(notif.message)
            if message['type'] == 'warehouse_3d/stock':
                messages.append((json.loads(notif.channel), message['payload']))
        return messages

    def _receive(self, destinations):
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'location_id': self.supplier.id, 'location_dest_id': self.stock.id,
            'move_ids': [(0, 0, {
                'product_id': self.product.id, 'product_uom_qty': 1,
                'location_id': self.supplier.id, 'location_dest_id': dest.id,
            }) for dest in destinations],
        })
        picking.action_confirm()
        for move in picking.move_ids:
            move.quantity = 1
            move.picked = True
        picking.button_validate()
        self.assertEqual(picking.state, 'done')
        return picking

    def test_three_line_receipt_sends_one_message_with_three_slots(self):
        self._stock_notifications()  # drop anything from setup
        self.env['bus.bus'].sudo().search([]).unlink()
        self._receive(self.slots)
        messages = self._stock_notifications()
        self.assertEqual(len(messages), 1)
        channel, payload = messages[0]
        self.assertEqual(sorted(payload['location_ids']), sorted(self.slots.ids))
        # Sent to the Inventory users group, which every Inventory user's browser listens to.
        # (The bus stores channels as [database, model, id].)
        self.assertEqual(channel[1:], ['res.groups', self.env.ref('stock.group_stock_user').id])

    def test_stock_outside_rack_slots_sends_nothing(self):
        self._stock_notifications()
        self.env['bus.bus'].sudo().search([]).unlink()
        self._receive(self.stock)
        self.assertEqual(self._stock_notifications(), [])

    def test_inventory_adjustment_is_announced(self):
        # The real path: Physical Inventory ▸ counted quantity ▸ Apply.
        self._stock_notifications()
        self.env['bus.bus'].sudo().search([]).unlink()
        quant = self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': self.product.id, 'location_id': self.slots[0].id, 'inventory_quantity': 4,
        })
        quant.action_apply_inventory()
        self.assertEqual(quant.quantity, 4)
        messages = self._stock_notifications()
        self.assertEqual([m[1]['location_ids'] for m in messages], [[self.slots[0].id]])

    def test_direct_quantity_update_is_announced(self):
        self._stock_notifications()
        self.env['bus.bus'].sudo().search([]).unlink()
        self.env['stock.quant']._update_available_quantity(self.product, self.slots[0], 4)
        messages = self._stock_notifications()
        self.assertEqual([m[1]['location_ids'] for m in messages], [[self.slots[0].id]])

    def test_reservations_send_nothing(self):
        # The 3D view doesn't show reservations, so they mustn't make every open view refetch.
        self.env['stock.quant']._update_available_quantity(self.product, self.slots[0], 4)
        self._stock_notifications()
        self.env['bus.bus'].sudo().search([]).unlink()
        quant = self.env['stock.quant'].search([('location_id', '=', self.slots[0].id)])
        quant.reserved_quantity = 2
        self.assertEqual(self._stock_notifications(), [])

    def test_moving_stock_between_slots_announces_both(self):
        self.env['stock.quant']._update_available_quantity(self.product, self.slots[0], 4)
        self._stock_notifications()
        self.env['bus.bus'].sudo().search([]).unlink()
        quant = self.env['stock.quant'].search([('location_id', '=', self.slots[0].id)])
        quant.location_id = self.slots[1]
        messages = self._stock_notifications()
        self.assertEqual(len(messages), 1)
        self.assertEqual(sorted(messages[0][1]['location_ids']), sorted(self.slots[:2].ids))
