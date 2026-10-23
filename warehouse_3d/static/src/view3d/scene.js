import {
    areaBox,
    cameraView,
    dockGeometry,
    floorGeometry,
    rackGeometry,
    rowLabelPosition,
    toWorld,
} from "@warehouse_3d/view3d/layout";

// The prototype's light palette.
const COLORS = {
    background: 0xe3e8ed,
    floor: 0xd3d9df,
    grid: 0xbcc4cd,
    curb: 0x8a96a4,
    area: 0xc3d0dc,
    dock: 0xe3a22b,
    steel: 0x3e5c7a,
    beam: 0xe0701b,
    deck: 0x96a3b0,
};
const LABEL = { fg: "#1B2430", muted: "#5B6676", bg: "#FFFFFF", line: "#D3D9E0" };
const FOV = 42;

/**
 * Builds and runs the Three.js scene for one warehouse (data from stock.warehouse.wh3d_get_scene).
 * Needs window.THREE and THREE.OrbitControls loaded. Throws if WebGL is unavailable.
 */
export class WarehouseScene {
    constructor(host, data) {
        const THREE = (this.THREE = window.THREE);
        this.host = host;
        this.building = data.building;
        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        host.appendChild(this.renderer.domElement);

        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(COLORS.background);
        this.camera = new THREE.PerspectiveCamera(FOV, 1, 0.5, 600);
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.08;
        this.controls.maxPolarAngle = Math.PI / 2 - 0.04;
        this.controls.minDistance = 4;
        this.controls.maxDistance = Math.max(180, this.building.length * 3);
        // Softer than the prototype's 0.8 + 0.65, which washed flat floors out to white.
        this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8899aa, 0.55));
        const sun = new THREE.DirectionalLight(0xffffff, 0.5);
        sun.position.set(-30, 60, 40);
        this.scene.add(sun);

        this.unitBox = new THREE.BoxGeometry(1, 1, 1);
        this.buildFloor();
        this.buildAreas(data.areas);
        this.buildRacks(data.rows);
        this.labels = new THREE.Group();
        this.scene.add(this.labels);
        this.buildLabels(data.areas, data.rows);

        this.reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
        this.anim = null;
        this.resizeObserver = new ResizeObserver(() => this.resize());
        this.resizeObserver.observe(host);
        this.resize();
        this.setView("3d", true);
        this.renderer.setAnimationLoop(() => this.frame());
    }

    // --- building blocks ---

    material(color) {
        return new this.THREE.MeshLambertMaterial({ color });
    }

    addBox(box, material) {
        const mesh = new this.THREE.Mesh(this.unitBox, material);
        mesh.position.set(box[0], box[1], box[2]);
        mesh.scale.set(box[3], box[4], box[5]);
        this.scene.add(mesh);
        return mesh;
    }

    /** One draw call for many identical boxes: thousands of uprights cost the GPU almost nothing. */
    addInstanced(boxes, material) {
        const THREE = this.THREE;
        const mesh = new THREE.InstancedMesh(this.unitBox, material, Math.max(boxes.length, 1));
        const m = new THREE.Matrix4();
        const q = new THREE.Quaternion();
        boxes.forEach((b, i) => {
            m.compose(new THREE.Vector3(b[0], b[1], b[2]), q, new THREE.Vector3(b[3], b[4], b[5]));
            mesh.setMatrixAt(i, m);
        });
        mesh.count = boxes.length;
        mesh.instanceMatrix.needsUpdate = true;
        this.scene.add(mesh);
        return mesh;
    }

    buildFloor() {
        const THREE = this.THREE;
        const { floor, gridLines, curbs } = floorGeometry(this.building);
        this.addBox(floor, this.material(COLORS.floor));
        const points = gridLines.flatMap(([x1, z1, x2, z2]) => [x1, 0.01, z1, x2, 0.01, z2]);
        const grid = new THREE.BufferGeometry();
        grid.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
        this.scene.add(new THREE.LineSegments(grid, new THREE.LineBasicMaterial({ color: COLORS.grid })));
        this.addInstanced(curbs, this.material(COLORS.curb));
    }

    buildAreas(areas) {
        const floorAreas = areas.filter((a) => a.kind === "area");
        const docks = areas.filter((a) => a.kind === "dock").map((d) => dockGeometry(d, this.building));
        this.addInstanced(floorAreas.map((a) => areaBox(a, this.building)), this.material(COLORS.area));
        this.addInstanced(docks.map((d) => d.pad), this.material(COLORS.dock));
        this.addInstanced(docks.flatMap((d) => d.frame), this.material(COLORS.steel));
    }

    buildRacks(rows) {
        const parts = rows.map((row) => rackGeometry(row, this.building));
        this.addInstanced(parts.flatMap((p) => p.uprights), this.material(COLORS.steel));
        this.addInstanced(parts.flatMap((p) => p.beams), this.material(COLORS.beam));
        this.addInstanced(parts.flatMap((p) => p.decks), this.material(COLORS.deck));
    }

    buildLabels(areas, rows) {
        for (const area of areas.filter((a) => a.kind === "area")) {
            const [x, z] = toWorld(this.building, area.x + area.width / 2, area.y + area.depth / 2);
            this.addLabel(area.name, [x, 0.9, z], 1.4, true);
        }
        rows.forEach((row, i) => {
            const height = row.kind === "pallet" ? 0.6 : 0.34;
            this.addLabel(row.code, rowLabelPosition(row, i, this.building), height, false);
        });
    }

    /** Text drawn on a canvas, shown as a sprite that always faces the camera. */
    addLabel(text, position, height, pill) {
        const THREE = this.THREE;
        const fontSize = 64;
        const padX = pill ? 30 : 6;
        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d");
        const font = `600 ${fontSize}px "Arial Narrow", "Helvetica Neue", sans-serif`;
        ctx.font = font;
        canvas.width = Math.ceil(ctx.measureText(text).width) + padX * 2;
        canvas.height = fontSize + (pill ? 36 : 16);
        ctx.font = font;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        if (pill) {
            const r = (canvas.height - 4) / 2;
            ctx.beginPath();
            ctx.roundRect(2, 2, canvas.width - 4, canvas.height - 4, r);
            ctx.fillStyle = LABEL.bg;
            ctx.fill();
            ctx.lineWidth = 3;
            ctx.strokeStyle = LABEL.line;
            ctx.stroke();
        }
        ctx.fillStyle = pill ? LABEL.fg : LABEL.muted;
        ctx.fillText(text, canvas.width / 2, canvas.height / 2 + 3);
        const texture = new THREE.CanvasTexture(canvas);
        texture.minFilter = THREE.LinearFilter;
        texture.generateMipmaps = false;
        // Area labels stay readable through racks (no depth test); row codes hide behind them.
        const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
            map: texture, transparent: true, depthWrite: false, depthTest: !pill,
        }));
        sprite.scale.set((height * canvas.width) / canvas.height, height, 1);
        sprite.position.set(...position);
        if (pill) {
            sprite.renderOrder = 10;
        }
        this.labels.add(sprite);
    }

    // --- camera ---

    setView(mode, instant = false) {
        const THREE = this.THREE;
        const view = cameraView(mode, this.building, FOV, this.camera.aspect);
        const position = new THREE.Vector3(...view.position);
        const target = new THREE.Vector3(...view.target);
        if (instant || this.reduceMotion) {
            this.camera.position.copy(position);
            this.controls.target.copy(target);
            this.controls.update();
            this.anim = null;
            return;
        }
        this.anim = {
            t0: performance.now(),
            p0: this.camera.position.clone(), q0: this.controls.target.clone(),
            p1: position, q1: target,
        };
    }

    setLabelsVisible(visible) {
        this.labels.visible = visible;
    }

    frame() {
        if (this.anim) {
            const k = Math.min(1, (performance.now() - this.anim.t0) / 700);
            const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2; // ease in-out
            this.camera.position.lerpVectors(this.anim.p0, this.anim.p1, e);
            this.controls.target.lerpVectors(this.anim.q0, this.anim.q1, e);
            if (k >= 1) {
                this.anim = null;
            }
        }
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
    }

    resize() {
        const { clientWidth: w, clientHeight: h } = this.host;
        if (!w || !h) {
            return;
        }
        this.renderer.setSize(w, h, false);
        this.camera.aspect = w / h;
        this.camera.updateProjectionMatrix();
    }

    /** Frees everything: WebGL memory isn't garbage-collected and browsers cap live contexts (~16). */
    dispose() {
        this.renderer.setAnimationLoop(null);
        this.resizeObserver.disconnect();
        this.controls.dispose();
        this.scene.traverse((obj) => {
            obj.geometry?.dispose();
            for (const m of [].concat(obj.material || [])) {
                m.map?.dispose();
                m.dispose();
            }
        });
        this.renderer.dispose();
        this.renderer.forceContextLoss();
        this.renderer.domElement.remove();
    }
}
