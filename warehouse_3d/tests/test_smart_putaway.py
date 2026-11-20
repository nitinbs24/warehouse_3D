import time

from odoo.tests import TransactionCase

from .common import create_p05, template_warehouse

LOGGER = 'odoo.addons.warehouse_3d.models.stock_putaway_rule'


class TestSmartPutaway(TransactionCase):
    """T27 (Odoo half): the "Smart (Warehaven)" putaway option, end to end on the template warehouse."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = template_warehouse(cls.env)
        cls.stock = cls.warehouse.lot_stock_id
        cls.supplier = cls.env.ref('stock.stock_location_suppliers')
        cls.distance = {k: v[0] for k, v in cls.warehouse._wh3d_slot_distances().items()}

    def product(self, name, smart=True, **kw):
        """A small light storable product (0.3 m cube, 1 kg) with its own rule (product rules win over category ones)."""
        product = self.env['product.product'].create({
            'name': name, 'is_storable': True, 'weight': 1.0,
            'wh3d_length': 0.3, 'wh3d_width': 0.3, 'wh3d_height': 0.3, **kw})
        if smart:
            self.rule(product)
        return product

    def rule(self, product, sublocation='wh3d_smart', **kw):
        return self.env['stock.putaway.rule'].create({
            'product_id': product.id, 'location_in_id': self.stock.id, 'location_out_id': self.stock.id,
            'sublocation': sublocation, **kw})

    def receive(self, product, qty=5):
        receipt = self.env['stock.picking'].create({
            'picking_type_id': self.warehouse.in_type_id.id,
            'location_id': self.supplier.id, 'location_dest_id': self.stock.id,
            'move_ids': [(0, 0, {'product_id': product.id, 'product_uom_qty': qty,
                                 'location_id': self.supplier.id, 'location_dest_id': self.stock.id})],
        })
        receipt.action_confirm()
        receipt.action_assign()
        return receipt.move_ids.move_line_ids.location_dest_id

    def test_option_is_selectable_in_the_rule_list(self):
        selection = dict(self.env['stock.putaway.rule'].fields_get(['sublocation'])['sublocation']['selection'])
        self.assertEqual(selection['wh3d_smart'], 'Smart (Warehaven)')
        self.assertIn('closest_location', selection)

    def test_receipt_of_a_fast_mover_lands_nearer_dispatch_than_a_slow_one(self):
        # Both already have a little stock in a far, empty shelf slot (pallet slots take new products only when
        # empty). Consolidation pulls the slow mover there; the fast mover's heavier travel weight takes it to
        # the nearest slots instead.
        empty = self.env['stock.location'].search(
            [('wh3d_rack_row_id.code', '=', 'S01'), ('wh3d_node', '=', 'slot')]).filtered(lambda s: not s.quant_ids)
        far = max(empty, key=lambda s: (self.distance[s.id], -s.id))  # by distance, not by search order
        fast, slow = self.product('Fast', wh3d_abc_class='A'), self.product('Slow', wh3d_abc_class='C')
        for product in (fast, slow):
            self.env['stock.quant']._update_available_quantity(product, far, 1)
        fast_slot, slow_slot = self.receive(fast), self.receive(slow)
        self.assertEqual(slow_slot, far)
        self.assertEqual(fast_slot.wh3d_node, 'slot')
        self.assertLess(self.distance[fast_slot.id], self.distance[slow_slot.id])

    def test_frozen_goods_only_go_to_the_cold_row(self):
        cold = self.env['warehouse.rack.row'].search([('warehouse_id', '=', self.warehouse.id), ('code', '=', 'P14')])
        cold.write({'temp_band': 'frozen'})
        peas = self.product('Peas', wh3d_temp_band='frozen')
        slot = self.receive(peas)
        self.assertEqual(slot.wh3d_rack_row_id, cold)

    def test_no_allowed_slot_keeps_the_destination_and_logs(self):
        gas = self.product('Gas', wh3d_hazard_class='gas')  # no template row is approved for it
        with self.assertLogs(LOGGER, 'INFO') as logs:
            slot = self.receive(gas)
        self.assertEqual(slot, self.stock)
        self.assertIn('no allowed slot', logs.output[0])

    def test_package_putaway_uses_the_products_in_the_context(self):
        row = self.env['warehouse.rack.row'].search([('warehouse_id', '=', self.warehouse.id), ('code', '=', 'P14')])
        row.write({'temp_band': 'frozen'})
        peas = self.product('Peas', smart=False, wh3d_temp_band='frozen')
        rule = self.env['stock.putaway.rule'].create({
            'location_in_id': self.stock.id, 'location_out_id': self.stock.id, 'sublocation': 'wh3d_smart',
            'package_type_ids': [(0, 0, {'name': 'Box'})]})
        package = self.env['stock.package'].create({'package_type_id': rule.package_type_ids.id})
        empty = self.env['product.product']
        slot = self.stock.with_context(products=peas)._get_putaway_strategy(empty, package=package)
        self.assertEqual(slot.wh3d_rack_row_id, row)

    def test_other_rules_are_unchanged_and_order_is_kept(self):
        product = self.product('Plain', smart=False)
        zone = self.env['stock.location'].create({'name': 'Z', 'usage': 'internal', 'location_id': self.stock.id})
        plain = self.rule(product, sublocation='no', location_out_id=zone.id)
        self.assertEqual(self.receive(product), zone)  # the standard rule answers
        plain.unlink()
        self.rule(product)  # now only a smart rule
        self.assertEqual(self.receive(product).wh3d_node, 'slot')

    def test_ranking_reports_what_it_removed_and_what_it_scored(self):
        product = self.product('Gas', wh3d_hazard_class='gas')
        rule = self.rule(product)
        slots = self.env['stock.location'].search([('id', 'child_of', self.stock.id), ('wh3d_node', '=', 'slot')])
        ranked, removed = rule._wh3d_rank_slots(product, 1, slots, self.stock)
        self.assertEqual(ranked, [])
        self.assertTrue(removed['hazard'])
        self.assertEqual(sum(removed.values()), len(slots))  # every slot refused, by some rule
        ranked, removed = rule._wh3d_rank_slots(self.product('Plain', smart=False), 1, slots, self.stock)
        self.assertEqual(len(ranked) + sum(removed.values()), len(slots))
        top = ranked[0]
        self.assertEqual(set(top), {'slot', 'score', 'criteria', 'distance', 'level', 'z'})
        self.assertEqual(top['distance'], self.distance[top['slot'].id])
        self.assertEqual([r['score'] for r in ranked], sorted((r['score'] for r in ranked), reverse=True))

    def test_one_move_line_takes_under_a_second(self):
        product = self.product('Timed', wh3d_abc_class='A')
        self.stock._get_putaway_strategy(product, 5)  # warm the caches (distances)
        start = time.perf_counter()
        slot = self.stock._get_putaway_strategy(product, 5)
        self.assertEqual(slot.wh3d_node, 'slot')
        self.assertLess(time.perf_counter() - start, 1.0)


class TestSmartPutawayEdges(TransactionCase):
    """Ranking edge cases on a one-row warehouse (from the CodeRabbit review of Phase 7)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env['stock.warehouse'].create({'name': 'Edge', 'code': 'EDG'})
        cls.stock = cls.warehouse.lot_stock_id
        cls.row = create_p05(cls.env, cls.warehouse, x=0.0)  # x 0–1.1, y 1–19.9, against the left wall
        cls.product = cls.env['product.product'].create({
            'name': 'Cube', 'is_storable': True, 'weight': 1.0,
            'wh3d_length': 0.3, 'wh3d_width': 0.3, 'wh3d_height': 0.3})
        cls.Rule = cls.env['stock.putaway.rule']

    def dock(self, role, **kw):
        return self.env['warehouse.layout.area'].create({
            'name': 'Dock', 'kind': 'dock', 'role': role, 'warehouse_id': self.warehouse.id,
            'x': 0.0, 'y': 5.0, 'width': 1.0, 'depth': 3.0} | kw)

    def rank(self, quantity=1):
        return self.Rule._wh3d_rank_slots(self.product, quantity, self.row.slot_location_ids, self.stock)[0]

    def test_a_dispatch_dock_that_no_slot_can_reach_ranks_every_slot_last_and_unreachable(self):
        # A door may stand over a rack: its cells are blocked, so no walkable way leads to it.
        self.dock('outbound')
        ranked = self.rank()
        self.assertEqual(len(ranked), 70)
        self.assertTrue(all(r['score'] == 0 and r['distance'] is None and r['criteria'] is None for r in ranked))

    def test_without_any_dispatch_dock_distance_is_ignored_and_slots_are_still_scored(self):
        self.dock('inbound')
        ranked = self.rank()
        self.assertTrue(all(r['criteria'] is not None and r['distance'] is None for r in ranked))

    def test_a_fraction_of_a_unit_leaves_more_room_than_a_whole_unit(self):
        self.dock('outbound', x=0.0, y=30.0, width=3.0, depth=1.6)  # reachable
        whole = {r['slot'].id: r['criteria']['waste'] for r in self.rank(1)}
        tenth = {r['slot'].id: r['criteria']['waste'] for r in self.rank(0.1)}
        slot = next(iter(whole))
        self.assertAlmostEqual(tenth[slot] - whole[slot], 0.9 * 0.3 ** 3, places=6)
