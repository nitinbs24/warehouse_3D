import { describe, expect, test } from "@odoo/hoot";
import {
    AREA_TYPES,
    areaProblems,
    diffAreas,
    diffLayout,
    GOODS_DEFAULTS,
    goodsInfo,
    rowZone,
    layoutProblems,
    newArea,
    newDock,
    newRow,
    nextCode,
    resizeArea,
    rowsOverlap,
    setDockOpening,
    snap,
    snapDockToWall,
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

    test("a rack taller than the clear height is a problem; touching the roof is not", () => {
        expect(layoutProblems([{ ...P05, levels: 6 }], BUILDING)[5]).toMatch(/clear height/); // 10.8 m > 10 m
        expect(Object.keys(layoutProblems([{ ...P05, level_height: 2.0 }], BUILDING)).length).toBe(0); // 10.0 m
    });

    test("shelving counts its 0.1 m base: 5 x 0.4 m is 2.1 m tall", () => {
        const shelf = { ...P05, kind: "shelf", slots_per_level: 1, levels: 5, level_height: 0.4 };
        expect(layoutProblems([shelf], { ...BUILDING, height: 2.0 })[5]).toMatch(/clear height/);
        expect(Object.keys(layoutProblems([shelf], { ...BUILDING, height: 2.1 })).length).toBe(0);
        expect(Object.keys(layoutProblems([{ ...P05, levels: 5, level_height: 0.4 }], { ...BUILDING, height: 2.0 })).length).toBe(0); // a pallet row has no base
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

describe("special-goods fields (T24)", () => {
    const P05G = { ...P05, ...GOODS_DEFAULTS };

    test("a new row starts ambient, normal, green, no hazards", () => {
        const row = newRow("pallet", [], BUILDING, -1);
        expect([row.temp_band, row.purpose, row.inspection_status, row.hazard_toxic, row.last_inspection])
            .toEqual(["ambient", "normal", "green", false, false]);
    });

    test("a preset sends only the band: the server fills the range", () => {
        const changed = { ...P05G, temp_band: "frozen", hazard_gas: true };
        expect(diffLayout([P05G], [changed]).write).toEqual([{ id: 5, vals: { temp_band: "frozen", hazard_gas: true } }]);
        const created = diffLayout([], [{ ...changed, id: -1 }]).create[0].vals;
        expect("temp_min" in created || "temp_max" in created).toBe(false);
    });

    test("a custom range keeps negative temperatures", () => {
        const changed = { ...P05G, temp_band: "custom", temp_min: -30, temp_max: -20 };
        expect(diffLayout([P05G], [changed]).write[0].vals).toEqual({ temp_band: "custom", temp_min: -30, temp_max: -20 });
    });

    test("the 3D panel describes what a row offers", () => {
        expect(goodsInfo(P05G)).toEqual({ temperature: "Ambient (uncontrolled)", purpose: "Normal", hazards: "None",
            inspection: "Green - OK", inspectionStatus: "green" });
        const cold = goodsInfo({ ...P05G, temp_band: "custom", temp_min: -30, temp_max: -20, hazard_toxic: true,
            hazard_gas: true, inspection_status: "red", last_inspection: "2026-11-01" });
        expect([cold.temperature, cold.hazards, cold.inspection])
            .toEqual(["-30 to -20 °C", "Compressed gas, Toxic", "Red - offload now (2026-11-01)"]);
    });

    test("a row's zone colour: purpose first, then temperature, then hazards", () => {
        expect(rowZone(P05G)).toBe(null);
        expect(rowZone({ ...P05G, temp_band: "frozen" })).toBe("cold");
        expect(rowZone({ ...P05G, hazard_toxic: true })).toBe("hazard");
        expect(rowZone({ ...P05G, purpose: "returns", temp_band: "chilled" })).toBe("quarantine");
        expect(rowZone({ ...P05G, inspection_status: "amber" })).toBe(null); // inspection is an outline, not a zone
    });

    test("an inspection date and status are sent as they are", () => {
        const changed = { ...P05G, inspection_status: "amber", last_inspection: "2026-11-01" };
        expect(diffLayout([P05G], [changed]).write[0].vals).toEqual({ inspection_status: "amber", last_inspection: "2026-11-01" });
    });
});

const RECEIVING = { id: 1, name: "Receiving", kind: "area", x: 25, y: 25, width: 5, depth: 5, color: "#c3d0dc", role: "both" };

describe("area palette", () => {
    test("every type has a name, a #rrggbb colour and a positive default size; Custom is last", () => {
        expect(AREA_TYPES.length).toBeGreaterThan(5);
        for (const type of AREA_TYPES) {
            expect(type.color).toMatch(/^#[0-9a-f]{6}$/i);
            expect(type.width > 0 && type.depth > 0).toBe(true);
        }
        expect(AREA_TYPES.at(-1).key).toBe("custom");
        expect(new Set(AREA_TYPES.map((t) => t.key)).size).toBe(AREA_TYPES.length);
    });
});

describe("newArea", () => {
    const packing = AREA_TYPES.find((t) => t.key === "packing");

    test("is centred on the drop point, snapped, with the type's name, colour and size", () => {
        const area = newArea(packing, [30.04, 20.02], BUILDING, -1);
        expect([area.id, area.name, area.kind, area.color]).toEqual([-1, packing.label, "area", packing.color]);
        expect([area.width, area.depth]).toEqual([packing.width, packing.depth]);
        expect(area.x).toBe(snap(30.04 - packing.width / 2));
        expect(area.y).toBe(snap(20.02 - packing.depth / 2));
    });

    test("a drop near a wall is pulled back inside the building", () => {
        const area = newArea(packing, [-5, 100], BUILDING, -2);
        expect(area.x).toBe(0);
        expect(area.y).toBe(snap(BUILDING.width - packing.depth));
        expect(Object.keys(areaProblems([area], [], BUILDING)).length).toBe(0);
    });
});

describe("areaProblems", () => {
    test("an area inside the building, clear of rows, is fine; touching a row is fine", () => {
        expect(Object.keys(areaProblems([RECEIVING], [P05], BUILDING)).length).toBe(0);
        expect(Object.keys(areaProblems([{ ...RECEIVING, x: 10.8, y: 5 }], [P05], BUILDING)).length).toBe(0);
    });

    test("overlapping a row names the area and the row", () => {
        const problems = areaProblems([{ ...RECEIVING, x: 10, y: 5 }], [P05], BUILDING);
        expect(problems[1]).toMatch(/Receiving/);
        expect(problems[1]).toMatch(/P05/);
    });

    test("sticking out of the building is a problem", () => {
        expect(areaProblems([{ ...RECEIVING, x: 58 }], [], BUILDING)[1]).toMatch(/outside/i);
    });

    test("areas may overlap each other", () => {
        const staging = { ...RECEIVING, id: 2, name: "Staging", x: 26, y: 26, width: 2, depth: 2 };
        expect(Object.keys(areaProblems([RECEIVING, staging], [], BUILDING)).length).toBe(0);
    });

    test("a zero-size area is a problem", () => {
        expect(areaProblems([{ ...RECEIVING, width: 0 }], [], BUILDING)[1]).toMatch(/size/i);
    });
});

describe("resizeArea", () => {
    test("dragging the east edge changes only the width, snapped", () => {
        expect(resizeArea(RECEIVING, "e", [33.04, 99])).toEqual({ x: 25, y: 25, width: 8, depth: 5 });
    });

    test("dragging the west edge moves x and keeps the east edge in place", () => {
        expect(resizeArea(RECEIVING, "w", [23, 0])).toEqual({ x: 23, y: 25, width: 7, depth: 5 });
    });

    test("north and south work the same way along y", () => {
        expect(resizeArea(RECEIVING, "n", [0, 22])).toEqual({ x: 25, y: 22, width: 5, depth: 8 });
        expect(resizeArea(RECEIVING, "s", [0, 28.96])).toEqual({ x: 25, y: 25, width: 5, depth: 4 });
    });

    test("a corner changes both sides", () => {
        expect(resizeArea(RECEIVING, "se", [32, 29])).toEqual({ x: 25, y: 25, width: 7, depth: 4 });
        expect(resizeArea(RECEIVING, "nw", [24, 24])).toEqual({ x: 24, y: 24, width: 6, depth: 6 });
    });

    test("it can't shrink below 0.5 m or flip over the opposite edge", () => {
        expect(resizeArea(RECEIVING, "e", [10, 0]).width).toBe(0.5);
        expect(resizeArea(RECEIVING, "w", [40, 0])).toEqual({ x: 29.5, y: 25, width: 0.5, depth: 5 });
    });
});

describe("diffAreas", () => {
    test("lists what to create, change and delete", () => {
        const original = [RECEIVING, { ...RECEIVING, id: 2, name: "Office" }];
        const current = [{ ...RECEIVING, x: 26, color: "#112233" }, { ...RECEIVING, id: -1, name: "Packing" }];
        const diff = diffAreas(original, current);
        expect(diff.write).toEqual([{ id: 1, vals: { x: 26, color: "#112233" } }]);
        expect(diff.delete).toEqual([2]);
        expect(diff.create.length).toBe(1);
        expect(diff.create[0].tmp_id).toBe(-1);
        expect(diff.create[0].vals).toEqual({ name: "Packing", kind: "area", x: 25, y: 25, width: 5, depth: 5,
            color: "#c3d0dc", role: "both" });
    });

    test("no edits, nothing to save", () => {
        expect(diffAreas([RECEIVING], [{ ...RECEIVING }])).toEqual({ create: [], write: [], delete: [] });
    });
});

const DOCK = { id: 7, name: "Dock door 1", kind: "dock", x: 18.5, y: 0, width: 3, depth: 1.6, color: "#e3a22b", role: "both" };

describe("snapDockToWall", () => {
    test("a point near each wall puts the door flush on that wall (opening 3 m, thickness 1.6 m)", () => {
        expect(snapDockToWall([20, 0.3], BUILDING, 3)).toEqual({ x: 18.5, y: 0, width: 3, depth: 1.6 });
        expect(snapDockToWall([20, 39.9], BUILDING, 3)).toEqual({ x: 18.5, y: 38.4, width: 3, depth: 1.6 });
        expect(snapDockToWall([0.2, 15], BUILDING, 3)).toEqual({ x: 0, y: 13.5, width: 1.6, depth: 3 });
        expect(snapDockToWall([59.9, 15], BUILDING, 3)).toEqual({ x: 58.4, y: 13.5, width: 1.6, depth: 3 });
    });

    test("the nearest wall wins, so a door dragged across the floor changes walls", () => {
        expect(snapDockToWall([5, 10], BUILDING, 3).x).toBe(0); // 5 m from the left wall, 10 from the front
        expect(snapDockToWall([30, 3], BUILDING, 3).y).toBe(0);
    });

    test("it slides along the wall in 0.1 m steps and never past the wall's ends", () => {
        expect(snapDockToWall([20.04, 0], BUILDING, 3).x).toBe(18.5);
        expect(snapDockToWall([0.5, 0], BUILDING, 3).x).toBe(0);
        expect(snapDockToWall([59.9, 0], BUILDING, 3).x).toBe(57);
        expect(snapDockToWall([0, 39], BUILDING, 3).y).toBe(37);
    });

    test("the result always touches a wall and stays inside the building", () => {
        for (const point of [[0, 0], [60, 40], [30, 20], [-5, 50], [12.34, 5.67]]) {
            const d = { id: 1, name: "D", kind: "dock", ...snapDockToWall(point, BUILDING, 3) };
            expect(Object.keys(areaProblems([d], [], BUILDING)).length).toBe(0);
        }
    });
});

describe("docks", () => {
    test("newDock is a 3 m door on the wall nearest the drop, named with the next free number", () => {
        const dock = newDock([20, 0], BUILDING, -3, [DOCK, { ...DOCK, id: 8, name: "Dock door 4" }]);
        expect([dock.id, dock.name, dock.kind, dock.color]).toEqual([-3, "Dock door 5", "dock", "#e3a22b"]);
        expect([dock.y, dock.width, dock.depth]).toEqual([0, 3, 1.6]);
        expect(newDock([20, 0], BUILDING, -4, []).name).toBe("Dock door 1");
    });

    test("setDockOpening keeps the door's centre and its wall", () => {
        expect(setDockOpening(DOCK, 5, BUILDING)).toEqual({ x: 17.5, y: 0, width: 5, depth: 1.6 });
        const side = { ...DOCK, x: 0, y: 13.5, width: 1.6, depth: 3 };
        expect(setDockOpening(side, 5, BUILDING)).toEqual({ x: 0, y: 12.5, width: 1.6, depth: 5 });
    });

    test("an opening under 2 m is refused (the door would no longer find its own wall)", () => {
        expect(setDockOpening(DOCK, 1, BUILDING)).toEqual({ x: 18.5, y: 0, width: 3, depth: 1.6 });
    });

    test("a door must touch a wall; it may sit in front of racks; outside is still outside", () => {
        expect(areaProblems([{ ...DOCK, y: 10 }], [], BUILDING)[7]).toMatch(/wall/);
        expect(Object.keys(areaProblems([{ ...DOCK, x: 9.7, y: 0, width: 3, depth: 1.6 }], [P05], BUILDING)).length).toBe(0);
        expect(areaProblems([{ ...DOCK, x: 58.5 }], [], BUILDING)[7]).toMatch(/outside/);
        expect(Object.keys(areaProblems([DOCK], [], BUILDING)).length).toBe(0);
    });

    test("a new door is used both ways until told otherwise; a role change is sent (T26)", () => {
        const dock = newDock([30, 0.5], BUILDING, -1, []);
        expect(dock.role).toBe("both");
        expect(diffAreas([DOCK], [{ ...DOCK, role: "outbound" }]).write).toEqual([{ id: 7, vals: { role: "outbound" } }]);
    });

    test("diffAreas sends a moved door's position and size", () => {
        const moved = { ...DOCK, ...snapDockToWall([0.2, 15], BUILDING, 3) };
        expect(diffAreas([DOCK], [moved]).write).toEqual([{ id: 7, vals: { x: 0, y: 13.5, width: 1.6, depth: 3 } }]);
    });
});
