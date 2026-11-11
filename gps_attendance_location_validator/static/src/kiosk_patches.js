/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import publicKioskApp from "@hr_attendance/public_kiosk/public_kiosk_app";
import { _t } from "@web/core/l10n/translation";

patch(publicKioskApp.kioskAttendanceApp.prototype, {
    async onManualSelection() {
        try {
            return await super.onManualSelection(...arguments);
        } catch (error) {
            const message = error.data?.message || error.message || _t("An error occurred during attendance change.");
            this.displayNotification(message);
        }
    },
    async onBarcodeScanned() {
        try {
            return await super.onBarcodeScanned(...arguments);
        } catch (error) {
            const message = error.data?.message || error.message || _t("An error occurred during attendance change.");
            this.displayNotification(message);
        }
    },
});
