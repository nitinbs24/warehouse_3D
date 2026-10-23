# Warehaven: 3D warehouse floorplan inside Odoo

Context handoff from a claude.ai planning chat (23 Oct 2026). Read this before doing anything in this repo.

## The project
- Final-year CSE project (two-person team, VVCE) done with a company mentor.
- Goal: an Odoo addon that lets users **design a warehouse layout (editor)** and **see it in 3D inside Odoo**, with live stock from Odoo Inventory.
- Original plan was a separate site (Kafka → FastAPI/WebSocket → React/Three.js) pulling from Odoo. **That plan is dropped.** Everything now lives inside Odoo as a module.
- The team builds its own module from scratch, separate from the company's own Odoo work.
- First task from the mentor: learn the Inventory module and how to code within Odoo. Build in small learning steps.

## Environment
- **Odoo 19 Community** + PostgreSQL 16 on Fedora Linux.
- Workspace: `/mnt/CODE/Workspace`.
- Module name (proposed): `warehouse_3d`, depends on `stock`.

## Working with me (Nitin)
- I write C/C++ comfortably; I can read Python and JS but don't write them independently yet. Briefly explain Odoo-specific patterns (`_inherit`, OWL lifecycle, assets, XML views) the first time they appear.
- I prefer complete deliverables, with you making reasonable decisions. Point out specific gaps when something is missing.

## Architecture
| Concern | Implementation |
|---|---|
| Layout data | New model `warehouse.rack.row` (one record per rack face), plus layout fields on `stock.location` via `_inherit` |
| Locations | Module generates the `stock.location` tree from each rack row: `WH/Stock/<zone>/<row>/<bay>/<level>/<position>` |
| Stock | Read `stock.quant` through the ORM |
| 3D view | OWL client action under the Inventory menu, containing a Three.js scene |
| Three.js | Vendored into `static/lib/`, registered in `__manifest__.py` assets (no CDN) |
| Live updates | Odoo bus service (not WebSockets/Kafka) |
| Editor | Place rack rows on a 2D grid; saving creates/updates the location tree |
| Template data | Data files shipped with the module: layout, locations, products, storage categories, opening stock |

### Rack row record (core data)
```json
{ "code": "P05", "kind": "pallet", "x": 9.7, "y": 1.0, "bays": 7, "bay_width": 2.7,
  "depth": 1.1, "levels": 5, "level_height": 1.8, "slots_per_level": 2 }
```
One record generates the uprights, beams and slots in 3D **and** the Odoo locations. Change a parameter, and both update.

Location codes: pallet `P05-03-2-A` (row-bay-level-position), shelf `S04-10-3` (row-bay-level).

## Template warehouse spec
- Building 60 m × 40 m, 10 m clear height, U-flow (inbound and outbound docks on the same wall, y = 40).
- **Pallet racking** (x 0–38 m, y 1.0–19.9 m): 14 rack faces P01–P14 (single rows at both ends, 6 back-to-back doubles with 0.2 m gap), 3 m reach-truck aisles. 7 bays × 2.7 m, depth 1.1 m, 5 levels × 1.8 m, 2 pallets per bay level = 980 pallet positions.
  - Face x-positions: 0.2, 4.3, 5.6, 9.7, 11.0, 15.1, 16.4, 20.5, 21.8, 25.9, 27.2, 31.3, 32.6, 36.7.
- **Shelving pick zone** (x 39.6–59.6 m, y 2–18 m): 17 faces S01–S17 (8 back-to-back doubles + 1 single). 16 bays × 1.0 m, depth 0.6 m, 5 shelves × 0.4 m = 1,360 bins. 1.2 m picker aisles.
- **Main cross aisle**: y 20–24 m.
- **Bottom strip** (y 24–40 m): Receiving/QC (x 0.5–20), Charging (x 21–29, y 25–30.5), Office (x 21–29, y 31.5–39.5), Packing (x 30–39, y 25–33), Shipping (x 40–59.5).
- **Docks**: 3 inbound (x 3, 8, 13 m) and 3 outbound (x 44, 49, 54 m), each 3 m wide.
- **Template data to load**: 50–200 products with L×W×H and weight (Odoo products only have weight/volume, so add dimension fields), package types (pallet, carton, tote), storage categories ("Pallet rack – bulk", "Shelving – small parts", "Golden zone"), opening stock ~60–70% full, ABC-skewed demand (~20% of SKUs = ~80% of picks).

The prototype `warehaven-3d-prototype.html` in this folder renders exactly this spec in standalone Three.js (InstancedMesh per part type, invisible hit boxes for click → slot lookup). Port its scene code into the OWL client action.

## Odoo putaway (standard behaviour)
- Rule = product / category / package type arriving in location A → store in location B. Product-specific beats category; ties go by sequence.
- Sublocation options: **No** (store in B), **Last used** (last location used for that product), **Closest location** (first child of B with the rule's storage category that has capacity). A storage category is required for Closest location.
- Storage categories limit capacity by max weight, by units per product, or by packages per package type, and control product mixing.
- Gaps: "closest" is not physical distance, there's no volume/3D fit check, no pick-frequency awareness, and decisions are greedy per move.
- Verify all of this in `addons/stock/models/stock_location.py` (`_get_putaway_strategy`) for Odoo 19.

## Optimization (undecided)
Plan: build editor + viewer on **standard putaway first**. Later, optionally add custom strategies from the literature review (3D-BPP/FFD for space, SLAP/ABC for pick frequency) by extending the putaway rule's `sublocation` selection (`selection_add`) and overriding `_get_putaway_strategy` on `stock.location`. Standard vs custom on the same template warehouse = the research paper's experiment.

## Build order
1. Inventory hands-on: warehouse with a real location hierarchy, receipt → putaway → delivery, watch quants.
2. Odoo "Server Framework 101" tutorial.
3. Minimal module: `warehouse.rack.row` model + layout fields on `stock.location` + form/list views + menu.
4. OWL tutorial; client action listing locations.
5. Three.js scene in the client action, rendered from rack-row records (port the prototype).
6. Location generator: rack row → `stock.location` tree.
7. Real stock from `stock.quant`, click slot → open location, bus updates.
8. 2D layout editor.
9. Template warehouse data files.
10. (Optional) custom putaway strategies.
