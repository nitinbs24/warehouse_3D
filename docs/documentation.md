# How the code works

Notes on how individual files in `warehouse_3d` operate. Entries are added only when asked.

Each file gets one numbered section (`## 1.`, `## 2.`, ...) in the order it was read, with the same sub-headings every time: **How it works** and **Why it's needed**.

## Folder structure

```
warehouse_3d/
├── __init__.py
├── __manifest__.py              module identity, dependencies, load list
├── data/
│   └── res_groups.xml
├── demo/                        sample data, loaded only with demo data
│   ├── catalogue.xml
│   ├── layout.xml
│   └── product.template.csv
├── models/                      Python / ORM
│   ├── __init__.py
│   ├── product_template.py
│   ├── stock_location.py
│   ├── stock_quant.py
│   ├── stock_warehouse.py
│   ├── warehouse_layout_area.py
│   └── warehouse_rack_row.py
├── security/
│   └── ir.model.access.csv
├── views/                       XML views, actions, menus
│   ├── menus.xml
│   ├── product_template_views.xml
│   ├── stock_location_views.xml
│   ├── view3d_actions.xml
│   ├── warehouse_layout_area_views.xml
│   └── warehouse_rack_row_views.xml
├── static/
│   ├── lib/three/               vendored three.js (r128)
│   ├── src/
│   │   ├── common/              shared by editor and 3D view
│   │   │   ├── warehouse_picker.js
│   │   │   └── warehouse_picker.xml
│   │   ├── editor/              2D layout editor
│   │   │   ├── editor_action.js / .scss / .xml
│   │   │   ├── geometry.js
│   │   │   └── layout_edit.js
│   │   └── view3d/              3D view
│   │       ├── view3d_action.js / .scss / .xml
│   │       ├── layout.js
│   │       ├── live.js
│   │       ├── occupancy.js
│   │       ├── scene.js
│   │       └── walk.js
│   └── tests/                   JS unit tests and browser tours
│       ├── editor_geometry.test.js
│       ├── layout_edit.test.js
│       ├── layout.test.js
│       ├── live.test.js
│       ├── occupancy.test.js
│       ├── walk.test.js
│       ├── warehouse_picker.test.js
│       └── tours/
│           ├── smoke_tour.js
│           └── view3d_tour.js
└── tests/                       Python tests
    ├── __init__.py
    ├── common.py
    ├── test_bus.py
    ├── test_inventory_flow.py
    ├── test_js.py
    ├── test_layout_area.py
    ├── test_layout_save.py
    ├── test_location_generator.py
    ├── test_location_lock.py
    ├── test_location_sync.py
    ├── test_rack_row.py
    ├── test_scene_data.py
    ├── test_smoke.py
    ├── test_template.py
    ├── test_view3d.py
    └── test_warehouse_list.py
```

---


## 1. `__manifest__.py`

**`__manifest__.py` is the module's identity card and load list.** Odoo reads it to find, install and wire up the `warehouse_3d` addon. Without it, Odoo doesn't see the folder as a module at all.

### How it works

Odoo scans every addons path for folders that contain `__manifest__.py`. The file is a plain Python dict, and Odoo reads each key like this:

- **Metadata (lines 2–5, 35–36):** `name`, `version`, `summary`, `category`, `author` and `license`. These show up in the Apps list. The version `19.0.x.y.z` means "for Odoo 19".
- **`depends: ['stock', 'bus']` (line 6):**
  - `stock` is the Inventory app. The module extends its warehouses, locations and quants.
  - `bus` is Odoo's websocket notification channel. It is what pushes live stock changes to the 3D view.
  - Odoo installs these first and loads them before this module.
- **`data` (lines 7–16):** files loaded on every install and upgrade, in this order:
  1. Security first (access rules and the user group).
  2. Then views for rack rows, locations, layout areas and products.
  3. Then the 3D view action and the menus. The menus come last because they point at the actions.
- **`demo` (lines 17–21):** sample catalogue, products and a layout. Odoo loads them only on databases created with demo data.
- **`assets` (lines 22–34):** JS/CSS bundles for the web client.
  - `web.assets_backend` holds the real code, split into `common`, `view3d` and `editor`.
  - `web.assets_unit_tests` holds the JS unit tests.
  - `web.assets_tests` holds the browser tours.
- **`installable: True`:** lets Odoo offer the module for install.

### Why it's needed

- **Discovery:** it marks the folder as an Odoo module.
- **Ordering:** `depends` and the `data` order decide what loads when. Getting these wrong gives errors like "model not found" or "action not found" at install.
- **Frontend delivery:** none of the JS (the 3D scene or the layout editor) reaches the browser unless it's listed under `assets`.
- **Testing:** the test bundles are registered here, which is why the tests only run when the module is installed.

If you add a new XML view, CSV or JS folder to the module, you must also list it here. Otherwise it is silently ignored.

---

## 2. `__init__.py` (module root)

**`__init__.py` (module root) is the Python entry point of the addon.** It contains one line: `from . import models`.

### How it works

- Python treats a folder as a package only if it has an `__init__.py`. When Odoo loads `warehouse_3d`, it imports the package, which runs this file.
- `from . import models` means "import the `models` subfolder, which sits next to this file". That runs `models/__init__.py`, which imports each model file in turn:
  - `stock_location`
  - `warehouse_rack_row`
  - `stock_warehouse`
  - `warehouse_layout_area`
  - `product_template`
  - `stock_quant`
- Importing a model file is what registers its classes with Odoo. Each class that uses `_name` or `_inherit` is added to the ORM registry when its file is imported. A model file that nobody imports never takes effect: no table, no fields, no methods.
- Odoo's chain is therefore `__manifest__.py` (find the module) → `__init__.py` (load Python) → `models/__init__.py` (load each model).

### Why it's needed

- **Registration:** a new model file does nothing until it's listed in `models/__init__.py`. Forgetting this is the most common reason an Odoo field or model is "missing".
- **Order:** imports run top to bottom. Here `stock_location` loads first and `stock_quant` last. Order only matters if one model file needs another at import time.
- **Only models are imported here.** The `tests/` folder has its own `__init__.py` and is picked up separately by Odoo's test runner. Views, security and JS are loaded from the manifest, not from Python.

---

## 3. `security/ir.model.access.csv`

**`security/ir.model.access.csv` is the table of who may read, edit, create or delete each custom model.** In Odoo, a new model is invisible to every non-admin user until a row here grants access.

### How it works

Odoo loads the file into the `ir.model.access` model. The manifest lists it first under `data`, ahead of the views. Each row is one permission rule:

| Column | Meaning |
|---|---|
| `id` | Unique XML id for the rule |
| `name` | Human label |
| `model_id:id` | Model it applies to. `model_warehouse_rack_row` is the id Odoo auto-generates from `warehouse.rack.row` |
| `group_id:id` | User group the rule applies to |
| `perm_read/write/create/unlink` | 1 = allowed, 0 = denied |

The four rows cover two models and two groups:

| Model | Inventory User (`stock.group_stock_user`) | Inventory Manager (`stock.group_stock_manager`) |
|---|---|---|
| `warehouse.rack.row` | read only | read, write, create, delete |
| `warehouse.layout.area` | read only | read, write, create, delete |

- **Warehouse staff** can view the layout and the 3D scene.
- **Only managers** can change the layout.
- Rules from several groups add up. A manager is also a user, but the manager row is the one that gives write access.
- If a model has no row at all, Odoo logs a warning and every non-admin user is denied.

### Why it's needed

- Without these rows, the rack-row and layout-area menus, the editor and the 3D view would fail for normal users with an access error.
- It enforces the project's rule that the layout is edited by managers and viewed by everyone else.
- The `stock.location` and `stock.quant` extensions need no rows. Those models already have access rules from the `stock` module.

---

## 4. `data/res_groups.xml`

**`data/res_groups.xml` switches on Inventory's "Storage Locations" setting at install.**

### How it works

- Despite the name, it doesn't define a group. It switches on Inventory's **Storage Locations** setting (`group_stock_multi_locations`) at install.
- Rack rows generate sub-locations, and Odoo hides sub-locations unless that setting is on.
- It goes through `res.config.settings` rather than touching the group directly, so Odoo applies the side effects of the setting. Saving the setting also re-enables the "New" button on Locations and the internal transfer operation type.
- `noupdate="1"` means it runs only at install. If an admin turns the setting off later, upgrading the module won't turn it back on.
- It is loaded second in the manifest, right after the access file.

### Why it's needed

- Without it, the generated rack locations would be hidden in a fresh Inventory database, and the module would look broken until someone found the setting.

---

## 5. `views/view3d_actions.xml`

**`views/view3d_actions.xml` registers the two screens that are built in JavaScript (the 3D view and the layout editor) as Odoo "actions".** Odoo menus can only open actions, so this file is the link between a menu click and the OWL component.

### How it works

The file declares two `ir.actions.client` records. A client action tells the web client "don't load a list or form from the server, run a JavaScript component instead".

| Record id | Menu label | `tag` | Component |
|---|---|---|---|
| `action_wh3d_view3d` | 3D View | `warehouse_3d.view3d` | `View3D` in `view3d_action.js` |
| `action_wh3d_editor` | Layout Editor | `warehouse_3d.editor` | `LayoutEditor` in `editor_action.js` |

- The `tag` is the join key. The end of each JS file has `registry.category("actions").add("warehouse_3d.view3d", View3D)` (and the same for the editor). When the action runs, the web client looks the tag up in that registry and mounts the matching component.
- A typo in the tag gives a "client action not found" error at runtime. Odoo can't check it at install time.

### Why it's needed

- Without these records the JS components exist but nothing can open them. There'd be no menu entry and no URL.
- This is also why the manifest loads this file before `menus.xml`: a menu can't reference an action that doesn't exist yet.
- The actions themselves carry no security. Access is controlled by the `groups` on the menu items and by the server-side access rules. Hiding a menu is not enough on its own.

---

## 6. `views/menus.xml`

**`views/menus.xml` builds the menu entries that let users reach the module's screens.** It defines the Warehouse 3D menus inside the Inventory app and decides who sees each one.

### How it works

Each `<menuitem>` is one entry in the menu tree. The attributes that matter:

- `parent` is the menu it sits under.
- `action` is what opens on click.
- `sequence` is the sort order (lower comes first).
- `groups` limits who can see it.
- An item with no `action` is only a folder that holds children.

The file defines two branches.

**Branch 1: the everyday screens, in the Inventory top bar**

```
Inventory (stock.menu_stock_root)
└── Warehouse 3D            (menu_wh3d_root, seq 4, Inventory Users)
    ├── 3D View             → action_wh3d_view3d   (seq 10, inherits root's group)
    └── Layout Editor       → action_wh3d_editor   (seq 20, Inventory Managers only)
```

**Branch 2: the raw data screens, under Configuration**

```
Inventory → Configuration (stock.menu_stock_config_settings)
└── Warehouse 3D            (menu_wh3d_config, seq 3, Inventory Managers)
    ├── Rack Rows           → action_warehouse_rack_row     (seq 10)
    └── Layout Areas        → action_warehouse_layout_area  (seq 20)
```

- **Visibility inherits downward.** A child menu is hidden if its parent is hidden. So 3D View is visible to Inventory Users because of the root's `groups`. The editor adds a stricter `groups`, so only managers see it.
- **The two JS actions** come from `view3d_actions.xml`, section 5.
- **The two list/form actions** (`action_warehouse_rack_row`, `action_warehouse_layout_area`) are `ir.actions.act_window` records in `warehouse_rack_row_views.xml` and `warehouse_layout_area_views.xml`.
- **The two parents** are `stock.menu_stock_root` and `stock.menu_stock_config_settings`. They are menu ids from Odoo's `stock` module, which is why `stock` is in `depends`.

### Why it's needed

- Without menus, the actions exist but users have no way to open them. This file is the only entry point to the 3D view and editor.
- It puts the module's access rules into the interface: users see the 3D view, and managers see the editor and the data screens. That matches `ir.model.access.csv`.
- Menu `groups` only hide the entry. They don't secure the data. The real protection is the server-side access rules, so a hidden menu is a convenience, not a lock.
- It must load last in `data`. A menu refers to actions by id, and those actions have to exist already (the manifest orders it that way).

---

## 7. `models/warehouse_rack_row.py`

**`models/warehouse_rack_row.py` defines the core model of the whole module.** One `warehouse.rack.row` record is one rack face: its position on the floor plan, how many bays and levels it has, and how big they are. That single record drives two things:

1. The 3D geometry (uprights, beams, slots).
2. The tree of `stock.location` records in Inventory.

Change a number on the row and both follow.

### How it works

#### 1. Fields (lines 30–54)

- **Identity:** `code` (like `P05`), `kind` (pallet rack or shelving), `active`.
- **Ownership:** `warehouse_id`, `company_id` (copied from the warehouse), `location_id` (the parent "zone" location, e.g. `WH/Stock/PR`), `storage_category_id` (used by putaway).
- **Geometry:** `x`, `y` (corner on the floor plan, in metres), `bays`, `bay_width`, `depth`, `levels`, `level_height`, `slots_per_level`.
- **Computed link:** `slot_location_ids` and `slot_count`, which count the generated slot locations pointing back to this row.

#### 2. Database constraints (lines 56–71)

Four `models.Constraint` entries become SQL rules, so even a direct database write can't break them:

- The code is unique within a warehouse.
- Counts are at least 1.
- Sizes are greater than 0.
- `x` and `y` are not negative.

#### 3. Python validation (`@api.constrains`, lines 80–139)

These run on create and write, and raise `ValidationError`:

- `_check_code`: the code must match a capital letter plus two digits.
- `_check_slots_per_level`: shelving rows have exactly 1 slot per level. Pallet rows have at most 26, because positions are lettered A to Z.
- `_check_location_in_warehouse` and `_check_location_internal`: the zone location must be inside the warehouse's stock location and of type Internal. A virtual location would reset `complete_name` and cut the generated paths short.
- `_check_layout`: the floor-plan check.
  - The footprint is `depth` along x and `bays × bay_width` along y (`_wh3d_footprint`).
  - Two rows may touch but not overlap. `EPS` absorbs floating-point error.
  - It also calls helpers on `stock.warehouse` for building bounds and area clashes.
  - The `wh3d_defer_layout_check` context flag skips it, so the editor can check once at the end.

#### 4. Create, write and delete (lines 141–167)

- `create` builds the row, then calls `_sync_locations()` to generate its locations.
- `write` does three things in order:
  1. Refuses to move a row with locations to another warehouse.
  2. Runs `_check_removal` before writing if the change would shrink the tree.
  3. Re-syncs afterwards if a field that matters changed (`SYNC_FIELDS`).
- `unlink` checks stock first. It then archives the locations instead of deleting them, because Inventory history may point at them.

#### 5. Generating the location tree (lines 257–376)

- `_location_tree` computes the wanted nodes as `(key, parent_key, name)`:
  - Pallet: row → bay → level → slot, e.g. `P05`, `P05-03`, `P05-03-2`, `P05-03-2-A`.
  - Shelf: row → bay → slot (no level node), e.g. `S04-10-3`.
  - It accepts pending `vals` so a change can be checked before it happens.
- `_sync_locations` makes the real locations match that tree:
  - It goes parents first (row, bay, level, slot).
  - It creates missing nodes and renames, re-parents or re-activates existing ones.
  - It archives nodes that are no longer wanted.
  - Only slots get the storage category, so "closest location" putaway never picks a bay or level.
- `_locations_to_archive` and `_check_removal` refuse a change if a location it would archive holds, reserves or expects stock. They look at `stock.quant`, `stock.move` and `stock.move.line`.

#### 6. Editor entry point: `wh3d_save_layout` (lines 169–231)

This is the method the 2D layout editor calls to save.

- It applies creates, writes and deletes for rows, and for floor areas and docks, all in one step: all of them or none.
- `clean` refuses any field outside `EDITOR_FIELDS` or `AREA_EDITOR_FIELDS`. `own` refuses records from another warehouse or ones deleted meanwhile.
- A savepoint makes the whole save atomic, even for Python callers that catch the error.
- The overlap check is deferred and run once on the final layout, so moves like swapping two rows work.
- It returns the new ids and the saved layout.

#### 7. Small items

- `action_generate_locations` is the form button. It re-checks and re-syncs.
- `action_view_slots` opens the slot list.
- The module-level constants at the top name the field groups. The comment on line 7 belongs to `SHAPE_FIELDS` on line 9, but `EPS` was inserted between them.

### Why it's needed

It is the single source of truth. Without it you'd edit the 3D scene and the Inventory locations separately and they would drift apart. The guards keep the layout valid (no overlaps, no deleting a location that still holds stock), which is what lets the 3D view trust the data.

---

## 8. `models/warehouse_rack_row.py` — line by line (plain version)

Section 7 gave the overview of this file. This section walks through it again, slowly, in plain words.

**The file in one sentence:** it describes a *rack row* (one line of shelves), checks that the row is valid, and builds the matching Inventory locations from it.

Read the chunks in order. Each chunk builds on the one before.

### Words you will see

| Word | Plain meaning |
|---|---|
| **model / class** | A database table, written as a Python class. `warehouse.rack.row` is the table of rack rows. |
| **record** | One row of that table. One rack face is one record. |
| **field** | One column of the table. |
| **recordset** | A group of records. It can hold 0, 1 or many. |
| **`self`** | Inside a method, the group of records the method was called on. That is why you see `for row in self:`: it goes through them one at a time. |
| **`self.env`** | Your working surroundings: who is logged in, which company, and the way to reach other tables. `self.env['stock.location']` means "the stock.location table". |
| **decorator** (`@api...`) | A label written above a function. It tells Odoo how to treat that function. |
| **domain** | A filter written as a list. `[('active', '=', True)]` means "only active records". |
| **constraint** | A rule that stops bad data from being saved. |
| **`super()`** | Call the original version of the method that this class replaces. Same idea as calling the base class function in C++. |
| **tuple** | A small fixed bundle of values, like `(a, b, c)`. Think of a tiny struct. |

---

### Chunk 1: lines 1–72 (setup and fields)

This chunk only *declares* things. Nothing runs yet.

#### Lines 1–4: imports

```python
import re
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
```

This works like `#include`.

- `re` gives you regular expressions (pattern matching on text).
- `models` is for making tables. `fields` is for column types. `api` is for the labels (decorators) above methods.
- `UserError` and `ValidationError` show a message box to the user and cancel the save.
- VS Code underlined the `odoo` imports earlier. That was only the editor not finding Odoo. The code itself is fine.

#### Lines 6–15: constants

```python
CODE_RE = re.compile(r'^[A-Z]\d{2}$')
```
The pattern for a valid row code: one capital letter, then exactly two digits. `P05` passes. `p5` and `P005` fail.

```python
EPS = 1e-6
```
A tiny number: 0.000001 metres. Computers store decimals a little off, so when we compare positions we allow this tiny gap.

```python
SHAPE_FIELDS = frozenset({'code', 'kind', 'bays', 'levels', 'slots_per_level'})
```
The names of the fields that decide **which locations exist** and what they are called.
- Change `bays` from 7 to 8 and a new bay appears. That is a shape change.
- Change `x` and nothing is added or removed. That is not a shape change.
- A `frozenset` is a list of names that cannot be changed and is fast to look things up in.

```python
SYNC_FIELDS = SHAPE_FIELDS | {'location_id', 'storage_category_id', 'active'}
```
`|` joins two sets. If any of these fields change, the locations must be refreshed.

```python
EDITOR_FIELDS = frozenset({...})
AREA_EDITOR_FIELDS = frozenset({...})
```
The only fields the 2D editor is allowed to change. Anything else is refused. This stops the editor from changing things like the warehouse.

*(The comment on line 7 describes `SHAPE_FIELDS`, but `EPS` got placed between them. It is only a layout quirk.)*

#### Lines 18–20: `node_key`

```python
def node_key(loc):
    return (loc.wh3d_node, loc.wh3d_bay, loc.wh3d_level, loc.wh3d_position)
```

Every generated location carries four labels:
1. its **type**: `row`, `bay`, `level` or `slot`
2. its bay number
3. its level number
4. its position

This function bundles them into one tuple. Later the code uses that bundle as a name tag, to match "a location we want" with "a location that already exists".

The `wh3d_*` fields are added to locations in `stock_location.py`.

#### Lines 23–28: the class

```python
class WarehouseRackRow(models.Model):
    _name = 'warehouse.rack.row'
    _description = 'Rack Row'
    _order = 'warehouse_id, code'
    _rec_name = 'code'
```

- Inheriting from `models.Model` turns this class into a database table. `_name` gives the table its name (dots become underscores: `warehouse_rack_row`).
- `_order` is the default sort: by warehouse, then by code.
- `_rec_name = 'code'` means a row appears as its code (for example `P05`) in dropdowns and links.
- The text on line 24 is the class comment: the row's numbers drive both the 3D shape and the locations.

#### Lines 30–42: identity and ownership fields

Each line `name = fields.Something(...)` adds one column.

- `code`: text, required. `help` is the tooltip shown in the screen.
- `kind`: a dropdown with two choices, `pallet` (shown as "Pallet rack") and `shelf` (shown as "Shelving"). Default is `pallet`.
- `active`: yes/no, default yes. This is Odoo's built-in archive switch. An inactive record is hidden from normal searches but still exists.
- `warehouse_id`: a link to a warehouse. This is a **Many2one**: many rows can point to one warehouse.
  - `required=True`: a row must have a warehouse.
  - `ondelete='cascade'`: if the warehouse is deleted, its rows are deleted too.
  - `default=lambda self: ...`: a tiny inline function that runs when you create a row. It picks the first warehouse of your current company.
- `company_id`: copied automatically from the warehouse. `store=True` saves the copy in the table so it can be filtered on.
- `location_id`: a link to a stock location, called the **zone**. It is the parent of everything this row generates (for example `WH/Stock/PR`).
  - `ondelete='restrict'`: you can't delete a location while a row still uses it.
  - `domain=...`: filters the dropdown to internal locations of this warehouse. This only filters what you *see*. The real rule is `_check_location_internal` on line 132.
- `storage_category_id`: a link to a storage category. It is copied onto every slot so putaway can use it.

#### Lines 44–52: shape and size fields

- `x`, `y`: where the row's corner is on the floor plan, in metres. `digits=(6, 2)` means up to 6 digits, 2 after the decimal point. `string='X (m)'` is the label on screen.
- `bays`, `levels`, `slots_per_level`: whole numbers. Defaults 7, 5 and 2 (the template warehouse).
- `bay_width` (2.7), `depth` (1.1), `level_height` (1.8): sizes in metres.

#### Lines 53–54: link back to the locations

```python
slot_location_ids = fields.One2many('stock.location', 'wh3d_rack_row_id', domain=[('wh3d_node', '=', 'slot')])
slot_count = fields.Integer(compute='_compute_slot_count')
```

- `One2many` is the reverse of Many2one. It means "all stock.location records whose `wh3d_rack_row_id` points to me". It is not a column. It is a live lookup. The domain keeps only the `slot` locations.
- `compute='_compute_slot_count'` means "don't store this number, calculate it with that method".

#### Lines 56–71: database rules

```python
_code_warehouse_uniq = models.Constraint('UNIQUE(warehouse_id, code)', 'A rack row code must be unique within a warehouse.')
```

Each `models.Constraint(rule, message)` becomes a rule inside the database itself. There are four:

1. The code must be unique within one warehouse.
2. Bays, levels and slots must be at least 1.
3. Bay width, depth and level height must be above 0.
4. `x` and `y` can't be negative.

Because they live in the database, even a script that skips Odoo's own checks can't break them.

#### Chunk 1 in short

- Lines 1–20: tools, plus lists of field names.
- Lines 23–54: the table's columns.
- Lines 56–71: rules the database enforces.

---

### Chunk 2: lines 73–139 (counting and checking)

#### Lines 73–78: `_compute_slot_count`

```python
@api.depends('slot_location_ids')
def _compute_slot_count(self):
    counts = dict(self.env['stock.location']._read_group(
        [('wh3d_rack_row_id', 'in', self.ids), ('wh3d_node', '=', 'slot')], ['wh3d_rack_row_id'], ['__count']))
    for row in self:
        row.slot_count = counts.get(row, 0)
```

**What it does:** works out how many slots each row has, for the `slot_count` field.

- `@api.depends('slot_location_ids')`: "recalculate whenever `slot_location_ids` changes".
- `_read_group(...)` asks the database one question: "for these rows, how many slot locations does each have?" It is like SQL `GROUP BY` with a count.
- It returns pairs of (row, count). `dict(...)` turns them into `{row: count}`.
- The loop writes each row's count. `counts.get(row, 0)` gives 0 when the row isn't in the result.
- Why one grouped question? Asking once per row would be slow when there are many rows.

#### Lines 80–85: `_check_code`

```python
@api.constrains('code')
def _check_code(self):
    for row in self:
        if not CODE_RE.match(row.code or ''):
            raise ValidationError(...)
```

- `@api.constrains('code')`: "run this check whenever a record is saved with a new `code`".
- `CODE_RE.match(...)` tests the code against the pattern from line 6.
- `row.code or ''` handles an empty code safely.
- `raise ValidationError(...)` cancels the save and shows the message.
- `self.env._("... %(code)s ...", code=row.code)` is Odoo's translation function. `%(code)s` is a blank that is filled by `code=row.code`.

#### Lines 87–94: `_check_slots_per_level`

- A shelf must have exactly 1 slot per level.
- Any row may have at most 26 slots per level, because positions are named `A` to `Z`.
- It runs when `kind` or `slots_per_level` changes.

#### Lines 96–103: `_check_location_in_warehouse`

```python
stock = row.warehouse_id.lot_stock_id
if not row.location_id.search_count([('id', '=', row.location_id.id), ('id', 'child_of', stock.id)]):
    raise ValidationError(...)
```

- `lot_stock_id` is the warehouse's main stock location, for example `WH/Stock`.
- `child_of` means "this one, or anything inside it".
- `search_count` counts matches. A count of 0 means the zone is **not** inside the warehouse's stock location, so it raises an error.

#### Lines 105–108: `_wh3d_footprint`

```python
def _wh3d_footprint(self):
    self.ensure_one()
    return self.x, self.y, self.x + self.depth, self.y + self.bays * self.bay_width
```

- `ensure_one()` makes sure `self` is exactly one record.
- It returns the rectangle the row covers on the floor: `(x0, y0, x1, y1)`.
- The depth goes along x. The bays go along y, so that side is `bays × bay_width` long.

#### Lines 110–130: `_check_layout`

This check makes sure rows fit in the building and don't overlap. It runs when position, size, warehouse or `active` changes.

```python
if self.env.context.get('wh3d_defer_layout_check'):
    return
```
`context` is a dictionary of flags passed along. If this flag is on, skip the check. The editor turns it on while saving and checks once at the end. That is why swapping two rows works.

```python
self.env['stock.warehouse']._check_wh3d_contains(self)
```
Checks the rows are inside the building. That helper lives in `stock_warehouse.py`.

```python
for row in self.filtered('active'):
    x0, y0, x1, y1 = row._wh3d_footprint()
    others = self.search([('warehouse_id', '=', row.warehouse_id.id), ('id', '!=', row.id)])
```
- `filtered('active')` keeps only active rows.
- The four numbers are unpacked into four variables.
- `others` are the other rows in the same warehouse. Archived rows don't show up in a normal search, so they never block anything.

```python
for other in others:
    ox0, oy0, ox1, oy1 = other._wh3d_footprint()
    if x0 < ox1 - EPS and ox0 < x1 - EPS and y0 < oy1 - EPS and oy0 < y1 - EPS:
        raise ValidationError(...)
```
The standard test for two overlapping rectangles: they overlap if they overlap left-right **and** up-down. Taking off `EPS` means rows that only *touch* (back to back) are allowed. Only a real overlap is an error.

```python
self.env['stock.warehouse']._check_wh3d_areas_clear_of_rows(...)
```
Last, check that no floor area (receiving, shipping and so on) sits on top of a row. That helper is also in `stock_warehouse.py`.

#### Lines 132–139: `_check_location_internal`

The zone must be of type **Internal**. A Virtual location would restart the location path and cut every generated name short (the comment on line 134). This is the real rule behind the dropdown filter on line 39.

#### Chunk 2 in short

- `_compute_slot_count` counts slots with one grouped question.
- The other methods are guards: valid code, sensible slots, zone inside the warehouse and Internal, no overlaps, nothing outside the building.
- Still nothing creates locations. That starts in chunk 3.

---

### Chunk 3: lines 141–167 (`create`, `write`, `unlink`)

`create`, `write` and `unlink` already exist on every Odoo model. Writing them again here is like overriding a virtual function in C++. `super()` calls the original, which does the real database work. This class adds its own steps before or after.

#### Lines 141–145: `create` (making new rows)

```python
@api.model_create_multi
def create(self, vals_list):
    rows = super().create(vals_list)
    rows._sync_locations()
    return rows
```

- `@api.model_create_multi`: `create` receives a **list** of dictionaries, one per new row.
- `super().create(vals_list)` saves the rows. The checks from chunk 2 run here, so a bad row stops before the next line.
- `rows._sync_locations()` builds the locations for the new rows (line 329).
- It returns the new rows.

#### Lines 147–160: `write` (editing rows)

`vals` is a dictionary of what is being changed, for example `{'bays': 8}`.

```python
if 'warehouse_id' in vals and self.filtered(lambda r: r.warehouse_id.id != vals['warehouse_id'])._nodes():
    raise UserError(...)
```
- `lambda r: ...` is a small inline function.
- Meaning: "if you are moving a row to a *different* warehouse and it already has locations, refuse". Locations can't change company, and a row's locations belong to its warehouse.

```python
if SHAPE_FIELDS.intersection(vals) or ('active' in vals and not vals['active']):
    for row in self:
        row._check_removal(vals)
```
- `SHAPE_FIELDS.intersection(vals)` finds names that appear in both. Any match counts as true.
- Meaning: "if this edit changes the shape, or archives the row, first check it won't remove a location that holds stock" (`_check_removal`, line 308).
- It runs **before** saving so a refused edit changes nothing.

```python
res = super().write(vals)
if SYNC_FIELDS.intersection(vals):
    self._sync_locations()
return res
```
- Save the change. The checks from chunk 2 run here.
- If a field that affects locations changed, update the locations. Changing only `x` or `depth` does not.

#### Lines 162–167: `unlink` (deleting rows)

```python
def unlink(self):
    for row in self:
        row._check_removal({'active': False})
    self._nodes().write({'active': False})
    return super().unlink()
```

1. For the stock check, deleting a row counts the same as archiving it. If any of its locations hold stock, stop.
2. The row's locations are **archived**, not deleted. Inventory history may point at them, and deleting them would break that history.
3. Then the row itself is deleted.

#### Chunk 3 in short

All three methods follow one pattern:
1. **Check** first.
2. **Do** the real work with `super()`.
3. **Update** the locations.

---

### Chunk 4: lines 169–255 (saving from the editor, plus two buttons)

#### Lines 169–179: `wh3d_save_layout` — what it receives

```python
@api.model
def wh3d_save_layout(self, warehouse_id, changes):
```

- `@api.model`: works on the table as a whole, not on particular rows. The 2D editor calls it from the browser.
- `changes` is a dictionary with three lists:
  - `create`: new rows, each as `{tmp_id, vals}`
  - `write`: edited rows, each as `{id, vals}`
  - `delete`: ids to remove
  - plus an `areas` entry with the same three lists, for floor areas and docks.
- The promise in the docstring: **all of it saves, or none of it does**.

#### Lines 180–182: find the warehouse

```python
warehouse = self.env['stock.warehouse'].browse(warehouse_id).exists()
if not warehouse:
    raise UserError(...)
```
`browse(id)` gets the record for an id. `.exists()` drops it if it has been deleted. If nothing is left, show an error.

#### Lines 184–198: two helper functions

A function written inside another function can use the outer variables (`self`, `warehouse`).

```python
def clean(vals, allowed=EDITOR_FIELDS):
    refused = set(vals) - allowed
    if refused:
        raise UserError(...)
    return dict(vals)
```
- `set(vals) - allowed` leaves the fields the editor is **not** allowed to touch.
- If there are any, refuse and list them.
- `dict(vals)` returns a copy, so the original isn't changed.

