/**
 * 2D floor-plan maths for the layout editor (plain numbers, unit-tested).
 *
 * Plan coordinates are metres from the building corner, x to the right, y downwards — the same
 * orientation as the 3D view's "Top" camera. A view is {scale (px per metre), ox, oy (px)}:
 * screen = plan × scale + offset.
 */

export const MIN_SCALE = 1;
export const MAX_SCALE = 200;

/** Largest scale that shows the whole building inside the viewport, centred, with a margin. */
export function fitView(building, width, height, margin = 24) {
    const scale = Math.min((width - 2 * margin) / building.length, (height - 2 * margin) / building.width);
    return {
        scale,
        ox: (width - building.length * scale) / 2,
        oy: (height - building.width * scale) / 2,
    };
}

export function toScreen(view, x, y) {
    return [x * view.scale + view.ox, y * view.scale + view.oy];
}

export function toPlan(view, px, py) {
    return [(px - view.ox) / view.scale, (py - view.oy) / view.scale];
}

/** Zoom by ``factor`` around a screen point, which stays under the cursor. */
export function zoomAt(view, px, py, factor) {
    const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, view.scale * factor));
    const [x, y] = toPlan(view, px, py);
    return { scale, ox: px - x * scale, oy: py - y * scale };
}

export function pan(view, dx, dy) {
    return { scale: view.scale, ox: view.ox + dx, oy: view.oy + dy };
}

/** Rack row on the plan: depth runs along x, its bays along y. */
export function rowRect(row) {
    return { x: row.x, y: row.y, w: row.depth, h: row.bays * row.bay_width };
}

/** Layout area on the plan: width along x, depth along y. */
export function areaRect(area) {
    return { x: area.x, y: area.y, w: area.width, h: area.depth };
}

/** 1 m grid lines {x1, y1, x2, y2, major}; every 5th metre is major. */
export function gridLines(building) {
    const lines = [];
    for (let x = 0; x <= building.length + 1e-9; x++) {
        lines.push({ x1: x, y1: 0, x2: x, y2: building.width, major: x % 5 === 0 });
    }
    for (let y = 0; y <= building.width + 1e-9; y++) {
        lines.push({ x1: 0, y1: y, x2: building.length, y2: y, major: y % 5 === 0 });
    }
    return lines;
}

/** The slot "View in 3D" flies to: middle bay, ground level, first position. */
export function middleSlot(row) {
    return { bay: Math.ceil(row.bays / 2), level: 1, position: 1 };
}
