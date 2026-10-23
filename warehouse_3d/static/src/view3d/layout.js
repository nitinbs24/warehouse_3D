/**
 * Warehouse geometry as plain numbers: no Three.js, no DOM, so it can be unit-tested.
 * Ported from docs/warehaven-3d-prototype.html.
 *
 * Floor plan: metres from one building corner, x along the length, y along the width.
 * World (Three.js): the building is centred on the origin, x → x, plan y → z, height → y.
 * A "box" is [centreX, centreY, centreZ, sizeX, sizeY, sizeZ] in world units.
 * Rack rows run along plan y: depth along x, bays along y.
 */

export function toWorld(building, x, y) {
    return [x - building.length / 2, y - building.width / 2];
}

/** Floor slab, 5 m grid lines ([x1, z1, x2, z2] at floor height) and the four kerbs. */
export function floorGeometry(building) {
    const { length: L, width: W } = building;
    const gridLines = [];
    for (let x = 0; x <= L + 1e-9; x += 5) {
        gridLines.push([x - L / 2, -W / 2, x - L / 2, W / 2]);
    }
    for (let y = 0; y <= W + 1e-9; y += 5) {
        gridLines.push([-L / 2, y - W / 2, L / 2, y - W / 2]);
    }
    const curbs = [
        [0, 0.2, -W / 2 - 0.1, L + 0.4, 0.4, 0.2],
        [0, 0.2, W / 2 + 0.1, L + 0.4, 0.4, 0.2],
        [-L / 2 - 0.1, 0.2, 0, 0.2, 0.4, W + 0.4],
        [L / 2 + 0.1, 0.2, 0, 0.2, 0.4, W + 0.4],
    ];
    return { floor: [0, -0.05, 0, L, 0.1, W], gridLines, curbs };
}

/** Thin coloured slab marking a floor area. */
export function areaBox(area, building) {
    const [cx, cz] = toWorld(building, area.x + area.width / 2, area.y + area.depth / 2);
    return [cx, 0.012, cz, area.width, 0.02, area.depth];
}

/** Dock pad on the floor, plus a door frame when the dock touches a long wall. */
export function dockGeometry(dock, building) {
    const [cx, cz] = toWorld(building, dock.x + dock.width / 2, dock.y + dock.depth / 2);
    const pad = [cx, 0.03, cz, dock.width, 0.06, dock.depth];
    const W = building.width;
    let wallZ = null;
    if (dock.y + dock.depth >= W - 0.01) {
        wallZ = W / 2 + 0.1;
    } else if (dock.y <= 0.01) {
        wallZ = -W / 2 - 0.1;
    }
    const frame = wallZ === null ? [] : [
        [cx - dock.width / 2 - 0.1, 1.8, wallZ, 0.15, 3.6, 0.15],
        [cx + dock.width / 2 + 0.1, 1.8, wallZ, 0.15, 3.6, 0.15],
        [cx, 3.6, wallZ, dock.width + 0.35, 0.2, 0.15],
    ];
    return { pad, frame };
}

/** Steel of one rack row: uprights, beams (pallet racks) or shelf decks (shelving). */
export function rackGeometry(row, building) {
    const [x0, z0] = toWorld(building, row.x, row.y);
    const length = row.bays * row.bay_width;
    const isPallet = row.kind === "pallet";
    const height = row.levels * row.level_height;
    const ut = isPallet ? 0.1 : 0.04; // upright thickness
    const topHeight = isPallet ? height : height + 0.1;
    const uprights = [];
    for (let b = 0; b <= row.bays; b++) {
        const z = z0 + b * row.bay_width;
        for (const xs of [x0 + ut / 2, x0 + row.depth - ut / 2]) {
            uprights.push([xs, topHeight / 2, z, ut, topHeight, ut]);
        }
    }
    const beams = [];
    const decks = [];
    if (isPallet) {
        for (let l = 1; l < row.levels; l++) {
            for (const xs of [x0 + 0.04, x0 + row.depth - 0.04]) {
                beams.push([xs, l * row.level_height, z0 + length / 2, 0.07, 0.12, length]);
            }
        }
    } else {
        for (let l = 0; l < row.levels; l++) {
            decks.push([x0 + row.depth / 2, 0.1 + l * row.level_height, z0 + length / 2, row.depth, 0.025, length]);
        }
    }
    return { uprights, beams, decks, topHeight };
}

