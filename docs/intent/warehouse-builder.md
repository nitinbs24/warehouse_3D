# Warehouse builder: intent

Agreed in an interview on 31 Oct 2026, before any code. Plan: tasks T16–T19 in `docs/todo.md`; how it works: `docs/notes.md`.

- **Outcome:** the Layout Editor becomes a warehouse builder. A manager drags area types from a palette onto the floor plan, moves and resizes them, and adds, moves and deletes dock doors. The result shows in 3D.
- **User:** a warehouse manager (or the mentor) laying out a warehouse, with no XML needed.
- **Why now:** areas (Receiving, Packing, Office, Charging, Shipping) came only from demo data, and the mentor's floorplan needs layouts the demo can't show.
- **Success:** from an empty building, build a layout using only the editor, save it and see it in 3D. The demo warehouse, existing tests and Save rules keep working. Everything is documented.
- **Constraint:** areas stay drawing-only (no Inventory locations, no stock). In 3D an area is a coloured floor patch with a floating label; no props.
- **Out of scope:** rotation, copy/paste, user-defined area types, import/export, props or trucks in 3D, the 44 × 90 row-count question from the mentor's floorplan.

## Details agreed

- **Palette:** a fixed list of common types plus "Custom area" (typed name and colour). No user-defined types.
- **Areas:** drag from the palette, move with 0.1 m snapping, resize by edge handles or the side panel, rename, recolour, delete. Red and Save blocked if outside the building or overlapping a rack row. Areas may overlap each other.
- **Dock doors:** a palette item. They snap to any of the four walls and slide along them; no floating doors. 3D draws door frames on all four walls.
- **XML and the editor share the same records.** There is no import or export.

## Not decided here

- Whether the 44 rows × 90 bays figures in the mentor's floorplan should be kept, or a layout that fits the 316 ft building (about 28 rows × 27 bays). The numbers in that picture don't fit together; this needs the mentor.