```python
def own(ids, model=self):
    records = model.browse(ids).exists()
    if len(records) != len(set(ids)) or records.filtered(lambda r: r.warehouse_id != warehouse):
        raise UserError(...)
    return records
```
- Loads the records for the ids and checks two things:
  1. none have been deleted in the meantime;
  2. all of them belong to **this** warehouse.
- This stops a made-up request from editing another warehouse's rows.

#### Lines 200–202: setup

```python
deferred = {'wh3d_defer_layout_check': True}
created, created_areas = {}, {}
area_changes = changes.get('areas', {})
```
- `deferred` is the flag that tells `_check_layout` to wait (line 112).
- Two empty dictionaries will hold "temporary id → real id".
- `changes.get('areas', {})` reads the areas part, or an empty one if missing.

#### Lines 203–230: the work, inside a safety net

```python
with self.env.cr.savepoint():
```
A **savepoint** is a bookmark in the database. If an error happens inside this block, everything goes back to the bookmark and none of the edits stay. The comment on line 203 notes this holds even if a caller catches the error.

**Step 1: deletes first (line 205)**
```python
own(changes.get('delete', [])).unlink()
```
Check the ids belong here, then delete them. Deleting first frees floor space. The stock check from chunk 3 still runs.

**Step 2: edits (lines 206–210)**
```python
touched = self.browse()
for change in changes.get('write', []):
    row = own([change['id']])
    row.with_context(**deferred).write(clean(change['vals']))
    touched |= row
```
- `self.browse()` with nothing inside is an empty group. `|=` adds records to it.
- `with_context(**deferred)` adds the "wait" flag for this one write. `**` spreads the dictionary into named arguments.
- The overlap check is held back, but the other checks and the location update still run.

**Step 3: creates (lines 211–217)**
```python
vals = clean(change['vals'])
vals.update(warehouse_id=warehouse.id,
            location_id=self._wh3d_default_zone(warehouse, vals.get('kind', 'pallet')).id)
row = self.with_context(**deferred).create(vals)
created[change['tmp_id']] = row.id
```
- The editor never sends the warehouse or the zone. The server fills them in.
- A `tmp_id` is a temporary id the browser gives to a row it hasn't saved yet. The server records which real id it got, so the browser can swap them.

**Step 4: areas (lines 218–228)**
The same three steps (delete, edit, create) for floor areas and docks.

**Step 5: check once at the end (lines 229–230)**
```python
self.browse(touched.ids)._check_layout()
Area.browse(touched_areas.ids)._check_layout()
```
Now that every edit is in, check the *final* layout once. The messy middle state (two rows overlapping while being swapped) is never checked. If a check fails, the savepoint undoes everything.

#### Line 231: what it sends back

```python
return {'created': created, 'created_areas': created_areas, 'layout': warehouse.wh3d_get_layout()}
```
The real ids for the new things, and a fresh copy of the floor plan (`wh3d_get_layout()` is in `stock_warehouse.py`).

#### Lines 233–237: `_wh3d_default_zone`

```python
sibling = self.search([('warehouse_id', '=', warehouse.id), ('kind', '=', kind)], limit=1)
return sibling.location_id or warehouse.lot_stock_id
```
Picks the zone for a row you just drew: the zone of another row of the same kind, or else the warehouse's main stock location. `or` works because an empty result counts as "false".

#### Lines 239–244: `action_generate_locations`

```python
def action_generate_locations(self):
    for row in self:
        row._check_removal({})
    self._sync_locations()
    return True
```
- Names starting with `action_` are the methods that buttons call.
- `_check_removal({})` with nothing changed asks: "if I rebuild the locations exactly as wanted, would any extra location (made by an import or a script) be archived?" If one of them holds stock, it refuses.
- Then it rebuilds the locations.

#### Lines 246–255: `action_view_slots`

```python
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
```
- A button method can return a dictionary that tells the browser "open this next".
- This one opens a list of `stock.location` records, filtered to this row's slots.
- `'create': False` hides the "New" button. Slots are generated, not made by hand.

#### Chunk 4 in short

- `wh3d_save_layout` is the one door the editor uses to save. It limits the allowed fields, checks ownership, applies deletes, edits and creates, checks the layout once, and undoes everything if anything fails.
- The last three methods are a default-zone helper and two buttons.

---

### Chunk 5: lines 257–327 (working out what locations are wanted)

This chunk contains the helper methods. It answers: *which locations should exist, which exist now, and is it safe to remove some?*

#### Lines 257–278: `_location_tree`

**What it does:** builds a to-do list of every location the row *should* have. Each entry is `(key, parent_key, name)`. Parents always come before their children.

```python
self.ensure_one()
shape = {f: self[f] for f in SHAPE_FIELDS} | {f: v for f, v in (vals or {}).items() if f in SHAPE_FIELDS}
code, kind = shape['code'], shape['kind']
```
- It takes the row's five shape values into a dictionary.
- Then it lays any pending changes (`vals`) over the top. `|` joins two dictionaries, and the right side wins.
- Why `vals`? So a change can be tested ("what would the tree look like if I changed `bays` to 5?") before it is saved.

```python
row_key = ('row', 0, 0, 0)
tree = [(row_key, None, code)]
```
First entry: the row itself. It has no parent, and its name is the code (for example `P05`).

```python
for b in range(1, shape['bays'] + 1):
    tree.append((('bay', b, 0, 0), row_key, f'{code}-{b:02d}'))
```
One entry for every bay: `P05-01`, `P05-02` and so on. `{b:02d}` means "pad the number to two digits".

```python
for b in range(1, shape['bays'] + 1):
    for lvl in range(1, shape['levels'] + 1):
        parent = ('bay', b, 0, 0)
        if kind == 'pallet':
            parent = ('level', b, lvl, 0)
            tree.append((parent, ('bay', b, 0, 0), f'{code}-{b:02d}-{lvl}'))
        for p in range(1, shape['slots_per_level'] + 1):
            name = f'{code}-{b:02d}-{lvl}-{chr(64 + p)}' if kind == 'pallet' else f'{code}-{b:02d}-{lvl}'
            tree.append((('slot', b, lvl, p), parent, name))
```
- For every bay and every level it first sets `parent` to the bay.
- **Pallet racks** get an extra *level* node (`P05-03-2`), and that level becomes the parent of the slots.
- **Shelves** skip the level node. Their slots hang straight under the bay.
- Slot names: pallet `P05-03-2-A` (`chr(64 + p)` turns 1 into `A`, 2 into `B`), shelf `S04-10-3`.

Example with the template numbers (7 bays, 5 levels, 2 slots):
`1 row + 7 bays + 35 levels + 70 slots = 113 locations`.

#### Lines 280–284: `_nodes`

```python
def _nodes(self, include_archived=False):
    domain = [('wh3d_rack_row_id', 'in', self.ids)]
    if not include_archived:
        domain.append(('active', '=', True))
    return self.env['stock.location'].with_context(active_test=False).search(domain)
```
Returns the locations that currently belong to these rows.
- `active_test=False` turns off Odoo's automatic hiding of archived records, so the search *can* see them.
- If you don't ask for archived ones, the code adds `active = True` back.

#### Lines 286–288: `_nodes_by_key`

```python
return {node_key(loc): loc for loc in self._nodes(include_archived=True)}
```
A lookup table: **key → existing location**, archived ones included. It lets the code find "the location that matches this wanted entry", and bring an archived one back if needed.

#### Lines 290–306: `_locations_to_archive`

**What it does:** answers "if I apply `vals`, which active locations would end up archived?" That includes hand-made locations under them.

```python
archiving_row = 'active' in vals and not vals['active']
wanted = set() if archiving_row else {key for key, _parent, _name in self._location_tree(vals)}
nodes = self._nodes()
removed = nodes.filtered(lambda loc: node_key(loc) not in wanted)
```
- If the whole row is being archived, nothing is wanted.
- Otherwise `wanted` is the set of keys in the new tree (`_parent` and `_name` are ignored, which the leading underscore signals).
- `removed` are the existing locations the new tree no longer wants. For example, going from 7 bays to 5 removes bays 6 and 7 and everything inside them.

```python
if not removed:
    return Location
below_removed = Location.search([('id', 'child_of', removed.ids)])
surviving = below_removed & (nodes - removed)
return below_removed - Location.search([('id', 'child_of', surviving.ids)])
```
- Nothing removed means nothing to archive. (`Location` here is an empty group of locations.)
- `below_removed` is everything inside the removed ones, including hand-made locations.
- `surviving` is the generated locations that are *still wanted* but happen to sit under a removed one. They get moved to a new parent instead of archived. `&` means "in both", `-` means "in the first but not the second".
- The result is: everything under the removed ones, **minus** the survivors and whatever is under them.

#### Lines 308–327: `_check_removal`

**What it does:** refuses a change if it would archive a location that holds, reserves or still expects stock.

```python
locations = self._locations_to_archive(vals)
if not locations:
    return
```
Work out what would be archived. If nothing, there's nothing to check.

```python
busy = self.env['stock.quant'].search([
    ('location_id', 'in', ids), '|', ('quantity', '!=', 0), ('reserved_quantity', '!=', 0),
]).location_id
```
- Looks for stock records (`stock.quant`) in those locations with a quantity or a reservation.
- In a domain, `'|'` means "or" and applies to the next two conditions. So this is "in those locations **and** (quantity not 0 **or** reserved not 0)".
- `.location_id` takes the locations those records sit in.

```python
for model in ('stock.move', 'stock.move.line'):
    busy |= self.env[model].search([
        ('state', 'not in', ('done', 'cancel')), '|', ('location_id', 'in', ids), ('location_dest_id', 'in', ids),
    ]).mapped(lambda m: (m.location_id | m.location_dest_id) & locations)
```
- Looks at stock moves that are **not finished** and start or end in those locations (stock is on its way in or out).
- `.mapped(...)` runs a small function on each move. For each move, it takes its source and destination, and keeps only the ones in `locations`.
- `busy |= ...` adds them to the busy group.

```python
if busy:
    names = sorted(busy.mapped('name'))
    shown = ', '.join(names[:10]) + (self.env._(" and %s more", len(names) - 10) if len(names) > 10 else '')
    raise UserError(...)
```
If anything is busy, show up to 10 names (and "and N more"), then refuse with "move the stock out (or cancel the transfers) first".

#### Chunk 5 in short

- `_location_tree`: **what should exist**.
- `_nodes` and `_nodes_by_key`: **what exists now**.
- `_locations_to_archive`: **what would go away**.
- `_check_removal`: **is it safe to let it go**.

---

### Chunk 6: lines 329–376 (`_sync_locations`)

This is the method that makes the real locations match the wanted list. Everything else in the file feeds into it.

```python
def _sync_locations(self):
    Location = self.env['stock.location'].with_context(active_test=False)
    for row in self:
```
`Location` is the locations table, with archived records visible. Then it handles each row.

The docstring says: it creates missing nodes, renames, re-parents and re-activates existing ones, and archives nodes no longer wanted. **The caller must run `_check_removal` first.** This method itself does no stock check.

#### Lines 337–339: inactive rows

```python
if not row.active:
    row._nodes().write({'active': False})
    continue
```
If the row is archived, archive its locations too, then move on to the next row (`continue`).

#### Lines 340–341: get ready

```python
by_key = row._nodes_by_key()
tree = row._location_tree()
```
`by_key` is what exists (archived included). `tree` is what is wanted.

#### Lines 343–372: one layer at a time

```python
for depth in ('row', 'bay', 'level', 'slot'):
    missing = []
    for key, parent, name in tree:
        if key[0] != depth:
            continue
```
It works through the tree **one layer at a time**: rows, then bays, then levels, then slots. A child can only be made once its parent exists, so parents always go first. `key[0]` is the node type, so this skips entries from other layers.

```python
vals = {
    'name': name,
    'location_id': by_key[parent].id if parent else row.location_id.id,
    'storage_category_id': row.storage_category_id.id if depth == 'slot' else False,
}
```
What the location should look like:
- its name,
- its parent: the parent location from the tree, or for the top node, the zone,
- its storage category: **only slots** get it, so "closest location" putaway never picks a bay or level.

```python
loc = by_key.get(key)
if not loc:
    missing.append((key, vals))
    continue
```
Look for an existing location with this key. If there isn't one, remember it as *missing* and move on.

```python
current = {'name': loc.name, 'location_id': loc.location_id.id,
           'storage_category_id': loc.storage_category_id.id}
changed = {f: v for f, v in vals.items() if current[f] != v}
if not loc.active:
    changed['active'] = True
if changed:
    loc.with_context(wh3d_sync=True).write(changed)
```
If it exists, compare what it is now (`current`) with what it should be (`vals`). Keep only the differences (`changed`). If it is archived, switch it back on. If anything changed, write it.

`wh3d_sync=True` is a flag passed along with the write. Generated locations are locked against hand editing. This flag most likely lets this code through that lock (the lock is in `stock_location.py`).

```python
if missing:
    created = Location.create([vals | {
        'usage': 'internal',
        'company_id': row.company_id.id,
        'wh3d_rack_row_id': row.id,
        'wh3d_node': key[0], 'wh3d_bay': key[1], 'wh3d_level': key[2], 'wh3d_position': key[3],
    } for key, vals in missing])
    by_key.update(zip((key for key, _v in missing), created))
```
- It creates all the missing locations of this layer in one go. Each is the earlier `vals` plus: type Internal, the company, the link back to this row, and its four labels.
- `by_key.update(zip(...))` adds the new locations to the lookup table. `zip` pairs each key with its new location. That way the next layer can find its parents.

#### Lines 373–376: archive what is left over

```python
wanted = {key for key, _p, _n in tree}
obsolete = Location.browse([loc.id for key, loc in by_key.items() if key not in wanted and loc.active])
obsolete.write({'active': False})
```
After everything is created and fixed, archive the existing locations that are active but no longer wanted. The comment explains why this is last: bringing a parent back to life also brings its children back, so archiving has to come after that.

#### Chunk 6 in short

For each row: work out what is wanted, compare with what exists, and then **create** what is missing, **fix** what is different, and **archive** what is not wanted. It goes one layer at a time, from the row down to the slots.

---

### How it all fits together

```
Editor presses Save
      │
      ▼
wh3d_save_layout          (chunk 4)  checks fields and ownership
      │  calls create / write / unlink for each change
      ▼
create / write / unlink   (chunk 3)  _check_removal first, then super()
      │  the checks run while saving
      ▼
@api.constrains checks    (chunk 2)  code, slots, zone, overlap
      │
      ▼
_sync_locations           (chunk 6)  builds, fixes and archives locations
      │  asks
      ▼
_location_tree, _nodes    (chunk 5)  what is wanted vs what exists
```

The fields at the top (chunk 1) are the data that every step above reads.

---

## 9. `models/stock_location.py`

**The file in one sentence:** it adds the rack-row fields to Odoo's own `stock.location` table, and locks generated locations so they can't be edited by hand.

It also explains two things from section 8: where the `wh3d_*` fields come from, and what the `wh3d_sync` flag does.

### Lines 1–5: setup

```python
from odoo import fields, models
from odoo.exceptions import UserError

LOCKED_FIELDS = ('name', 'location_id', 'usage')
```

- Same kind of imports as before. This file needs `fields` and `models`, but not `api`.
- `LOCKED_FIELDS` is the list of fields that must not be changed on a generated location: its name, its parent, and its type.
- The comment says it: these are owned by the rack row. Change the row, not the location. Only `_sync_locations` may write them.

### Lines 8–9: extending a table that already exists

```python
class StockLocation(models.Model):
    _inherit = 'stock.location'
```

- In section 8, `_name = 'warehouse.rack.row'` created a **new** table.
- `_inherit = 'stock.location'` with no `_name` means "reopen the existing `stock.location` table and add to it". It is a bit like adding members to a class you didn't write. Everything Odoo's Inventory already does with locations keeps working.
- That is how this module puts its own fields and rules into Inventory.

### Lines 11–19: five new fields on every location

| Field | Meaning |
|---|---|
| `wh3d_rack_row_id` | Which rack row generated this location |
| `wh3d_node` | The kind of location: `row`, `bay`, `level` or `slot` |
| `wh3d_bay` | The bay number |
| `wh3d_level` | The level number |
| `wh3d_position` | The position number in the level |

These are the four labels that `node_key()` bundles in `warehouse_rack_row.py`, plus the link to the row.

- Ordinary Inventory locations leave all of them empty.
- **`copy=False`** on every field means that duplicating a location gives a plain one. It never makes a second claim on the same rack slot (see the comment on line 12).
- On `wh3d_rack_row_id`:
  - It's a link to the row (a Many2one).
  - `index='btree_not_null'` creates a database index that skips empty values. Most locations have no row, so this keeps the index small and still makes "find this row's locations" fast.
  - `ondelete='set null'` means that if a row is deleted, the location stays and only the link is cleared. It does not delete the location.

### Lines 21–30: the lock, in `write`

```python
def write(self, vals):
    if not self.env.context.get('wh3d_sync') and any(f in vals for f in LOCKED_FIELDS):
```

- This replaces `write` for locations, so it runs on every edit to any location. The condition means: "this is **not** the rack row doing the edit, **and** the edit touches a locked field".
- `wh3d_sync` is the flag `_sync_locations` passes in `with_context(wh3d_sync=True)`. It means "this edit comes from the rack row's own code". So it lets that code through the lock.
- `any(f in vals for f in LOCKED_FIELDS)` is true if at least one locked name appears in the edit.

```python
for loc in self.filtered('wh3d_rack_row_id'):
    current = {'name': loc.name, 'location_id': loc.location_id.id, 'usage': loc.usage}
    if any(f in vals and vals[f] != current[f] for f in LOCKED_FIELDS):
        raise UserError(...)
```

- `filtered('wh3d_rack_row_id')` keeps only locations that came from a row. Plain locations are not affected at all.
- `current` holds the location's values right now.
- The test is "is a locked field in this edit **and** is the new value different from the current one?" Saving the same value again is allowed. Only a real change is refused.
- If so, it raises an error that tells the user to change the rack row instead, and shows where: Inventory ▸ Configuration ▸ Warehouse 3D ▸ Rack Rows.

```python
return super().write(vals)
```
Otherwise it continues with the normal save.

### Why it's needed

- **Single source of truth:** the rack row generates the locations. If someone renamed a generated location by hand, the next `_sync_locations` would see a mismatch and change it back, or get confused. The lock prevents the conflict up front.
- **A bypass that stays private:** the context flag is how the row's own code gets past the lock. Ordinary users and other code never set it.
- **Archiving still works:** `active` is not in `LOCKED_FIELDS`. That is why the row's `unlink` and `_sync_locations` can archive locations with a plain `write({'active': False})`, with no flag.
- **Not locked:** `storage_category_id` isn't in the list. The row writes it on every slot at sync time, but nothing in this file stops a hand edit.

### One consequence to know

When a row is deleted, its `unlink` archives the locations first. Then the `set null` rule clears their `wh3d_rack_row_id` link. After that they are archived plain locations with no row behind them. (Worked out by reading the two files together, not by running it.)

---

## 10. `models/warehouse_layout_area.py`

**The file in one sentence:** it describes a flat shape drawn on the floor plan, either a floor area (receiving, packing, shipping) or a dock door, and checks that the shape is valid.

Unlike a rack row, an area holds no stock and creates no locations. It exists only so the 3D view and the editor can draw it.

### Lines 1–7: setup

```python
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError

COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
EPS = 1e-6
```

- Same tools as in section 8: `re` for text patterns, `api`, `fields` and `models` from Odoo.
- Only `ValidationError` is imported here. This file has no `UserError`.
- `COLOR_RE` is the pattern for a valid colour: a `#`, then exactly six hex characters (0–9, a–f). `#c3d0dc` passes. `red` and `#fff` fail.
- `EPS` is the same tiny number as in the rack row file: 0.000001 metres. It lets us compare positions without trouble from rounding. It is defined again here, not shared.

### Lines 10–14: the class

```python
class WarehouseLayoutArea(models.Model):
    _name = 'warehouse.layout.area'
    _description = 'Layout Area'
    _order = 'warehouse_id, kind, name'
```

- `_name` makes a **new table**, `warehouse_layout_area`.
- `_order` sorts by warehouse, then kind, then name.
- The class comment on line 11 says what it is: a floor area or a dock door drawn on the floor plan, and it holds no stock.

### Lines 16–27: fields

- `name`: text, required. For example "Receiving".
- `kind`: a dropdown with two choices: `area` ("Floor area") and `dock` ("Dock door"). Default is `area`.
- `warehouse_id`: a link to the warehouse. It is set up exactly like the one in the rack row file: required, deleted along with the warehouse (`cascade`), and by default the first warehouse of the current company.
- `company_id`: copied from the warehouse and saved in the table (`store=True`).
- `x`, `y`: the corner of the shape on the floor plan, in metres.
- `width`, `depth`: the size, in metres.
  - `width` runs along **x**.
  - `depth` runs along **y**.
- `color`: text, required, default `#c3d0dc`. It is the floor colour in the 3D view.

**Watch the axes.** A rack row's `depth` runs along x, and its bays run along y. An area is the other way round: its `width` runs along x and its `depth` runs along y. The comment on line 22 says both use the same axes, with x along the length of the building. Only the names of the sides differ.

### Lines 29–32: the database rule

```python
_positive_size = models.Constraint(
    'CHECK(width > 0 AND depth > 0)',
    'An area must have a width and depth greater than zero.',
)
```

The database refuses an area with a width or depth of zero or less. A rack row has more rules of this kind (counts, unique code, no negative position). This file has just this one.

### Lines 34–37: `_wh3d_footprint`

```python
def _wh3d_footprint(self):
    self.ensure_one()
    return self.x, self.y, self.x + self.width, self.y + self.depth
```

- `ensure_one()` makes sure `self` is exactly one record.
- It returns the rectangle the shape covers on the floor: `(x0, y0, x1, y1)`.
- It has the same name and the same return shape as the rack row's version. Other code can ask either kind of record for its footprint in the same way.

### Lines 39–44: `_check_color`

```python
@api.constrains('color')
def _check_color(self):
    for area in self:
        if not COLOR_RE.fullmatch(area.color or ''):
            raise ValidationError(...)
```

- `@api.constrains('color')` runs this check whenever a record is saved with a new `color`.
- `fullmatch` means the **whole** text must fit the pattern, not just the start.
- `area.color or ''` copes with an empty colour.
- A bad colour cancels the save and shows the message: the colour must look like `#rrggbb`.

### Lines 46–60: `_check_layout`

This check keeps areas and docks in sensible places. It runs when `x`, `y`, `width`, `depth`, `kind` or `warehouse_id` changes.

```python
if self.env.context.get('wh3d_defer_layout_check'):
    return
```
The same "wait" flag as in section 8. The editor turns it on while saving, then checks the final layout once at the end.

```python
warehouse = self.env['stock.warehouse']
warehouse._check_wh3d_contains(self)
```
- `warehouse` is the warehouse table itself, used only to call its helper methods.
- `_check_wh3d_contains` checks that the shape fits inside the building. That helper lives in `stock_warehouse.py`.

**Docks must touch a wall:**

```python
for dock in self.filtered(lambda a: a.kind == 'dock'):
    building = dock.warehouse_id
    x0, y0, x1, y1 = dock._wh3d_footprint()
    if min(x0, y0, building.wh3d_length - x1, building.wh3d_width - y1) > EPS:
        raise ValidationError(...)
```

- It goes through only the records whose kind is `dock`.
- It gets the dock's rectangle and the building's size (`wh3d_length` along x, `wh3d_width` along y).
- The four numbers inside `min(...)` are the gaps between the dock and each of the four walls:
  - `x0`: gap to the left wall.
  - `y0`: gap to the near wall.
  - `wh3d_length - x1`: gap to the right wall.
  - `wh3d_width - y1`: gap to the far wall.
- `min` takes the smallest gap. If even the smallest gap is bigger than `EPS`, the dock touches no wall, and it raises "must touch a wall of the building".

**Areas must stay clear of rack rows:**

```python
for building in self.warehouse_id:
    rows = self.env['warehouse.rack.row'].search([('warehouse_id', '=', building.id)])
    warehouse._check_wh3d_areas_clear_of_rows(self.filtered(lambda a: a.warehouse_id == building), rows)
```

- It goes through each warehouse that appears among these areas.
- It loads that warehouse's rack rows.
- It hands this warehouse's areas and its rows to a helper (in `stock_warehouse.py`) that checks no area sits on top of a row.
- The rack row file calls the same helper from its own side. That way the check runs no matter which of the two you edit.
- Nothing in this file checks an area against another area.

### What is *not* in this file

There is no `create`, `write` or `unlink` override and no location syncing. Saving an area only runs the checks above. That is the main difference from a rack row, which drives a whole tree of Inventory locations.

### Why it's needed

- It stores everything on the floor plan that is not a rack: receiving, charging, office, packing, shipping and the dock doors.
- Without it, the 3D view would show racks floating on an empty floor.
- Its checks keep the plan believable: docks sit on a wall, and areas don't overlap racks.

---

## 11. `views/warehouse_rack_row_views.xml`

**The file in one sentence:** it defines the screens for rack rows (a list, a form and a search bar) and the action that opens them.

A view only says *what to show and where*. The data itself lives in the model from section 8.

### XML basics

- `<record>` means "create one row in a database table when the module is installed".
- Here the tables are `ir.ui.view` (stored screen layouts) and `ir.actions.act_window` (stored "open this screen" actions).
- `id` is a name other files can use. For example, `menus.xml` (section 6) uses `action_warehouse_rack_row` from the bottom of this file.
- `<field name="arch" type="xml">` holds the actual layout. Everything inside is what the user sees.
- `<field name="name">` and `<field name="model">` are labels. The name is for developers. The model says which table the screen is for.

### Lines 3–20: the list view

```xml
<list string="Rack Rows">
    <field name="code"/>
    <field name="kind"/>
    <field name="warehouse_id" groups="stock.group_stock_multi_warehouses"/>
    ...
    <field name="storage_category_id" optional="hide"/>
</list>
```

- It is the table of rows you see first. Each `<field>` is one column.
- Odoo 19 calls it `<list>`. Older versions called it `<tree>`.
- Shown columns: code, kind, warehouse, zone, x, y, bays, levels and slots per level. The sizes (`bay_width`, `depth`, `level_height`) are not in the list.
- `groups="stock.group_stock_multi_warehouses"` shows the warehouse column only to users who have the "multiple warehouses" setting on. A company with one warehouse never sees it.
- `optional="hide"` means the column exists but is hidden by default. A user can switch it on from the column picker.

### Lines 22–64: the form view

This is the screen for one row. It opens when you click a row in the list. It fills the main area of the page, with a breadcrumb to go back. It is not a side panel.

**The top bar (lines 27–30)**

```xml
<header>
    <button name="action_generate_locations" type="object" string="Regenerate Locations"
            groups="stock.group_stock_manager" help="..."/>
</header>
```

- `type="object"` means "call the Python method with this `name` on this record".
- So this button runs `action_generate_locations` from chunk 4 of section 8.
- `string` is the button label. `help` is the tooltip.
- `groups` makes the button visible to Inventory Managers only.

**The body (lines 31–61)**

- `<sheet>` is the white card in the middle of the screen.
- **The smart button (lines 32–36):**
  ```xml
  <button name="action_view_slots" type="object" class="oe_stat_button" icon="fa-th">
      <field name="slot_count" widget="statinfo" string="Slots"/>
  </button>
  ```
  - A small box at the top right that shows a number with a label ("Slots").
  - `slot_count` is the computed field from chunk 2. `widget="statinfo"` displays it as a number plus a label.
  - Clicking it calls `action_view_slots` (chunk 4), which opens the list of this row's slots.
- **The ribbon (line 37):**
  ```xml
  <widget name="web_ribbon" title="Archived" bg_color="text-bg-danger" invisible="active"/>
  ```
  - A red "Archived" corner tag.
  - `invisible="active"` hides it while the row is active, so it appears only when the row is archived.
  - In Odoo 17 and later, these `invisible`, `readonly` and `required` attributes take a short Python-like condition.
- **The title (lines 38–41):** a label and a big heading holding the `code` field. `placeholder="e.g. P05"` is the grey hint shown when it's empty.
- **Two columns (lines 42–60):** `<group>` inside `<group>` makes a left and a right column. The inner `string` is the column heading.

**Placement column (left)**

- `kind` uses `widget="radio"` with `horizontal: true`, so you get two radio buttons in a row instead of a dropdown.
- `warehouse_id` is again shown only with multiple warehouses.
- `location_id` (the zone), `storage_category_id`, `x` and `y`.
- `<field name="active" invisible="1"/>` loads the `active` field but never shows it. The ribbon above needs to read it, and a form must contain every field that its conditions use.

**Dimensions column (right)**

- `bays`, `bay_width`, `depth`, `levels`, `level_height`, `slots_per_level`.
- `slots_per_level` has `readonly="kind == 'shelf'"`. For shelving the field is locked, because a shelf must have exactly 1 slot per level (the check in chunk 2).
- Worth knowing: the screen only locks the field. It doesn't set it to 1. Nothing in the Python file sets it for you, so a pallet row with 2 slots that is switched to shelf is refused when you save.

### Lines 66–83: the search view

```xml
<search>
    <field name="code"/>
    <field name="location_id"/>
    <filter name="pallet" string="Pallet racks" domain="[('kind', '=', 'pallet')]"/>
    <filter name="shelf" string="Shelving" domain="[('kind', '=', 'shelf')]"/>
    <separator/>
    <filter name="archived" string="Archived" domain="[('active', '=', False)]"/>
    <group>
        <filter name="group_kind" string="Kind" context="{'group_by': 'kind'}"/>
        <filter name="group_zone" string="Zone" context="{'group_by': 'location_id'}"/>
    </group>
</search>
```

This controls the search bar above the list.

- The two `<field>` lines mean "typing text in the bar offers to search the code or the zone".
- A `<filter>` is a one-click choice in the dropdown. Its `domain` is the filter from section 8: only pallet racks, only shelving, or only archived rows.
- `<separator/>` splits the filters into groups, so a pallet filter and the archived filter can be combined.
- The `<group>` part holds the **Group By** choices: group the list by kind or by zone (`context="{'group_by': ...}"`).
- Normally archived rows are hidden. The Archived filter is how you find them.

### Lines 85–93: the action

```xml
<record id="action_warehouse_rack_row" model="ir.actions.act_window">
    <field name="name">Rack Rows</field>
    <field name="res_model">warehouse.rack.row</field>
    <field name="view_mode">list,form</field>
    <field name="help" type="html">...</field>
</record>
```

- An `ir.actions.act_window` is a stored instruction: "open this table in these views".
- `res_model` is the table. `view_mode` is `list,form`, so you land on the list and click a row to open the form.
- `help` is the message shown when there are no rows yet. `o_view_nocontent_smiling_face` is the style that adds the smiley.
- This is the action that the "Rack Rows" menu entry opens (section 6).

### How it fits with the other files

- The manifest (section 1) loads this file under `data`, after the security files and before `menus.xml`. The menu needs the action to exist.
- The buttons call methods from `warehouse_rack_row.py` (section 8): `action_generate_locations` and `action_view_slots`.
- `groups` on a column or button only *hides* it. The real permissions are in `ir.model.access.csv` (section 3).
- The side panels you see in the 3D view and the layout editor are **not** in this file. They are built in the OWL templates under `static/src/view3d/` and `static/src/editor/`.

### Why it's needed

- Without these records, the rack row table exists in the database, but nobody can see or edit it.
- It is the plain data-entry path next to the 2D editor. You can fix one number on one row without opening the editor.
- Its two buttons are the only places that call `action_generate_locations` and `action_view_slots`.

---

## 12. `models/stock_warehouse.py`

**The file in one sentence:** it adds the building size and the data-serving methods to Odoo's own warehouse table, so the editor and the 3D view can ask the server for a floor plan, a scene and live slot data.

It also holds the shared floor-plan checks that the rack row file (section 8) and the layout area file (section 10) both call, and the code that books the demo opening stock.

### Who calls what

