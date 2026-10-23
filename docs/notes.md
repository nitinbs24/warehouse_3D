# Learning notes: Odoo patterns, task by task

Each section explains the Odoo ideas a task introduced, the first time they appear.
Read alongside the code of that task's commit (`git log --oneline` in `warehouse_3D/`).

## T0: Environment and an empty module

**Two Odoo versions side by side.** Odoo reads one config file per server process (`-c`).
`odoo.conf` stays the Odoo 18 file; `odoo19.conf` is the Odoo 19 one. They share the PostgreSQL
role `odoo18` but use different databases (`warehaven` for development, `wh3d_test` for tests), so
nothing collides. The dev server is `venv19/bin/python odoo19/odoo-bin -c odoo19.conf`.

**`addons_path`** is the list of folders Odoo scans for modules. Any sub-folder with a
`__manifest__.py` is a module. We added `/mnt/CODE/Workspace/odoo/warehouse_3D`, so
`warehouse_3D/warehouse_3d/` is found; `docs/` is ignored because it has no manifest.

**A module is a Python package plus a manifest.**
- `__manifest__.py` is a plain dict: name, version (`19.0.x.y.z` = Odoo series + module version),
  `depends` (modules that must be installed first — for us only `stock`, which pulls in
  `product`, `web`, etc.), `data` (XML/CSV files loaded on install, in order), `demo` (loaded only
  on databases created with `--with-demo`), and `assets` (JS/CSS/XML added to front-end bundles).
- `__init__.py` imports the Python sub-packages (`models`, later). Empty for now.
- `tests/` is imported by Odoo's test runner only, never in production.

**Asset bundles.** Odoo doesn't serve JS files one by one; it concatenates them into named bundles.
`web.assets_backend` is the main back-office bundle, `web.assets_tests` is only loaded when a test
tour runs. Our tour file goes into `web.assets_tests` so it never ships to real users.

**Two kinds of tests.**
- `TransactionCase`: Python, runs inside a database transaction that is rolled back after each
  test, so tests can't pollute each other. Used for models and business logic. Very fast.
- `HttpCase` + **tour**: starts headless Chrome, logs in, and replays steps written in JS
  (`static/tests/tours/*.js`): "wait for this CSS selector, then click it". Used to prove the UI
  works. Needs the `websocket-client` Python package (Chrome is driven over a websocket). Without
  it Odoo *skips* the test without failing, which is why `run_tests.sh` treats a skip as a failure.
- `@tagged('post_install', '-at_install')` makes a test run after all modules are installed
  instead of right after ours; tours need the full menu and assets, so they always use it.

**Running tests:** `warehouse_3D/run_tests.sh` drops `wh3d_test`, installs the module with demo
data, runs every test tagged `/warehouse_3d`, and exits non-zero on any error, failure or skipped
browser test. Pass a tag to run one class: `./run_tests.sh /warehouse_3d:TestSmoke`. It uses port
8079, so it works while the dev server runs on 8069.

## T1: The rack-row model, its rules, views and menu

Files: `models/warehouse_rack_row.py`, `models/stock_location.py`, `security/ir.model.access.csv`,
`data/res_groups.xml`, `views/*.xml`, `tests/test_rack_row.py`.

**A model is a Python class = a database table.** `_name = 'warehouse.rack.row'` creates the table
`warehouse_rack_row`; each `fields.X(...)` is a column. Think of it like a C `struct` that the ORM
(Object-Relational Mapper) saves for you: `self.env['warehouse.rack.row'].create({...})` inserts a row,
`record.bays = 8` updates it. `self` is always a *recordset* (zero or more records), which is why
methods loop `for row in self`.
- `Many2one('stock.warehouse')` is a foreign key (a pointer to another record). `ondelete='restrict'`
  on `location_id` means you can't delete a zone location while rows still point at it.
- `related='warehouse_id.company_id', store=True` copies a value through a pointer and keeps it in sync.
- `_rec_name = 'code'` makes the record display as "P05" everywhere (dropdowns, breadcrumbs).
- `default=lambda self: ...` is computed at creation time — here: the company's first warehouse.

