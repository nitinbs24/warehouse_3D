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

## T4: Three.js inside an OWL client action (the spike)

Files: `static/lib/three/` (vendored), `static/src/view3d/view3d_action.{js,xml,scss}`,
`views/view3d_actions.xml`, `views/menus.xml`, `__manifest__.py`, `tests/test_view3d.py`,
`static/tests/tours/view3d_tour.js`.

**Client action = "Odoo, show my own screen here".** Odoo's normal screens (list, form) are
*window actions* that display a model with a view. When you need a screen Odoo doesn't have —
a 3D canvas — you register a **client action**: an `ir.actions.client` record whose `tag`
(`warehouse_3d.view3d`) names a JavaScript component. The menu points at the action; the web
client looks the tag up in `registry.category("actions")` and mounts our component.

**OWL in five lines.** OWL is Odoo's front-end framework (like React or Vue). A component is a JS
class plus an XML template:
- `static template = "warehouse_3d.View3D"` — the XML in `view3d_action.xml` (QWeb syntax:
  `t-if`, `t-esc`, `t-ref`).
- `useState({...})` — reactive data: change `this.state.error` and the template re-renders.
- `useRef("canvas")` — a handle on the DOM element marked `t-ref="canvas"`.
- **Lifecycle hooks**, the part that matters for Three.js:
  - `onWillStart` — runs *before* the first render and may be `async`; Odoo waits for it. We load
    Three.js here, so it's ready when the component appears.
  - `onMounted` — the component's HTML is now in the page; we can measure it and attach the canvas.
  - `onWillUnmount` — the user is leaving; free everything we created.

**Lazy loading.** `loadJS(url)` adds a `<script>` tag once and remembers it, so opening the view a
second time doesn't download again. Three.js (600 KB) is *not* listed in the manifest's
`web.assets_backend`, so it isn't sent to every Odoo page — only when someone opens the 3D view.
`test_three_js_is_not_in_the_backend_bundle` guards that. Our own small component *is* in
`web.assets_backend` (it must be registered before anyone clicks the menu).

**Why r128 and a global `THREE`.** Odoo bundles its JS as `@module/path` ES modules. Recent
Three.js versions are ES modules too and import each other in ways Odoo's bundler doesn't follow.
r128 still ships a classic "UMD" build that just sets `window.THREE`, plus
`examples/js/controls/OrbitControls.js`, which adds `THREE.OrbitControls` to it — so they must load
in that order. The prototype already used this exact version.

**Vendoring safely.** The files came from the official npm package `three@0.128.0`, checked against
the SHA-512 checksum the npm registry publishes, and the MIT `LICENSE` sits next to them.

**Cleaning up (why `stop()` is long).** WebGL memory isn't freed by JavaScript's garbage collector
the way normal objects are, and browsers allow only about 16 live WebGL contexts per page. Odoo
keeps the page open for hours while you move between screens, so a 3D view that leaks would break
after a dozen visits. On leave we stop the render loop, disconnect the resize observer, dispose
controls, every geometry and material, the renderer, force-release the WebGL context, and remove
the canvas. The tour opens the view, leaves, checks the canvas is gone, and opens it again.

**No WebGL?** `new THREE.WebGLRenderer()` throws; we catch it and show the prototype's message.

**Headless Chrome can do WebGL.** Odoo starts its test browser with `--enable-unsafe-swiftshader`, a
software GPU, so the tour checks for a real WebGL context, not just a `<canvas>` tag.

## T5: Building size and layout areas

Files: `models/stock_warehouse.py`, `models/warehouse_layout_area.py`,
`views/warehouse_layout_area_views.xml`, `views/menus.xml`, `security/ir.model.access.csv`,
`tests/test_layout_area.py`.

**Why.** The prototype had the building size, zones and docks hard-coded in JavaScript. Now they are
data: three fields on the warehouse (length along X, width along Y, clear height; defaults 60/40/10)
and a small model `warehouse.layout.area` for floor areas (Receiving, Packing…) and dock doors.
The 3D view (T6–T7) and the editor (T11) will read them instead of hard-coding.

**One check, two callers.** "Is this rectangle inside the building?" is needed when an *area* moves
and when the *building* shrinks. Both call `stock.warehouse._check_wh3d_contains(records)`; T10 will
reuse it for rack rows. `@api.model` marks a method that doesn't care which records `self` holds.

**`One2many` (`wh3d_area_ids`)** is the reverse side of the area's `warehouse_id` pointer — no column
of its own, just "all areas whose `warehouse_id` is me". It lets the warehouse check its areas.

