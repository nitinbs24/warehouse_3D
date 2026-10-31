/**
 * Editing rules for the layout editor (plain data, unit-tested). The overlap and building rules
 * mirror the server's (warehouse.rack.row._check_layout) so problems show up while dragging;
 * the server stays the authority when saving.
 */
import { areaRect, rowRect } from "@warehouse_3d/editor/geometry";

const EPS = 1e-6;
const EDITABLE = ["code", "kind", "x", "y", "bays", "bay_width", "depth", "levels", "level_height", "slots_per_level"];
const AREA_EDITABLE = ["name", "kind", "x", "y", "width", "depth", "color"];
const MIN_AREA_SIZE = 0.5; // metres, when resizing by dragging

// The handoff's template rows (docs/CLAUDE.md), used for rows added in the editor.
const TEMPLATE = {
    pallet: { bays: 7, bay_width: 2.7, depth: 1.1, levels: 5, level_height: 1.8, slots_per_level: 2 },
    shelf: { bays: 16, bay_width: 1.0, depth: 0.6, levels: 5, level_height: 0.4, slots_per_level: 1 },
};

/** Round to the 0.1 m grid (and never below 0). */
export function snap(value, step = 0.1) {
    return Math.max(0, Math.round(Math.round(value / step) * step * 100) / 100);
}

/** Strict overlap of two {x, y, w, h} rectangles: ones that only touch (back to back) don't count. */
function rectsOverlap(r, o) {
    return r.x < o.x + o.w - EPS && o.x < r.x + r.w - EPS && r.y < o.y + o.h - EPS && o.y < r.y + r.h - EPS;
}

export function rowsOverlap(a, b) {
    return rectsOverlap(rowRect(a), rowRect(b));
}

function insideRect(r, building) {
    return r.x >= -EPS && r.y >= -EPS && r.x + r.w <= building.length + EPS && r.y + r.h <= building.width + EPS;
}

function inside(row, building) {
    return insideRect(rowRect(row), building);
}

/** {row id: message} for every row that sticks out of the building or overlaps another. */
export function layoutProblems(rows, building) {
    const problems = {};
    for (const row of rows) {
        if (!inside(row, building)) {
            problems[row.id] = `${row.code} is outside the ${building.length} × ${building.width} m building.`;
            continue;
        }
        const other = rows.find((o) => o !== row && rowsOverlap(row, o));
        if (other) {
            problems[row.id] = `${row.code} overlaps ${other.code}.`;
        }
    }
    return problems;
}

/** Next free code for a kind: P + 2 digits for pallet racks, S for shelving. */
export function nextCode(kind, rows) {
    const prefix = kind === "pallet" ? "P" : "S";
    const used = rows.filter((r) => r.code?.startsWith(prefix)).map((r) => parseInt(r.code.slice(1), 10) || 0);
    return `${prefix}${String(Math.max(0, ...used) + 1).padStart(2, "0")}`;
}

/**
 * A new row of ``kind`` with the template sizes, placed on the first free spot of the floor
 * (scanning every 0.5 m), or null if it fits nowhere. ``tmpId`` (negative) marks it as unsaved.
 */
export function newRow(kind, rows, building, tmpId) {
    const row = { id: tmpId, code: nextCode(kind, rows), kind, x: 0, y: 0, ...TEMPLATE[kind] };
    for (let y = 0; y <= building.width; y += 0.5) {
        for (let x = 0; x <= building.length; x += 0.5) {
            Object.assign(row, { x: snap(x), y: snap(y) });
            if (inside(row, building) && !rows.some((o) => rowsOverlap(row, o))) {
                return row;
            }
        }
    }
    return null;
}

/** What Save must send for a list of records: {create: [{tmp_id, vals}], write: [{id, vals}], delete: [ids]}. */
function diffRecords(original, current, fields) {
    const byId = new Map(original.map((r) => [r.id, r]));
    const keep = new Set(current.map((r) => r.id));
    const pick = (row, names) => Object.fromEntries(names.map((f) => [f, row[f]]));
    const diff = { create: [], write: [], delete: original.filter((r) => !keep.has(r.id)).map((r) => r.id) };
    for (const row of current) {
        const before = byId.get(row.id);
        if (!before) {
            diff.create.push({ tmp_id: row.id, vals: pick(row, fields) });
            continue;
        }
        const changed = fields.filter((f) => row[f] !== before[f]);
        if (changed.length) {
            diff.write.push({ id: row.id, vals: pick(row, changed) });
        }
    }
    return diff;
}

export function diffLayout(original, current) {
    return diffRecords(original, current, EDITABLE);
}

export function diffAreas(original, current) {
    return diffRecords(original, current, AREA_EDITABLE);
}

// --- floor areas (receiving, packing, …): drawing only, no stock ---

/** The palette: common warehouse areas with a default colour and size (metres). Custom is last. */
export const AREA_TYPES = [
    { key: "receiving", label: "Receiving", color: "#8fb8de", width: 20, depth: 12 },
    { key: "putaway", label: "Put-away", color: "#9ecfc0", width: 12, depth: 10 },
    { key: "packing", label: "Packing", color: "#e8a79c", width: 10, depth: 8 },
    { key: "staging", label: "Dispatch staging", color: "#a8d5a2", width: 14, depth: 10 },
    { key: "charging", label: "Charging", color: "#f2d27a", width: 8, depth: 5 },
    { key: "office", label: "Office", color: "#c9c9c9", width: 8, depth: 6 },
    { key: "returns", label: "Returns", color: "#d4b3e6", width: 8, depth: 6 },
    { key: "quarantine", label: "Quarantine", color: "#f0b27a", width: 6, depth: 5 },
    { key: "custom", label: "Custom area", color: "#c3d0dc", width: 6, depth: 6 },
];

