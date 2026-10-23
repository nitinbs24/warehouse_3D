/**
 * Editing rules for the layout editor (plain data, unit-tested). The overlap and building rules
 * mirror the server's (warehouse.rack.row._check_layout) so problems show up while dragging;
 * the server stays the authority when saving.
 */
import { rowRect } from "@warehouse_3d/editor/geometry";

const EPS = 1e-6;
const EDITABLE = ["code", "kind", "x", "y", "bays", "bay_width", "depth", "levels", "level_height", "slots_per_level"];

// The handoff's template rows (docs/CLAUDE.md), used for rows added in the editor.
const TEMPLATE = {
    pallet: { bays: 7, bay_width: 2.7, depth: 1.1, levels: 5, level_height: 1.8, slots_per_level: 2 },
    shelf: { bays: 16, bay_width: 1.0, depth: 0.6, levels: 5, level_height: 0.4, slots_per_level: 1 },
};

/** Round to the 0.1 m grid (and never below 0). */
export function snap(value, step = 0.1) {
    return Math.max(0, Math.round(Math.round(value / step) * step * 100) / 100);
}

/** Strict overlap: rows that only touch (back to back) don't count. */
export function rowsOverlap(a, b) {
    const r = rowRect(a);
    const o = rowRect(b);
    return r.x < o.x + o.w - EPS && o.x < r.x + r.w - EPS && r.y < o.y + o.h - EPS && o.y < r.y + r.h - EPS;
}

function inside(row, building) {
    const r = rowRect(row);
    return r.x >= -EPS && r.y >= -EPS && r.x + r.w <= building.length + EPS && r.y + r.h <= building.width + EPS;
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

/** What Save must send: {create: [{tmp_id, vals}], write: [{id, vals}], delete: [ids]}. */
export function diffLayout(original, current) {
    const byId = new Map(original.map((r) => [r.id, r]));
    const keep = new Set(current.map((r) => r.id));
    const pick = (row, fields) => Object.fromEntries(fields.map((f) => [f, row[f]]));
    const diff = { create: [], write: [], delete: original.filter((r) => !keep.has(r.id)).map((r) => r.id) };
    for (const row of current) {
        const before = byId.get(row.id);
        if (!before) {
            diff.create.push({ tmp_id: row.id, vals: pick(row, EDITABLE) });
            continue;
        }
        const changed = EDITABLE.filter((f) => row[f] !== before[f]);
        if (changed.length) {
            diff.write.push({ id: row.id, vals: pick(row, changed) });
        }
    }
    return diff;
}
