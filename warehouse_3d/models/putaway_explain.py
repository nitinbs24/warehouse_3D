from odoo import api, fields, models
from odoo.exceptions import UserError

HARD_RULE_TEXT = {
    'temperature': lambda p: f"product needs {p.wh3d_temp_min:g}–{p.wh3d_temp_max:g} °C" if p.wh3d_temp_band != 'none'
    else "temperature zone",
    'hazard': lambda p: f"hazard class {p.wh3d_hazard_class}" if p.wh3d_hazard_class != 'none'
    else "one hazard class per slot",
    'purpose': lambda p: "quarantine and normal rows are kept apart",
    'fit': lambda p: "product or quantity does not fit the slot",
    'fragile': lambda p: "fragile goods, heavy goods above or below",
    'inspection': lambda p: "rack not inspected green",
    'odoo_capacity': lambda p: "storage category limits",
}


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def action_wh3d_explain_putaway(self):
        """The "Why this slot?" dialog for this receipt line."""
        self.ensure_one()
        if self.state in ('done', 'cancel') or self.picking_code != 'incoming':
            raise UserError(self.env._("Only open receipt lines can be explained."))
        wizard = self.env['wh3d.putaway.explain']._wh3d_explain(self)
        return {'type': 'ir.actions.act_window', 'name': self.env._("Why this slot?"),
                'res_model': wizard._name, 'res_id': wizard.id, 'view_mode': 'form', 'target': 'new'}


class PutawayExplain(models.TransientModel):
    _name = 'wh3d.putaway.explain'
    _description = 'Why this slot?'

    line_id = fields.Many2one('stock.move.line', required=True, ondelete='cascade')
    product_id = fields.Many2one(related='line_id.product_id')
    summary = fields.Char(readonly=True)
    excluded = fields.Text(readonly=True)
    slot_ids = fields.One2many('wh3d.putaway.explain.slot', 'wizard_id', readonly=True)

    @api.model
    def _wh3d_explain(self, line):
        """Rank the slots for ``line`` and build the dialog's record.

        Which slots: the smart rule that applies (its 'when received in' contains the move's destination),
        ranked among the slots under its 'Store to'; with no such rule, the slots under the move's destination.
        The move's destination (not the line's, which putaway may already have changed) is the goods' purpose.
        """
        move = line.move_id
        product = line.product_id
        dest = move.location_dest_id or line.location_dest_id
        categs = self.env['product.category'].search([('id', 'parent_of', product.categ_id.id)])
        rules = self.env['stock.putaway.rule'].search([
            ('sublocation', '=', 'wh3d_smart'), ('location_in_id', 'parent_of', dest.id)]).filtered(
            lambda r: (not r.product_id or r.product_id == product) and (not r.category_id or r.category_id in categs))
        rule = rules.sorted(lambda r: (bool(r.product_id), bool(r.category_id)), reverse=True)[:1]
        root = rule.location_out_id or dest
        slots = self.env['stock.location'].search([('id', 'child_of', root.id), ('wh3d_node', '=', 'slot')])
        Rule = self.env['stock.putaway.rule'].with_context(exclude_sml_ids=set(line.ids))
        # shortcut: ranks the product alone, ignoring a result package; refine if receipts are palletised.
        ranked, removed = Rule._wh3d_rank_slots(product, line.quantity_product_uom or move.product_uom_qty, slots, dest)
        # shortcut: top 3 only; the 3D view and the rule list cover the rest.
        choices = [(0, 0, {
            'slot_id': r['slot'].id, 'score': r['score'], 'distance': r['distance'] or 0.0, 'level': r['level'],
            'reasons': self._wh3d_reasons(r)}) for r in ranked[:3]]
        excluded = [self.env._("%(count)s slots excluded: %(rule)s (%(why)s)", count=count, rule=code,
                               why=HARD_RULE_TEXT.get(code, lambda p: code)(product))
                    for code, count in removed.most_common()]
        if rule:
            summary = self.env._("%(count)s slots under %(root)s, rule %(rule)s", count=len(slots),
                                 root=root.display_name, rule=rule.display_name)
        else:
            summary = self.env._("No Smart rule applies: %(count)s slots under %(root)s", count=len(slots),
                                 root=root.display_name)
        return self.create({'line_id': line.id, 'summary': summary, 'excluded': '\n'.join(excluded), 'slot_ids': choices})

    @api.model
    def _wh3d_reasons(self, ranked):
        if ranked['criteria'] is None:
            return self.env._("no walkable way to a dispatch dock")
        parts = []
        if ranked['distance'] is not None:
            parts.append(self.env._("%(m).0f m from dispatch", m=ranked['distance']))
        z = ranked['z']
        parts.append(self.env._("floor level") if z < 0.5 else self.env._("waist height") if 0.7 <= z <= 1.5
                     else self.env._("high up") if z > 1.5 else self.env._("low shelf"))
        if ranked['criteria']['consolidation']:
            parts.append(self.env._("already holds this product"))
        parts.append(self.env._("%(v).2f m³ left", v=ranked['criteria']['waste']))
        return ' · '.join(parts)


class PutawayExplainSlot(models.TransientModel):
    _name = 'wh3d.putaway.explain.slot'
    _description = 'Why this slot? candidate'
    _order = 'id'

    wizard_id = fields.Many2one('wh3d.putaway.explain', required=True, ondelete='cascade')
    slot_id = fields.Many2one('stock.location', string='Slot', readonly=True)
    score = fields.Float(digits=(3, 2), readonly=True)
    distance = fields.Float(string='To dispatch (m)', digits=(6, 1), readonly=True)
    level = fields.Integer(readonly=True)
    reasons = fields.Char(readonly=True)

    def action_choose(self):
        self.ensure_one()
        self.wizard_id.line_id.location_dest_id = self.slot_id
        return {'type': 'ir.actions.act_window_close'}
