from odoo import fields, models
from odoo.exceptions import UserError

# Owned by the rack row: change the row, not the location. Only _sync_locations may write them.
LOCKED_FIELDS = ('name', 'location_id', 'usage')


class StockLocation(models.Model):
    _inherit = 'stock.location'

    # Set on locations generated from a rack row; plain Inventory locations leave them empty.
    # copy=False: a duplicated location is a plain one, never a second claim on the same rack slot.
    wh3d_rack_row_id = fields.Many2one(
        'warehouse.rack.row', string='Rack Row', index='btree_not_null', ondelete='set null', copy=False)
    wh3d_node = fields.Selection(
        [('row', 'Row'), ('bay', 'Bay'), ('level', 'Level'), ('slot', 'Slot')], string='Rack Node', copy=False)
    wh3d_bay = fields.Integer(string='Bay', copy=False)
    wh3d_level = fields.Integer(string='Level', copy=False)
    wh3d_position = fields.Integer(string='Position', copy=False)

    def write(self, vals):
        if not self.env.context.get('wh3d_sync') and any(f in vals for f in LOCKED_FIELDS):
            for loc in self.filtered('wh3d_rack_row_id'):
                current = {'name': loc.name, 'location_id': loc.location_id.id, 'usage': loc.usage}
                if any(f in vals and vals[f] != current[f] for f in LOCKED_FIELDS):
                    raise UserError(self.env._(
                        "Location %(loc)s is managed by rack row %(row)s. Change the rack row instead "
                        "(Inventory ▸ Configuration ▸ Warehouse 3D ▸ Rack Rows).",
                        loc=loc.name, row=loc.wh3d_rack_row_id.code))
        return super().write(vals)
