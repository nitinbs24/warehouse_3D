# Task list: `warehouse_3d`

Plan and rationale: `docs/plan.md`. Status: **awaiting approval**.

Paths below are relative to `warehouse_3D/warehouse_3d/` (the module) unless they start with `docs/` or `/`.
Every task is test-first: write the failing test(s) in **Verification**, see them fail, implement, see them pass, refactor.
Every task ends with: full module test run green with **no skipped browser tests**, an entry in `docs/notes.md`, and a suggested commit message. Nitin commits; Claude never does.
**Claude stops after every task and reports progress; the next task starts only when Nitin says "continue".**

`TEST` = `<venv python> warehouse_3D/run_tests.py` (Linux and Windows; `run_tests.sh` wraps it on Linux): fresh `wh3d_test` DB with demo, port 8079, fails on any error/failure/skipped browser test/failed demo data/no tests. One class: `run_tests.py /warehouse_3d:TestName`.
Tours live in `static/tests/tours/` (Odoo convention, loaded via `web.assets_tests`); their Python drivers in `tests/test_tours.py`.

---

## Phase 0 — Environment

### T0: Odoo 19 config, DB, git, empty module, proven test command
**Description:** Separate Odoo 19 setup next to the untouched Odoo 18 one, plus an installable empty module and a test pipeline that provably runs Python and browser tests.

**Acceptance criteria:**
- [x] `/mnt/CODE/Workspace/odoo/odoo19.conf` exists (addons path `odoo19/addons,warehouse_3D`, DB `warehaven`, port 8069, bound to 127.0.0.1). `odoo.conf` byte-identical to before (sha256 checked).
- [x] `warehouse_3d` (manifest: depends `stock`, LGPL-3) installs on a fresh DB; `git init` in `warehouse_3D/` with `.gitignore` (no commits).
- [x] `websocket-client` 1.9.2 installed in `venv19`; one Python test and one tour **run** (not skipped): `0 failed, 0 error(s) of 2 tests`.

**Verification:** done 23 Oct — `run_tests.sh` exit 0; deliberately broken test made it exit 1 (then restored).
**Dependencies:** none
**Files:** `/…/odoo19.conf`, `__manifest__.py`, `__init__.py`, `tests/__init__.py`, `tests/test_smoke.py`, `.gitignore`
**Scope:** S

---

## Phase 1 — Layout data → real Inventory locations

### T1: `warehouse.rack.row` model, validation, views, menu
**Description:** The core record from the handoff, editable in Odoo's standard list/form, under *Inventory ▸ Configuration ▸ Warehouse 3D ▸ Rack rows*. Adds the slot index fields to `stock.location` via `_inherit`.

**Acceptance criteria:**
- [x] Fields: `code`, `kind` (pallet/shelf), `x`, `y`, `bays`, `bay_width`, `depth`, `levels`, `level_height`, `slots_per_level`, `warehouse_id`, `location_id` (zone parent), `storage_category_id`, `active`. `stock.location` gains `wh3d_rack_row_id`, `wh3d_node`, `wh3d_bay`, `wh3d_level`, `wh3d_position`.
- [x] Rejected with a clear message: non-positive dimensions/counts, negative x/y, `code` not matching `^[A-Z]\d{2}$`, duplicate code per warehouse, shelf with `slots_per_level ≠ 1`, `slots_per_level > 26`, zone location outside the warehouse's stock location.
- [x] Access rules: Inventory users read, Inventory managers write. "Storage Locations" setting switched on by the module.

**Verification:** done 23 Oct — `tests/test_rack_row.py` 11 tests (incl. regression for the missing "New" button on Locations, found in manual check); full run `0 failed, 0 error(s) of 13 tests`. Manual (Nitin): create P05 from the handoff record in the UI.
**Dependencies:** T0
**Files:** `models/warehouse_rack_row.py`, `models/stock_location.py`, `views/warehouse_rack_row_views.xml`, `views/menus.xml`, `security/ir.model.access.csv`, `tests/test_rack_row.py`
**Scope:** M

### T2: Generate the location tree from a rack row
**Description:** Creating a rack row builds its `stock.location` subtree (decision 4 in the plan). A form button "Regenerate locations" exists for repair.

