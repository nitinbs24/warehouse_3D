/**
 * Stock in the 3D view, as plain numbers (unit-tested, no Three.js).
 * A slot's ``stock`` comes from stock.warehouse.wh3d_get_scene: {used_m3, fill, ...} or null.
 */
import { slotBox } from "@warehouse_3d/view3d/layout";

/** Occupancy band of a fill ratio: "low" < 50 % ≤ "mid" ≤ 90 % < "high"; null fill → "nodims". */
export function fillBand(fill) {
    if (fill === null || fill === undefined) {
        return "nodims";
    }
    if (fill < 0.5) {
        return "low";
    }
    return fill <= 0.9 ? "mid" : "high";
}

/**
 * One box for everything in a slot: the slot's footprint, as tall as the stored volume needs
 * (volume ÷ floor area), never taller than the slot. Unknown volume → half the slot's height.
 */
export function loadBox(row, slot, stock, building) {
    const { base, box } = slotBox(row, slot, building);
    const slotWidth = row.bay_width / row.slots_per_level;
    const maxHeight = box[4];
    const height = stock.used_m3 === null
        ? maxHeight / 2
        : Math.min(stock.used_m3 / (row.depth * slotWidth), maxHeight);
    const margin = row.kind === "pallet" ? 0.1 : 0.04;
    return [box[0], base + height / 2, box[2], row.depth - margin, height, slotWidth - margin];
}

export function normalizeCode(text) {
    return (text || "").trim().toUpperCase();
}

/** Per kind: slot count, stocked count, average of the known fills; plus rows per kind. */
export function capacitySummary(rows, slots) {
    const kindOf = Object.fromEntries(rows.map((r) => [r.id, r.kind]));
    const summary = { rows: { pallet: 0, shelf: 0 } };
    const fills = { pallet: [], shelf: [] };
    for (const kind of ["pallet", "shelf"]) {
        summary[kind] = { total: 0, used: 0, avgFill: null };
    }
    for (const row of rows) {
        summary.rows[row.kind]++;
    }
    for (const slot of slots) {
        const kind = kindOf[slot.row_id];
        summary[kind].total++;
        if (slot.stock) {
            summary[kind].used++;
            if (slot.stock.fill !== null) {
                fills[kind].push(slot.stock.fill);
            }
        }
    }
    for (const kind of ["pallet", "shelf"]) {
        const f = fills[kind];
        summary[kind].avgFill = f.length ? f.reduce((a, b) => a + b, 0) / f.length : null;
    }
    return summary;
}

/** Stocked slots per occupancy band, for the legend. */
export function legendCounts(slots) {
    const counts = { low: 0, mid: 0, high: 0, nodims: 0 };
    for (const slot of slots) {
        if (slot.stock) {
            counts[fillBand(slot.stock.fill)]++;
        }
    }
    return counts;
}

/**
 * Put refetched slot data into ``slots`` (the array the scene draws from). A slot that was asked
 * for but not returned is no longer an active slot (archived meanwhile): show it empty.
 * Ids not in ``indexByLocation`` belong to another warehouse and are ignored.
 * Returns how many of this view's slots were updated.
 */
export function mergeSlotUpdates(slots, indexByLocation, requestedIds, fresh) {
    const returned = new Map(fresh.map((s) => [s.location_id, s]));
    let changed = 0;
    for (const id of requestedIds) {
        const index = indexByLocation.get(id);
        if (index === undefined) {
            continue;
        }
        slots[index] = returned.get(id) || { ...slots[index], stock: null };
        changed++;
    }
    return changed;
}
