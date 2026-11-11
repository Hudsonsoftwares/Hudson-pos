/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

// Operators type "/ticket <subject>" in a live chat to create a helpdesk ticket from the conversation
registry.category("discuss.channel_commands").add("ticket", {
    condition: ({ store }) => store.has_access_livechat,
    help: _t("Create a new helpdesk ticket (/ticket ticket subject)"),
    methodName: "execute_command_ticket",
});
