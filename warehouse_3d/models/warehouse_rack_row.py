import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

CODE_RE = re.compile(r'^[A-Z]\d{2}$')


class WarehouseRackRow(models.Model):
    """One rack face. Its numbers drive both the 3D geometry and the stock.location tree."""
    _name = 'warehouse.rack.row'
    _description = 'Rack Row'
    _order = 'warehouse_id, code'
    _rec_name = 'code'

    code = fields.Char(required=True, help="Row code, a capital letter and two digits, e.g. P05.")
    kind = fields.Selection([('pallet', 'Pallet rack'), ('shelf', 'Shelving')], required=True, default='pallet')
    active = fields.Boolean(default=True)
    warehouse_id = fields.Many2one(
        'stock.warehouse', required=True, ondelete='cascade',
        default=lambda self: self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1))
    company_id = fields.Many2one(related='warehouse_id.company_id', store=True)
    location_id = fields.Many2one(
        'stock.location', string='Zone Location', required=True, ondelete='restrict',
        domain="[('usage', 'in', ('view', 'internal')), ('warehouse_id', '=', warehouse_id)]",
        help="Parent of this row's locations, e.g. WH/Stock/PR.")
    storage_category_id = fields.Many2one(
        'stock.storage.category', help="Applied to every slot location of this row (used by putaway).")

    # Position of the row's corner on the floor plan, in metres from the building's origin.
    x = fields.Float(string='X (m)', digits=(6, 2), required=True)
    y = fields.Float(string='Y (m)', digits=(6, 2), required=True)
    bays = fields.Integer(required=True, default=7)
    bay_width = fields.Float(string='Bay Width (m)', digits=(6, 2), required=True, default=2.7)
    depth = fields.Float(string='Depth (m)', digits=(6, 2), required=True, default=1.1)
    levels = fields.Integer(required=True, default=5)
    level_height = fields.Float(string='Level Height (m)', digits=(6, 2), required=True, default=1.8)
    slots_per_level = fields.Integer(required=True, default=2, help="Slots side by side in one bay level.")

    _code_warehouse_uniq = models.Constraint(
        'UNIQUE(warehouse_id, code)',
        'A rack row code must be unique within a warehouse.',
    )
    _positive_counts = models.Constraint(
        'CHECK(bays > 0 AND levels > 0 AND slots_per_level > 0)',
        'Bays, levels and slots per level must be at least 1.',
    )
    _positive_sizes = models.Constraint(
        'CHECK(bay_width > 0 AND depth > 0 AND level_height > 0)',
        'Bay width, depth and level height must be greater than zero.',
    )
    _non_negative_position = models.Constraint(
        'CHECK(x >= 0 AND y >= 0)',
        'X and Y must not be negative.',
    )

    @api.constrains('code')
    def _check_code(self):
        for row in self:
            if not CODE_RE.match(row.code or ''):
                raise ValidationError(self.env._(
                    "Rack row code %(code)s must be a capital letter followed by two digits, like P05.", code=row.code))

    @api.constrains('kind', 'slots_per_level')
    def _check_slots_per_level(self):
        for row in self:
            if row.kind == 'shelf' and row.slots_per_level != 1:
                raise ValidationError(self.env._("Shelving row %(code)s must have exactly 1 slot per level.", code=row.code))
            if row.slots_per_level > 26:
                raise ValidationError(self.env._(
                    "Rack row %(code)s: at most 26 slots per level (positions are lettered A to Z).", code=row.code))

    @api.constrains('location_id', 'warehouse_id')
    def _check_location_in_warehouse(self):
        for row in self:
            stock = row.warehouse_id.lot_stock_id
            if not row.location_id.search_count([('id', '=', row.location_id.id), ('id', 'child_of', stock.id)]):
                raise ValidationError(self.env._(
                    "Zone location %(loc)s of row %(code)s must be inside %(stock)s.",
                    loc=row.location_id.complete_name, code=row.code, stock=stock.complete_name))
