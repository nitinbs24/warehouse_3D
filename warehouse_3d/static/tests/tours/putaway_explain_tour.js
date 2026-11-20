import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";

const callKw = (model, method, args, kwargs = {}) =>
    rpc(`/web/dataset/call_kw/${model}/${method}`, { model, method, args, kwargs });
const state = {};

// A receipt whose line was sent to the best slot by putaway: ask why, take the runner-up, validate.
registry.category("web_tour.tours").add("warehouse_3d_putaway_explain", {
    steps: () => [
        { content: "Open the detailed operations", trigger: ".oe_stat_button[name='action_detailed_operations']", run: "click" },
        { content: "Ask why this slot", trigger: ".o_data_row button[name='action_wh3d_explain_putaway']", run: "click" },
        {
            content: "The dialog offers three slots and says how many were excluded",
            trigger: ".modal .o_data_row:eq(2)",
            run() {
                const rows = document.querySelectorAll(".modal .o_data_row");
                if (rows.length !== 3) {
                    throw new Error(`expected 3 slots, found ${rows.length}`);
                }
                if (!document.querySelector(".modal").textContent.includes("slots excluded: hazard")) {
                    throw new Error("the excluded-slots sentence is missing");
                }
                state.slot = rows[1].querySelector("td[name='slot_id']").textContent.trim();
            },
        },
        { content: "Pick the second slot", trigger: ".modal .o_data_row:eq(1) button[name='action_choose']", run: "click" },
        {
            content: "The line now goes to the second slot, validate and check the stock is there",
            trigger: ".o_list_view",
            async run() {
                const [picking] = await callKw("stock.picking", "search", [[["origin", "=", "Explain tour"]]]);
                const [line] = await callKw("stock.move.line", "search_read", [[["picking_id", "=", picking]], ["location_dest_id"]]);
                if (line.location_dest_id[1] !== state.slot) {
                    throw new Error(`line goes to ${line.location_dest_id[1]}, expected ${state.slot}`);
                }
                await callKw("stock.move", "write", [(await callKw("stock.picking", "read", [[picking], ["move_ids"]]))[0].move_ids, { picked: true }]);
                await callKw("stock.picking", "button_validate", [[picking]]);
                const quants = await callKw("stock.quant", "search_read",
                    [[["location_id.complete_name", "=", state.slot], ["product_id.name", "=", "Tour bags"]], ["quantity"]]);
                if (!quants.length || quants[0].quantity !== 5) {
                    throw new Error(`no 5 bags in ${state.slot}`);
                }
            },
        },
    ],
});