| Method | Called by |
|---|---|
| `wh3d_list_warehouses` | `editor_action.js` line 73, `view3d_action.js` line 63 (the warehouse picker) |
| `wh3d_default_warehouse_id` | `editor_action.js` line 75, `view3d_action.js` line 65 |
| `wh3d_get_layout` | `editor_action.js` line 101, `wh3d_save_layout` (section 8, chunk 4), `wh3d_get_scene` |
| `wh3d_get_scene` | `view3d_action.js` line 102 |
| `wh3d_get_slots` | `view3d_action.js` line 190 (live updates) |
| `action_wh3d_open_view3d`, `action_wh3d_open_editor` | two smart buttons in `views/warehouse_layout_area_views.xml` (lines 37 and 39) |
| `_wh3d_fill_template_stock` | `demo/layout.xml` line 582 |
| `_check_wh3d_contains`, `_check_wh3d_areas_clear_of_rows` | the checks in sections 8 and 10, and `_check_wh3d_size` in this file |

`this.orm.call("stock.warehouse", "method", [...])` in the JavaScript files is the browser calling a Python method on the server.

### Lines 1–9: setup

```python
import math
import random

from odoo import api, fields, models
from odoo.exceptions import ValidationError

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'
```

- `math` is used once, for `floor`. `random` is used to make the demo stock.
- Same Odoo tools as before.
- `_inherit = 'stock.warehouse'` with no `_name` means "reopen the existing warehouse table and add to it" (the same trick as in section 9).

### Lines 11–15: the building and its areas

```python
wh3d_length = fields.Float(string='Building Length (m)', digits=(6, 2), default=60.0, help="Along X.")
wh3d_width = fields.Float(string='Building Width (m)', digits=(6, 2), default=40.0, help="Along Y.")
wh3d_height = fields.Float(string='Clear Height (m)', digits=(6, 2), default=10.0)
wh3d_area_ids = fields.One2many('warehouse.layout.area', 'warehouse_id', string='Layout Areas')
```

- The three numbers are the inside size of the building in metres. The defaults, 60 × 40 × 10, are the template warehouse.
- The floor plan's origin (0, 0) is one corner of the building. Length runs along x and width runs along y.
- `wh3d_area_ids` lists every floor area and dock of this warehouse. It is the reverse link of `warehouse_id` on `warehouse.layout.area`.

### Lines 17–26: `_check_wh3d_size`

```python
@api.constrains('wh3d_length', 'wh3d_width', 'wh3d_height')
def _check_wh3d_size(self):
    for warehouse in self:
        if min(warehouse.wh3d_length, warehouse.wh3d_width, warehouse.wh3d_height) <= 0:
            raise ValidationError(...)
        warehouse._check_wh3d_contains(warehouse.wh3d_area_ids)
        warehouse._check_wh3d_contains(
            self.env['warehouse.rack.row'].search([('warehouse_id', '=', warehouse.id)]))
```

- It runs when the building size changes.
- First rule: all three sizes must be above zero. `min(...)` takes the smallest of them.
- Then it checks that every area and every rack row still fits in the new size. So you can't shrink the building below what is already placed in it.

### Lines 28–34: `wh3d_default_warehouse_id`

```python
@api.model
def wh3d_default_warehouse_id(self):
    rows = self.env['warehouse.rack.row'].search([], order='warehouse_id')
    warehouses = self.search([])
    with_rows = warehouses.filtered(lambda w: w in rows.warehouse_id)
    return (with_rows or warehouses)[:1].id
```

- It decides which warehouse the 3D view and the editor open first.
- `with_rows` is the warehouses that have at least one rack row.
- `(with_rows or warehouses)` means "those with rows, or if there are none, all of them". `[:1]` keeps the first one, or nothing, and `.id` gives its id.
- `self.search([])` returns only the warehouses this user may see.

### Lines 36–42: `wh3d_list_warehouses`

```python
@api.model
def wh3d_list_warehouses(self):
    warehouses = self.search([])
    counts = dict(self.env['warehouse.rack.row']._read_group(
        [('warehouse_id', 'in', warehouses.ids)], ['warehouse_id'], ['__count']))
    return [{'id': w.id, 'name': w.name, 'code': w.code, 'row_count': counts.get(w, 0)} for w in warehouses]
```

- It gives the warehouse picker its list: id, name, code and how many rack rows each warehouse has.
- `self.search([])` returns the usual warehouse order, and the company rules limit it to what this user may see.
- `_read_group` counts the rows of every warehouse in one query. That is the same trick as in section 8, chunk 2.
- The last line is a *list comprehension*: one small dictionary per warehouse. `counts.get(w, 0)` gives 0 for a warehouse with no rows.

### Lines 44–55: opening the screens from a warehouse

```python
def action_wh3d_open_view3d(self):
    return self._wh3d_open('warehouse_3d.action_wh3d_view3d')

def action_wh3d_open_editor(self):
    return self._wh3d_open('warehouse_3d.action_wh3d_editor')

def _wh3d_open(self, xmlid):
    self.ensure_one()
    action = self.env['ir.actions.actions']._for_xml_id(xmlid)
    action['context'] = {'warehouse_id': self.id}
    return action
```

- The first two are button methods (the `action_` prefix). They are the buttons wired up in `warehouse_layout_area_views.xml`.
- `_wh3d_open` loads one of the two client actions from section 5 by its XML id, as a dictionary.
- It then puts `{'warehouse_id': self.id}` into the action's `context`. That is how the JavaScript screen knows which warehouse to show.
- `ensure_one()` makes sure the button was pressed on exactly one warehouse.

### Lines 57–68: `wh3d_get_layout`

```python
def wh3d_get_layout(self):
    self.ensure_one()
    rows = self.env['warehouse.rack.row'].search([('warehouse_id', '=', self.id)])
    return {
        'warehouse_id': self.id,
        'name': self.name,
        'building': {'length': self.wh3d_length, 'width': self.wh3d_width, 'height': self.wh3d_height},
        'areas': self.wh3d_area_ids.read([...], load=None),
        'rows': rows.read([...], load=None),
    }
```

- It returns the floor plan as one dictionary: the building size, all areas and all rack rows.
- `.read([...fields...])` turns records into plain dictionaries with only the fields listed. `load=None` makes links come back as plain ids.
- The editor uses it to draw the plan. `wh3d_save_layout` returns it after a save (section 8, chunk 4), and the next method builds on it.

### Lines 70–76: `wh3d_get_scene`

```python
def wh3d_get_scene(self):
    scene = self.wh3d_get_layout()
    slots = self.env['stock.location'].search(
        [('wh3d_rack_row_id', 'in', [r['id'] for r in scene['rows']]), ('wh3d_node', '=', 'slot')])
    scene['slots'] = self._wh3d_slot_data(slots)
    return scene
```

- It returns everything the 3D view draws: the floor plan plus every slot with its stock.
- It finds all slot locations that belong to the layout's rows. The docstring says it uses a fixed number of queries, however many slots there are.

### Lines 78–82: `wh3d_get_slots`

```python
@api.model
def wh3d_get_slots(self, location_ids):
    slots = self.env['stock.location'].search([('id', 'in', location_ids), ('wh3d_node', '=', 'slot')])
    return self._wh3d_slot_data(slots)
```

- It returns fresh data for only the slots you ask about. The 3D view uses it for live updates, so it doesn't reload the whole scene.
- Ids that are not active slots are ignored.

### Lines 84–92: `_wh3d_slot_data`

```python
quants = self.env['stock.quant']._read_group(
    [('location_id', 'in', slots.ids), ('quantity', '>', 0)],
    ['location_id', 'product_id'], ['quantity:sum'])
by_slot = {}
for location, product, qty in quants:
    by_slot.setdefault(location, []).append((product, qty))
return [self._wh3d_slot_dict(slot, by_slot.get(slot, [])) for slot in slots]
```

- One grouped question to the database: "in these slots, how much of each product is there?" A `stock.quant` is a record of a quantity of one product in one location.
- `'quantity:sum'` means add up the quantities of each group. `('quantity', '>', 0)` skips empty ones.
- The loop builds a dictionary: slot → list of `(product, quantity)`. `setdefault(location, [])` creates the empty list the first time a slot appears.
- Then one dictionary is built per slot. A slot with no stock gets an empty list from `by_slot.get(slot, [])`.
- Again, one query for all slots, not one per slot.

### Lines 94–112: `_wh3d_slot_dict`

This builds the data for one slot.

```python
row = slot.wh3d_rack_row_id
capacity = row.bay_width / row.slots_per_level * row.depth * row.level_height
```

- `capacity` is the volume of one slot in cubic metres: the bay's width shared between the slots that sit side by side, times the depth, times the level height.
- Example with the template numbers: 2.7 ÷ 2 × 1.1 × 1.8 = 2.673 m³.

```python
stock = None
if contents:
    product, qty = max(contents, key=lambda pq: pq[1])
    volumes = [p.wh3d_length * p.wh3d_width * p.wh3d_height * q for p, q in contents]
    used = sum(volumes) if all(volumes) else None
```

- With no stock, `stock` stays `None`.
- With stock, `max(..., key=...)` picks the product with the largest quantity. That one is the product shown for the slot.
- `volumes` is the volume each product takes: its length × width × height (product dimension fields added by this module) times the quantity.
- `all(volumes)` is false if any volume is 0, which is what a product without dimensions gives. Then `used` is `None`, meaning "fill unknown" (the comment on line 102).

```python
stock = {
    'product_id': product.id, 'name': product.name, 'default_code': product.default_code or '',
    'qty': qty, 'uom': product.uom_id.name, 'mixed': len(contents) > 1,
    'used_m3': used, 'fill': used / capacity if used is not None else None,
}
```

- `mixed` is true when the slot holds more than one product.
- `fill` is the used volume divided by the capacity, so 0.5 means half full. It is `None` when `used` is unknown.
- The name and quantity are for the biggest product only, but `used_m3` adds up all products. `mixed` tells the screen that more is in there.

```python
return {
    'location_id': slot.id, 'code': slot.name, 'path': slot.complete_name, 'row_id': row.id,
    'bay': slot.wh3d_bay, 'level': slot.wh3d_level, 'position': slot.wh3d_position,
    'capacity_m3': capacity, 'stock': stock,
}
```

The final dictionary: where the slot is, how big it is, and what is in it.

### Lines 114–120: constants for the demo stock

```python
_WH3D_ABC_WEIGHT = {'A': 6, 'B': 2, 'C': 1}
_WH3D_FILL_BANDS = ((0.25, 0.45), (0.55, 0.85), (0.94, 0.99))
```

- `_WH3D_ABC_WEIGHT`: how much more often a fast mover gets stocked than a slow one. An "A" product is picked 6 times as often as a "C" product.
- `_WH3D_FILL_BANDS`: three target fill ranges, one for each colour of "Colour by occupancy": green below 50%, amber 50–90%, red above 90%. The demo picks one of the three evenly so that all colours show up.

### Lines 122–151: `_wh3d_plan_template_stock`

**What it does:** decides what opening stock the template warehouse gets, as a list of `(slot, product, quantity)`. It only plans. It writes nothing. For a given `seed` it gives the same result every time.

```python
rng = random.Random(seed)
```
A random number generator of its own, started from a fixed seed. The same seed gives the same "random" numbers every run, so the demo is the same on every machine.

```python
products = {
    'pallet': Product.search([('categ_id', '=', self.env.ref('warehouse_3d.categ_bulk').id)], order='default_code'),
    'shelf': Product.search([('categ_id', '=', self.env.ref('warehouse_3d.categ_small_parts').id)], order='default_code'),
}
weights = {kind: [self._WH3D_ABC_WEIGHT.get(p.wh3d_abc_class, 1) for p in prods]
           for kind, prods in products.items()}
```

- `self.env.ref('warehouse_3d.categ_bulk')` gets a record by its XML id.
- Bulk goods go on pallet rows, and small parts go on shelves.
- `order='default_code'` fixes the order so the result is repeatable.
- `weights` gives each product its ABC weight (1 if it has no class).

```python
rows = self.env['warehouse.rack.row'].search([('warehouse_id', '=', warehouse.id)])
slots = self.env['stock.location'].search(
    [('wh3d_rack_row_id', 'in', rows.ids), ('wh3d_node', '=', 'slot')], order='complete_name')
```
All slots of the warehouse, sorted by name, again for repeatability.

```python
for slot in slots:
    if rng.random() >= occupancy:
        continue
    row = slot.wh3d_rack_row_id
    product = rng.choices(products[row.kind], weights=weights[row.kind])[0]
    capacity = row.bay_width / row.slots_per_level * row.depth * row.level_height
    unit = product.wh3d_length * product.wh3d_width * product.wh3d_height
    target = rng.uniform(*rng.choice(self._WH3D_FILL_BANDS))
    plan.append((slot, product, max(1, math.floor(target * capacity / unit))))
```

For each slot:
1. `rng.random()` gives a number between 0 and 1. If it is at or above `occupancy` (0.65), skip the slot. So about 65% of the slots get stock.
2. Pick a product of the right kind. `rng.choices(..., weights=...)` is a random pick where heavier weights come up more often.
3. Work out the slot's capacity and the volume of one unit of the product.
4. Pick one of the three fill bands at random, then pick a random fill inside it. `*` unpacks the pair into the two arguments.
5. The quantity is the fill target times the capacity, divided by the unit volume, rounded down (`math.floor`), and never below 1.

### Lines 153–161: `_wh3d_fill_template_stock`

```python
warehouse = self.browse(warehouse_id)
plan = self._wh3d_plan_template_stock(warehouse, seed=seed)
quants = self.env['stock.quant'].with_context(inventory_mode=True).create([
    {'product_id': product.id, 'location_id': slot.id, 'inventory_quantity': qty}
    for slot, product, qty in plan])
quants.with_context(inventory_name='Warehaven DC opening stock').action_apply_inventory()
```

- It takes the plan and books it as **one inventory adjustment**, the same thing a person does in Inventory when they count stock.
- `inventory_mode=True` tells Odoo to treat `inventory_quantity` as a counted amount.
- `action_apply_inventory()` turns the counts into real stock. `inventory_name` is the label that appears on those moves.
- The demo data calls this method (`demo/layout.xml` line 582), so the demo warehouse starts with real stock, not made-up numbers.

### Lines 163–174: `_check_wh3d_contains`

```python
@api.model
def _check_wh3d_contains(self, items):
    eps = 1e-6
    for item in items:
        wh = item.warehouse_id
        x0, y0, x1, y1 = item._wh3d_footprint()
        if x0 < -eps or y0 < -eps or x1 > wh.wh3d_length + eps or y1 > wh.wh3d_width + eps:
            raise ValidationError(...)
```

- It refuses an item (a floor area or a rack row) that sticks out of its building.
- Each item gives its rectangle with `_wh3d_footprint()`. Both models have that method with the same shape, so this one check works for both.
- The test is: the left edge is below 0, the near edge is below 0, the right edge is past the building length, or the far edge is past the building width. `eps` allows touching a wall.
- The error shows the item's position and the building size.

### Lines 176–190: `_check_wh3d_areas_clear_of_rows`

```python
@api.model
def _check_wh3d_areas_clear_of_rows(self, areas, rows):
    eps = 1e-6
    for area in areas.filtered(lambda a: a.kind == 'area'):
        ax0, ay0, ax1, ay1 = area._wh3d_footprint()
        for row in rows.filtered(lambda r: r.active and r.warehouse_id == area.warehouse_id):
            x0, y0, x1, y1 = row._wh3d_footprint()
            if ax0 < x1 - eps and x0 < ax1 - eps and ay0 < y1 - eps and y0 < ay1 - eps:
                raise ValidationError(...)
```

- It refuses a floor area that overlaps a rack row.
- Only things of kind `area` are checked. Docks are left out, because docks sit on the wall and are not floor space.
- For each area, it looks at the active rows of the same warehouse and runs the same rectangle-overlap test as in section 8. Touching edges are fine.
- The error lists both positions.

### Why it's needed

- **The building:** the warehouse needs a size, so the rack rows and areas have something to fit inside.
- **One place for the data:** the JavaScript screens ask the server for a floor plan, a scene and slot updates. These methods return plain dictionaries that the browser can use directly, with a fixed number of database queries.
- **Shared checks:** "inside the building" and "areas clear of rows" are needed by both the rack row file and the layout area file. Keeping them here means one version of each rule.
- **Demo stock:** the template warehouse starts about 65% full, with fast movers stocked more often and a mix of fill levels. That makes the 3D view and the occupancy colours worth looking at straight after install.

---

## 13. `models/stock_quant.py`

**The file in one sentence:** it watches for any change to stock quantities and, when a rack slot is affected, sends one live notification so the 3D view can refresh that slot.

It adds no new fields. It only adds behaviour to Odoo's own quant table.

### Words you will see

| Word | Plain meaning |
|---|---|
| **quant** | A record of how much of one product sits in one location. |
| **transaction** | A bundle of database changes that are saved together (a *commit*) or all thrown away (a *rollback*). |
| **`self.env.cr`** | The database cursor: your connection to the current transaction. |
| **pre-commit hook** | A function you register to run just before the transaction is committed. |
| **bus** | Odoo's notification channel from the server to open browsers. The module depends on `bus` (section 1) for this. |

### Lines 1–3: setup

```python
from odoo import api, models

PENDING_KEY = 'warehouse_3d.changed_locations'
```

- Only `api` and `models` are needed. There are no new fields.
- `PENDING_KEY` is a name tag. It is used to keep one shared bag of changed location ids for the whole transaction.

### Lines 6–7: the class

```python
class StockQuant(models.Model):
    _inherit = 'stock.quant'
```

`_inherit` with no `_name` means "reopen the existing quant table and add to it" (the same trick as sections 9 and 12). Odoo's own stock code keeps working. It just goes through the methods below first.

### Lines 9–13: `create`

```python
@api.model_create_multi
def create(self, vals_list):
    quants = super().create(vals_list)
    quants._wh3d_notify(quants.location_id)
    return quants
```

- Save the new quants with `super()`.
- Then report their locations as changed. `quants.location_id` is the group of locations those quants sit in.

### Lines 15–21: `write`

```python
def write(self, vals):
    before = self.location_id
    res = super().write(vals)
    if {'quantity', 'location_id', 'product_id'}.intersection(vals):
        self._wh3d_notify(before | self.location_id)
    return res
```

- `before` remembers where the quants were *before* the edit. A quant moved to another location changes both places.
- `super().write(vals)` does the real save.
- It only reports a change if the edit touched `quantity`, `location_id` or `product_id`. The comment on line 18 explains why reservations are left out: the 3D view doesn't show them, so they would only cause pointless refreshes.
- `before | self.location_id` joins the old and the new locations (`|` is union).

### Lines 23–27: `unlink` (delete)

```python
def unlink(self):
    locations = self.location_id
    res = super().unlink()
    self._wh3d_notify(locations)
    return res
```

The locations are remembered **before** the delete, because once the quants are gone there is nothing left to read them from.

### Lines 29–40: `_wh3d_notify` (collect, don't send)

**What it does:** notes which locations changed, and arranges for one message to be sent later. The docstring gives the reason: a receipt of 50 lines writes quants more than 50 times, and the 3D view should hear about it once.

```python
if not locations:
    return
```
Nothing changed, so nothing to do.

```python
precommit = self.env.cr.precommit
if PENDING_KEY not in precommit.data:
    precommit.data[PENDING_KEY] = set()
    precommit.add(self._wh3d_send_changed)
precommit.data[PENDING_KEY].update(locations.ids)
```

- `precommit` is the transaction's list of "run this just before commit" functions. `precommit.data` is a dictionary that lives as long as the transaction.
- The first time a quant changes in this transaction, the bag does not exist yet. So the code creates an empty `set` under `PENDING_KEY` and registers `_wh3d_send_changed` to run before the commit. This registering happens **once per transaction**.
- Every call then adds its location ids to the set. A `set` drops duplicates on its own, so a slot changed 50 times is stored once.

### Lines 42–47: `_wh3d_send_changed` (send once)

This runs just before the commit.

```python
ids = self.env.cr.precommit.data.pop(PENDING_KEY, set())
slots = self.env['stock.location'].sudo().search([('id', 'in', list(ids)), ('wh3d_node', '=', 'slot')])
```

- `pop` takes the bag out and removes it from the transaction. The second argument is the fallback if it is missing.
- It keeps only the ids that are rack **slots** (`wh3d_node = 'slot'`). Changes in ordinary locations are ignored.
- `.sudo()` runs the search without the current user's access rules, so the user who made the stock move doesn't change which slots are found.

```python
if slots:
    self.env['bus.bus']._sendone(
        self.env.ref('stock.group_stock_user'), 'warehouse_3d/stock', {'location_ids': slots.ids})
```

- If at least one slot changed, it sends **one** bus message.
- The three arguments are: the channel (the Inventory User group, so only people in that group are addressed), the message type (`'warehouse_3d/stock'`) and the content.
- The content is only a list of slot ids: `{'location_ids': [...]}`. No stock data travels in the message.

### How the pieces connect

```
Any stock change (receipt, delivery, count, move)
      │   Odoo creates, edits or deletes quants
      ▼
create / write / unlink here        note the changed locations in one bag
      │
      ▼
just before commit                  keep only the rack slots, send ONE bus message
      │
      ▼
the browser's 3D view               gets the ids, then asks for fresh data
      │
      ▼
wh3d_get_slots (section 12)         returns the new stock for just those slots
```

### Why it's needed

- **Live updates:** without it, the 3D view would only show stock as of the moment you opened it.
- **No flood of messages:** a big receipt changes many quants, but the 3D view gets a single message.
- **Light messages:** the bus only carries ids. The 3D view then asks `wh3d_get_slots` for the actual data, so each user's own access rules apply to what they see.
- **Only real changes:** reservations are ignored, and only rack slots are announced.

---

## 14. `models/product_template.py`

**The file in one sentence:** it adds a box size (length, width, height) and a speed class (A, B or C) to every product.

Odoo's products only store weight and volume. The 3D view needs the shape of a product to work out how full a slot is.

### Lines 1–5: setup and the class

```python
from odoo import fields, models

class ProductTemplate(models.Model):
    _inherit = 'product.template'
```

- Only `fields` and `models` are needed. This file has no checks and no methods, so it has no `api` or errors to import.
- `_inherit = 'product.template'` with no `_name` means "reopen the existing product table and add to it" (the same trick as sections 9, 12 and 13).
- A **product template** is what you normally think of as "a product" in Odoo. A **product variant** (`product.product`) is one specific version of it, such as a size or colour. Variants can read every field of their template.
- That is why `stock_warehouse.py` (section 12) can read `product.wh3d_length` on a variant. The field lives here, on the template.

### Lines 7–11: the box size

```python
# Odoo only stores weight and volume; the 3D view and later the putaway experiments need the box shape.
# 0 means "unknown": such products show without a fill % in the 3D view.
wh3d_length = fields.Float(string='Length (m)', digits=(6, 3))
wh3d_width = fields.Float(string='Width (m)', digits=(6, 3))
wh3d_height = fields.Float(string='Height (m)', digits=(6, 3))
```

- Three decimal numbers, in **metres**. `digits=(6, 3)` means up to 6 digits in total and 3 after the decimal point, so you can store a size down to the millimetre.
- `string='Length (m)'` is the label on the screen.
- There is no `required=True` and no default, so a new product starts with 0 in all three.
- **0 means "unknown".** In section 12, `_wh3d_slot_dict` multiplies the three sizes and the quantity. A product with a 0 gives a volume of 0, and then the slot shows no fill percentage.
- Example: a box of 0.4 × 0.3 × 0.2 m is 0.024 m³. Fifty of them use 1.2 m³. In a slot of 2.673 m³ (the template slot from section 12), that is about 45% full.
- The warehouse table also has fields called `wh3d_length`, `wh3d_width` and `wh3d_height`. Those are the **building** size. They are on a different table, so the names don't clash, but don't mix them up.

### Lines 12–15: the ABC class

```python
wh3d_abc_class = fields.Selection([('A', 'A - fast mover'), ('B', 'B - medium'), ('C', 'C - slow mover')],
                                  string='ABC Class')
```

- A dropdown with three choices: **A** is picked often, **B** is medium, **C** is picked rarely. This is how warehouses commonly rank products by how often they are picked.
- There is no default, so the field can stay empty.
- The comment says it is kept for the later putaway experiments, where fast movers would be stored near the docks. The 3D view colours slots by fill, not by class.
- In the files covered so far, the only code that reads it is the demo-stock planner in section 12. It gives an "A" product six times the chance of a "C" product (`_WH3D_ABC_WEIGHT`), and a product with no class counts as 1.

### What is *not* in this file

- There are no rules. Nothing stops a negative size here.
- There are no methods. The file is only four new columns.

### Why it's needed

- **Fill percentage:** the 3D view can only say "this slot is 45% full" if it knows how big each product is.
- **Demo stock:** the template warehouse picks products by class and fills slots by volume, which needs both new fields.
- **Later experiments:** the research plan compares standard putaway with custom strategies. Those strategies need the box shape (to fit things in a slot) and the pick speed (to place fast movers near the docks).

---

## 15. `tests/common.py`

**The file in one sentence:** it holds the shared test data and small helper functions that the Python tests use, so each test doesn't have to build a rack row or find the demo warehouse by hand.

It is not part of the running module. It is only used when tests run. The comment at the top says it is "kept small on purpose: each test still says what it needs".

### Words you will see

| Word | Plain meaning |
|---|---|
| **test helper** | A small function that sets up data for a test, so the test itself stays short. |
| **`env`** | The Odoo environment (section 8): your way into the database tables. Each test passes in its own `self.env`. |
| **skip** | A test that is not run, and not counted as a failure. |

### Lines 1–2: setup

```python
"""Shared test data. Kept small on purpose: each test still says what it needs."""
from unittest import SkipTest
```

- The text in triple quotes is the file's comment.
- `SkipTest` comes from Python's standard test library. Raising it tells the test runner "skip this test".

### Lines 4–8: `P05`, the standard test row

```python
P05 = {
    'code': 'P05', 'kind': 'pallet', 'x': 9.7, 'y': 1.0, 'bays': 7, 'bay_width': 2.7,
    'depth': 1.1, 'levels': 5, 'level_height': 1.8, 'slots_per_level': 2,
}
```

- A dictionary holding the field values of one rack row. These are the values from the project handoff (`docs/CLAUDE.md`).
- 7 bays × 5 levels × 2 slots = **70 pallet slots**.
- It has no warehouse and no zone. The helper below adds those.
- Tests copy this and change what they need, so there is one agreed example row.

### Lines 11–13: `create_zone`

```python
def create_zone(env, warehouse, name='PR'):
    return env['stock.location'].create({'name': name, 'usage': 'internal', 'location_id': warehouse.lot_stock_id.id})
```

- A rack row needs a **zone**: an Internal location inside the warehouse's stock location (the rules in section 8, chunk 2).
- This helper creates one called `PR` by default, directly under the warehouse's stock location (`WH/Stock`).
- `name='PR'` is a default value. A test can pass a different name.

### Lines 16–20: `create_p05`

```python
def create_p05(env, warehouse, zone=None, **overrides):
    zone = zone or create_zone(env, warehouse)
    return env['warehouse.rack.row'].create(
        dict(P05, warehouse_id=warehouse.id, location_id=zone.id, **overrides))
```

- It creates rack row P05 in the warehouse you give it.
- `zone=None` means "make a zone for me". `zone or create_zone(...)` uses the zone you passed, or creates one if you didn't.
- `**overrides` collects any extra named values. A test can call `create_p05(env, wh, bays=3)` to change the number of bays.
- `dict(P05, warehouse_id=..., location_id=..., **overrides)` copies `P05`, adds the warehouse and zone, and then adds the overrides.
- Creating the row runs the code from section 8, so the row's locations are made at once: 1 row + 7 bays + 35 levels + 70 slots = **113 locations**. That is the number in the docstring.
- To use a different zone, pass `zone=`. Passing `warehouse_id=` or `location_id=` as an override fails with a "multiple values for keyword argument" error, because the function already sets both.

### Lines 23–28: `template_warehouse`

```python
def template_warehouse(env):
    warehouse = env.ref('warehouse_3d.warehouse_template', raise_if_not_found=False)
    if not warehouse:
        raise SkipTest('needs the demo data (database created with --with-demo)')
    return warehouse
```

- It returns the demo **template warehouse** (code `WHV`).
- `env.ref('warehouse_3d.warehouse_template')` gets a record by its XML id. `raise_if_not_found=False` makes it return an empty result instead of an error when the record doesn't exist.
- If the database was made without demo data, the warehouse isn't there. Then it raises `SkipTest`, and the test is skipped, not failed.

### Lines 31–39: `template_rows`

```python
def template_rows():
    pallet_x = [0.2, 4.3, 5.6, 9.7, 11.0, 15.1, 16.4, 20.5, 21.8, 25.9, 27.2, 31.3, 32.6, 36.7]
    shelf_x = [round(39.6 + 2.4 * k + d, 1) for k in range(8) for d in (0, 0.6)] + [59.0]
    rows = [dict(P05, code=f'P{i + 1:02d}', x=x) for i, x in enumerate(pallet_x)]
    rows += [{'code': f'S{i + 1:02d}', 'kind': 'shelf', 'x': x, 'y': 2.0, 'bays': 16, 'bay_width': 1.0,
              'depth': 0.6, 'levels': 5, 'level_height': 0.4, 'slots_per_level': 1}
             for i, x in enumerate(shelf_x)]
    return rows
```

It returns the whole template warehouse layout as a list of **31 rack rows**, each a dictionary of field values:

- **14 pallet rows, `P01` to `P14`.** `pallet_x` lists the x position of each one. Every row copies `P05` and changes only `code` and `x`.
  - `enumerate(pallet_x)` gives a counter and an item together.
  - `f'P{i + 1:02d}'` builds `P01`, `P02`, … (`:02d` pads to two digits).
- **17 shelving rows, `S01` to `S17`.** The x positions come from the list on the `shelf_x` line:
  - The first part is a loop inside a loop. For each of 8 steps (`k`), it makes two positions: `39.6 + 2.4k` and `39.6 + 2.4k + 0.6`. These are 8 shelving pairs standing back to back.
  - `+ [59.0]` adds one last single row at the end.
  - 8 × 2 + 1 = 17 positions.
  - Each shelf row is 16 bays of 1.0 m, 0.6 m deep, 5 levels of 0.4 m, and 1 slot per level, at y = 2.0.
- Check against the spec: 14 × 70 = 980 pallet positions, and 17 × 16 × 5 = 1,360 shelf bins. Both match the numbers in the project handoff.
- The rows have no warehouse or zone. Whoever uses them adds those.

### Why it's needed

- **Less repetition:** without these helpers, every test would repeat the same long set-up.
- **One agreed example:** `P05` and the 31 template rows are written once, and every test uses the same values.
- **No false failures:** a test that needs the demo data is skipped, not failed, when the database has none.

---

## 16. `tests/test_rack_row.py`

**The file in one sentence:** it checks that the rack row rules from section 8 really work: valid rows are accepted, invalid rows are refused, and the layout rules (inside the building, no overlaps) hold.

Each test is a small function that sets up data, does one thing, and checks the result. If a check fails, the test fails. The file has 13 tests for the row's own rules and 12 tests for the layout rules.

### Words you will see

| Word | Plain meaning |
|---|---|
| **`TransactionCase`** | The base class for Odoo database tests. Each test runs inside a transaction that is thrown away afterwards, so tests don't affect each other. |
| **`setUpClass`** | Runs **once** before all the tests in the class. It prepares data they share. `cls` means "the class" (like `self`, but for the whole class). |
| **assert** | A check. `assertEqual(a, b)` fails unless `a` equals `b`. `assertIn`, `assertNotIn` and `assertFalse` work the same way. |
| **`assertRaises(X)`** | The test passes only if the code inside raises error `X`. It checks that a bad action is refused. |
| **`subTest`** | Runs the same check for several inputs and reports each input separately. |
| **savepoint** | A bookmark in the transaction (section 8, chunk 4). After a database error, going back to it keeps the test usable. |
| **`mute_logger`** | Hides log lines that are expected, so a deliberate error doesn't fill the output. |
| **`with_user(user)`** | Runs the next call as that user, so access rules apply. |

