import { describe, expect, test } from "@odoo/hoot";
import {
    capacitySummary,
    fillBand,
    legendCounts,
    loadBox,
    mergeSlotUpdates,
    normalizeCode,
} from "@warehouse_3d/view3d/occupancy";

const BUILDING = { length: 60, width: 40, height: 10 };
const P05 = { id: 1, code: "P05", kind: "pallet", x: 9.7, y: 1.0, bays: 7, bay_width: 2.7, depth: 1.1,
    levels: 5, level_height: 1.8, slots_per_level: 2 };
const S04 = { id: 2, code: "S04", kind: "shelf", x: 41.0, y: 2.0, bays: 16, bay_width: 1.0, depth: 0.6,
    levels: 5, level_height: 0.4, slots_per_level: 1 };

function close(a, b) {
    return Math.abs(a - b) < 1e-9;
}

describe("fillBand", () => {
    test("green below 50 %, amber 50–90 %, red above 90 %", () => {
        expect(fillBand(0)).toBe("low");
        expect(fillBand(0.499)).toBe("low");
        expect(fillBand(0.5)).toBe("mid");
        expect(fillBand(0.9)).toBe("mid");
        expect(fillBand(0.901)).toBe("high");
        expect(fillBand(1.4)).toBe("high"); // over-full still red
    });

    test("unknown fill (product without dimensions)", () => {
        expect(fillBand(null)).toBe("nodims");
    });
});

describe("loadBox", () => {
    const slot = { bay: 3, level: 2, position: 1 };

    test("height is stored volume over the slot's floor area", () => {
        // floor area 1.1 × 1.35 = 1.485 m²; 1.32 m³ → 0.8889 m high, sitting on the beam at 1.86 m
        const box = loadBox(P05, slot, { used_m3: 1.32, fill: 0.49 }, BUILDING);
        expect(close(box[4], 1.32 / 1.485)).toBe(true);
        expect(close(box[1], 1.86 + box[4] / 2)).toBe(true);
        expect(close(box[0], -19.75)).toBe(true);
        expect(close(box[2], -12.925)).toBe(true);
    });

    test("height is capped at the slot's clear height", () => {
        const box = loadBox(P05, slot, { used_m3: 50, fill: 18.7 }, BUILDING);
        expect(close(box[4], 1.6)).toBe(true); // 1.8 m level − 0.2 m beam clearance
    });

    test("unknown volume draws a half-height box", () => {
        const box = loadBox(P05, slot, { used_m3: null, fill: null }, BUILDING);
        expect(close(box[4], 0.8)).toBe(true);
    });

    test("shelf bin sits on its deck", () => {
        const box = loadBox(S04, { bay: 10, level: 3, position: 1 }, { used_m3: 0.06, fill: 0.27 }, BUILDING);
        expect(close(box[4], 0.06 / 0.6)).toBe(true); // floor area 0.6 × 1.0
        expect(close(box[1], 0.9125 + box[4] / 2)).toBe(true);
    });
});

describe("normalizeCode", () => {
    test("trims and upper-cases what the user typed", () => {
        expect(normalizeCode("  p05-03-2-a ")).toBe("P05-03-2-A");
        expect(normalizeCode("")).toBe("");
    });
});

describe("capacity and legend", () => {
    const rows = [P05, S04];
    const slots = [
        { row_id: 1, stock: { fill: 0.4 } },
        { row_id: 1, stock: { fill: 0.95 } },
        { row_id: 1, stock: null },
        { row_id: 1, stock: { fill: null } },
        { row_id: 2, stock: { fill: 0.6 } },
        { row_id: 2, stock: null },
    ];

    test("totals, used and average known fill per kind", () => {
        const summary = capacitySummary(rows, slots);
        expect(summary.pallet.total).toBe(4);
        expect(summary.pallet.used).toBe(3);
        expect(close(summary.pallet.avgFill, (0.4 + 0.95) / 2)).toBe(true); // unknown fill left out
        expect(summary.shelf.total).toBe(2);
        expect(summary.shelf.used).toBe(1);
        expect(close(summary.shelf.avgFill, 0.6)).toBe(true);
        expect(summary.rows).toEqual({ pallet: 1, shelf: 1 });
    });

    test("no stock at all gives no average", () => {
        expect(capacitySummary(rows, [{ row_id: 1, stock: null }]).pallet.avgFill).toBe(null);
    });

    test("legend counts stocked slots per band", () => {
        expect(legendCounts(slots)).toEqual({ low: 1, mid: 1, high: 1, nodims: 1 });
    });
});

describe("mergeSlotUpdates", () => {
    test("replaces refetched slots and empties slots the server no longer returns", () => {
        const slots = [
            { location_id: 10, code: "A", stock: { fill: 0.4 } },
            { location_id: 11, code: "B", stock: { fill: 0.9 } },
            { location_id: 12, code: "C", stock: null },
        ];
        const index = new Map(slots.map((s, i) => [s.location_id, i]));
        const changed = mergeSlotUpdates(slots, index, [10, 11, 99], [{ location_id: 10, code: "A", stock: null }]);
        expect(slots[0].stock).toBe(null); // refetched
        expect(slots[1].stock).toBe(null); // asked for, not returned (archived): shown empty
        expect(slots[2].stock).toBe(null);
        expect(changed).toBe(2); // 99 belongs to another warehouse: ignored
    });
});