**New fields on existing records.** When `-u` adds a column to a table that already has rows, Odoo
fills it with the field's `default` (`odoo/orm/fields.py`, `update_db_column`), so your existing
warehouse got 60 × 40 × 10 automatically.

**Editable list.** `<list editable="bottom">` lets you type areas straight into the list, like a
spreadsheet — no form needed for six simple fields.

**Where the fields appear.** The warehouse form's tabs are only visible with multi-step routes or
several warehouses, so the "3D Layout" group is inserted *before* the tabs (`xpath ... position="before"`).

## T6: One call that gives the 3D view everything

Files: `models/stock_warehouse.py` (`wh3d_get_scene`, `wh3d_get_slots`, `_wh3d_slot_data`),
`models/product_template.py`, `views/product_template_views.xml`, `tests/test_scene_data.py`.

**RPC = the browser calling a Python method.** Any public method (name not starting with `_`) on a
model can be called from JavaScript: `orm.call("stock.warehouse", "wh3d_get_scene", [[warehouse_id]])`.
Odoo checks access rights as usual — an Inventory user may read warehouses, rows and stock, so they
can load the scene. Methods starting with `_` can't be called from outside: that's how `_wh3d_slot_data`
stays private.

**What comes back**
```
{ building: {length, width, height},
  areas:    [{id, name, kind, x, y, width, depth}],
  rows:     [{id, code, kind, x, y, bays, bay_width, depth, levels, level_height, slots_per_level}],
  slots:    [{location_id, code, row_id, bay, level, position, capacity_m3,
              stock: null | {product_id, name, default_code, qty, uom, mixed, used_m3, fill}}] }
```
- `capacity_m3` = slot width (bay width ÷ slots per level) × depth × level height. P05: 2.673 m³.
- `used_m3` = Σ product L×W×H × quantity over the slot's stock; `fill` = used ÷ capacity.
- A product with no dimensions makes `used_m3`/`fill` `null` → T8 draws it striped grey ("no dimensions").
- Mixed slots name the product with the largest quantity and set `mixed: true`.
- `wh3d_get_slots(ids)` returns the same slot shape for a few slots; T9 calls it on live updates.

**The N+1 query trap.** The naive way — loop over 2,340 slots and ask the database for each slot's
stock — is 2,340+ queries ("N+1"). Instead:
- `_read_group` gets the stock of *all* slots in one grouped query
  (`GROUP BY location_id, product_id` with `SUM(quantity)`).
- `read([...], load=None)` reads all rows/areas in one go; `load=None` returns plain ids instead of
  `(id, name)` pairs.
- The ORM's **prefetching**: when you touch `slot.wh3d_rack_row_id` for one slot in a recordset, Odoo
  loads that field for the whole recordset at once. So loops over records are fine; loops that call
  `search` are not.
`test_query_count_does_not_grow_with_slots` proves it: 1 row or 3 rows, the same number of queries.

