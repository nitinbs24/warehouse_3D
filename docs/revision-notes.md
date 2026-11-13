# Warehouse 3D: revision notes

Short version of `documentation.md`. One small card per file, plus the big picture. Card numbers match the section numbers in `documentation.md`, so you can jump there for the full line-by-line explanation.

Read this file for revision. Read `documentation.md` when a card isn't enough.

Each file card has the same four parts:

- **Does:** what the file does, in brief.
- **Decisions:** the design choices made in this file, and why.
- **Data structures:** the shapes of data it uses or hands out.
- **Watch out:** easy mistakes and surprises.

---

## The big picture

**What the module does:** you draw a warehouse layout (2D editor) and see it in 3D inside Odoo, with live stock from Inventory.

**The one idea behind everything:**

```
one rack row record  ──►  the 3D shape (uprights, beams, slots)
                     └─►  the Inventory locations (WH/Stock/PR/P05/P05-03/P05-03-2/P05-03-2-A)
```

Change a number on the row (bays, levels, size) and both follow.

**The three layers:**

| Layer | Files | Job |
|---|---|---|
| Data (Python) | `models/*.py` | Tables, rules, generating locations, serving data |
| Screens (XML) | `views/*.xml` | Lists, forms, menus, and the doors to the JS screens |
| Browser (JS) | `static/src/**` | The 3D view and the 2D editor *(covered in `view3d/`: `layout.js`, `occupancy.js`, `live.js`, `walk.js`, `scene.js`, `view3d_action.js`, `view3d_action.xml`)* |

**Facts to remember:** Odoo 19, depends on `stock` and `bus`. Template building is 60 × 40 × 10 m. Pallet row = 7 bays × 5 levels × 2 slots. Location names: pallet `P05-03-2-A`, shelf `S04-10-3`.

---

## Decisions across the whole module

The per-file cards below repeat the ones that belong to each file. This is the short list of the ones that matter most.

| # | Decision | Why |
|---|---|---|
| 1 | The rack row is the **single source of truth**. Generated locations are locked against hand edits | Edits made in two places would drift apart |
| 2 | Locations are **archived, never deleted** | Inventory history (moves, counts) may point at them |
| 3 | A change that would archive a location is **refused if it holds, reserves or awaits stock** | Never lose track of real stock |
| 4 | The editor saves **all or nothing** (a savepoint), and the overlap check runs **once on the final layout** | Swapping two rows would otherwise fail on the messy middle state |
| 5 | The editor may change **only whitelisted fields**, and only records of the **same warehouse** | A made-up request can't touch other data |
| 6 | Data is fetched with **one grouped query**, not one per record | Avoids the "N+1 queries" slowdown |
| 7 | Live updates: **collect changed locations, send one bus message just before commit, carrying only ids**; the browser then asks for fresh data | A 50-line receipt gives one message; each user's own access rules apply to the data |
| 8 | Slot **capacity** = bay width ÷ slots per level × depth × level height. **Fill** = used volume ÷ capacity. Size 0 means **unknown** | Needs only the product box size |
| 9 | Demo stock uses a **seeded random generator** and is booked as a **real inventory adjustment** | Same demo on every machine, and the stock is real |
| 10 | Layout rules: rows may **touch** but not overlap; docks must **touch a wall**; areas can't overlap rows; everything stays **inside the building** | Keeps the plan believable |
| 11 | Menus **hide**, access rules **secure** | Hiding a menu is not a lock |
| 12 | On delete: warehouse **cascade**, zone location **restrict**, row link on a location **set null** | Protects data in each direction |

## Data structures across the whole module