const round2 = (value) => Math.round(value * 100) / 100;

/** A new area of palette ``type`` centred on plan point ``[px, py]``, snapped and pulled inside the building. */
export function newArea(type, [px, py], building, tmpId) {
    const { width, depth } = type;
    return {
        id: tmpId, name: type.label, kind: "area", color: type.color, width, depth,
        x: round2(Math.max(0, Math.min(snap(px - width / 2), building.length - width))),
        y: round2(Math.max(0, Math.min(snap(py - depth / 2), building.width - depth))),
    };
}

/**
 * {id: message} for every area or dock door with no size or outside the building; a floor area on
 * top of a rack row; a dock door touching no wall. (Doors may stand in front of racks.)
 */
export function areaProblems(areas, rows, building) {
    const problems = {};
    for (const area of areas) {
        const r = areaRect(area);
        if (!(r.w > 0 && r.h > 0)) {
            problems[area.id] = `${area.name} has no size.`;
        } else if (!insideRect(r, building)) {
            problems[area.id] = `${area.name} is outside the ${building.length} × ${building.width} m building.`;
        } else if (area.kind === "dock") {
            const touches = Math.min(r.x, r.y, building.length - r.x - r.w, building.width - r.y - r.h) <= EPS;
            if (!touches) {
                problems[area.id] = `${area.name} must touch a wall.`;
            }
        } else {
            const row = rows.find((o) => rectsOverlap(r, rowRect(o)));
            if (row) {
                problems[area.id] = `${area.name} overlaps rack row ${row.code}.`;
            }
        }
    }
    return problems;
}

/**
 * The area's new {x, y, width, depth} when its ``edge`` ("n", "s", "e", "w" or a corner such as "se")
 * is dragged to plan point ``[px, py]``. Snapped to 0.1 m; the opposite edge stays put and the
 * area never gets thinner than MIN_AREA_SIZE.
 */
export function resizeArea(area, edge, [px, py]) {
    let { x, y, width, depth } = area;
    if (edge.includes("e")) {
        width = Math.max(MIN_AREA_SIZE, snap(px) - x);
    }
    if (edge.includes("w")) {
        const right = x + width;
        x = Math.min(snap(px), right - MIN_AREA_SIZE);
        width = right - x;
    }
    if (edge.includes("s")) {
        depth = Math.max(MIN_AREA_SIZE, snap(py) - y);
    }
    if (edge.includes("n")) {
        const bottom = y + depth;
        y = Math.min(snap(py), bottom - MIN_AREA_SIZE);
        depth = bottom - y;
    }
    return { x: round2(x), y: round2(y), width: round2(width), depth: round2(depth) };
}

// --- dock doors: always on a wall ---

const DOCK_THICKNESS = 1.6; // metres, across the wall
const DEFAULT_DOCK_OPENING = 3; // metres, along the wall
const MIN_DOCK_OPENING = 2; // above the thickness, so a door's centre is always nearer its own wall than a neighbour's
export const DOCK_COLOR = "#e3a22b";

/**
 * A door of ``opening`` metres on the wall nearest plan point ``[px, py]``: {x, y, width, depth} flush
 * on that wall, slid along it in 0.1 m steps and kept within the wall's ends. On the left and right
 * walls the opening runs along y, so width and depth swap.
 */
export function snapDockToWall([px, py], building, opening = DEFAULT_DOCK_OPENING) {
    const { length: L, width: W } = building;
    const distance = { front: py, back: W - py, left: px, right: L - px };
    const wall = Object.keys(distance).reduce((a, b) => (distance[b] < distance[a] ? b : a));
    const along = (centre, wallLength) => round2(Math.max(0, Math.min(snap(centre - opening / 2), wallLength - opening)));
    const T = DOCK_THICKNESS;
    switch (wall) {
        case "front":
            return { x: along(px, L), y: 0, width: opening, depth: T };
        case "back":
            return { x: along(px, L), y: round2(W - T), width: opening, depth: T };
        case "left":
            return { x: 0, y: along(py, W), width: T, depth: opening };
        default:
            return { x: round2(L - T), y: along(py, W), width: T, depth: opening };
    }
}

const dockOpening = (dock) => Math.max(dock.width, dock.depth);
const dockCentre = (dock) => [dock.x + dock.width / 2, dock.y + dock.depth / 2];

/** The door moved so its centre is at ``centre``: it jumps to whichever wall is nearest. */
export function moveDock(dock, centre, building) {
    return snapDockToWall(centre, building, dockOpening(dock));
}

/** The door with a new opening, on the same wall around the same centre (under 2 m: unchanged). */
export function setDockOpening(dock, opening, building) {
    if (!(opening >= MIN_DOCK_OPENING)) {
        return { x: dock.x, y: dock.y, width: dock.width, depth: dock.depth };
    }
    return snapDockToWall(dockCentre(dock), building, opening);
}

/** A new door dropped at plan point ``point``, named with the next free "Dock door N". */
export function newDock(point, building, tmpId, areas) {
    const used = areas.filter((a) => a.kind === "dock").map((a) => parseInt(/(\d+)$/.exec(a.name)?.[1] ?? 0, 10));
    return {
        id: tmpId, name: `Dock door ${Math.max(0, ...used) + 1}`, kind: "dock", color: DOCK_COLOR,
        ...snapDockToWall(point, building),
    };
}
