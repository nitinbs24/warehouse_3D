import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const LIB = "/warehouse_3d/static/lib/three/";

/**
 * Inventory ▸ Warehouse 3D ▸ 3D View.
 * Three.js is loaded on first open (not bundled), and everything it allocates is freed on leave.
 */
export class View3D extends Component {
    static template = "warehouse_3d.View3D";
    static props = { ...standardActionServiceProps };

    setup() {
        this.canvasRef = useRef("canvas");
        this.state = useState({ error: "" });
        onWillStart(async () => {
            await loadJS(LIB + "three.min.js");
            await loadJS(LIB + "OrbitControls.js"); // extends window.THREE, so it must come second
        });
        onMounted(() => this.start());
        onWillUnmount(() => this.stop());
    }

    start() {
        const THREE = window.THREE;
        const host = this.canvasRef.el;
        try {
            this.renderer = new THREE.WebGLRenderer({ antialias: true });
        } catch {
            this.state.error = _t("The 3D view needs WebGL, which this browser has turned off.");
            return;
        }
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        host.appendChild(this.renderer.domElement);

        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0xe3e8ed);
        this.camera = new THREE.PerspectiveCamera(42, 1, 0.5, 600);
        this.camera.position.set(-36, 37, 41);
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.maxPolarAngle = Math.PI / 2 - 0.04;
        this.controls.target.set(0, 1, 0);

        this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 0.8));
        const sun = new THREE.DirectionalLight(0xffffff, 0.65);
        sun.position.set(-30, 60, 40);
        this.scene.add(sun);

        // Spike content: the 60 × 40 m floor and one pallet-sized box. T7 replaces this with real racks.
        const floor = new THREE.Mesh(new THREE.BoxGeometry(60, 0.1, 40), new THREE.MeshLambertMaterial({ color: 0xd3d9df }));
        floor.position.y = -0.05;
        const box = new THREE.Mesh(new THREE.BoxGeometry(1.2, 1.2, 1.0), new THREE.MeshLambertMaterial({ color: 0xe0701b }));
        box.position.y = 0.6;
        this.scene.add(floor, box);

        this.resizeObserver = new ResizeObserver(() => this.resize());
        this.resizeObserver.observe(host);
        this.resize();
        this.renderer.setAnimationLoop(() => {
            this.controls.update();
            this.renderer.render(this.scene, this.camera);
        });
    }

    resize() {
        const { clientWidth: w, clientHeight: h } = this.canvasRef.el;
        if (!w || !h) {
            return;
        }
        this.renderer.setSize(w, h, false);
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
    }

    stop() {
        if (!this.renderer) {
            return;
        }
        this.renderer.setAnimationLoop(null);
        this.resizeObserver.disconnect();
        this.controls.dispose();
        this.scene.traverse((obj) => {
            obj.geometry?.dispose();
            [].concat(obj.material || []).forEach((m) => m.dispose());
        });
        this.renderer.dispose();
        // Browsers allow only ~16 live WebGL contexts; free ours now rather than at garbage collection.
        this.renderer.forceContextLoss();
        this.renderer.domElement.remove();
        this.renderer = null;
    }
}

registry.category("actions").add("warehouse_3d.view3d", View3D);
