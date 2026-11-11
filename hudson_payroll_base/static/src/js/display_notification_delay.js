/** @odoo-module **/

import { markup } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { htmlSprintf } from "@web/core/utils/html";

/**
 * Same as the standard "display_notification" client action, but also honours
 * params.autocloseDelay (in ms) so server actions can choose how long a
 * non-sticky notification stays visible.
 */
function displayNotificationWithDelay(env, action) {
    const notification = useService("notification");
    const params = action.params || {};
    const options = {
        className: params.className || "",
        sticky: params.sticky || false,
        title: params.title,
        type: params.type || "info",
    };
    if (typeof params.autocloseDelay === "number" && params.autocloseDelay > 0) {
        options.autocloseDelay = params.autocloseDelay;
    }
    const links = (params.links || []).map(
        (link) => markup`<a href="${link.url}" target="_blank">${link.label}</a>`
    );
    const message = htmlSprintf(params.message, ...links);
    notification.add(message, options);
    return params.next;
}

registry.category("actions").add("display_notification", displayNotificationWithDelay, { force: true });