**Acceptance criteria:**
- [x] P05 (7 bays × 5 levels × 2) → exactly 70 internal slot locations `P05-01-1-A … P05-07-5-B`, full name `WH/Stock/PR/P05/P05-03/P05-03-2/P05-03-2-A`; all nodes `internal` (a `view` node would cut the path); only slots carry the row's storage category; all carry indices and `wh3d_node`. A "Closest location" putaway rule on the zone puts stock into a slot, never a bay/level node.
- [x] Shelf S04 (16 × 5) → 80 slots `S04-01-1 … S04-16-5`, path `WH/Stock/SH/S04/S04-10/S04-10-3`.
- [x] Generating twice is idempotent (no duplicates). 14 pallet rows generate in < 30 s (timed test).

**Verification:** done 23 Oct — `tests/test_location_generator.py` 10 tests (counts, names, paths, internal usage, category on slots only, indices, idempotency, repair, internal-zone rule, closest putaway → slot, 14 rows ≈ 4.6 s); full run `0 failed, 0 error(s) of 23 tests`. Manual: Inventory ▸ Locations shows the tree; a manual receipt can target `P05-03-2-A`.
**Dependencies:** T1
**Files:** `models/warehouse_rack_row.py`, `views/warehouse_rack_row_views.xml`, `tests/test_location_generator.py`
**Scope:** S

### T3: Regenerate on edit / delete without losing stock
**Description:** Changing a row keeps locations in sync, never destroying stock (decision 5).

**Acceptance criteria:**
- [x] Rename P05→P15 renames all 70 slots and intermediates in place (same record ids, quants untouched). Moving x/y changes no location.
- [x] Grow (bays 7→8) adds 10 slots; shrink (7→6) archives the 10 removed slots when empty, and raises `UserError` listing the codes when any holds stock (nothing changes).
- [x] Deleting/archiving a row archives its subtree, with the same stock guard.

**Verification:** done 23 Oct — `tests/test_location_sync.py` 15 tests: rename, move, grow, shrink-empty, shrink-with-stock, shrink-with-incoming-transfer, regrow reuses archived, fewer levels, category, pallet→shelf, zone move, archive/unarchive, archive-with-stock, delete, delete-with-stock. Full run `0 failed, 0 error(s) of 38 tests`.
**Dependencies:** T2
**Files:** `models/warehouse_rack_row.py`, `tests/test_location_sync.py`
**Scope:** S

### T3b: Lock generated locations *(added 23 Oct after the T3 manual check)*
**Description:** A generated slot was re-parented by hand inside another slot. The rack row owns name, parent and type of its locations; lock them so the tree can't drift.

**Acceptance criteria:**
- [x] On a generated location, writing a different name / parent / type raises `UserError` naming the rack row; same-value writes and all other fields are allowed; ordinary locations are unaffected.
- [x] Location form shows a "Managed by rack row …" banner and those three fields read-only.
- [x] Rack row edits (rename, re-parent via `_sync_locations`) still work.

**Verification:** done 23 Oct — `tests/test_location_lock.py` 9 tests; full run `0 failed, 0 error(s) of 47 tests`.
**Dependencies:** T3
**Files:** `models/stock_location.py`, `views/stock_location_views.xml`, `models/warehouse_rack_row.py`, `__manifest__.py`, `tests/test_location_lock.py`
**Scope:** S

### T3c: Code-review fixes *(added 23 Oct after `/code-review`)*
**Description:** Fix review findings #1–#6 and #9 (see `docs/notes.md` T3c); #7 and #8 deliberately deferred with reasons.

**Acceptance criteria:**
- [x] Removal check uses the exact set of locations that will be archived (surviving slots and their children excluded, hand-made children of removed nodes included).
- [x] Duplicated generated locations are plain locations; falsy `active` and Regenerate both run the check; warehouse change refused once a row has locations.

**Verification:** done 23 Oct — 6 new tests (5 in `test_location_sync.py`, 1 in `test_location_lock.py`); full run `0 failed, 0 error(s) of 53 tests`.
**Dependencies:** T3b
**Files:** `models/warehouse_rack_row.py`, `models/stock_location.py`, `tests/test_location_sync.py`, `tests/test_location_lock.py`
**Scope:** S

### Checkpoint A
- [ ] `TEST` green, nothing skipped
- [ ] Manual: create P05 in the UI → receipt into `P05-03-2-A` → quant visible in Inventory ▸ Reporting ▸ Stock
- [ ] **Review with Nitin + teammate** (read `docs/notes.md` sections T0–T3)

