import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

CODE_RE = re.compile(r'^[A-Z]\d{2}$')
# Fields that decide which locations exist and what they're called.
EPS = 1e-6  # metres; floating-point slack for "touching" comparisons
SHAPE_FIELDS = frozenset({'code', 'kind', 'bays', 'levels', 'slots_per_level'})
# Fields whose change needs the location tree updated.
SYNC_FIELDS = SHAPE_FIELDS | {'location_id', 'storage_category_id', 'active'}
# What the layout editor may change (wh3d_save_layout); anything else is refused.
EDITOR_FIELDS = frozenset({'code', 'kind', 'x', 'y', 'bays', 'bay_width', 'depth', 'levels', 'level_height',
                           'slots_per_level'})


def node_key(loc):
    """Where a generated location sits in its row: (node, bay, level, position)."""
    return (loc.wh3d_node, loc.wh3d_bay, loc.wh3d_level, loc.wh3d_position)


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
        domain="[('usage', '=', 'internal'), ('warehouse_id', '=', warehouse_id)]",  # see _check_location_internal
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

    def _wh3d_footprint(self):
        """Floor rectangle (x0, y0, x1, y1) in metres: depth runs along x, the bays along y."""
        self.ensure_one()
        return self.x, self.y, self.x + self.depth, self.y + self.bays * self.bay_width

    @api.constrains('x', 'y', 'bays', 'bay_width', 'depth', 'warehouse_id', 'active')
    def _check_layout(self):
        if self.env.context.get('wh3d_defer_layout_check'):
            return  # wh3d_save_layout checks the end state once all edits are applied
        self.env['stock.warehouse']._check_wh3d_contains(self)
        for row in self.filtered('active'):
            x0, y0, x1, y1 = row._wh3d_footprint()
            others = self.search([('warehouse_id', '=', row.warehouse_id.id), ('id', '!=', row.id)])
            for other in others:
                ox0, oy0, ox1, oy1 = other._wh3d_footprint()
                # Strict overlap only: rows standing back to back (touching) are fine.
                if x0 < ox1 - EPS and ox0 < x1 - EPS and y0 < oy1 - EPS and oy0 < y1 - EPS:
                    raise ValidationError(self.env._(
                        "Rack rows %(row)s and %(other)s overlap on the floor plan "
                        "(%(row)s: x %(x0)s–%(x1)s m, y %(y0)s–%(y1)s m; %(other)s: x %(ox0)s–%(ox1)s m, y %(oy0)s–%(oy1)s m).",
                        row=row.code, other=other.code,
                        x0=round(x0, 2), x1=round(x1, 2), y0=round(y0, 2), y1=round(y1, 2),
                        ox0=round(ox0, 2), ox1=round(ox1, 2), oy0=round(oy0, 2), oy1=round(oy1, 2)))

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
        if 'warehouse_id' in vals and self.filtered(lambda r: r.warehouse_id.id != vals['warehouse_id'])._nodes():
            # Locations can't change company, and a row's locations belong to its warehouse.
            raise UserError(self.env._(
                "A rack row with locations can't move to another warehouse. "
                "Create a new row in the other warehouse instead."))
        # Check before writing, so a refused change leaves the row and its locations untouched.
        if SHAPE_FIELDS.intersection(vals) or ('active' in vals and not vals['active']):
            for row in self:
                row._check_removal(vals)
        res = super().write(vals)
        if SYNC_FIELDS.intersection(vals):
            self._sync_locations()
        return res

    def unlink(self):
        for row in self:
            row._check_removal({'active': False})
        # Locations are archived, never deleted: Inventory history (moves, counts) may point at them.
        self._nodes().write({'active': False})
        return super().unlink()

    @api.model
    def wh3d_save_layout(self, warehouse_id, changes):
        """Apply the layout editor's edits in one go: all of them, or none.

        ``changes`` = {'create': [{'tmp_id', 'vals'}], 'write': [{'id', 'vals'}], 'delete': [ids]}.
        Only EDITOR_FIELDS may be set, and only rows of this warehouse touched. Overlaps and the
        building bounds are checked on the final layout, so moves like swapping two rows work.
        Returns {'created': {tmp_id: new id}, 'layout': the saved floor plan}.
        """
        warehouse = self.env['stock.warehouse'].browse(warehouse_id).exists()
        if not warehouse:
            raise UserError(self.env._("This warehouse no longer exists."))

        def clean(vals):
            refused = set(vals) - EDITOR_FIELDS
            if refused:
                raise UserError(self.env._(
                    "The layout editor can't change these fields: %s", ", ".join(sorted(refused))))
            return dict(vals)

        def own(ids):
            rows = self.browse(ids).exists()
            if len(rows) != len(set(ids)) or rows.filtered(lambda r: r.warehouse_id != warehouse):
                raise UserError(self.env._("Some rack rows were deleted meanwhile or belong to another warehouse."))
            return rows

        deferred = {'wh3d_defer_layout_check': True}
        created = {}
        # A savepoint makes the whole save atomic even for Python callers that catch the error.
        with self.env.cr.savepoint():
            own(changes.get('delete', [])).unlink()
            touched = self.browse()
            for change in changes.get('write', []):
                row = own([change['id']])
                row.with_context(**deferred).write(clean(change['vals']))
                touched |= row
            for change in changes.get('create', []):
                vals = clean(change['vals'])
                vals.update(warehouse_id=warehouse.id,
                            location_id=self._wh3d_default_zone(warehouse, vals.get('kind', 'pallet')).id)
                row = self.with_context(**deferred).create(vals)
                created[change['tmp_id']] = row.id
                touched |= row
            self.browse(touched.ids)._check_layout()
        return {'created': created, 'layout': warehouse.wh3d_get_layout()}

    @api.model
    def _wh3d_default_zone(self, warehouse, kind):
        """Zone for a row added in the editor: where rows of the same kind already live, else WH/Stock."""
        sibling = self.search([('warehouse_id', '=', warehouse.id), ('kind', '=', kind)], limit=1)
        return sibling.location_id or warehouse.lot_stock_id

    def action_generate_locations(self):
        # The tree may have drifted (imports, scripts), so extras get the same stock check as an edit.
        for row in self:
            row._check_removal({})
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
        return {node_key(loc): loc for loc in self._nodes(include_archived=True)}

    def _locations_to_archive(self, vals):
        """Active locations that writing ``vals`` would archive, including hand-made ones below them.

        Generated nodes the new tree still wants survive (they're renamed or re-parented first),
        and so does everything below them.
        """
        self.ensure_one()
        Location = self.env['stock.location']
        archiving_row = 'active' in vals and not vals['active']
        wanted = set() if archiving_row else {key for key, _parent, _name in self._location_tree(vals)}
        nodes = self._nodes()
        removed = nodes.filtered(lambda loc: node_key(loc) not in wanted)
        if not removed:
            return Location
        below_removed = Location.search([('id', 'child_of', removed.ids)])
        surviving = below_removed & (nodes - removed)
        return below_removed - Location.search([('id', 'child_of', surviving.ids)])

    def _check_removal(self, vals):
        """Refuse ``vals`` if a location it would archive holds, reserves or awaits stock."""
        self.ensure_one()
        locations = self._locations_to_archive(vals)
        if not locations:
            return
        ids = locations.ids
        busy = self.env['stock.quant'].search([
            ('location_id', 'in', ids), '|', ('quantity', '!=', 0), ('reserved_quantity', '!=', 0),
        ]).location_id
        for model in ('stock.move', 'stock.move.line'):
            busy |= self.env[model].search([
                ('state', 'not in', ('done', 'cancel')), '|', ('location_id', 'in', ids), ('location_dest_id', 'in', ids),
            ]).mapped(lambda m: (m.location_id | m.location_dest_id) & locations)
        if busy:
            names = sorted(busy.mapped('name'))
            shown = ', '.join(names[:10]) + (self.env._(" and %s more", len(names) - 10) if len(names) > 10 else '')
            raise UserError(self.env._(
                "Row %(code)s: these locations still hold or expect stock, so they can't be removed: %(names)s. "
                "Move the stock out (or cancel the transfers) first.", code=self.code, names=shown))

    def _sync_locations(self):
        """Make each row's stock.location tree match its fields.

        Creates missing nodes, renames/re-parents/re-activates existing ones, and archives
        nodes that are no longer wanted. Callers must run ``_check_removal`` first.
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
                        loc.with_context(wh3d_sync=True).write(changed)
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
