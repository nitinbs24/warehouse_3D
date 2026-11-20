import math
import random

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..putaway.aisles import slot_distances
from ..putaway.goods import HAZARD_CLASSES
from ..putaway.rules import HEAVY_KG
from .warehouse_rack_row import GOODS_FIELDS


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    # The building's inside dimensions in metres; the floor plan's origin is one corner.
    wh3d_length = fields.Float(string='Building Length (m)', digits=(6, 2), default=60.0, help="Along X.")
    wh3d_width = fields.Float(string='Building Width (m)', digits=(6, 2), default=40.0, help="Along Y.")
    wh3d_height = fields.Float(string='Clear Height (m)', digits=(6, 2), default=10.0)
    wh3d_area_ids = fields.One2many('warehouse.layout.area', 'warehouse_id', string='Layout Areas')

    @api.constrains('wh3d_length', 'wh3d_width', 'wh3d_height')
    def _check_wh3d_size(self):
        for warehouse in self:
            if min(warehouse.wh3d_length, warehouse.wh3d_width, warehouse.wh3d_height) <= 0:
                raise ValidationError(self.env._(
                    "Warehouse %(wh)s: building length, width and height must be greater than zero.",
                    wh=warehouse.name))
            warehouse._check_wh3d_contains(warehouse.wh3d_area_ids)
            rows = self.env['warehouse.rack.row'].search([('warehouse_id', '=', warehouse.id)])
            warehouse._check_wh3d_contains(rows)
            rows._check_clear_height()

    @api.model
    def wh3d_default_warehouse_id(self):
        """The warehouse the 3D view and editor open: the first one with a rack layout, else the first."""
        rows = self.env['warehouse.rack.row'].search([], order='warehouse_id')
        warehouses = self.search([])
        with_rows = warehouses.filtered(lambda w: w in rows.warehouse_id)
        return (with_rows or warehouses)[:1].id

    @api.model
    def wh3d_list_warehouses(self):
        """The warehouses the user may open in the 3D view and the editor: [{id, name, code, row_count}]."""
        warehouses = self.search([])  # the usual warehouse order; company rules apply
        counts = dict(self.env['warehouse.rack.row']._read_group(
            [('warehouse_id', 'in', warehouses.ids)], ['warehouse_id'], ['__count']))
        return [{'id': w.id, 'name': w.name, 'code': w.code, 'row_count': counts.get(w, 0)} for w in warehouses]

    def action_wh3d_open_view3d(self):
        return self._wh3d_open('warehouse_3d.action_wh3d_view3d')

    def action_wh3d_open_editor(self):
        return self._wh3d_open('warehouse_3d.action_wh3d_editor')

    def _wh3d_open(self, xmlid):
        """One of our client actions, told (through its context) which warehouse to show."""
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id(xmlid)
        action['context'] = {'warehouse_id': self.id}
        return action

    def wh3d_get_layout(self):
        """The floor plan: building size, areas and rack rows (what the 2D editor needs)."""
        self.ensure_one()
        rows = self.env['warehouse.rack.row'].search([('warehouse_id', '=', self.id)])
        return {
            'warehouse_id': self.id,
            'name': self.name,
            'building': {'length': self.wh3d_length, 'width': self.wh3d_width, 'height': self.wh3d_height},
            'areas': self.wh3d_area_ids.read(['name', 'kind', 'x', 'y', 'width', 'depth', 'color', 'role'], load=None),
            'rows': rows.read(['code', 'kind', 'x', 'y', 'bays', 'bay_width', 'depth', 'levels', 'level_height',
                               'slots_per_level', *GOODS_FIELDS], load=None),
        }

    def _wh3d_slot_distances(self):
        """{slot location id: (metres to the nearest dispatch dock, … receiving dock)}; None = no such dock or no way.

        Walkable distances around the racks (putaway/aisles.py). Cached on the layout's geometry, so any
        change to rows, docks or the building size is picked up.
        """
        self.ensure_one()
        rows = self.env['warehouse.rack.row'].search([('warehouse_id', '=', self.id)])
        docks = self.wh3d_area_ids.filtered(lambda a: a.kind == 'dock')
        distances = slot_distances(
            (self.wh3d_length, self.wh3d_width),
            tuple((r.id, r.x, r.y, r.depth, r.bays, r.bay_width, r.slots_per_level) for r in rows),
            tuple((d.x, d.y, d.width, d.depth, d.role) for d in docks))
        slots = self.env['stock.location'].search([('wh3d_rack_row_id', 'in', rows.ids), ('wh3d_node', '=', 'slot')])
        return {s.id: distances[(s.wh3d_rack_row_id.id, s.wh3d_bay, s.wh3d_position)] for s in slots}

    def wh3d_get_scene(self):
        """Everything the 3D view draws for this warehouse, in one call (a fixed number of queries)."""
        scene = self.wh3d_get_layout()
        slots = self.env['stock.location'].search(
            [('wh3d_rack_row_id', 'in', [r['id'] for r in scene['rows']]), ('wh3d_node', '=', 'slot')])
        scene['slots'] = self._wh3d_slot_data(slots)
        return scene

    @api.model
    def wh3d_get_slots(self, location_ids):
        """Fresh data for some slots (live updates). Ids that aren't active slots are ignored."""
        slots = self.env['stock.location'].search([('id', 'in', location_ids), ('wh3d_node', '=', 'slot')])
        return self._wh3d_slot_data(slots)

    @api.model
    def _wh3d_slot_data(self, slots):
        quants = self.env['stock.quant']._read_group(
            [('location_id', 'in', slots.ids), ('quantity', '>', 0)],
            ['location_id', 'product_id'], ['quantity:sum'])
        by_slot = {}
        for location, product, qty in quants:
            by_slot.setdefault(location, []).append((product, qty))
        return [self._wh3d_slot_dict(slot, by_slot.get(slot, [])) for slot in slots]

    @api.model
    def _wh3d_slot_dict(self, slot, contents):
        row = slot.wh3d_rack_row_id
        capacity = row.bay_width / row.slots_per_level * row.depth * row.level_height
        stock = None
        if contents:
            product, qty = max(contents, key=lambda pq: pq[1])
            volumes = [p.wh3d_length * p.wh3d_width * p.wh3d_height * q for p, q in contents]
            used = sum(volumes) if all(volumes) else None  # one product without dimensions: fill unknown
            stock = {
                'product_id': product.id, 'name': product.name, 'default_code': product.default_code or '',
                'qty': qty, 'uom': product.uom_id.name, 'mixed': len(contents) > 1,
                'used_m3': used, 'fill': used / capacity if used is not None else None,
            }
        return {
            'location_id': slot.id, 'code': slot.name, 'path': slot.complete_name, 'row_id': row.id,
            'bay': slot.wh3d_bay, 'level': slot.wh3d_level, 'position': slot.wh3d_position,
            'capacity_m3': capacity, 'stock': stock,
        }

    # --- template warehouse opening stock (demo data) ---

    # How much more often a fast mover is stocked than a slow one.
    _WH3D_ABC_WEIGHT = {'A': 6, 'B': 2, 'C': 1}
    # Target fill ranges for the three colours of "Colour by occupancy"; drawn evenly so the
    # demo shows all three (green < 50 %, amber 50–90 %, red > 90 %).
    _WH3D_FILL_BANDS = ((0.25, 0.45), (0.55, 0.85), (0.94, 0.99))

    @api.model
    def _wh3d_plan_template_stock(self, warehouse, seed=20261023, occupancy=0.65):
        """Decide the opening stock of a template warehouse: [(slot, product, quantity)].

        Pure planning, no writes, deterministic for a given seed: about ``occupancy`` of the slots get one
        product each (bulk goods on pallet rows, small parts on shelves, fast movers more often), in a
        quantity that fills the slot to a randomly chosen fill band. Only placements the hard rules accept
        are planned: rows that are quarantine, returns or not green stay empty; goods with a temperature
        or hazard requirement go only to rows that offer it, and ordinary goods only to ordinary rows;
        the product must fit the slot, the quantity stays under the category's weight limit, and a fragile
        product never sits directly below a heavy one (the neighbours planned so far are tracked).
        """
        rng = random.Random(seed)
        Product = self.env['product.product']
        products = {
            'pallet': Product.search([('categ_id', '=', self.env.ref('warehouse_3d.categ_bulk').id)], order='default_code'),
            'shelf': Product.search([('categ_id', '=', self.env.ref('warehouse_3d.categ_small_parts').id)], order='default_code'),
        }
        rows = self.env['warehouse.rack.row'].search([('warehouse_id', '=', warehouse.id)])
        eligible = {}  # row -> ([product], [weight]); computed once per row
        for row in rows:
            if row.purpose != 'normal' or row.inspection_status != 'green':
                continue
            pool = [p for p in products[row.kind] if self._wh3d_template_row_takes(row, p)]
            eligible[row] = (pool, [self._WH3D_ABC_WEIGHT.get(p.wh3d_abc_class, 1) for p in pool])
        slots = self.env['stock.location'].search(
            [('wh3d_rack_row_id', 'in', rows.ids), ('wh3d_node', '=', 'slot')], order='complete_name')
        planned = {}  # (row id, bay, level, position) -> product, for the stacking rule
        plan = []
        for slot in slots:
            row = slot.wh3d_rack_row_id
            if row not in eligible or rng.random() >= occupancy:
                continue
            key = (row.id, slot.wh3d_bay, slot.wh3d_level, slot.wh3d_position)
            below, above = (planned.get(key[:2] + (key[2] + d, key[3])) for d in (-1, 1))
            pool, weights = eligible[row]
            capacity = row.bay_width / row.slots_per_level * row.depth * row.level_height
            limit = row.storage_category_id.max_weight or 1e9  # no limit
            band = rng.choice(self._WH3D_FILL_BANDS)

            def reaches(p):  # can the weight limit still let this product fill the slot to the band?
                return limit / p.weight * p.wh3d_length * p.wh3d_width * p.wh3d_height / capacity >= band[0]

            choices = [(p, w) for p, w in zip(pool, weights)
                       if not (p.wh3d_fragile and above and above.weight > HEAVY_KG)
                       and not (p.weight > HEAVY_KG and below and below.wh3d_fragile)]
            choices = [(p, w) for p, w in choices if reaches(p)] or choices
            if not choices:
                continue
            product = rng.choices([p for p, _w in choices], weights=[w for _p, w in choices])[0]
            unit = product.wh3d_length * product.wh3d_width * product.wh3d_height
            qty = max(1, min(math.floor(rng.uniform(*band) * capacity / unit), math.floor(limit / product.weight)))
            planned[key] = product
            plan.append((slot, product, qty))
        return plan

    @api.model
    def _wh3d_template_row_takes(self, row, product):
        """May this product be stocked in this row of the template? (the hard rules' temperature, hazard and fit
        checks, as fields; tests/test_template.py proves the plan against putaway.rules itself)"""
        eps = 1e-6
        row_special = row.temp_band != 'ambient' or any(row[f'hazard_{key}'] for key, _label in HAZARD_CLASSES)
        product_special = product.wh3d_temp_band != 'none' or product.wh3d_hazard_class != 'none'
        if row_special != product_special:
            return False  # cold and hazard rows hold only goods that need them; ordinary rows only ordinary goods
        if product.wh3d_temp_band != 'none' and (
                row.temp_band == 'ambient' or row.temp_min < product.wh3d_temp_min - eps
                or row.temp_max > product.wh3d_temp_max + eps):
            return False
        if product.wh3d_hazard_class != 'none' and not row[f'hazard_{product.wh3d_hazard_class}']:
            return False
        width, depth, height = row.bay_width / row.slots_per_level, row.depth, row.level_height
        l, w, h = product.wh3d_length, product.wh3d_width, product.wh3d_height
        return h <= height + eps and ((l <= width + eps and w <= depth + eps) or (w <= width + eps and l <= depth + eps)) \
            and product.weight <= (row.storage_category_id.max_weight or float('inf'))

    @api.model
    def _wh3d_fill_template_stock(self, warehouse_id, seed=20261023):
        """Book the planned opening stock as one inventory adjustment (called from the demo data)."""
        warehouse = self.browse(warehouse_id)
        plan = self._wh3d_plan_template_stock(warehouse, seed=seed)
        quants = self.env['stock.quant'].with_context(inventory_mode=True).create([
            {'product_id': product.id, 'location_id': slot.id, 'inventory_quantity': qty}
            for slot, product, qty in plan])
        quants.with_context(inventory_name='Warehaven DC opening stock').action_apply_inventory()

    @api.model
    def _check_wh3d_contains(self, items):
        """Refuse when any of ``items`` (layout areas or rack rows) sticks out of its building."""
        eps = 1e-6  # touching a wall is fine
        for item in items:
            wh = item.warehouse_id
            x0, y0, x1, y1 = item._wh3d_footprint()
            if x0 < -eps or y0 < -eps or x1 > wh.wh3d_length + eps or y1 > wh.wh3d_width + eps:
                raise ValidationError(self.env._(
                    "%(item)s (x %(x0)s–%(x1)s m, y %(y0)s–%(y1)s m) must lie inside the %(l)s × %(w)s m building of %(wh)s.",
                    item=item.display_name, x0=round(x0, 2), x1=round(x1, 2), y0=round(y0, 2), y1=round(y1, 2),
                    l=wh.wh3d_length, w=wh.wh3d_width, wh=wh.name))

    @api.model
    def _check_wh3d_areas_clear_of_rows(self, areas, rows):
        """Refuse when a floor area (docks excluded) overlaps a rack row; touching edges are fine."""
        eps = 1e-6
        for area in areas.filtered(lambda a: a.kind == 'area'):
            ax0, ay0, ax1, ay1 = area._wh3d_footprint()
            for row in rows.filtered(lambda r: r.active and r.warehouse_id == area.warehouse_id):
                x0, y0, x1, y1 = row._wh3d_footprint()
                if ax0 < x1 - eps and x0 < ax1 - eps and ay0 < y1 - eps and y0 < ay1 - eps:
                    raise ValidationError(self.env._(
                        "Area %(area)s and rack row %(row)s overlap on the floor plan "
                        "(%(area)s: x %(ax0)s–%(ax1)s m, y %(ay0)s–%(ay1)s m; %(row)s: x %(x0)s–%(x1)s m, y %(y0)s–%(y1)s m).",
                        area=area.name, row=row.code,
                        ax0=round(ax0, 2), ax1=round(ax1, 2), ay0=round(ay0, 2), ay1=round(ay1, 2),
                        x0=round(x0, 2), x1=round(x1, 2), y0=round(y0, 2), y1=round(y1, 2)))