---

## Phase 2 — 3D viewer

### T4: Spike — vendored Three.js inside an OWL client action
**Description:** Riskiest piece first. A client action under *Inventory ▸ Warehouse 3D ▸ 3D view* that lazy-loads vendored Three.js r128 + OrbitControls and renders a floor and one box with orbit controls.

**Acceptance criteria:**
- [x] `static/lib/three/{three.min.js,OrbitControls.js,LICENSE}` vendored from the npm `three@0.128.0` package; no network requests to any CDN.
- [x] Three.js is loaded only when the action opens (`loadJS` in `onWillStart`), not in `web.assets_backend`.
- [x] Leaving the action disposes renderer, controls, geometries and the resize observer; opening it again works; no console errors. Missing WebGL shows the prototype's fallback message *(implemented, not covered by a test — headless Chrome always has WebGL)*.

**Verification:** done 23 Oct — `tests/test_view3d.py`: bundle test (Three.js not in `web.assets_backend`) + tour `static/tests/tours/view3d_tour.js`: open → real WebGL context → leave to Rack Rows → canvas gone → reopen → WebGL again. Full run `0 failed, 0 error(s) of 55 tests`. Chrome log: only SwiftShader "GPU stall" performance notices, no errors.
**Dependencies:** T0
**Files:** `static/lib/three/*`, `static/src/view3d/view3d_action.{js,xml,scss}`, `views/menus.xml`, `__manifest__.py`, `static/tests/tours/view3d_tour.js`, `tests/test_view3d.py`
**Scope:** M

### T5: Layout areas + building size
**Description:** Replace the prototype's hard-coded zones/docks/building with data.

**Acceptance criteria:**
- [x] `warehouse.layout.area` (name, kind area/dock, x, y, width, depth, warehouse_id) with list view under the Warehouse 3D config menu.
- [x] `stock.warehouse` gains `wh3d_length`, `wh3d_width`, `wh3d_height` (defaults 60/40/10), shown in a "3D Layout" group on the warehouse form (above the tabs, which are often hidden).
- [x] Areas must have positive size and lie inside the building.

**Verification:** done 23 Oct — `tests/test_layout_area.py` 9 tests (defaults, create area/dock, positive size, outside building ×3, touching walls OK, shrinking building refused, size > 0, form, access). Full run `0 failed, 0 error(s) of 63 tests`.
**Dependencies:** T1
**Files:** `models/warehouse_layout_area.py`, `models/stock_warehouse.py`, `views/warehouse_layout_area_views.xml`, `views/stock_warehouse_views.xml`, `security/ir.model.access.csv`, `tests/test_layout_area.py`
**Scope:** M

### T6: Scene RPC
**Description:** One call returns everything the viewer draws (decision 7).

