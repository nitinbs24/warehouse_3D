import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

function openView3d() {
    return [
        {
            content: "Open the Warehouse 3D menu",
            trigger: "button[data-menu-xmlid='warehouse_3d.menu_wh3d_root']",
            run: "click",
        },
        {
            content: "Open the 3D view",
            trigger: ".o-dropdown-item[data-menu-xmlid='warehouse_3d.menu_wh3d_view3d']",
            run: "click",
        },
        {
            content: "The scene loaded the one rack row and rendered it with WebGL",
            trigger: ".o_wh3d_view[data-row-count='1'] .o_wh3d_canvas canvas",
            run() {
                const canvases = document.querySelectorAll(".o_wh3d_canvas canvas");
                if (canvases.length !== 1) {
                    throw new Error(`Expected exactly one 3D canvas, found ${canvases.length}`);
                }
                if (!canvases[0].getContext("webgl2") && !canvases[0].getContext("webgl")) {
                    throw new Error("3D canvas has no WebGL context");
                }
                if (document.querySelector(".o_wh3d_empty, .o_wh3d_fallback")) {
                    throw new Error("Empty-state or fallback message shown although a row exists");
                }
            },
        },
    ];
}

registry.category("web_tour.tours").add("warehouse_3d_view3d", {
    steps: () => [
        ...stepUtils.goToAppSteps("stock.menu_stock_root", "Open the Inventory app"),
        ...openView3d(),
        {
            content: "Switch to the top view",
            trigger: ".o_wh3d_toolbar button[name='view_top']",
            run: "click",
        },
        {
            trigger: ".o_wh3d_toolbar button[name='view_top'][aria-pressed='true']",
        },
        {
            content: "Hide labels",
            trigger: ".o_wh3d_toolbar input[name='labels']",
            run: "click",
        },
        {
            trigger: ".o_wh3d_toolbar input[name='labels']:not(:checked)",
        },
        {
            content: "Leave the 3D view for Rack Rows",
            trigger: "button[data-menu-xmlid='stock.menu_stock_config_settings']",
            run: "click",
        },
        {
            trigger: ".o-dropdown-item[data-menu-xmlid='warehouse_3d.menu_wh3d_rack_row']",
            run: "click",
        },
        {
            content: "The 3D canvas is gone",
            trigger: ".o_list_view",
            run() {
                if (document.querySelector(".o_wh3d_canvas canvas")) {
                    throw new Error("3D canvas still in the page after leaving the view");
                }
            },
        },
        // Opening it again proves the view cleans up and restarts without errors.
        ...openView3d(),
    ],
});

// Used by the opt-in screenshot test: wait until the scene is up and the camera has settled.
registry.category("web_tour.tours").add("warehouse_3d_screenshot", {
    steps: () => [
        { trigger: ".o_wh3d_view[data-row-count='31'] .o_wh3d_canvas canvas" },
        { trigger: ".o_wh3d_toolbar input[name='occupancy']", run: "click" },
        { trigger: ".o_wh3d_find input", run: "edit P05-03-2-A" },
        { trigger: ".o_wh3d_find button[type='submit']", run: "click" },
        { trigger: ".o_wh3d_selected .o_wh3d_code:contains(P05-03-2-A)" },
        { trigger: "body", run: () => new Promise((resolve) => setTimeout(resolve, 1500)) },
    ],
});