### Lines 1–10: imports

- `IntegrityError` comes from `psycopg2`, the PostgreSQL driver. It is raised when a **database rule** (the `models.Constraint` entries from section 8) is broken.
- `ValidationError` is raised by the **Python rules** (`@api.constrains`). `AccessError` is raised when a user lacks permission (section 3).
- `new_test_user` creates a temporary user with chosen groups for a test.
- `Command` is used for one operation on many-to-many fields (line 92). `convert_file` loads a data file the way install or update does. `safe_eval` evaluates a text expression safely.
- `from .common import create_p05, create_zone, template_rows` brings in the helpers from section 15.

### The pattern used by the database-rule tests

```python
with self.subTest(field=field), self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'), self.cr.savepoint():
    self.Row.create(self._vals(**{field: 0}))
```

One `with` line holds four things:
1. `subTest(field=field)`: report each field separately.
2. `assertRaises(IntegrityError)`: the create **must** fail.
3. `mute_logger(...)`: hide the expected database error in the log.
4. `savepoint()`: after a database error the transaction is unusable. Rolling back to the bookmark lets the next loop pass run.

`**{field: 0}` turns the variable `field` into a named value, so one line can set `bays=0`, then `depth=0`, and so on.

### Class `TestRackRow` (lines 13–110)

**Setup (lines 15–22).** `setUpClass` gets Odoo's default warehouse (`stock.warehouse0`), creates a zone `PR` under its stock location, and keeps `cls.Row`, the rack row table, for short use.

**`_vals(**overrides)` (lines 24–32).** Returns the P05 values plus the warehouse and zone as a dictionary. `vals.update(overrides)` lets a test change any field. This is like `create_p05` from section 15, but it returns the dictionary and doesn't create the row.

| Test | What it does | What it proves |
|---|---|---|
| `test_create_handoff_record` | Creates P05. Checks `display_name` is `P05` and the counts are (7, 5, 2). | A normal row works. The row shows by its code (`_rec_name`). |
| `test_rejects_non_positive_dimensions` | Sets each of six fields (bays, bay width, depth, levels, level height, slots) to 0. | The database refuses it (`IntegrityError`). |
| `test_rejects_negative_position` | Sets `x`, then `y`, to −0.1. | The database refuses a negative position. |
| `test_rejects_bad_code_format` | Tries `P5`, `p05`, `P005`, `PX5`, `05`. | The code pattern from section 8 refuses each (`ValidationError`). |
| `test_rejects_duplicate_code_in_warehouse` | Creates P05, then another P05 at a different `x`. | The code is unique within a warehouse (`IntegrityError`). |
| `test_shelf_has_one_slot_per_level` | A shelf with 2 slots fails. A shelf with 1 works. | The shelf rule. |
| `test_at_most_26_slots_per_level` | 27 slots fails. | Positions only run A to Z. |
| `test_zone_location_must_be_in_warehouse_stock` | Uses a location outside the warehouse. | The zone must be inside the warehouse's stock location. |
| `test_stock_user_reads_but_cannot_write` | A user in the Inventory User group reads the row, then tries to change `bays`. | Reading works and writing gives `AccessError` (section 3). |
| `test_storage_locations_setting_enabled_like_settings_page` | Checks the "Storage Locations" group is implied for all internal users and that two Odoo location views are archived. | `res_groups.xml` (section 4) switched the setting on the proper way, side effects included. |
| `test_module_update_keeps_storage_locations_off` | Removes the setting, re-loads `res_groups.xml` in update mode, and checks it stays off. | `noupdate="1"` works: an admin's later "off" survives a module update. |
| `test_zone_dropdown_offers_internal_locations_only` | Takes the zone field's filter text, evaluates it with `safe_eval`, and searches with it. | The dropdown offers the internal zone and not a virtual location. |
| `test_stock_manager_can_write` | A manager user changes `bays` to 8. | Managers can write (section 3). |

Two comments in this class say the test came from a CodeRabbit code review (lines 89 and 97). Those were real problems that were then pinned down with tests.

### Class `TestRackRowLayout` (lines 113–188)

The docstring says it: rows stay inside the building and don't overlap, and the editor relies on this.

**Setup (lines 116–123).** The default warehouse (60 × 40 m) and one zone made with `create_zone`. `_row(**overrides)` calls `create_p05` with them, so a test only states what differs.

**Numbers to keep in mind:** P05 is 1.1 m deep along x and 7 × 2.7 = 18.9 m long along y.

| Test | What it does | What it proves |
|---|---|---|
| `test_row_must_lie_inside_the_building` | Tries `x=59` (59 + 1.1 is past the 60 m wall) and `y=22` (22 + 18.9 is past the 40 m wall). | A row sticking out is refused, with a message containing "inside". |
| `test_row_touching_the_walls_is_allowed` | Puts the row exactly against the far walls. | Touching a wall is fine. |
| `test_growing_a_row_through_the_wall_is_refused` | A row at `y=20` gets `bays = 8`. | Editing an existing row is checked too (20 + 21.6 is more than 40). |
| `test_overlapping_rows_are_refused_naming_both` | P06 placed 0.5 m into P05. | The error names both rows. The pattern `(?s)P06.*P05\|P05.*P06` accepts either order. |
| `test_rows_touching_back_to_back_are_allowed` | P06 starts exactly where P05 ends. | Touching rows are fine. Decimals like these aren't stored exactly, which is what `EPS` is for. |
| `test_rows_in_different_stretches_of_floor_dont_clash` | P06 at `y=20`, just after P05 ends at 19.9. | Rows apart along y don't clash. |
| `test_moving_a_row_onto_another_is_refused` | Moves P06 onto P05 by setting `x`. | Moving a row is checked as well. |
| `test_archived_rows_dont_block` | Archives P05, then creates P06 in the same place. | An archived row blocks nothing. |
| `test_reactivating_onto_a_newer_row_is_refused` | Archives P05, creates P06 in its place, then un-archives P05. | Bringing a row back is checked too (`active` triggers the layout check). |
| `test_rows_in_other_warehouses_dont_clash` | Makes a second warehouse and a P05 there. | Position and code only matter inside one warehouse. |
| `test_shrinking_the_building_below_a_row_is_refused` | A row at `x=36.7`, then the building length is set to 37. | `_check_wh3d_size` (section 12) refuses and names `P05`. |
| `test_all_31_template_rows_are_valid` | Creates all 31 rows from `template_rows()` in one call, pallets in one zone and shelves in another. | The template warehouse layout passes every layout rule. |

The `savepoint` in the first layout test (comment on line 130) is there because a refused create must not leave its row behind for the next case.

### Why it's needed

- **Safety net:** every rule in section 8 has a test. If a later change breaks a rule, a test fails straight away.
- **Rules written as examples:** each test shows a concrete case, such as "P06 at x=10.2 overlaps P05", which is easier to read than the rule itself.
- **Edge cases:** touching a wall, touching another row, archived rows and moving rows are the cases that are easy to get wrong.
- **The editor depends on it:** the editor can only save what these rules accept.

---

## 17. `tests/test_location_generator.py`

**The file in one sentence:** it checks that a rack row builds the right tree of Inventory locations (the right number, names, paths and settings), that rebuilding it is safe, and that Odoo's own putaway can use the result.

It tests the location generation from section 8, chunks 5 and 6 (`_location_tree` and `_sync_locations`). It has 10 tests.

### Words you will see

| Word | Plain meaning |
|---|---|
| **`mapped('name')`** | Takes the `name` of every record in a group and gives them back together. |
| **`filtered(lambda s: ...)`** | Keeps only the records where the little function is true. |
| **`search_count`** | Counts the records that match, without loading them. |
| **putaway rule** | An Odoo rule that decides where incoming stock is stored, for example "this product goes into zone PR, in the closest free slot". |
| **storage category** | A label on a location that tells putaway what the location can hold. |

### Lines 1–4: imports

- `time` is used by the last test to measure how long something takes.
- `ValidationError` and `TransactionCase` are used as in section 16.
- This file does **not** use the helpers from `common.py`. It builds its own rows below.

### Lines 9–18: setup

`setUpClass` runs once and prepares what every test shares:

- The default warehouse and its main stock location (`cls.stock`).
- Two zones under it, both Internal: **PR** for pallet rows and **SH** for shelving.
- A storage category called "Pallet rack – bulk".
- `cls.Row`, the rack row table.

### Lines 20–40: three helpers

- `_pallet(**overrides)` creates pallet row **P05** (7 bays, 5 levels, 2 slots) in zone PR, with the storage category. `vals.update(overrides)` lets a test change any value.
- `_shelf(**overrides)` creates shelving row **S04** (16 bays, 5 levels, 1 slot) in zone SH, with no storage category.
- `_nodes(row, node)` finds the locations of one row that are of one type (`row`, `bay`, `level` or `slot`).

### The tests

| Test | What it does | What it proves |
|---|---|---|
| `test_pallet_row_creates_70_slots` | Creates P05 and counts its slots. Checks the first name `P05-01-1-A`, the last name `P05-07-5-B`, and `slot_count`. | 7 × 5 × 2 = 70 slots, with the right names. |
| `test_pallet_tree_shape` | Counts the other node types. | 1 row node, 7 bays, 35 levels. |
| `test_pallet_slot_full_path_and_indices` | Looks at slot `P05-03-2-A`. | Its full path is `WH/Stock/PR/P05/P05-03/P05-03-2/P05-03-2-A`. Bay, level and position are (3, 2, 1). It is Internal and has the storage category. |
| `test_only_slots_carry_storage_category` | Checks the row, bay and level nodes. | None of them has a storage category, and all are Internal. |
| `test_shelf_row_creates_80_bins_without_level_nodes` | Creates S04. | 16 × 5 × 1 = 80 bins and no level nodes. Slot `S04-10-3` has the path `WH/Stock/SH/S04/S04-10/S04-10-3` and indices (10, 3, 1). |
| `test_generating_twice_creates_no_duplicates` | Counts the row's locations, presses "Regenerate Locations" (`action_generate_locations`), and counts again. | The count doesn't change, and it is 1 + 7 + 35 + 70 = **113**. |
| `test_regenerate_recreates_missing_slot` | Deletes one slot by hand, then regenerates. | The missing slot comes back (70 again). |
| `test_zone_location_must_be_internal` | Uses a virtual zone. | A `ValidationError`. A virtual zone would cut every generated path short. |
| `test_closest_putaway_lands_in_a_slot` | Creates a storable product and a putaway rule, then asks Odoo where one unit of it would go. | The answer is a **slot** of the row. |
| `test_fourteen_pallet_rows_generate_quickly` | Creates 14 pallet rows, `P01` to `P14`, 2.6 m apart, and times it. | There are 980 slots, and it took under 30 seconds. |

### What the interesting tests show

**The path test (lines 57–63).** The long path, with `P05`, `P05-03` and `P05-03-2` between the zone and the slot, proves the parents are linked in the right order. A pallet slot also stores its bay, level and position as numbers, so the 3D view can place it without reading the name.

**The shelf test (lines 73–80).** A shelf row has no level nodes, so the path goes from the bay straight to the slot. The slot still stores its level (3) as a number.

**Regenerating (lines 82–95).** Pressing the button twice makes no duplicates, and a missing slot is created again. That is what `_sync_locations` promises: it compares what exists with what is wanted. It is how a row heals after an import or a script left its locations in a bad state.

**The putaway test (lines 103–112).** This is the main reason for the decision "only slots get the storage category" (section 8, chunk 6).

```python
self.env['stock.putaway.rule'].create({
    'location_in_id': self.stock.id, 'location_out_id': self.pr.id, 'product_id': product.id,
    'sublocation': 'closest_location', 'storage_category_id': self.pallet_cat.id,
})
dest = self.stock._get_putaway_strategy(product, quantity=1)
```

- The rule says: stock arriving in the main stock location goes into zone PR, and Odoo should pick the closest location that has this storage category.
- `_get_putaway_strategy` is the Odoo method that makes that choice. The test asks it for one unit of the product.
- The result must be a slot of our row (`dest.wh3d_rack_row_id == row` and `dest.wh3d_node == 'slot'`). If bays and levels also had the category, Odoo could pick one of them instead.
- This is also the **standard putaway** behaviour that the research comparison is based on (the project plan).

**The speed test (lines 114–121).** A real warehouse has 14 pallet rows. This test builds 14 and measures the time with `time.time()`. It checks that the warehouse then has 14 × 70 = **980** slots, the number in the project spec, and that it took less than 30 seconds. The message shows the actual time if it fails.

### Why it's needed

- It proves the generator builds what section 8 describes: the right counts, names, paths and indices.
- It guards the "regenerate" promise: repeating is safe, and missing pieces come back.
- The putaway test connects the module to Odoo's own putaway logic.
- The speed test catches a slowdown, for example if a later change makes the sync run one query per location.

---

## 18. `tests/test_location_sync.py`

**The file in one sentence:** it checks that when a rack row is edited, archived or deleted, its Inventory locations follow it correctly, and that stock is never lost on the way.

It tests `_sync_locations`, `_check_removal` and the `write` / `unlink` methods from section 8 (chunks 3, 5 and 6). It has 20 tests. The class comment says it: "keeps its locations in step, never losing stock".

### Words you will see

| Word | Plain meaning |
|---|---|
| **`setUp`** | Runs before **each** test. (`setUpClass` runs once for the whole class.) Here it builds a fresh row P05 for every test. |
| **`assertRaisesRegex(Error, 'text')`** | Like `assertRaises`, but the error message must also contain that text. It checks the *right* problem was reported. |
| **transfer (`stock.picking`)** | A planned stock movement, such as a receipt from a supplier. |
| **confirm (`action_confirm`)** | Marks a transfer as expected. The stock is not there yet, but it is on its way. |
| **`(0, 0, {...})`** | Odoo's older way to say "create this related record now". It is how a transfer gets its move in one call. |

### Lines 8–15: `setUpClass` (once)

- The default warehouse and its stock location.
- A zone `PR` (Internal) under the stock location.
- A storage category "Pallet rack – bulk".
- A storable product, "Rice 25 kg", used whenever a test needs stock.

### Lines 17–23: `setUp` (before every test)

Creates rack row **P05** (7 bays, 5 levels, 2 slots) in zone PR. Each test therefore starts with the same 113 locations. Odoo throws away the changes after every test, so one test can't affect the next.

### Lines 25–36: four helpers

- `_locations(node=None, active=True)` returns the row's locations. By default only the active ones. With `active=False` it returns the archived ones. A `node` limits it to `row`, `bay`, `level` or `slot`. It uses `active_test=False` so the domain, not Odoo, decides what is hidden.
- `_slot(name)` finds one of the row's locations by name, archived or not.
- `_put_stock(location, qty=10)` puts 10 units of the product straight into a location, using `_update_available_quantity`. It is a quick way to make a location "hold stock".
- `_confirmed_receipt_into(location)` (lines 145–156) builds a receipt from the supplier location into a location and confirms it, so 5 units are **on their way** there.

### The tests: editing and reshaping

| Test | What it does | What it proves |
|---|---|---|
| `test_rename_keeps_records_and_stock` | Puts stock in slot `P05-03-2-A`, then renames the row `P05` to `P15`. | The **same** location records are kept. The slot becomes `P15-03-2-A` with the new path, and still holds 10. |
| `test_moving_on_floor_plan_leaves_locations_alone` | Changes `x`, `y`, `bay_width`, `depth` and `level_height`. | No location name changes. Only shape fields touch locations. |
| `test_growing_adds_slots` | `bays = 8`. | 80 slots, and `P05-08-5-B` exists and is active. |
| `test_shrinking_empty_row_archives_removed_slots` | `bays = 6`. | 60 slots remain. 16 locations are archived: bay 7, its 5 levels and its 10 slots. |
| `test_regrowing_reuses_archived_slots` | `bays = 6`, then `bays = 7` again. | The **same** slot record comes back to life. There are 70 slots and nothing is left archived. |
| `test_fewer_levels_archives_top_levels` | `levels = 4`. | 56 slots and 28 level nodes. |
| `test_storage_category_change_reaches_slots_only` | Sets a storage category on the row. | Slots get it. Bays don't. |
| `test_pallet_to_shelf_restructures_tree` | Changes `kind` to shelf and `slots_per_level` to 1 together. | 35 slots and no level nodes. Slot `P05-03-2` now sits directly under the bay. |
| `test_moving_to_another_zone_moves_the_subtree` | Gives the row a new zone `PR2`. | The slot's path moves under `PR2`. The whole tree follows its top node. |

The pallet-to-shelf test has a comment worth reading (line 108): the old level node `P05-03-2` is archived and has the same name as the new slot, so the test looks among **active** slots only. The first slot of each level survives. It is renamed (`P05-03-2-A` becomes `P05-03-2`) and moves up to the bay. The second slots and the level nodes are archived.

### The tests: protecting stock

| Test | What it does | What it proves |
|---|---|---|
| `test_shrinking_over_stock_is_refused` | Stock in `P05-07-1-A`, then `bays = 6`. | A `UserError` naming that slot, and still 70 slots. |
| `test_shrinking_over_reserved_or_incoming_stock_is_refused` | A confirmed receipt into `P05-07-1-A`, then `bays = 6`. | Stock that is only **on its way** also blocks the change. |
| `test_archiving_row_archives_its_locations` | Archives the row, then restores it. | Archiving the row archives its locations. Restoring brings back all 70 slots with none left archived. |
| `test_archiving_row_with_stock_is_refused` | Stock in `P05-01-1-A`, then `action_archive()`. | Refused, and the row stays active. |
| `test_deleting_row_archives_its_locations` | Deletes the row. | Its locations **still exist** but are all archived. They are not deleted. |
| `test_deleting_row_with_stock_is_refused` | Stock in `P05-01-1-A`, then `unlink()`. | Refused, and the row still exists. |

### The tests: fixes found in code review

