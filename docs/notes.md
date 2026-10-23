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

Files: `models/warehouse_rack_row.py` (`create`, `_location_tree`, `_generate_locations`,
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
`_generate_locations()` then compares that list with what is already in the database (found by the
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
