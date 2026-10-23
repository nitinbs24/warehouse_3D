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

    @api.model
    def _check_wh3d_contains(self, footprints):
        """Refuse when any record in ``footprints`` (with x, y, width, depth) sticks out of its building."""
        for item in footprints:
            wh = item.warehouse_id
            inside = (item.x >= 0 and item.y >= 0
                      and item.x + item.width <= wh.wh3d_length
                      and item.y + item.depth <= wh.wh3d_width)
            if not inside:
                raise ValidationError(self.env._(
                    "%(item)s (x %(x)s–%(x2)s m, y %(y)s–%(y2)s m) must lie inside the %(l)s × %(w)s m building of %(wh)s.",
                    item=item.display_name, x=item.x, x2=item.x + item.width, y=item.y, y2=item.y + item.depth,
                    l=wh.wh3d_length, w=wh.wh3d_width, wh=wh.name))
