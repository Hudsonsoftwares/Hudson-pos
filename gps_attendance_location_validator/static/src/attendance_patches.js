/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ActivityMenu } from "@hr_attendance/components/attendance_menu/attendance_menu";
import { rpc } from "@web/core/network/rpc";
import { isIosApp } from "@web/core/browser/feature_detection";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

// Global safeguard against benign Owl destroyed component promise rejections
window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    const msg = (reason && (reason.message || reason.cause?.message || String(reason))) || "";
    if (typeof msg === "string" && msg.includes("Component is destroyed")) {
        console.warn("Suppressed benign Owl lifecycle unhandled rejection:", msg);
        event.preventDefault();
        if (typeof event.stopImmediatePropagation === "function") {
            event.stopImmediatePropagation();
        }
    }
});

patch(ActivityMenu.prototype, {
    setup() {
        super.setup(...arguments);
        this.notification = useService("notification");
    },

    async signInOut() {
        this.dropdown.close();

        if (!isIosApp() && navigator.geolocation) {
            const getPosition = (options) =>
                new Promise((resolve, reject) => {
                    navigator.geolocation.getCurrentPosition(resolve, reject, options);
                });

            let coords = null;
            try {
                // Try high accuracy with timeout first
                const pos = await getPosition({ enableHighAccuracy: true, timeout: 5000, maximumAge: 60000 });
                coords = pos.coords;
            } catch (err) {
                console.warn("High accuracy geolocation failed, falling back to network/low accuracy:", err);
                try {
                    // Fallback to low accuracy (Wi-Fi / IP based)
                    const pos = await getPosition({ enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
                    coords = pos.coords;
                } catch (fallbackErr) {
                    console.warn("Geolocation failed completely:", fallbackErr);
                }
            }

            if (coords) {
                try {
                    this.employee = await rpc("/hr_attendance/systray_check_in_out", {
                        latitude: coords.latitude,
                        longitude: coords.longitude,
                    });
                    this._searchReadEmployeeFill();
                } catch (error) {
                    this.notification.add(
                        error.data?.message || _t("An error occurred during attendance change."),
                        { type: "danger" }
                    );
                }
            } else {
                try {
                    this.employee = await rpc("/hr_attendance/systray_check_in_out");
                    this._searchReadEmployeeFill();
                } catch (error) {
                    this.notification.add(
                        error.data?.message || _t("Location permission is required to perform check-in. Please enable location services in your browser and Windows settings."),
                        { type: "danger" }
                    );
                }
            }
        } else {
            try {
                this.employee = await rpc("/hr_attendance/systray_check_in_out");
                this._searchReadEmployeeFill();
            } catch (error) {
                this.notification.add(
                    error.data?.message || _t("An error occurred during attendance change."),
                    { type: "danger" }
                );
            }
        }
    },
});

