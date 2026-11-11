/** @odoo-module **/

import { _t, translationIsReady } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

// Default fields of a form using the "Create a Ticket" action
translationIsReady.then(() => {
    registry.category("website.form_editor_actions").add("create_ticket", {
        formFields: [{
            type: "char",
            required: true,
            name: "partner_name",
            fillWith: "name",
            string: _t("Your Name"),
        }, {
            type: "tel",
            name: "partner_phone",
            fillWith: "phone",
            string: _t("Phone Number"),
        }, {
            type: "email",
            required: true,
            name: "partner_email",
            fillWith: "email",
            string: _t("Your Email"),
        }, {
            type: "char",
            modelRequired: true,
            name: "subject",
            string: _t("Subject"),
        }, {
            type: "text",
            required: true,
            name: "description",
            string: _t("Description"),
        }],
    });
});
