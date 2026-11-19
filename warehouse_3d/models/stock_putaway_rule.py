from collections import defaultdict

from odoo import api, models

from ..putaway.goods import HAZARD_CLASSES
from ..putaway.rules import allowed


def _product_info(product):
    return {
        'id': product.id, 'temp_band': product.wh3d_temp_band, 'temp_min': product.wh3d_temp_min,
        'temp_max': product.wh3d_temp_max, 'hazard': product.wh3d_hazard_class, 'fragile': product.wh3d_fragile,
        'weight': product.weight, 'dims': (product.wh3d_length, product.wh3d_width, product.wh3d_height),
    }


class StockPutawayRule(models.Model):
    _inherit = 'stock.putaway.rule'

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
        if package:
            goods |= {'package': True, 'weight': sum(
                package.quant_ids.mapped(lambda q: q.quantity * q.product_id.weight))}

        weights = slots._get_weight(set(exclude))
        result = {}
        for loc in slots:
            row = loc.wh3d_rack_row_id
            category = loc.storage_category_id
            if qty_by_location is not None:
                location_qty = qty_by_location.get(loc.id, 0.0)
            else:  # what Odoo would pass: this product on hand plus incoming
                location_qty = 0.0 if package else held.get(loc, {}).get(product, [0.0, 0.0])[1]
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
                    'product_capacity': sum(category.product_capacity_ids.filtered(
                        lambda c: c.product_id == product).mapped('quantity')) or None,
                    'package_capacity': sum(category.package_capacity_ids.filtered(
                        lambda c: package and c.package_type_id == package.package_type_id).mapped('quantity')) or None,
                } or None,
                'forecast_weight': weights[loc]['forecast_weight'],
                'location_qty': location_qty,
                'above': neighbour(loc, 1), 'below': neighbour(loc, -1),
            }
            result[loc.id] = allowed(goods, slot, contents(loc))
        return result
