import { describe, expect, test } from "@odoo/hoot";
import {
    aisleClearance,
    areaBox,
    floorGeometry,
    openSide,
    rackGeometry,
    rowLabelPosition,
    slotBox,
    toWorld,
} from "@warehouse_3d/view3d/layout";

// Numbers below come from the prototype (docs/warehaven-3d-prototype.html) for the same records.
const BUILDING = { length: 60, width: 40, height: 10 };
const P05 = { code: "P05", kind: "pallet", x: 9.7, y: 1.0, bays: 7, bay_width: 2.7, depth: 1.1,
    levels: 5, level_height: 1.8, slots_per_level: 2 };
const S04 = { code: "S04", kind: "shelf", x: 41.0, y: 2.0, bays: 16, bay_width: 1.0, depth: 0.6,
    levels: 5, level_height: 0.4, slots_per_level: 1 };

function expectBox(actual, expected) {
    expect(actual.length).toBe(6);
    actual.forEach((v, i) => expect(Math.abs(v - expected[i]) < 1e-9).toBe(true, {
        message: `component ${i}: got ${v}, expected ${expected[i]}`,
    }));
}

describe("toWorld", () => {
    test("centres the building on the origin", () => {
        expect(toWorld(BUILDING, 0, 0)).toEqual([-30, -20]);
        expect(toWorld(BUILDING, 60, 40)).toEqual([30, 20]);
        expect(toWorld({ length: 80, width: 50, height: 12 }, 40, 25)).toEqual([0, 0]);
    });
});

describe("rackGeometry", () => {
    test("pallet row P05: 16 uprights, 8 beams, no decks", () => {
        const g = rackGeometry(P05, BUILDING);
        expect(g.uprights.length).toBe(16); // (7 bays + 1) × 2 sides
        expect(g.beams.length).toBe(8); // 4 beam levels × 2 sides
        expect(g.decks.length).toBe(0);
        expect(g.topHeight).toBe(9);
    });

    test("pallet upright matches the prototype", () => {
        // First upright: x0 + ut/2, height H/2, z0; size ut × H × ut (ut = 0.1, H = 9).
        expectBox(rackGeometry(P05, BUILDING).uprights[0], [-20.3 + 0.05, 4.5, -19, 0.1, 9, 0.1]);
    });

    test("shelf row S04: 34 uprights, 5 decks, no beams", () => {
        const g = rackGeometry(S04, BUILDING);
        expect(g.uprights.length).toBe(34); // (16 + 1) × 2
        expect(g.decks.length).toBe(5);
        expect(g.beams.length).toBe(0);
        expect(Math.abs(g.topHeight - 2.1) < 1e-9).toBe(true);
    });
});

describe("slotBox", () => {
    test("pallet slot P05-03-2-A matches the prototype hit box", () => {
        // bay 3, level 2, position 1 (1-based, as stored on the location)
        const { box, base } = slotBox(P05, { bay: 3, level: 2, position: 1 }, BUILDING);
        expect(Math.abs(base - 1.86) < 1e-9).toBe(true);
        expectBox(box, [-19.75, 2.66, -12.925, 1.25, 1.6, 1.3]);
    });

    test("ground-level pallet slot sits on the floor", () => {
        expect(slotBox(P05, { bay: 1, level: 1, position: 2 }, BUILDING).base).toBe(0);
    });

    test("shelf bin S04-10-3 matches the prototype hit box", () => {
        const { box, base } = slotBox(S04, { bay: 10, level: 3, position: 1 }, BUILDING);
        expect(Math.abs(base - 0.9125) < 1e-9).toBe(true);
        expectBox(box, [11.3, 1.0925, -8.5, 0.62, 0.36, 0.96]);
    });
});

describe("floor and areas", () => {
    test("5 m grid over a 60 × 40 m floor has 13 + 9 lines", () => {
        const { gridLines, floor, curbs } = floorGeometry(BUILDING);
        expect(gridLines.length).toBe(22);
        expectBox(floor, [0, -0.05, 0, 60, 0.1, 40]);
        expect(curbs.length).toBe(4);
    });

    test("area box is a thin slab over its rectangle", () => {
        const receiving = { x: 0.5, y: 25, width: 19.5, depth: 13.5 };
        expectBox(areaBox(receiving, BUILDING), [-30 + 0.5 + 9.75, 0.012, 5 + 6.75, 19.5, 0.02, 13.5]);
    });
});

describe("rowLabelPosition", () => {
    test("label floats above the rack top, alternating ends", () => {
        const [x, y, z] = rowLabelPosition(P05, 0, BUILDING);
        expect(Math.abs(x - -19.75) < 1e-9).toBe(true);
        expect(Math.abs(y - 9.6) < 1e-9).toBe(true);
        expect(Math.abs(z - (-19 + 18.9 + 0.3)) < 1e-9).toBe(true); // far end for even index
        expect(Math.abs(rowLabelPosition(P05, 1, BUILDING)[2] - (-19 - 0.3)) < 1e-9).toBe(true);
    });
});

describe("openSide", () => {
    const row = (code, x) => ({ ...P05, code, x });

    test("a lone row is viewed from the -x side", () => {
        expect(openSide(P05, [P05])).toBe(-1);
    });

    test("back-to-back pair: each row is viewed from its own aisle", () => {
        const p05 = row("P05", 9.7);
        const p06 = row("P06", 11.0); // 0.2 m behind P05
        expect(openSide(p05, [p05, p06])).toBe(-1);
        expect(openSide(p06, [p05, p06])).toBe(1);
    });

    test("a row in another stretch of floor doesn't count as a neighbour", () => {
        const far = { ...P05, code: "P99", x: 11.0, y: 30 };
        expect(openSide(P05, [P05, far])).toBe(-1);
        const p06 = row("P06", 11.0);
        expect(openSide(p06, [p06, { ...P05, code: "P98", x: 9.7, y: 30 }])).toBe(-1);
    });
});

describe("aisleClearance", () => {
    // Handoff x-positions: P04 9.7 and P05 11.0 stand back to back; P06 at 15.1 is across a 3 m aisle.
    const p04 = { ...P05, code: "P04", x: 9.7 };
    const p05 = { ...P05, code: "P05", x: 11.0 };
    const p06 = { ...P05, code: "P06", x: 15.1 };

    test("free space in front of the open face, up to the next row", () => {
        expect(Math.abs(aisleClearance(p05, [p04, p05, p06], BUILDING, 1) - 3.0) < 1e-9).toBe(true);
    });

    test("up to the wall when nothing stands in front", () => {
        expect(Math.abs(aisleClearance(P05, [P05], BUILDING, -1) - 9.7) < 1e-9).toBe(true);
        expect(Math.abs(aisleClearance(P05, [P05], BUILDING, 1) - (60 - 10.8)) < 1e-9).toBe(true);
    });
});
