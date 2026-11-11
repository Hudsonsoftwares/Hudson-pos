/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";

export class SalaryRevisionListController extends ListController {
    async onClickCreate() {
        return this.actionService.doAction("hudson_in_payroll.action_hds_in_salary_revision_wizard", {
            onClose: async () => {
                await this.model.root.load();
            },
        });
    }
}

export const salaryRevisionListView = {
    ...listView,
    Controller: SalaryRevisionListController,
};

registry.category("views").add("hds_salary_revision_list", salaryRevisionListView);
