# Implementation Plan: Warehaven `warehouse_3d` (Odoo 19 addon)

Status: **DRAFT — awaiting approval. No code is written until Nitin approves.**
Source: `docs/CLAUDE.md` (handoff) + `docs/warehaven-3d-prototype.html`. Task checklist: `docs/todo.md`.

## Overview

An Odoo 19 Community addon, `warehouse_3d`, that depends on `stock` and plugs into Inventory:
you lay out rack rows in a 2D editor, the module generates real `stock.location` records for every
slot, and a 3D view (OWL + vendored Three.js, ported from the prototype) shows those slots with live
`stock.quant` stock. Ships the template distribution center (31 rack faces, 2,340 slots, products,
storage categories, opening stock) as demo data. Standard Odoo putaway only.

## Confirmed intent (interview, 23 Oct 2026)

- **Outcome:** working addon: rack-row model → generated location tree → 3D viewer with live stock → 2D editor → template data.
- **Who:** Nitin + teammate review and learn from each task; mentor sees the demo. Claude writes all code.
- **Success:** fresh Odoo 19 DB + `-i warehouse_3d --with-demo` shows the template warehouse in 3D; receipts/deliveries in Inventory update the view live; editing a row regenerates its locations; all Python and JS tests green.
- **Constraint:** Odoo 19 Community, no CDN, no new Python packages, standard putaway. Odoo 18 setup and `odoo.conf` stay untouched.
- **Out of scope:** custom putaway (3D-BPP/FFD, SLAP/ABC) and the research experiment (a later plan), per-carton packed rendering (that is the 3D-BPP problem — later plan), pick/delivery history (the mentor will supply real data), dark theme, tutorials 1/2/4 of the handoff build order (your own learning), multi-warehouse polish, rotated rack rows, the dropped Kafka/FastAPI/React design.
- **No deadline.** Local git only (no shared remote).
- **Walk mode (added 23 Oct, interview):** a first-person "walk the aisles" view in the 3D view, mainly for the mentor demo, partly so someone can see a slot from floor level. Steered by hand; no guided route; can't walk through racks. Starts in front of the selected slot, else at the first dock door. Out of scope for it: guided routes / "walk me to slot X", a start-location prompt, touch/phone controls, jumping, doors, people, VR, recording a walk.

## What I verified in the Odoo 19 source (so the plan rests on facts)

| Fact | Where | Consequence |
|---|---|---|
| `_get_putaway_strategy(product, quantity, package, packaging, additional_qty)` exists | `addons/stock/models/stock_location.py:297` | Later optimisation plan can override it; nothing needed now. |
| Rule ranking is **package type first**, then product, then same category, then any category (sorted desc) | same file, ~line 322 | Correction to the handoff ("product beats category" is true, but package-type rules beat both). Template putaway rules are designed with this in mind. |
| "Closest location" searches `child_internal_location_ids` = all `internal` descendants via `child_of` | `stock_location.py:175` | Leaf slots are found through any depth of tree. |
| `complete_name` restarts at every `view` location | `stock_location.py:127` | All generated nodes are `internal` (see decision 4). |
| `stock.location` already has `storage_category_id`, `_parent_store`, stored `complete_name` | `stock_location.py:17,30,86` | Paths like `WH/Stock/PR/P05/P05-03/P05-03-2/P05-03-2-A` come for free from naming each node. |
| Products have no L×W×H fields; `stock.package.type` does (`packaging_length` …) | `product_template.py`, `stock_package_type.py:24` | Add `wh3d_length/width/height` on `product.template`. |
| Bus: `bus.bus._sendone(target, type, payload)`; websocket auto-subscribes each user to `broadcast`, their partner, and **all their groups** | `bus/models/bus.py:111`, `bus/models/ir_websocket.py:15` | Send stock updates to the `stock.group_stock_user` group record — no custom channel plumbing, no `ir.websocket` override. Client uses `bus_service.subscribe(type, cb)`. |
| Lazy JS loading via `loadJS` / `loadBundle` in `@web/core/assets` | `web/static/src/core/assets.js` | Three.js (~600 KB) loads only when the 3D view opens, not on every backend page. |
| JS unit tests are **Hoot**, run headless through `HttpCase.browser_js('/web/tests?headless…')`; Chrome is at `/usr/bin/google-chrome` | `web/tests/test_js.py:189` | One Python test class drives our JS tests, so one command runs everything. |
| Demo data is **off by default** in Odoo 19 (`--with-demo` flag) | `odoo/tools/config.py:233` | Template warehouse = demo data; real databases stay clean. DB created with `--with-demo`. |
| Current `odoo.conf` points at **odoo18** (addons path, db_user) | `/mnt/CODE/Workspace/odoo/odoo.conf` | New `odoo19.conf` alongside it; existing file untouched. |

