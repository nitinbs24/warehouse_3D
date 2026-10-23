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
    slot_location_ids = fields.One2many('stock.location', 'wh3d_rack_row_id', domain=[('wh3d_node', '=', 'slot')])
    slot_count = fields.Integer(compute='_compute_slot_count')

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

    @api.depends('slot_location_ids')
    def _compute_slot_count(self):
        counts = dict(self.env['stock.location']._read_group(
            [('wh3d_rack_row_id', 'in', self.ids), ('wh3d_node', '=', 'slot')], ['wh3d_rack_row_id'], ['__count']))
        for row in self:
            row.slot_count = counts.get(row, 0)

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

    @api.constrains('location_id')
    def _check_location_internal(self):
        # A Virtual (view) location restarts complete_name, which would cut every generated path short.
        for row in self:
            if row.location_id.usage != 'internal':
                raise ValidationError(self.env._(
                    "Zone location %(loc)s of row %(code)s must have the type Internal, not Virtual.",
                    loc=row.location_id.display_name, code=row.code))

    @api.model_create_multi
    def create(self, vals_list):
        rows = super().create(vals_list)
        rows._generate_locations()
        return rows

    def action_generate_locations(self):
        self._generate_locations()
        return True

    def action_view_slots(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Slots of %s", self.code),
            'res_model': 'stock.location',
            'view_mode': 'list,form',
            'domain': [('wh3d_rack_row_id', '=', self.id), ('wh3d_node', '=', 'slot')],
            'context': {'create': False},
        }

    def _slot_name(self, bay, level, position):
        if self.kind == 'pallet':
            return f'{self.code}-{bay:02d}-{level}-{chr(64 + position)}'
        return f'{self.code}-{bay:02d}-{level}'

    def _location_tree(self):
        """Wanted nodes, parents first: list of (key, parent_key, name). key = (node, bay, level, position)."""
        self.ensure_one()
        row_key = ('row', 0, 0, 0)
        tree = [(row_key, None, self.code)]
        for b in range(1, self.bays + 1):
            tree.append((('bay', b, 0, 0), row_key, f'{self.code}-{b:02d}'))
        for b in range(1, self.bays + 1):
            for lvl in range(1, self.levels + 1):
                parent = ('bay', b, 0, 0)
                if self.kind == 'pallet':
                    parent = ('level', b, lvl, 0)
                    tree.append((parent, ('bay', b, 0, 0), f'{self.code}-{b:02d}-{lvl}'))
                for p in range(1, self.slots_per_level + 1):
                    tree.append((('slot', b, lvl, p), parent, self._slot_name(b, lvl, p)))
        return tree

    def _generate_locations(self):
        """Create the missing stock.location nodes of each row. Existing ones are left as they are."""
        Location = self.env['stock.location'].with_context(active_test=False)
        for row in self:
            by_key = {
                (loc.wh3d_node, loc.wh3d_bay, loc.wh3d_level, loc.wh3d_position): loc
                for loc in Location.search([('wh3d_rack_row_id', '=', row.id)])
            }
            tree = row._location_tree()
            # One batched create per tree depth, so each node's parent already exists.
            for depth in ('row', 'bay', 'level', 'slot'):
                missing = [(key, parent, name) for key, parent, name in tree
                           if key[0] == depth and key not in by_key]
                if not missing:
                    continue
                created = Location.create([{
                    'name': name,
                    'usage': 'internal',
                    'location_id': by_key[parent].id if parent else row.location_id.id,
                    'company_id': row.company_id.id,
                    # Only slots get the category, so "closest location" putaway never picks a bay or level.
                    'storage_category_id': row.storage_category_id.id if depth == 'slot' else False,
                    'wh3d_rack_row_id': row.id,
                    'wh3d_node': key[0], 'wh3d_bay': key[1], 'wh3d_level': key[2], 'wh3d_position': key[3],
                } for key, parent, name in missing])
                by_key.update(zip((key for key, _p, _n in missing), created))
