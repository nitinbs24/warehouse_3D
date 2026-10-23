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
        { trigger: "body", run: () => new Promise((resolve) => setTimeout(resolve, 1500)) },
    ],
});
