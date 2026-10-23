import { describe, expect, test } from "@odoo/hoot";
import {
    diffLayout,
    layoutProblems,
    newRow,
    nextCode,
    rowsOverlap,
    snap,
} from "@warehouse_3d/editor/layout_edit";

const BUILDING = { length: 60, width: 40, height: 10 };
const PALLET = { kind: "pallet", y: 1.0, bays: 7, bay_width: 2.7, depth: 1.1, levels: 5, level_height: 1.8,
    slots_per_level: 2 };
const P05 = { ...PALLET, id: 5, code: "P05", x: 9.7 };

describe("snap", () => {
    test("rounds to the nearest 0.1 m without floating-point noise", () => {
        expect(snap(9.74)).toBe(9.7);
        expect(snap(9.76)).toBe(9.8);
        expect(snap(0.1 + 0.2)).toBe(0.3);
        expect(snap(-0.04)).toBe(0); // never below the origin
    });
});

describe("rules mirror the server (T10)", () => {
    test("back to back (touching) is fine, 0.5 m into each other is an overlap", () => {
        expect(rowsOverlap(P05, { ...P05, id: 6, x: 10.8 })).toBe(false);
        expect(rowsOverlap(P05, { ...P05, id: 6, x: 10.2 })).toBe(true);
    });

    test("rows in different stretches of floor don't overlap", () => {
        expect(rowsOverlap(P05, { ...P05, id: 6, x: 10.2, y: 20 })).toBe(false);
    });

    test("problems name the other row, or the wall", () => {
        const rows = [P05, { ...P05, id: 6, code: "P06", x: 10.2 }, { ...P05, id: 7, code: "P07", x: 59.5 }];
        const problems = layoutProblems(rows, BUILDING);
        expect(problems[5]).toMatch(/P06/);
        expect(problems[6]).toMatch(/P05/);
        expect(problems[7]).toMatch(/outside/i);
        expect(Object.keys(layoutProblems([P05], BUILDING)).length).toBe(0);
    });

    test("touching the walls is inside", () => {
        expect(Object.keys(layoutProblems([{ ...P05, x: 60 - 1.1, y: 40 - 18.9 }], BUILDING)).length).toBe(0);
    });
});

describe("adding rows", () => {
    test("next code continues the kind's numbering", () => {
        expect(nextCode("pallet", [P05, { ...P05, code: "P14" }, { code: "S03", kind: "shelf" }])).toBe("P15");
        expect(nextCode("shelf", [P05])).toBe("S01");
    });

    test("a new pallet row has the template sizes and lands on free floor", () => {
        const row = newRow("pallet", [P05], BUILDING, -1);
        expect(row.id).toBe(-1);
        expect(row.code).toBe("P06");
        expect([row.bays, row.bay_width, row.depth, row.levels, row.level_height, row.slots_per_level])
            .toEqual([7, 2.7, 1.1, 5, 1.8, 2]);
        expect(Object.keys(layoutProblems([P05, row], BUILDING)).length).toBe(0);
    });

    test("a new shelf row has shelving sizes", () => {
        const row = newRow("shelf", [], BUILDING, -2);
        expect([row.code, row.bays, row.bay_width, row.depth, row.level_height, row.slots_per_level])
            .toEqual(["S01", 16, 1.0, 0.6, 0.4, 1]);
    });

    test("no free floor: no row", () => {
        const tiny = { length: 1, width: 1, height: 10 };
        expect(newRow("pallet", [], tiny, -1)).toBe(null);
    });
});

describe("diffLayout", () => {
    test("lists what to create, change and delete", () => {
        const original = [P05, { ...P05, id: 6, code: "P06", x: 20.5 }];
        const current = [{ ...P05, x: 10.2 }, { ...P05, id: -1, code: "P07", x: 30 }];
        const diff = diffLayout(original, current);
        expect(diff.write).toEqual([{ id: 5, vals: { x: 10.2 } }]);
        expect(diff.delete).toEqual([6]);
        expect(diff.create.length).toBe(1);
        expect(diff.create[0].tmp_id).toBe(-1);
        expect(diff.create[0].vals.code).toBe("P07");
        expect("id" in diff.create[0].vals).toBe(false);
    });

    test("no edits, nothing to save", () => {
        expect(diffLayout([P05], [{ ...P05 }])).toEqual({ create: [], write: [], delete: [] });
    });
});
