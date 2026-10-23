from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
            warehouse._check_wh3d_contains(
                self.env['warehouse.rack.row'].search([('warehouse_id', '=', warehouse.id)]))

    def wh3d_get_layout(self):
        """The floor plan: building size, areas and rack rows (what the 2D editor needs)."""
        self.ensure_one()
        rows = self.env['warehouse.rack.row'].search([('warehouse_id', '=', self.id)])
        return {
            'warehouse_id': self.id,
            'building': {'length': self.wh3d_length, 'width': self.wh3d_width, 'height': self.wh3d_height},
            'areas': self.wh3d_area_ids.read(['name', 'kind', 'x', 'y', 'width', 'depth'], load=None),
            'rows': rows.read(['code', 'kind', 'x', 'y', 'bays', 'bay_width', 'depth', 'levels', 'level_height',
                               'slots_per_level'], load=None),
        }

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
