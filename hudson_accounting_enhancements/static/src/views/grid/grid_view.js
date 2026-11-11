/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { session } from "@web/session";
import { GridController } from "./grid_controller";
import { AnalyticSearchModel } from "@analytic/views/analytic_search_model";

// Ensure grid view info is defined in session.view_info for the action manager
if (session && session.view_info) {
    session.view_info.grid = {
        icon: "grid_view",
        display_name: _t("Grid"),
        multi_record: true,
    };
}

export const gridView = {
    type: "grid",
    display_name: _t("Grid"),
    icon: "grid_view",
    multiRecord: true,
    Controller: GridController,
    SearchModel: AnalyticSearchModel,
    searchMenuTypes: ["filter", "groupBy", "favorite"],

    props: (genericProps, view) => {
        return {
            ...genericProps,
            display_name: view.display_name,
        };
    },
};

registry.category("views").add("grid", gridView);
registry.category("views").add("analytic_grid", gridView);
