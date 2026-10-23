from odoo import api, fields, models


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

    _positive_size = models.Constraint(
        'CHECK(width > 0 AND depth > 0)',
        'An area must have a width and depth greater than zero.',
    )

    def _wh3d_footprint(self):
        """Floor rectangle (x0, y0, x1, y1) in metres: width runs along x, depth along y."""
        self.ensure_one()
        return self.x, self.y, self.x + self.width, self.y + self.depth

    @api.constrains('x', 'y', 'width', 'depth', 'warehouse_id')
    def _check_inside_building(self):
        self.env['stock.warehouse']._check_wh3d_contains(self)
