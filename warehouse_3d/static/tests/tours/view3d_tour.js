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
            content: "A WebGL canvas is rendered",
            trigger: ".o_wh3d_canvas canvas",
            run() {
                const canvas = document.querySelector(".o_wh3d_canvas canvas");
                if (!canvas.getContext("webgl2") && !canvas.getContext("webgl")) {
                    throw new Error("3D canvas has no WebGL context");
                }
                if (document.querySelectorAll(".o_wh3d_canvas canvas").length !== 1) {
                    throw new Error("Expected exactly one 3D canvas");
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
