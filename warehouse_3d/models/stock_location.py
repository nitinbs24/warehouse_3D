from odoo import fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    # Set on locations generated from a rack row; plain Inventory locations leave them empty.
    wh3d_rack_row_id = fields.Many2one('warehouse.rack.row', string='Rack Row', index='btree_not_null', ondelete='set null')
    wh3d_node = fields.Selection(
        [('row', 'Row'), ('bay', 'Bay'), ('level', 'Level'), ('slot', 'Slot')], string='Rack Node')
    wh3d_bay = fields.Integer(string='Bay')
    wh3d_level = fields.Integer(string='Level')
    wh3d_position = fields.Integer(string='Position')
