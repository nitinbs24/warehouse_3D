# Implementation Plan: Warehaven `warehouse_3d` (Odoo 19 addon)

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
- [x] **Checkpoint A** — rows create correct locations; Inventory can receive into them

### Phase 2 — 3D viewer
- [x] T4: Spike — vendored Three.js rendering inside an OWL client action
- [x] T5: Layout areas + building size
- [x] T6: Scene RPC
- [x] T7: Port prototype geometry; render racks from records
- [x] T8: Stock, selection panel, find, capacity cards, open in Inventory
- [x] T9: Live updates over the bus
- [x] T9b: Live-update review fixes
- [x] T9c: Walk mode — first-person walk through the aisles *(added 23 Oct)*
- [x] **Checkpoint B** — 3D view matches the prototype with real data, updates live

### Phase 3 — 2D editor
- [x] T10: Server-side layout constraints (bounds, overlap)
- [x] T11: Editor client action — draw and select
- [x] T12: Editor — move, edit, add, delete, save
- [x] T12b: CodeRabbit review fixes
- [x] **Checkpoint C** — design a layout in the editor, see it in 3D, locations follow

### Phase 4 — Template warehouse + end-to-end
- [x] T13: Template catalogue: package types, storage categories, products, putaway rules
- [x] T14: Template layout + generated locations + opening stock (own warehouse "Warehaven DC")
- [x] T15: End-to-end Inventory tour, README for the team (Fedora + Windows), cross-platform test runner
- [x] **Checkpoint D (complete)** — success criteria above all met

---

# Plan 2: Smart putaway, evaluation, floor-plan import (18 Nov 2026)

Status: **awaiting approval**. Tasks T24–T41 in `docs/todo.md` (Phases 7–10).

## Confirmed intent (interview, 13–18 Nov 2026)
- **Outcome:** (1) a smart putaway engine that replaces Odoo's slot choice: hard rules filter slots, AHP-weighted TOPSIS ranks the rest, the top 3 are shown with reasons, and manual moves that break a hard rule are blocked; (2) its evaluation against standard Odoo; (3) 2D floor-plan import (DXF, then images via classical CV and a locally trained detector) into a reviewable draft in the Layout Editor; (4) the mentor's feature list afterwards.
- **Why:** final-year project; the mentor asked for real-warehouse concerns (cold storage, hazardous, fragile, quarantine) and floor-plan → 3D.
- **Success:** zero hard-rule violations; better pick travel, space use and ergonomics than standard Odoo on the template warehouse at 30/60/85 % fill; floor-plan detector measured with precision/recall/mAP and correction count.
- **Out of scope:** ML/RL putaway, re-slotting stock already stored, worker/forklift tracking, DWG, editable AHP weights (later), TRGS 510 neighbour-compatibility matrix (later).
- Research basis: `docs/survey.md`, `docs/review/review.md`, `docs/review/ahp-questionnaire.md`. Project summary: `docs/intent/project-details.md`.

