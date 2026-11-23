import { patch } from "@web/core/utils/patch";
import { Navbar } from "@point_of_sale/app/components/navbar/navbar";
import { WaitlistPanel } from "./waitlist_panel";

patch(Navbar.prototype, {
    openWaitlist() {
        this.dialog.add(WaitlistPanel, {});
    },
});
