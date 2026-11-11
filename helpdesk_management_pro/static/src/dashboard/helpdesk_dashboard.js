/** @odoo-module **/

import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { Component, onWillStart, proxy } from "@odoo/owl";

export class HelpdeskDashboard extends Component {
    static template = "helpdesk_management_pro.HelpdeskDashboard";
    
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ metrics: null });
        
        onWillStart(async () => {
            await this.fetchMetrics();
        });
    }

    async fetchMetrics() {
        try {
            this.state.metrics = await this.orm.call("helpdesk.management.team", "get_dashboard_metrics", []);
        } catch (e) {
            console.error("Failed to fetch dashboard metrics", e);
        }
    }

    /** Daily targets are stored per user on the server (0 = not set, shown as an empty input). */
    targetInputValue(targetType) {
        const value = this.state.metrics[`target_${targetType}`];
        return value ? value : "";
    }

    /**
     * Colour of a "My Performance" figure compared to its daily target, like the standard dashboard:
     * green when the target is reached, orange when it is not. No colour without a target or data.
     * @param {"closed"|"success"|"rating"} targetType
     * @param {"today"|"7d"} period
     */
    performanceClass(targetType, period) {
        const target = this.state.metrics[`target_${targetType}`];
        const value = this.state.metrics.performance?.[`${targetType}_${period}`];
        if (!target || value === null || value === undefined) {
            return "";
        }
        return value >= target ? "o_target_reached" : "o_target_missed";
    }

    async updateTarget(targetType, ev) {
        const raw = ev.target.value.trim();
        const value = raw === "" ? 0 : parseFloat(raw);
        if (isNaN(value)) {
            ev.target.value = this.targetInputValue(targetType);
            return;
        }
        // The server clamps the value to its valid range and returns what was stored
        const stored = await this.orm.call("helpdesk.management.team", "set_dashboard_target", [targetType, value]);
        this.state.metrics[`target_${targetType}`] = stored;
        ev.target.value = this.targetInputValue(targetType);
    }

    _openTickets(title, domain, key) {
        // The server sends the exact domain of each figure, so that the list matches the count
        // (failed SLAs evaluated now, "today" in the user's timezone); the local domain is a fallback.
        const serverDomain = key && this.state.metrics?.domains?.[key];
        this.action.doAction({
            type: "ir.actions.act_window",
            name: title,
            res_model: "helpdesk.management.ticket",
            views: [[false, "list"], [false, "kanban"], [false, "form"]],
            // Same scope as the metrics: the open / closed tickets assigned to the current user
            domain: serverDomain || [...domain, ["user_id", "=", user.userId]],
            context: {},
        });
    }

    openMyTickets() {
        this._openTickets("Open Tickets", ['|', ['stage_id', '=', false], ['stage_id.is_close', '=', false]], "open");
    }

    openHighPriority() {
        this._openTickets("High Priority Tickets", ['&', '|', ['stage_id', '=', false], ['stage_id.is_close', '=', false], ['priority', '=', '2']], "high_priority");
    }

    openUrgent() {
        this._openTickets("Urgent Tickets", ['&', '|', ['stage_id', '=', false], ['stage_id.is_close', '=', false], ['priority', '=', '3']], "urgent");
    }

    openFailed() {
        this._openTickets("Failed SLA Tickets", ['&', '|', ['stage_id', '=', false], ['stage_id.is_close', '=', false], ['sla_status', '=', 'breached']], "failed");
    }

    openHpFailed() {
        this._openTickets("High Priority Failed SLA", ['&', '&', ['priority', '=', '2'], ['sla_status', '=', 'breached'], '|', ['stage_id', '=', false], ['stage_id.is_close', '=', false]], "hp_failed");
    }

    openUrgFailed() {
        this._openTickets("Urgent Failed SLA", ['&', '&', ['priority', '=', '3'], ['sla_status', '=', 'breached'], '|', ['stage_id', '=', false], ['stage_id.is_close', '=', false]], "urg_failed");
    }

    openTodayClosed() {
        const today = new Date().toISOString().split('T')[0] + ' 00:00:00';
        this._openTickets("Today's Closed Tickets", ['&', ['stage_id', '!=', false], ['stage_id.is_close', '=', true], ['close_date', '>=', today]], "closed_today");
    }

    openLast7DaysClosed() {
        const d = new Date();
        d.setDate(d.getDate() - 7);
        const last7 = d.toISOString().split('T')[0] + ' 00:00:00';
        this._openTickets("Last 7 Days Closed Tickets", ['&', ['stage_id', '!=', false], ['stage_id.is_close', '=', true], ['close_date', '>=', last7]], "closed_7d");
    }

    openClosed() {
        this._openTickets("Closed Tickets", [['stage_id', '!=', false], ['stage_id.is_close', '=', true]], "closed");
    }
}

export class HelpdeskDashboardKanbanRenderer extends KanbanRenderer {
    static template = "helpdesk_management_pro.DashboardKanbanRenderer";
    static components = {
        ...KanbanRenderer.components,
        HelpdeskDashboard,
    };
}

export const helpdeskDashboardKanbanView = {
    ...kanbanView,
    Renderer: HelpdeskDashboardKanbanRenderer,
};

registry.category("views").add("helpdesk_dashboard_kanban", helpdeskDashboardKanbanView);
