/**
 * Walk mode maths: where the walker starts, how keys move them, and how racks and walls stop them.
 * Plain numbers on the floor plan (metres from the building corner, x along the length, y along the
 * width), so it is unit-tested without Three.js. A pose is {x, y, yaw}: yaw is the heading on the
 * plan, 0 = towards +x, π/2 = towards +y.
 */
import { aisleClearance, openSide } from "@warehouse_3d/view3d/layout";

export const EYE_HEIGHT = 1.7; // metres
export const RADIUS = 0.3; // the walker is a circle this wide on the floor
export const WALK_SPEED = 1.4; // metres per second, an ordinary walking pace
export const RUN_FACTOR = 2.5; // with Shift
const MAX_STAND_OFF = 2.5;
const WALK_KEYS = {
    w: "forward", ArrowUp: "forward",
    s: "back", ArrowDown: "back",
    a: "left", ArrowLeft: "left",
    d: "right", ArrowRight: "right",
};

/** Stand in the aisle in front of a slot, mid-aisle (at most 2.5 m back), facing the rack. */
export function walkStartAtSlot(row, slot, rows, building) {
    const side = openSide(row, rows);
    const clearance = aisleClearance(row, rows, building, side);
    const standOff = Math.min(MAX_STAND_OFF, Math.max(RADIUS + 0.05, clearance / 2));
    const slotWidth = row.bay_width / row.slots_per_level;
    return {
        x: side < 0 ? row.x - standOff : row.x + row.depth + standOff,
        y: row.y + (slot.bay - 1) * row.bay_width + (slot.position - 0.5) * slotWidth,
        yaw: side < 0 ? 0 : Math.PI,
    };
}

/** No slot selected: stand on the first dock, looking at the middle of the hall; no docks: front wall. */
export function walkStartAtEntrance(areas, building) {
    const centre = { x: building.length / 2, y: building.width / 2 };
    const dock = areas.find((a) => a.kind === "dock");
    if (!dock) {
        return { x: centre.x, y: building.width - 1.5, yaw: -Math.PI / 2 };
    }
    const x = dock.x + dock.width / 2;
    const y = dock.y + dock.depth / 2;
    return { x, y, yaw: Math.atan2(centre.y - y, centre.x - x) };
}

/**
 * How far to move this frame. ``keys`` has forward/back/left/right/run flags; ``dt`` in seconds.
 * Right is 90° clockwise from forward on the plan (that's the camera's right in the 3D view).
 */
export function moveVector(keys, yaw, dt) {
    const f = (keys.forward ? 1 : 0) - (keys.back ? 1 : 0);
    const r = (keys.right ? 1 : 0) - (keys.left ? 1 : 0);
    let dx = f * Math.cos(yaw) - r * Math.sin(yaw);
    let dy = f * Math.sin(yaw) + r * Math.cos(yaw);
    const length = Math.hypot(dx, dy);
    if (!length) {
        return { dx: 0, dy: 0 };
    }
    const distance = WALK_SPEED * (keys.run ? RUN_FACTOR : 1) * dt;
    dx = (dx / length) * distance; // diagonal isn't faster
    dy = (dy / length) * distance;
    return { dx, dy };
}

/** Rack footprints the walker can't enter: {x0, y0, x1, y1} per row. */
export function rackObstacles(rows) {
    return rows.map((r) => ({ x0: r.x, y0: r.y, x1: r.x + r.depth, y1: r.y + r.bays * r.bay_width }));
}

function blocked(x, y, obstacles, building) {
    if (x < RADIUS || y < RADIUS || x > building.length - RADIUS || y > building.width - RADIUS) {
        return true;
    }
    return obstacles.some((o) => {
        // Distance from the walker's centre to the nearest point of the rectangle.
        const nx = Math.max(o.x0, Math.min(x, o.x1));
        const ny = Math.max(o.y0, Math.min(y, o.y1));
        return Math.hypot(x - nx, y - ny) < RADIUS - 1e-9;
    });
}

/**
 * Apply one frame's move. If the full move is blocked, try each axis on its own, so walking into a
 * rack at an angle slides along its face instead of stopping dead. Steps are split so no single
 * step is longer than the walker's radius (no tunnelling through a thin rack in a slow frame).
 */
export function stepWalker(pose, move, obstacles, building) {
    const steps = Math.max(1, Math.ceil(Math.hypot(move.dx, move.dy) / (RADIUS / 2)));
    let { x, y } = pose;
    for (let i = 0; i < steps; i++) {
        const dx = move.dx / steps;
        const dy = move.dy / steps;
        if (!blocked(x + dx, y + dy, obstacles, building)) {
            x += dx;
            y += dy;
        } else if (dx && !blocked(x + dx, y, obstacles, building)) {
            x += dx;
        } else if (dy && !blocked(x, y + dy, obstacles, building)) {
            y += dy;
        }
    }
    return { ...pose, x, y };
}

const LOOK_SPEED = 0.005; // radians per pixel dragged
const MAX_PITCH = 1.4; // about 80°

/**
 * Turn the head by a mouse drag of (dx, dy) pixels. Drag-the-view, like Street View: dragging
 * right turns the view left, dragging up looks down. (Changed after Nitin tried the opposite.)
 */
export function look(pose, dx, dy) {
    return {
        ...pose,
        yaw: pose.yaw - dx * LOOK_SPEED,
        pitch: Math.max(-MAX_PITCH, Math.min(MAX_PITCH, pose.pitch + dy * LOOK_SPEED)),
    };
}

/**
 * Apply one key event to the held keys. ``event`` = {type, key, shiftKey, typing}; ``typing`` is
 * true when the key went to an input (e.g. Find). Returns {keys, handled, exit}.
 * Presses while typing are ignored, but releases always count: hold W, click into Find, let go,
 * and the walker must still stop (CodeRabbit review).
 */
export function walkKey(keys, { type, key, shiftKey, typing }) {
    const down = type === "keydown";
    if (down && typing) {
        return { keys, handled: false, exit: false };
    }
    if (down && key === "Escape") {
        return { keys, handled: true, exit: true };
    }
    if (key === "Shift") {
        return { keys: { ...keys, run: down }, handled: false, exit: false };
    }
    const action = WALK_KEYS[key.length === 1 ? key.toLowerCase() : key];
    if (!action) {
        return { keys, handled: false, exit: false };
    }
    return { keys: { ...keys, [action]: down, run: shiftKey }, handled: true, exit: false };
}
