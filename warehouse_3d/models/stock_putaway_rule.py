import logging
from collections import Counter, defaultdict

from odoo import api, fields, models

from ..putaway import score
from ..putaway.goods import HAZARD_CLASSES
from ..putaway.rules import HEAVY_KG, allowed

_logger = logging.getLogger(__name__)


def _product_info(product):
    return {
        'id': product.id, 'temp_band': product.wh3d_temp_band, 'temp_min': product.wh3d_temp_min,
        'temp_max': product.wh3d_temp_max, 'hazard': product.wh3d_hazard_class, 'fragile': product.wh3d_fragile,
        'weight': product.weight, 'dims': (product.wh3d_length, product.wh3d_width, product.wh3d_height),
    }


class StockPutawayRule(models.Model):
    _inherit = 'stock.putaway.rule'

    sublocation = fields.Selection(selection_add=[('wh3d_smart', 'Smart (Warehaven)')],
                                   ondelete={'wh3d_smart': 'set default'})

    def _get_putaway_location(self, product, quantity=0, package=None, packaging=None, qty_by_location=None):
        # One rule at a time, in Odoo's order (first non-empty wins). Odoo's own loop only shares a "checked"
        # cache between rules, which never changes the answer.
        for rule in self:
            if rule.sublocation == 'wh3d_smart':
                location = rule._wh3d_smart_location(product, quantity, package)
            else:
                location = super(StockPutawayRule, rule)._get_putaway_location(
                    product, quantity, package, packaging, qty_by_location)
            if location:
                return location
        return None

    def _wh3d_smart_location(self, product, quantity, package):
        """The best allowed slot under 'Store to', or an empty recordset (Odoo then keeps the destination)."""
        self.ensure_one()
        slots = self.env['stock.location'].search(
            [('id', 'child_of', self.location_out_id.id), ('wh3d_node', '=', 'slot')])
        # The goods' purpose (quarantine …) follows from the rule's own 'when received in' location, which
        # is where Odoo asked for a putaway.
        ranked, removed = self._wh3d_rank_slots(product, quantity, slots, self.location_in_id, package)
        if ranked:
            return ranked[0]['slot']
        _logger.info("Smart putaway: no allowed slot under %s for %s (%d slots, removed by rule: %s)",
                     self.location_out_id.display_name, (product or self.env.context.get('products')).display_name,
                     len(slots), dict(removed))
        return self.env['stock.location']

    @api.model
    def _wh3d_rank_slots(self, product, quantity, slots, dest, package=None):
        """Rank ``slots`` for these goods: ``(ranked, removed)``.

        ``ranked``: best first, a list of {'slot': record, 'score': TOPSIS closeness 0..1, 'criteria': {'travel'
        (m to dispatch), 'height' (cost, 0 = ideal), 'consolidation' (1 = same product there), 'waste' (m³ left
        over)}, 'distance': m to the nearest dispatch dock or None, 'level': int, 'z': m}. Slots with no way to
        a dispatch dock come last with score 0.
        ``removed``: {hard rule code: number of slots it removed} (see putaway.rules).
        """
        checks = self._wh3d_check_slots(product, quantity, slots, dest, package)
        removed = Counter(reason.code for ok, reason in checks.values() if not ok)
        slots = slots.filtered(lambda s: checks[s.id][0])
        if not slots:
            return [], removed
        products = (self.env.context.get('products') or self.env['product.product']) | product
        classes = [p.wh3d_abc_class or score.DEFAULT_ABC for p in products]
        goods = {'abc': min(classes), 'heavy': any(p.weight > HEAVY_KG for p in products),
                 'fragile': any(p.wh3d_fragile for p in products)}  # 'A' < 'B' < 'C': the most demanding class
        # shortcut: a package's own volume is not counted as incoming, and stock on its way is not counted as
        # used; only what is on hand. Refine if slots are often filled by a batch of receipts.
        incoming = (product.wh3d_length * product.wh3d_width * product.wh3d_height * (quantity or 1)
                    if len(products) == 1 and not package else 0.0)
        used, there = defaultdict(float), set()
        for loc, prod, qty in self.env['stock.quant']._read_group(
                [('location_id', 'in', slots.ids), ('quantity', '>', 0)], ['location_id', 'product_id'], ['quantity:sum']):
            used[loc.id] += qty * prod.wh3d_length * prod.wh3d_width * prod.wh3d_height
            if prod in products:
                there.add(loc.id)
        distance = {}
        for warehouse in slots.wh3d_rack_row_id.warehouse_id:
            distance.update({k: v[0] for k, v in warehouse._wh3d_slot_distances().items()})
        has_dispatch = any(a.kind == 'dock' and a.role in ('outbound', 'both')
                           for a in slots.wh3d_rack_row_id.warehouse_id.wh3d_area_ids)
        if not has_dispatch:
            distance = {}  # no dispatch dock at all: distance can't separate the slots
        # With a dock that nothing can reach, distances stay None: those slots rank last with no criteria.
        candidates = []
        for s in slots:
            row = s.wh3d_rack_row_id
            capacity = row.bay_width / row.slots_per_level * row.depth * row.level_height
            candidates.append({'dispatch': distance.get(s.id) if distance else 0.0, 'z': (s.wh3d_level - 0.5) * row.level_height,
                               'has_product': s.id in there, 'free_m3': max(0.0, capacity - used[s.id] - incoming)})
        reachable = [i for i, c in enumerate(candidates) if c['dispatch'] is not None]
        scores = dict(zip(reachable, score.score(goods, [candidates[i] for i in reachable])))
        ranked = [{
            'slot': s, 'score': scores.get(i, 0.0), 'distance': c['dispatch'] if distance else None,
            'level': s.wh3d_level, 'z': c['z'],
            'criteria': dict(zip(score.CRITERIA, score.criteria_row(goods, c))) if i in scores else None,
        } for i, (s, c) in enumerate(zip(slots, candidates))]
        ranked.sort(key=lambda r: (-r['score'], r['slot'].id))
        return ranked, removed

    @api.model
    def _wh3d_check_slots(self, product, quantity, slots, dest, package=None, qty_by_location=None):
        """Run the hard rules (putaway.rules.allowed) on every slot in ``slots``: {slot id: (ok, reason)}.

        ``dest`` is where the goods were sent (a quarantine zone, or plain WH/Stock); ``product`` may be
        empty for a package, whose products then come from ``context['products']`` as in Odoo.
        Contents include stock on its way (move lines not done), so lines planned together don't clash.
        A fixed number of queries, however many slots and rows.
        """
        Location = self.env['stock.location']
        slots = Location.browse(slots.ids)  # own prefetch set: a caller's (e.g. a one2many's) may fetch one by one
        products = (self.env.context.get('products') or self.env['product.product']) | product
        exclude = tuple(self.env.context.get('exclude_sml_ids', set()))
        rows = slots.wh3d_rack_row_id
        row_slots = Location.search([('wh3d_rack_row_id', 'in', rows.ids), ('wh3d_node', '=', 'slot')]) | slots
        by_key = {(s.wh3d_rack_row_id.id, s.wh3d_bay, s.wh3d_level, s.wh3d_position): s for s in row_slots}

        # Contents of the candidates and their neighbours: {location: {product: [on hand, on hand + incoming]}}.
        held = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
        for loc, prod, qty in self.env['stock.quant']._read_group(
                [('location_id', 'in', row_slots.ids)], ['location_id', 'product_id'], ['quantity:sum']):
            held[loc][prod][0] += qty
            held[loc][prod][1] += qty
        for loc, prod, qty in self.env['stock.move.line']._read_group(
                [('location_dest_id', 'in', row_slots.ids), ('state', 'not in', ('done', 'cancel')), ('id', 'not in', exclude)],
                ['location_dest_id', 'product_id'], ['quantity_product_uom:sum']):
            held[loc][prod][1] += qty
        info = {p: _product_info(p) for p in products.union(*(prod for by_prod in held.values() for prod in by_prod))}

        def contents(loc):
            return [info[p] | {'on_hand': on_hand, 'qty': total} for p, (on_hand, total) in held.get(loc, {}).items()
                    if on_hand > 0 or total > on_hand]

        def neighbour(loc, step):
            other = by_key.get((loc.wh3d_rack_row_id.id, loc.wh3d_bay, loc.wh3d_level + step, loc.wh3d_position))
            return contents(other) if other else []

        # Where the goods were sent decides their purpose: inside a quarantine row's zone = quarantine goods.
        special = self.env['warehouse.rack.row'].search(
            [('purpose', '!=', 'normal'), ('location_id', 'parent_of', dest.id)], limit=1)
        goods = {'products': [info[p] for p in products], 'qty': quantity, 'dest_path': dest.parent_path,
                 'purpose': special.purpose or 'normal'}
        # As Odoo: the package path only for a typed package, weighed by its open move lines (a received
        # package has no quants until the receipt is done).
        typed_package = package if package and package.package_type_id else None
        if typed_package:
            goods |= {'package': True, 'weight': sum(qty * prod.weight for prod, qty in self.env['stock.move.line']._read_group(
                [('result_package_id', '=', typed_package.id), ('state', 'not in', ('done', 'cancel'))],
                ['product_id'], ['quantity_product_uom:sum']))}

        weights = slots._get_weight(set(exclude))
        categories = slots.storage_category_id
        product_cap = {c.storage_category_id: c.quantity for c in categories.product_capacity_ids if c.product_id == product}
        package_cap = {c.storage_category_id: c.quantity for c in categories.package_capacity_ids
                       if typed_package and c.package_type_id == typed_package.package_type_id}
        result = {}
        for loc in slots:
            row = loc.wh3d_rack_row_id
            category = loc.storage_category_id
            if qty_by_location is not None:
                location_qty = qty_by_location.get(loc.id, 0.0)
            else:  # what Odoo would pass: this product on hand plus incoming
                location_qty = 0.0 if typed_package else held.get(loc, {}).get(product, [0.0, 0.0])[1]
            slot = {
                'id': loc.id,
                'row': {
                    'temp_band': row.temp_band, 'temp_min': row.temp_min, 'temp_max': row.temp_max,
                    'hazards': {key for key, _label in HAZARD_CLASSES if row[f'hazard_{key}']},
                    'purpose': row.purpose, 'inspection_status': row.inspection_status,
                    'zone_path': row.location_id.parent_path,
                },
                'size': (row.bay_width / row.slots_per_level, row.depth, row.level_height),
                'capacity_m3': row.bay_width / row.slots_per_level * row.depth * row.level_height,
                'category': category and {
                    'max_weight': category.max_weight, 'allow_new_product': category.allow_new_product,
                    'product_capacity': product_cap.get(category), 'package_capacity': package_cap.get(category),
                } or None,
                'forecast_weight': weights[loc]['forecast_weight'],
                'location_qty': location_qty,
                'above': neighbour(loc, 1), 'below': neighbour(loc, -1),
            }
            result[loc.id] = allowed(goods, slot, contents(loc))
        return result