## Architecture decisions

1. **Module location:** `/mnt/CODE/Workspace/odoo/warehouse_3D/warehouse_3d/` (the module) next to `docs/`. `warehouse_3D/` goes on the Odoo 19 `addons_path`. `git init` in `warehouse_3D/`, one commit per task.
2. **One source of truth for the layout:** `warehouse.rack.row` (one record per rack face, fields exactly as the handoff record + `warehouse_id`, `location_id` (zone parent, e.g. `WH/Stock/PR`), `storage_category_id`). Plus a tiny `warehouse.layout.area` model (name, kind = area/dock, x, y, width, depth) and building size fields on `stock.warehouse` (`wh3d_length/width/height`) — so nothing in the scene is hard-coded like the prototype's `zones`/`docks` arrays.
3. **Codes are made only in Python.** Each generated slot location stores `wh3d_rack_row_id`, `wh3d_bay`, `wh3d_level`, `wh3d_position`. The client receives those indices and computes geometry from them — it never re-derives codes, so Python and JS can't disagree.
4. **Location tree:** `<zone>/<row>/<row-bay>/<row-bay-level>/<slot>` for pallet (slot = `P05-03-2-A`); `<zone>/<row>/<row-bay>/<slot>` for shelf (slot = `S04-10-3`), matching the prototype paths. All nodes (zone, row, bay, level, slot) are `usage='internal'`; only slots get the row's storage category. *Changed 23 Oct:* the original plan made intermediates `view`, but Odoo 19 restarts `complete_name` at every `view` location (`stock_location.py:127`), which would turn `WH/Stock/PR/P05/…/P05-03-2-A` into `P05-03-2/P05-03-2-A`. Found during Nitin's T1 manual check. T2 tests the full path and that putaway lands in slots, never in bay/level nodes.
5. **Regeneration is non-destructive (data-loss guard).** On row edit: rename codes in place; create new slots on growth; on shrink or delete, **archive** empty slots and **refuse** (`UserError` naming the locations) if any removed slot holds stock. Moving x/y never touches locations.
6. **3D view = OWL client action** (`ir.actions.client`, tag `warehouse_3d.view3d`) under *Inventory ▸ Warehouse 3D*. Scene code ported from the prototype into a pure module `layout.js` (records → instance matrices / hit boxes, no DOM, unit-tested) and a thin `scene.js` (renderer, camera, picking). Three.js **r128** + `examples/js/controls/OrbitControls.js` vendored in `static/lib/three/` with its MIT licence — same version the prototype already proves, and it is a global script so no ES-module shimming inside Odoo's bundler.
6b. **What a stocked slot looks like (agreed 23 Oct):** one load box per slot, never one per carton. Footprint = the slot's footprint; height = stored volume ÷ footprint, capped at the level height — a half-full slot looks half-height. Stored volume = Σ (product L×W×H × qty) over the slot's quants. Boxes are **neutral grey by default**; a toolbar toggle **"Colour by occupancy"** colours by fill = stored ÷ slot volume in three bands: green < 50 %, amber 50–90 %, red > 90 %. A slot containing any product without dimensions is drawn striped grey, panel says "no dimensions", and it is counted separately in the legend. ABC class stays a product field for the later optimisation plan but drives no colour. Light theme only.
7. **One RPC for the scene:** `stock.warehouse.wh3d_get_scene(warehouse_id)` returns building, areas, rows, and slots (`location_id`, indices, product/qty summary). Bus message `warehouse_3d/stock` carries changed `location_id`s; the client refetches just those slots via `wh3d_get_slots(ids)`.
8. **Live updates hook:** override `stock.quant` `create`/`write`/`unlink` to collect affected slot locations (only those with `wh3d_rack_row_id`) and send one bus message per transaction (bus delivers after commit).
9. **Editor = second OWL client action** (`warehouse_3d.editor`), top-down **SVG** (not Three.js — simpler, crisp, testable): drag rows with 0.1 m snap, edit fields in a side panel, add/delete rows, Save writes through the ORM. Server constraints (inside building, no footprint overlap within a warehouse) are authoritative; the client mirrors them for instant feedback.
10. **Template warehouse as demo data:** XML for package types, storage categories, product categories, products (with dimensions + ABC class), putaway rules, areas, 31 rack rows; a `<function>` call then generates locations and seeded (deterministic) opening stock ~65% full, ABC-skewed.
11. **Tests:** Python `TransactionCase` for models/generator/RPC/bus/template; Hoot for `layout.js` and editor geometry; one `HttpCase` tour per client action (smoke: it opens, renders, the main interaction works). Written test-first per task (red → green → refactor).
11b. **Walk mode = a second camera mode, not a second scene.** Same `WarehouseScene`; OrbitControls are switched off and a small first-person controller takes over (WASD/arrows to move at ~1.4 m/s, Shift faster, mouse drag to look, no pointer lock so Esc and the panel keep working). Eye height 1.7 m. Collision is 2D on the floor plan: the walker is a 0.3 m circle that may not enter any rack footprint or leave the building, and slides along edges instead of stopping. Start pose and collision maths live in a pure, unit-tested `walk.js`, like `layout.js`.
12. **Learning notes:** each task appends a short section to `docs/notes.md` — "Odoo patterns used here" (e.g. `_inherit`, `@api.constrains`, OWL `onWillStart`/`onMounted`/`onWillUnmount`, asset bundles, XML views/actions/menus, bus). Explained once, the first time each pattern appears.