**`_inherit` = adding to someone else's model.** `models/stock_location.py` has
`_inherit = 'stock.location'` and no `_name`. That doesn't create a new table; it adds our five
`wh3d_*` columns to Inventory's existing location table. Every Inventory feature keeps working on
the same records. Prefix your fields (`wh3d_`) so they never clash with Odoo's or other modules'.
`wh3d_node` says what a generated location is (row / bay / level / slot); T2 fills these in.
Location types: in code `usage='view'` is a grouping location that holds no stock itself; the UI
labels it **Virtual** in Odoo 19. `usage='internal'` (UI: Internal) is a real storage place.
Catch: a `view` location's full name is just its own name — the path restarts there
(`stock_location.py:127`). So zones like `PR` and every generated rack node are `internal`.

**Two kinds of validation.**
- `models.Constraint('CHECK(...)' or 'UNIQUE(...)', message)` becomes a real PostgreSQL constraint.
  The database itself refuses bad rows, even from SQL scripts. Use for simple per-row rules.
  (This is the Odoo 19 syntax; older tutorials show `_sql_constraints = [...]`.)
- `@api.constrains('field', ...)` is a Python check run after create/write when one of those fields
  changes; raise `ValidationError` to refuse. Use when the rule needs code: the code regex, "shelf ⇒
  one slot per level", and "zone location must be inside WH/Stock" (a `child_of` search, which uses
  the location tree).
- In tests, a SQL constraint shows up as `psycopg2.IntegrityError`, a Python one as `ValidationError`.
  `self.cr.savepoint()` lets a test trigger several database errors in a row without breaking the
  transaction.

**Access rights.** `security/ir.model.access.csv` — one line per (model, group): read/write/create/
delete. Inventory **users** may read rack rows (they will use the 3D view); only Inventory
**managers** may change the layout. A new model with no access line is invisible to everyone but
the superuser, and Odoo logs a warning.

**Views are XML records.** `views/warehouse_rack_row_views.xml` defines `ir.ui.view` records: a
`<list>` (table), a `<form>` (one record) and a `<search>` (filters, group-by). An
`ir.actions.act_window` says "open this model with these views"; a `<menuitem>` points at the action.
Our menu is *Inventory ▸ Configuration ▸ Warehouse 3D ▸ Rack Rows*, visible to managers.
- Attributes like `invisible="active"` and `readonly="kind == 'shelf'"` are small Python-like
  expressions evaluated in the browser per record.
- `groups="stock.group_stock_multi_warehouses"` hides the warehouse field unless you run several.

**Turning on an Inventory setting from a module.** Generated sub-locations are hidden in Inventory
unless *Settings ▸ Storage Locations* is on. That setting is backed by the group
`stock.group_stock_multi_locations`, but saving it does **more** than add the group:
`stock/models/res_config_settings.py` (`set_values`) also archives two views that hide the **New**
button on Locations, and activates the internal-transfer operation type.
- First attempt (bug, found by Nitin in the UI): linking the group directly with
  `(4, ref(...))` on `base.group_user.implied_ids`. Group on, but no "New" button.
- Fix: `data/res_groups.xml` uses a `<function>` tag to call `res.config.settings.execute()` on a
  settings record with the box ticked — the same code path as clicking Save in Settings.
  `<function>` runs a model method while data files load.
- Lesson: when Odoo has a settings checkbox, go through `res.config.settings`, not its group.
  The regression test `test_storage_locations_setting_enabled_like_settings_page` guards it.

**Order in the manifest matters.** `data` files load top to bottom: access rules, then the group
change, then views (which define the action), then menus (which reference the action).

## T2: Generating the location tree from a rack row

Files: `models/warehouse_rack_row.py` (`create`, `_location_tree`, `_sync_locations` (called `_generate_locations` until T3),
`action_generate_locations`, `action_view_slots`), `views/warehouse_rack_row_views.xml`,
`tests/test_location_generator.py`.

**Overriding `create`.** `@api.model_create_multi def create(self, vals_list)` replaces the standard
"insert records" method. We call `super().create(vals_list)` first — that runs Odoo's own create
(validation, saving) — then generate locations for the new rows. This "call `super()`, then add your
part" shape is how you extend *any* Odoo method, ours or Inventory's. `vals_list` is a list because
Odoo creates records in batches.

