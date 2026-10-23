from odoo import api, models

PENDING_KEY = 'warehouse_3d.changed_locations'


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    @api.model_create_multi
    def create(self, vals_list):
        quants = super().create(vals_list)
        quants._wh3d_notify(quants.location_id)
        return quants

    def write(self, vals):
        before = self.location_id  # a quant moved to another location changes both
        res = super().write(vals)
        if {'quantity', 'reserved_quantity', 'location_id', 'product_id'}.intersection(vals):
            self._wh3d_notify(before | self.location_id)
        return res

    def unlink(self):
        locations = self.location_id
        res = super().unlink()
        self._wh3d_notify(locations)
        return res

    def _wh3d_notify(self, locations):
        """Collect changed locations; at commit, announce the rack slots among them in one bus message.

        A receipt of 50 lines writes quants 50+ times; the 3D view should hear about it once.
        """
        if not locations:
            return
        precommit = self.env.cr.precommit
        if PENDING_KEY not in precommit.data:
            precommit.data[PENDING_KEY] = set()
            precommit.add(self._wh3d_send_changed)
        precommit.data[PENDING_KEY].update(locations.ids)

    def _wh3d_send_changed(self):
        ids = self.env.cr.precommit.data.pop(PENDING_KEY, set())
        slots = self.env['stock.location'].sudo().search([('id', 'in', list(ids)), ('wh3d_node', '=', 'slot')])
        if slots:
            self.env['bus.bus']._sendone(
                self.env.ref('stock.group_stock_user'), 'warehouse_3d/stock', {'location_ids': slots.ids})
