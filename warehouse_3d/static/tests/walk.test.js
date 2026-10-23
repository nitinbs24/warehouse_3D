import { describe, expect, test } from "@odoo/hoot";
import {
    EYE_HEIGHT,
    RADIUS,
    WALK_SPEED,
    look,
    moveVector,
    rackObstacles,
    stepWalker,
    walkStartAtEntrance,
    walkStartAtSlot,
} from "@warehouse_3d/view3d/walk";

// Plan coordinates: metres from the building corner, x along the length, y along the width.
const BUILDING = { length: 60, width: 40, height: 10 };
const PALLET = { kind: "pallet", y: 1.0, bays: 7, bay_width: 2.7, depth: 1.1, levels: 5,
    level_height: 1.8, slots_per_level: 2 };
const P04 = { ...PALLET, id: 4, code: "P04", x: 9.7 };
const P05 = { ...PALLET, id: 5, code: "P05", x: 11.0 }; // back to back with P04 (0.2 m gap)
const P06 = { ...PALLET, id: 6, code: "P06", x: 15.1 }; // across a 3 m aisle
const LONE = { ...PALLET, id: 9, code: "P09", x: 9.7 };

function close(a, b, tol = 1e-9) {
    return Math.abs(a - b) < tol;
}

/** Walk for ``seconds`` at 60 frames per second holding ``keys``. */
function walkFor(start, keys, seconds, rows, building = BUILDING) {
    const obstacles = rackObstacles(rows);
    let pos = { ...start };
    for (let i = 0; i < seconds * 60; i++) {
        pos = stepWalker(pos, moveVector(keys, pos.yaw, 1 / 60), obstacles, building);
    }
    return pos;
}

describe("start pose", () => {
    test("in front of a selected slot, in its aisle, facing it", () => {
        // Lone row, nothing on its -x side: stand back 2.5 m (the cap), facing +x (yaw 0).
        const pose = walkStartAtSlot(LONE, { bay: 3, level: 2, position: 1 }, [LONE], BUILDING);
        expect(close(pose.x, 9.7 - 2.5)).toBe(true);
        expect(close(pose.y, 1 + 2 * 2.7 + 0.5 * 1.35)).toBe(true); // bay 3, position A
        expect(close(pose.yaw, 0)).toBe(true);
    });

    test("back-to-back row: from its open aisle, mid-aisle, facing -x", () => {
        const pose = walkStartAtSlot(P05, { bay: 1, level: 1, position: 2 }, [P04, P05, P06], BUILDING);
        expect(close(pose.x, 12.1 + 1.5)).toBe(true); // half of the 3 m aisle to P06
        expect(close(Math.abs(pose.yaw), Math.PI)).toBe(true);
    });

    test("no selection: at the first dock door, facing into the building", () => {
        const dock = { kind: "dock", x: 3, y: 38.4, width: 3, depth: 1.6 };
        const pose = walkStartAtEntrance([{ kind: "area", x: 0.5, y: 25, width: 19.5, depth: 13.5 }, dock], BUILDING);
        expect(close(pose.x, 4.5) && close(pose.y, 39.2)).toBe(true);
        expect(Math.sin(pose.yaw) < 0).toBe(true); // looking towards smaller y = into the hall
    });

    test("no docks: middle of the front wall, facing in", () => {
        const pose = walkStartAtEntrance([], BUILDING);
        expect(close(pose.x, 30) && close(pose.y, 38.5)).toBe(true);
        expect(close(pose.yaw, -Math.PI / 2)).toBe(true);
    });

    test("eye height and walker size", () => {
        expect(EYE_HEIGHT).toBe(1.7);
        expect(RADIUS).toBe(0.3);
    });
});

describe("moving", () => {
    test("forward follows the heading, right is 90° clockwise on the plan", () => {
        const f = moveVector({ forward: true }, 0, 1);
        expect(close(f.dx, WALK_SPEED) && close(f.dy, 0)).toBe(true);
        const r = moveVector({ right: true }, 0, 1);
        expect(close(r.dx, 0) && close(r.dy, WALK_SPEED)).toBe(true);
        const up = moveVector({ forward: true }, -Math.PI / 2, 1);
        expect(close(up.dx, 0) && close(up.dy, -WALK_SPEED)).toBe(true);
    });

    test("diagonal is not faster; Shift is 2.5× faster", () => {
        const d = moveVector({ forward: true, right: true }, 0, 1);
        expect(close(Math.hypot(d.dx, d.dy), WALK_SPEED)).toBe(true);
        const run = moveVector({ forward: true, run: true }, 0, 1);
        expect(close(run.dx, WALK_SPEED * 2.5)).toBe(true);
    });

    test("opposite keys cancel out", () => {
        const v = moveVector({ forward: true, back: true }, 1.2, 1);
        expect(close(v.dx, 0) && close(v.dy, 0)).toBe(true);
    });
});

describe("collisions", () => {
    test("can't walk into a rack: stops one radius from its face", () => {
        const end = walkFor({ x: 7, y: 8, yaw: 0 }, { forward: true }, 3, [LONE]);
        expect(end.x <= 9.7 - RADIUS + 1e-6).toBe(true);
        expect(end.x > 9.7 - RADIUS - 0.05).toBe(true);
    });

    test("walking into a rack at an angle slides along it", () => {
        const end = walkFor({ x: 9.2, y: 8, yaw: Math.PI / 4 }, { forward: true }, 2, [LONE]);
        expect(end.x <= 9.7 - RADIUS + 1e-6).toBe(true);
        expect(end.y > 8 + 1).toBe(true); // kept moving along the face
    });

    test("can't squeeze into the 0.2 m gap between back-to-back rows", () => {
        const end = walkFor({ x: 10.9, y: 21, yaw: -Math.PI / 2 }, { forward: true }, 3, [P04, P05]);
        // 0.1 m from each rack's corner, the circle stops √(0.3² − 0.1²) past the rack ends: never in the gap.
        expect(end.y >= 19.9 + Math.sqrt(RADIUS ** 2 - 0.1 ** 2) - 1e-6).toBe(true);
        expect(end.y < 19.9 + RADIUS).toBe(true);
    });

    test("can't leave the building", () => {
        const end = walkFor({ x: 1, y: 30, yaw: Math.PI }, { forward: true }, 3, []);
        expect(close(end.x, RADIUS, 1e-6) || end.x >= RADIUS).toBe(true);
        expect(end.x < RADIUS + 0.05).toBe(true);
    });

    test("an open aisle is free to walk", () => {
        const end = walkFor({ x: 13.6, y: 2, yaw: Math.PI / 2 }, { forward: true }, 5, [P04, P05, P06]);
        expect(close(end.x, 13.6, 1e-9)).toBe(true);
        expect(close(end.y, 2 + 5 * WALK_SPEED, 1e-6)).toBe(true);
    });
});

describe("looking around", () => {
    // Drag-the-view, like Street View: the scene follows the mouse.
    test("dragging right turns the view left", () => {
        expect(look({ yaw: 0, pitch: 0 }, 100, 0).yaw < 0).toBe(true);
    });

    test("dragging up looks down", () => {
        expect(look({ yaw: 0, pitch: 0 }, 0, -100).pitch < 0).toBe(true);
    });

    test("pitch stops at about ±80°", () => {
        expect(close(look({ yaw: 0, pitch: 0 }, 0, 10000).pitch, 1.4)).toBe(true);
        expect(close(look({ yaw: 0, pitch: 0 }, 0, -10000).pitch, -1.4)).toBe(true);
    });
});