**The tree, described before it is built.** `_location_tree()` only *lists* what should exist, as
`(key, parent_key, name)`, with key = `(node, bay, level, position)`:
```
pallet: P05 ─ P05-03 ─ P05-03-2 ─ P05-03-2-A      (row ─ bay ─ level ─ slot, 1+7+35+70 = 113 locations)
shelf:  S04 ─ S04-10 ─ S04-10-3                   (row ─ bay ─ slot, no level node, 1+16+80 = 97)
```
`_sync_locations()` then compares that list with what is already in the database (found by the
`wh3d_*` fields, not by name) and creates only what's missing. That's why running it twice creates
nothing, and why the "Regenerate Locations" button can repair a deleted slot. T3 will use the same
keys to rename and archive.

**Batching for speed.** Creating 113 records one by one means 113 round trips plus recomputing each
parent's stored fields every time. Instead we call `create([...])` once per depth (row, then all
bays, then all levels, then all slots), so every parent exists before its children. 14 pallet rows =
1,442 locations in about 4.6 s.

**Why only slots get the storage category.** Odoo's *Closest Location* putaway
(`stock/models/product_strategy.py`, `_get_putaway_location`) only considers child locations whose
storage category equals the rule's. Bays and levels have none, so stock can never be put "on a bay".
`test_closest_putaway_lands_in_a_slot` proves this with a real putaway rule. (The option's internal
value is `closest_location`; I first wrote `closest` in the test and Odoo rejected it — a useful
reminder that selection fields store a key, and the UI shows its label.)

**Smart button.** The "Slots" counter at the top right of the form is an `oe_stat_button` showing
a computed field (`slot_count`, counted with one `_read_group` query for all rows at once). Clicking
it calls `action_view_slots`, which returns an *action dictionary* — a Python way to say "open this
model, with this filter". Methods called from buttons can return such a dict to navigate.

**`company_id` and `active_test`.** Generated locations get the row's company. The search uses
`with_context(active_test=False)` so archived locations are found too; otherwise a re-generate would
create a duplicate of a slot that was merely archived.

## T3: Editing, archiving and deleting rows without losing stock

Files: `models/warehouse_rack_row.py` (`write`, `unlink`, `_locations_to_archive` and `_check_removal`
(named `_nodes_to_remove` / `_check_no_stock_in` until T3c), `_sync_locations`), `tests/test_location_sync.py`.

**What happens when you change a row**

| You change | Locations |
|---|---|
| x, y, bay width, depth, level height | nothing (they only affect the drawing) |
| code (P05 → P15) | every node renamed in place; same records, so stock and history stay attached |
| bays / levels / slots per level up | new nodes created, or archived ones reactivated |
| bays / levels / slots per level down | removed nodes archived — **refused** if any holds stock |
| kind pallet ↔ shelf | tree reshaped (slots move under the bay, level nodes archived) |
| zone location | the row's subtree moves under the new zone |
| storage category | copied to every slot |
| archive the row / delete the row | all its locations archived — **refused** if any holds stock |

**Overriding `write`.** Same pattern as `create` in T2: do our part, call `super().write(vals)`.
`vals` only contains the fields being changed, so `SHAPE_FIELDS.intersection(vals)` asks "does this
edit change which locations exist?" Edits to x/y skip the sync entirely.

**Check first, then change.** If we wrote first and raised an error afterwards, the test (and any
code that catches the error) could be left with half-applied changes. So `write` first works out
which locations *would* disappear — `_location_tree(vals)` builds the tree from the pending values —
and `_check_removal` refuses if any of them holds stock, has reserved stock, or is the source or
destination of an open transfer. Only then does it write. Odoo's own archive check
(`stock.location.write`) also refuses archiving stocked locations; ours runs earlier and names every
blocked location in one message.

**Archive, never delete.** Odoo convention: records that history points to (stock moves, inventory
counts) are archived (`active = False`), not deleted. Archived records disappear from lists and
dropdowns but keep their history; the "Archived" filter shows them. Growing a row back reactivates
the *same* records, so nothing is duplicated.

**Order matters when archiving.** In Odoo 19, archiving or unarchiving a location does the same to all
its children (`stock.location.write`). So `_sync_locations` first creates/renames/reactivates (parents
before children), and archives obsolete nodes last — otherwise reactivating a bay would wake up the
slots we just archived.

