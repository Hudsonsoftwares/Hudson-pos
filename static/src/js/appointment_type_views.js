/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { listView } from "@web/views/list/list_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class AppointmentTypeListController extends ListController {
    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    async createRecord() {
        this.actionService.doAction("appointment.appointment_type_wizard_action");
    }
    
    onClickShare() {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            name: 'Share Appointment',
            res_model: 'appointment.invite',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
        });
    }
}

export const appointmentTypeListView = {
    ...listView,
    Controller: AppointmentTypeListController,
    buttonTemplate: "appointment.appointment_type_list.Buttons",
};
registry.category("views").add("appointment_type_list", appointmentTypeListView);


export class AppointmentTypeKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    async createRecord() {
        this.actionService.doAction("appointment.appointment_type_wizard_action");
    }
    
    onClickShare() {
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            name: 'Share Appointment',
            res_model: 'appointment.invite',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
        });
    }
}

export const appointmentTypeKanbanView = {
    ...kanbanView,
    Controller: AppointmentTypeKanbanController,
    buttonTemplate: "appointment.appointment_type_kanban.Buttons",
};
registry.category("views").add("appointment_type_kanban", appointmentTypeKanbanView);

async function copyAndCloseAction(env, action) {
    if (action.params && action.params.url) {
        try {
            await navigator.clipboard.writeText(action.params.url);
            env.services.notification.add("Link copied to clipboard!", { type: "success" });
        } catch (e) {
            console.error("Failed to copy to clipboard", e);
        }
    }
    if (action.params && action.params.close) {
        env.services.action.doAction({ type: "ir.actions.act_window_close" });
    }
}
registry.category("actions").add("appointment.action_copy_close", copyAndCloseAction);