function clickCanvasAt(fx, fy) {
    const canvas = document.querySelector(".o_wh3d_canvas canvas");
    const r = canvas.getBoundingClientRect();
    const init = { bubbles: true, clientX: r.left + r.width * fx, clientY: r.top + r.height * fy,
        pointerId: 1, pointerType: "mouse", button: 0, isPrimary: true };
    canvas.dispatchEvent(new PointerEvent("pointerdown", init));
    canvas.dispatchEvent(new PointerEvent("pointerup", init));
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

registry.category("web_tour.tours").add("warehouse_3d_stock", {
    steps: () => [
        ...stepUtils.goToAppSteps("stock.menu_stock_root", "Open the Inventory app"),
        ...openView3d(),
        {
            content: "Capacity card counts 70 pallet positions, 1 used",
            trigger: ".o_wh3d_capacity tr[data-kind='pallet'] td:eq(1):text(70)",
        },
        { trigger: ".o_wh3d_capacity tr[data-kind='pallet'] td:eq(2):text(1)" },
        {
            content: "Unknown code shows a helpful error",
            trigger: ".o_wh3d_find input",
            run: "edit P99-01-1-A",
        },
        { trigger: ".o_wh3d_find button[type='submit']", run: "click" },
        { trigger: ".o_wh3d_find .o_wh3d_err:contains(No location P99-01-1-A)" },
        {
            content: "Find a slot, typed in lower case",
            trigger: ".o_wh3d_find input",
            run: "edit p05-03-2-a",
        },
        { trigger: ".o_wh3d_find button[type='submit']", run: "click" },
        {
            content: "Panel shows the slot, its path, product and fill",
            trigger: ".o_wh3d_selected .o_wh3d_code:contains(P05-03-2-A)",
        },
        { trigger: ".o_wh3d_selected .o_wh3d_path:contains(WH/Stock/PR/P05/P05-03/P05-03-2/P05-03-2-A)" },
        { trigger: ".o_wh3d_selected:contains(Basmati rice pallet) .o_wh3d_psub:contains(fill 49 %)" },
        {
            content: "Turn on occupancy colours; the legend shows one slot under 50 %",
            trigger: ".o_wh3d_toolbar input[name='occupancy']",
            run: "click",
        },
        { trigger: ".o_wh3d_legend li[data-band='low'] .o_wh3d_n:text(1)" },
        {
            content: "Click empty sky: selection clears",
            trigger: ".o_wh3d_canvas canvas",
            async run() {
                await wait(900); // let the camera finish flying to the slot
                clickCanvasAt(0.03, 0.97);
            },
        },
        { trigger: ".o_wh3d_selected:not(:has(.o_wh3d_code))" },
        {
            content: "Click the centre, where Find put the slot: it is picked",
            trigger: ".o_wh3d_canvas canvas",
            run: () => clickCanvasAt(0.5, 0.5),
        },
        { trigger: ".o_wh3d_selected .o_wh3d_code:contains(P05-03-2-A)" },
        {
            content: "Open the slot's stock in Inventory",
            trigger: ".o_wh3d_selected button[name='open_in_inventory']",
            run: "click",
        },
        { trigger: ".o_list_view .o_data_row:contains(Basmati rice pallet)" },
    ],
});

registry.category("web_tour.tours").add("warehouse_3d_live", {
    steps: () => [
        ...stepUtils.goToAppSteps("stock.menu_stock_root", "Open the Inventory app"),
        ...openView3d(),
        { trigger: ".o_wh3d_capacity tr[data-kind='pallet'] td:eq(2):text(0)" },
        { trigger: ".o_wh3d_legend li[data-band='low'] .o_wh3d_n:text(0)" },
        { trigger: ".o_wh3d_find input", run: "edit P05-01-1-A" },
        { trigger: ".o_wh3d_find button[type='submit']", run: "click" },
        { trigger: ".o_wh3d_selected:contains(Empty. Available for putaway.)" },
        {
            content: "Elsewhere in Odoo, an inventory adjustment puts 1 pallet in that slot",
            trigger: ".o_wh3d_view",
            async run() {
                const call = (model, method, args, kwargs = {}) =>
                    rpc(`/web/dataset/call_kw/${model}/${method}`, { model, method, args, kwargs });
                const [location] = await call("stock.location", "search", [[["name", "=", "P05-01-1-A"], ["warehouse_id.code", "=", "WH"]]]);
                const [product] = await call("product.product", "search", [[["name", "=", "Basmati rice pallet"]]]);
                const quantId = await call("stock.quant", "create",
                    [{ product_id: product, location_id: location, inventory_quantity: 1 }],
                    { context: { inventory_mode: true } });
                await call("stock.quant", "action_apply_inventory", [[quantId]]);
            },
        },
        {
            content: "Without reloading, the panel, capacity and legend show the new stock",
            trigger: ".o_wh3d_view[data-updates='1'] .o_wh3d_selected:contains(Basmati rice pallet)",
        },
        { trigger: ".o_wh3d_capacity tr[data-kind='pallet'] td:eq(2):text(1)" },
        { trigger: ".o_wh3d_legend li[data-band='low'] .o_wh3d_n:text(1)" },
    ],
});

registry.category("web_tour.tours").add("warehouse_3d_editor", {
    steps: () => [
        ...stepUtils.goToAppSteps("stock.menu_stock_root", "Open the Inventory app"),
        {
            trigger: "button[data-menu-xmlid='warehouse_3d.menu_wh3d_root']",
            run: "click",
        },
        {
            content: "Open the layout editor",
            trigger: ".o-dropdown-item[data-menu-xmlid='warehouse_3d.menu_wh3d_editor']",
            run: "click",
        },
        {
            content: "The floor plan shows the row and the area",
            trigger: ".o_wh3d_editor svg .o_wh3d_area:contains(Receiving)",
        },
        { trigger: ".o_wh3d_editor_panel:contains(Click a rack row)" },
        {
            // Tour helpers call HTMLElement.focus() on the target, which throws on SVG elements,
            // so the click is dispatched directly (real browsers focus SVG tabindex elements fine).
            content: "Click row P05",
            trigger: ".o_wh3d_editor svg .o_wh3d_row[data-code='P05']",
            run() {
                this.anchor.dispatchEvent(new MouseEvent("click", { bubbles: true }));
            },
        },
        {
            content: "Panel shows P05's fields, the row is highlighted",
            trigger: ".o_wh3d_editor_panel .o_wh3d_code:text(P05)",
        },
        { trigger: ".o_wh3d_editor_panel input[name='bays']:value(7)" },
        { trigger: ".o_wh3d_editor svg .o_wh3d_row.o_selected[data-code='P05']" },
        {
            content: "Esc deselects",
            trigger: ".o_wh3d_editor svg .o_wh3d_row[data-code='P05']",
            run() {
                this.anchor.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
            },
        },
        { trigger: ".o_wh3d_editor_panel:contains(Click a rack row)" },
        {
            content: "Keyboard: focusing a row selects it",
            trigger: ".o_wh3d_editor svg .o_wh3d_row[data-code='P05']",
            run() {
                this.anchor.focus();
            },
        },
        {
            trigger: ".o_wh3d_editor_panel .o_wh3d_code:text(P05)",
            // Same tour-helper limitation: blur the focused SVG row natively before the next click.
            run: () => document.activeElement.blur(),
        },
        {
            content: "View it in 3D",
            trigger: ".o_wh3d_editor_panel button[name='view_in_3d']",
            run: "click",
        },
        {
            content: "3D view opens on the row's middle slot",
            trigger: ".o_wh3d_view .o_wh3d_selected .o_wh3d_code:text(P05-04-1-A)",
        },
    ],
});

// Used by the opt-in editor screenshot: template layout with P05 selected.
registry.category("web_tour.tours").add("warehouse_3d_editor_screenshot", {
    steps: () => [
        { trigger: ".o_wh3d_editor_panel:contains(31 rack rows)" },
        {
            trigger: ".o_wh3d_editor svg .o_wh3d_row[data-code='P05']",
            run() {
                this.anchor.dispatchEvent(new MouseEvent("click", { bubbles: true }));
            },
        },
        { trigger: ".o_wh3d_editor_panel .o_wh3d_code:text(P05)" },
    ],
});

function pressKey(type, key) {
    window.dispatchEvent(new KeyboardEvent(type, { key, bubbles: true }));
}

registry.category("web_tour.tours").add("warehouse_3d_walk", {
    steps: () => [
        ...stepUtils.goToAppSteps("stock.menu_stock_root", "Open the Inventory app"),
        ...openView3d(),
        { trigger: ".o_wh3d_view[data-mode='orbit']" },
        { trigger: ".o_wh3d_find input", run: "edit P05-03-2-A" },
        { trigger: ".o_wh3d_find button[type='submit']", run: "click" },
        { trigger: ".o_wh3d_selected .o_wh3d_code:text(P05-03-2-A)" },
        {
            content: "Walk from the selected slot",
            trigger: ".o_wh3d_toolbar button[name='walk']",
            run: "click",
        },
        {
            content: "First-person at eye height, in front of the slot",
            trigger: ".o_wh3d_view[data-mode='walk'][data-eye='1.7'] .o_wh3d_toolbar button[name='walk'][aria-pressed='true']",
        },
        {
            content: "Hold W for half a second",
            trigger: ".o_wh3d_view[data-mode='walk']",
            async run() {
                pressKey("keydown", "w");
                await wait(500);
                pressKey("keyup", "w");
            },
        },
        {
            content: "The walker moved towards the rack (and stopped short of it)",
            trigger: ".o_wh3d_view[data-mode='walk']",
            run() {
                const x = Number(this.anchor.dataset.walkX);
                if (!(x > 7.2 && x <= 9.4 + 1e-6)) {
                    throw new Error(`walker x ${x} not between start 7.2 and rack face 9.4`);
                }
            },
        },
        {
            content: "Hold W, then the window loses focus (Alt-Tab): the walker stops",
            trigger: ".o_wh3d_view[data-mode='walk']",
            async run() {
                pressKey("keydown", "w");
                await wait(200);
                window.dispatchEvent(new Event("blur"));
                await wait(100);
                const x1 = this.anchor.dataset.walkX;
                await wait(400);
                if (this.anchor.dataset.walkX !== x1) {
                    throw new Error(`still walking after focus loss: ${x1} -> ${this.anchor.dataset.walkX}`);
                }
            },
        },
        {
            content: "Esc goes back to the orbit view",
            trigger: ".o_wh3d_view[data-mode='walk']",
            run: () => pressKey("keydown", "Escape"),
        },
        { trigger: ".o_wh3d_view[data-mode='orbit'] .o_wh3d_toolbar button[name='walk'][aria-pressed='false']" },
        {
            content: "Clear the selection, walk again: starts at the entrance",
            trigger: ".o_wh3d_canvas canvas",
            async run() {
                clickCanvasAt(0.03, 0.97);
                await wait(100);
            },
        },
        { trigger: ".o_wh3d_selected:not(:has(.o_wh3d_code))" },
        { trigger: ".o_wh3d_toolbar button[name='walk']", run: "click" },
        { trigger: ".o_wh3d_view[data-mode='walk'][data-eye='1.7']" },
        { trigger: ".o_wh3d_toolbar button[name='walk']", run: "click" },
        { trigger: ".o_wh3d_view[data-mode='orbit']" },
    ],
});

// Used by the opt-in walk screenshot: stand in P05's aisle, step back and turn a little.
registry.category("web_tour.tours").add("warehouse_3d_walk_screenshot", {
    steps: () => [
        { trigger: ".o_wh3d_view[data-row-count='31'] .o_wh3d_canvas canvas" },
        { trigger: ".o_wh3d_toolbar input[name='occupancy']", run: "click" },
        { trigger: ".o_wh3d_find input", run: "edit P05-03-2-A" },
        { trigger: ".o_wh3d_find button[type='submit']", run: "click" },
        { trigger: ".o_wh3d_selected .o_wh3d_code:text(P05-03-2-A)" },
        { trigger: ".o_wh3d_toolbar button[name='walk']", run: "click" },
        {
            trigger: ".o_wh3d_view[data-mode='walk']",
            async run() {
                pressKey("keydown", "s");
                await wait(500);
                pressKey("keyup", "s");
                const canvas = document.querySelector(".o_wh3d_canvas canvas");
                const r = canvas.getBoundingClientRect();
                const at = (x) => ({ bubbles: true, clientX: r.left + x, clientY: r.top + r.height / 2,
                    buttons: 1, pointerType: "mouse" });
                canvas.dispatchEvent(new PointerEvent("pointerdown", at(r.width / 2)));
                canvas.dispatchEvent(new PointerEvent("pointermove", at(r.width / 2 + 90)));
                canvas.dispatchEvent(new PointerEvent("pointerup", { ...at(r.width / 2 + 90), buttons: 0 }));
                await wait(500);
            },
        },
    ],
});

function clickSvgRow(code) {
    return {
        content: `Select row ${code}`,
        trigger: `.o_wh3d_editor svg .o_wh3d_row[data-code='${code}']`,
        run() {
            this.anchor.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        },
    };
}

/** Drag a row on the plan by (mx, my) metres, using the plan's current scale. */
function dragRow(code, mx, my) {
    return {
        content: `Drag ${code} by ${mx} m, ${my} m`,
        trigger: `.o_wh3d_editor svg .o_wh3d_row[data-code='${code}']`,
        run() {
            const svg = this.anchor.closest("svg");
            const scale = Number(svg.querySelector("g").getAttribute("transform").match(/scale\(([\d.]+)\)/)[1]);
            const box = this.anchor.getBoundingClientRect();
            const start = { x: box.left + box.width / 2, y: box.top + box.height / 2 };
            const ev = (x, y, buttons) => ({ bubbles: true, clientX: x, clientY: y, button: 0, buttons,
                pointerId: 1, pointerType: "mouse", isPrimary: true });
            this.anchor.dispatchEvent(new PointerEvent("pointerdown", ev(start.x, start.y, 1)));
            for (let i = 1; i <= 5; i++) {
                svg.dispatchEvent(new PointerEvent("pointermove",
                    ev(start.x + (mx * scale * i) / 5, start.y + (my * scale * i) / 5, 1)));
            }
            svg.dispatchEvent(new PointerEvent("pointerup", ev(start.x + mx * scale, start.y + my * scale, 0)));
        },
    };
}

/** Type a value into a panel field and commit it (as Enter or Tab would). */
function setField(name, value) {
    return {
        content: `Set ${name} to ${value}`,
        trigger: `.o_wh3d_editor_panel [name='${name}']`,
        run() {
            this.anchor.value = String(value);
            this.anchor.dispatchEvent(new Event("change", { bubbles: true }));
        },
    };
}

function openEditor() {
    return [
        { trigger: "button[data-menu-xmlid='warehouse_3d.menu_wh3d_root']", run: "click" },
        { trigger: ".o-dropdown-item[data-menu-xmlid='warehouse_3d.menu_wh3d_editor']", run: "click" },
        { trigger: ".o_wh3d_editor[data-dirty='0'] svg .o_wh3d_row" },
    ];
}

registry.category("web_tour.tours").add("warehouse_3d_editor_edit", {
    steps: () => [
        ...stepUtils.goToAppSteps("stock.menu_stock_root", "Open the Inventory app"),
        ...openEditor(),
        // 1. Drag P05 half a metre to the right, save, and see it stick.
        clickSvgRow("P05"),
        dragRow("P05", 0.5, 0),
        { trigger: ".o_wh3d_editor[data-dirty='1'] .o_wh3d_editor_panel input[name='x']:value(10.2)" },
        { trigger: ".o_wh3d_savebar button[name='save']:enabled", run: "click" },
        { trigger: ".o_notification:contains(Layout saved)" },
        { trigger: ".o_wh3d_editor[data-dirty='0']" },
        // 2. A move onto another row is shown at once and can't be saved.
        clickSvgRow("P06"),
        setField("x", 10.5),
        { trigger: ".o_wh3d_editor svg .o_wh3d_row.o_invalid[data-code='P06']" },
        { trigger: ".o_wh3d_problems:contains(P06 overlaps P05)" },
        { trigger: ".o_wh3d_savebar button[name='save']:disabled" },
        { trigger: ".o_wh3d_savebar button[name='discard']", run: "click" },
        { trigger: ".o_wh3d_editor[data-dirty='0']:not(:has(.o_invalid))" },
        // 3. Add a pallet row and save: it gets its locations.
        { trigger: ".o_wh3d_editor_toolbar button[name='add_pallet']", run: "click" },
        { trigger: ".o_wh3d_editor svg .o_wh3d_row.o_new.o_selected[data-code='P07']" },
        { trigger: ".o_wh3d_savebar button[name='save']:enabled", run: "click" },
        { trigger: ".o_wh3d_editor[data-dirty='0'] svg .o_wh3d_row:not(.o_new)[data-code='P07']" },
        {
            content: "P07's slot locations exist",
            trigger: ".o_wh3d_editor",
            async run() {
                const count = await rpc("/web/dataset/call_kw/stock.location/search_count", {
                    model: "stock.location", method: "search_count",
                    args: [[["name", "=like", "P07-%"], ["wh3d_node", "=", "slot"], ["warehouse_id.code", "=", "WH"]]], kwargs: {},
                });
                if (count !== 70) {
                    throw new Error(`expected 70 P07 slots, found ${count}`);
                }
            },
        },
        // 4. Shrinking P05 under its stock: the server refuses, nothing is saved, the edit stays.
        clickSvgRow("P05"),
        setField("bays", 6),
        { trigger: ".o_wh3d_savebar button[name='save']:enabled", run: "click" },
        { trigger: ".o_notification:contains(Layout not saved):contains(P05-07-1-A)" },
        { trigger: ".o_wh3d_editor[data-dirty='1'] .o_wh3d_editor_panel input[name='bays']:value(6)" },
        // 5. Leaving with unsaved edits asks first; Cancel stays.
        { trigger: "button[data-menu-xmlid='warehouse_3d.menu_wh3d_root']", run: "click" },
        { trigger: ".o-dropdown-item[data-menu-xmlid='warehouse_3d.menu_wh3d_view3d']", run: "click" },
        { trigger: ".modal:contains(Discard layout changes?) button:contains(Cancel)", run: "click" },
        { trigger: ".o_wh3d_editor[data-dirty='1']" },
        { trigger: ".o_wh3d_savebar button[name='discard']", run: "click" },
        // 6. Reopen: the saved move and the new row are there, the refused shrink isn't.
        { trigger: "button[data-menu-xmlid='warehouse_3d.menu_wh3d_root']", run: "click" },
        { trigger: ".o-dropdown-item[data-menu-xmlid='warehouse_3d.menu_wh3d_view3d']", run: "click" },
        { trigger: ".o_wh3d_view .o_wh3d_canvas canvas" },
        ...openEditor(),
        clickSvgRow("P05"),
        { trigger: ".o_wh3d_editor_panel input[name='x']:value(10.2)" },
        { trigger: ".o_wh3d_editor_panel input[name='bays']:value(7)" },
        { trigger: ".o_wh3d_editor svg .o_wh3d_row[data-code='P07']" },
    ],
});

// End to end on the template warehouse: Inventory books a receipt (Odoo's standard putaway picks
// the slot) and a delivery while the 3D view is open; the view follows both without reloading.
const flow = {};

async function callKw(model, method, args, kwargs = {}) {
    return rpc(`/web/dataset/call_kw/${model}/${method}`, { model, method, args, kwargs });
}

async function bookPicking(typeField, fromLocation, toLocation, qty) {
    const picking = await callKw("stock.picking", "create", [{
        picking_type_id: flow.warehouse[typeField][0],
        location_id: fromLocation, location_dest_id: toLocation,
        move_ids: [[0, 0, { product_id: flow.productId, product_uom_qty: qty,
            location_id: fromLocation, location_dest_id: toLocation }]],
    }]);
    await callKw("stock.picking", "action_confirm", [[picking]]);
    await callKw("stock.picking", "action_assign", [[picking]]);
    const [{ move_ids }] = await callKw("stock.picking", "read", [[picking], ["move_ids"]]);
    await callKw("stock.move", "write", [move_ids, { quantity: qty, picked: true }]);
    await callKw("stock.picking", "button_validate", [[picking]]);
    return move_ids;
}

registry.category("web_tour.tours").add("warehouse_3d_inventory_flow", {
    steps: () => [
        ...stepUtils.goToAppSteps("stock.menu_stock_root", "Open the Inventory app"),
        { trigger: "button[data-menu-xmlid='warehouse_3d.menu_wh3d_root']", run: "click" },
        { trigger: ".o-dropdown-item[data-menu-xmlid='warehouse_3d.menu_wh3d_view3d']", run: "click" },
        {
            content: "The 3D view opened the template warehouse",
            trigger: ".o_wh3d_view[data-row-count='31'][data-updates='0'] .o_wh3d_canvas canvas",
        },
        {
            content: "Inventory receives 10 bags into WHV/Stock; putaway sends them to a pallet slot",
            trigger: ".o_wh3d_view",
            async run() {
                [flow.warehouse] = await callKw("stock.warehouse", "search_read",
                    [[["code", "=", "WHV"]], ["in_type_id", "out_type_id", "lot_stock_id"]]);
                [flow.productId] = await callKw("product.product", "search", [[["default_code", "=", "PR-1001"]]]);
                [flow.supplier] = await callKw("stock.location", "search", [[["usage", "=", "supplier"]]], { limit: 1 });
                [flow.customer] = await callKw("stock.location", "search", [[["usage", "=", "customer"]]], { limit: 1 });
                const moves = await bookPicking("in_type_id", flow.supplier, flow.warehouse.lot_stock_id[0], 10);
                const [line] = await callKw("stock.move.line", "search_read",
                    [[["move_id", "in", moves]], ["location_dest_id"]]);
                flow.slotId = line.location_dest_id[0];
                [{ name: flow.slotCode }] = await callKw("stock.location", "read", [[flow.slotId], ["name"]]);
                if (!/^P\d\d-\d\d-\d-[AB]$/.test(flow.slotCode)) {
                    throw new Error(`putaway chose ${flow.slotCode}, not a pallet slot`);
                }
            },
        },
        {
            content: "Live update arrived (no reload)",
            trigger: ".o_wh3d_view[data-updates='1']",
        },
        {
            content: "Find the slot putaway chose",
            trigger: ".o_wh3d_find input",
            run() {
                this.anchor.value = flow.slotCode;
                this.anchor.dispatchEvent(new Event("input", { bubbles: true }));
            },
        },
        { trigger: ".o_wh3d_find button[type='submit']", run: "click" },
        {
            content: "The panel shows the 10 bags just received",
            trigger: ".o_wh3d_selected:contains(PR-1001):contains(10 Units)",
        },
        {
            content: "Inventory delivers the 10 bags from that slot",
            trigger: ".o_wh3d_view",
            async run() {
                await bookPicking("out_type_id", flow.slotId, flow.customer, 10);
            },
        },
        {
            content: "The slot is empty again, without a reload",
            trigger: ".o_wh3d_view[data-updates='2'] .o_wh3d_selected:contains(Empty. Available for putaway.)",
        },
    ],
});
