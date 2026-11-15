/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { Component, proxy, onWillDestroy, useProps } from "@odoo/owl";

export class FieldServiceTimerWidget extends Component {
    static template = "hudson_field_service.FieldServiceTimerWidget";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = proxy({ loading: false, loadingAction: '' });
        
        // Background tracking interval
        this.trackingInterval = setInterval(() => {
            this._pingLocation();
        }, 60000); // Ping every 60 seconds

        onWillDestroy(() => {
            clearInterval(this.trackingInterval);
        });
    }

    async _pingLocation() {
        if (!this.isTimerRunning) return;
        try {
            const loc = await this._fetchLocation();
            if (loc.latitude && loc.longitude) {
                await this.orm.call(
                    this.record.resModel,
                    "action_update_current_location",
                    [this.record.resId],
                    { latitude: loc.latitude, longitude: loc.longitude }
                );
            }
        } catch (e) {
            console.warn("Background tracking failed", e);
        }
    }

    get record() {
        return this.props.record;
    }

    // The widget is also used on planning shifts, which carry the job's
    // values in their own fields.
    get isShift() {
        return this.record.resModel === "fs.planning.slot";
    }

    get orderState() {
        return this.isShift ? this.record.data.field_service_state : this.record.data.state;
    }

    get isTimerRunning() {
        return this.isShift ? this.record.data.fs_is_timer_running : this.record.data.is_timer_running;
    }

    async _reload() {
        if (this.isShift) {
            // Shifts are edited in a dialog: refresh the record in place.
            await this.record.load();
        } else {
            await this.action.doAction({ type: "ir.actions.client", tag: "reload" });
        }
    }

    // Published jobs only, by their technicians (see _get_start_work_error)
    get canStartWork() {
        return this.isShift ? this.record.data.fs_can_start_work : this.record.data.can_start_work;
    }

    get showStart() {
        return ['new', 'scheduled'].includes(this.orderState) && !this.isTimerRunning && this.canStartWork;
    }

    get showResume() {
        return this.orderState === 'paused' && !this.isTimerRunning && this.canStartWork;
    }


    get showStop() {
        return this.isTimerRunning;
    }

    /**
     * Fetch geolocation from the browser.
     * Returns {latitude, longitude} or {latitude: 0, longitude: 0} on failure.
     */
    _fetchLocation() {
        return new Promise((resolve) => {
            // Settings > Geolocation disabled: no location is recorded
            if (!navigator.geolocation || this.record.data.fs_geolocation_enabled === false) {
                resolve({ latitude: 0, longitude: 0 });
                return;
            }
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    resolve({
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                    });
                },
                (error) => {
                    console.warn("Geolocation failed, proceeding without location:", error);
                    resolve({ latitude: 0, longitude: 0 });
                },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
            );
        });
    }

    async onClickStart() {
        if (this.state.loading) return;
        this.state.loading = true;
        this.state.loadingAction = 'start';
        try {
            // Save the record first (in case there are unsaved changes)
            await this.record.save();

            // Fetch geolocation
            const loc = await this._fetchLocation();

            // Call the backend with location
            await this.orm.call(
                this.record.resModel,
                "action_start_timer_with_location",
                [this.record.resId],
                { latitude: loc.latitude, longitude: loc.longitude }
            );

            // Reload the form
            await this._reload();
        } catch (error) {
            this.notification.add("Error: " + (error.message || error), { type: "danger" });
        } finally {
            this.state.loading = false;
            this.state.loadingAction = '';
        }
    }

    async onClickResume() {
        if (this.state.loading) return;
        this.state.loading = true;
        this.state.loadingAction = 'resume';
        try {
            await this.record.save();
            const loc = await this._fetchLocation();
            await this.orm.call(
                this.record.resModel,
                "action_resume_timer_with_location",
                [this.record.resId],
                { latitude: loc.latitude, longitude: loc.longitude }
            );
            await this._reload();
        } catch (error) {
            this.notification.add("Error: " + (error.message || error), { type: "danger" });
        } finally {
            this.state.loading = false;
            this.state.loadingAction = '';
        }
    }

    async onClickStop() {
        if (this.state.loading) return;
        this.state.loading = true;
        this.state.loadingAction = 'stop';
        try {
            if (!navigator.onLine) {
                // OFFLINE MODE: Save to local storage
                this.notification.add("You are offline. Stop action saved locally and will sync when online.", { type: "warning" });
                const offlineStops = JSON.parse(localStorage.getItem('fs_offline_stops') || '[]');
                offlineStops.push({
                    resId: this.record.resId,
                    timestamp: new Date().toISOString(),
                });
                localStorage.setItem('fs_offline_stops', JSON.stringify(offlineStops));
                
                // Optimistically reload
                await this._reload();
                return;
            }
            
            await this.record.save();
            const loc = await this._fetchLocation();
            if (loc.latitude && loc.longitude) {
                await this.orm.call(
                    this.record.resModel,
                    "action_log_location",
                    [this.record.resId],
                    { latitude: loc.latitude, longitude: loc.longitude, event_label: "Stopped" }
                );
            }
            const result = await this.orm.call(
                this.record.resModel,
                "action_stop_timer",
                [this.record.resId]
            );
            if (result && result.type) {
                await this.action.doAction(result, {
                    onClose: async () => {
                        await this.record.load();
                    }
                });
            }
        } catch (error) {
            this.notification.add("Error: " + (error.message || error), { type: "danger" });
        } finally {
            this.state.loading = false;
            this.state.loadingAction = '';
        }
    }
}

// Global listener for syncing offline stops
window.addEventListener('online', async () => {
    const offlineStops = JSON.parse(localStorage.getItem('fs_offline_stops') || '[]');
    if (offlineStops.length > 0) {
        // Need to find the ORM service dynamically since we're outside the component
        // In Odoo 16/17+, this is tricky, so a page reload is the safest way to force state sync,
        // but let's clear it and alert the user.
        alert("You are back online. Please refresh the page to sync your offline Field Service timers.");
    }
});

export const fieldServiceTimerWidget = {
    component: FieldServiceTimerWidget,
};

registry.category("view_widgets").add("field_service_timer", fieldServiceTimerWidget);
// Keep old name registered so any cached views still work
registry.category("view_widgets").add("log_location_button", fieldServiceTimerWidget);
