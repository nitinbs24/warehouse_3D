import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import {
    areaRect,
    fitView,
    gridLines,
    middleSlot,
    pan,
    rowRect,
    toPlan,
    zoomAt,
} from "@warehouse_3d/editor/geometry";
import {
    AREA_TYPES,
    areaProblems,
    diffAreas,
    diffLayout,
    layoutProblems,
    moveDock,
    newArea,
    newDock,
    newRow,
    resizeArea,
    setDockOpening,
    snap,
} from "@warehouse_3d/editor/layout_edit";

const ZOOM_STEP = 1.15;
const INT_FIELDS = new Set(["bays", "levels", "slots_per_level"]);
const AREA_DRAG_TYPE = "application/x-wh3d-area"; // so only palette items can be dropped on the plan
const HANDLE_PX = 9; // resize handles keep this size on screen at any zoom
const EDGES = { nw: [0, 0], n: [0.5, 0], ne: [1, 0], e: [1, 0.5], se: [1, 1], s: [0.5, 1], sw: [0, 1], w: [0, 0.5] };

/**
 * Inventory ▸ Warehouse 3D ▸ Layout Editor: the floor plan seen from above, drawn in SVG.
 * Everything is drawn in metres inside one <g transform>, so zooming and panning only change
 * that transform. Rows and floor areas can be dragged, edited, added and deleted (areas come from a
 * palette and can also be resized); nothing reaches the server until Save, which sends every
 * change in one all-or-nothing call (wh3d_save_layout). Dock doors are areas of kind "dock" that
 * always sit on one of the four walls: dragging one makes it jump to the nearest wall.
 */
