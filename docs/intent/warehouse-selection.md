# Choosing the warehouse: intent

Agreed in an interview on 1 Nov 2026, before any code. Plan: tasks T20–T23 in `docs/todo.md`; how it works: `docs/notes.md`.

- **Outcome:** every warehouse can be opened in the 3D view and the Layout Editor, each with its own layout.
- **User:** a manager (or the mentor) with several warehouses in Configuration ▸ Warehouses.
- **Why now:** both screens only ever opened the first warehouse with rack rows (Warehaven DC), so a second warehouse, such as "YourCompany", could never be given a layout.
- **Success:** from the warehouse form or from a dropdown, open any warehouse's 3D view or editor. An empty warehouse can be built from nothing. Existing screens, tests and docs keep working.
- **Constraint:** no new data model. Warehouses stay Odoo's own, and the layout stays per warehouse as it already was.
- **Out of scope:** a landing page of warehouse cards, copying a layout between warehouses, editing the building size inside the editor, per-warehouse permissions.

## Details agreed

- A dropdown at the top of the editor and the 3D view, shown only when more than one warehouse exists. It remembers the last choice (shared by both screens). In the editor, switching with unsaved changes reuses the "Discard layout changes?" warning.
- "3D View" and "Layout Editor" smart buttons on the warehouse form; the editor one only for Inventory managers.
- An empty warehouse shows a friendly "No layout yet" screen with a link to the form to set the building size.
- Order of choice: the warehouse the screen was asked for, else the remembered one (if it still exists and is visible), else the first warehouse with rack rows.

## Not decided here

- Whether a warehouse overview (cards with row counts and a floor-plan thumbnail) becomes worthwhile once there are many warehouses.