**Acceptance criteria:**
- [x] `stock.warehouse.wh3d_get_scene()` returns `{building, areas[], rows[], slots[]}`; each slot has `location_id`, `code`, `row_id`, `bay`, `level`, `position`, `capacity_m3` (slot width × depth × level height; pallet slot width = bay_width ÷ slots_per_level), and `stock` (`null` or `{product_id, name, default_code, qty, uom, used_m3, fill, mixed}`; `used_m3` = Σ L×W×H×qty over the slot's quants, `fill` = used ÷ capacity, both `null` if any product lacks dimensions; mixed slots name the largest quant and set `mixed: true`).
- [x] `wh3d_get_slots(location_ids)` returns the same slot shape for a subset.
- [x] Query count does not grow with the number of slots (fixed number of `search_read`/`read_group` calls).

**Verification:** done 23 Oct — `tests/test_scene_data.py` 11 tests (shape, indices/capacity, empty, fill math, mixed, no-dimensions → null, archived excluded, `wh3d_get_slots` subset, same query count for 1 vs 3 rows, stock-user access, product form). Full run `0 failed, 0 error(s) of 74 tests`.
**Dependencies:** T3, T5, product dimension fields (moved from T13 into this task: `product.template` `wh3d_length/width/height` + form view)
**Files:** `models/stock_warehouse.py`, `models/product_template.py`, `views/product_template_views.xml`, `tests/test_scene_data.py`
**Scope:** M

### T7: Port prototype geometry; render racks from records
**Description:** Move the prototype's scene-building into `layout.js` (pure functions: records → matrices, hit boxes) and render it from the scene RPC.

**Acceptance criteria:**
- [x] `layout.js` has no Three.js or DOM dependency at all (returns plain number boxes); given P05 it produces 16 uprights, 8 beams, 70 hit boxes (prototype numbers).
- [x] Floor, grid, curbs, areas, docks, racks, shelves and labels render from RPC data, with the 3D/Top camera toggle and Labels toggle from the prototype. *(Not ported: the prototype's hard-coded section labels — "Pallet racking", "Main cross aisle", "Shelving pick zone", "Outbound docks". They aren't data; can be added as layout areas later.)*
- [x] Visual parity with the prototype for the same layout (checked side by side, screenshot in `docs/`).

**Verification:** done 23 Oct — Hoot `static/tests/layout.test.js` 10 tests (run by `tests/test_js.py`; a deliberately wrong number fails the run). Tour: row + area + dock present → scene loads 1 row with WebGL, Top view and Labels toggles work, leave and reopen. Screenshots `docs/screenshots/t7-odoo-3d-view.png` vs `t7-prototype.png` (via `./run_tests.sh wh3d_screenshot`). Full run `0 failed, 0 error(s) of 75 tests`.
**Dependencies:** T4, T6
**Files:** `static/src/view3d/layout.js`, `static/src/view3d/scene.js`, `static/src/view3d/view3d_action.{js,xml}`, `static/tests/layout.test.js`, `tests/test_js.py`, `tests/test_view3d.py`, `static/tests/tours/view3d_tour.js`
**Scope:** M

### T8: Stock, selection panel, find, capacity, open in Inventory
**Description:** The prototype's right-hand panel with real data.

**Acceptance criteria:**
- [x] Each stocked slot draws **one** load box: slot footprint, height = `used_m3` ÷ footprint capped at level height (fixed half-height when `fill` is null). Neutral grey by default; toolbar toggle "Colour by occupancy" → green < 50 %, amber 50–90 %, red > 90 %, striped grey when dimensions are missing. Stock toggle hides boxes.
- [x] Click a slot → panel shows code, full path, level/height, contents, fill % (or "no dimensions"), or "Empty"; "Open in Inventory" opens the quants of that location. Find box accepts a code, flies the camera there, shows the prototype's error text on unknown codes.
- [x] Capacity card (totals/used per kind, average fill) and occupancy legend (slot count per band + "no dimensions") computed from the payload.

**Verification:** done 23 Oct — Hoot `static/tests/occupancy.test.js` 10 tests (bands at 49.9/50/90/90.1 %, null → no-dims, box height and cap, shelf deck, code normalisation, capacity, legend) + `openSide`/`aisleClearance` 5 tests (25 Hoot total). Tour `warehouse_3d_stock`: capacity card, unknown-code error, find in lower case → panel (code, path, product, 49 %), occupancy on → legend, click sky clears, click centre picks the found slot, Open in Inventory → quant list. Screenshot `docs/screenshots/t8-find-slot.png`. Full run `0 failed, 0 error(s) of 76 tests`.
*Changed from the prototype:* Find now looks at the slot from its aisle (the prototype's angle let the neighbouring slot block it — caught by the tour).
**Dependencies:** T7
**Files:** `static/src/view3d/occupancy.js`, `static/src/view3d/layout.js`, `static/src/view3d/scene.js`, `static/src/view3d/view3d_action.{js,xml,scss}`, `models/stock_warehouse.py`, `static/tests/occupancy.test.js`, `static/tests/layout.test.js`, `static/tests/tours/view3d_tour.js`, `tests/test_view3d.py`
**Scope:** M

### T9: Live updates over the bus
**Description:** Stock moves in Inventory appear in an open 3D view without reload (decisions 7–8).

**Acceptance criteria:**
- [x] Any quant create/write/unlink on a slot location sends **one** `warehouse_3d/stock` message per transaction to `stock.group_stock_user`, carrying the affected location ids; non-slot locations send nothing.
- [x] The client refetches only those slots and updates instance colours/visibility and the open panel.
- [x] Unsubscribes on unmount.

**Verification:** done 23 Oct — `tests/test_bus.py` 4 tests (3-line receipt → exactly one message with the 3 slots, sent to the Inventory users group; receipt into WH/Stock → none; inventory adjustment → one; quant moved between slots → both). Tour `warehouse_3d_live`: 3D view open with a slot selected, an inventory adjustment is made through the normal API, and the panel, capacity and legend update without reload. Full run `0 failed, 0 error(s) of 81 tests`. Manual (Nitin): two browser tabs.
*Not covered by a test:* unsubscribe on unmount (in code; the leave/reopen tour shows no errors).
**Dependencies:** T8
**Files:** `models/stock_quant.py`, `static/src/view3d/view3d_action.{js,xml}`, `__manifest__.py`, `tests/test_bus.py`, `static/tests/tours/view3d_tour.js`, `tests/test_view3d.py`
**Scope:** S

### T9b: Live-update review fixes *(added 23 Oct after the second `/code-review`)*
**Description:** Fix review findings #1–#5, #7–#10 on the live updates (see `docs/notes.md` T9b); #6 deferred (multi-company out of scope).

**Acceptance criteria:**
- [x] `UpdateQueue`: collects before the scene loads, throttles, one fetch at a time, retries failed fetches; slots no longer returned are shown empty.
- [x] Reservations send no bus message; the real Physical Inventory ▸ Apply path is tested; tour counts are exact; one shared test helper.

**Verification:** done 23 Oct — Hoot `static/tests/live.test.js` 5 tests + `mergeSlotUpdates` 1 test (31 Hoot total); mutation check: switching `live.js` back to a restarting debounce fails the throttle test. `tests/test_bus.py` +2 (reservations silent; real Apply). Full run `0 failed, 0 error(s) of 83 tests`.
*Not covered by a test:* the subscribe-before-load window (#2) — fixed by structure (subscribe in `setup()`), not reproduced in a browser.
**Dependencies:** T9
**Files:** `static/src/view3d/live.js`, `static/src/view3d/view3d_action.js`, `static/src/view3d/occupancy.js`, `models/stock_quant.py`, `tests/common.py`, `tests/test_bus.py`, `tests/test_view3d.py`, `static/tests/live.test.js`, `static/tests/occupancy.test.js`, `static/tests/tours/view3d_tour.js`
**Scope:** M

### T9c: Walk mode — first-person walk through the aisles *(added 23 Oct, interview)*
**Description:** A **Walk** button in the 3D view toolbar switches to a first-person camera at eye height so you can walk the aisles by hand (plan decision 11b). Mainly for the demo; also a floor-level look at where a slot is.

**Acceptance criteria:**
- [x] **Start:** with a slot selected, you start in its aisle facing it (side chosen with `openSide`, distance limited by `aisleClearance`); with nothing selected, at the first dock door (or the middle of the front wall if there are no docks) facing into the building. Eye height 1.7 m.
- [x] **Controls:** W/A/S/D or arrow keys walk (~1.4 m/s, Shift ×2.5); mouse drag looks around, drag-the-view style (drag right → turn left, drag up → look down; flipped 23 Oct after manual check), pitch limited to ±80°; no pointer lock. Keys are ignored while typing in an input (e.g. Find). Esc or the Walk button returns to the orbit view where it was.
- [x] **Collisions:** the walker (0.3 m radius) can't enter a rack footprint or leave the building; moving into a rack at an angle slides along it. Floor areas and docks are walkable.
- [x] Clicking a slot, Find, the side panel and live stock updates keep working in walk mode.

**Verification:**
- [x] Hoot `static/tests/walk.test.js` (16 tests incl. look direction; 57 Hoot total): start pose in front of a slot (both aisle sides, back-to-back pair), start at first dock / no docks, key → movement direction for a given heading, Shift speed, can't enter a rack, slides along a rack face, stays inside walls, corner case between two racks.
- [x] Tour `warehouse_3d_walk`: Find P05-03-2-A → Walk → view in walk mode at eye height (marker attribute) → Esc → back to orbit; enter/leave twice with no console errors; holding W for 0.5 s moves the walker towards the rack and it stops short of it.
- [ ] Manual (Nitin): from P05-03-2-A walk the aisle, turn into the main cross aisle and reach Shipping without passing through anything.
- [x] Screenshot `docs/screenshots/t9c-walk-mode.png` (opt-in `./run_tests.sh wh3d_screenshot`).
- [x] Full run `0 failed, 0 error(s) of 98 tests` (23 Oct).
*Not covered by a test:* Shift and mouse-look in a real browser (their maths is unit-tested); look-drag direction feel — check manually.

**Dependencies:** T8, T9b
**Files:** `static/src/view3d/walk.js` (new, pure), `static/src/view3d/scene.js`, `static/src/view3d/view3d_action.{js,xml,scss}`, `static/tests/walk.test.js`, `static/tests/tours/view3d_tour.js`, `tests/test_view3d.py`
**Scope:** M

### Checkpoint B
- [ ] `TEST` green, nothing skipped
- [ ] Manual: 3D view looks like the prototype with real rows; receipt in tab A appears live in tab B
- [ ] **Review with Nitin + teammate** (notes T4–T9: OWL lifecycle, assets, client actions, RPC, bus)

---

## Phase 3 — 2D editor

### T10: Server-side layout constraints
**Description:** The rules the editor must respect, enforced where they can't be bypassed.

**Acceptance criteria:**
- [x] A rack row's footprint (`x..x+depth`, `y..y+bays·bay_width`) must lie inside the building.
- [x] Two active rows in the same warehouse must not overlap (touching edges allowed — back-to-back doubles have a 0.2 m gap anyway).
- [x] Error message names both row codes.

**Verification:** done 23 Oct — `tests/test_rack_row.py::TestRackRowLayout` 12 tests (outside ×2, touching walls, growing through a wall, overlap names both, back-to-back OK, different stretch OK, moving onto another, archived ignored, re-activating onto a newer row, other warehouse OK, building can't shrink under a row, all 31 template rows valid). Full run `0 failed, 0 error(s) of 95 tests`.
*Also:* the building-size check now covers rows too.
**Dependencies:** T5
**Files:** `models/warehouse_rack_row.py`, `models/warehouse_layout_area.py`, `models/stock_warehouse.py`, `tests/test_rack_row.py`, `tests/common.py`, `tests/test_view3d.py`
**Scope:** XS

### T11: Editor client action — draw and select
**Description:** *Inventory ▸ Warehouse 3D ▸ Layout editor*: top-down SVG of building, grid (1 m minor / 5 m major), areas, docks and rack rows (from the T6 RPC). Click a row → side panel shows its fields read-only; "View in 3D" opens the 3D view focused on it.

**Acceptance criteria:**
- [x] Scale fits the building to the viewport; zoom with wheel, pan with drag on empty floor.
- [x] Selected row highlighted; keyboard: rows are focusable, so Tab moves between them (and focusing selects), Esc deselects. *(Tab isn't captured, so keyboard users can still leave the plan.)*

**Verification:** done 23 Oct — Hoot `static/tests/editor_geometry.test.js` 10 tests (fit ×2, round-trip, zoom keeps point, zoom clamp, pan, row/area rectangles, grid, middle slot; 41 Hoot total). Tour `warehouse_3d_editor`: area drawn, click P05 → panel + highlight, Esc clears, focus selects, View in 3D → 3D view selects P05-04-1-A. Python: `wh3d_get_layout` test. Screenshot `docs/screenshots/t11-layout-editor.png` (opt-in `./run_tests.sh wh3d_screenshot`). Full run `0 failed, 0 error(s) of 97 tests`.
*Not covered by a test:* mouse-wheel zoom and drag-to-pan in the browser (their maths is unit-tested).
**Dependencies:** T6
**Files:** `static/src/editor/editor_action.{js,xml,scss}`, `static/src/editor/geometry.js`, `views/view3d_actions.xml`, `views/menus.xml`, `models/stock_warehouse.py`, `static/src/view3d/view3d_action.js`, `static/tests/editor_geometry.test.js`, `static/tests/tours/view3d_tour.js`, `tests/test_view3d.py`, `tests/test_scene_data.py`
**Scope:** M

### T12: Editor — move, edit, add, delete, save
**Description:** Make the editor edit.

**Acceptance criteria:**
- [x] Drag a row (0.1 m snap); edit fields in the panel; "Add row" (pallet/shelf defaults from the template) at a free spot; delete with confirmation. Overlap/out-of-bounds shown red immediately (client mirror of T10).
- [x] Save writes all changes in one ORM call; server errors (T10, T3 stock guard) shown in a notification and nothing is half-saved. Unsaved-changes warning on leaving.
- [x] After save, locations reflect the changes (via T3) and the 3D view shows the new layout.

**Verification:** done 23 Oct — `tests/test_layout_save.py` 10 tests (move+edit, create with ids and locations, default zones, delete, swap allowed, overlap refuses all, stock guard refuses all, field whitelist, other warehouse refused, stock user refused). Hoot `static/tests/layout_edit.test.js` 11 tests (68 Hoot total); mutation check: counting touching rows as overlapping fails the back-to-back test. Tour `warehouse_3d_editor_edit` (44 steps): drag P05 0.5 m → save → stays; overlap shown red + Save disabled → Discard; add pallet row P07 → save → 70 slot locations; shrink P05 under stock → "Layout not saved … P05-07-1-A", edit kept; leaving asks, Cancel stays; reopen shows saved state. Screenshot `docs/screenshots/t12-layout-editor-editing.png`. Full run `0 failed, 0 error(s) of 109 tests`.
*Not covered by a test:* the browser's own tab-close warning (`beforeunload` can't be driven from a tour); arrow-key nudging (same `snap` maths as dragging).
**Dependencies:** T11, T10, T3
**Files:** `static/src/editor/editor_action.{js,xml,scss}`, `static/src/editor/layout_edit.js`, `models/warehouse_rack_row.py`, `tests/test_layout_save.py`, `static/tests/layout_edit.test.js`, `static/tests/tours/view3d_tour.js`, `tests/test_view3d.py`
**Scope:** M

### T12b: CodeRabbit review fixes *(added 24 Oct after `/coderabbit:code-review`)*
**Description:** Fix the 4 minor findings of the CodeRabbit review of all work since the first commit (see `docs/notes.md` T12b).

**Acceptance criteria:**
- [x] `run_tests.sh` fails when Odoo exits non-zero or no tests ran (misspelt tag).
- [x] Walk mode: key releases always count, presses while typing don't, focus loss stops walking; Shift alone still hurries.
- [x] Storage Locations setting switched on at install only (`noupdate`); zone dropdown offers Internal locations only.

**Verification:** done 24 Oct — red first for all four: `./run_tests.sh /warehouse_3d:TestTypo` printed OK (now exits 1 with "no tests ran"); 7 new Hoot key tests; walk tour step (hold W, window blur → walker stops); 2 Python tests (module update keeps setting off; zone domain). Full run `0 failed, 0 error(s) of 111 tests`, 75 Hoot. CodeRabbit re-run on the fixes: 0 findings.
**Dependencies:** T12
**Files:** `run_tests.sh`, `data/res_groups.xml`, `models/warehouse_rack_row.py`, `static/src/view3d/walk.js`, `static/src/view3d/scene.js`, `static/tests/walk.test.js`, `static/tests/tours/view3d_tour.js`, `tests/test_rack_row.py`
**Scope:** S

### Checkpoint C
- [ ] `TEST` green, nothing skipped
- [ ] Manual: lay out a small warehouse from scratch in the editor, see it in 3D, receive stock into it
- [ ] **Review with Nitin + teammate**

---

## Phase 4 — Template warehouse + end-to-end

### T13: Template catalogue
**Description:** Demo data for the inventory side of the template (handoff "Template data to load").

**Acceptance criteria:**
- [x] `product.template` gains `wh3d_abc_class` (A/B/C), shown on the product form (dimension fields already exist from T6). Not used for colour.
- [x] Demo XML: package types Pallet/Carton/Tote (with dimensions, max weight); storage categories "Pallet rack – bulk" (1 Pallet package per slot, mixing: empty only), "Shelving – small parts" (max weight, mixing allowed), "Golden zone"; ~120 products across pallet/shelf categories, extending the prototype's catalogue, **every one** with L×W×H, weight, volume and ABC class (≈20% A).
- [x] Putaway rules: bulk category → `WH/Stock/PR` closest; small-parts category → `WH/Stock/SH` closest. *(The PR/SH zone locations moved here from T14, since the rules need them.)*

**Verification:** done 24 Oct — `tests/test_template.py` 10 tests (120 products split bulk/small parts, every product with dims/weight/volume/class, unique codes, A share 20 %, package types, storage categories and capacity, zones, putaway rules, standard putaway fills empty slots in order, ABC on the form). Full run `0 failed, 0 error(s) of 121 tests`. `run_tests.sh` now also fails when demo data doesn't install.
**Dependencies:** T2
**Files:** `models/product_template.py`, `views/product_template_views.xml`, `demo/catalogue.xml`, `demo/product.template.csv`, `__manifest__.py`, `run_tests.sh`, `tests/test_template.py`
**Scope:** M

### T14: Template layout + generated locations + opening stock
**Description:** The 60×40 m DC from the handoff as demo data, filled to ~65%. *(Decided 24 Oct: in its own warehouse "Warehaven DC" (WHV), not WH, so the template and anything tried in WH — including the tests — never collide; the views open the first warehouse with rack rows.)*

**Acceptance criteria:**
- [x] Demo XML: building 60×40×10, 5 areas + 6 docks (PR/SH zones already in T13), 31 rack rows at the handoff x-positions; generation yields **980 pallet + 1,360 shelf = 2,340** slot locations.
- [x] `<function>` fills opening stock with a fixed seed: 60–70% of slots occupied per kind, pallet slots hold one bulk product, shelf bins small parts, A-class over-represented; quantities chosen so stocked slots spread across all three fill bands (each band ≥ 15 % of stocked slots); reinstalling gives the same result.
- [x] Install with demo completes in < 3 min.

**Verification:** `tests/test_template.py` — slot counts, occupancy band, fill-band spread, determinism (two runs of the filler on fresh rows produce identical quants), no row overlaps. Manual: 3D view of the template vs the prototype screenshot.
**Dependencies:** T13, T3, T10
**Files:** `demo/catalogue.xml`, `demo/layout.xml`, `models/stock_warehouse.py`, `static/src/view3d/view3d_action.js`, `static/src/editor/editor_action.js`, `tests/test_template.py`, tests scoped to their warehouse (`test_bus`, `test_layout_save`, `test_location_generator`, `test_location_lock`, `test_scene_data`, `test_view3d`, tours)
**Scope:** M

### T15: End-to-end Inventory tour + README
**Description:** Prove the module "plays nicely with Inventory" in one scripted flow, and leave the team a guide.

**Acceptance criteria:**
- [x] Tour: receipt of a bulk product as a pallet → validate → putaway puts it in an empty pallet slot → 3D view shows it there; delivery from that slot → it disappears.
- [x] `warehouse_3D/README.md`: what it is, install, run, test, architecture diagram, where each concept lives, known limits (no rotation, standard putaway only, uninstall leaves locations).
- [x] Uninstall on a copy DB succeeds and Inventory still opens.

**Verification:** done 24 Oct — `tests/test_inventory_flow.py`: Python flow test (receipt → putaway into the first empty pallet slot → scene data + bus → delivery → empty) and tour `warehouse_3d_inventory_flow` (same, live in the 3D view). Uninstall checked on throwaway databases: without demo data clean; with demo data Odoo logs an error removing the template warehouse and leaves it (documented). `run_tests.py` replaces the bash runner (Linux + Windows); misspelt tag / broken test / missing config / protected db name all exit 1. README with Fedora (tested) and Windows (untested) setup. Full run via `run_tests.py`: `0 failed, 0 error(s) of 134 tests`, 75 Hoot.
**Dependencies:** T9, T14
**Files:** `tests/test_inventory_flow.py`, `static/tests/tours/view3d_tour.js`, `run_tests.py`, `run_tests.sh`, `README.md`
**Scope:** S

### T15b: CodeRabbit fixes for T13–T15
- [x] Demo-dependent test classes skip with a reason on databases without demo data
- [x] `run_tests.py` only drops databases whose names start with `wh3d_test`

**Verification:** done 24 Oct. Without demo data: before `1 failed, 3 error(s) of 112`, after `0 failed, 0 error(s) of 112` (4 classes skipped). With demo: `0 failed, 0 error(s) of 134`, 75 Hoot. Bad db names (`warehaven`, `postgres`, `template1`, `wh3d_test;drop`, `wh3d_tes`) exit 1 before connecting.

### Checkpoint D — Complete
- [x] All success criteria in `docs/plan.md` met; `TEST` green, nothing skipped *(24 Oct: fresh demo DB opens Warehaven DC in 3D — T14; receipts/deliveries update it live — T9, T15; editing a row regenerates its locations — T3, T12; 134 tests + 75 Hoot green; every task explained in notes.md)*
- [ ] Demo walkthrough rehearsed with Nitin + teammate
- [ ] Ready for the next plan: custom putaway strategies + experiment