export class LayoutEditor extends Component {
    static template = "warehouse_3d.LayoutEditor";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.planRef = useRef("plan");
        this.state = useState({ view: { scale: 10, ox: 0, oy: 0 }, selectedId: null, selectedAreaId: null, rows: [], areas: [], saving: false });
        this.areaTypes = AREA_TYPES;
        this.drag = null; // panning the floor
        this.itemDrag = null; // moving a row or an area
        this.resizeDrag = null; // dragging an area's edge or corner
        this.userMoved = false; // once the user zooms or pans, resizing no longer refits
        this.nextTmpId = -1; // unsaved rows and areas get negative ids
        onWillStart(async () => {
            let warehouseId = this.props.action.context?.warehouse_id;
            if (!warehouseId) {
                // The first warehouse with a rack layout (e.g. the template "Warehaven DC"), else the first one.
                warehouseId = await this.orm.call("stock.warehouse", "wh3d_default_warehouse_id", []);
            }
            this.load(await this.orm.call("stock.warehouse", "wh3d_get_layout", [[warehouseId]]));
        });
        onMounted(() => {
            this.resizeObserver = new ResizeObserver(() => !this.userMoved && this.fit());
            this.resizeObserver.observe(this.planRef.el);
            this.fit();
        });
        onWillUnmount(() => this.resizeObserver.disconnect());
        useSetupAction({
            beforeLeave: () => this.confirmLeave(),
            beforeUnload: (ev) => {
                if (this.dirty) {
                    ev.preventDefault();
                    ev.returnValue = ""; // the browser shows its own "leave site?" prompt
                }
            },
        });
    }

    load(layout) {
        this.layout = layout;
        this.original = layout.rows.map((r) => ({ ...r }));
        this.state.rows = layout.rows.map((r) => ({ ...r }));
        this.originalAreas = layout.areas.map((a) => ({ ...a }));
        this.state.areas = layout.areas.map((a) => ({ ...a }));
        this.grid = gridLines(layout.building);
    }

    // --- derived state used by the template ---

    get transform() {
        const { scale, ox, oy } = this.state.view;
        return `translate(${ox} ${oy}) scale(${scale})`;
    }

    get problems() {
        return layoutProblems(this.state.rows, this.layout.building);
    }

    get areaProblemMap() {
        return areaProblems(this.state.areas, this.state.rows, this.layout.building);
    }

    get problemList() {
        return [...Object.values(this.problems), ...Object.values(this.areaProblemMap)];
    }

    get changes() {
        return { ...diffLayout(this.original, this.state.rows), areas: diffAreas(this.originalAreas, this.state.areas) };
    }

    get dirty() {
        const { areas, ...rows } = this.changes;
        return [rows, areas].some((c) => c.create.length || c.write.length || c.delete.length);
    }

    get selectedRow() {
        return this.state.rows.find((r) => r.id === this.state.selectedId) || null;
    }

    get selectedArea() {
        return this.state.areas.find((a) => a.id === this.state.selectedAreaId) || null;
    }

    get areaCount() {
        return this.state.areas.filter((a) => a.kind === "area").length;
    }

    get dockCount() {
        return this.state.areas.length - this.areaCount;
    }

    /** A dock's opening along its wall, in metres (its other size is the wall's thickness). */
    dockOpening(dock) {
        return Math.max(dock.width, dock.depth);
    }

    /** Resize handles of the selected area: {edge, x, y} in metres, plus their size in metres. */
    get handles() {
        const r = areaRect(this.selectedArea);
        return Object.entries(EDGES).map(([edge, [fx, fy]]) => ({ edge, x: r.x + fx * r.w, y: r.y + fy * r.h }));
    }

    get handleSize() {
        return HANDLE_PX / this.state.view.scale;
    }

    rowRect(row) {
        return rowRect(row);
    }

    areaRect(area) {
        return areaRect(area);
    }

    metres(value) {
        return value.toFixed(2);
    }

    // --- view: fit, zoom, pan ---

    fit() {
        const { clientWidth, clientHeight } = this.planRef.el;
        if (clientWidth && clientHeight) {
            this.state.view = fitView(this.layout.building, clientWidth, clientHeight);
        }
    }

    onFitClick() {
        this.userMoved = false;
        this.fit();
    }

    onWheel(ev) {
        ev.preventDefault();
        const rect = this.planRef.el.getBoundingClientRect();
        const factor = ev.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
        this.state.view = zoomAt(this.state.view, ev.clientX - rect.left, ev.clientY - rect.top, factor);
        this.userMoved = true;
    }

    onPointerDown(ev) {
        if (ev.button !== 0 || ev.target.closest(".o_wh3d_row, .o_wh3d_area, .o_wh3d_dock, .o_wh3d_handle")) {
            return; // rows, areas and handles start their own drag
        }
        this.drag = { x: ev.clientX, y: ev.clientY, view: this.state.view, moved: false };
        this.planRef.el.setPointerCapture?.(ev.pointerId);
    }

    onRowPointerDown(ev, row) {
        this.startItemDrag(ev, "rows", row);
    }

    onAreaPointerDown(ev, area) {
        this.startItemDrag(ev, "areas", area);
    }

    startItemDrag(ev, list, item) {
        if (ev.button !== 0) {
            return;
        }
        this.itemDrag = { list, id: item.id, x: ev.clientX, y: ev.clientY, from: { x: item.x, y: item.y, width: item.width, depth: item.depth }, moved: false };
        this.planRef.el.setPointerCapture?.(ev.pointerId);
    }

    onHandlePointerDown(ev, edge) {
        if (ev.button === 0) {
            this.resizeDrag = { edge, id: this.state.selectedAreaId };
            this.planRef.el.setPointerCapture?.(ev.pointerId);
        }
    }

    /** Plan coordinates (metres) of a mouse event. */
    planPoint(ev) {
        const rect = this.planRef.el.getBoundingClientRect();
        return toPlan(this.state.view, ev.clientX - rect.left, ev.clientY - rect.top);
    }

    onPointerMove(ev) {
        if (this.resizeDrag) {
            const area = this.state.areas.find((a) => a.id === this.resizeDrag.id);
            Object.assign(area, resizeArea(area, this.resizeDrag.edge, this.planPoint(ev)));
            return;
        }
        const drag = this.itemDrag || this.drag;
        if (!drag) {
            return;
        }
        const dx = ev.clientX - drag.x;
        const dy = ev.clientY - drag.y;
        if (Math.hypot(dx, dy) > 4) {
            drag.moved = true;
        }
        if (!drag.moved) {
            return;
        }
        if (this.itemDrag) {
            const { list, id, from } = this.itemDrag;
            const item = this.state[list].find((i) => i.id === id);
            const scale = this.state.view.scale;
            if (item.kind === "dock") {
                // The door follows the mouse by its centre and snaps to the nearest wall.
                const centre = [from.x + from.width / 2 + dx / scale, from.y + from.depth / 2 + dy / scale];
                Object.assign(item, moveDock(from, centre, this.layout.building));
            } else {
                item.x = snap(from.x + dx / scale);
                item.y = snap(from.y + dy / scale);
            }
            this.select(list, item);
        } else {
            this.userMoved = true;
            this.state.view = pan(this.drag.view, dx, dy);
        }
    }

    onPointerUp() {
        if (this.drag && !this.drag.moved) {
            this.clearSelection(); // a click on empty floor clears the selection
        }
        this.drag = null;
        this.itemDrag = null;
        this.resizeDrag = null;
    }

    // --- selection and keyboard ---

    /** One thing is selected at a time: a row or an area. */
    select(list, item) {
        this.state.selectedId = list === "rows" ? item.id : null;
        this.state.selectedAreaId = list === "areas" ? item.id : null;
    }

    selectRow(row) {
        this.select("rows", row);
    }

    selectArea(area) {
        this.select("areas", area);
    }

    clearSelection() {
        this.state.selectedId = null;
        this.state.selectedAreaId = null;
    }

    onKeydown(ev) {
        if (ev.key === "Escape") {
            this.clearSelection();
        }
    }

    /** The arrow key's move in metres: 0.1 m, or 1 m with Shift. Undefined for other keys. */
    arrowMove(ev) {
        const step = ev.shiftKey ? 1 : 0.1;
        return { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[ev.key];
    }

    /** Arrow keys nudge the focused row by 0.1 m (1 m with Shift). */
    onRowKeydown(ev, row) {
        const move = this.arrowMove(ev);
        if (move) {
            ev.preventDefault();
            row.x = snap(row.x + move[0]);
            row.y = snap(row.y + move[1]);
        }
    }

    // --- editing ---

    /**
     * A field was committed (Enter, leaving the field, or a spinner click). Not on every keystroke:
     * re-rendering mid-typing rewrites the box and a half-typed "10." would be lost.
     */
    onFieldInput(field, ev) {
        const row = this.selectedRow;
        const raw = ev.target.value;
        if (field === "code") {
            row.code = raw.trim().toUpperCase();
            return;
        }
        if (field === "kind") {
            row.kind = raw;
            if (raw === "shelf") {
                row.slots_per_level = 1; // shelving has one bin per level (server rule)
            }
            return;
        }
        const value = INT_FIELDS.has(field) ? parseInt(raw, 10) : parseFloat(raw);
        if (Number.isFinite(value) && value >= 0) {
            row[field] = INT_FIELDS.has(field) ? value : Math.round(value * 100) / 100;
        }
    }

    /** A dock door dropped on the plan lands on the wall nearest the drop; clicked, on the front wall's middle. */
    addDock(at) {
        const { length } = this.layout.building;
        const dock = newDock(at || [length / 2, 0], this.layout.building, this.nextTmpId--, this.state.areas);
        this.state.areas.push(dock);
        this.selectArea(dock);
    }

    /** A palette item was dragged onto the plan, or clicked (then it lands in the middle of the view). */
    addArea(type, at) {
        const { clientWidth, clientHeight } = this.planRef.el;
        const centre = toPlan(this.state.view, clientWidth / 2, clientHeight / 2);
        const area = newArea(type, at || centre, this.layout.building, this.nextTmpId--);
        this.state.areas.push(area);
        this.selectArea(area);
    }

    onPaletteDragStart(ev, key) {
        ev.dataTransfer.setData(AREA_DRAG_TYPE, key);
        ev.dataTransfer.effectAllowed = "copy";
    }

    onPlanDragOver(ev) {
        if (ev.dataTransfer.types.includes(AREA_DRAG_TYPE)) {
            ev.preventDefault(); // allow the drop
        }
    }

    onPlanDrop(ev) {
        const key = ev.dataTransfer.getData(AREA_DRAG_TYPE);
        const type = AREA_TYPES.find((t) => t.key === key);
        if (type || key === "dock") {
            ev.preventDefault();
            const at = this.planPoint(ev);
            return type ? this.addArea(type, at) : this.addDock(at);
        }
    }

    /** Same rules as onFieldInput: committed on change, bad values are ignored. */
    onAreaField(field, ev) {
        const area = this.selectedArea;
        const raw = ev.target.value;
        if (field === "name") {
            area.name = raw.trim() || area.name;
        } else if (field === "opening") {
            Object.assign(area, setDockOpening(area, parseFloat(raw), this.layout.building));
        } else if (field === "color") {
            area.color = /^#[0-9a-f]{6}$/i.test(raw) ? raw.toLowerCase() : area.color;
        } else {
            const value = parseFloat(raw);
            if (Number.isFinite(value) && value >= 0) {
                area[field] = Math.round(value * 100) / 100;
            }
        }
    }

    onAreaKeydown(ev, area) {
        const move = area.kind === "dock" && this.arrowMove(ev);
        if (!move) {
            return this.onRowKeydown(ev, area); // areas nudge like rows
        }
        ev.preventDefault();
        const centre = [area.x + area.width / 2 + move[0], area.y + area.depth / 2 + move[1]];
        Object.assign(area, moveDock(area, centre, this.layout.building));
    }

    deleteArea() {
        const area = this.selectedArea;
        this.dialog.add(ConfirmationDialog, {
            title: area.kind === "dock" ? _t("Delete dock door %s?", area.name) : _t("Delete area %s?", area.name),
            body: _t("It is only a drawing: no stock or locations are affected. The deletion is saved with Save."),
            confirmLabel: _t("Delete"),
            confirmClass: "btn-danger",
            confirm: () => {
                this.state.areas = this.state.areas.filter((a) => a.id !== area.id);
                this.clearSelection();
            },
            cancel: () => {},
        });
    }

    addRow(kind) {
        const row = newRow(kind, this.state.rows, this.layout.building, this.nextTmpId--);
        if (!row) {
            this.notification.add(_t("There is no free floor left for a new row."), { type: "warning" });
            return;
        }
        this.state.rows.push(row);
        this.state.selectedId = row.id;
    }

    deleteRow() {
        const row = this.selectedRow;
        this.dialog.add(ConfirmationDialog, {
            title: _t("Delete rack row %s?", row.code),
            body: _t("Its locations will be archived when you save. Saving is refused if any of them holds stock."),
            confirmLabel: _t("Delete"),
            confirmClass: "btn-danger",
            confirm: () => {
                this.state.rows = this.state.rows.filter((r) => r.id !== row.id);
                this.clearSelection();
            },
            cancel: () => {},
        });
    }

    discard() {
        this.state.rows = this.original.map((r) => ({ ...r }));
        this.state.areas = this.originalAreas.map((a) => ({ ...a }));
        if (!this.selectedRow && !this.selectedArea) {
            this.clearSelection();
        }
    }

    async save() {
        this.state.saving = true;
        try {
            const result = await this.orm.call("warehouse.rack.row", "wh3d_save_layout",
                [this.layout.warehouse_id, this.changes]);
            const { selectedId: selected, selectedAreaId: selectedArea } = this.state;
            this.load(result.layout);
            // A new row or area keeps its selection under its real id.
            this.state.selectedId = selected < 0 ? result.created[selected] ?? null : selected;
            this.state.selectedAreaId = selectedArea < 0 ? result.created_areas[selectedArea] ?? null : selectedArea;
            this.notification.add(_t("Layout saved."), { type: "success" });
        } catch (error) {
            // Nothing was saved (the server applies all changes or none); the edits stay on screen.
            const message = error.data?.message || error.message || String(error);
            this.notification.add(message, { title: _t("Layout not saved"), type: "danger", sticky: true });
        } finally {
            this.state.saving = false;
        }
    }

    /** Leaving with unsaved edits: ask first. Returning false keeps the user here. */
    confirmLeave() {
        if (!this.dirty) {
            return true;
        }
        return new Promise((resolve) => {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Discard layout changes?"),
                body: _t("You have unsaved changes to the layout. Leaving will discard them."),
                confirmLabel: _t("Discard and leave"),
                confirmClass: "btn-danger",
                confirm: () => resolve(true),
                cancel: () => resolve(false),
            });
        });
    }

    // --- elsewhere ---

    viewIn3d() {
        const row = this.selectedRow;
        const slot = middleSlot(row);
        this.action.doAction("warehouse_3d.action_wh3d_view3d", {
            additionalContext: {
                warehouse_id: this.layout.warehouse_id,
                focus_row_id: row.id,
                focus_bay: slot.bay,
                focus_level: slot.level,
                focus_position: slot.position,
            },
        });
    }

    openRowForm() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "warehouse.rack.row",
            res_id: this.state.selectedId,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("warehouse_3d.editor", LayoutEditor);
