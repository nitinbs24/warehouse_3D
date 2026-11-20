import logging
from collections import defaultdict

from markupsafe import Markup

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _action_done(self):
        """Refuse to book stock into a generated slot that breaks a hard rule (T25's rules, T28).

        Every receipt, internal transfer and inventory adjustment ends here, so this one hook covers them all.
        """
        self._wh3d_check_hard_rules()
        return super()._action_done()

    def _wh3d_check_hard_rules(self):
        lines = self.filtered(lambda l: l.quantity > 0 and l.location_dest_id.wh3d_node == 'slot')
        if not lines:
            return
        # The purpose rule looks at where the goods were sent (the move's destination, before putaway): a
        # quarantine receipt is "sent into the zone" even though putaway then picks a slot inside it.
        # shortcut: one check call per (slot, product, destination, package), not per slot set; upgrade if
        # a single validation routinely spreads over hundreds of slots.
        groups = defaultdict(lambda: self.browse())
        for line in lines:
            dest = line.move_id.location_dest_id or line.location_dest_id
            groups[line.location_dest_id, line.product_id, dest, line.result_package_id] |= line
        Rule = self.env['stock.putaway.rule'].with_context(exclude_sml_ids=set(lines.ids))
        violations = []
        for (slot, product, dest, package), group in groups.items():
            qty = sum(group.mapped('quantity_product_uom'))
            ok, reason = Rule._wh3d_check_slots(product, qty, slot, dest, package=package)[slot.id]
            if not ok:
                violations.append((group, slot, product, reason))
        if not violations:
            return
        if self.env.context.get('wh3d_override_hard_rules') and self.env.user.has_group('stock.group_stock_manager'):
            for group, slot, product, reason in violations:
                self._wh3d_log_override(group, slot, product, reason)
            return
        group, slot, product, reason = violations[0]
        raise UserError(self.env._(
            "%(product)s cannot go into %(slot)s (%(rule)s rule): %(text)s",
            product=product.display_name, slot=slot.name, rule=reason.code, text=reason.text))

    def _wh3d_log_override(self, lines, slot, product, reason):
        text = self.env._("Hard rule overridden by %(user)s: %(product)s into %(slot)s broke the %(rule)s rule (%(text)s).",
                          user=self.env.user.name, product=product.display_name, slot=slot.name,
                          rule=reason.code, text=reason.text)
        _logger.warning(text)
        # A picking has a chatter; an inventory adjustment has none, so it goes on the product.
        for target in lines.picking_id or product.product_tmpl_id:
            target.sudo().message_post(body=Markup('%s') % text)
