import { describe, expect, test } from "@odoo/hoot";
import { browser } from "@web/core/browser/browser";
import { pickWarehouseId, readStoredWarehouseId, storeWarehouseId } from "@warehouse_3d/common/warehouse_picker";

const WAREHOUSES = [{ id: 1, name: "A" }, { id: 3, name: "B" }, { id: 7, name: "C" }];

describe("pickWarehouseId", () => {
    test("an id from the action context wins over everything (the buttons on the warehouse form)", () => {
        expect(pickWarehouseId({ contextId: 7, storedId: 3, warehouses: WAREHOUSES, defaultId: 1 })).toBe(7);
    });

    test("without a context id the stored choice is used", () => {
        expect(pickWarehouseId({ contextId: undefined, storedId: 3, warehouses: WAREHOUSES, defaultId: 1 })).toBe(3);
    });

    test("a stored id that is no longer in the list (archived, other company) falls back to the default", () => {
        expect(pickWarehouseId({ contextId: undefined, storedId: 99, warehouses: WAREHOUSES, defaultId: 1 })).toBe(1);
    });

    test("nothing chosen, nothing stored: the default", () => {
        expect(pickWarehouseId({ contextId: undefined, storedId: null, warehouses: WAREHOUSES, defaultId: 3 })).toBe(3);
    });
});

describe("remembering the choice", () => {
    test("a stored id comes back as a number; nothing stored is null", () => {
        expect(readStoredWarehouseId()).toBe(null);
        storeWarehouseId(7);
        expect(readStoredWarehouseId()).toBe(7);
    });

    test("garbage in storage is ignored", () => {
        browser.localStorage.setItem("warehouse_3d.warehouse_id", "abc");
        expect(readStoredWarehouseId()).toBe(null);
    });

    test("unavailable storage (private window) never throws", () => {
        const real = browser.localStorage;
        const broken = { getItem() { throw new Error("denied"); }, setItem() { throw new Error("denied"); } };
        Object.defineProperty(browser, "localStorage", { value: broken, configurable: true });
        try {
            expect(readStoredWarehouseId()).toBe(null);
            storeWarehouseId(3); // must not throw
        } finally {
            Object.defineProperty(browser, "localStorage", { value: real, configurable: true });
        }
    });
});