**Product dimensions.** Odoo products only have weight and volume, so `product.template` gets L×W×H in
metres (shown under Volume on the product's Inventory tab). Fields defined on `product.template` are
visible on `product.product` too: Odoo links the two with `_inherits` (delegation inheritance —
each variant "has a" template and borrows its fields).

## T7: Real racks in 3D, drawn from your records

Files: `static/src/view3d/layout.js` (pure geometry), `static/src/view3d/scene.js` (Three.js),
`static/src/view3d/view3d_action.{js,xml,scss}`, `static/tests/layout.test.js`, `tests/test_js.py`,
`tests/test_view3d.py`, `static/tests/tours/view3d_tour.js`, `docs/screenshots/t7-*.png`.

**Three layers, each testable on its own.**
```
view3d_action.js   OWL component: loads Three.js + calls wh3d_get_scene, toolbar state
      │
scene.js           WarehouseScene: turns boxes into Three.js meshes, camera, labels, cleanup
      │
layout.js          plain maths: rack row record → list of boxes [x, y, z, sizeX, sizeY, sizeZ]
```
`layout.js` has no Three.js and no DOM, so its unit tests run in milliseconds and pin every number
to the prototype (e.g. P05 has 16 uprights and 8 beams; slot P05-03-2-A's box centre is
(-19.75, 2.66, -12.925)). If someone changes a formula, those tests say exactly which number moved.

**Hoot = Odoo's JavaScript test runner.** Test files end in `.test.js`, are listed in the manifest
under `web.assets_unit_tests`, and use `describe` / `test` / `expect(...).toBe(...)` like Jest. They
run in the browser at `/web/tests`. `tests/test_js.py` starts that page headless, filtered to the
`@warehouse_3d` suite, so `run_tests.sh` runs Python, Hoot and tours in one go. (Checked: a wrong
expected number makes the whole run fail.)

**Coordinates.** Floor plan = metres from a building corner (x along the length, y along the width),
like the rack-row fields. Three.js wants the building centred on (0, 0) with "up" as y, so
`toWorld()` shifts by half the building and plan-y becomes world-z.

**Speed: instancing.** The 31 rows have ~1,000 uprights. Drawing each as its own mesh is ~1,000
draw calls per frame; an `InstancedMesh` draws all identical boxes in **one** call, each with its
own position/size matrix. The whole warehouse is about a dozen draw calls.

**Labels** are text painted on a small `<canvas>` and used as a texture on a `Sprite` (a flat image
that always faces the camera). Area labels ignore depth so they show through racks; row codes don't.

**Lighting.** The prototype's lights (0.8 + 0.65) add up to more than 100 % on upward-facing
surfaces, which is why its floor looks white. Here they're 0.55 + 0.5, so floor and areas keep their
greys — compare `docs/screenshots/t7-prototype.png` and `t7-odoo-3d-view.png`.

**Screenshots on demand.** `./run_tests.sh wh3d_screenshot` builds the handoff's 31 rows, 5 areas
and 6 docks in a test database, opens the 3D view and saves a PNG under
`/tmp/odoo_tests/wh3d_test/screenshots/`. It's tagged `-standard`, so normal runs skip it.

## T8: Stock, clicking a slot, Find, capacity

Files: `static/src/view3d/occupancy.js` (pure), `layout.js` (`openSide`, `aisleClearance`),
`scene.js` (stock boxes, picking, selection, focus), `view3d_action.{js,xml,scss}` (side panel),
`models/stock_warehouse.py` (`path` in slot data), `static/tests/occupancy.test.js`,
`static/tests/layout.test.js`, `static/tests/tours/view3d_tour.js`, `tests/test_view3d.py`.

**Load boxes (decision 6b of the plan).** One box per stocked slot, never one per carton. Its
footprint is the slot's floor, its height = stored volume ÷ that floor area, capped at the slot's
clear height — a half-full slot looks half-height. If any product in the slot has no dimensions the
volume is unknown: the box is drawn half-height, striped when colours are on, and the panel says so.

**Colours.** Grey by default. *Colour by occupancy*: green under 50 %, amber 50–90 %, red over 90 %
(fill above 100 % — more volume than the slot holds — is still red; the box stops at the slot top).
Implementation: one `InstancedMesh` with a white material and a colour **per instance**
(`setColorAt`), so switching colours rewrites a colour list, not the geometry.

**Picking = ray casting.** A click becomes a ray from the camera through the mouse point
(`THREE.Raycaster`); we test it against invisible boxes, one per slot, and the first box hit is the
slot. `instanceId` of the hit is the slot's index in the scene data. A press-and-release that moved
more than 6 px is an orbit drag, not a click.

**A bug the tour caught.** The prototype's Find flew the camera to the front-left of a slot. The tour
then clicked the middle of the screen and expected that same slot — and got its neighbour, which
stands in front of it from that angle. The camera now stands **in the aisle facing the rack**:
- `openSide(row, rows)` — back-to-back rows have a 0.2 m gap, so look from the side without a partner.
- `aisleClearance(...)` — how much floor is free in front of that face (to the next row or wall); the
  camera stays inside it, or the rack across the aisle would block the view (seen in a screenshot of
  the full template). OrbitControls' minimum distance went from 4 m to 1 m so it can stand in a
  1.2 m picker aisle.

**The side panel is plain OWL.** State lives in `useState`; the template reads it
(`t-if`, `t-esc`, `t-att-…`) and re-renders when it changes. `selectedInfo` is a JavaScript *getter*
— a computed property recalculated on each render. "Open in Inventory" calls the `action` service
with an `ir.actions.act_window` dictionary: the same kind of action a menu item opens, built in JS.

**Capacity and legend** are computed in the browser from the scene data (`capacitySummary`,
`legendCounts`), so they need no extra server call. Average fill counts only slots whose fill is
known.

## T9: Live updates over the bus

Files: `models/stock_quant.py`, `static/src/view3d/view3d_action.{js,xml}`, `__manifest__.py`
(`bus` added to `depends`), `tests/test_bus.py`, `static/tests/tours/view3d_tour.js`
(`warehouse_3d_live`), `tests/test_view3d.py`.

**The bus is Odoo's push channel.** Every open Odoo tab keeps one websocket to the server. Python code
calls `bus.bus._sendone(target, type, payload)`; every browser subscribed to `target` receives it.
Browsers are automatically subscribed to their user's partner and to **every group the user is in**,
so sending to the `stock.group_stock_user` group record reaches every Inventory user — no custom
channel or `ir.websocket` override needed. The client listens with
`bus_service.subscribe("warehouse_3d/stock", callback)`.

**Where the change is detected.** All stock in Odoo lives in `stock.quant` (one row per product per
location). Receipts, deliveries, transfers and inventory adjustments all end up creating, writing
or deleting quants, so overriding those three methods catches every stock change. A quant that
moves reports both its old and new location.

**One message per transaction, not per line.** Validating a 50-line receipt writes quants 50+
times. Instead of sending each time, `_wh3d_notify` collects location ids in
`cr.precommit.data` and registers one *pre-commit hook* — a function Odoo runs once, just before the
transaction commits. The hook keeps only rack slots and sends a single message. If the transaction
fails and rolls back, the hook never runs, so the 3D view never shows stock that didn't happen.

**In the browser.** `onStockChanged` ignores slots from other warehouses, waits 150 ms to batch bursts,
then calls `wh3d_get_slots(ids)` for just those slots, swaps them into the scene data, rebuilds the
stock boxes, recomputes capacity/legend, and re-renders the panel (the selected slot updates in
place). Subscribing happens in `onMounted`, unsubscribing in `onWillUnmount` — a listener left
behind would keep firing into a closed view.

**Running it for real.** With Odoo's default single-process server (what you run), the websocket is
served on the same port. If you later run with `--workers`, the websocket needs Odoo's separate
gevent port (8072) behind a proxy; that's standard Odoo deployment, not specific to this module.

## T9b: Fixes from the second code review (live updates)

Files: `static/src/view3d/live.js` (new), `view3d_action.js`, `occupancy.js` (`mergeSlotUpdates`),
`models/stock_quant.py`, `tests/common.py` (new), `tests/test_bus.py`, `tests/test_view3d.py`,
`static/tests/live.test.js` (new), `static/tests/occupancy.test.js`, `static/tests/tours/view3d_tour.js`.

The T9 browser code had a naive "wait 150 ms after the last message, then refetch". The review found
five ways it could show stale stock; they're all handled by one small class, `UpdateQueue`:

| Review # | Problem | Now |
|---|---|---|
| 1 | Two overlapping refetches could finish in the wrong order (old data last). | **One fetch at a time**; messages arriving meanwhile wait for the next one. |
| 2 | Listening started only after the scene loaded; changes in between were lost. | Subscribe in `setup()`, **before** loading; ids are collected and applied once the scene is ready. |
| 3 | A failed refetch dropped its slots and raised an unhandled error. | Ids go back in the queue; **retry after 5 s**. |
| 7 | A steady stream (message every 100 ms) kept restarting the 150 ms wait: no refresh, ever. | **Throttle**, not debounce: an armed timer isn't restarted, so at most one refresh per 150 ms. |
| 4 | A slot archived meanwhile kept its old box (the server no longer returns it). | `mergeSlotUpdates`: asked for but not returned → shown empty. |

Also: **#5** reservations no longer trigger messages (the view doesn't show them); **#8** tour count
checks use `:text(1)` (exact) instead of `:contains(1)` (which also matches "10" or "1 %");
**#9** the bus test now uses the real *Physical Inventory ▸ Apply* path
(`inventory_mode` + `action_apply_inventory`); **#10** one shared `create_p05()` helper in
`tests/common.py` instead of six copies.

**Debounce vs throttle** (general idea, worth knowing): *debounce* = "act once things go quiet"
(good for search-as-you-type), *throttle* = "act at most every N ms" (good for streams that never go
quiet). The test `a steady stream still refreshes every delay` fails if `live.js` is switched back
to debounce — checked by temporarily doing exactly that.

**Testing time without waiting.** Hoot replaces `setTimeout` with a fake clock in tests;
`advanceTime(150)` jumps it forward instantly, and `Deferred` is a promise the test resolves by hand
— that's how the "replies arrive in the wrong order" case is staged deterministically.

**`onWillDestroy` vs `onWillUnmount`.** Unmount only happens for a component that was mounted. If
loading the scene fails, the component is destroyed without ever mounting — so cleanup that must
always run (unsubscribing from the bus) lives in `onWillDestroy`.

**Not fixed, on purpose: #6.** Messages go to all Inventory users, in every company; each browser
drops other warehouses' slots. In a multi-company database that's extra traffic and exposes bare
location ids (no names or stock) across companies. Multi-company is out of scope for this project;
the fix would be per-company channels.

## T10: Rows stay inside the building and never overlap

Files: `models/warehouse_rack_row.py` (`_wh3d_footprint`, `_check_layout`),
`models/warehouse_layout_area.py` (`_wh3d_footprint`), `models/stock_warehouse.py`
(`_check_wh3d_contains`, `_check_wh3d_size`), `tests/test_rack_row.py` (`TestRackRowLayout`),
`tests/common.py` (`template_rows`).

**Why on the server.** The 2D editor (T11–T12) will check these rules in the browser for instant
red/green feedback, but the browser can be bypassed (imports, scripts, a second tab). The rules
that keep the data consistent must live in the model, where every write passes.

**One question, asked of different shapes.** "Is this rectangle inside the building?" applies to
layout areas and rack rows, but they describe their rectangle differently: an area's `width` runs
along x, a rack row's `depth` runs along x and its bays along y. Each model answers
`_wh3d_footprint() → (x0, y0, x1, y1)`; `_check_wh3d_contains` only uses that. (A small example of
*duck typing*: the check doesn't care which model it gets, only that it can answer the question.)

**Overlap test for two rectangles** (axis-aligned, so no rotation): they overlap only if they
overlap on **both** axes — `a.x0 < b.x1 and b.x0 < a.x1 and a.y0 < b.y1 and b.y0 < a.y1`. Strict `<`
(with a 1 µm slack for floating point) means touching edges don't count, so back-to-back rows are
fine. Only **active** rows count, and re-activating a row onto a newer one is refused.

**The building can't shrink under its contents** — the warehouse's size check now covers rack rows
as well as areas.

**Test detail worth knowing.** When a test expects several refusals in a row, each attempt needs its
own `self.cr.savepoint()`: a Python constraint runs *after* the row was inserted, so without the
savepoint the refused row stays in the test's transaction and breaks the next attempt (caught here
when the second case hit "duplicate code" instead of "outside the building").

## T11: The 2D layout editor — drawing and selecting

Files: `static/src/editor/geometry.js` (pure), `static/src/editor/editor_action.{js,xml,scss}`,
`views/view3d_actions.xml`, `views/menus.xml`, `models/stock_warehouse.py` (`wh3d_get_layout`),
`static/src/view3d/view3d_action.js` (`focusFromContext`), `static/tests/editor_geometry.test.js`,
`static/tests/tours/view3d_tour.js`, `tests/test_view3d.py`, `docs/screenshots/t11-layout-editor.png`.

**SVG, drawn in metres.** The plan is an `<svg>` whose single `<g transform="translate(ox oy)
scale(s)">` turns metres into pixels. Rows, areas and the grid are drawn with their real
coordinates (P05 is `<rect x="11" y="1" width="1.1" height="18.9">`); zooming and panning only
change `s`, `ox`, `oy`. `vector-effect="non-scaling-stroke"` keeps outlines 1 px thick at any zoom,
and text sizes are in metres too (`font-size: 0.7px` inside the scaled group = 0.7 m).
Why not Three.js again? A flat plan needs no 3D, SVG elements are clickable and focusable like HTML,
and they're crisp when zoomed.

**The view maths** (`geometry.js`, unit-tested): `fitView` picks the largest scale that shows the
whole building with a margin; `zoomAt` zooms around the mouse so the point under it stays put
(convert the mouse to plan coordinates, change scale, solve the offset so that point maps back to
the same pixel); `pan` adds the drag distance. Zoom is clamped to 1–200 px per metre.

**Keyboard without trapping it.** Each row is `<g tabindex="0" role="button">`, so the browser's own
Tab key walks through rows and focusing one selects it; Esc clears. Capturing Tab to "cycle rows"
would have locked keyboard users inside the plan.

**A lighter request.** `wh3d_get_layout` returns building, areas and rows — no 2,340 slots — and
`wh3d_get_scene` now builds on it (one definition of the floor plan instead of two).

**Opening another action with context.** "View in 3D" calls
`action.doAction("warehouse_3d.action_wh3d_view3d", {additionalContext: {focus_row_id, focus_bay, …}})`;
the 3D view reads `props.action.context`, selects that slot and flies to it. Bay/level/position are
passed instead of a code, because codes are only ever built in Python (plan decision 3).

**A test-tool limitation, worked around.** Odoo's tour `click` helper calls `HTMLElement.focus()`/
`blur()` on the target and the previously focused element; on SVG elements that throws
"Illegal invocation". Browsers handle focus on SVG `tabindex` elements fine, so the tour dispatches
the click and Escape events itself and blurs the SVG row natively before clicking HTML buttons.

**Screenshot-driven polish.** The first editor screenshot showed back-to-back rows' codes colliding
("P02P03"); codes now alternate above/below, like the 3D view's labels.
