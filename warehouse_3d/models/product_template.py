from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Odoo only stores weight and volume; the 3D view and later the putaway experiments need the box shape.
    # 0 means "unknown": such products show without a fill % in the 3D view.
    wh3d_length = fields.Float(string='Length (m)', digits=(6, 3))
    wh3d_width = fields.Float(string='Width (m)', digits=(6, 3))
    wh3d_height = fields.Float(string='Height (m)', digits=(6, 3))
    # How often it's picked (A fast, B medium, C slow). Kept for the later putaway experiments
    # (slotting fast movers near the docks); the 3D view colours by fill, not by class.
    wh3d_abc_class = fields.Selection([('A', 'A - fast mover'), ('B', 'B - medium'), ('C', 'C - slow mover')],
                                      string='ABC Class')
