import { Component, onMounted, onWillDestroy, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { slotBox } from "@warehouse_3d/view3d/layout";
import { UpdateQueue } from "@warehouse_3d/view3d/live";
import {
    capacitySummary,
    fillBand,
    legendCounts,
    mergeSlotUpdates,
    normalizeCode,
} from "@warehouse_3d/view3d/occupancy";
import { WarehouseScene } from "@warehouse_3d/view3d/scene";

const LIB = "/warehouse_3d/static/lib/three/";

/**
 * Inventory ▸ Warehouse 3D ▸ 3D View.
 * Loads Three.js on first open (not bundled) and the warehouse's scene data, then hands both to
 * WarehouseScene. The side panel shows the selected slot, Find, capacity and the occupancy legend.
 */
export class View3D extends Component {
    static template = "warehouse_3d.View3D";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.busService = useService("bus_service");
        this.canvasRef = useRef("canvas");
        this.state = useState({
            error: "", rowCount: 0, view: "3d", labels: true, stock: true, occupancy: false,
            selected: -1, find: "", findError: "", summary: null, legend: null, updates: 0,
        });
        // Listen *before* loading the scene: a stock change committed while Three.js and the scene
        // load is queued and applied once the scene is ready, instead of being missed.
        this.updates = new UpdateQueue({
            delay: 150,
            retryDelay: 5000,
            fetch: (ids) => this.fetchSlots(ids),
            apply: (ids, fresh) => this.applySlots(ids, fresh),
        });
        this.onStockChanged = ({ location_ids }) => this.updates.push(location_ids);
        this.busService.subscribe("warehouse_3d/stock", this.onStockChanged);
        this.busService.start();
        onWillStart(async () => {
            const [scene] = await Promise.all([this.loadScene(), this.loadThree()]);
            this.data = scene;
            this.slotByCode = new Map(scene.slots.map((s, i) => [s.code, i]));
            this.slotByLocation = new Map(scene.slots.map((s, i) => [s.location_id, i]));
            this.rowsById = Object.fromEntries(scene.rows.map((r) => [r.id, r]));
            this.state.rowCount = scene.rows.length;
            this.refreshStats();
        });
        onMounted(() => {
            this.start();
            this.updates.start();
        });
        onWillUnmount(() => {
            this.scene?.dispose();
            this.scene = null;
        });
        // Runs even if loading failed and the view never mounted, so the listener can't leak.
        onWillDestroy(() => {
            this.busService.unsubscribe("warehouse_3d/stock", this.onStockChanged);
            this.updates.stop();
        });
    }

    async loadThree() {
        await loadJS(LIB + "three.min.js");
        await loadJS(LIB + "OrbitControls.js"); // extends window.THREE, so it must come second
    }

    async loadScene() {
        let warehouseId = this.props.action.context?.warehouse_id;
        if (!warehouseId) {
            [warehouseId] = await this.orm.search("stock.warehouse", [], { limit: 1 });
        }
        return this.orm.call("stock.warehouse", "wh3d_get_scene", [[warehouseId]]);
    }

    start() {
        try {
            this.scene = new WarehouseScene(this.canvasRef.el, this.data, {
                onSelect: (index) => (this.state.selected = index),
            });
            this.focusFromContext();
        } catch {
            this.state.error = _t("The 3D view needs WebGL, which this browser has turned off.");
        }
    }

    // --- live updates ---

    /** Opened from the layout editor's "View in 3D": select and fly to the given slot. */
    focusFromContext() {
        const ctx = this.props.action.context || {};
        if (!ctx.focus_row_id) {
            return;
        }
        const index = this.data.slots.findIndex((s) => s.row_id === ctx.focus_row_id
            && s.bay === ctx.focus_bay && s.level === ctx.focus_level && s.position === ctx.focus_position);
        if (index >= 0) {
            this.state.selected = index;
            this.state.view = "";
            this.scene.select(index);
            this.scene.focusOn(index);
        }
    }

    // Bus messages (stock.quant changes) go through this.updates: throttled, one fetch at a time.

    async fetchSlots(ids) {
        const mine = ids.filter((id) => this.slotByLocation.has(id)); // others: another warehouse
        return mine.length ? this.orm.call("stock.warehouse", "wh3d_get_slots", [mine]) : [];
    }

    applySlots(ids, fresh) {
        // Same array the scene draws from, so buildStock() sees the new values.
        if (!mergeSlotUpdates(this.data.slots, this.slotByLocation, ids, fresh)) {
            return;
        }
        this.scene?.buildStock();
        this.refreshStats();
        this.state.updates++; // slots aren't reactive: re-render the panel explicitly
    }

    refreshStats() {
        this.state.summary = capacitySummary(this.data.rows, this.data.slots);
        this.state.legend = legendCounts(this.data.slots);
    }

    // --- toolbar ---

    setView(mode) {
        this.state.view = mode;
        this.scene?.setView(mode);
    }

    toggleLabels(ev) {
        this.state.labels = ev.target.checked;
        this.scene?.setLabelsVisible(this.state.labels);
    }

    toggleStock(ev) {
        this.state.stock = ev.target.checked;
        this.scene?.setStockVisible(this.state.stock);
    }

    toggleOccupancy(ev) {
        this.state.occupancy = ev.target.checked;
        this.scene?.setColourByOccupancy(this.state.occupancy);
    }

    // --- selected slot ---

    get selectedSlot() {
        return this.state.selected >= 0 ? this.data.slots[this.state.selected] : null;
    }

    get selectedInfo() {
        const slot = this.selectedSlot;
        const row = this.rowsById[slot.row_id];
        const isPallet = row.kind === "pallet";
        const { base } = slotBox(row, slot, this.data.building);
        const width = row.bay_width / row.slots_per_level;
        const stock = slot.stock;
        return {
            slot, row,
            zone: isPallet ? _t("Pallet racking") : _t("Shelving"),
            level: `${slot.level} of ${row.levels} · ${base.toFixed(2)} m`,
            capacity: `${width.toFixed(2)} × ${row.depth.toFixed(2)} × ${row.level_height.toFixed(2)} m · ${slot.capacity_m3.toFixed(2)} m³`,
            fill: stock && stock.fill !== null ? `${Math.round(stock.fill * 100)} %` : "",
            band: stock ? fillBand(stock.fill) : "",
        };
    }

    openInInventory() {
        const slot = this.selectedSlot;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: slot.code,
            res_model: "stock.quant",
            views: [[false, "list"]],
            domain: [["location_id", "=", slot.location_id]],
            context: { create: false },
        });
    }

    // --- find ---

    onFindInput(ev) {
        this.state.find = ev.target.value;
        this.state.findError = "";
    }

    onFind(ev) {
        ev.preventDefault();
        const code = normalizeCode(this.state.find);
        if (!code) {
            this.state.findError = _t("Enter a location code, like P05-03-2-A or S04-10-3.");
            return;
        }
        const index = this.slotByCode.get(code);
        if (index === undefined) {
            this.state.findError = _t(
                "No location %s. Pallet codes look like P05-03-2-A, shelf codes like S04-10-3.", code);
            return;
        }
        this.state.findError = "";
        this.state.selected = index;
        this.state.view = "";
        this.scene?.select(index);
        this.scene?.focusOn(index);
    }

    percent(value) {
        return value === null ? "–" : `${Math.round(value * 100)} %`;
    }
}

registry.category("actions").add("warehouse_3d.view3d", View3D);
