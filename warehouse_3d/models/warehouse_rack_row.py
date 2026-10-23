import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

CODE_RE = re.compile(r'^[A-Z]\d{2}$')
# Fields that decide which locations exist and what they're called.
SHAPE_FIELDS = frozenset({'code', 'kind', 'bays', 'levels', 'slots_per_level'})
# Fields whose change needs the location tree updated.
SYNC_FIELDS = SHAPE_FIELDS | {'location_id', 'storage_category_id', 'active'}


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
        rows._sync_locations()
        return rows

    def write(self, vals):
        # Check before writing, so a refused change leaves the row and its locations untouched.
        if SHAPE_FIELDS.intersection(vals) or vals.get('active') is False:
            for row in self:
                row._check_no_stock_in(row._nodes_to_remove(vals))
        res = super().write(vals)
        if SYNC_FIELDS.intersection(vals):
            self._sync_locations()
        return res

    def unlink(self):
        for row in self:
            row._check_no_stock_in(row._nodes())
        # Locations are archived, never deleted: Inventory history (moves, counts) may point at them.
        self._nodes().write({'active': False})
        return super().unlink()

    def action_generate_locations(self):
        self._sync_locations()
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

    def _location_tree(self, vals=None):
        """Wanted nodes, parents first: list of (key, parent_key, name). key = (node, bay, level, position).

        ``vals`` are pending field values, so a write can be checked before it happens.
        """
        self.ensure_one()
        shape = {f: self[f] for f in SHAPE_FIELDS} | {f: v for f, v in (vals or {}).items() if f in SHAPE_FIELDS}
        code, kind = shape['code'], shape['kind']
        row_key = ('row', 0, 0, 0)
        tree = [(row_key, None, code)]
        for b in range(1, shape['bays'] + 1):
            tree.append((('bay', b, 0, 0), row_key, f'{code}-{b:02d}'))
        for b in range(1, shape['bays'] + 1):
            for lvl in range(1, shape['levels'] + 1):
                parent = ('bay', b, 0, 0)
                if kind == 'pallet':
                    parent = ('level', b, lvl, 0)
                    tree.append((parent, ('bay', b, 0, 0), f'{code}-{b:02d}-{lvl}'))
                for p in range(1, shape['slots_per_level'] + 1):
                    name = f'{code}-{b:02d}-{lvl}-{chr(64 + p)}' if kind == 'pallet' else f'{code}-{b:02d}-{lvl}'
                    tree.append((('slot', b, lvl, p), parent, name))
        return tree

    def _nodes(self, include_archived=False):
        domain = [('wh3d_rack_row_id', 'in', self.ids)]
        if not include_archived:
            domain.append(('active', '=', True))
        return self.env['stock.location'].with_context(active_test=False).search(domain)

    def _nodes_by_key(self):
        self.ensure_one()
        return {(loc.wh3d_node, loc.wh3d_bay, loc.wh3d_level, loc.wh3d_position): loc
                for loc in self._nodes(include_archived=True)}

    def _nodes_to_remove(self, vals):
        """Active locations this write would archive."""
        self.ensure_one()
        if vals.get('active') is False:
            return self._nodes()
        wanted = {key for key, _parent, _name in self._location_tree(vals)}
        return self._nodes().filtered(
            lambda loc: (loc.wh3d_node, loc.wh3d_bay, loc.wh3d_level, loc.wh3d_position) not in wanted)

    def _check_no_stock_in(self, locations):
        """Refuse when any of these locations holds, reserves or awaits stock."""
        if not locations:
            return
        busy = self.env['stock.quant'].search([
            ('location_id', 'child_of', locations.ids), '|', ('quantity', '!=', 0), ('reserved_quantity', '!=', 0),
        ]).location_id
        busy |= self.env['stock.move'].search([
            ('state', 'not in', ('done', 'cancel')),
            '|', ('location_id', 'child_of', locations.ids), ('location_dest_id', 'child_of', locations.ids),
        ]).mapped(lambda m: (m.location_id | m.location_dest_id) & locations)
        busy |= self.env['stock.move.line'].search([
            ('state', 'not in', ('done', 'cancel')),
            '|', ('location_id', 'child_of', locations.ids), ('location_dest_id', 'child_of', locations.ids),
        ]).mapped(lambda ml: (ml.location_id | ml.location_dest_id) & locations)
        if busy:
            names = sorted(busy.mapped('name'))
            shown = ', '.join(names[:10]) + (self.env._(" and %s more", len(names) - 10) if len(names) > 10 else '')
            raise UserError(self.env._(
                "Row %(code)s: these locations still hold or expect stock, so they can't be removed: %(names)s. "
                "Move the stock out (or cancel the transfers) first.", code=self.code, names=shown))

    def _sync_locations(self):
        """Make each row's stock.location tree match its fields.

        Creates missing nodes, renames/re-parents/re-activates existing ones, and archives
        nodes that are no longer wanted. Callers must run ``_check_no_stock_in`` first.
        """
        Location = self.env['stock.location'].with_context(active_test=False)
        for row in self:
            if not row.active:
                row._nodes().write({'active': False})
                continue
            by_key = row._nodes_by_key()
            tree = row._location_tree()
            # Parents first (row, bay, level, slot), so every node's parent exists and is active.
            for depth in ('row', 'bay', 'level', 'slot'):
                missing = []
                for key, parent, name in tree:
                    if key[0] != depth:
                        continue
                    vals = {
                        'name': name,
                        'location_id': by_key[parent].id if parent else row.location_id.id,
                        # Only slots get the category, so "closest location" putaway never picks a bay or level.
                        'storage_category_id': row.storage_category_id.id if depth == 'slot' else False,
                    }
                    loc = by_key.get(key)
                    if not loc:
                        missing.append((key, vals))
                        continue
                    current = {'name': loc.name, 'location_id': loc.location_id.id,
                               'storage_category_id': loc.storage_category_id.id}
                    changed = {f: v for f, v in vals.items() if current[f] != v}
                    if not loc.active:
                        changed['active'] = True
                    if changed:
                        loc.write(changed)
                if missing:
                    created = Location.create([vals | {
                        'usage': 'internal',
                        'company_id': row.company_id.id,
                        'wh3d_rack_row_id': row.id,
                        'wh3d_node': key[0], 'wh3d_bay': key[1], 'wh3d_level': key[2], 'wh3d_position': key[3],
                    } for key, vals in missing])
                    by_key.update(zip((key for key, _v in missing), created))
            # Last: re-activating a parent above also re-activates all its children, so archive after.
            wanted = {key for key, _p, _n in tree}
            obsolete = Location.browse([loc.id for key, loc in by_key.items() if key not in wanted and loc.active])
            obsolete.write({'active': False})
