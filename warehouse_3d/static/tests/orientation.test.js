import { describe, expect, test } from "@odoo/hoot";
import { rowRect } from "@warehouse_3d/editor/geometry";
import { layoutProblems, newRow, rotateRow } from "@warehouse_3d/editor/layout_edit";
import { rackGeometry, rowLabelPosition, slotBox } from "@warehouse_3d/view3d/layout";
import { loadBox } from "@warehouse_3d/view3d/occupancy";
import { rackObstacles, walkStartAtSlot } from "@warehouse_3d/view3d/walk";

// T31: a row along x is a row along y with the plan's x and y swapped.
const BUILDING = { length: 60, width: 40, height: 10 };
const PALLET = { kind: "pallet", bays: 2, bay_width: 2.7, depth: 1.1, levels: 5, level_height: 1.8, slots_per_level: 2 };
const XROW = { ...PALLET, id: 1, code: "P01", x: 10, y: 5, orientation: "x" };   // x 10–15.4, y 5–6.1
const YROW = { ...PALLET, id: 2, code: "P02", x: 10, y: 5, orientation: "y" };   // x 10–11.1, y 5–10.4
const close = (a, b) => expect(Math.abs(a - b) < 1e-9).toBe(true);

describe("rack orientation (T31)", () => {
    test("the plan rectangle follows the orientation; no orientation means along y", () => {
        expect(rowRect(XROW)).toEqual({ x: 10, y: 5, w: 5.4, h: 1.1 });
        expect(rowRect(YROW)).toEqual({ x: 10, y: 5, w: 1.1, h: 5.4 });
        const { orientation, ...legacy } = YROW;
        expect(rowRect(legacy)).toEqual(rowRect(YROW));
    });

    test("rotating keeps the corner and turns the row; a new row runs along y", () => {
        expect(rotateRow(YROW)).toEqual({ orientation: "x" });
        expect(rotateRow(XROW)).toEqual({ orientation: "y" });
        expect(newRow("pallet", [], BUILDING, -1).orientation).toBe("y");
    });

    test("an x row is checked against the walls and other rows", () => {
        expect(layoutProblems([{ ...XROW, x: 56 }], BUILDING)[1]).toMatch(/outside/);
        const crossing = { ...YROW, x: 12, y: 3 }; // x 12–13.1, y 3–8.4: through the x row
        expect(layoutProblems([XROW, crossing], BUILDING)[1]).toMatch(/P02/);
        expect(Object.keys(layoutProblems([XROW, YROW], BUILDING))).toEqual(["1", "2"]);
    });

    test("3D steel: uprights stand across the row's depth along z, beams run along x", () => {
        const { uprights, beams } = rackGeometry(XROW, BUILDING);
        // First upright at the row's start (x 10 → world -20), on the near face (y 5 + half an upright → z -14.95).
        close(uprights[0][0], -20);
        close(uprights[0][2], -14.95);
        // A beam spans the row's length along x; its 7 cm thickness is now along z.
        close(beams[0][3], 5.4);
        close(beams[0][5], 0.07);
    });

    test("3D slot and load boxes sit along x, position A first", () => {
        const a = slotBox(XROW, { bay: 2, level: 1, position: 1 }, BUILDING).box;
        const b = slotBox(XROW, { bay: 2, level: 1, position: 2 }, BUILDING).box;
        close(a[0], 10 + 2.7 + 0.675 - 30); // along the row
        close(a[2], 5 + 0.55 - 20);         // centre of the depth
        expect(b[0] > a[0]).toBe(true);
        const load = loadBox(XROW, { bay: 1, level: 1, position: 1 }, { used_m3: null }, BUILDING);
        close(load[5], 1.1 - 0.1);          // the load's depth now runs along z
    });

    test("the row label floats above one end of the row", () => {
        const [x, , z] = rowLabelPosition(XROW, 0, BUILDING);
        close(z, 5 + 0.55 - 20);
        expect(x > 10 + 5.4 - 30).toBe(true);
    });

    test("walk mode: stand in front of the face, facing it; the rack blocks its own footprint", () => {
        const pose = walkStartAtSlot(XROW, { bay: 1, position: 1 }, [XROW], BUILDING);
        close(pose.x, 10 + 0.675);
        expect(pose.y < 5).toBe(true);       // a lone row is looked at from its lower side
        close(pose.yaw, Math.PI / 2);        // facing +y, towards the rack
        expect(rackObstacles([XROW])).toEqual([{ x0: 10, y0: 5, x1: 15.4, y1: 6.1 }]);
    });
});
