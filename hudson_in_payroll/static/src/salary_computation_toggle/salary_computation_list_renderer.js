/** @odoo-module **/

import { ListRenderer } from "@web/views/list/list_renderer";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import { useState } from "@odoo/owl";
import { SalaryComputationColumnToggle } from "./salary_computation_column_toggle";
import { SalaryComputationColumnState } from "./salary_computation_state";

// Register SalaryComputationColumnToggle on ListRenderer.components for QWeb template resolution
ListRenderer.components.SalaryComputationColumnToggle = SalaryComputationColumnToggle;

export class SalaryComputationListRenderer extends ListRenderer {
    static template = "hudson_in_payroll.SalaryComputationListRenderer";
    static components = {
        ...ListRenderer.components,
        SalaryComputationColumnToggle,
    };

    setup() {
        super.setup();
        this.columnState = useState(new SalaryComputationColumnState());
        this.onVisibilityChange = this.onVisibilityChange.bind(this);
    }

    get columns() {
        const allColumns = super.columns;
        if (!allColumns) return [];
        return allColumns.filter((col) => {
            const colName = col.name;
            if (!colName) return true;
            return this.columnState.isColumnVisible(colName);
        });
    }

    onVisibilityChange() {
        if (typeof this.render === "function") {
            this.render(true);
        }
    }
}

export const salaryComputationListView = {
    ...listView,
    Renderer: SalaryComputationListRenderer,
};

registry.category("views").add("salary_computation_list", salaryComputationListView);
