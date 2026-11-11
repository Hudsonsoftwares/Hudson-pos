/** @odoo-module **/

import { CalendarController } from "@web/views/calendar/calendar_controller";
import { calendarView } from "@web/views/calendar/calendar_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class AppointmentCalendarController extends CalendarController {
    setup() {
        super.setup();
        this.actionService = useService("action");
    }

    onClickNew() {
        this.actionService.doAction("appointment.action_appointment_booking_quick_create", {
            onClose: () => { 
                if (this.model && this.model.load) {
                    this.model.load(); 
                }
            }
        });
    }

    onClickAddClosingDay() {
        this.actionService.doAction("appointment.action_appointment_closing_day");
    }
}

export const appointmentCalendarView = {
    ...calendarView,
    Controller: AppointmentCalendarController,
    buttonTemplate: "appointment.CalendarController.controlButtons",
};
registry.category("views").add("appointment_calendar", appointmentCalendarView);
