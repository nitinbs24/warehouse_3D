import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
EPS = 1e-6  # metres; floating-point slack for "touching" comparisons


class WarehouseLayoutArea(models.Model):
    """A floor area (receiving, packing, …) or a dock door, drawn on the floor plan. Holds no stock."""
    _name = 'warehouse.layout.area'
    _description = 'Layout Area'
    _order = 'warehouse_id, kind, name'

    name = fields.Char(required=True)
    kind = fields.Selection([('area', 'Floor area'), ('dock', 'Dock door')], required=True, default='area')
    warehouse_id = fields.Many2one(
        'stock.warehouse', required=True, ondelete='cascade',
        default=lambda self: self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1))
    company_id = fields.Many2one(related='warehouse_id.company_id', store=True)
    # Corner on the floor plan and size, in metres; same axes as rack rows (x along the length).
    x = fields.Float(string='X (m)', digits=(6, 2), required=True)
    y = fields.Float(string='Y (m)', digits=(6, 2), required=True)
    width = fields.Float(string='Width (m)', digits=(6, 2), required=True, help="Size along X.")
    depth = fields.Float(string='Depth (m)', digits=(6, 2), required=True, help="Size along Y.")
    color = fields.Char(default='#c3d0dc', required=True, help="Floor colour in the 3D view, as #rrggbb.")

    _positive_size = models.Constraint(
        'CHECK(width > 0 AND depth > 0)',
        'An area must have a width and depth greater than zero.',
    )

    def _wh3d_footprint(self):
        """Floor rectangle (x0, y0, x1, y1) in metres: width runs along x, depth along y."""
        self.ensure_one()
        return self.x, self.y, self.x + self.width, self.y + self.depth

    @api.constrains('color')
    def _check_color(self):
        for area in self:
            if not COLOR_RE.fullmatch(area.color or ''):
                raise ValidationError(self.env._(
                    "Area %(name)s: the color must look like #rrggbb, e.g. #c3d0dc.", name=area.name))

    @api.constrains('x', 'y', 'width', 'depth', 'kind', 'warehouse_id')
    def _check_layout(self):
        if self.env.context.get('wh3d_defer_layout_check'):
            return  # wh3d_save_layout checks the end state once all edits are applied
        warehouse = self.env['stock.warehouse']
        warehouse._check_wh3d_contains(self)
        for dock in self.filtered(lambda a: a.kind == 'dock'):
            building = dock.warehouse_id
            x0, y0, x1, y1 = dock._wh3d_footprint()
            if min(x0, y0, building.wh3d_length - x1, building.wh3d_width - y1) > EPS:
                raise ValidationError(self.env._(
                    "Dock door %(name)s must touch a wall of the building.", name=dock.name))
        for building in self.warehouse_id:
            rows = self.env['warehouse.rack.row'].search([('warehouse_id', '=', building.id)])
            warehouse._check_wh3d_areas_clear_of_rows(self.filtered(lambda a: a.warehouse_id == building), rows)
