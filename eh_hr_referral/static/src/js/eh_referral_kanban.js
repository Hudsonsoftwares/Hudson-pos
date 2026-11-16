/** @odoo-module **/

import { KanbanController } from "@web/views/kanban/kanban_controller";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { registry } from "@web/core/registry";
import { onMounted, onWillUnmount } from "@odoo/owl";

export class EhReferralKanbanController extends KanbanController {
    setup() {
        super.setup();
        onMounted(() => {
            document.body.classList.add("eh_referral_background");
        });
        onWillUnmount(() => {
            document.body.classList.remove("eh_referral_background");
        });
    }
}

export const ehReferralKanbanView = {
    ...kanbanView,
    Controller: EhReferralKanbanController,
};

registry.category("views").add("eh_referral_kanban", ehReferralKanbanView);