These come from the comment "Code-review fixes (T3c)" on line 143. The numbers in the comments (#1, #2, #4, #5, #6) are the review findings.

| Test | What it does | What it proves |
|---|---|---|
| `test_pallet_to_shelf_keeps_stock_in_surviving_slot` (#1) | Stock in slot A, then pallet to shelf. | The slot survives (renamed, moved up), so its stock **must not block** the change. The stock is still 10. |
| `test_shrinking_over_transfer_into_user_sublocation_is_refused` (#2) | A hand-made location `Left` under slot `P05-07-1-A`, with a confirmed receipt into it, then `bays = 6`. | A hand-made bin below a removed slot counts too. The error names `Left`. |
| `test_falsy_active_value_still_checks_transfers` (#4) | `write({'active': 0})` with a receipt on its way. | `0` is treated like `False`. The change is still checked and refused. |
| `test_regenerate_checks_transfers_before_archiving_extras` (#5) | A hand-made stray slot `P05-09-1-A` (bay 9 of a 7-bay row) with a receipt into it, then "Regenerate Locations". | The button checks stock on extras before archiving them. The stray stays active. |
| `test_changing_warehouse_of_a_row_with_locations_is_refused` (#6) | Moves the row to a second warehouse. | Refused: locations can't change company. |

### Why it's needed

- It is the safety net for the module's most important promise, **never lose track of real stock**. Every way a row can change (rename, shrink, reshape, archive, delete, regenerate) has a test with and without stock.
- It pins down the "same records, not recreated" design, because stock is attached to location records.
- Each review finding has its own test, so the same mistake can't come back unnoticed.

---

## 19. `tests/test_layout_save.py`

**The file in one sentence:** it checks the editor's Save call, `wh3d_save_layout` from section 8 (chunk 4), end to end: it works for rows and areas, it is all-or-nothing, it only accepts allowed fields, and it only lets managers use it.

It has 21 tests: 10 about rack rows, then 11 about floor areas and dock doors, which "ride in the same save" (the comment on line 105).

### Words you will see

| Word | Plain meaning |
|---|---|
| **all or nothing** | If any part of a save is refused, none of it is kept. The data looks as if the save never happened. |
| **end state** | How the layout looks after every edit in the save has been applied. Only that is checked for overlaps. |
| **`tmp_id`** | A temporary number the editor gives to something it has just drawn. The server replies with the real id for each one. |
| **`**pos`** | Collects any named values into a dictionary. Used by the `door` helper on line 190. |

### Lines 7–20: setup

- `setUpClass` gets the default warehouse and creates a zone with `create_zone` (section 15).
- `setUp` runs before every test and creates two rows with `create_p05` (section 15):
  - **P05** at x 9.7–10.8.
  - **P06** at x 20.5–21.6.
- They are 9.7 m apart on the floor, so they don't overlap.

### Lines 22–35: helpers

- `_save(create, write, delete, areas)` builds the `changes` dictionary the editor would send and calls `wh3d_save_layout`. The `areas` part is only added when a test gives it.
- `_area(**overrides)` creates a floor area called "Receiving" at x 25, y 25, size 5 × 5.
- `_slots(row)` counts the slot locations of a row.

### The tests for rack rows

| Test | What it does | What it proves |
|---|---|---|
| `test_move_and_edit` | Moves P05 and gives it 8 bays. | The values change, and the slots grow to 80 (locations follow the row). |
| `test_create_returns_new_ids_and_builds_locations` | Creates a new row `P07` with `tmp_id` −1. | The reply maps −1 to the real id. The row gets the existing pallet zone and 70 slots. The returned layout lists P05, P06 and P07. |
| `test_new_shelf_row_without_a_shelf_zone_goes_under_stock` | Creates a shelf row when no shelf row exists. | With no sibling row to copy a zone from, it goes under the main stock location (`_wh3d_default_zone`). |
| `test_delete` | Deletes P06. | It is gone. |
| `test_swapping_two_rows_is_allowed` | Sends P05 to P06's place and P06 to P05's place in one save. | Each step alone would overlap the other row. Only the end state is checked, so it works. |
| `test_overlap_refuses_everything` | Sends a valid move of P06 and a move of P05 that overlaps P06. | Error "overlap", and P06 did not move either. |
| `test_stock_guard_refuses_everything` | Puts stock in `P05-07-1-A`, then sends a valid move of P06 and `bays = 6` for P05. | Error naming the slot. P06 is back at its old place and P05 still has 7 bays. |
| `test_only_layout_fields_are_accepted` | Tries to set `warehouse_id`, `active`, `storage_category_id` and `create_uid` through the editor. | Each is refused, and the error names the field. |
| `test_rows_of_another_warehouse_are_refused` | Tries to edit and to delete a row of a second warehouse. | Both refused, and the row still exists. |
| `test_stock_user_cannot_save` | A user in the Inventory User group calls the save. | `AccessError`. The method relies on the normal access rules (section 3). |

### The tests for floor areas and docks

| Test | What it does | What it proves |
|---|---|---|
| `test_area_create_write_delete_in_one_save` | One save creates an area "Packing" and a dock "Door 1", edits "Keep" and deletes "Drop". | All three kinds of change work. The new colour and kind are kept. The reply layout lists the right names, each with a `color`. |
| `test_rows_and_areas_save_together` | One save edits P05 and creates an area "Office". | Rows and areas can travel in the same save. |
| `test_area_overlapping_a_row_refuses_everything` | A valid row edit plus an area edit that lands on P06. | Error "overlap", and neither the area nor the row moved. |
| `test_moving_a_row_onto_an_area_refuses_everything` | Moves P06 onto an area and renames the area in the same save. | Error "overlap", and the rename was undone too. |
| `test_swapping_a_row_and_an_area_is_allowed` | The row moves into the area's spot as the area moves into the row's old spot. | Only the end state is checked, so a swap between a row and an area works too. |
| `test_floating_dock_refuses_everything` | A valid row edit plus a dock in the middle of the floor. | Error "wall", and the row edit was undone. |
| `test_area_outside_building_refuses_everything` | An area 20 m wide that starts at x = 50. | Error "inside" (the building is 60 m long). |
| `test_only_area_fields_are_accepted` | Tries to set `warehouse_id`, `create_uid` and `company_id` on an area. | Each is refused, and the error names the field. |
| `test_areas_of_another_warehouse_are_refused` | Tries to edit and delete an area of a second warehouse. | Both refused, and the area still exists. |
| `test_stock_user_cannot_save_areas` | An Inventory User tries to delete an area. | `AccessError`. |
| `test_a_warehouse_can_be_built_from_nothing_in_one_save` | See below. | A whole empty building can be laid out in one save. |

### The parts worth understanding

**The "refuses everything" pattern.** Several tests send one valid change together with one invalid change. For example, line 69 moves P06 (valid on its own) and line 70 moves P05 onto it. The test then checks that **both** are unchanged (lines 71–72). That is the proof of "all or nothing". Without it, you could only know the bad change was refused.

**Swaps (lines 62–65 and 145–150).** In a swap, the first edit moves a row on top of the other. If the overlap were checked after each edit, the save would fail. Section 8 solves this with the `wh3d_defer_layout_check` flag and one check at the end. These tests prove the flag works.

**`result['created'][-1]` is not "the last item".** `result['created']` is a **dictionary** that maps each `tmp_id` to the real id. The `-1` is the key, the `tmp_id` the test chose. It is the first (and only) new row, not the last element of a list. The same goes for `created_areas`.

**Building a warehouse from nothing (lines 186–209).**
- It makes a new warehouse `WHB`, 50 × 30 m, with no areas.
- Then one save sends everything a manager's first layout would contain: one pallet row `P01`, one area "Receiving", and four dock doors, one on each wall (front at y = 0, back at y = 28.4 so it ends at 30, left at x = 0, right at x = 48.4 so it ends at 50).
- The `door(n, **pos)` helper on line 190 builds each dock dictionary. Its `tmp_id` is `-n - 1`, so the doors get −2, −3, −4 and −5, and none clashes with the area's −1. Areas and docks share one `created_areas` dictionary, so their temporary ids must be different. The project notes record that this test was fixed for exactly that clash.
- It checks the layout has `P01`, the five area names, five created areas, and 70 slots.

### Why it's needed

- It proves the editor's one Save call is safe. The editor trusts it completely, so every promise from section 8 has a test: atomic, end-state checks, whitelisted fields, same-warehouse only, stock guard, and manager-only.
- It covers rows and areas together, because the editor saves them together.
- The last test is the closest thing in the file to what the editor really sends.

---

## 20. `tests/test_scene_data.py`

**The file in one sentence:** it checks the data the 3D view is given, `wh3d_get_scene`, `wh3d_get_slots` and `wh3d_get_layout` from section 12: the right shape, the right numbers for slot capacity and fill, a fixed number of database queries, and access for normal users.

It has 12 tests. The class comment says it: "everything the 3D view draws, in one call".

### Words you will see

| Word | Plain meaning |
|---|---|
| **`Form`** | A test tool that behaves like a person filling in a screen. You set fields on it and call `save()`. It can only set fields that are on that screen. |
| **`assertAlmostEqual(a, b, places=3)`** | Passes if the two numbers are equal to 3 decimal places. Used for decimal values, which are never stored exactly. |
| **`assertIsNone`** | Passes if the value is `None`, meaning "no value". |
| **`next(... for ... if ...)`** | Takes the first item that matches. Used by `_scene_slot`. |

### Lines 7–37: `setUpClass` (once)

It builds a small world that every test reads:

- The default warehouse and a zone `PR`.
- Row **P05** (7 bays, 5 levels, 2 slots), through the helper `_row_vals(code, x)` that returns the row values. The comment on line 14 gives the capacity of one slot: (2.7 ÷ 2) × 1.1 × 1.8 = **2.673 m³**.
- An area "Receiving".
- Three products:
  - **Rice**, 1.2 × 1.0 × 1.1 m = **1.32 m³** per unit.
  - **Oil**, 0.3 × 0.3 × 0.4 m = **0.036 m³** per unit.
  - **Mystery box**, with no dimensions.

Because this runs once, the data is shared. Every test still starts clean, since Odoo undoes each test's changes afterwards.

### Lines 39–46: helpers

- `_slot(name)` finds a slot by name in this warehouse.
- `_put(product, slot_name, qty)` puts stock into a slot.
- `_scene_slot(scene, name)` takes the first slot of the scene whose `code` matches. If there is none, it fails with a `StopIteration` error, which is a confusing message.

### The tests

| Test | What it does | What it proves |
|---|---|---|
| `test_scene_has_building_areas_rows_and_slots` | Loads the scene. | The building is 60 × 40 × 10. It lists the area "Receiving" and the row P05 (7 bays), and has 70 slots. |
| `test_slot_carries_indices_and_capacity` | Looks at slot `P05-03-2-A`. | Its location id and row id are right. Bay, level, position are (3, 2, 1). Capacity is 2.673 m³. The path is `WH/Stock/PR/P05/P05-03/P05-03-2/P05-03-2-A`. |
| `test_empty_slot_has_no_stock` | Looks at an empty slot. | `stock` is `None`. |
| `test_stocked_slot_reports_product_volume_and_fill` | One rice in a slot. | The slot reports the product id, name, code, quantity 1 and unit name. Used volume is 1.32 m³ and fill is 1.32 ÷ 2.673 (about 49%). `mixed` is false. |
| `test_mixed_slot_names_largest_quant_and_sums_volume` | One rice and five oil in the same slot. | `mixed` is true. The product shown is the **oil**, because 5 units beat 1. Used volume is 1.32 + 0.18 = 1.5 m³. |
| `test_product_without_dimensions_gives_no_fill` | Three Mystery boxes. | The quantity is shown (3), but `used_m3` and `fill` are `None`. |
| `test_archived_slots_are_left_out` | `bays = 6`. | The scene has 60 slots, not 70. |
| `test_get_slots_returns_only_the_asked_slots` | Asks for two slots **and** the zone `PR`. | Only the two slots come back, because the zone is not a slot. The slot with rice has quantity 1. |
| `test_layout_has_building_areas_and_rows_but_no_slots` | Loads the layout. | It has exactly the keys `warehouse_id`, `name`, `building`, `areas`, `rows`. Its rows equal the scene's rows. |
| `test_query_count_does_not_grow_with_slots` | Counts the database queries. | See below. |
| `test_stock_user_can_load_the_scene` | An Inventory User loads the scene. | It works, with 70 slots. |
| `test_product_form_has_dimensions` | Fills in a product form with a name and three sizes, then saves. | The sizes were saved, and the variant reads 0.2 for the height. |

### The parts worth understanding

**The numbers are worked out by hand.** The comments (lines 14, 20 and 83) show the maths: slot 2.673 m³, rice 1.32 m³, five oil 0.18 m³. The test does not copy the formula from the code. It checks the code against a separate calculation, which is why it can catch a mistake in the formula.

**Which product is shown in a mixed slot (lines 81–87).** The product named is the one with the **largest quantity**, not the largest volume. Here that is the oil (5 units), even though the rice takes more space. The volume, though, adds up **all** products. This is the "biggest quant" rule from section 12.

**Unknown size means unknown fill (lines 89–94).** A product with no dimensions still shows its quantity, but fill and used volume are `None`, and not 0. The screen can then show "unknown" and not "empty".

**Counting queries (lines 113–126).**

```python
def count_queries():
    self.env.invalidate_all()
    before = self.cr.sql_log_count
    self.warehouse.wh3d_get_scene()
    return self.cr.sql_log_count - before
```

- `invalidate_all()` clears Odoo's memory of what it already read, so the scene really has to ask the database again.
- `cr.sql_log_count` counts the queries sent so far. The number before and after, subtracted, is how many the scene needed.
- The test first checks the counter is greater than 0 (`assertGreater`), so it can't pass just because nothing is being counted.
- Then it adds two more rows and another stocked slot, which takes the scene from 70 to 210 slots, and counts again. The count must be **exactly the same**.
- That proves the claim in section 12: the scene is built in a fixed number of queries, however many slots there are.

**The product form test (lines 133–140).** `Form` can only set fields that are on the screen. So this test proves that the product form really shows the three size fields. It also proves that the variant can read what was saved on the template (section 14).

### Why it's needed

- **A contract with the browser.** The JavaScript expects exact names (`building`, `areas`, `rows`, `slots`, and the slot and stock keys). A renamed key would break the 3D view, and these tests catch that.
- **The maths is checked:** capacity, used volume, fill, mixed slots, unknown sizes.
- **The speed promise is checked** by counting queries, not by timing.
- **Normal users can load the scene,** not only administrators.

---

## 21. `tests/test_bus.py`

**The file in one sentence:** it checks that stock changes in rack slots are announced on the bus (section 13) exactly as promised: once per transaction, only for slots, to the right group, and never for reservations.

It has 6 tests. The class comment says it: "Stock changes in rack slots are announced on the bus, once per transaction".

### Words you will see

| Word | Plain meaning |
|---|---|
| **`bus.bus`** | The table where Odoo queues notifications before sending them to browsers. The tests read it to see what would be sent. |
| **channel** | The "address" of a message. Here it is the Inventory User group. The bus stores it as `[database, model, id]`. |
| **payload** | The content of a message. Ours is `{'location_ids': [...]}`. |
| **`json.loads`** | Turns text in JSON format into a Python list or dictionary. The bus stores messages as JSON text. |
| **`precommit.run()`** | Runs the "just before commit" functions now. See below. |

### Lines 11–21: setup

`setUpClass` runs once:

- The default warehouse and its stock location.
- Row P05, made with `create_p05` (section 15), so its slots exist.
- Three slots, sorted by name: `P05-01-1-A`, `P05-01-1-B` and `P05-02-1-A`.
- A storable product, "Rice 25 kg", and the supplier location.

### Lines 23–31: `_stock_notifications`, the key helper

```python
def _stock_notifications(self):
    self.env.cr.precommit.run()
    messages = []
    for notif in self.env['bus.bus'].sudo().search([]):
        message = json.loads(notif.message)
        if message['type'] == 'warehouse_3d/stock':
            messages.append((json.loads(notif.channel), message['payload']))
    return messages
```

- In section 13, the module registers a function to run **just before commit**. A test never commits, because Odoo undoes the transaction when the test ends. So the test runs those functions by hand: `self.env.cr.precommit.run()`. The comment says "as a real commit would".
- Then it reads every queued bus message, turns the JSON text into data, and keeps only ours (type `warehouse_3d/stock`).
- It returns a list of `(channel, payload)` pairs. `.sudo()` skips the user's access rules so the test can read the whole bus table.

**Without that first line no message would appear.** The hook would simply never have run.

### Lines 33–48: `_receive`

This helper does a real stock receipt, the way a warehouse worker would:

1. Create a receipt (a transfer of type "receipt") from the supplier, with **one move per destination**, one unit each.
2. `action_confirm()` confirms it.
3. For each move, set `quantity = 1` and `picked = True`, meaning "this was actually picked".
4. `button_validate()` presses the Validate button, and the test checks the transfer is `done`.

So the tests go through the same path Odoo uses, not a shortcut.

### The "start clean" step

Most tests begin with the same two lines:

```python
self._stock_notifications()
self.env['bus.bus'].sudo().search([]).unlink()
```

The first runs any pending hook, so nothing is left over from setup. The second deletes every queued message. Now the test counts only the messages **it** causes.

### The tests

| Test | What it does | What it proves |
|---|---|---|
| `test_three_line_receipt_sends_one_message_with_three_slots` | Receives 1 unit into each of 3 slots in one receipt. | **One** message, listing all three slot ids. Its channel is `[db, 'res.groups', <Inventory User group id>]`, so it goes to everyone in that group. |
| `test_stock_outside_rack_slots_sends_nothing` | Receives into the main stock location, not a slot. | No messages. Only rack slots are announced. |
| `test_inventory_adjustment_is_announced` | A counted quantity of 4 in a slot, then Apply (the Physical Inventory path). | One message with that slot's id. |
| `test_direct_quantity_update_is_announced` | Adds 4 to a slot with `_update_available_quantity`. | The change is announced, even from this lower-level call. |
| `test_reservations_send_nothing` | Sets `reserved_quantity = 2` on a quant that already has stock. | No messages. The 3D view doesn't show reservations (the comment on line 88). |
| `test_moving_stock_between_slots_announces_both` | Moves a quant from the first slot to the second. | One message with **both** slot ids. |

### The parts worth understanding

**Once per transaction (test 1).** A three-line receipt touches three quants, and Odoo writes to quants more than once per line. The test shows the result is still a single message. That is the whole point of the "collect, then send before commit" design in section 13.

**Both places on a move (last test).** When a quant moves, `write` remembers where it was and where it is now (`before | self.location_id` in section 13). The last test shows both slots are in the message, so the 3D view clears the old slot and fills the new one.

**Three ways in, all caught (tests 1, 3 and 4).** A receipt, an inventory adjustment and a direct quantity update are three different Odoo paths. All of them end in quant `create` or `write`, and that is where section 13 hooks in, so all three are announced.

**The audience (line 60).** `channel[1:]` drops the database name from the channel and compares the rest: model `res.groups` and the id of `stock.group_stock_user`. So the message is addressed to the Inventory User group.

### What is *not* tested here

- Deleting a quant (the `unlink` path in section 13).
- A transaction that is rolled back (no message should be sent).
- The browser side: that is a different file.

### Why it's needed

- It guards the live-update promise from section 13: once per transaction, only slots, both slots on a move, no reservation noise, and the right audience.
- Without it, a later change to quant handling could silently stop live updates. The 3D view would just stop refreshing, and nothing would fail.

---

## 22. `static/src/view3d/layout.js`

**The file in one sentence:** it turns the floor plan numbers from the server (building size, rows, areas, docks, slots) into the sizes and positions of the boxes the 3D view will draw, using plain maths with no drawing code.

This is the first JavaScript file we cover. The header comment gives the key idea: "no Three.js, no DOM, so it can be unit-tested". Three.js is the 3D library, and the DOM is the web page itself. A file that touches neither can be tested with plain numbers. The geometry was ported from the standalone prototype (`docs/warehaven-3d-prototype.html`).

### JavaScript words you will see

| Word | Plain meaning |
|---|---|
| **`export function f() {}`** | Makes `f` usable from other files, which then `import` it. Like a non-static function declared in a header. |
| **`const` / `let`** | `const` is a name that can't be reassigned. `let` can be. |
| **array `[a, b, c]`** | A list. Here it is often a tiny fixed bundle, like a small struct. |
| **destructuring** | `const [cx, cz] = f()` unpacks a list into names. `const { length: L, width: W } = building` takes `length` and `width` out of an object and calls them `L` and `W`. |
| **arrow function** | `(a, b) => a + b` is a small inline function, like a lambda. |
| **`.map`, `.forEach`, `.some`, `.sort`** | Helpers on lists. `map` builds a new list, `forEach` runs something for each item, `some` is true if any item passes, `sort` orders the list. |
| **`cond ? a : b`** | The same conditional expression as in C. |
| **`...list`** | "Spread": passes the items of a list as separate arguments. |
| **`for (const x of list)`** | Loop over the items of a list. |

### Lines 1–9: the two coordinate systems and the box

Every function depends on these rules, so read them first.

- **Floor plan** (what the server and the editor use): metres from one corner of the building. `x` runs along the length, `y` along the width.
- **World** (what Three.js uses): the building is **centred** on the origin. Plan `x` becomes world `x`, plan `y` becomes world `z`, and the height is world `y` (up).
- **A box** is six numbers: `[centreX, centreY, centreZ, sizeX, sizeY, sizeZ]`. Every shape in this file is returned as one or more boxes.
- **A rack row** runs along plan `y`: its depth is along `x` and its bays are along `y` (as in section 8).

### Lines 11–13: `toWorld`

```js
export function toWorld(building, x, y) {
    return [x - building.length / 2, y - building.width / 2];
}
```

Moves a plan point from "origin at a corner" to "origin at the centre". It returns `[worldX, worldZ]`. Almost every other function calls it first.

### Lines 15–32: `floorGeometry`

Returns `{ floor, gridLines, curbs }`:

- **`floor`:** one flat slab, `[0, -0.05, 0, L, 0.1, W]`. It is 0.1 m thick and centred at −0.05, so its **top face is at height 0**.
- **`gridLines`:** a line every 5 m in each direction, each written as `[x1, z1, x2, z2]`. The `+ 1e-9` in the loop conditions stops a rounding error from losing the last line.
- **`curbs`:** four low walls (0.4 m high, 0.2 m thick) around the edge: front, back, left and right. (The code says "curbs", the comment says "kerbs": same thing.)

### Lines 34–38: `areaBox`

A floor area becomes a thin coloured slab. The area's centre is its corner plus half its size, converted with `toWorld`. The slab is 0.02 m thick and sits at height 0.012. Its size is `width` along x and `depth` along z. This matches section 10: for an area, `width` runs along x.

### Lines 40–53: `areaLifts`

**The problem:** two flat shapes at exactly the same height flicker when drawn on top of each other. This is called z-fighting. A smaller area inside a bigger one (for example "Packing" inside "Shipping") would flicker.

**The fix:** lift each area off the floor by a different small amount, with **bigger areas lowest**.

```js
const bySize = areas.map((a, i) => i).sort((i, j) => areas[j].width * areas[j].depth - areas[i].width * areas[i].depth || i - j);
const lifts = new Array(areas.length);
bySize.forEach((index, rank) => {
    lifts[index] = Math.min(rank, 3) * 0.01;
});
```

- The first line makes a list of positions (0, 1, 2, …) and sorts them from the biggest area to the smallest. `|| i - j` breaks a tie by the original order.
- Then the biggest area gets lift 0, the next 0.01 m, the next 0.02 m, and everyone from the fourth biggest on gets 0.03 m. `Math.min(rank, 3)` is the cap.
- The result is a list in the **original order** of the areas.

**The documented shortcut (lines 43–44).** This is a `shortcut:` comment, the marker for a known limit. The lift stops at three steps so that the top of a stack (5.2 cm) stays under a dock pad (6 cm). Areas nested more than four deep share the top level. The comment says to upgrade only if anyone does that.

### Lines 55–58: `areaColor`

```js
return /^#[0-9a-f]{6}$/i.test(area.color) ? parseInt(area.color.slice(1), 16) : fallback;
```

- The pattern is `#` plus exactly six hex characters, case-insensitive (`i`). It is the same rule as `COLOR_RE` in section 10, checked again in the browser.
- If it matches, `slice(1)` drops the `#` and `parseInt(..., 16)` reads the rest as a hex number, which is the form Three.js wants.
- If it doesn't match, it returns the `fallback` colour.

### Lines 60–90: `dockGeometry`

Returns `{ pad, frame }`:

- **`pad`:** a flat slab on the floor, 0.06 m thick, the size of the dock.
- **`frame`:** a door frame, but only if the dock touches a wall. Otherwise it is an empty list.

How it decides which wall:

- The comment explains: a door is wider along the wall than it is thick. So `width >= depth` means a front or back wall, and the opening runs along x. Otherwise it is a side wall, and the opening runs along y.
- For a front or back door, `wallZ` is found with a pair of conditions: if the dock's far edge reaches the far wall, `wallZ` is just outside that wall (`W / 2 + 0.1`). If its near edge is at 0, it is just outside the near wall. Otherwise it is `null`. The `0.01` is a tolerance.
- If there is a wall, the frame is three boxes: two **posts** (0.15 × 3.6 × 0.15 m) either side, and a **top bar** across them at height 3.6. The side-wall case is the same with x and z swapped.

This is the browser-side partner of the rule in section 10 ("a dock must touch a wall"). A dock that touches no wall is not an error here, it just gets no frame.

### Lines 92–121: `rackGeometry`

Builds the steel of one rack row and returns `{ uprights, beams, decks, topHeight }`.

- `length = bays × bay_width` and `height = levels × level_height`.
- **Uprights** (the vertical posts): one line of posts at every bay boundary, which is `bays + 1` lines, on both the front and back faces. A pallet post is 0.1 m thick, a shelf post 0.04 m. A pallet row with 7 bays has 8 × 2 = **16 uprights**.
- **Beams** (pallet only): two long horizontal rails at each level height from level 1 up to `levels − 1`, one on each face. With 5 levels that is 4 heights × 2 = **8 beams**, each as long as the whole row.
- **Decks** (shelving only): one flat board per level, 0.025 m thick, as deep as the row and as long as the row.
- `topHeight` is the height of the posts. Shelving adds 0.1 m.

### Lines 123–144: `slotBox`

The space that one slot takes up. The comment says it is used for click targets and, later (task T8), for stock boxes.

- `slot.bay`, `slot.level` and `slot.position` are **1-based** (as stored on the location, section 9), so the code subtracts 1 to get zero-based numbers `b`, `l` and `p`.
- `slotWidth = bay_width / slots_per_level`. This is the same share of the bay as in the capacity formula in section 12.
- `xc` is the centre of the row's depth. `zc` is the centre of the slot along the row: bay start plus `(p + 0.5)` slot widths.
- **Pallet:** the slot's floor `base` is 0 on level 1, otherwise just above the beam below (`l × level_height + 0.06`, since the beam is 0.12 m tall). The height is `level_height − 0.2`, so the box leaves space for the beam above.
- **Shelf:** `base` is the top of the deck (`0.1 + l × level_height + 0.0125`) and the height is `level_height − 0.04`.
- It returns `{ base, box }`. The boxes are made slightly different in size from the slot (for example `slotWidth − 0.05`) so neighbours don't touch.

### Lines 146–154: `rowLabelPosition`

Where the row's code (for example `P05`) floats: above the rack, at the **alternating ends** of the row (`index % 2`), so labels of neighbouring rows don't land on top of each other. It returns `[x, y, z]`, with the height at `topHeight` plus 0.6 for pallet rows or 0.3 for shelves.

### Lines 156–169: `cameraView`

The camera position and target for the **3D** and **Top** buttons, fitted to the building and the shape of the window.

- `fovDeg` is the camera's field of view. `Math.tan((fovDeg * Math.PI) / 360)` is the tangent of half of it. `aspect || 1.5` uses 1.5 when no aspect ratio is given.
- **Top view:** works out how high to go so the whole building fits (the larger of the width needs and the length needs), plus 4%. The camera goes straight above the centre.
- **3D view:** a distance `d` from the building size and aspect, along a fixed direction `[-0.55, 0.56, 0.62]` (from the front-left, above). The direction is turned into a unit length with `Math.hypot(...dir)` and multiplied by `d`.
- The numbers 0.533, 1.033, 1.15 and the direction are fitted values from the prototype.

### Lines 171–183: `openSide`

Decides which side of a row faces an aisle: **−1** (towards −x) or **+1**.

- The comment gives the rule: a row with a back-to-back partner less than 1 m away on one side is looked at from the other. A lone row is looked at from −x.
- `rows.some(...)` asks "is there any other row `r` that is on the minus side, within 1 m, and in the same stretch of floor?" A partner "in the same stretch" means their `y` ranges overlap. If so, the answer is `1`, otherwise `-1`.
- `gap >= -1e-9` allows for rows that touch exactly.

### Lines 185–199: `aisleClearance`

The free floor in front of a row's face on `side`, up to the next row in the same stretch or up to the wall.

- It starts with the distance to the wall: `row.x` for side −1, or the building length minus the row's far edge for +1.
- Then, for every other row in the same stretch that lies on that side, it takes the gap between the two and keeps the smallest one.

### Rules of each function

**Rules for the whole file**

| Rule | Where it shows |
|---|---|
| **No drawing code.** The file touches neither Three.js nor the page, so it can be tested with plain numbers. | Header, lines 1–2 |
| **Plan to world.** Plan `x` is world `x`, plan `y` is world `z`, and height is world `y` (up). | Header, line 6 |
| **Every shape is a box:** `[centreX, centreY, centreZ, sizeX, sizeY, sizeZ]`. | Header, line 7 |
| **Racks run along plan `y`:** depth along `x`, bays along `y`. | Header, line 8 |
| **No input checking.** The file trusts the data from the server. The Python rules in sections 8 to 12 are what keep that data valid. | The whole file |

**Rules per function**

| Function | Rule |
|---|---|
| `toWorld` (11–13) | The building is centred on the origin, so a plan point is moved by minus half the length in x and minus half the width in y. |
| `floorGeometry` (16–32) | The floor's **top face is at height 0**. Grid lines run every 5 m from 0 to the full length and width, including the far edge. There are always four curbs, one on each wall, sitting just outside it. |
| `areaBox` (35–38) | An area is a very thin slab. Its `width` runs along x and its `depth` along z. It is centred on the area's middle. |
| `areaLifts` (46–53) | **Bigger areas go lowest.** Equal sizes keep the order they were given in. Each step up is 0.01 m. The lift never goes above 3 steps (0.03 m). The top of a full stack (5.2 cm) must stay under a dock pad (6 cm). Known limit: areas nested more than four deep share the top level. |
| `areaColor` (56–58) | The colour must be `#` plus exactly six hex digits, in upper or lower case. Anything else gives the fallback colour. |
| `dockGeometry` (65–90) | A dock always gets its **pad**. It gets a **door frame only if it touches a wall**, meaning within 1 cm of it. `width >= depth` means a front or back wall, and anything else means a side wall. For front and back, the far wall is checked before the near wall. A dock that touches no wall gets no frame. A wide dock (`width >= depth`) that touches only a side wall also gets no frame, because only front and back walls are checked for it. |
| `rackGeometry` (93–121) | Uprights stand at **every bay boundary** on both faces, so `bays + 1` lines. **Pallet rows** get beams at heights 1 to `levels − 1` and no decks. There is no beam at the floor or above the top level. **Shelf rows** get a deck at every level and no beams. Shelf uprights are thinner and 0.1 m taller. |
| `slotBox` (128–144) | `bay`, `level` and `position` are **1-based** (as stored on the location). A bay's width is shared equally between its slots. On a pallet row, level 1 starts at the floor and higher levels start on top of the beam. On a shelf row, a slot starts on top of its deck. The box is made a little smaller or larger than the real slot, so neighbours don't touch. Nothing checks that the numbers are in range. A bad index just gives a box outside the rack. |
| `rowLabelPosition` (147–154) | The label always floats above the rack. Rows with an even index get the label at the **far end**, and odd rows at the **near end**, so neighbours don't overlap. |
| `cameraView` (157–169) | The mode `"top"` looks straight down. **Any other mode gives the 3D view.** A missing aspect ratio counts as 1.5. The whole building must fit in the window, with the building's width or length deciding the distance (top view has a 4% margin). |
| `openSide` (175–183) | The face is `+1` only if **another** row sits on the minus side within 1 m, **and** the two rows overlap in `y` (the same stretch of floor). Otherwise the face is `-1`. A row never counts as its own partner, which works because row codes are unique within a warehouse. Overlapping rows are not counted as partners. |
| `aisleClearance` (186–199) | It starts from the distance to the wall on that side. Only **other** rows in the **same stretch** and **on that side** can shorten it. The smallest gap wins. A row on the other side is ignored. |

### Why it's needed

- **The 3D view only draws what this file works out.** The server sends plain numbers (section 12). This file turns each row, area, dock and slot into the boxes to draw.
- **No drawing code in here,** so each function can be tested with a few numbers and a check, with no browser. The tests are in `static/tests/layout.test.js`.
- **One conversion point:** `toWorld` is the single place that turns plan coordinates into world coordinates.

---

## 23. `static/src/view3d/occupancy.js`

**The file in one sentence:** it turns the stock data of each slot into things the 3D view can show (a colour band, a box that is as tall as the stock, summary counts, and the merge of fresh data after a live update), using plain numbers and no drawing code.

Like `layout.js` (section 22), it touches neither Three.js nor the page, so it can be unit-tested. The header says where its data comes from: a slot's `stock` is what `wh3d_get_scene` gives (section 12), either `{used_m3, fill, ...}` or `null`.

### JavaScript words you will see

New ones only. The words from section 22 still apply.

| Word | Plain meaning |
|---|---|
| **`import { f } from "..."`** | Brings function `f` in from another file. Like `#include`, but for one named thing. |
| **`===` / `!==`** | Strict equality. It compares value **and** type, so `null === undefined` is false. |
| **`null` / `undefined`** | Two kinds of "no value". `null` is set on purpose. `undefined` means "never set" or "not found". |
| **`Object.fromEntries(list)`** | Builds a dictionary from a list of `[key, value]` pairs. |
| **`Map`** | A dictionary with a `.get(key)` that gives `undefined` when the key is missing. |
| **`.reduce((a, b) => a + b, 0)`** | Folds a list into one value. Here it adds up the numbers. |
| **`{ ...obj, key: value }`** | Makes a copy of `obj` with one field changed. |
| **`x++`** | Add one to `x`, as in C. |
| **`a \|\| b`** | `a` if it has a value, otherwise `b`. |

### Lines 5: the import

```js
import { slotBox } from "@warehouse_3d/view3d/layout";
```

It brings in `slotBox` from section 22. `@warehouse_3d/...` is how Odoo names a JavaScript file: the addon name followed by the path inside it.

### Lines 7–16: `fillBand`

```js
export function fillBand(fill) {
    if (fill === null || fill === undefined) { return "nodims"; }
    if (fill < 0.5) { return "low"; }
    return fill <= 0.9 ? "mid" : "high";
}
```

Turns a fill ratio (0.5 means half full) into one of four labels, which the colour mode and the legend use:

| Label | When |
|---|---|
| `"low"` | below 50% |
| `"mid"` | 50% to 90%, both ends included |
| `"high"` | above 90% |
| `"nodims"` | no fill known (the product has no size, section 14) |

The comment writes it as `"low" < 50 % ≤ "mid" ≤ 90 % < "high"`. These are the same three bands as `_WH3D_FILL_BANDS` in section 12 (green, amber, red).

### Lines 18–31: `loadBox`

**What it does:** one box that stands for everything in a slot. It has the slot's footprint, and its height shows how much stock there is.

```js
const { base, box } = slotBox(row, slot, building);
const slotWidth = row.bay_width / row.slots_per_level;
const maxHeight = box[4];
const height = stock.used_m3 === null
    ? maxHeight / 2
    : Math.min(stock.used_m3 / (row.depth * slotWidth), maxHeight);
const margin = row.kind === "pallet" ? 0.1 : 0.04;
return [box[0], base + height / 2, box[2], row.depth - margin, height, slotWidth - margin];
```

- `slotBox` (section 22) gives the empty slot's box. `base` is the height of the slot's floor. `box[4]` is the slot box's height, which becomes the limit.
- **Height of the stock:** the stored volume divided by the floor area of the slot (`depth × slotWidth`). That is how tall a block of that volume would be if it filled the whole floor of the slot.
- It is capped at the height of the slot. If the volume is unknown (`used_m3` is `null`), the box is **half the slot's height**, so the slot still shows as "something is here".
- `margin` shrinks the box a little on each side (0.1 m for pallets, 0.04 m for shelves), so it sits inside the slot.
- The result is in the box format from section 22: the centre x and z are the slot's, the centre height is the base plus half the height, and the sizes are the footprint and the height.

### Lines 33–35: `normalizeCode`

```js
export function normalizeCode(text) {
    return (text || "").trim().toUpperCase();
}
```

Tidies a typed code: a missing value becomes `""`, spaces at both ends are cut, and letters become capitals. So `" p05-03-2-a "` becomes `"P05-03-2-A"`, and two codes typed differently compare equal.

### Lines 37–63: `capacitySummary`

**What it does:** counts for the side panel: for each kind of rack (pallet, shelf), how many slots there are, how many hold stock, and the average fill.

```js
const kindOf = Object.fromEntries(rows.map((r) => [r.id, r.kind]));
const summary = { rows: { pallet: 0, shelf: 0 } };
const fills = { pallet: [], shelf: [] };
for (const kind of ["pallet", "shelf"]) {
    summary[kind] = { total: 0, used: 0, avgFill: null };
}
```

- `kindOf` is a lookup: row id → its kind. A slot only knows its `row_id`, so this is how the code finds out whether it is a pallet or a shelf slot.
- `summary` starts with zeros. `fills` collects the known fill values of each kind.

```js
for (const row of rows) { summary.rows[row.kind]++; }
for (const slot of slots) {
    const kind = kindOf[slot.row_id];
    summary[kind].total++;
    if (slot.stock) {
        summary[kind].used++;
        if (slot.stock.fill !== null) { fills[kind].push(slot.stock.fill); }
    }
}
```

- The first loop counts rows per kind.
- The second loop goes through every slot: it counts it (`total`), counts it as `used` if it holds any stock, and remembers its fill **only if the fill is known**.

```js
for (const kind of ["pallet", "shelf"]) {
    const f = fills[kind];
    summary[kind].avgFill = f.length ? f.reduce((a, b) => a + b, 0) / f.length : null;
}
```

The average is the sum of the known fills divided by how many there are. With no known fills it stays `null`, not 0.

The result looks like `{ rows: {pallet, shelf}, pallet: {total, used, avgFill}, shelf: {total, used, avgFill} }`.

### Lines 65–74: `legendCounts`

```js
const counts = { low: 0, mid: 0, high: 0, nodims: 0 };
for (const slot of slots) {
    if (slot.stock) { counts[fillBand(slot.stock.fill)]++; }
}
```

For the legend: how many **stocked** slots fall in each band. Empty slots are not counted.

### Lines 76–94: `mergeSlotUpdates`

**What it does:** when fresh data arrives after a live update, it puts it into the list of slots that the scene draws from.

The four inputs:
- `slots`: the list the scene draws from.
- `indexByLocation`: a `Map` from location id to the position in `slots`.
- `requestedIds`: the slot ids the view asked about.
- `fresh`: what `wh3d_get_slots` returned (section 12).

```js
const returned = new Map(fresh.map((s) => [s.location_id, s]));
let changed = 0;
for (const id of requestedIds) {
    const index = indexByLocation.get(id);
    if (index === undefined) { continue; }
    slots[index] = returned.get(id) || { ...slots[index], stock: null };
    changed++;
}
return changed;
```

- `returned` is a lookup of the fresh data by location id.
- For each requested id, it finds the slot's position. **If there is none, the id belongs to another warehouse and is ignored.** (A live message goes to every Inventory User in every warehouse, section 13, so a view hears about slots that aren't on its screen.)
- Otherwise it replaces that entry with the fresh data. **If the slot was asked about but not returned, it is no longer an active slot** (it was archived meanwhile, and `wh3d_get_slots` skips such ids). Then the old entry is kept, with its `stock` set to `null`, so it shows as empty.
- It returns how many of this view's slots were updated.

### Why it's needed

- **Stock in the picture.** The server sends numbers. This file decides which colour band a slot is in, how tall its stock box is, and what the summary and legend say.
- **Live updates.** After a bus message (section 13) and a refetch (`wh3d_get_slots`, section 12), `mergeSlotUpdates` is the step that gets the new data into the scene. It also copes with archived slots and other warehouses' ids.
- **Easy to test.** Every function takes numbers in and gives numbers out. The tests are in `static/tests/occupancy.test.js`.

---

## 24. `static/src/view3d/live.js`

**The file in one sentence:** it takes the stream of "these locations changed" live messages (section 13) and turns it into a calm series of refetches, so the 3D view asks the server for fresh slot data in an orderly way and not once per message.

It holds one class, `UpdateQueue`. It knows nothing about Odoo or Three.js. The view gives it two functions: one that fetches data (`fetch`) and one that uses the result (`apply`).

### JavaScript words you will see

New ones only. The words from sections 22 and 23 still apply.

| Word | Plain meaning |
|---|---|
| **`class`, `constructor`, `this`** | A class is like a C++ class. The `constructor` runs when you create one. `this` is the object itself, like `this` in C++. |
| **Promise, `async`, `await`** | A Promise is a result that arrives later (here, a server reply). `await` pauses the function until it arrives. A function that uses `await` is marked `async`. |
| **`try` / `catch` / `finally`** | The same idea as in C++. `catch` runs if the `try` part fails. `finally` always runs. |
| **`setTimeout(f, ms)`** | Runs `f` once after `ms` milliseconds, and gives back a timer you can cancel. `clearTimeout(timer)` cancels it. |
| **`Set`** | A collection with no duplicates. `.add`, `.clear`, `.size`. |
| **`[...set]`** | Copies the items of a set into a normal list. |
| **`Object.assign(this, {...})`** | Copies several named values onto the object in one go. |

### Lines 1–9: what it promises

The header lists four promises:

1. **Collect until `start()`.** Messages that arrive before the scene is loaded are kept, so nothing is missed.
2. **Throttle, don't debounce.** At most one fetch per `delay` milliseconds, however steady the stream. A *debounce* waits for things to go quiet and restarts its wait on every new message. In a busy warehouse it would never go quiet, so it would never fire. A *throttle* fires on a fixed rhythm no matter what.
3. **One fetch at a time.** An older reply can never arrive after, and overwrite, a newer one.
4. **A failed fetch is not lost.** Its ids are put back, and it is retried after `retryDelay` milliseconds.

### Lines 10–22: the class and its state

```js
constructor({ delay, retryDelay, fetch, apply }) {
    Object.assign(this, { delay, retryDelay, fetch, apply });
    this.pending = new Set();
    this.started = false;
    this.running = false;
    this.timer = null;
}
```

- The constructor takes **one object with four named values** (the comment on lines 11–15 describes them):
  - `delay`: the throttle wait, in ms.
  - `retryDelay`: the wait after a failure, in ms.
  - `fetch(ids)`: gets fresh data for those ids and returns a Promise.
  - `apply(ids, result)`: puts the result into the scene.
- `Object.assign` stores those four on the object.
- Then four pieces of state:

| Name | Meaning |
|---|---|
| `pending` | A set of location ids waiting to be fetched. A set drops duplicates for free. |
| `started` | Has `start()` been called, and not `stop()` since? |
| `running` | Is a fetch in progress right now? |
| `timer` | The waiting timer, or `null` if none is waiting. |

### Lines 24–39: `push`, `start`, `stop`

```js
push(ids) {
    ids.forEach((id) => this.pending.add(id));
    this.schedule(this.delay);
}
```
Called for each message. It adds the ids to `pending` and asks `schedule` to arrange a fetch.

```js
start() {
    this.started = true;
    this.schedule(this.delay);
}
```
Called when the scene is loaded. It switches the queue on and schedules a fetch for anything collected so far.

```js
stop() {
    this.started = false;
    clearTimeout(this.timer);
    this.timer = null;
    this.pending.clear();
}
```
Switches it off and **forgets everything**: cancel the timer and empty the set. The project notes say the view does this when it switches to another warehouse.

### Lines 41–49: `schedule`, the throttle

```js
schedule(wait) {
    if (this.started && !this.running && !this.timer && this.pending.size) {
        this.timer = setTimeout(() => {
            this.timer = null;
            this.flush();
        }, wait);
    }
}
```

A timer is only set up when **all four** are true:

- the queue is started,
- no fetch is running,
- no timer is already waiting,
- something is pending.

The comment on line 42 says why the third one matters: "An armed timer is left alone: that's what makes it a throttle." Later messages add to `pending` but do not touch the timer. When the timer fires, it clears itself (`this.timer = null`) and calls `flush`.

So the **first** change waits up to `delay` before its fetch. Changes that arrive in the meantime join the same fetch.

### Lines 51–68: `flush`, the fetch

```js
async flush() {
    const ids = [...this.pending];
    this.pending.clear();
    this.running = true;
    let wait = this.delay;
    try {
        const result = await this.fetch(ids);
        if (this.started) {
            this.apply(ids, result);
        }
    } catch {
        ids.forEach((id) => this.pending.add(id));
        wait = this.retryDelay;
    } finally {
        this.running = false;
    }
    this.schedule(wait);
}
```

Step by step:

1. **Take the ids:** copy `pending` into a list and empty the set. New messages during the fetch go into the now-empty set.
2. **Mark `running`,** so no second fetch can start.
3. **`await this.fetch(ids)`:** wait for the server's answer.
4. **If still started, `apply`** the result. If `stop()` was called while waiting, the answer is thrown away.
5. **If the fetch failed (`catch`):** put the ids back into `pending` and use `retryDelay` as the next wait.
6. **`finally`:** `running` goes back to false, whatever happened.
7. **`this.schedule(wait)`:** if ids piled up during the fetch (or were put back), arrange the next fetch after `wait`.

### A timeline

Let `D` be the delay.

| Time | What happens |
|---|---|
| 0 | `push([1])`. A timer is set for `D`. |
| 0.3 D | `push([2, 3])`. A timer already waits, so the ids are only collected. |
| D | The timer fires. `flush` fetches `[1, 2, 3]` in one request. |
| during the fetch | `push([4])`. The id is collected. No timer is set, because `running` is true. |
| fetch done | `schedule(D)` sees `4` pending and sets a timer. |
| next timer | `flush` fetches `[4]`. |

If the fetch for `[1, 2, 3]` had failed, those ids would be back in `pending`, and the next attempt would wait `retryDelay` instead of `D`.

### Worth knowing

If a fetch **fails after `stop()`** was called, its ids are put back into `pending` even though `stop()` had cleared it. They would be fetched after the next `start()`. I read this from the code and haven't tested it. It looks harmless: those ids may belong to the warehouse the view just left, and `mergeSlotUpdates` ignores ids that aren't in the current view (section 23).

### Why it's needed

- **Messages come in bursts.** Section 13 sends one message per transaction, but a busy warehouse has many transactions. Without a queue, every message would cause a request to the server.
- **Order matters.** Two requests in flight at once could return in the wrong order, and an old answer could replace a newer one. One fetch at a time prevents that.
- **Nothing is lost.** Early messages and failed fetches are kept and retried.
- **Easy to test.** It takes `fetch` and `apply` as inputs, so a test can give it fake ones. The tests are in `static/tests/live.test.js`.

---

## 25. `static/src/view3d/walk.js`

**The file in one sentence:** it holds the maths of **walk mode**, the first-person view where you walk the aisles: where the walker starts, how keys and the mouse move them, and how racks and walls stop them.

It uses plain numbers on the floor plan, so it can be unit-tested without Three.js. This is also where `openSide` and `aisleClearance` from section 22 are used (in `walkStartAtSlot`).

### Words you will see

| Word | Plain meaning |
|---|---|
| **pose** | Where the walker is and which way they face: `{x, y, yaw}`. `x` and `y` are plan metres. |
| **yaw** | The heading on the plan, as an angle in **radians**. `0` is towards +x, `π/2` is towards +y, `π` is towards −x. |
| **pitch** | How far the head looks up or down, in radians. |
| **frame** | One redraw of the screen. `dt` is the time since the previous frame, in seconds. |
| **tunnelling** | A fast move jumping clean over a thin obstacle, because the code only checked the start and the end. |
| **`Math.cos`, `Math.sin`, `Math.atan2`, `Math.hypot`** | Maths helpers. `atan2(dy, dx)` gives the angle of a direction. `hypot(a, b)` gives the length of a vector, `√(a² + b²)`. |
| **`{ ...pose, x, y }`** | A copy of `pose` with `x` and `y` replaced. The old object is not changed. |
| **`[action]: down`** | A field whose **name** comes from a variable. |
| **`.find(f)`** | The first item of a list where `f` is true, or `undefined`. |

Every function here takes the current state and **returns a new one**. None of them changes anything it was given.

### Lines 7–19: the import and the constants

```js
import { aisleClearance, openSide } from "@warehouse_3d/view3d/layout";
```
Brings in two helpers from section 22.

| Constant | Value | Meaning |
|---|---|---|
| `EYE_HEIGHT` | 1.7 m | How high the walker's eyes are. |
| `RADIUS` | 0.3 m | The walker is a circle this wide on the floor. |
| `WALK_SPEED` | 1.4 m/s | An ordinary walking pace. |
| `RUN_FACTOR` | 2.5 | Speed multiplier while Shift is held. |
| `MAX_STAND_OFF` | 2.5 m | The furthest the walker starts from a rack (not exported). |
| `WALK_KEYS` | a lookup | Which key does what: `w` or `ArrowUp` is forward, `s` or `ArrowDown` is back, `a` or `ArrowLeft` is left, `d` or `ArrowRight` is right. |

### Lines 21–32: `walkStartAtSlot`

Where to put the walker when you choose a slot: **in the aisle in front of it, in the middle of the aisle (at most 2.5 m back), facing the rack.**

```js
const side = openSide(row, rows);
const clearance = aisleClearance(row, rows, building, side);
const standOff = Math.min(MAX_STAND_OFF, Math.max(RADIUS + 0.05, clearance / 2));
```

- `openSide` says which face of the row is the open one (−1 or +1).
- `aisleClearance` says how much free floor there is in front of that face.
- `standOff` is the distance back from the rack: **half the aisle**, but at least `RADIUS + 0.05` (so the walker does not touch the rack) and at most 2.5 m.

```js
return {
    x: side < 0 ? row.x - standOff : row.x + row.depth + standOff,
    y: row.y + (slot.bay - 1) * row.bay_width + (slot.position - 0.5) * slotWidth,
    yaw: side < 0 ? 0 : Math.PI,
};
```

- `x`: in front of the open face, `standOff` away.
- `y`: along the row, at the **centre of the slot** (bay start plus half a slot width, the same maths as `slotBox`).
- `yaw`: facing the rack. On the −x side that is towards +x (`0`), on the +x side it is towards −x (`π`).

### Lines 34–44: `walkStartAtEntrance`

Where to start when **no slot is chosen**.

- If the building has a dock (`areas.find((a) => a.kind === "dock")` takes the first one), stand in the middle of it and look at the middle of the hall. The heading comes from `Math.atan2(centre.y - y, centre.x - x)`.
- If there is no dock, stand 1.5 m in from the wall at `y = width` (the comment calls it the front wall), looking towards −y (`-Math.PI / 2`) into the hall.

### Lines 46–63: `moveVector`

**What it does:** works out how far to move in this frame, from the keys held down.

```js
const f = (keys.forward ? 1 : 0) - (keys.back ? 1 : 0);
const r = (keys.right ? 1 : 0) - (keys.left ? 1 : 0);
let dx = f * Math.cos(yaw) - r * Math.sin(yaw);
let dy = f * Math.sin(yaw) + r * Math.cos(yaw);
```

- `f` is +1 for forward, −1 for back, 0 if neither or both. `r` is the same for right and left.
- Forward is the direction `(cos yaw, sin yaw)`. Right is a quarter turn from it, `(−sin yaw, cos yaw)`. The comment says this is the camera's right in the 3D view.
- `dx` and `dy` add the forward and sideways parts.

```js
const length = Math.hypot(dx, dy);
if (!length) { return { dx: 0, dy: 0 }; }
const distance = WALK_SPEED * (keys.run ? RUN_FACTOR : 1) * dt;
dx = (dx / length) * distance;
dy = (dy / length) * distance;
```

- No key gives no movement.
- `distance` is speed × time. At 1.4 m/s and 60 frames a second, that is about 2.3 cm per frame, or 5.8 cm when running.
- Dividing by `length` first and then multiplying by `distance` means **a diagonal move is not faster** (the comment on line 60).

### Lines 65–68: `rackObstacles`

```js
return rows.map((r) => ({ x0: r.x, y0: r.y, x1: r.x + r.depth, y1: r.y + r.bays * r.bay_width }));
```

Turns each rack row into a rectangle the walker can't enter. It is the same floor rectangle as `_wh3d_footprint` in section 8.

### Lines 70–80: `blocked` (private)

Is this spot forbidden? Two tests:

1. **Walls:** the walker's centre must stay at least `RADIUS` away from every wall (`x < RADIUS`, `y < RADIUS`, `x > length − RADIUS`, `y > width − RADIUS`).
2. **Racks:** for each rectangle, find the nearest point of the rectangle to the walker's centre and measure the distance.

```js
const nx = Math.max(o.x0, Math.min(x, o.x1));
const ny = Math.max(o.y0, Math.min(y, o.y1));
return Math.hypot(x - nx, y - ny) < RADIUS - 1e-9;
```

`Math.max(x0, Math.min(x, x1))` pushes `x` into the range `x0` to `x1`. If the centre is inside the rectangle, the nearest point is the centre itself and the distance is 0, so it is blocked. If the distance is less than the radius, the circle overlaps the rack, so it is blocked. The `1e-9` lets the walker stand exactly touching.

### Lines 82–103: `stepWalker`

**What it does:** applies one frame's move, with collisions.

```js
const steps = Math.max(1, Math.ceil(Math.hypot(move.dx, move.dy) / (RADIUS / 2)));
let { x, y } = pose;
for (let i = 0; i < steps; i++) {
    const dx = move.dx / steps;
    const dy = move.dy / steps;
    if (!blocked(x + dx, y + dy, obstacles, building)) {
        x += dx; y += dy;
    } else if (dx && !blocked(x + dx, y, obstacles, building)) {
        x += dx;
    } else if (dy && !blocked(x, y + dy, obstacles, building)) {
        y += dy;
    }
}
return { ...pose, x, y };
```

- **Small steps (no tunnelling).** The move is cut into steps no longer than `RADIUS / 2` (15 cm), and each step is checked. A slow frame with a big `dt` therefore can't jump over a thin rack. The comment says "no longer than the radius", but the code uses half the radius.
- **Sliding.** For each step it tries the full move first. If that is blocked, it tries only the `x` part, then only the `y` part. So walking at an angle into a rack **slides along its face** and doesn't stop dead.
- If both parts are blocked, the walker doesn't move for that step.
- It returns a copy of the pose with the new `x` and `y`, so `yaw` and `pitch` are kept.

### Lines 105–118: `look` (the mouse)

```js
const LOOK_SPEED = 0.005; // radians per pixel dragged
const MAX_PITCH = 1.4;    // about 80°
...
yaw: pose.yaw - dx * LOOK_SPEED,
pitch: Math.max(-MAX_PITCH, Math.min(MAX_PITCH, pose.pitch + dy * LOOK_SPEED)),
```

- Each dragged pixel turns the view by 0.005 radians.
- It works like **dragging the view in Street View**: dragging right turns the view left, and dragging up looks down. The comment records that this direction was chosen after trying the opposite.
- The pitch is held between −1.4 and +1.4 radians (about 80°), so you can't flip over the top.
- The start functions above return `{x, y, yaw}` only, with no `pitch`. `look` needs one, so whoever calls it has to add a `pitch` first. Otherwise the result would be `NaN` ("not a number").

### Lines 120–142: `walkKey` (the keyboard)

**What it does:** takes one key event and updates which keys are held. It returns `{ keys, handled, exit }`.

The event is `{ type, key, shiftKey, typing }`. `typing` is true when the key went into a text box (such as Find).

```js
if (down && typing) { return { keys, handled: false, exit: false }; }
if (down && key === "Escape") { return { keys, handled: true, exit: true }; }
if (key === "Shift") { return { keys: { ...keys, run: down }, handled: false, exit: false }; }
const action = WALK_KEYS[key.length === 1 ? key.toLowerCase() : key];
if (!action) { return { keys, handled: false, exit: false }; }
return { keys: { ...keys, [action]: down, run: shiftKey }, handled: true, exit: false };
```

In order:

1. **A key press while typing is ignored.** The walker doesn't move while you type in a box.
2. **Escape leaves walk mode** (`exit: true`).
3. **Shift sets `run`** to true on press and false on release.
4. **Look up the key.** Single letters are lower-cased, so `W` and `w` are the same. Names like `ArrowUp` are used as they are. An unknown key changes nothing.
5. **A walking key sets its flag** (`forward`, `back`, `left` or `right`) to true on press and false on release. `run` follows the event's Shift flag.

The comment explains why **releases always count**, even while typing: hold W, click into the Find box, let go, and the walker must still stop. This came from a code review (CodeRabbit). Only presses are blocked while typing (`down && typing`).

### How the pieces fit together

From the header: every frame the view takes the held keys and the heading, asks `moveVector` how far to go, and passes that to `stepWalker` to get the new pose. Key events go through `walkKey`, and mouse drags go through `look`. This wiring comes from the header comment and the function names.

### Why it's needed

- **Walk mode is real movement, not just a camera.** It needs speed, direction, diagonals, running, collisions with racks and walls, and mouse look. This file is all of that.
- **Starting somewhere sensible.** Choosing a slot puts you in the aisle in front of it, facing it.
- **Easy to test.** Everything takes numbers in and returns new numbers, so the tests need no browser. They are in `static/tests/walk.test.js`.

---

## 26. `static/src/view3d/scene.js`

**The file in one sentence:** it builds and runs the 3D picture of one warehouse with Three.js: the floor, areas, docks, racks, stock boxes and labels, plus clicking, camera flights, walk mode and clean-up.

This is the file that **uses** the three pure maths files (sections 22, 23 and 25). They work out numbers, and this file turns those numbers into things on the screen. It is also where walk mode is wired up, and where the walker's `pitch` is added.

### Words you will see

| Word | Plain meaning |
|---|---|
| **Three.js** | The 3D library. It is loaded separately as `window.THREE` (the project keeps its own copy of the library, section 1). |
| **WebGL** | The browser's way of drawing 3D on the graphics card. The scene throws an error if WebGL isn't available. |
| **scene, camera, renderer** | The scene holds the objects. The camera is the viewpoint. The renderer draws the scene through the camera onto a canvas. |
| **mesh** | One drawable object: a shape (geometry) plus a surface (material). |
| **instanced mesh** | Many copies of one shape, drawn in **one** call to the graphics card. Thousands of uprights cost almost nothing. |
| **sprite** | A flat picture that always faces the camera. Used for labels. |
| **raycaster** | Shoots an invisible line from the camera through the mouse position and reports what it hits. Used for clicking. |
| **OrbitControls** | Drag to orbit around the building, scroll to zoom. |
| **animation loop** | A function called before every screen redraw (about 60 times a second). |
| **colours like `0xe3e8ed`** | Hex numbers, `0xRRGGBB`: red, green, blue. |
| **`?.`** | Optional chaining: `a?.b` gives `undefined` instead of an error if `a` is missing. |

### Lines 1–35: imports and constants

- It imports 13 functions from `layout.js` (section 22), `fillBand` and `loadBox` from `occupancy.js` (section 23), and six names from `walk.js` (section 25).
- `COLORS` is "the prototype's light palette": background, floor, grid, curb, area, dock, steel, beam, deck, accent and stock colours.
- `BAND_COLORS` is exported: **low** green `0x1f8a70`, **mid** amber `0xcf9b12`, **high** red `0xb3261e`. These are the three bands from `fillBand`.
- `LABEL` holds the label colours, and `FOV = 42` is the camera's field of view in degrees.

### Lines 37–47: the class

`WarehouseScene` builds and runs the scene for one warehouse. Its data is the `wh3d_get_scene()` result (section 12). It needs `window.THREE` and `THREE.OrbitControls` to be loaded. The constructor takes:

- `host`: the page element to draw into.
- `data`: the scene data.
- `onSelect(index)`: called when a slot is clicked (the index into `data.slots`, or `-1` when cleared).
- `onWalk(pose)`: called each time the walker moves (and with `null` on leaving walk mode).

The scene never calls the page's own code directly. It only calls these two functions it is given, so it doesn't need to know what the page looks like.

### Lines 48–107: the constructor, in order

1. **The renderer** (lines 49–54): a `WebGLRenderer` with smoothing (`antialias`). The pixel ratio is capped at 2, so high-resolution screens stay sharp without too much work. Its canvas is added to the host.
2. **Scene and camera** (56–58): a background colour, and a perspective camera with near plane 0.5 and far plane 600.
3. **Orbit controls** (59–64): smooth stopping (`enableDamping`), the camera can't go below the floor (`maxPolarAngle`), the closest zoom is 1 m ("close enough to stand in a 1.2 m picker aisle"), and the furthest is at least 180 m or 3 building lengths.
4. **Lights** (65–69): a soft sky light and a "sun". The comment says it is softer than the prototype's, which washed flat floors out to white.
5. **`unitBox`** (71): **one** 1 × 1 × 1 cube, shared by everything. Every box in the scene is a scaled copy of it. That is why the box format from section 22 (centre and size) fits so well.
6. **Build everything** (72–77): floor, areas and docks, racks, and labels.
7. **Bookkeeping** (79–89):
   - `rowsById`: a lookup from row id to row.
   - `slots`: the slot list.
   - The two callbacks.
   - `walk = null`: not walking.
   - `onWalkKey` and `onWalkBlur`: the handlers for walk mode. The comment on line 85 says why: Alt-Tab away while holding W and the key-up goes to the other window, so on `blur` it lets go of every key.
   - `stockVisible = true` and **`colourByOccupancy = false`**: occupancy colouring is off until switched on.
8. **Hit targets, stock and selection** (90–98): see below. The selection outline is an orange wireframe of the unit box, drawn without depth testing so it shows through racks, and hidden at first.
9. **Motion, resizing and the loop** (100–106):
   - `reduceMotion` reads the user's "prefers reduced motion" setting.
   - A `ResizeObserver` resizes the picture when the host changes size.
   - `setView("3d", true)` puts the camera in the 3D position at once.
   - `renderer.setAnimationLoop(() => this.frame())` starts the loop.

### Lines 111–137: building blocks

- `material(color)`: a simple lit surface (`MeshLambertMaterial`).
- `addBox(box, material)`: makes a mesh from the unit cube, then moves it to the box centre (`box[0..2]`) and scales it to the box size (`box[3..5]`).
- `addInstanced(boxes, material)`: the same, but for **many boxes in one instanced mesh**.
  - Each box is turned into a transform (a `Matrix4`, built with `compose` from a position, no rotation, and a scale).
  - The capacity is at least 1 (`Math.max(boxes.length, 1)`), and then `mesh.count` is set to the real number.
  - `instanceMatrix.needsUpdate = true` tells the graphics card that the data changed.

### Lines 139–167: floor and areas

- **`buildFloor`:** gets the floor, grid lines and curbs from `floorGeometry`. The grid lines are flattened into one list of points at height 0.01 and drawn as line segments. The curbs go in one instanced mesh.
- **`buildAreas`:**
  - Floor areas and docks are separated. Each dock goes through `dockGeometry`.
  - Areas are grouped **by colour** in a `Map`, so there is one draw call per colour ("managers pick a colour per area, and there are only a few colours").
  - For each area: the colour comes from `areaColor`, the box from `areaBox`, and `box[1] += lifts[i]` adds the lift from `areaLifts` ("overlapping areas of different colours must not share a height").
  - Then come the dock pads (amber) and dock frames (steel), each as one instanced mesh.

### Lines 169–183: racks and hit targets

- **`buildRacks`:** runs `rackGeometry` for every row, then puts **all uprights of all rows into one instanced mesh**, all beams into another, and all decks into a third.
- **`buildHitTargets`:** one **invisible** box per slot, from `slotBox`. They have opacity 0 and write no colour or depth, but they can still be hit by the raycaster. The comment on line 176 states the key fact: **instance index = slot index.** The n-th hit box belongs to `this.slots[n]`.

### Lines 185–255: stock

- **`buildStock`** redraws all the stock boxes:
  - It removes the old stock meshes and frees their materials. The shared unit box is freed later in `dispose`.
  - For each slot that has stock, `loadBox` (section 23) gives the box, and `fillBand` the band.
  - A slot goes into `known` if its fill is known, otherwise into `unknown`.
  - `known` gets one instanced mesh with a **white** material: the colour of each instance decides it (neutral grey, or the band colour). `unknown` gets its own mesh in the neutral colour.
  - The comment says it is rebuilt from scratch whenever stock changes, which is cheap because it is only one draw call per mesh.
- **`applyStockStyle`:**
  - For each known instance it sets the colour: the band colour when `colourByOccupancy` is on, otherwise neutral grey.
  - Unknown-fill boxes get a **striped texture** while colouring by occupancy, "so it doesn't pass for empty-ish". Otherwise they stay plain grey.
  - Finally it shows or hides all stock meshes by `stockVisible`.
- **`stripeTexture`:** draws a 32 × 32 picture of diagonal stripes on a hidden canvas and turns it into a texture. It makes it once and keeps it.
- **`setStockVisible` and `setColourByOccupancy`:** set the flag and apply the style again.

### Lines 259–329: picking and selection

**`listenForPicks`** sets up three pointer handlers on the canvas:

- **Pointer down:** remember where the press began (`down`), and also `lookFrom`, the start point for walk-mode looking.
- **Pointer up:** if the pointer moved **less than 6 pixels** since it went down, it was a click, not the end of an orbit drag. Then it picks the slot under the pointer, outlines it (`select`) and tells the page (`onSelect`).
- **Pointer move:**
  - In **walk mode with the left button held** (`ev.buttons & 1`), the drag turns the head: it calls `look` (section 25) with the movement since the last point, stores the new `yaw` and `pitch`, and updates the camera.
  - Otherwise, only a free mouse is handled (no button held). The hover test runs **at most once per frame** (through `requestAnimationFrame`) and sets the cursor to `pointer` over a slot or `grab` elsewhere. The `if (this.renderer)` check guards against running after `dispose`.

**`pickAt(clientX, clientY)`** finds the slot under a screen point:

```js
const ndc = new THREE.Vector2(
    ((clientX - rect.left) / rect.width) * 2 - 1,
    -((clientY - rect.top) / rect.height) * 2 + 1);
ray.setFromCamera(ndc, this.camera);
const hit = ray.intersectObject(this.hitMesh)[0];
return hit ? hit.instanceId : -1;
```

- The screen point is turned into "normalised device coordinates", from −1 to +1 on each axis (the vertical axis is flipped).
- The ray goes from the camera through that point. The first hit on the invisible boxes gives the instance id, which is the slot index. No hit gives `-1`.

**`select(index)`** shows or hides the outline. For a slot it takes the slot's box and sets the outline to its position, **0.08 m bigger** on each side.

**`focusOn(index)`** flies the camera to a slot:

- It finds the open side and the aisle clearance (section 22), and chooses a stand-off of the clearance minus 0.3 m, kept between 0.8 and 7 m.
- The camera goes in front of the rack face, a little above (up to 1.5 m) and to one side, looking at the slot.
- The comment says why: never further back than the aisle allows, or the opposite rack blocks the view. Looking along the row, as the prototype did, lets the neighbouring slot hide the chosen one.

### Lines 350–404: labels

- **`buildLabels`:** an area gets its name in a "pill" (a rounded label) at height 0.9. A dock gets its name at height 4.2, above the door frame. Each row gets its code, with `rowLabelPosition` (section 22) giving the position.
- **`addLabel`:** Three.js has no easy text, so the text is **drawn on a hidden canvas** and used as a texture.
  - The canvas is sized to fit the text. A pill gets a white rounded rectangle with a border.
  - The texture goes on a **sprite**, which always faces the camera.
  - **Area labels** (pills) have the depth test off and a higher render order, so they stay readable **through racks**. **Row codes and dock names** have the depth test on, so they hide behind racks.
  - The sprite is scaled to the label's height and the canvas shape. All labels are in one group, so `setLabelsVisible` can hide them together.

### Lines 408–481: walk mode

- **`enterWalk(pose)`:**
  - The first time, it saves the orbit camera (position and target), builds the rack obstacles (`rackObstacles`, section 25), turns the orbit controls off, and moves the camera's near plane to 0.05 m ("racks can be 0.3 m away; the orbit view's 0.5 m would cut them off"). Then it listens for key presses, key releases and `blur` on the window.
  - Each time, it creates the walk state: `{ ...pose, pitch: 0, keys: {}, last: performance.now() }`, moves the camera, and calls `onWalk`.
  - **This is where `pitch: 0` is added**, so `look` always has one. Entering again while already walking just teleports the walker.
- **`exitWalk()`:** removes the listeners, restores the near plane, puts the camera and orbit target back **exactly where they were**, turns the controls on again, and calls `onWalk(null)`.
- **`handleWalkKey(ev)`:** works out whether the key went into a text box (`typing`), and passes the event to `walkKey` (section 25). Escape leaves walk mode. Otherwise it saves the new held keys. If the key was used and you are not typing, it calls `preventDefault()`, because arrow keys would otherwise scroll the page.
- **`applyWalkCamera()`:** puts the camera at the walker's position, 1.7 m up (`EYE_HEIGHT`), and aims it with the yaw and pitch: `(cos pitch · cos yaw, sin pitch, cos pitch · sin yaw)` from the eye. Plan `y` is world `z`.
- **`stepWalk()`:** runs every frame in walk mode. The time since the last frame is capped at 0.1 s ("a slow frame mustn't teleport you"). `moveVector` gives the move, and if there is one, `stepWalker` gives the new position, and `onWalk` is called. The camera is updated every frame.

### Lines 483–525: camera and the frame loop

- **`setView(mode, instant)`:** gets a position and target from `cameraView` (section 22) and moves there.
- **`animateTo(position, target, instant)`:** moves at once if `instant` or the user prefers reduced motion. Otherwise it stores the start time, the start and end positions, and the start and end targets.
- **`frame()`** is the animation loop, and it runs every frame:
  1. **Walking:** `stepWalk()`, draw, done.
  2. **Otherwise, a camera flight:** its progress `k` goes from 0 to 1 over **0.7 s**, and is shaped by an ease-in-out curve (`2k²` for the first half, then slowing down). The camera position and the orbit target are both blended between start and end (`lerpVectors`).
  3. Update the orbit controls and draw.
- **`resize()`:** takes the host's width and height (and does nothing if either is 0), resizes the renderer without changing its CSS size, and updates the camera's aspect ratio.

### Lines 537–561: `dispose`, the clean-up

The comment on line 537 gives the reason: **WebGL memory is not garbage-collected, and browsers allow only about 16 live contexts.** So `dispose` must free everything by hand:

- stop the animation loop;
- remove every listener (window and canvas);
- disconnect the `ResizeObserver`, and dispose the controls;
- walk the whole scene (`traverse`) and dispose every geometry, material and texture (`[].concat(obj.material || [])` copes with one material or a list);
- dispose the renderer and the stripe texture, force the context to be released, remove the canvas from the page, and set `renderer = null`.

### A frame at a glance

```
every frame:  frame()
   ├─ walking?  → stepWalk():  moveVector → stepWalker → camera at 1.7 m
   └─ else      → camera flight (0.7 s ease) → controls.update()
   → renderer.render(scene, camera)

click:  pointer up (under 6 px moved) → pickAt (ray vs invisible boxes) → select + onSelect(index)
```

### Why it's needed

- **It is the picture.** The server and the three maths files only produce numbers. This file creates the Three.js objects and draws them.
- **Speed.** Everything is a scaled copy of one cube, and identical parts are **instanced**, so a warehouse with thousands of parts is only a few dozen draw calls.
- **Interaction.** Clicking uses invisible boxes and a raycaster. Orbit, camera flights and walk mode are all here.
- **Cleanliness.** `dispose` stops the browser from running out of WebGL contexts when the view is opened and closed, or switched between warehouses.

---

## 27. `static/src/view3d/view3d_action.js`

**The file in one sentence:** it is the 3D View screen itself: an Odoo component that loads the data and Three.js, creates the scene, listens for live stock updates, and holds the state and actions of the side panel (selected slot, Find, capacity, legend, toolbar, walk button).

This is the file that section 5 pointed to: the action tag `warehouse_3d.view3d` opens this component. It is also the file that creates the scene from section 26. The panel's layout (the HTML) is in a separate template file, `view3d_action.xml`. This file supplies the data and the actions the panel uses.

### Words you will see

These come from OWL, Odoo's user interface framework. New JavaScript words are in the second table.

| OWL word | Plain meaning |
|---|---|
| **component** | A piece of screen made of a class plus an HTML template. `View3D` is one. |
| **`setup()`** | Runs once when the component is created. All the wiring goes here. |
| **hook** | A function you call in `setup` to say "run this at a certain moment". `onWillStart`, `onMounted`, `onWillUnmount` and `onWillDestroy` are hooks for loading, appearing, leaving and being thrown away. |
| **template** | The HTML of the component. `static template = "warehouse_3d.View3D"` names it. |
| **`useState`** | Makes an object **reactive**: when a field changes, the screen redraws by itself. |
| **`useRef`** | A handle to an element in the template, found by name. |
| **service** | A shared helper from Odoo. `orm` calls Python methods on the server, `action` opens screens, `bus_service` receives live messages. |

| JavaScript word | Plain meaning |
|---|---|
| **`static x = ...`** | A value that belongs to the class, not to each instance. |
| **`get name() {}`** | A "getter": used like a field (`this.selectedSlot`) but computed when read. |
| **`Promise.all([a, b])`** | Starts several things at once and waits until **all** are done. |
| **`` `text ${value}` ``** | A template string: `${...}` puts a value inside the text. |
| **`x.toFixed(2)`** | A number as text with 2 decimals. |
| **`.findIndex(f)`** | The position of the first item where `f` is true, or `-1`. |
| **`{ focus = true } = {}`** | A parameter with named options and a default for each. |
| **`el.dataset.walkX`** | Reads or writes the HTML attribute `data-walk-x`. |

### Lines 1–26: imports and the library path

- OWL pieces, `loadJS` (loads a script file on demand), `_t` (translation, like `self.env._` on the Python side), `registry`, `user` (the logged-in user) and `useService`.
- The warehouse picker pieces from `common/warehouse_picker`: the dropdown component and three helpers for choosing and remembering a warehouse.
- `slotBox` (section 22), `UpdateQueue` (section 24), five functions from `occupancy.js` (section 23), `WarehouseScene` (section 26), and the walk start functions (section 25).
- `LIB` is the folder holding the project's own copy of Three.js.

### Lines 28–36: the class

```js
export class View3D extends Component {
    static template = "warehouse_3d.View3D";
    static components = { WarehousePicker };
    static props = { ...standardActionServiceProps };
```

The header says it all: Inventory ▸ Warehouse 3D ▸ 3D View. It **loads Three.js on first open (not bundled)** with the warehouse's scene data, then hands both to `WarehouseScene`. The side panel shows the selected slot, Find, capacity and the occupancy legend. `props` are the standard values every Odoo action component receives, including `action` with its `context`.

### Lines 38–89: `setup`

**Services, handles and state (38–49)**

- `orm`, `action` and `bus_service` are fetched with `useService`.
- `canvasRef` and `rootRef` are handles to elements in the template.
- `state` is the reactive object the template reads:

| Field | Meaning |
|---|---|
| `error` | A message to show instead of the scene (empty means no error). |
| `rowCount` | Number of rack rows. |
| `view` | `"3d"`, `"top"`, or `""` (neither, for example when flying to a slot). |
| `labels`, `stock`, `occupancy` | The three toolbar switches. |
| `selected` | Index of the selected slot, or `-1`. |
| `find`, `findError` | The text typed in Find, and its error message. |
| `summary`, `legend` | The capacity numbers and the legend counts (section 23). |
| `updates` | A counter, bumped to force a redraw (see `applySlots`). |
| `walking` | Is walk mode on? |
| `warehouseId` | The warehouse shown. |

**The live-update queue (50–60)**

```js
this.updates = new UpdateQueue({
    delay: 150,
    retryDelay: 5000,
    fetch: (ids) => this.fetchSlots(ids),
    apply: (ids, fresh) => this.applySlots(ids, fresh),
});
this.onStockChanged = ({ location_ids }) => this.updates.push(location_ids);
this.busService.subscribe("warehouse_3d/stock", this.onStockChanged);
this.busService.start();
```

- This is how the queue from section 24 is created: it throttles to one fetch per **150 ms**, retries a failed fetch after **5 seconds**, and is given `fetchSlots` and `applySlots` below.
- The view subscribes to the bus message type `warehouse_3d/stock` (the one sent in section 13). Each message's `location_ids` go straight into the queue.
- The comment on line 50 explains the order. It **listens before loading the scene**: a stock change committed while Three.js and the scene are still loading is collected by the queue and applied once the scene is ready, so it isn't missed.

**`onWillStart` (61–75)** runs before the first draw:

1. `Promise.all` makes three requests **at the same time**: the list of warehouses (`wh3d_list_warehouses`), the default warehouse (`wh3d_default_warehouse_id`) and whether the user is an Inventory Manager (`user.hasGroup(...)`). The first two are from section 12. `canEdit` is stored, because only managers may open the layout editor.
2. `pickWarehouseId({ contextId, storedId, warehouses, defaultId })` chooses the warehouse from three sources: the one named in the action's context (section 12's buttons put `warehouse_id` there), the one remembered in this browser, or the default. The helper is in the picker file.
3. A second `Promise.all` loads **the scene data and Three.js together**, then `setScene` stores them.

**`onMounted`, `onWillUnmount`, `onWillDestroy` (76–88)**

- **Mounted:** the page elements now exist, so `start()` builds the scene and `updates.start()` switches the queue on. (This is when anything collected earlier gets fetched.)
- **Will unmount:** `this.scene?.dispose()` frees the WebGL memory (section 26).
- **Will destroy:** unsubscribe from the bus and `updates.stop()`. The comment says this runs **even if loading failed and the view never mounted**, so the listener can't leak.

### Lines 91–103: loading

- **`loadThree`:** loads `three.min.js`, then `OrbitControls.js`. The second extends the first, so the order matters. Loading only when this view opens keeps the rest of Odoo light.
- **`loadScene(id)`:**
  - With no warehouse at all, it sets an error message ("There is no warehouse yet…") and returns an **empty building** (60 × 40 × 10, no rows) so there is "a message instead of a crash".
  - Otherwise it calls `wh3d_get_scene` for that warehouse. The `[[id]]` is Odoo's way of saying "call on the record with this id".

### Lines 105–117: `setScene`

Makes a scene the data the view works with:

- `this.data` is the scene.
- Three lookups: `slotByCode` (code → index), `slotByLocation` (location id → index) and `rowsById`. An index here is the position in `data.slots`, the same index the scene uses for picking (section 26). `slotByLocation` is the `indexByLocation` that `mergeSlotUpdates` needs (section 23).
- Remember the row count and the warehouse id, store the choice with `storeWarehouseId` (remembered per browser), and compute the summary and legend with `refreshStats`.

### Lines 119–138: `switchWarehouse` (the dropdown)

The comment lists the order, which is the point:

1. If it is the same warehouse, do nothing.
2. **Load the new scene first.** If that fails, the old scene is still on the screen.
3. Then leave walk mode, **dispose the old scene**, and clear what was selected, searched or walked (and the view back to `"3d"`).
4. `setScene` with the new data.
5. `updates.stop()` then `updates.start()`: the stop clears the queue, so **ids belonging to the old warehouse are dropped** (section 24).
6. `start({ focus: false })` builds the new scene without flying to anything.

### Lines 140–166: a few small methods

- `warehouseName` is a getter for the panel.
- **`openEditor`:** opens the layout editor action (section 5) with `warehouse_id` in the context, so it opens on the same warehouse.
- **`start({ focus = true })`:** creates a `WarehouseScene` on the canvas element with two callbacks: `onSelect` stores the clicked index in `state.selected`, and `onWalk` forwards to `onWalk` below. A new scene starts with its defaults, so it then **re-applies the user's three switches** (labels, stock, occupancy). If anything goes wrong (no WebGL), the `catch` shows "The 3D view needs WebGL…".

### Lines 168–184: `focusFromContext`

When the layout editor opens the 3D view with "View in 3D", it puts `focus_row_id`, `focus_bay`, `focus_level` and `focus_position` in the context. This finds the slot with those four values (`findIndex`), selects it and flies the camera to it. Without `focus_row_id` it does nothing.

### Lines 186–206: live updates arrive here

This is the whole path of a stock change on the screen:

```js
async fetchSlots(ids) {
    const mine = ids.filter((id) => this.slotByLocation.has(id)); // others: another warehouse
    return mine.length ? this.orm.call("stock.warehouse", "wh3d_get_slots", [mine]) : [];
}

applySlots(ids, fresh) {
    if (!mergeSlotUpdates(this.data.slots, this.slotByLocation, ids, fresh)) { return; }
    this.scene?.buildStock();
    this.refreshStats();
    this.state.updates++;
}
```

- **`fetchSlots`:** keeps only ids that are in this view (the live message goes to everyone, section 13), and asks the server for just those with `wh3d_get_slots` (section 12). If none are left, it skips the request.
- **`applySlots`:** merges the fresh data into `this.data.slots` **in place** (section 23). The comment says it is the same array the scene draws from, so `buildStock()` sees the new values. If nothing changed it stops. Otherwise it redraws the stock boxes, recomputes the summary and legend, and adds 1 to `state.updates`.
- Why `state.updates++`? The slot list is not reactive, so changing it doesn't redraw the panel by itself. Changing the counter does, and the panel is redrawn explicitly.
- `refreshStats` computes `capacitySummary` and `legendCounts` from the current rows and slots.

This shows that `buildStock` is called after a live update (here, in `applySlots`), that the `slots` array is merged in place and so keeps its order, and that `dispose` is called on unmount and when switching warehouse.

### Lines 208–229: toolbar

- `setView(mode)` leaves walk mode, remembers the mode, and moves the camera (the 3D and Top buttons).
- `toggleLabels`, `toggleStock` and `toggleOccupancy` read the checkbox (`ev.target.checked`), save it in `state`, and tell the scene.

### Lines 231–264: the selected slot

- `selectedSlot` gives the slot, or `null` when nothing is selected.
- **`selectedInfo`** builds what the panel shows about the selected slot:

| Field | Value |
|---|---|
| `zone` | "Pallet racking" or "Shelving" (translated). |
| `level` | For example `2 of 5 · 1.86 m`: the level number, and the height of the slot's floor from `slotBox`. |
| `capacity` | For example `1.35 × 1.10 × 1.80 m · 2.67 m³`: slot width, depth, level height, and the capacity from the server. |
| `fill` | For example `49 %`, or empty if there is no stock or the fill is unknown. |
| `band` | `low`, `mid`, `high` or `nodims` (empty if no stock). |

- **`openInInventory`:** opens Odoo's stock quantity list, filtered to this slot's location, with the New button hidden (`create: false`).

### Lines 266–295: Find

- `onFindInput` stores the typed text and clears the error.
- `onFind` is the submit handler:
  1. `ev.preventDefault()` stops the form from reloading the page.
  2. `normalizeCode` (section 23) tidies the text. This is where it is used.
  3. Empty gives a hint with example codes.
  4. `slotByCode.get(code)` looks the code up. Unknown gives "No location …" with the examples (the `%s` is filled with the code).
  5. Found: select it, set the view to `""`, outline it, and then either **walk to it** (if walking: `enterWalk(walkStartFor(index))`, "go and stand in front of it") or **fly the camera to it** (`focusOn`).

### Lines 297–333: walk mode

- **`walkStartFor(index)`:** no slot selected gives `walkStartAtEntrance`, otherwise `walkStartAtSlot` (section 25).
- **`toggleWalk`:** the Walk button. If walking, leave. Otherwise enter at the start point for the selected slot, and set the view to `""`.
- **`onWalk(pose)`:** called by the scene on every move. `null` means walking ended (Esc or the button), so `walking` is set to false. Otherwise `walking` is true, and the position is written to `data-walk-x` and `data-walk-y` on the root element. The comment says why it is **written straight to the page, not into `state`**: it fires every frame, and reactive state would redraw the whole panel each time.
- **`percent(value)`:** `null` becomes `–`, otherwise a rounded percent like `49 %`. The panel uses it for the average fill.

### Line 336: registering

```js
registry.category("actions").add("warehouse_3d.view3d", View3D);
```

This is the line that matches the `tag` in `view3d_actions.xml` (section 5). It is how a click on the menu ends up here.

### How the pieces fit together

```
open the screen ─► onWillStart: warehouses, default, manager? ─► pick one ─► load scene + Three.js
                 ─► onMounted: new WarehouseScene (section 26) + queue.start()

stock changes on the server ─► bus message (section 13) ─► queue (section 24)
        ─► fetchSlots ─► wh3d_get_slots (section 12) ─► mergeSlotUpdates (section 23)
        ─► scene.buildStock() + refreshStats()

user acts: click ─► scene.onSelect ─► state.selected ─► panel (selectedInfo)
           Find ─► normalizeCode ─► select + focusOn / enterWalk
           Walk ─► walkStartFor ─► scene.enterWalk (section 25) ─► onWalk (DOM attributes)
           dropdown ─► switchWarehouse
```

### Why it's needed

- **It is the glue.** The server, the bus, the maths files and the scene each do one job. This file connects them to Odoo and to the user.
- **It owns the panel.** All the state the side panel shows (selection, Find, capacity, legend, switches) lives here.
- **It handles the messy parts:** the order of loading, messages arriving before the scene is ready, failed loads, warehouse switching, and clean-up.

---

## 28. `static/src/view3d/view3d_action.xml`

**The file in one sentence:** it is the HTML template of the 3D View screen: the area for the 3D picture, the toolbar, the messages and hints, and the **side panel** with the selected location, Find, capacity and legend.

It has no logic of its own. It only shows what `state` and the methods of `View3D` give it (section 27), and calls those methods when you click or type. The side panel is built here, in the `<aside>` on lines 45–121.

### Words you will see

This is OWL's template language. The `t-` words are instructions to the template engine, not HTML.

| Word | Plain meaning |
|---|---|
| **`t-name="..."`** | The name of the template. It matches `static template` in section 27. |
| **`t-ref="root"`** | Gives the element a name, so the code can reach it (`useRef` in section 27). |
| **`t-att-NAME="expr"`** | Sets the attribute `NAME` from a JavaScript expression, so it can change. |
| **`t-attf-class="a {{ x }}"`** | Builds an attribute from text with values inside `{{ }}`. |
| **`t-on-EVENT="method"`** | Calls a method when the event happens (`t-on-click`, `t-on-input`, `t-on-submit`, `t-on-change`). |
| **`t-if`, `t-elif`, `t-else`** | Show an element only if a condition is true, as in C. |
| **`t-esc="expr"`** | Prints a value as text. |
| **`t-set="info" t-value="..."`** | Gives a value a name to reuse below. |
| **`<t>`** | An invisible wrapper: it holds an instruction but adds nothing to the page. |
| **`onChange.bind="method"`** | Passes a method of this component to a child component. |
| **`aria-...`, `role`** | Information for screen readers. |
| **`<aside>`** | The HTML tag for a side column. |

Names, text and values that come from the code are in `state` (the reactive object) and the getters and methods of `View3D`.

### Lines 1–5: the root element

```xml
<div class="o_wh3d_view" t-ref="root" t-att-data-row-count="state.rowCount" t-att-data-updates="state.updates"
     t-att-data-mode="state.walking ? 'walk' : 'orbit'" t-att-data-eye="state.walking ? eyeHeight : ''">
```

- `t-ref="root"` is the `rootRef` that `onWalk` writes the walker's position onto (section 27).
- Four `data-` attributes put some state **into the page**: the row count, the update counter, the mode (`walk` or `orbit`), and the eye height while walking. A style sheet or a browser test can read these.
- **This line explains `state.updates++` in section 27.** The template **reads** `state.updates` here. OWL redraws a component when something it read changes. The slot list is not reactive, but this counter is, so adding 1 to it makes the whole template redraw with the new slot data.

The root holds two blocks: the **viewer** (left) and the **panel** (right).

### Lines 6–43: the viewer

**The 3D area (7–8)**

```xml
<!-- Three.js owns this element's children, so OWL renders nothing inside it. -->
<div class="o_wh3d_canvas" t-ref="canvas"/>
```

An empty box. Three.js adds its own canvas into it (section 26). The comment is the rule: OWL must not put anything inside, because Three.js owns the contents.

**The toolbar (9–34)**

| Control | What it does |
|---|---|
| `WarehousePicker` | The warehouse dropdown. It gets the list (`warehouses`), the current choice (`state.warehouseId`) and the method to call on change (`switchWarehouse`). |
| **3D** and **Top** buttons | Call `setView('3d')` and `setView('top')`. `t-att-aria-pressed` marks the current one. They sit in a group labelled "Camera view". |
| **Walk** button | Calls `toggleWalk`. It shows as pressed while walking. The tooltip says "Walk the aisles at eye height (from the selected slot, or the entrance)". The icon (`fa-male`) is hidden from screen readers. |
| **Stock**, **Colour by occupancy**, **Labels** | Three checkboxes. `t-att-checked` shows the current state, and `t-on-change` calls `toggleStock`, `toggleOccupancy` and `toggleLabels`. |

The buttons and boxes have `name` attributes (`view_3d`, `view_top`, `walk`, `stock`, `occupancy`, `labels`). Such names are how browser tests find them.

**Messages (35–40)**

```xml
<div t-if="state.error" class="o_wh3d_fallback" role="alert" t-esc="state.error"/>
<div t-elif="!state.rowCount" class="o_wh3d_empty" role="status">
    No rack rows in <t t-esc="warehouseName"/> yet.
    <button t-if="canEdit" ... t-on-click="openEditor">Open Layout Editor</button>
    <t t-else="">Ask an Inventory manager to lay it out in the Layout Editor.</t>
</div>
```

- If there is an error (no WebGL, or no warehouse), show it.
- Otherwise, if the warehouse has **no rack rows**, say so. Managers (`canEdit`) get an "Open Layout Editor" button, and everyone else is told to ask a manager. This matches the rule that only managers use the editor.

**Hints (41–42)** The hint line changes with the mode:

- Walking: "W A S D or arrows to walk · Shift to hurry · drag to look around · Esc to stop walking".
- Otherwise: "Drag to orbit · scroll to zoom · right-drag to pan · click a slot".

### Lines 45–121: the side panel

`<aside class="o_wh3d_panel">` holds four cards.

**1. Selected location (46–75)**

- The card has `aria-live="polite"`, so a screen reader announces it when it changes.
- With **no selection**, it says "Click a slot in the 3D view, or find one below."
- With a selection, `t-set="info" t-value="selectedInfo"` calls the getter from section 27 **once** and names the result `info`. Then it shows:
  - the slot **code** and its full **path**;
  - a list with **Zone**, **Level** and **Space** (`info.zone`, `info.level`, `info.capacity`);
  - if the slot has **stock**: a colour swatch whose class comes from the band (`o_wh3d_band_{{ info.band }}`), the product name (with "+ other products" when mixed), and a second line with the product code, the quantity and unit, and either the fill (`fill 49 %`) or "no dimensions, fill unknown";
  - if the slot is **empty**: "Empty. Available for putaway.";
  - an **Open in Inventory** button that calls `openInInventory`.

**2. Find (77–85)**

```xml
<form class="o_wh3d_card o_wh3d_find" t-on-submit="onFind" novalidate="">
    <label ... for="o_wh3d_find_input">Find a location</label>
    <input id="o_wh3d_find_input" ... placeholder="e.g. P05-03-2-A"
           t-att-value="state.find" t-on-input="onFindInput"/>
    <button type="submit" class="btn btn-primary">Go</button>
    <p t-if="state.findError" ... t-esc="state.findError"/>
```

- Pressing Enter or "Go" submits the form and calls `onFind` (section 27).
- The text box shows `state.find` and calls `onFindInput` on every keystroke.
- `novalidate` stops the browser from showing its own validation popups.
- The error line shows only when `state.findError` has text.

**3. Capacity (87–109)**

Shown only when `state.summary` exists. A table with columns **Type, Total, Used, Avg fill** and two rows: "Pallet positions" and "Shelf bins". The average is shown through `percent(...)` (section 27), so `null` appears as `–`. A note underneath says how many pallet rows and shelving rows there are. All the numbers come from `capacitySummary` (section 23).

**4. Legend (111–120)**

Shown only when `state.legend` exists. "Stocked slots by fill" with four lines and the number of slots in each:

| Line | Band |
|---|---|
| Under 50 % | `low` |
| 50–90 % | `mid` |
| Over 90 % | `high` |
| No dimensions | `nodims` |

Each line has a colour swatch with the same band class as the selected slot's swatch. The note says "Fill = product L × W × H × quantity ÷ slot volume. Turn on "Colour by occupancy" to see it in 3D."

### How it fits together

```
view3d_action.js (section 27)  ──state, getters, methods──►  view3d_action.xml  ──►  the screen
        ▲                                                           │
        └──────────── clicks, typing, checkboxes ◄──────────────────┘
```

The template reads `state` and the getters, and the clicks call the methods. The 3D picture is not drawn here: the empty `o_wh3d_canvas` box is where Three.js puts it (section 26).

### Why it's needed

- **It is the part the user sees and clicks.** Without it the logic has no screen.
- **Everything shown comes from state,** so one change in the code updates the toolbar, the panel and the hints together.
- **It is built to be used by everyone:** buttons marked pressed, labelled groups, alerts and status messages, a panel that announces changes, and decorative items hidden from screen readers.

---

## 29. `static/src/common/warehouse_picker.js` and `warehouse_picker.xml`

**The file in one sentence:** it is the warehouse dropdown shared by the 3D view and the layout editor, plus the small helpers that decide which warehouse to open and remember the choice in the browser.

It lives in the `common/` folder because **both screens use it**. The manifest loads that folder first (section 1). Its template is the small `warehouse_picker.xml` next to it, so both files are covered here.

### Words you will see

| Word | Plain meaning |
|---|---|
| **`localStorage`** | A small store of named text values inside the browser. It survives closing the page. It belongs to this browser, not to the user's account. |
| **`browser`** | Odoo's wrapper around the browser's own features (here, `localStorage`). Tests can replace it with a fake. |
| **`parseInt(text, 10)`** | Reads whole-number text as a number. If the text isn't a number, it gives `NaN` ("not a number"). |
| **`Number.isFinite(x)`** | True only for a real number (false for `NaN`). |
| **`.some(f)`** | True if any item of a list passes the test `f`. |
| **`props`** | The values a parent gives a component. The 3D view gives the picker `warehouses`, `value` and `onChange`. |
| **`static props = {...}`** | The types the picker expects. OWL warns during development if a parent passes the wrong type. |
| **`t-foreach`, `t-as`, `t-key`** | A loop in a template. `t-key` is a unique id per item, so OWL can track items. |
| **`&gt;`** | The XML way to write `>`, because `>` is special in XML. |

### Lines 1–5: imports and the storage key

```js
import { Component } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";

const STORAGE_KEY = "warehouse_3d.warehouse_id";
```

The comment says it: **one key for both screens.** The 3D view and the editor open the warehouse you looked at last, and they share this single remembered value.

### Lines 7–16: `pickWarehouseId`

**What it does:** decides which warehouse to open.

```js
export function pickWarehouseId({ contextId, storedId, warehouses, defaultId }) {
    if (contextId) {
        return contextId;
    }
    return warehouses.some((w) => w.id === storedId) ? storedId : defaultId;
}
```

The order of preference:

1. **The context.** If the screen was opened with a warehouse named in its context (the buttons on the warehouse form, section 12), use that one. It is not checked against the list.
2. **The remembered one**, but only if it is **still in the list** `warehouses`. The comment explains: that means not archived, and not another company's.
3. **The default** (`defaultId`, from `wh3d_default_warehouse_id`, section 12).

### Lines 18–34: reading and storing the choice

```js
export function readStoredWarehouseId() {
    try {
        const id = parseInt(browser.localStorage.getItem(STORAGE_KEY), 10);
        return Number.isFinite(id) ? id : null;
    } catch {
        return null;
    }
}
```

- It reads the saved text and turns it into a number.
- If nothing was saved, `getItem` gives `null`, `parseInt` gives `NaN`, `isFinite` is false, and the result is `null`.
- The `try` / `catch` is there because **storage can be blocked** (the comment: a private window). Then it returns `null` and never throws.

```js
export function storeWarehouseId(id) {
    try {
        browser.localStorage.setItem(STORAGE_KEY, String(id));
    } catch {
        // the choice just isn't remembered
    }
}
```

It saves the id as text. If saving fails, nothing happens: the choice simply isn't remembered.

**Both helpers are written so a blocked or failing store never breaks the screen.**

### Lines 36–50: the `WarehousePicker` component

```js
export class WarehousePicker extends Component {
    static template = "warehouse_3d.WarehousePicker";
    static props = { warehouses: Array, value: Number, onChange: Function };

    async onSelect(ev) {
        const select = ev.target;
        if (!(await this.props.onChange(parseInt(select.value, 10)))) {
            select.value = String(this.props.value);
        }
    }
}
```

- **The inputs:**
  - `warehouses`: the list from `wh3d_list_warehouses` (section 12). Each item is `{id, name, code, row_count}`, and only `id` and `name` are used here.
  - `value`: the id of the warehouse now shown.
  - `onChange`: a function to call when the user picks another one.
- **`onSelect`** runs when the dropdown changes. It reads the chosen id (the dropdown's value is text, so `parseInt`) and calls `onChange`.
- **The rule in the comment on lines 37–38:** `onChange` must return `true` (or a promise of `true`) when the screen switched. On `false`, for example when the user cancelled a "discard changes" dialog, **the dropdown snaps back** to the current warehouse.
- Why the snap-back is needed: by the time `onSelect` runs, the browser has already changed what the dropdown shows. If the screen didn't switch, the dropdown must be put back by hand: `select.value = String(this.props.value)`.
- `View3D.switchWarehouse` (section 27) is what the 3D view passes as `onChange`.

### The template, `warehouse_picker.xml`

```xml
<select t-if="props.warehouses.length &gt; 1" name="warehouse" class="form-select form-select-sm o_wh3d_picker"
        aria-label="Warehouse" t-on-change="onSelect">
    <option t-foreach="props.warehouses" t-as="w" t-key="w.id" t-att-value="w.id"
            t-att-selected="w.id === props.value" t-esc="w.name"/>
</select>
```

- **It only appears when there is more than one warehouse** (`t-if="props.warehouses.length > 1"`). With one warehouse, nothing is drawn.
- It is a normal HTML dropdown. `form-select form-select-sm` are Bootstrap (the style library Odoo uses) classes for a small dropdown, and `aria-label="Warehouse"` names it for screen readers. `name="warehouse"` lets a browser test find it.
- `t-on-change="onSelect"` calls the method above.
- **The options** are a loop over `props.warehouses`: one `<option>` per warehouse, with its `id` as the value and its `name` as the text. `t-att-selected` marks the one that equals `props.value`.

### How it is used

```
open the screen ─► pickWarehouseId(context, remembered, list, default) ─► warehouse shown
                         ▲
                         └── readStoredWarehouseId()   ◄── storeWarehouseId(id) when the scene is set

user picks another ─► onSelect ─► onChange(id) ─► screen switches (true) ─► stays
                                                 └─ refuses (false)     ─► dropdown snaps back
```

### Why it's needed

- **One shared dropdown.** The 3D view and the editor behave the same, from one piece of code.
- **A sensible first warehouse.** A warehouse chosen on purpose beats the remembered one, and the remembered one beats the default, but only if it is still valid.
- **It never breaks.** A blocked store, an archived warehouse or a refused switch are all handled.

---

## 30. `static/src/editor/geometry.js`

**The file in one sentence:** it holds the 2D maths of the layout editor: how to fit the building on screen, how to convert between metres on the floor plan and pixels on the screen, how to zoom and pan, and the rectangles and grid lines to draw.

Like the 3D maths files, it uses plain numbers only, so it can be unit-tested without the page. It is the 2D partner of `layout.js` (section 22).

### Words you will see

| Word | Plain meaning |
|---|---|
| **plan coordinates** | Metres from one corner of the building. `x` goes to the right, `y` goes **downwards** (like a screen, not like a maths graph). |
| **screen coordinates** | Pixels on the editor's drawing area. |
| **view** | The link between the two: `{ scale, ox, oy }`. `scale` is pixels per metre, and `ox` and `oy` are the pixel position of the plan's corner. |
| **viewport** | The visible drawing area, in pixels. |
| **`margin = 24`** | A parameter with a default: if the caller gives no margin, it is 24 pixels. |
| **`%`** | Remainder after dividing, as in C. `x % 5 === 0` means "x is a multiple of 5". |

### Lines 1–10: the header and the limits

The comment gives the rule everything else follows:

```
screen = plan × scale + offset
```

A point at plan position `(x, y)` appears on the screen at `(x × scale + ox, y × scale + oy)`. The orientation (x right, y down) is **the same as the 3D view's Top camera**, so the editor's plan and the 3D Top view look alike.

```js
export const MIN_SCALE = 1;
export const MAX_SCALE = 200;
```

You can zoom between 1 pixel per metre (a speck) and 200 pixels per metre (very close).

### Lines 12–20: `fitView`

```js
export function fitView(building, width, height, margin = 24) {
    const scale = Math.min((width - 2 * margin) / building.length, (height - 2 * margin) / building.width);
    return {
        scale,
        ox: (width - building.length * scale) / 2,
        oy: (height - building.width * scale) / 2,
    };
}
```

It finds the **largest scale at which the whole building fits**, centred, with a margin all round.

- Each side gives a scale: the room left after the margins, divided by the building's size in metres. The **smaller** of the two is used, so the building fits in both directions.
- `ox` and `oy` split the leftover space equally on each side, which centres the building.
- Example: a 60 × 40 m building in a 1000 × 700 px viewport. The scales are 952 ÷ 60 ≈ 15.87 and 652 ÷ 40 = 16.3, so the scale is 15.87 px per metre. Then `ox` = 24 and `oy` ≈ 32.7. The plan point (30, 20), the middle of the building, lands at screen (500, 350), the middle of the viewport.
- `fitView` does **not** keep the scale between `MIN_SCALE` and `MAX_SCALE`. Only `zoomAt` does that.

### Lines 22–28: `toScreen` and `toPlan`

```js
export function toScreen(view, x, y) { return [x * view.scale + view.ox, y * view.scale + view.oy]; }
export function toPlan(view, px, py)  { return [(px - view.ox) / view.scale, (py - view.oy) / view.scale]; }
```

Two functions that undo each other: metres to pixels, and pixels to metres. `toPlan` is how a mouse position (in pixels) becomes a position on the floor plan.

### Lines 30–39: `zoomAt` and `pan`

```js
export function zoomAt(view, px, py, factor) {
    const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, view.scale * factor));
    const [x, y] = toPlan(view, px, py);
    return { scale, ox: px - x * scale, oy: py - y * scale };
}
```

**Zoom around a screen point, which stays under the cursor.**

1. The new scale is the old one times `factor`, kept between 1 and 200.
2. `toPlan` finds which plan point is under the cursor now.
3. The new offset is chosen so that **the same plan point is still under the same pixel** after the zoom. That is why zooming with the mouse wheel feels like zooming into the spot you point at, not into the corner.

```js
export function pan(view, dx, dy) {
    return { scale: view.scale, ox: view.ox + dx, oy: view.oy + dy };
}
```

Panning is just sliding the offset by the number of pixels dragged. The scale does not change.

Both functions return a **new** view and leave the old one alone.

### Lines 41–49: `rowRect` and `areaRect`

```js
export function rowRect(row)   { return { x: row.x, y: row.y, w: row.depth, h: row.bays * row.bay_width }; }
export function areaRect(area) { return { x: area.x, y: area.y, w: area.width, h: area.depth }; }
```

The rectangle each thing covers on the plan, as `{ x, y, w, h }` (width and height in metres):

- A **rack row** is `depth` wide (along x) and `bays × bay_width` high (along y), the same footprint as `_wh3d_footprint` in section 8.
- A **layout area** is `width` wide (along x) and `depth` high (along y), as in section 10.

So the word `depth` runs along a different axis for a row and for an area. These two functions hide that difference: the drawing code only sees `w` and `h`.

### Lines 51–61: `gridLines`

```js
for (let x = 0; x <= building.length + 1e-9; x++) {
    lines.push({ x1: x, y1: 0, x2: x, y2: building.width, major: x % 5 === 0 });
}
```

The editor's grid: a line **every metre** in each direction, and every fifth one is marked `major`, so it can be drawn heavier. A 60 × 40 m building gives 61 vertical and 41 horizontal lines, 102 in all. (The 3D floor, in section 22, only has a line every 5 m.)

### Lines 63–66: `middleSlot`

```js
export function middleSlot(row) {
    return { bay: Math.ceil(row.bays / 2), level: 1, position: 1 };
}
```

The slot that the editor's **"View in 3D"** flies to: the **middle bay**, **ground level**, **first position**. `Math.ceil` rounds up, so 7 bays give bay 4, and 16 bays give bay 8. This is the slot identified by `focus_bay`, `focus_level` and `focus_position` in section 27.

### Why it's needed

- **Two worlds, one mapping.** The server and the layout are in metres, and the editor draws in pixels. `toScreen` and `toPlan` are the single place that converts between them.
- **Zoom and pan feel right** because `zoomAt` keeps the point under the cursor fixed.
- **Drawing is simple.** The editor gets plain rectangles and grid lines and doesn't need to know which axis is `depth`.
- **Easy to test.** Every function takes numbers in and returns numbers out. The tests are in `static/tests/editor_geometry.test.js`.

---

## 31. `static/src/editor/layout_edit.js`

**The file in one sentence:** it holds the editing rules of the layout editor as plain data: snapping, spotting problems while you drag, adding new rows, areas and dock doors, resizing and moving them, and working out exactly what Save must send.

The header says why the rules exist twice: the overlap and building rules **mirror the server's** (`warehouse.rack.row._check_layout`), so problems show up **while dragging**. The server stays the authority when saving.

### How this file mirrors the server

| In this file | Server rule it mirrors |
|---|---|
| `layoutProblems` | A row must be inside the building and must not overlap another row (`_check_layout`, sections 8 and 12). |
| `areaProblems` | An area must have a size and be inside the building, a dock must touch a wall, and a floor area must not sit on a rack row (sections 10 and 12). |
| `EDITABLE`, `AREA_EDITABLE` | `EDITOR_FIELDS`, `AREA_EDITOR_FIELDS` (section 8). |
| `diffLayout`, `diffAreas` | The `changes` dictionary that `wh3d_save_layout` receives (section 8, chunk 4). |
| `nextCode` | The row code format: a capital letter and two digits (section 8). |

### Words you will see

New ones only. The words from sections 22 to 30 still apply.

| Word | Plain meaning |
|---|---|
| **`a ?? b`** | `a`, unless `a` is `null` or `undefined`, then `b`. |
| **`a?.b`** | `a.b`, or `undefined` if `a` is missing, with no error. |
| **`/(\d+)$/`** | A pattern (regular expression): "one or more digits at the end of the text". The brackets capture them. |
| **`str.padStart(2, "0")`** | Pads the text on the left to 2 characters with `"0"`: `"7"` becomes `"07"`. |
| **`switch / case / default`** | The same multi-way choice as in C. |
| **`function f([px, py])`** | The parameter is a list, and its two items are named `px` and `py` right away. |
| **`...used`** | Passes the items of a list as separate arguments (`Math.max(0, ...used)`). |

### Lines 6–17: imports and constants

- `areaRect` and `rowRect` come from `geometry.js` (section 30).
- `EPS = 1e-6`: the tiny allowance for decimal comparisons.
- `EDITABLE` lists the row fields the editor may change, and `AREA_EDITABLE` the area fields. They are the same lists as on the server.
- `MIN_AREA_SIZE = 0.5` m: the smallest an area can be made by dragging.
- `TEMPLATE` holds the sizes of a **new row**, taken from the project handoff:
  - pallet: 7 bays of 2.7 m, 1.1 m deep, 5 levels of 1.8 m, 2 slots per level;
  - shelf: 16 bays of 1.0 m, 0.6 m deep, 5 levels of 0.4 m, 1 slot per level.

### Lines 19–39: snapping and the two basic checks

```js
export function snap(value, step = 0.1) {
    return Math.max(0, Math.round(Math.round(value / step) * step * 100) / 100);
}
```

**`snap`** rounds to the 0.1 m grid and never goes below 0. The last `* 100 ... / 100` removes tiny decimal errors, so 9.74 becomes exactly `9.7` and not `9.700000000000001`.

- `rectsOverlap(r, o)` is the same **strict overlap** test as on the server: rectangles that only touch (back to back) do **not** count. `rowsOverlap(a, b)` applies it to two rows.
- `insideRect(r, building)` checks the rectangle is within the building, with the `EPS` allowance. `inside(row, building)` does it for a row.

### Lines 41–55: `layoutProblems`

```js
export function layoutProblems(rows, building) {
    const problems = {};
    for (const row of rows) {
        if (!inside(row, building)) {
            problems[row.id] = `${row.code} is outside the ${building.length} × ${building.width} m building.`;
            continue;
        }
        const other = rows.find((o) => o !== row && rowsOverlap(row, o));
        if (other) {
            problems[row.id] = `${row.code} overlaps ${other.code}.`;
        }
    }
    return problems;
}
```

Returns `{ row id: message }` for every row that is outside the building or overlaps another. Each row gets **at most one** message: "outside" comes first, then "overlaps" (naming the first overlapping row it finds). Two overlapping rows are both flagged.

### Lines 57–62: `nextCode`

The next free code for a kind: the prefix is `P` for pallet and `S` for shelving. It reads the number after the letter in every existing code of that prefix, takes the **highest**, adds 1, and pads to two digits. So rows `P01` to `P14` give `P15`. It uses the highest number, not the first gap.

### Lines 64–79: `newRow`

A new row of a kind, with the template sizes, put on **the first free spot** of the floor:

```js
for (let y = 0; y <= building.width; y += 0.5) {
    for (let x = 0; x <= building.length; x += 0.5) {
        Object.assign(row, { x: snap(x), y: snap(y) });
        if (inside(row, building) && !rows.some((o) => rowsOverlap(row, o))) {
            return row;
        }
    }
}
return null;
```

- It scans every 0.5 m, left to right and then top to bottom, and returns the first spot where the row is inside the building and overlaps nothing.
- If there is no spot, it returns `null`.
- `tmpId` (a negative number) is the row's id until it is saved, which marks it as unsaved (section 8, chunk 4).
- It has no warehouse and no zone. The server adds those when it saves.

### Lines 81–107: the diff, what Save must send

```js
function diffRecords(original, current, fields) { ... }
export function diffLayout(original, current) { return diffRecords(original, current, EDITABLE); }
export function diffAreas(original, current)  { return diffRecords(original, current, AREA_EDITABLE); }
```

It compares the list loaded from the server (`original`) with the list now on screen (`current`) and produces exactly the dictionary `wh3d_save_layout` expects: `{ create: [{tmp_id, vals}], write: [{id, vals}], delete: [ids] }`.

- **delete:** ids in `original` that are no longer in `current`.
- **create:** rows in `current` with no original (the negative ids). Their `vals` hold all the editable fields.
- **write:** rows in both. Only the fields whose value **changed** are sent. A row with no change sends nothing.
- `pick(row, names)` builds an object of just the named fields (`Object.fromEntries`).
- `diffLayout` is for rows and `diffAreas` is for areas and docks, each with its own list of editable fields.

### Lines 109–134: the area palette and `newArea`

`AREA_TYPES` is the palette of common warehouse areas, each with a default colour and size (in metres). Custom is last:

| Key | Label | Size (width × depth) | Colour |
|---|---|---|---|
| `receiving` | Receiving | 20 × 12 | `#8fb8de` |
| `putaway` | Put-away | 12 × 10 | `#9ecfc0` |
| `packing` | Packing | 10 × 8 | `#e8a79c` |
| `staging` | Dispatch staging | 14 × 10 | `#a8d5a2` |
| `charging` | Charging | 8 × 5 | `#f2d27a` |
| `office` | Office | 8 × 6 | `#c9c9c9` |
| `returns` | Returns | 8 × 6 | `#d4b3e6` |
| `quarantine` | Quarantine | 6 × 5 | `#f0b27a` |
| `custom` | Custom area | 6 × 6 | `#c3d0dc` |

**`newArea(type, [px, py], building, tmpId)`** creates an area of a palette type, **centred on the point where it is dropped**. Its corner is the point minus half the size, snapped to the grid and then pulled back inside the building (`Math.max(0, Math.min(..., building.length - width))`). The area's name is the label, and its kind is `area`.

### Lines 136–161: `areaProblems`

Returns `{ id: message }` for areas and dock doors, one message per item, with the checks in this order:

1. **No size** (width or depth not above 0): "has no size."
2. **Outside the building.**
3. For a **dock door:** it must **touch a wall**. The test is the smallest of its four wall gaps being within `EPS`, the same test as `dockGeometry` in section 22 and the server rule in section 10.
4. For a **floor area:** it must not overlap a **rack row**.

The comment says "Doors may stand in front of racks", so a dock is never checked against rows.

### Lines 163–187: `resizeArea`

The new `{x, y, width, depth}` when an edge of an area is dragged to a plan point. The `edge` is `"n"`, `"s"`, `"e"`, `"w"`, or a corner such as `"se"` (which contains both letters, so both rules apply).

| Edge | What changes | What stays put |
|---|---|---|
| `e` | `width` becomes `snap(px) − x`, at least 0.5 | the left edge |
| `w` | `x` moves to `snap(px)` (at most `right − 0.5`), and `width` follows | the right edge |
| `s` | `depth` becomes `snap(py) − y`, at least 0.5 | the top edge |
| `n` | `y` moves to `snap(py)` (at most `bottom − 0.5`), and `depth` follows | the bottom edge |

As the comment says: snapped to 0.1 m, the opposite edge stays put, and the area never gets thinner than 0.5 m. The results are rounded to two decimals. Because `snap` never goes below 0, dragging cannot push the left or top edge out of the building, but the right and bottom edges can, and `areaProblems` flags that.

### Lines 189–242: dock doors, always on a wall

Constants:

- `DOCK_THICKNESS = 1.6` m across the wall, and `DEFAULT_DOCK_OPENING = 3` m along it.
- `MIN_DOCK_OPENING = 2` m. The comment says it is above the thickness, so a door's centre is always nearer its own wall than a neighbour's. It also keeps `layout.js` right: that file decides front or back wall by `width >= depth` (section 22). A side-wall door has `width = 1.6` and `depth = opening`, so `opening` must stay above 1.6 for it to be recognised as a side door.
- `DOCK_COLOR = "#e3a22b"`.

**`snapDockToWall([px, py], building, opening)`** puts a door of a given opening on the **nearest wall**:

```js
const distance = { front: py, back: W - py, left: px, right: L - px };
const wall = Object.keys(distance).reduce((a, b) => (distance[b] < distance[a] ? b : a));
```

- The distance to each wall is measured, and the smallest wins (on a tie, the first of front, back, left, right).
- `along(centre, wallLength)` slides the door along the wall in 0.1 m steps and keeps it within the ends of the wall.
- A door on the **front** wall is `{ x: along, y: 0, width: opening, depth: 1.6 }`. On the **back** wall it is `y: W − 1.6`. On the **left** and **right** walls the opening runs along y, so **width and depth swap**: `{ x: 0 or L − 1.6, y: along, width: 1.6, depth: opening }`.

The other door functions all use it:

- `moveDock(dock, centre, building)`: moves the door to a new centre. It **jumps to whichever wall is nearest**, keeping its opening (the longer of its two sides).
- `setDockOpening(dock, opening, building)`: a new opening on the same wall around the same centre. An opening under 2 m changes nothing.
- `newDock(point, building, tmpId, areas)`: a new door dropped at a point. It is named "Dock door N", where N is one more than the highest number at the end of an existing dock's name (the pattern `/(\d+)$/`, with `?? 0` when a name has no number). Its kind is `dock` and its colour is `DOCK_COLOR`.

### Why it's needed

- **Instant feedback.** The editor can warn about an overlap or a door floating in the middle of the floor **while the user is dragging**, without waiting for a save.
- **Sensible defaults.** New rows get the template sizes and the first free spot. New areas come from a palette. Doors always land on a wall.
- **A correct Save.** The diff turns "what is on screen now" into exactly what the server expects, and sends only the fields that changed.
- **Easy to test.** All of it is plain data in and out. The tests are in `static/tests/layout_edit.test.js`.
- **The server still has the last word.** These checks are a convenience. The server re-checks everything on save (section 8).

---

## 32. `static/src/editor/editor_action.js`

**The file in one sentence:** it is the Layout Editor screen: an Odoo component that shows the floor plan from above, lets a manager drag, edit, add and delete rows, areas and dock doors, and sends everything to the server in one all-or-nothing Save.

This is the file that section 5 points to for the action tag `warehouse_3d.editor`. It is the screen layer that sits on top of the two editor maths files:

```
editor_action.js   (this file: the screen, mouse, keys, Save)
      │ uses
      ▼
layout_edit.js     (rules and edits, section 31)
      │ uses
      ▼
geometry.js        (plan ↔ screen maths, section 30)
```

The panel and drawing are in the template `editor_action.xml`, a separate file. This file holds the state and the actions that template uses.

### Words you will see

Words from sections 27 to 31 still apply. New ones:

| Word | Plain meaning |
|---|---|
| **SVG** | Drawing made of shapes in the page. Here the plan is drawn in **metres** in one group, and one `transform` (move + scale) zooms and pans all of it. |
| **pointer events** | `pointerdown`, `pointermove`, `pointerup`: the mouse (or finger) pressing, moving and releasing. |
| **pointer capture** | `setPointerCapture(id)` makes the element keep getting move events during a drag, even when the pointer leaves it. |
| **drag and drop** | `ev.dataTransfer` carries a value from the thing being dragged to the place it is dropped. |
| **`ConfirmationDialog`** | Odoo's ready-made yes/no pop-up. |
| **notification** | Odoo's "toast" message in the corner. |
| **`useSetupAction`** | An Odoo hook that lets the screen react when the user is about to leave. |
| **`dirty`** | "Has unsaved changes." |
| **`{ areas, ...rows } = obj`** | Takes `areas` out of `obj`, and puts everything else in `rows`. |
| **`this.nextTmpId--`** | Uses the current value, then subtracts 1. |
| **`new Promise((resolve) => ...)`** | Makes a result that arrives later, when `resolve(value)` is called. |

### Lines 1–43: imports and constants

- The OWL hooks, `ConfirmationDialog`, `_t`, `registry`, `useService`, `useSetupAction` and the standard action props.
- From `geometry.js` (section 30): `areaRect`, `fitView`, `gridLines`, `middleSlot`, `pan`, `rowRect`, `toPlan`, `zoomAt`.
- From the picker (section 29): the dropdown and its three helpers.
- From `layout_edit.js` (section 31): the palette, the problem checks, the diffs, the move, new and resize functions, and `snap`.

| Constant | Meaning |
|---|---|
| `ZOOM_STEP = 1.15` | Each wheel notch zooms by 15%. |
| `INT_FIELDS` | `bays`, `levels`, `slots_per_level`: these must be whole numbers. |
| `AREA_DRAG_TYPE` | A custom drag type, so **only items from the palette** can be dropped on the plan. |
| `HANDLE_PX = 9` | Resize handles stay 9 pixels on the screen at any zoom. |
| `EDGES` | The eight handle positions as fractions of an area's rectangle: `nw [0,0]`, `n [0.5,0]`, `ne [1,0]`, `e [1,0.5]`, `se [1,1]`, `s [0.5,1]`, `sw [0,1]`, `w [0,0.5]`. |

### Lines 45–97: the class and `setup`

The comment sums it up: the floor plan seen from above, drawn in SVG. **Everything is drawn in metres inside one `<g transform>`**, so zooming and panning only change that transform. **Nothing reaches the server until Save**, which sends every change in one all-or-nothing call (`wh3d_save_layout`, section 8). Dock doors are areas of kind `dock` that always sit on a wall.

**State and fields (58–70)**

| Name | Meaning |
|---|---|
| `state.view` | The zoom and pan, `{ scale, ox, oy }` (section 30). It starts at a placeholder, then `fit()` sets it. |
| `state.rows`, `state.areas` | The rows and areas **as they are on screen now**. |
| `state.selectedId`, `state.selectedAreaId` | The selected row or area (only one at a time). |
| `state.saving`, `state.warehouseId` | Is a save running, and which warehouse is open. |
| `areaTypes` | The palette from `layout_edit.js`. |
| `drag`, `itemDrag`, `resizeDrag` | The drag in progress: panning the floor, moving a row or area, or resizing an area's edge. Plain fields, not reactive state. |
| `userMoved` | Once the user zooms or pans, resizing the window no longer refits the plan. |
| `nextTmpId = -1` | New rows and areas get negative ids (−1, −2, …) until they are saved. |

**Starting up (71–87)**

- `onWillStart` fetches the warehouse list and the default **in parallel**, then calls `openWarehouse(pickWarehouseId(...))`. The choice follows the same rule as the 3D view (section 29): context first, then the remembered one, then the default.
- `onMounted` adds a `ResizeObserver` that refits the plan when the window changes, **unless the user has already moved the view** (`!this.userMoved && this.fit()`), and does a first `fit()`.

**Guarding unsaved work (88–96)**

`useSetupAction` gives two hooks:

- `beforeLeave: () => this.confirmLeave()`: ask before navigating away inside Odoo.
- `beforeUnload`: if `dirty`, call `preventDefault()` and set `returnValue = ""`, so the **browser shows its own "leave site?" prompt** when the tab is closed or reloaded.

### Lines 99–130: loading and switching warehouses

- **`openWarehouse(id)`:** loads the floor plan with `wh3d_get_layout` (section 12), remembers the id in `state.warehouseId`, and stores the choice in the browser.
- **`switchWarehouse(id)`:** this is the function the dropdown calls as `onChange` (section 29).
  1. Same warehouse: return `true`.
  2. `if (!(await this.confirmLeave())) return false;` so, with unsaved edits and a "keep editing" answer, it returns **`false`**, and the dropdown snaps back.
  3. Otherwise it opens the new warehouse, clears the selection, resets the temporary ids, the drags and `userMoved`, refits, and returns `true`.
- **`load(layout)`:** keeps `this.layout` (what the server sent), makes **two separate copies** of the rows and of the areas (`{ ...r }` copies each record): `original` and `originalAreas` (what the server has) and `state.rows` and `state.areas` (what is being edited). It also builds the grid lines. Editing changes only the second copies.

### Lines 132–201: derived values the template uses

| Getter | What it gives |
|---|---|
| `transform` | The SVG transform text: `translate(ox oy) scale(scale)`. |
| `problems`, `areaProblemMap` | The messages from `layoutProblems` and `areaProblems` (section 31), by id. |
| `problemList` | All messages in one list. |
| `changes` | **The Save payload:** `{ ...diffLayout(...), areas: diffAreas(...) }`, exactly the dictionary `wh3d_save_layout` expects. |
| `dirty` | True if anything was created, written or deleted. It takes `areas` out of `changes` and checks each part. |
| `selectedRow`, `selectedArea` | The selected record, or `null`. |
| `areaCount`, `dockCount` | How many floor areas and how many docks. |
| `dockOpening(dock)` | The longer of a dock's two sides. |
| `handles` | The eight resize handles of the selected area as `{ edge, x, y }` in metres. |
| `handleSize` | `HANDLE_PX / scale`: because the plan is drawn in metres, a 9-pixel handle must be 9 ÷ scale metres. |
| `rowRect`, `areaRect`, `metres` | Wrappers so the template can use them. `metres` is `value.toFixed(2)`. |

Because `dirty` and `changes` are **worked out by comparing** the two copies, moving a row away and then back leaves nothing changed, and the screen is not dirty.

### Lines 203–223: fit, zoom and pan

- **`fit()`:** reads the plan element's size and, if it has one, sets the view to `fitView(building, w, h)`.
- **`onFitClick()`:** the Fit button: allow refitting again and fit.
- **`onWheel(ev)`:** stops the page from scrolling, takes the mouse position relative to the plan, zooms in for a scroll up (`ZOOM_STEP`) or out for a scroll down (`1 / ZOOM_STEP`) with `zoomAt`, and sets `userMoved`.

### Lines 225–306: the pointer, in four jobs

**Starting a drag**

- **`onPointerDown`:** only the left button. If the click landed on a row, area, dock or handle (`ev.target.closest(".o_wh3d_row, ...")`), it returns, because those start their own drags. Otherwise it starts **panning**: `drag = { x, y, view, moved: false }`, and captures the pointer.
- **`onRowPointerDown` and `onAreaPointerDown`** call `startItemDrag`. It stores `itemDrag = { list, id, x, y, from, moved }`, where `from` is the item's **starting** position and size.
- **`onHandlePointerDown(ev, edge)`:** starts `resizeDrag = { edge, id }` for the selected area.

**`planPoint(ev)`** turns a mouse event into plan metres with `toPlan` (section 30).

**`onPointerMove(ev)`** does the dragging:

1. **Resizing:** `Object.assign(area, resizeArea(area, edge, planPoint(ev)))`. Done.
2. Otherwise, with no drag in progress, do nothing.
3. A drag only counts once the pointer moved **more than 4 pixels**. Until then it is still a click.
4. **Moving an item:**
   - A **dock** follows the mouse by its **centre** and calls `moveDock`, so it **jumps to the nearest wall**.
   - A **row or area** goes to `snap(from + movement ÷ scale)`. The pixel movement is divided by the scale to get metres.
   - The item being dragged is selected.
5. **Panning:** `userMoved = true` and `view = pan(drag.view, dx, dy)`.

Both moves are calculated from the **starting** state (`from`, `drag.view`) and the total movement since the press, not added up step by step, so they can't drift.

**`onPointerUp`:** if it was a panning drag that never moved, it was a click on empty floor, so the selection is cleared. Then all three drags are reset.

### Lines 308–349: selection and the keyboard

- **`select(list, item)`:** one thing is selected at a time: a row or an area. It sets one id and clears the other. `selectRow`, `selectArea` and `clearSelection` are shortcuts.
- **`onKeydown`:** Escape clears the selection.
- **`arrowMove(ev)`:** an arrow key gives a move of 0.1 m, or 1 m with Shift. Other keys give `undefined`.
- **`onRowKeydown(ev, row)`:** arrow keys **nudge** the focused row by that amount, snapped to the grid.

### Lines 351–431: editing

- **`onFieldInput(field, ev)`:** called when a field is **committed** (Enter, leaving the box, or a spinner click), not on every key. The comment says why: re-rendering while you type rewrites the box, and a half-typed `10.` would be lost.
  - `code`: trimmed and turned to capitals.
  - `kind`: set, and **a shelf row is forced to `slots_per_level = 1`** ("shelving has one bin per level (server rule)").
  - Other fields: whole numbers for `INT_FIELDS`, decimals otherwise. A value that is not a number or is below 0 is **ignored**. Decimals are rounded to 2 places.
- **`addDock(at)`:** a dock dropped on the plan lands on the wall nearest the drop. A click puts it in the middle of the front wall.
- **`addArea(type, at)`:** a palette item that was dropped goes where it was dropped. If it was clicked, it goes to the middle of the view (`toPlan` of the plan's centre).
- **Palette drag and drop:**
  - `onPaletteDragStart` puts the item's key in `dataTransfer` under `AREA_DRAG_TYPE`.
  - `onPlanDragOver` allows the drop only for that type.
  - `onPlanDrop` finds the palette type (or the key `dock`), works out the drop point with `planPoint`, and calls `addArea` or `addDock`.
- **`onAreaField(field, ev)`:** the same rules for an area: `name` keeps the old one if left empty, `opening` (docks) calls `setDockOpening`, `color` must look like `#rrggbb` or the old one stays (and it is lower-cased), and other numbers must be 0 or more, rounded to 2 places.
- **`onAreaKeydown`:** for a **dock**, arrow keys move it by its centre with `moveDock`, so it may jump to another wall. Other areas nudge like rows.

### Lines 443–489: adding, deleting and discarding

- **`deleteArea()`:** a confirmation dialog: "Delete area X?" or "Delete dock door X?", with the explanation "It is only a drawing: no stock or locations are affected. The deletion is saved with Save." On confirm, the item is filtered out and the selection cleared.
- **`addRow(kind)`:** `newRow` (section 31). If there is no free floor (`null`), a warning toast says so. Otherwise the row is added and selected.
- **`deleteRow()`:** a dialog: "Delete rack row X?" with "Its locations will be archived when you save. Saving is refused if any of them holds stock." This matches the server's behaviour in section 8.
- **`discard()`:** puts both lists back from the original copies.

### Lines 491–526: `save` and `confirmLeave`

```js
const result = await this.orm.call("warehouse.rack.row", "wh3d_save_layout", [this.layout.warehouse_id, this.changes]);
const { selectedId: selected, selectedAreaId: selectedArea } = this.state;
this.load(result.layout);
this.state.selectedId = selected < 0 ? result.created[selected] ?? null : selected;
this.state.selectedAreaId = selectedArea < 0 ? result.created_areas[selectedArea] ?? null : selectedArea;
```

- **`save()`** sends the whole `changes` dictionary in one call to `wh3d_save_layout` (section 8, chunk 4).
- On success it **reloads everything from the layout the server returned** (`result.layout`), so the screen shows the saved truth.
- A selected item that was new (negative id) keeps its selection **under its real id**: `result.created[selected]` is a dictionary lookup by temporary id, as in section 19. `?? null` covers a missing id.
- It shows a "Layout saved." toast.
- **On failure** (`catch`), nothing was saved, because the server applies all changes or none. The edits stay on screen, and a **sticky red toast** titled "Layout not saved" shows the server's message (`error.data?.message || error.message || String(error)`).
- `finally` always sets `saving` back to false.

**`confirmLeave()`** returns `true` straight away if nothing is dirty. Otherwise it returns a Promise tied to a dialog: "Discard layout changes?" with the button "Discard and leave". Confirm resolves `true`, cancel resolves `false`. Returning `false` keeps the user on the editor. It is used by `beforeLeave` and by `switchWarehouse`.

### Lines 528–568: going elsewhere

- **`viewIn3d()`:** opens the 3D view (section 5) on the same warehouse with `focus_row_id`, `focus_bay`, `focus_level` and `focus_position` in the context. The slot comes from `middleSlot` (section 30). These are the keys that `focusFromContext` reads in section 27.
- **`openWarehouseForm()`:** opens the warehouse's own form, where the building size is set. Leaving asks first if there are unsaved edits.
- **`openRowForm()`:** opens the standard form of the selected row (section 11).
- **`isEmpty`:** true when there are no rows and no areas.
- The last line registers the component under `warehouse_3d.editor` (section 5).

### How it fits together

```
open ─► pick warehouse ─► wh3d_get_layout ─► load(): original copy + editing copy

edit (drag, type, palette, keys) ─► changes the editing copy only
        ─► problems / dirty / changes are worked out by comparing the two copies

Save ─► changes ─► wh3d_save_layout (all or nothing)
          ├─ ok     ─► reload from the server's layout, keep the selection under its real id
          └─ error  ─► edits stay, a sticky message shows

leave / switch warehouse / close the tab ─► asked first if dirty
```

### Why it's needed

- **It is the editor.** The server rules and the maths files do nothing visible until this screen puts them in the manager's hands.
- **Safe by design.** Nothing is sent until Save. Leaving with unsaved work is blocked in three ways. A failed save loses nothing.
- **Direct and fast.** You drag items on a plan, see problems straight away, and zoom and pan freely.

---

## 33. `static/src/editor/editor_action.xml`

**The file in one sentence:** it is the HTML and SVG template of the Layout Editor: the drawn floor plan with its rows, areas, docks and resize handles, the toolbar above it, and the **side panel** with the save bar, the palette, and the cards for the selected area, the selected rack row and the floor.

It has no logic of its own. It shows what `state` and the getters of `LayoutEditor` give it (section 32), and calls that component's methods when you click, drag or type. The side panel is the `<aside>` on lines 74–190.

### Words you will see

The `t-` words from section 28 still apply (`t-if`, `t-else`, `t-esc`, `t-on-...`, `t-att-...`, `t-set`, `t-foreach`, `t-ref`). New ones:

| Word | Plain meaning |
|---|---|
| **`<svg>`, `<g>`, `<rect>`, `<line>`, `<text>`** | SVG drawing shapes. `<g>` groups shapes, so one transform can move and scale all of them. |
| **`vector-effect="non-scaling-stroke"`** | Keeps an outline the same thickness on screen, however much the group is zoomed. |
| **`t-att-class="{ name: condition, ... }"`** | Adds each class `name` only when its condition is true. |
| **`row_index`, `line_index`** | `t-foreach="x" t-as="row"` also gives a counter called `row_index`. |
| **`t-key`** | A unique id per item in a loop, so OWL can track items. |
| **`&lt;`** | The XML way to write `<`. |
| **`and`, `or`, `not`** | Allowed in template expressions, as well as `&&`, `\|\|` and `!`. |
| **`tabindex="0"`** | Lets the keyboard reach an element with Tab. |
| **`role="button"`, `aria-label`, `aria-pressed`** | Tell a screen reader what an element is, how to read it, and whether it is selected. |
| **`draggable="true"`** | Lets the element be dragged with the mouse. |
| **`t-on-change`** | Fires when a value is **committed**, not on every keystroke (section 32 explains why). |

### Lines 3–6: the root element

```xml
<t t-set="rowProblems" t-value="problems"/>
<t t-set="areaIssues" t-value="areaProblemMap"/>
<div class="o_wh3d_editor" t-on-keydown="onKeydown" t-att-data-dirty="dirty ? '1' : '0'">
```

- The two `t-set` lines call the getters `problems` and `areaProblemMap` **once** and give the results short names. Every row and area in the loops below then reads from those, instead of recalculating the checks for each one.
- `t-on-keydown="onKeydown"` is what makes Esc clear the selection (section 32).
- `data-dirty` puts "has unsaved changes" into the page as `1` or `0`.

The root holds two blocks: the **main area** (plan, toolbar, hint) and the **panel**.

### Lines 8–60: the floor plan (SVG)

```xml
<svg t-ref="plan" class="o_wh3d_plan" role="group" aria-label="Floor plan"
     t-on-wheel="onWheel" t-on-pointerdown="onPointerDown"
     t-on-pointermove="onPointerMove" t-on-pointerup="onPointerUp"
     t-on-dragover="onPlanDragOver" t-on-drop="onPlanDrop">
```

- `t-ref="plan"` is the `planRef` the code uses for its size and position.
- Six events go to the methods from section 32: the wheel (zoom), the three pointer events (panning and dragging), and drag-over and drop (the palette).
- The comment on line 12 repeats the key idea: **everything inside is in metres, and one transform does all the zooming and panning.** That transform is on the first `<g>`: `t-att-transform="transform"`.

**Inside that group, in drawing order:**

**1. The floor (14–15).** A rectangle from `0, 0` as big as the building (`layout.building.length` × `width`).

**2. The grid (16–20).** One `<line>` per entry of `grid` (from `gridLines`, section 30). A line with `major` gets the class `o_major`. `vector-effect="non-scaling-stroke"` keeps the lines thin however much you zoom. (The group is scaled, so without this, the lines would become thick when zoomed in.)

**3. The areas and docks (21–34).** One `<g>` per item of `state.areas`:

- **Classes by state:** `o_wh3d_area` or `o_wh3d_dock` by kind, `o_selected` if selected, `o_invalid` if there is a problem for it, and `o_new` if its id is negative (not saved yet). The style sheet uses these to show each state.
- **Keyboard and screen reader:** `tabindex="0"`, `role="button"`, `aria-pressed` for selected, and an `aria-label` such as "Area Receiving" or "Dock door Dock door 1: must touch a wall". When there is a problem, its message is **read out as part of the label**.
- **Events:** pointer down starts a drag (`onAreaPointerDown`), click and focus both select it (so pressing Tab to it selects it), and key down handles the arrow keys (`onAreaKeydown`).
- **Drawing:** `areaRect(area)` gives the rectangle. A floor area is filled with its own `color`. A **dock gets no fill** (`false` removes the attribute) and is styled by the style sheet. Only floor areas show their name as text, centred in the rectangle.

**4. The rack rows (35–50).** The same pattern for `state.rows`: classes `o_wh3d_row`, `o_selected`, `o_shelf`, `o_invalid` and `o_new`, an `aria-label` like "Rack row P05: overlaps P06.", and the rectangle from `rowRect(row)`. The row's code is drawn **above or below** the row, depending on whether `row_index` is odd or even. The comment says why: so back-to-back neighbours' codes don't collide. (The 3D view labels use the same idea, section 22.)

**5. The resize handles (51–58).** Only when an area is selected **and it is a floor area** (docks have no handles). One small square per entry of `handles`, centred on its position (`h.x - handleSize / 2`) and sized `handleSize`, so it stays 9 pixels on screen (section 32). Pressing one calls `onHandlePointerDown(ev, h.edge)`. The comment on line 51 explains the placement: **outside the area's own group**, so grabbing a handle doesn't also move the area.

### Lines 61–72: the toolbar and the hint

- The **warehouse dropdown** (`WarehousePicker`, section 29), with `onChange.bind="switchWarehouse"`.
- **Pallet row** and **Shelf row** buttons call `addRow('pallet')` and `addRow('shelf')`.
- **Fit to screen** calls `onFitClick`.
- The hint line lists every gesture: "Scroll to zoom · drag the floor to pan · drag a row or area to move it (0.1 m steps) · drag an area's handles to resize it · drag an area type from the right onto the plan · arrow keys nudge · Esc clears".

### Lines 74–190: the side panel

`<aside class="o_wh3d_editor_panel">` holds five cards.

**1. Save bar (75–87)**

- It has the class `o_dirty` while there are unsaved changes.
- The note says "All changes saved." or "Unsaved changes. Nothing is stored until you save."
- If there are problems (`problemList.length`), a list of every message is shown, with `role="alert"` so a screen reader announces it.
- **Save** is disabled when `!dirty or problemList.length or state.saving`: **you can't save while there is nothing to save, while any problem is showing, or while a save is running.** That is where the browser-side rules of section 31 stop a bad layout from being sent (the server re-checks anyway).
- **Discard** is disabled when there is nothing to discard or a save is running.

**2. The palette, "Add area" (89–107)**

- One button per palette type (`t-foreach="areaTypes"`), with a colour swatch (`t-att-style="'background:' + type.color"`) and its label. Each is `draggable="true"`: dragging starts `onPaletteDragStart(ev, type.key)`, and a click calls `addArea(type)`.
- A last **Dock door** button does the same with the key `'dock'`, and `addDock()` on click.
- The note says: "Drag onto the plan, or click to add in the middle. Areas are drawings only: no stock or locations. A dock door snaps to the nearest wall."

**3. The selected area or dock (109–138)**

Shown only when `selectedArea` exists. It shows the kind ("Area" or "Dock door"), the name, and the problem message if there is one. The fields call `onAreaField` when committed:

- **Name:** a text box.
- **For a floor area:** a **Colour** picker (`type="color"`), then **X, Y, Width and Depth** in metres (number boxes with `min="0"` and `step="0.1"`), made with one loop over four field names.
- **For a dock:** one **Opening (m)** box with `min="2"`, the same as the minimum opening in section 31. A note says "Drag the door along any wall; it jumps to the nearest wall."
- A **Delete** button calls `deleteArea` (which asks first).

**4. The rack row (140–175)**

- With **no selection** it says: "Click a rack row on the plan, or Tab to one. Add rows with the buttons above the plan."
- With a selected row it shows:
  - the code and the problem message if there is one;
  - **Code** (text) and **Kind** (a dropdown: Pallet rack or Shelving), each calling `onFieldInput`;
  - a loop over **eight number boxes**: X, Y, Bays, Bay width, Depth, Levels, Level height, Slots per level, each with its step (0.1 for metres, 1 for counts);
  - **Slots per level is disabled for a shelf** (`row.kind === 'shelf'`), matching the rule that shelving has one slot per level (section 32 forces it to 1, and section 11's form makes it read-only).
- Three buttons:
  - **View in 3D** is **disabled when the row is unsaved (`row.id < 0`) or when there are any unsaved changes (`dirty`)**, with the tooltip "Save first". So the 3D view is only opened for a row that exists on the server.
  - **Open record** is disabled for an unsaved row, and calls `openRowForm`.
  - **Delete** calls `deleteRow` (which asks first).

**5. Floor (176–189)**

- A summary line: "Building L × W m · N rack rows · A areas · D docks".
- If the layout is empty (`isEmpty`): "No layout yet. Add rows with the buttons above the plan, and areas and dock doors from the palette. If the building is not L × W m, set its size first." and a **Set building size** button, which calls `openWarehouseForm`, the warehouse form where the building size is set (section 12).

### How it fits together

```
editor_action.js (section 32)  ──state, getters, methods──►  editor_action.xml  ──►  the screen
        ▲                                                           │
        └──── clicks, drags, typing, drops, wheel, keys ◄───────────┘
```

### Why it's needed

- **It is what the manager sees and touches.** Without it the editor's logic has no screen.
- **State shows on the screen:** a selected, invalid or unsaved item looks different and is read out differently to a screen reader.
- **It keeps bad data from being saved,** because Save is disabled while any problem is showing.
- **It can be used with the keyboard:** every row and area can be reached with Tab, selected, and nudged with the arrow keys.
