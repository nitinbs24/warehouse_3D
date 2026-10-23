import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
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

const ZOOM_STEP = 1.15;

/**
 * Inventory ▸ Warehouse 3D ▸ Layout Editor: the floor plan seen from above, drawn in SVG.
 * Everything is drawn in metres inside one <g transform>, so zooming and panning only change
 * that transform. Rows are focusable: Tab moves between them, Esc clears the selection.
 */
export class LayoutEditor extends Component {
    static template = "warehouse_3d.LayoutEditor";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.planRef = useRef("plan");
        this.state = useState({ view: { scale: 10, ox: 0, oy: 0 }, selectedId: null });
        this.drag = null;
        this.userMoved = false; // once the user zooms or pans, resizing no longer refits
        onWillStart(async () => {
            let warehouseId = this.props.action.context?.warehouse_id;
            if (!warehouseId) {
                [warehouseId] = await this.orm.search("stock.warehouse", [], { limit: 1 });
            }
            this.layout = await this.orm.call("stock.warehouse", "wh3d_get_layout", [[warehouseId]]);
            this.grid = gridLines(this.layout.building);
        });
        onMounted(() => {
            this.resizeObserver = new ResizeObserver(() => !this.userMoved && this.fit());
            this.resizeObserver.observe(this.planRef.el);
            this.fit();
        });
        onWillUnmount(() => this.resizeObserver.disconnect());
    }

    // --- drawing helpers used by the template ---

    get transform() {
        const { scale, ox, oy } = this.state.view;
        return `translate(${ox} ${oy}) scale(${scale})`;
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

    get selectedRow() {
        return this.layout.rows.find((r) => r.id === this.state.selectedId) || null;
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
            return; // rows handle their own clicks
        }
        this.drag = { x: ev.clientX, y: ev.clientY, view: this.state.view, moved: false };
        this.planRef.el.setPointerCapture?.(ev.pointerId);
    }

    onPointerMove(ev) {
        if (!this.drag) {
            return;
        }
        const dx = ev.clientX - this.drag.x;
        const dy = ev.clientY - this.drag.y;
        if (Math.hypot(dx, dy) > 4) {
            this.drag.moved = true;
            this.userMoved = true;
        }
        if (this.drag.moved) {
            this.state.view = pan(this.drag.view, dx, dy);
        }
    }

    onPointerUp() {
        if (this.drag && !this.drag.moved) {
            this.state.selectedId = null; // a click on empty floor clears the selection
        }
        this.drag = null;
    }

    // --- selection ---

    selectRow(row) {
        this.state.selectedId = row.id;
    }

    onKeydown(ev) {
        if (ev.key === "Escape") {
            this.state.selectedId = null;
        }
    }

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