### Dependency graph

```
T0 env + skeleton
 └─ T1 rack.row model/views ──┬─ T2 generate locations ── T3 regenerate/guard
                              │                                │
 T4 3D spike (Three in OWL) ──┤                                │
                              └─ T5 areas + building fields ── T6 scene RPC ── T7 racks in 3D ── T8 stock+select+find ── T9 live bus
                                                                                     │
                                                         T10 layout constraints ── T11 editor view ── T12 editor edit/save
 T11-T12 + T9 ── T13 template catalogue/putaway ── T14 template layout+stock ── T15 end-to-end Inventory tour + README
```

T4 is the riskiest (third-party lib inside Odoo's asset pipeline + OWL lifecycle), so it runs early, right after the data model.

## Task list (details and acceptance criteria in `docs/todo.md`)

### Phase 0 — Environment
- [x] T0: Odoo 19 config, DB, git, empty module that installs, test command proven

### Phase 1 — Layout data → real Inventory locations
- [x] T1: `warehouse.rack.row` model, validation, list/form views, menu
- [x] T2: Generate the location tree from a rack row
- [x] T3: Regenerate on edit / delete without losing stock
- [x] T3b: Lock generated locations
- [x] T3c: Code-review fixes
- [ ] **Checkpoint A** — rows create correct locations; Inventory can receive into them

### Phase 2 — 3D viewer
- [x] T4: Spike — vendored Three.js rendering inside an OWL client action
- [x] T5: Layout areas + building size
- [x] T6: Scene RPC
- [x] T7: Port prototype geometry; render racks from records
- [x] T8: Stock, selection panel, find, capacity cards, open in Inventory
- [x] T9: Live updates over the bus
- [x] T9b: Live-update review fixes
- [x] T9c: Walk mode — first-person walk through the aisles *(added 23 Oct)*
- [ ] **Checkpoint B** — 3D view matches the prototype with real data, updates live

### Phase 3 — 2D editor
- [x] T10: Server-side layout constraints (bounds, overlap)
- [x] T11: Editor client action — draw and select
- [x] T12: Editor — move, edit, add, delete, save
- [x] T12b: CodeRabbit review fixes
- [ ] **Checkpoint C** — design a layout in the editor, see it in 3D, locations follow

### Phase 4 — Template warehouse + end-to-end
- [x] T13: Template catalogue: package types, storage categories, products, putaway rules
- [x] T14: Template layout + generated locations + opening stock (own warehouse "Warehaven DC")
- [x] T15: End-to-end Inventory tour, README for the team (Fedora + Windows), cross-platform test runner
- [ ] **Checkpoint D (complete)** — success criteria above all met

## Commands (set up in T0)

```bash
cd /mnt/CODE/Workspace/odoo
# run server
venv19/bin/python odoo19/odoo-bin -c odoo19.conf -d warehaven
# full module test run (Python + Hoot + tours) on a throwaway DB
venv19/bin/python odoo19/odoo-bin -c odoo19.conf -d wh3d_test --with-demo \
  -i warehouse_3d --test-tags /warehouse_3d --stop-after-init
# focused test
... --test-tags /warehouse_3d:TestLocationGenerator
```

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Three.js global script misbehaves in Odoo's asset pipeline / OWL lifecycle (leaks on navigate-away, double init) | High | T4 spike first; lazy `loadJS` (not bundled); dispose renderer/geometry/controls in `onWillUnmount`; tour navigates away and back. |
| Creating 2,340 locations is slow (`parent_store` + recursive `child_internal_location_ids` recompute per record) | Med | Batch `create` per row (one call per level of the tree); measure in T2 with a timed test on 14 pallet rows; fall back to `with_context(tracking_disable=True)` / deferred recompute if > ~30 s. |
| `websocket-client` is **not installed** in `venv19` (verified). Without it Odoo **silently skips** every browser test (`odoo/tests/common.py:1274`), so Hoot and tours would look green while not running | High | T0 installs it into `venv19` (test-only tool of Odoo's own harness, not a module dependency) — needs your OK. T0 acceptance requires a tour to visibly *run*, and every later run is checked for "skipped" in the log. |
| Quant hook fires many times per picking (one write per move line) | Med | Accumulate location ids per transaction, send once post-commit; test asserts one bus message for a multi-line receipt. |
| Removing a slot that holds stock | High (data loss) | Refuse with a clear error (T3); archive, never delete, empty slots. |
| Large scenes slow in browser | Low | InstancedMesh per part type, as the prototype already does at this size. |
| Live-update messages go to all Inventory users in every company (each browser filters by warehouse) | Low (single company here) | Accepted: multi-company is out of scope; fix would be per-company bus channels. |
| Uninstall leaves generated locations (records created by code persist; module fields drop) | Low | Documented in README; Inventory keeps working; locations can be archived manually. |

## Resolved questions (23 Oct 2026)

1. **Deadline:** none. Phases are ordered so each checkpoint is a demoable state.
2. **Pick/delivery history:** not generated — the mentor will supply real data. Products carry an ABC class and opening stock is skewed by it, nothing more.
3. **Theme:** light only (the prototype's light palette).
4. **Git:** local repo in `warehouse_3D/`, no shared remote.
5. **Box colour and size:** see decision 6b.

## Open questions

None.