## Verified in the Odoo 19 source
| Fact | Where | Consequence |
|---|---|---|
| Rules are evaluated one by one through `stock.putaway.rule._get_putaway_location(product, quantity, package, packaging, qty_by_location)`; the first non-empty result wins | `stock/models/product_strategy.py:133` | Add `sublocation` value `wh3d_smart` (`selection_add`), override `_get_putaway_location`: smart rules run our engine, others call `super()` |
| `qty_by_location` (this product's on-hand + incoming per location) is only computed when the candidate locations have a storage category | `stock/models/stock_location.py:337` | Every generated slot keeps a storage category (already true for template rows) |
| No rule returns a location → the move's own destination (e.g. `WH/Stock`) is kept | `stock_location.py:373` | "No allowed slot" lands at `WH/Stock`, not in a slot; the engine logs it and the experiment counts it as a failed placement |
| Putaway is called without the lot | `stock_location.py:297` signature | "Don't mix expiry lots" is not enforceable at putaway; deferred (enforce at move-line validation later) |
| Package putaway passes products in `context['products']` with an empty product | `stock_move_line.py:272` | Engine handles a product set |
| `_check_can_be_used` already checks weight, capacity and mixing | `stock_location.py:418` | Reused as one hard rule |
| `_compute_storage_category` clears the rule's category unless `closest_location` | `product_strategy.py:75` | Smart rules don't need one |

## Architecture decisions (Plan 2)
| Decision | Why |
|---|---|
| Engine = pure Python functions (`putaway/rules.py`, `putaway/score.py`, `putaway/aisles.py`) + thin Odoo glue on the putaway rule | Unit-testable without the ORM; the same code runs in the experiment |
| Zone attributes live on **rack rows** (temperature range, approved hazard classes, purpose, inspection status); slots inherit them | Areas have no Inventory locations; one setting per row |
| Temperature as a °C range with presets, not labels | Food and pharma bands differ (survey A8.1) |
| AHP weights are constants computed by `docs/review/ahp.py`; TOPSIS and weighted sum both implemented | Fixed for now; the experiment compares them |
| Distances on an **aisle graph** built from the layout (Dijkstra), cached per warehouse and rebuilt when the layout is saved | Racks are obstacles; fast at receipt time |
| Experiment and ML pipeline live **outside** the add-on: `warehouse_3D/experiments/`, `warehouse_3D/ml/` | The add-on stays light; only the ONNX model file ships |
| Floor-plan import produces an **unsaved draft in the Layout Editor** | Every importer has one output format; the user reviews before Save (human-in-the-loop) |
| New Python deps only in Phase 9 (`ezdxf`, `opencv-python-headless`, `onnxruntime`, `pytesseract` + Tesseract), declared in `external_dependencies` | Phase 7–8 need nothing new |

### Dependency graph (Plan 2)
```
T24 zone/product fields ─┬─ T25 hard rules ─┐
                         └─ T26 aisle graph ─┴─ T27 scoring + smart rule ─┬─ T28 block manual moves
                                                                          ├─ T29 "why this slot" top 3
                                                                          └─ T30 template special zones ── Checkpoint E
T27+T30 ── T31 experiment harness ── T32 metrics ── T33 runs + results ── Checkpoint F
T34 background + scale ── T35 draft import ─┬─ T36 DXF
                                            ├─ T37 classical CV ── T38 synthetic generator ── T39 train (Colab) ── T40 ONNX + OCR in Odoo
                                            └────────────────────────────────────────────────── T41 wrap-up ── Checkpoint G
Phase 10 (mentor's list) after Checkpoint G, planned in detail then.
```

## Task list (details in `docs/todo.md`)
### Phase 7: Smart putaway
- [x] T24: Special-goods fields on products and rack rows (form, editor side panel, 3D tooltip)
- [ ] T25: Hard-rule filter
- [ ] T26: Aisle graph and dock distances
- [ ] T27: Criteria, AHP–TOPSIS and weighted-sum ranking; "Smart" putaway option
- [ ] T28: Block manual moves that break a hard rule
- [ ] T29: "Why this slot?": top 3 with reasons, pick another
- [ ] T30: Template warehouse: cold room, hazardous area, quarantine, special products; README
- [ ] **Checkpoint E**
### Phase 8: Evaluation
- [ ] T31: Experiment harness: seeded receipts and pick lists on a throwaway database
- [ ] T32: Metrics: travel (single-command, S-shape, largest gap), space, ergonomics, violations, failures, decision time
- [ ] T33: Runs (5 variants × 3 fill levels × seeds, ±50 % weight sensitivity) and `docs/results.md`
- [ ] **Checkpoint F**
### Phase 9: Floor-plan import
- [ ] T34: Background plan image and two-click scale in the editor
- [ ] T35: Draft import into the editor (common output of all importers)
- [ ] T36: DXF importer
- [ ] T37: Classical-CV importer (OpenCV)
- [ ] T38: Synthetic warehouse floor-plan generator (COCO labels)
- [ ] T39: Train and evaluate YOLOX-S on Colab; export ONNX
- [ ] T40: ONNX detector + OCR in Odoo, CV fallback
- [ ] T41: Wrap-up: README, notes, `docs/results-floorplan.md`
- [ ] **Checkpoint G**
### Phase 10: Mentor's feature list (planned after Checkpoint G)

## Risks
| Risk | Mitigation |
|---|---|
| Engine too slow on 2,340 slots per move line | Batch-read quants once per call; cache the aisle graph; T27 asserts < 1 s per line on the template |
| Hard-rule data missing on old rows/products | Empty = no requirement / not approved; hazardous or temperature-controlled products never go to a row without matching settings |
| YOLOX licence or tooling problems | RT-DETR (Apache-2.0) as the fallback |
| Synthetic plans don't transfer to real ones | Real plans test only; classical CV and manual tracing stay available |
| Mentor data (AHP answers, pick data, real plans) late | Provisional weights, synthetic picks, synthetic test plans; swap in later |
