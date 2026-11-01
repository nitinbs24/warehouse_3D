import { Component } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";

// One key for both screens: the 3D view and the editor open the warehouse you looked at last.
const STORAGE_KEY = "warehouse_3d.warehouse_id";

/**
 * The warehouse to open: the one in the action context (the buttons on the warehouse form), else the
 * remembered one if it is still in ``warehouses`` (not archived, not another company's), else the default.
 */
export function pickWarehouseId({ contextId, storedId, warehouses, defaultId }) {
    if (contextId) {
        return contextId;
    }
    return warehouses.some((w) => w.id === storedId) ? storedId : defaultId;
}

/** The remembered warehouse id, or null. Storage can be blocked (private window): never throws. */
export function readStoredWarehouseId() {
    try {
        const id = parseInt(browser.localStorage.getItem(STORAGE_KEY), 10);
        return Number.isFinite(id) ? id : null;
    } catch {
        return null;
    }
}

export function storeWarehouseId(id) {
    try {
        browser.localStorage.setItem(STORAGE_KEY, String(id));
    } catch {
        // the choice just isn't remembered
    }
}

/**
 * Dropdown of warehouses, only shown when there is more than one. ``onChange(id)`` must return (a promise of)
 * true when the screen switched; on false (e.g. the user cancelled a discard dialog) the dropdown snaps back.
 */
export class WarehousePicker extends Component {
    static template = "warehouse_3d.WarehousePicker";
    static props = { warehouses: Array, value: Number, onChange: Function };

    async onSelect(ev) {
        const select = ev.target;
        if (!(await this.props.onChange(parseInt(select.value, 10)))) {
            select.value = String(this.props.value);
        }
    }
}
