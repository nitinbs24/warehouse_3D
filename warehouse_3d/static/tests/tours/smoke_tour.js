import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

registry.category("web_tour.tours").add("warehouse_3d_smoke", {
    steps: () => [
        ...stepUtils.goToAppSteps("stock.menu_stock_root", "Open the Inventory app"),
        {
            content: "Inventory overview is shown",
            trigger: ".o_action_manager .o_kanban_view",
        },
    ],
});
