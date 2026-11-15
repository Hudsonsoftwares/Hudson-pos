/** @odoo-module **/

import { Component, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";

/** "Copy link" button of the Share Document dialog */
export class HudsonSignCopyLink extends Component {
    static template = "hudson_sign.CopyLinkButton";
    props = useProps({ ...standardWidgetProps });

    setup() {
        this.notification = useService("notification");
    }

    async copyLink() {
        const link = this.props.record.data.share_link;
        if (!link) {
            return;
        }
        try {
            await browser.navigator.clipboard.writeText(link);
            this.notification.add("Link copied to clipboard.", { type: "success" });
        } catch {
            this.notification.add("Could not copy the link, please copy it manually.", { type: "warning" });
        }
    }
}

registry.category("view_widgets").add("hudson_sign_copy_link", {
    component: HudsonSignCopyLink,
});
