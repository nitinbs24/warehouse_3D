from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..putaway.goods import BAND_SELECTION, HAZARD_CLASSES, TEMP_BANDS


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

    # Special goods (smart putaway's hard rules). The band, not the floats, says whether there is a
    # requirement: Odoo reads an empty float as 0.0, and 0 °C is a real bound (chilled food).
    wh3d_temp_band = fields.Selection([('none', 'No requirement')] + BAND_SELECTION, string='Storage Temperature',
                                      required=True, default='none')
    wh3d_temp_min = fields.Float(string='Min Temperature (°C)', digits=(4, 1),
                                 compute='_compute_wh3d_temp_range', store=True, readonly=False)
    wh3d_temp_max = fields.Float(string='Max Temperature (°C)', digits=(4, 1),
                                 compute='_compute_wh3d_temp_range', store=True, readonly=False)
    wh3d_hazard_class = fields.Selection([('none', 'None')] + HAZARD_CLASSES, string='Hazard Class',
                                         required=True, default='none')
    wh3d_fragile = fields.Boolean(string='Fragile')

    @api.depends('wh3d_temp_band')
    def _compute_wh3d_temp_range(self):
        for product in self:
            band = product.wh3d_temp_band
            if band in TEMP_BANDS:
                _label, product.wh3d_temp_min, product.wh3d_temp_max = TEMP_BANDS[band]
            elif band != 'custom':
                product.wh3d_temp_min = product.wh3d_temp_max = 0.0
            # custom: keep what the user typed

    @api.constrains('wh3d_temp_band', 'wh3d_temp_min', 'wh3d_temp_max')
    def _check_wh3d_temp_range(self):
        for product in self:
            if product.wh3d_temp_band != 'none' and product.wh3d_temp_min > product.wh3d_temp_max:
                raise ValidationError(self.env._(
                    "%(name)s: the minimum temperature must not be above the maximum.", name=product.display_name))