/**
 * The space one slot occupies (used for click targets and, in T8, stock boxes).
 * ``slot.bay``, ``slot.level`` and ``slot.position`` are 1-based, as stored on the location.
 * ``base`` is the height of the slot's floor (beam top or shelf deck).
 */
export function slotBox(row, slot, building) {
    const [x0, z0] = toWorld(building, row.x, row.y);
    const b = slot.bay - 1;
    const l = slot.level - 1;
    const p = slot.position - 1;
    const slotWidth = row.bay_width / row.slots_per_level;
    const xc = x0 + row.depth / 2;
    const zc = z0 + b * row.bay_width + (p + 0.5) * slotWidth;
    if (row.kind === "pallet") {
        const base = l === 0 ? 0 : l * row.level_height + 0.06;
        const h = row.level_height - 0.2;
        return { base, box: [xc, base + h / 2, zc, row.depth + 0.15, h, slotWidth - 0.05] };
    }
    const base = 0.1 + l * row.level_height + 0.0125;
    const h = row.level_height - 0.04;
    return { base, box: [xc, base + h / 2, zc, row.depth + 0.02, h, slotWidth - 0.04] };
}

/** Where a row's code label floats: above the rack, at alternating ends so neighbours don't overlap. */
export function rowLabelPosition(row, index, building) {
    const [x0, z0] = toWorld(building, row.x, row.y);
    const { topHeight } = rackGeometry(row, building);
    const isPallet = row.kind === "pallet";
    const length = row.bays * row.bay_width;
    const z = index % 2 === 0 ? z0 + length + 0.3 : z0 - 0.3;
    return [x0 + row.depth / 2, topHeight + (isPallet ? 0.6 : 0.3), z];
}

/** Camera position and target for the "3D" and "Top" buttons, fitted to the building and view aspect. */
export function cameraView(mode, building, fovDeg, aspect) {
    const { length: L, width: W } = building;
    const tan = Math.tan((fovDeg * Math.PI) / 360);
    const a = aspect || 1.5;
    if (mode === "top") {
        const halfH = Math.max(W * 0.6, (L * 0.533) / a);
        return { position: [0, (halfH / tan) * 1.04, 0.01], target: [0, 0, 1.5] };
    }
    const d = Math.max(L * 1.1, ((L * 1.033) / a) * 1.15);
    const dir = [-0.55, 0.56, 0.62];
    const n = Math.hypot(...dir);
    return { position: dir.map((c) => (c / n) * d), target: [0, 1, W * 0.0625] };
}

/**
 * Which side of a row faces an aisle: -1 (towards -x) or +1. A row with a back-to-back partner
 * less than 1 m away on one side is looked at from the other; a lone row from -x.
 */
export function openSide(row, rows) {
    const yEnd = row.y + row.bays * row.bay_width;
    const partnerOnMinus = rows.some((r) => {
        const gap = row.x - (r.x + r.depth); // free space between r's back and this row's front
        const sameStretch = r.y < yEnd && row.y < r.y + r.bays * r.bay_width;
        return r.code !== row.code && sameStretch && gap >= -1e-9 && gap < 1;
    });
    return partnerOnMinus ? 1 : -1;
}

/** Free floor in front of a row's face on ``side`` (-1 / +1): up to the next row in the same stretch, or the wall. */
export function aisleClearance(row, rows, building, side) {
    const yEnd = row.y + row.bays * row.bay_width;
    let clearance = side < 0 ? row.x : building.length - (row.x + row.depth);
    for (const r of rows) {
        if (r.code === row.code || !(r.y < yEnd && row.y < r.y + r.bays * r.bay_width)) {
            continue;
        }
        const gap = side < 0 ? row.x - (r.x + r.depth) : r.x - (row.x + row.depth);
        if (gap >= -1e-9) {
            clearance = Math.min(clearance, gap);
        }
    }
    return clearance;
}
