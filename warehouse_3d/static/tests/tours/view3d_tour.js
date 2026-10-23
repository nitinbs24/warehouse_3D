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
            trigger: ".o_wh3d_capacity tr[data-kind='pallet']:contains(70):contains(1)",
        },
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
        { trigger: ".o_wh3d_selected:contains(Basmati rice pallet):contains(49 %)" },
        {
            content: "Turn on occupancy colours; the legend shows one slot under 50 %",
            trigger: ".o_wh3d_toolbar input[name='occupancy']",
            run: "click",
        },
        { trigger: ".o_wh3d_legend li[data-band='low']:contains(1)" },
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
