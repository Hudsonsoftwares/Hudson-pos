/** @odoo-module **/
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class ReferralDashboardIframe extends Component {
    static template = "eh_hr_referral.ReferralDashboardIframe";
}

registry.category("actions").add("eh_hr_referral_dashboard_client_action", ReferralDashboardIframe);
