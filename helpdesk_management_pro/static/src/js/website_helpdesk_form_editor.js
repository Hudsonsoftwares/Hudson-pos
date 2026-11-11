/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

// Website Builder options of the "Create a Ticket" form action
registry.category("builder.form_editor_actions").add("create_ticket", {
    fields: [{
        name: "team_id",
        type: "many2one",
        relation: "helpdesk.management.team",
        domain: [["use_website_helpdesk_form", "=", true]],
        string: _t("Helpdesk Team"),
        title: _t("Assign the tickets created by this form to a helpdesk team."),
    }],
});
