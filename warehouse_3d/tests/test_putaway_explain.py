from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged

from .common import create_p05


class TestPutawayExplain(TransactionCase):
    """T29: the "Why this slot?" dialog on a receipt line (wh3d.putaway.explain)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].create({'name': 'Explain', 'code': 'EXP'})
        cls.stock = cls.warehouse.lot_stock_id
        cls.row = create_p05(cls.env, cls.warehouse)  # 70 pallet slots, no dispatch dock
        cls.supplier = cls.env.ref('stock.stock_location_suppliers')

    def receipt_line(self, smart=True, **product_vals):
        product = self.env['product.product'].create({
            'name': 'Bags', 'is_storable': True, 'weight': 1.0,
            'wh3d_length': 0.3, 'wh3d_width': 0.3, 'wh3d_height': 0.3, **product_vals})
        if smart:
            self.env['stock.putaway.rule'].create({
                'product_id': product.id, 'location_in_id': self.stock.id,
                'location_out_id': self.row.location_id.id, 'sublocation': 'wh3d_smart'})
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'location_id': self.supplier.id, 'location_dest_id': self.stock.id,
            'move_ids': [(0, 0, {'product_id': product.id, 'product_uom_qty': 5,
                                 'location_id': self.supplier.id, 'location_dest_id': self.stock.id})]})
        picking.action_confirm()
        picking.action_assign()
        return picking.move_ids.move_line_ids

    def explain(self, line):
        return self.env['wh3d.putaway.explain'].browse(line.action_wh3d_explain_putaway()['res_id'])

    def test_top_three_in_score_order_with_reasons(self):
        line = self.receipt_line()
        first = line.location_dest_id
        wizard = self.explain(line)
        self.assertEqual(len(wizard.slot_ids), 3)
        scores = wizard.slot_ids.mapped('score')
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(wizard.slot_ids[0].slot_id, first)  # the dialog agrees with what putaway chose
        for choice in wizard.slot_ids:
            self.assertIn(' m³ left', choice.reasons)
            self.assertTrue(choice.level)

    def test_reasons_mention_what_the_criteria_say(self):
        line = self.receipt_line()
        slot = self.env['stock.location'].search([('wh3d_rack_row_id', '=', self.row.id), ('wh3d_node', '=', 'slot')])[0]
        self.env['stock.quant']._update_available_quantity(line.product_id, slot, 1)
        top = self.explain(line).slot_ids[0]
        self.assertEqual(top.slot_id, slot)
        self.assertIn('already holds this product', top.reasons)

    def test_removed_counts_become_sentences(self):
        line = self.receipt_line(wh3d_temp_band='pharma_fridge')  # the row is ambient: every slot is out
        wizard = self.explain(line)
        self.assertFalse(wizard.slot_ids)
        self.assertIn('70 slots excluded: temperature (product needs 2–8 °C)', wizard.excluded)

    def test_picking_the_second_slot_sets_the_destination(self):
        line = self.receipt_line()
        wizard = self.explain(line)
        second = wizard.slot_ids[1]
        self.assertNotEqual(line.location_dest_id, second.slot_id)
        second.action_choose()
        self.assertEqual(line.location_dest_id, second.slot_id)

    def test_a_stale_dialog_cannot_change_a_receipt_that_is_already_done(self):
        line = self.receipt_line()
        choice = self.explain(line).slot_ids[1]
        placed = line.location_dest_id
        line.picking_id.button_validate()  # another session completes the receipt while the dialog is open
        self.assertEqual(line.state, 'done')
        with self.assertRaisesRegex(UserError, 'no longer open'):
            choice.action_choose()
        self.assertEqual(line.location_dest_id, placed)

    def test_without_a_smart_rule_the_slots_under_the_destination_are_ranked(self):
        line = self.receipt_line(smart=False)
        wizard = self.explain(line)
        self.assertEqual(len(wizard.slot_ids), 3)
        self.assertTrue(all(s.slot_id.wh3d_node == 'slot' for s in wizard.slot_ids))

    def test_no_slots_at_all_is_handled(self):
        empty = self.env['stock.warehouse'].create({'name': 'Bare', 'code': 'BRE'})
        product = self.env['product.product'].create({'name': 'Nuts', 'is_storable': True})
        picking = self.env['stock.picking'].create({
            'picking_type_id': empty.in_type_id.id, 'location_id': self.supplier.id,
            'location_dest_id': empty.lot_stock_id.id,
            'move_ids': [(0, 0, {'product_id': product.id, 'product_uom_qty': 1,
                                 'location_id': self.supplier.id, 'location_dest_id': empty.lot_stock_id.id})]})
        picking.action_confirm()
        picking.action_assign()
        wizard = self.explain(picking.move_ids.move_line_ids)
        self.assertFalse(wizard.slot_ids)
        self.assertEqual(wizard.excluded, '')
        self.assertTrue(wizard.summary)

    def test_done_lines_are_refused(self):
        line = self.receipt_line()
        line.picking_id.move_ids.picked = True
        line.picking_id.button_validate()
        with self.assertRaises(UserError):
            line.action_wh3d_explain_putaway()


@tagged('post_install', '-at_install')
class TestPutawayExplainTour(HttpCase):

    def test_pick_the_second_slot_validate_and_find_the_stock(self):
        warehouse = self.env['stock.warehouse'].create({'name': 'Explain tour', 'code': 'EXT'})
        row = create_p05(self.env, warehouse, hazard_toxic=True)
        create_p05(self.env, warehouse, row.location_id, code='P06', x=15.0)  # not approved: 70 slots excluded
        product = self.env['product.product'].create({
            'name': 'Tour bags', 'is_storable': True, 'weight': 1.0, 'wh3d_hazard_class': 'toxic',
            'wh3d_length': 0.3, 'wh3d_width': 0.3, 'wh3d_height': 0.3})
        self.env['stock.putaway.rule'].create({
            'product_id': product.id, 'location_in_id': warehouse.lot_stock_id.id,
            'location_out_id': row.location_id.id, 'sublocation': 'wh3d_smart'})
        supplier = self.env.ref('stock.stock_location_suppliers')
        picking = self.env['stock.picking'].create({
            'picking_type_id': warehouse.in_type_id.id, 'origin': 'Explain tour',
            'location_id': supplier.id, 'location_dest_id': warehouse.lot_stock_id.id,
            'move_ids': [(0, 0, {'product_id': product.id, 'product_uom_qty': 5, 'location_id': supplier.id,
                                 'location_dest_id': warehouse.lot_stock_id.id})]})
        picking.action_confirm()
        picking.action_assign()
        self.start_tour(f'/odoo/action-stock.action_picking_tree_all/{picking.id}', 'warehouse_3d_putaway_explain', login='admin')
