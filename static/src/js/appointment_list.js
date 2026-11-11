/** @odoo-module **/

import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class AppointmentListController extends ListController {
    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    onClickAddClosingDay() {
        this.actionService.doAction("appointment.action_appointment_closing_day");
    }
}

export const appointmentListView = {
    ...listView,
    Controller: AppointmentListController,
    buttonTemplate: "appointment.ListView.Buttons",
};

registry.category("views").add("appointment_list", appointmentListView);
