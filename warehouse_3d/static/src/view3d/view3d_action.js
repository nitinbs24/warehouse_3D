import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { WarehouseScene } from "@warehouse_3d/view3d/scene";

const LIB = "/warehouse_3d/static/lib/three/";

/**
 * Inventory ▸ Warehouse 3D ▸ 3D View.
 * Loads Three.js on first open (not bundled) and the warehouse's scene data, then hands both to
 * WarehouseScene. Everything the scene allocates is freed on leave.
 */
export class View3D extends Component {
    static template = "warehouse_3d.View3D";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.canvasRef = useRef("canvas");
        this.state = useState({ error: "", rowCount: 0, view: "3d", labels: true });
        onWillStart(async () => {
            const [scene] = await Promise.all([this.loadScene(), this.loadThree()]);
            this.data = scene;
            this.state.rowCount = scene.rows.length;
        });
        onMounted(() => this.start());
        onWillUnmount(() => this.scene?.dispose());
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
            this.scene = new WarehouseScene(this.canvasRef.el, this.data);
        } catch {
            this.state.error = _t("The 3D view needs WebGL, which this browser has turned off.");
        }
    }

    setView(mode) {
        this.state.view = mode;
        this.scene?.setView(mode);
    }

    toggleLabels(ev) {
        this.state.labels = ev.target.checked;
        this.scene?.setLabelsVisible(this.state.labels);
    }
}

registry.category("actions").add("warehouse_3d.view3d", View3D);