**Delete = archive, then delete the row.** `unlink` is the ORM's delete. We check stock, archive the
row's locations, then let `super().unlink()` delete the rack-row record itself. The locations keep
existing (archived), with `wh3d_rack_row_id` cleared because of `ondelete='set null'`.

**A name can repeat.** Pallet → shelf renames slot `P05-03-2-A` to `P05-03-2`, the same name as the now
archived level node. Odoo allows duplicate location names; only the active one shows anywhere.

## T3b: Locking generated locations

Files: `models/stock_location.py` (`write`), `views/stock_location_views.xml`,
`models/warehouse_rack_row.py` (one `with_context`), `tests/test_location_lock.py`.

**Why.** During the T3 manual check, slot `P15-01-1-A` got its *Parent Location* changed by hand and
ended up inside slot `P15-07-1-A`. Nothing stopped it; the tree silently stopped matching the row.
Now the three fields the rack row owns — **name, parent, type** — can only change through the row.
Everything else on a location (barcode, removal strategy, cycle counting…) stays editable.

**Two layers, on purpose.**
- *View* (`views/stock_location_views.xml`): an **inherited view** adds a blue "Managed by rack row
  P15" banner and `readonly="wh3d_rack_row_id"` on the three fields. `inherit_id` + `xpath` /
  `<field position="attributes">` is how you change someone else's screen without copying it: Odoo
  merges our small patch into Inventory's form at load time.
- *Model* (`stock.location.write` override): refuses the change with a `UserError` if it would
  actually change one of the three. A read-only field in one form doesn't stop other screens (the
  Locations list allows multi-edit), imports, or scripts — the server check does.
  Rule of thumb: **views are for convenience, model checks are for safety.**

**Context flags.** `_sync_locations` must still be allowed to rename and move nodes. It writes with
`loc.with_context(wh3d_sync=True)`; the `write` override skips the check when it sees that flag.
`with_context(...)` returns the same records carrying extra key/values that every method called on
them can read via `self.env.context`. (We already used `active_test=False` the same way in T2.)

**Testing a view in Python.** `odoo.tests.Form` simulates the form in Python, applying the view's
`readonly` / `invisible` rules. Setting a read-only field raises an `AssertionError`, which is how
`test_form_shows_locked_fields_read_only` checks the screen without a browser.

## T3c: Fixes from the code review

A `/code-review` of T1–T3b found nine issues; six were fixed, each with a test that failed first
(`tests/test_location_sync.py` and `tests/test_location_lock.py`, marked "Review #n").

| # | Problem | Fix |
|---|---|---|
| 1 | Pallet → shelf was refused when the surviving slot A held stock: the check saw it below the removed level node. | `_locations_to_archive` works out exactly what disappears: removed nodes and everything below them, **minus** nodes that survive and everything below those. |
| 2 | An open transfer into a hand-made bin below a removed slot (e.g. `P05-07-1-A/Left`) was missed. | Same function: hand-made locations below a removed node are included, and quants, moves and move lines are all checked against that one exact set. |
| 3 | Duplicating a generated location copied its rack-row key, confusing the sync and locking both copies. | `copy=False` on the `wh3d_*` fields: a copy is a plain location. |
| 4 | `write({'active': 0})` skipped the check (code tested `is False`). | Test "is `active` in vals and falsy". |
| 5 | *Regenerate Locations* could archive stray nodes without the check. | `action_generate_locations` runs `_check_removal` first. |
| 6 | Moving a row to another company's warehouse would leave its locations in the old company. | Changing a row's warehouse once it has locations is refused; create a new row instead. |
| 9 | The node key tuple was spelled out in two places. | One `node_key(loc)` helper. |

Not fixed, on purpose: **#7** the `wh3d_sync` context flag can be set by an API caller to bypass the
lock — the lock guards against mistakes, not attackers, and anyone who can write locations can
already change the rack row. **#8** a row rename writes its 113 locations one by one; fine at this
size, revisit in T14 if the template install is slow.

**Lesson (Odoo):** `field.copy=False` decides what `record.copy()` (the *Duplicate* menu) carries
over. Any field that identifies "this exact record" — keys, links that must be unique — should be
`copy=False`. **Lesson (general):** a safety check must test exactly the set of things that will be
lost; checking a superset blocks valid edits (#1), checking a subset lets data slip (#2).
