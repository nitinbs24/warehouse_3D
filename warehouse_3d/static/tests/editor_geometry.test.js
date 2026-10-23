import { describe, expect, test } from "@odoo/hoot";
import {
    areaRect,
    fitView,
    gridLines,
    middleSlot,
    pan,
    rowRect,
    toPlan,
    toScreen,
    zoomAt,
} from "@warehouse_3d/editor/geometry";

const BUILDING = { length: 60, width: 40, height: 10 };
const P05 = { id: 5, code: "P05", kind: "pallet", x: 9.7, y: 1.0, bays: 7, bay_width: 2.7, depth: 1.1,
    levels: 5, level_height: 1.8, slots_per_level: 2 };

function close(a, b) {
    return Math.abs(a - b) < 1e-9;
}

describe("fitView", () => {
    test("fits the building with a margin and centres it", () => {
        // 800 × 600 px, 20 px margin: width-bound, (800 − 40) / 60 px per metre.
        const view = fitView(BUILDING, 800, 600, 20);
        expect(close(view.scale, 760 / 60)).toBe(true);
        expect(close(view.ox, 20)).toBe(true);
        expect(close(view.oy, (600 - 40 * view.scale) / 2)).toBe(true);
    });

    test("a tall viewport is height-bound", () => {
        const view = fitView(BUILDING, 400, 1000, 0);
        expect(close(view.scale, 400 / 60)).toBe(true);
        const narrow = fitView(BUILDING, 2000, 200, 0);
        expect(close(narrow.scale, 200 / 40)).toBe(true);
    });
});

describe("screen ↔ plan", () => {
    test("round-trips", () => {
        const view = { scale: 12.5, ox: 33, oy: -7 };
        const [px, py] = toScreen(view, 17.3, 22.1);
        const [x, y] = toPlan(view, px, py);
        expect(close(x, 17.3) && close(y, 22.1)).toBe(true);
    });
});

describe("zoom and pan", () => {
    test("zooming keeps the point under the cursor still", () => {
        const view = { scale: 10, ox: 50, oy: 40 };
        const before = toPlan(view, 300, 200);
        const zoomed = zoomAt(view, 300, 200, 2);
        expect(close(zoomed.scale, 20)).toBe(true);
        const after = toPlan(zoomed, 300, 200);
        expect(close(before[0], after[0]) && close(before[1], after[1])).toBe(true);
    });

    test("zoom is clamped", () => {
        const view = { scale: 10, ox: 0, oy: 0 };
        expect(zoomAt(view, 0, 0, 1000).scale).toBe(200);
        expect(zoomAt(view, 0, 0, 0.0001).scale).toBe(1);
    });

    test("pan moves by screen pixels", () => {
        expect(pan({ scale: 10, ox: 5, oy: 6 }, 20, -4)).toEqual({ scale: 10, ox: 25, oy: 2 });
    });
});

describe("footprints and grid", () => {
    test("row rectangle: depth along x, bays along y", () => {
        const r = rowRect(P05);
        expect(close(r.x, 9.7) && close(r.y, 1) && close(r.w, 1.1) && close(r.h, 18.9)).toBe(true);
    });

    test("area rectangle: width along x, depth along y", () => {
        expect(areaRect({ x: 0.5, y: 25, width: 19.5, depth: 13.5 })).toEqual({ x: 0.5, y: 25, w: 19.5, h: 13.5 });
    });

    test("1 m grid over 60 × 40 m with every 5th line major", () => {
        const lines = gridLines(BUILDING);
        expect(lines.length).toBe(61 + 41);
        expect(lines.filter((l) => l.major).length).toBe(13 + 9);
    });

    test("middle slot of a row, for 'View in 3D'", () => {
        expect(middleSlot(P05)).toEqual({ bay: 4, level: 1, position: 1 });
    });
});
