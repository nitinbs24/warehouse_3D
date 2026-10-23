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
    zoomAt,
} from "@warehouse_3d/editor/geometry";
import { diffLayout, layoutProblems, newRow, snap } from "@warehouse_3d/editor/layout_edit";

const ZOOM_STEP = 1.15;
const INT_FIELDS = new Set(["bays", "levels", "slots_per_level"]);

/**
 * Inventory ▸ Warehouse 3D ▸ Layout Editor: the floor plan seen from above, drawn in SVG.
 * Everything is drawn in metres inside one <g transform>, so zooming and panning only change
 * that transform. Rows can be dragged, edited, added and deleted; nothing reaches the server
 * until Save, which sends every change in one all-or-nothing call (wh3d_save_layout).
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
        this.state = useState({ view: { scale: 10, ox: 0, oy: 0 }, selectedId: null, rows: [], saving: false });
        this.drag = null; // panning the floor
        this.rowDrag = null; // moving a row
        this.userMoved = false; // once the user zooms or pans, resizing no longer refits
        this.nextTmpId = -1; // unsaved rows get negative ids
        onWillStart(async () => {
            let warehouseId = this.props.action.context?.warehouse_id;
            if (!warehouseId) {
                [warehouseId] = await this.orm.search("stock.warehouse", [], { limit: 1 });
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

    get problemList() {
        return Object.values(this.problems);
    }

    get changes() {
        return diffLayout(this.original, this.state.rows);
    }

    get dirty() {
        const c = this.changes;
        return Boolean(c.create.length || c.write.length || c.delete.length);
    }

    get selectedRow() {
        return this.state.rows.find((r) => r.id === this.state.selectedId) || null;
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
        if (ev.button !== 0 || ev.target.closest(".o_wh3d_row")) {
            return; // rows start their own drag
        }
        this.drag = { x: ev.clientX, y: ev.clientY, view: this.state.view, moved: false };
        this.planRef.el.setPointerCapture?.(ev.pointerId);
    }

    onRowPointerDown(ev, row) {
        if (ev.button !== 0) {
            return;
        }
        this.rowDrag = { id: row.id, x: ev.clientX, y: ev.clientY, from: { x: row.x, y: row.y }, moved: false };
        this.planRef.el.setPointerCapture?.(ev.pointerId);
    }

    onPointerMove(ev) {
        const drag = this.rowDrag || this.drag;
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
        if (this.rowDrag) {
            const row = this.state.rows.find((r) => r.id === this.rowDrag.id);
            const scale = this.state.view.scale;
            row.x = snap(this.rowDrag.from.x + dx / scale);
            row.y = snap(this.rowDrag.from.y + dy / scale);
            this.state.selectedId = row.id;
        } else {
            this.userMoved = true;
            this.state.view = pan(this.drag.view, dx, dy);
        }
    }

    onPointerUp() {
        if (this.drag && !this.drag.moved) {
            this.state.selectedId = null; // a click on empty floor clears the selection
        }
        this.drag = null;
        this.rowDrag = null;
    }

    // --- selection and keyboard ---

    selectRow(row) {
        this.state.selectedId = row.id;
    }

    onKeydown(ev) {
        if (ev.key === "Escape") {
            this.state.selectedId = null;
        }
    }

    /** Arrow keys nudge the focused row by 0.1 m (1 m with Shift). */
    onRowKeydown(ev, row) {
        const step = ev.shiftKey ? 1 : 0.1;
        const move = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[ev.key];
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
                this.state.selectedId = null;
            },
            cancel: () => {},
        });
    }

    discard() {
        this.state.rows = this.original.map((r) => ({ ...r }));
        if (!this.selectedRow) {
            this.state.selectedId = null;
        }
    }

    async save() {
        this.state.saving = true;
        try {
            const result = await this.orm.call("warehouse.rack.row", "wh3d_save_layout",
                [this.layout.warehouse_id, this.changes]);
            const selected = this.state.selectedId;
            this.load(result.layout);
            // A new row keeps its selection under its real id.
            this.state.selectedId = selected < 0 ? result.created[selected] ?? null : selected;
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