| Name | Shape | Where |
|---|---|---|
| **Rack row record** | `code`, `kind`, `warehouse_id`, `location_id` (zone), `x`, `y`, `bays`, `bay_width`, `depth`, `levels`, `level_height`, `slots_per_level` | `warehouse_rack_row.py` |
| **Node key** | tuple `(node, bay, level, position)`. `node` is `row`, `bay`, `level` or `slot` | matches "wanted" with "existing" locations |
| **Location tree** | list of `(key, parent_key, name)`, parents first | `_location_tree` |
| **Footprint** | `(x0, y0, x1, y1)` floor rectangle in metres | rows and areas both have `_wh3d_footprint()` |
| **Save request** | `{create: [{tmp_id, vals}], write: [{id, vals}], delete: [ids], areas: {same three}}` | `wh3d_save_layout` |
| **Layout** | `{warehouse_id, name, building, areas, rows}` | `wh3d_get_layout` |
| **Scene** | the layout plus `slots` | `wh3d_get_scene` |
| **Slot dict** | `{location_id, code, path, row_id, bay, level, position, capacity_m3, stock}` | `_wh3d_slot_dict` |
| **Pending set** | a `set` of location ids in `cr.precommit.data` for one transaction | `stock_quant.py` |
| **Context flags** | `wh3d_defer_layout_check` (skip the overlap check for now), `wh3d_sync` (the row's own code may edit locked locations) | the model files |

## How a save flows

```
Editor presses Save
   ▼
wh3d_save_layout       whitelist fields, check ownership, savepoint
   ▼
create / write / unlink   check stock first, then super()
   ▼
@api.constrains        code, slots, zone, overlap, bounds
   ▼
_sync_locations        create missing, fix different, archive unwanted (layer by layer)
```

## How a live update flows

```
stock change ─► quant create/write/unlink ─► note the location
   ─► just before commit: keep only slots, send ONE bus message {location_ids}
   ─► 3D view receives it ─► wh3d_get_slots(ids) ─► redraw those slots
```

---

# File cards

## 1. `__manifest__.py`

**Does:** the module's identity card and load list. Odoo finds, installs and wires up the addon from it.

**Decisions:**
- Depend on `bus` for live updates instead of building a separate websocket or Kafka service (the project moved fully inside Odoo).
- `data` loads in a fixed order: security, then views, then actions, then menus last. A later file can use things an earlier one defines.
- The JS is split into three folders (`common`, `view3d`, `editor`) but ships in one bundle, `web.assets_backend`.
- Unit tests and browser tours get their own bundles, so they never reach normal users.
- Demo data is kept apart from real data, and loads only on demo databases.

**Data structures:**
- One Python dictionary.
- `data` and `demo` are ordered lists of file paths.
- `assets` is a dictionary: bundle name → list of path patterns.

**Watch out:** a new XML, CSV or JS file is ignored until it is listed here.

## 2. `__init__.py` (module root)

**Does:** the Python entry point. One line: `from . import models`.

**Decisions:**
- The root file only imports the `models` package. The list of model files lives in `models/__init__.py`.
- Import order is the load order: `stock_location`, `warehouse_rack_row`, `stock_warehouse`, `warehouse_layout_area`, `product_template`, `stock_quant`.
- Only models are imported here. The `tests/` folder has its own `__init__.py`.

**Data structures:** none. It is a chain of imports: manifest → `__init__` → `models/__init__` → each model file.

**Watch out:** a model file that is not listed in `models/__init__.py` does nothing, so its fields and methods are "missing".

## 3. `security/ir.model.access.csv`

**Does:** says who may read, write, create or delete the two new tables.

**Decisions:**
- Two levels: Inventory User reads only, Inventory Manager can do everything. This matches the rule "everyone views the layout, only managers change it".
- No rows for `stock.location`, `stock.quant` or products. Those tables already have access rules from `stock`.
- No access for the public or portal.

**Data structures:** a CSV table. Each row is one rule: id, name, model, group, and four 1/0 flags (read, write, create, delete). There are four rows: two models × two groups.

**Watch out:** a model with no row here is denied to every non-admin user.

## 4. `data/res_groups.xml`

**Does:** switches on Inventory's "Storage Locations" setting at install.

**Decisions:**
- Go through `res.config.settings` and not the group directly. Saving the setting also applies its side effects (the New button on Locations, the internal transfer operation type).
- `noupdate="1"`: runs at install only, so an admin who later turns the setting off keeps it off after upgrades.

**Data structures:** an XML `<function>` call that creates one settings record, `{'group_stock_multi_locations': True}`, and applies it.

**Watch out:** despite the file name, it does not define a group.

## 5. `views/view3d_actions.xml`

**Does:** registers the two JS screens (3D View, Layout Editor) as Odoo client actions.

**Decisions:**
- The screens are **client actions** (run a JS component), not window actions (list or form).
- The `tag` is the join key between XML and JS: `warehouse_3d.view3d` and `warehouse_3d.editor`.
- The actions carry no security. Menus and access rules do that.
- They are reusable. Section 12's warehouse buttons load them and add a `warehouse_id` to their context.

**Data structures:** two `ir.actions.client` records, each with a `name` and a `tag`. On the JS side, `registry.category("actions").add(tag, Component)`.

**Watch out:** a typo in a tag fails only at runtime ("client action not found").

## 6. `views/menus.xml`

**Does:** builds the menu entries under Inventory.

**Decisions:**
- Two branches. The everyday screens go in the Inventory top bar (**Warehouse 3D**: 3D View for users, Layout Editor for managers). The raw data screens go under **Configuration ▸ Warehouse 3D** (Rack Rows, Layout Areas, managers only).
- Visibility is set on the parent and inherited by the children. The editor adds a stricter group on top.
- `sequence` numbers fix the order. The file loads last, because a menu needs its action to exist.

**Data structures:** a menu tree. Each node has a parent, an action (or none, for a folder), a sequence number and a `groups` list.

**Watch out:** `groups` on a menu only hides the entry. The real protection is `ir.model.access.csv`.

## 7–8. `models/warehouse_rack_row.py` (the core)

**Does:** the rack row table, its validation, and the generation of Inventory locations. 377 lines.

**Decisions:**
- **Locations are generated from the row.** The row is the single source of truth.
- **Two levels of rules:** simple ones in the database (`models.Constraint`), cross-record ones in Python (`@api.constrains`).
- **Check first, then act, then sync** in `create`, `write` and `unlink`. A refused change leaves everything untouched.
- **Stock guard:** `_check_removal` blocks any change that would archive a location holding, reserving or awaiting stock.
- **Archive, don't delete.** Inventory history may point at those locations.
- **Deferred overlap check** (`wh3d_defer_layout_check`). The editor applies all edits, then checks the end state once, so swapping two rows works.
- **Atomic save** with a savepoint, and a **field whitelist** plus an **ownership check** on every record the editor touches.
- **Sync layer by layer** (row, bay, level, slot) and reuse, rename, re-parent or re-activate existing locations instead of recreating them.
- **Storage category only on slots,** so "closest location" putaway never picks a bay or a level.
- Touching rows are allowed. Only a real overlap is an error (tolerance `EPS`).

**Data structures:**
- **Recordsets:** `self` is a group of 0, 1 or many records.
- **Frozensets of field names:** `SHAPE_FIELDS`, `SYNC_FIELDS`, `EDITOR_FIELDS`, `AREA_EDITOR_FIELDS`.
- **Node key:** a tuple `(node, bay, level, position)`.
- **Location tree:** a list of `(key, parent_key, name)`, parents first.
- **`by_key`:** a dictionary of node key → existing location (archived ones included).
- **Footprint:** a tuple `(x0, y0, x1, y1)`.
- **Save request and reply:** `changes` dictionary in, `{created, created_areas, layout}` out. `tmp_id` maps a browser-made id to the real one.
- **Constraint list:** four `models.Constraint` entries.

**Watch out:** `depth` runs along **x** and the bays run along **y**. Pallet rows get a level node, shelf rows skip it. With the template numbers, one pallet row makes 113 locations.

## 9. `models/stock_location.py`

**Does:** adds five fields to Odoo's locations and locks the generated ones.

**Decisions:**
- Extend the existing table with `_inherit`, not a new table, so Inventory keeps working with the same locations.
- Lock `name`, `location_id` and `usage` on generated locations with a `write` override.
- The lock has a **private bypass**: only code that sets `wh3d_sync` in its context can change them.
- Saving the **same value** is allowed. Only a real change is refused.
- `active` is not locked, so archiving still works.
- `copy=False` on every field, so a duplicated location is a plain one.
- `index='btree_not_null'`: most locations have no row, so the index skips empty values.
- `ondelete='set null'`: deleting a row keeps the location and clears the link.

**Data structures:**
- Five fields: `wh3d_rack_row_id` (link), `wh3d_node` (`row`, `bay`, `level` or `slot`), `wh3d_bay`, `wh3d_level`, `wh3d_position`.
- `LOCKED_FIELDS`, a tuple of three names.
- The context flag `wh3d_sync`.

**Watch out:** `storage_category_id` is not locked. Nothing in this file stops a hand edit of it.

## 10. `models/warehouse_layout_area.py`

**Does:** a floor area (receiving, packing, …) or a dock door drawn on the plan. Holds no stock.

**Decisions:**
- A **separate table** from rack rows: areas have no stock and no location tree.
- **One table for both areas and docks,** told apart by `kind`.
- A dock must **touch a wall**: the smallest of its four wall gaps must be within `EPS`.
- **Docks are left out** of the "area vs rack row" overlap check, because they sit on walls.
- The shared checks live on the warehouse model, so areas and rows use the same rules.
- The same method name, `_wh3d_footprint`, as rack rows, so other code can treat both alike.
- The colour is checked with a regex (`#rrggbb`) and `fullmatch`.

**Data structures:**
- Fields: `name`, `kind`, `warehouse_id`, `company_id`, `x`, `y`, `width`, `depth`, `color`.
- Footprint tuple `(x0, y0, x1, y1)`.
- The four wall gaps `(x0, y0, length − x1, width − y1)`, checked with `min`.
- One database rule: width and depth above 0.

**Watch out:** `width` runs along **x** and `depth` along **y**. That is the other way round from a rack row.

## 11. `views/warehouse_rack_row_views.xml`

**Does:** the list, form and search screens for rack rows, and the action that opens them.

**Decisions:**
- The warehouse column and field show only with multiple warehouses (`groups`), so single-warehouse users see a simpler screen.
- `storage_category_id` is an optional column, hidden by default.
- The form has a **Regenerate Locations** button (managers only) and a **Slots** smart button.
- `slots_per_level` is read-only for shelves, but the screen does not set it to 1.
- The `active` field is loaded but hidden, so the *Archived* ribbon can read it.
- The search view has Pallet, Shelving and Archived filters, and Group By kind or zone.

**Data structures:** four XML records: three `ir.ui.view` (list, form, search) and one `ir.actions.act_window` (`view_mode` `list,form`). Filters are domains, lists of `(field, operator, value)`.

**Watch out:** the side panels in the 3D view and the editor are **not** here. They are in the OWL templates under `static/src/`.

## 12. `models/stock_warehouse.py`

**Does:** adds the building size to warehouses, serves data to the JS screens, holds shared checks, and books demo stock.

**Decisions:**
- **The building size lives on the warehouse** (60 × 40 × 10 m default). Shrinking it is refused if anything would stick out.
- **Shared checks sit here** as `@api.model` methods, so rack rows and areas call one version of each rule.
- **The server returns plain dictionaries** (`read(..., load=None)`), so the browser can use them directly.
- **The scene is built in a fixed number of queries** however many slots there are.
- **Two-step loading:** `wh3d_get_scene` for the first draw, `wh3d_get_slots` for live updates of only the changed slots.
- **Default warehouse** for the screens: the first one with rack rows, else the first one. The warehouse list follows the user's company rules.
- **The screens learn which warehouse to show** from the action's `context` (`{'warehouse_id': id}`).
- **Capacity** = bay width ÷ slots per level × depth × level height. **Fill** = used volume ÷ capacity. If any product has no size, fill is unknown (`None`).
- **Demo stock is repeatable:** a seeded random generator, products and slots sorted before use, about 65% of slots filled, fast movers (ABC weights 6, 2, 1) stocked more often, and three fill bands that match the occupancy colours.
- **Demo stock is real:** booked as one inventory adjustment, not inserted directly.

**Data structures:**
- **Layout:** `{warehouse_id, name, building, areas, rows}`.
- **Scene:** the layout plus `slots`.
- **Slot dict:** `{location_id, code, path, row_id, bay, level, position, capacity_m3, stock}`.
- **Stock dict:** `{product_id, name, default_code, qty, uom, mixed, used_m3, fill}`.
- **`by_slot`:** a dictionary of slot → list of `(product, quantity)`.
- **Plan:** a list of `(slot, product, quantity)`.
- **Constants:** `_WH3D_ABC_WEIGHT` and `_WH3D_FILL_BANDS`.

**Watch out:** the name and quantity in a slot are for its **biggest** product only, but `used_m3` adds up all products. `mixed` says there is more than one.

## 13. `models/stock_quant.py`

**Does:** notices stock changes and sends one live notification for the affected rack slots.

**Decisions:**
- **Hook the ORM methods** (`create`, `write`, `unlink`), so every stock operation is caught, whichever screen caused it.
- **Batch with a pre-commit hook:** collect changed locations during the transaction and send **one** message just before commit.
- **Send only ids,** never stock data. The browser then asks for the data, so access rules apply per user.
- **Filter to slots at send time,** with `sudo()`, so the result doesn't depend on who made the change.
- **Ignore reservations,** since the 3D view doesn't show them.
- **Remember locations before a delete,** and both old and new locations after a move.
- The message goes to the Inventory User group.

**Data structures:**
- `PENDING_KEY`: a name under which a `set` of location ids is kept in `cr.precommit.data`.
- The bus message: type `'warehouse_3d/stock'`, content `{'location_ids': [...]}`.

**Watch out:** a `set` drops duplicates, so 50 changes to one slot count once.

## 14. `models/product_template.py`

**Does:** adds a box size and a speed class to every product.

**Decisions:**
- The fields go on the **template**, so every variant reads them.
- Sizes are in **metres** with 3 decimals (millimetre precision).
- **0 means unknown,** so there is no default and no `required`. Unknown size means no fill percentage.
- The ABC class is optional. It is kept for the later putaway experiments.
- No validation rules in this file.

**Data structures:** four fields: `wh3d_length`, `wh3d_width`, `wh3d_height` (floats) and `wh3d_abc_class` (a selection: A fast, B medium, C slow).

**Watch out:** the warehouse table has fields with the same names (the building size). Different tables, so no clash. Only the demo-stock planner reads the class so far.

## 15. `tests/common.py`

**Does:** shared test data and helper functions for the Python tests.

**Decisions:**
- Keep the helpers **small**. Each test still says what it needs.
- One standard example row, `P05`, taken from the project handoff, and every test copies it.
- `create_p05` accepts **overrides**, so a test changes only the field it cares about.
- A test that needs the demo warehouse is **skipped, not failed**, when the database has no demo data.
- The 31-row template layout is written once as plain dictionaries.

**Data structures:**
- `P05`: a dictionary of rack row fields (70 slots, 113 locations).
- A zone: an Internal `stock.location` under `WH/Stock`.
- `template_rows()`: a list of 31 field dictionaries (14 pallet, 17 shelf), without warehouse or zone.
- `SkipTest`: the signal that skips a test.

**Watch out:** do not pass `warehouse_id` or `location_id` as overrides. Use the `zone` argument instead.

## 16. `tests/test_rack_row.py`

**Does:** tests the rack row rules (valid data, refused data, permissions, layout).

**Decisions:**
- Two classes: one for the row's own rules, one for the **layout** rules.
- Database rules are tested through `IntegrityError`, and Python rules through `ValidationError`.
- A `savepoint` wraps each expected failure, so the test keeps working after a database error.
- Permissions are tested with **real test users** (Inventory User and Manager).
- The install-time setting and its `noupdate` behaviour are tested too.
- Review findings (CodeRabbit) were turned into tests.
- Edge cases are tested on purpose: touching walls, touching rows, archived rows, moving, growing, shrinking the building.
- One test creates all **31 template rows** at once, to prove the spec layout is valid.

**Data structures:**
- `_vals(**overrides)`: the P05 dictionary plus warehouse and zone.
- `cases`: a dictionary of label → overrides, looped with `subTest`.
- `template_rows()`: the list of 31 field dictionaries from section 15.
- Test users made with `new_test_user`.

**Watch out:** the "zone must be inside the warehouse" test uses a location of type `view`. That location also breaks the "zone must be Internal" rule, so the test can't tell which of the two rules refused it.

## 17. `tests/test_location_generator.py`

**Does:** tests that a rack row builds the right location tree, and that rebuilding it is safe.

**Decisions:**
- Check the tree on every level: **counts, names, full paths and stored indices** (bay, level, position).
- **Only slots carry the storage category.** A test proves that Odoo's "closest location" putaway then lands in a slot.
- **Regenerating is safe:** no duplicates, and a missing slot comes back.
- A **speed guard**: 14 pallet rows must build in under 30 seconds, and give 980 slots.
- The file builds its own rows (`_pallet`, `_shelf`) and doesn't use `common.py`.

**Data structures:**
- Counts to remember: pallet row = 1 + 7 + 35 + 70 = **113** locations, 70 slots. Shelf row = 80 bins, no level nodes.
- Path strings: `WH/Stock/PR/P05/P05-03/P05-03-2/P05-03-2-A` and `WH/Stock/SH/S04/S04-10/S04-10-3`.
- The putaway rule fields: `location_in_id`, `location_out_id`, `sublocation = 'closest_location'`, `storage_category_id`.

**Watch out:** the speed test uses the wall clock, so on a very busy machine it could be slow for reasons that have nothing to do with the code.

## 18. `tests/test_location_sync.py`

**Does:** tests that editing, archiving or deleting a rack row keeps its locations in step and never loses stock.

**Decisions:**
- Every test starts from a **fresh P05** (`setUp`), so tests are independent.
- A change must **keep the same location records** (rename, re-parent, revive). Stock is attached to them.
- Only shape fields touch locations. Floor-plan changes leave them alone.
- Every removing change is tested **with stock, with a transfer on its way, and below a hand-made bin**.
- Archiving or deleting a row follows the **same guard**.
- Locations are **archived on delete**, and still exist.
- Each code-review finding (#1, #2, #4, #5, #6) has its own test.

**Data structures:**
- Counts: grow to 8 bays = 80 slots. Shrink to 6 = 60 slots and 16 archived (1 bay + 5 levels + 10 slots). 4 levels = 56 slots and 28 level nodes. Pallet to shelf = 35 slots.
- `_locations(node, active)`: a helper that returns recordsets, archived ones included on request.
- `(0, 0, {...})`: the "create this related record" tuple used to build a transfer.

**Watch out:** the test named "reserved or incoming" sets up only the *incoming* case (a confirmed receipt), not a reservation. The receipt code at lines 73–82 repeats `_confirmed_receipt_into`, which was added later.

## 19. `tests/test_layout_save.py`

**Does:** tests the editor's Save call (`wh3d_save_layout`) for rows, areas and docks.

**Decisions:**
- **All or nothing** is proven by sending one valid and one invalid change together, then checking that **neither** was kept.
- **End-state checking** is proven with swaps: row with row, and row with area.
- The **field whitelists** are tested for rows and for areas, field by field.
- **Records from another warehouse** are refused for both edits and deletes.
- Only **managers** can save (an Inventory User gets `AccessError`).
- Rows, areas and docks use **one save call**.
- One test builds a whole empty warehouse in a single save, like the editor does.

**Data structures:**
- The `changes` dictionary: `create`, `write`, `delete`, and `areas` with the same three keys.
- The reply: `created` and `created_areas` (each maps `tmp_id` to the real id) and `layout`.
- `tmp_id`s are negative numbers (−1, −2, …) chosen by the caller.
- `door(n, **pos)`: a small function that builds a dock dictionary.

**Watch out:** `result['created'][-1]` is a dictionary key, not the last item. Areas and docks share one `created_areas` dictionary, so their `tmp_id`s must all be different.

## 20. `tests/test_scene_data.py`

**Does:** tests the data given to the 3D view: the scene, the slot refresh, the layout, and the product form fields.

**Decisions:**
- The tests **pin the data contract** with the browser: exact keys for scene, slot and stock.
- Expected numbers are **calculated by hand** in comments (slot 2.673 m³, rice 1.32 m³), not copied from the code.
- A mixed slot shows the product with the **largest quantity** but adds up **all** volumes.
- **Unknown size gives `None`** for fill, never 0.
- Archived slots are left out.
- **A fixed number of queries** is proven by counting queries before and after adding rows and stock.
- A normal Inventory User can load the scene.
- A `Form` test proves the size fields are on the product screen.

**Data structures:**
- Scene: `{warehouse_id, name, building, areas, rows, slots}`.
- Slot: `{location_id, code, path, row_id, bay, level, position, capacity_m3, stock}`.
- Stock: `{product_id, name, default_code, qty, uom, mixed, used_m3, fill}`.
- Test products: rice (1.32 m³), oil (0.036 m³), a box with no size.

**Watch out:** `_scene_slot` fails with a plain `StopIteration` if the slot isn't in the scene. The query count test needs `invalidate_all()` first, or Odoo's cache hides the queries.

## 21. `tests/test_bus.py`

**Does:** tests that stock changes in rack slots are announced on the bus (section 13).

**Decisions:**
- Test through **real paths**: a validated receipt, an inventory adjustment, and a direct quantity update.
- **Run the pre-commit hooks by hand** (`cr.precommit.run()`), since a test never commits.
- **Clear the bus table** at the start of each test, so only that test's messages are counted.
- One multi-line receipt must give **one message**.
- A move announces **both** slots. A reservation announces **nothing**. Stock outside slots announces nothing.
- The **channel** is checked: the Inventory User group.

**Data structures:**
- A bus record: `channel` (JSON: `[database, 'res.groups', group id]`) and `message` (JSON: `{'type': 'warehouse_3d/stock', 'payload': {'location_ids': [...]}}`).
- `_stock_notifications()` returns a list of `(channel, payload)` pairs.
- Three test slots: `P05-01-1-A`, `P05-01-1-B`, `P05-02-1-A`.

**Watch out:** without `precommit.run()` no message appears, because the hook never runs. Not tested here: deleting a quant, and a rolled-back transaction.

## 22. `static/src/view3d/layout.js`

**Does:** turns floor plan numbers into the boxes and camera positions the 3D view draws. Pure maths, no Three.js, no page.

**Decisions:**
- **Keep geometry pure** (no Three.js, no DOM), so it can be unit-tested with plain numbers.
- **Two coordinate systems and one converter:** plan (origin at a corner, y along the width) and world (centred, plan y becomes world z, height is world y), joined by `toWorld`.
- **Everything is a box:** `[centreX, centreY, centreZ, sizeX, sizeY, sizeZ]`.
- **Lift bigger areas lowest** so a smaller area inside shows on top and doesn't flicker. A documented `shortcut:` caps the lift at 3 steps.
- A dock gets a frame **only if it touches a wall**. The wall comes from its shape (`width >= depth` means front or back).
- The colour is **checked again** in the browser, with a fallback.
- Slot boxes are made slightly smaller or larger than the slot, so neighbours don't touch.

**Data structures:**
- Box: `[cx, cy, cz, sx, sy, sz]`. Grid line: `[x1, z1, x2, z2]`.
- Returns: `floorGeometry` → `{floor, gridLines, curbs}`. `dockGeometry` → `{pad, frame}`. `rackGeometry` → `{uprights, beams, decks, topHeight}`. `slotBox` → `{base, box}`. `cameraView` → `{position, target}`.
- Inputs are the scene dictionaries from section 12: `building`, row, area or dock, and slot.
- Counts: a pallet row with 7 bays has 16 uprights and 8 beams. A shelf row has decks and no beams.

**Watch out:** plan `y` is world `z`, and world `y` is up. Slot `bay`, `level` and `position` are 1-based. For an area `width` is along x, but for a rack row `depth` is along x.

## 23. `static/src/view3d/occupancy.js`

**Does:** turns slot stock data into a colour band, a stock box, summary counts, and the merge of fresh data after a live update. Pure maths, no Three.js.

**Decisions:**
- The **three bands** (below 50%, 50–90%, above 90%) match the server constants in section 12. An **unknown fill** gets its own label, `nodims`.
- **One box per slot**, sized by volume: stock volume ÷ floor area, **capped at the slot's height**. Unknown volume shows as **half height**.
- The **average fill ignores unknown fills**, and is `null` when none are known.
- **Live merge works in place.** A slot that was asked for but not returned is shown **empty** (it was archived). Ids from **other warehouses are ignored**, because the live message goes to everyone.
- Reuses `slotBox` from `layout.js`.

**Data structures:**
- Bands: the strings `"low"`, `"mid"`, `"high"`, `"nodims"`.
- Summary: `{ rows: {pallet, shelf}, pallet: {total, used, avgFill}, shelf: {total, used, avgFill} }`.
- Legend: `{ low, mid, high, nodims }`.
- Load box: `[cx, cy, cz, sx, sy, sz]`.
- `indexByLocation`: a `Map` from location id to position in `slots`.

**Watch out:** the stock box height is capped at the slot box height, which is smaller than the slot's volume height. With the template numbers, a pallet slot looks full from about 89% fill (1.6 m of 1.8 m), and a shelf from 90%. A slot whose `row_id` isn't in the rows list makes `capacitySummary` fail.

## 24. `static/src/view3d/live.js`

**Does:** turns the stream of "these locations changed" live messages into orderly refetches. One class, `UpdateQueue`.

**In simple words:** think of a runner with a notepad.
1. **Write it on the notepad.** Each live message only adds a slot number to the notepad (`pending`). The same slot twice is written once.
2. **Wait a moment, then go once.** The first message starts a short timer. More messages during the wait go on the same notepad. When the timer ends, he takes the whole notepad and makes **one trip** to the server for all of them.
3. **Only one trip at a time.** While he is away, new messages go on a fresh notepad. He never starts a second trip until he is back, so an old answer can't arrive after a newer one.
4. **If the trip fails, write the numbers back** and try again after a slightly longer wait. Nothing is lost.
5. **After a trip, check the notepad.** If new numbers appeared, set another timer and go again. If it is empty, rest.
- **Before the scene is ready** he only collects notes (until `start()`).
- **When the view closes or switches warehouse** (`stop()`) he throws the notepad away and cancels his timer. An answer that arrives after that is ignored.
- **In one line:** collect the changes, go to the server once in a while for all of them together, never run two trips at once, never lose a change.

**Decisions:**
- **Throttle, not debounce.** At most one fetch per `delay` ms. A debounce would never fire in a busy warehouse.
- **One fetch at a time,** so an older reply can't overwrite a newer one.
- **Collect until `start()`,** so nothing is missed while the scene loads.
- **A failed fetch puts its ids back** and retries after a separate, longer `retryDelay`.
- **`stop()` forgets everything** (used when the view switches warehouse), and a result that arrives after `stop()` is thrown away.
- `fetch` and `apply` are **given in**, so the class knows nothing about Odoo and can be tested with fake ones.

**Data structures:**
- `pending`: a `Set` of location ids waiting to be fetched (it drops duplicates).
- State flags: `started`, `running`, and `timer` (`null` when none waits).
- Options object: `{ delay, retryDelay, fetch, apply }`.

**Watch out:** a timer is only set when started, not running, no timer waiting, and something pending. The first change waits up to `delay`. A fetch that fails after `stop()` puts its ids back, which looks harmless because ids from other warehouses are ignored (section 23).

## 25. `static/src/view3d/walk.js`

**Does:** the maths of walk mode: where the walker starts, how keys and the mouse move them, and how racks and walls stop them. Plain numbers on the floor plan, no Three.js.

**Decisions:**
- **Pure functions:** state in, new state out, nothing changed in place.
- **Plan coordinates,** not world ones. The walker is a **circle** (radius 0.3 m). Racks are rectangles. Walls are limits.
- **Slide along obstacles:** if the full move is blocked, try each axis alone.
- **Small steps** (at most half the radius) so a slow frame can't tunnel through a thin rack.
- **Diagonals are not faster:** the move is normalised, then scaled by speed × time.
- **Start in the middle of the aisle** (half the clearance, at least radius + 5 cm, at most 2.5 m), facing the rack. With no slot, start on the first dock, or by the front wall.
- **Mouse look is like Street View** (drag right turns the view left), and pitch is limited to about 80°.
- **Key presses are ignored while typing, but releases always count,** so the walker can't get stuck walking (found in code review).

**Data structures:**
- Pose: `{ x, y, yaw }` (plus `pitch` for `look`). Yaw 0 is towards +x, π/2 towards +y.
- Keys: `{ forward, back, left, right, run }`. Move: `{ dx, dy }`. Obstacle: `{ x0, y0, x1, y1 }`.
- Key event: `{ type, key, shiftKey, typing }`. `walkKey` returns `{ keys, handled, exit }`.
- `WALK_KEYS`: a lookup from key name to action. Constants: eye height 1.7 m, radius 0.3 m, speed 1.4 m/s, run ×2.5.

**Watch out:** the start functions give no `pitch`, but `look` needs one. The comment on `stepWalker` says steps are at most the radius, but the code uses half the radius. The walker's centre can never be closer than 0.3 m to a wall or rack.

## 26. `static/src/view3d/scene.js`

**Does:** builds and runs the Three.js scene of one warehouse (floor, areas, docks, racks, stock, labels), with clicking, camera flights, walk mode and clean-up.

**Decisions:**
- **Everything is a scaled copy of one unit cube,** using the boxes from `layout.js`.
- **Instancing:** identical parts share one draw call (all uprights, all beams, all decks, curbs, areas per colour, dock pads, dock frames, stock). Few draw calls, fast on large warehouses.
- **Click = invisible hit boxes + a raycaster.** Instance index = slot index.
- **A click is a pointer that moved under 6 px,** so an orbit drag isn't mistaken for a click.
- **Stock is rebuilt from scratch** when it changes. Colour per instance: neutral grey or the occupancy band. **Unknown fill is striped** while colouring by occupancy.
- **Occupancy colouring starts off.**
- **The scene calls back (`onSelect`, `onWalk`)** and does not know the page.
- **Pure maths stays in other files;** this file only does Three.js and the page.
- **Reduced motion is respected,** and the frame time is capped at 0.1 s in walk mode.
- **Walk mode saves the orbit view and restores it exactly.** It uses a nearer near plane (0.05 m).
- **Labels are drawn on a canvas as sprites.** Area labels show through racks, and row codes hide behind them.
- **`dispose` frees everything,** because WebGL isn't garbage-collected and browsers allow about 16 contexts.

**Data structures:**
- `data`: the scene dictionary from section 12 (`building`, `areas`, `rows`, `slots`).
- `this.slots`: an array whose **index** is also the hit-box instance id and the selection index. `rowsById`: row id → row.
- `this.walk`: `{ x, y, yaw, pitch, keys, last }`. `this.anim`: `{ t0, p0, q0, p1, q1 }`.
- `byColor`: a `Map` from colour to boxes. `knownBands`: the band of each known-fill stock box.
- `COLORS`, `BAND_COLORS` (low green, mid amber, high red).

**Watch out:** the **order of `slots` must not change,** because picks and selection use the index. (`mergeSlotUpdates` replaces entries in place, so it keeps the order.) `window.THREE` and OrbitControls must already be loaded, and without WebGL the constructor throws. `dispose()` must be called when the view closes.

## 27. `static/src/view3d/view3d_action.js`

**Does:** the 3D View screen: an Odoo (OWL) component that loads data and Three.js, creates the scene, receives live stock updates, and holds the side panel's state and actions.

**Decisions:**
- **Listen to the bus before loading the scene.** Early changes wait in the queue (150 ms throttle, 5 s retry) and are applied when the scene is ready.
- **Load things in parallel** (`Promise.all`): warehouses, default and manager check; then the scene data and Three.js.
- **Three.js is loaded only when this view opens,** not bundled with the rest of Odoo. OrbitControls loads second, because it extends Three.js.
- **Choose the warehouse from three sources:** the action's context, the one remembered in the browser, and the default.
- **Switching loads the new scene first,** so a failed load keeps the old view. Then it disposes the old scene, clears selection and search, and **drops the old warehouse's queued ids**.
- **A live update merges in place** into the array the scene draws from, then rebuilds the stock boxes. A counter (`state.updates`) forces the panel to redraw, because slots aren't reactive.
- **The walker's position goes to the page's data attributes,** not to state, because it changes every frame.
- **Only managers get the editor** (`canEdit`).
- **No warehouse gives an empty building and a message,** not a crash. No WebGL gives a message.
- **Clean-up runs in `onWillDestroy`,** even if loading failed, so the bus listener can't leak.

**Data structures:**
- `state`: `error`, `rowCount`, `view`, `labels`, `stock`, `occupancy`, `selected`, `find`, `findError`, `summary`, `legend`, `updates`, `walking`, `warehouseId`.
- Lookups: `slotByCode` (code → index), `slotByLocation` (location id → index), `rowsById`. The index is the position in `data.slots`.
- `selectedInfo`: `{ slot, row, zone, level, capacity, fill, band }`.
- Context keys: `warehouse_id` (in), and `focus_row_id`, `focus_bay`, `focus_level`, `focus_position` (from the editor's "View in 3D").
- Bus message: type `warehouse_3d/stock`, content `{ location_ids }`.

**Watch out:** `this.data.slots` is changed **in place**, and its order must stay stable, because selection, picking and the lookups all use the index. The panel won't redraw after a live update unless `state.updates` is bumped. `start()` must run after the component is mounted, because it needs the canvas element.

## 28. `static/src/view3d/view3d_action.xml`

**Does:** the HTML template of the 3D View screen: the 3D area, toolbar, messages, hints, and the side panel (selected location, Find, capacity, legend).

**Decisions:**
- **Logic and layout are separate files.** The template has no logic and only reads `state`, getters and methods from `view3d_action.js`.
- **The 3D area is an empty box owned by Three.js.** OWL renders nothing inside it.
- **The root element reads `state.updates`,** which is what makes the screen redraw after a live update (slots aren't reactive).
- **The panel is four cards:** selected location, Find, capacity, legend. Capacity and legend show only once their data exists.
- **Messages by priority:** an error first, then "no rack rows" (with the editor button only for managers).
- **The hint line changes with the mode** (walk or orbit).
- **Built to be accessible:** `aria-pressed`, `aria-label`, `role="alert"`/`"status"`, `aria-live` on the selected card, hidden decorative icons.
- **Data attributes and button names** make the screen easy to test.

**Data structures:**
- The template reads `state` (`rowCount`, `updates`, `walking`, `view`, `stock`, `occupancy`, `labels`, `error`, `selected`, `find`, `findError`, `summary`, `legend`, `warehouseId`), the getters `selectedSlot`, `selectedInfo` and `warehouseName`, and `canEdit`, `warehouses` and `eyeHeight`.
- `info` (from `selectedInfo`): `{ slot, row, zone, level, capacity, fill, band }`.
- Band classes: `o_wh3d_band_low`, `_mid`, `_high`, `_nodims`.
- Page attributes: `data-row-count`, `data-updates`, `data-mode`, `data-eye`.

**Watch out:** nothing OWL-managed may go inside `o_wh3d_canvas`. The panel only redraws after a live update because line 4 reads `state.updates`. The layout and look come from the style sheet `view3d_action.scss`, not from this file.

## 29. `static/src/common/warehouse_picker.js` and `.xml`

**Does:** the warehouse dropdown shared by the 3D view and the editor, with the helpers that choose and remember the warehouse.

**Decisions:**
- **One storage key for both screens,** so both open the warehouse you looked at last. It is remembered **per browser**, not per user account.
- **Order of choice:** the warehouse in the action's context, then the remembered one **if it is still in the list** (not archived, not another company's), then the default.
- **Storage failures never break the screen.** Reading gives `null` and saving is ignored when the store is blocked (for example in a private window).
- **The dropdown hides itself with only one warehouse.**
- **`onChange` must return `true` on success.** On `false` (for example a cancelled discard dialog) the dropdown snaps back to the current warehouse.
- **A shared component in `common/`,** used by both screens. The choosing logic is plain functions, so it can be unit-tested.

**Data structures:**
- A warehouse item: `{ id, name, code, row_count }` (from `wh3d_list_warehouses`). Only `id` and `name` are used here.
- `pickWarehouseId` input: `{ contextId, storedId, warehouses, defaultId }`.
- Storage key: `"warehouse_3d.warehouse_id"`.
- Props: `{ warehouses: Array, value: Number, onChange: Function }`.

**Watch out:** the context choice is not checked against the list. The dropdown's value is text, so it is turned into a number with `parseInt`. The picker draws nothing at all when there is only one warehouse.

## 30. `static/src/editor/geometry.js`

**Does:** the 2D maths of the layout editor: fitting the building on screen, converting metres to pixels and back, zooming and panning, row and area rectangles, the grid, and the "View in 3D" slot.

**Decisions:**
- **One linear mapping** for everything: `screen = plan × scale + offset`, held in a view `{ scale, ox, oy }`. `toScreen` and `toPlan` undo each other.
- **The same orientation as the 3D Top view** (x right, y down), so the plan and the Top view match.
- **Zoom keeps the point under the cursor fixed.** The scale is limited to 1–200 px per metre.
- **Fit = the larger scale that fits both ways,** centred, with a 24 px margin.
- **Rows and areas become plain rectangles** `{ x, y, w, h }`, so the drawing code ignores the fact that `depth` runs along x for a row and along y for an area.
- **A 1 m grid with every 5th line major.**
- **"View in 3D" goes to the middle bay, level 1, position 1.**
- Pure functions, so they are unit-tested without the page.

**Data structures:**
- View: `{ scale, ox, oy }` (scale in pixels per metre, offsets in pixels).
- Rectangle: `{ x, y, w, h }` (metres).
- Grid line: `{ x1, y1, x2, y2, major }`.
- Slot reference: `{ bay, level, position }`.
- Constants: `MIN_SCALE = 1`, `MAX_SCALE = 200`.

**Watch out:** `fitView` doesn't clamp the scale to the limits, but `zoomAt` does. Plan `y` points **down**. For a row the width of the rectangle is its `depth`, but for an area it is its `width`. A viewport smaller than twice the margin would give a nonsense scale (nothing checks).

## 31. `static/src/editor/layout_edit.js`

**Does:** the editing rules of the layout editor as plain data: snapping, problem detection while dragging, new rows, areas and docks, resizing and moving, and the diff that Save sends.

**Decisions:**
- **The rules are written twice on purpose:** the browser mirrors the server's overlap, bounds and dock rules so problems show **while dragging**. The **server stays the authority** on save.
- **Problems are a dictionary `{ id: message }`,** with at most one message per item (the first problem found).
- **The diff sends only changed fields.** Rows and areas each have a list of editable fields that matches the server's whitelist.
- **New things have negative temporary ids** until saved.
- **Everything snaps to a 0.1 m grid** and is never below 0.
- **A new row goes on the first free spot,** scanning every 0.5 m.
- **A palette of nine common area types,** each with a default size and colour.
- **Resizing keeps the opposite edge fixed** and enforces a 0.5 m minimum.
- **Docks always sit on a wall:** they jump to the nearest wall, and on side walls width and depth swap. The minimum opening (2 m) stays above the thickness (1.6 m), so `layout.js` still tells front/back from side doors.
- **Docks may overlap racks** (not checked), but must touch a wall.

**Data structures:**
- Problems: `{ id: message }`.
- Diff: `{ create: [{ tmp_id, vals }], write: [{ id, vals }], delete: [ids] }`.
- `TEMPLATE` (pallet and shelf sizes), `AREA_TYPES` (key, label, colour, width, depth), `EDITABLE`, `AREA_EDITABLE`.
- A dock: `{ x, y, width, depth }` with thickness 1.6 and opening 3 by default.
- Constants: `EPS`, `MIN_AREA_SIZE = 0.5`, `DOCK_THICKNESS = 1.6`, `DEFAULT_DOCK_OPENING = 3`, `MIN_DOCK_OPENING = 2`.

**Watch out:** `nextCode` takes the highest number plus one, so after `P99` it would make `P100`, which does not match the server's two-digit code rule. `layoutProblems` names only the first overlapping row. Dragging an area's right or bottom edge can push it out of the building (it is then flagged, not stopped).

## 32. `static/src/editor/editor_action.js`

**Does:** the Layout Editor screen: shows the floor plan in SVG, lets a manager drag, edit, add and delete rows, areas and docks, and saves everything in one all-or-nothing call.

**Decisions:**
- **Two copies of the data:** `original` (what the server has) and `state.rows` / `state.areas` (what is being edited). `changes` and `dirty` are **worked out by comparing them**, so moving a row away and back is not a change.
- **Nothing reaches the server until Save,** and Save is one call (`wh3d_save_layout`). If it fails, the edits stay on screen and a sticky message explains.
- **Leaving is guarded three ways:** inside Odoo (`beforeLeave`), closing the tab (`beforeUnload`), and switching warehouse (the dropdown snaps back if the user keeps editing).
- **Everything is drawn in metres inside one SVG group,** so zoom and pan only change one transform. Handles are sized `9 ÷ scale` so they stay 9 px on screen.
- **Drags are calculated from the starting position,** not step by step, and count only after 4 px of movement.
- **A field is committed on change, not on each key,** so re-rendering doesn't eat half-typed text.
- **A shelf row is forced to one slot per level** (the server rule).
- **New items get negative temporary ids.** After Save the selection moves to the real id.
- **Delete asks first** and explains what will happen. Palette drops use a custom drag type.
- **Docks jump to the nearest wall** when dragged or nudged.
- **The plan refits when the window resizes,** until the user zooms or pans.

**Data structures:**
- `state`: `view`, `rows`, `areas`, `selectedId`, `selectedAreaId`, `saving`, `warehouseId`.
- Server copy and edit copies: `layout`, `original`, `originalAreas`, `state.rows`, `state.areas`.
- Drags: `drag { x, y, view, moved }`, `itemDrag { list, id, x, y, from, moved }`, `resizeDrag { edge, id }`.
- `changes`: the Save payload (`create`, `write`, `delete`, and `areas`).
- `EDGES`: eight handle positions as fractions. `handles`: `{ edge, x, y }` in metres.
- `nextTmpId`: −1, −2, …

**Watch out:** `drag`, `itemDrag` and `resizeDrag` are plain fields, not reactive state. The editor accepts `0` for counts like bays, but the server refuses it on save. After a successful Save the whole screen is reloaded from the server's reply. `save()` uses `result.created[tmpId]`, a dictionary key, not a list position.

## 33. `static/src/editor/editor_action.xml`

**Does:** the template of the Layout Editor: the SVG floor plan, the toolbar, and the side panel (save bar, palette, selected area, selected row, floor summary).

**Decisions:**
- **Logic and layout are separate files.** The template only reads `state`, getters and methods from `editor_action.js`.
- **Everything is drawn in metres inside one SVG group,** so zoom and pan change one transform. **Outlines use `non-scaling-stroke`,** so they stay thin at any zoom.
- **States are CSS classes** (`o_selected`, `o_invalid`, `o_new`, `o_shelf`), so the style sheet decides how each looks.
- **Accessible:** rows and areas can be reached with Tab, have a role and label, and **their problem message is part of the spoken label**.
- **Resize handles sit outside the area's group,** so grabbing one doesn't also move the area. Docks have no handles.
- **Row codes alternate above and below,** so back-to-back neighbours don't collide.
- **The problem lists are read once** per render (`t-set`) and reused by every item.
- **Save is disabled while there are problems,** nothing to save, or a save running. **Discard** is disabled when there is nothing to discard.
- **"View in 3D" is disabled for an unsaved row or any unsaved change** ("Save first").
- **Fields commit on change,** not on every key. Slots per level is disabled for a shelf.
- **Palette items can be dragged or clicked.**

**Data structures:**
- The template reads `state` (`areas`, `rows`, `selectedId`, `selectedAreaId`, `warehouseId`, `saving`), the getters `transform`, `problems`, `areaProblemMap`, `problemList`, `dirty`, `selectedArea`, `selectedRow`, `handles`, `handleSize`, `areaCount`, `dockCount`, `isEmpty`, and `layout`, `grid`, `warehouses`, `areaTypes`.
- Row fields in the panel: x, y, bays, bay width, depth, levels, level height, slots per level (with steps 0.1 or 1).
- Area fields: x, y, width, depth, colour, name, and the dock's opening.
- State classes: `o_selected`, `o_invalid`, `o_new`, `o_shelf`, `o_major`. Handle classes: `o_h_` plus the edge.
- Page attribute: `data-dirty`.

**Watch out:** the `min` on the number boxes is only a hint for the browser's spinner, and the code ignores values below 0 anyway. `t-key="line_index"` is fine here because the grid never reorders. The look (colours for invalid, new and selected, and the handle cursors) is in the style sheet, not here.

---

## Not covered yet

- `views/stock_location_views.xml`, `views/warehouse_layout_area_views.xml`, `views/product_template_views.xml`
- `demo/` (catalogue, products, layout)
- `static/src/` (the 3D view and the 2D editor in JavaScript), except `editor/geometry.js`, `editor/layout_edit.js`, `editor/editor_action.js`, `editor/editor_action.xml`, `common/warehouse_picker.js` and `.xml` and the `view3d/` files `layout.js`, `occupancy.js`, `live.js`, `walk.js`, `scene.js`, `view3d_action.js` and `view3d_action.xml`
- the rest of `tests/` (all test files except `common.py`, `test_rack_row.py`, `test_location_generator.py`, `test_location_sync.py`, `test_layout_save.py`, `test_scene_data.py` and `test_bus.py`) and `static/tests/`
