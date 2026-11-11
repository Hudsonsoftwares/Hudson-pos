/** @odoo-module **/

import { registry } from "@web/core/registry";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";

// The list view ignores `on_create`, so "New" would open a blank pay run form.
// Open the same "New Pay Run" wizard as the kanban view instead.
export class PayrunListController extends ListController {
    async createRecord() {
        const { root } = this.model;
        await this.actionService.doAction("hudson_payroll_base.action_hudson_payrun_wizard", {
            additionalContext: root.context,
            onClose: async ({ noReload } = {}) => {
                if (!noReload) {
                    await root.load();
                }
            },
        });
    }
}

registry.category("views").add("hudson_payrun_list", {
    ...listView,
    Controller: PayrunListController,
});
