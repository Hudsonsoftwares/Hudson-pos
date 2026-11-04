import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { getOnNotified } from "@point_of_sale/utils";
import { _t } from "@web/core/l10n/translation";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        if (this.config.use_booking && this.bus) {
            this._setupBookingBusListener();
        }
    },

    _setupBookingBusListener() {
        if (!this.config.access_token) return;
        const onNotified = getOnNotified(this.bus, this.config.access_token);
        onNotified("BOOKING_UPDATE", (payload) => {
            this._onRemoteBookingUpdate(payload);
        });
    },

    _onRemoteBookingUpdate(payload) {
        if (!payload || !payload.booking_data) return;
        const bookingData = payload.booking_data;
        const bookingModel = this.models["appointment.booking"];
        if (!bookingModel) return;

        const existing = bookingModel.get(bookingData.id);
        if (existing) {
            existing.state = bookingData.state;
            existing.party_size = bookingData.party_size;
            existing.guest_details = bookingData.notes;
            existing.table_ids = bookingData.table_ids;
            existing.start_datetime = bookingData.start_datetime;
            existing.end_datetime = bookingData.end_datetime;
        } else {
            bookingModel.createOrReplace(bookingData);
        }
    },

    addNewOrder(vals = {}) {
        const order = super.addNewOrder(...arguments);
        if (this.config.use_booking && order && order.table_id) {
            const table = order.table_id;
            const booking = table.getUpcomingBooking ? table.getUpcomingBooking() : null;
            if (booking && booking.state === "checked_in") {
                order.booking_id = booking;
                if (booking.partner_id && typeof order.set_partner === "function") {
                    order.set_partner(booking.partner_id);
                }
                if (booking.party_size) {
                    order.customer_count = booking.party_size;
                }
            }
        }
        return order;
    },

    async createBookingFromPos(vals) {
        if (!navigator.onLine) {
            this.dialog.add(_t("Network Offline"), {
                body: _t("Cannot create bookings while offline. Please check your connection."),
            });
            return null;
        }
        try {
            const res = await this.data.callRelated("pos.config", "pos_create_booking", [this.config.id, vals]);
            if (res && this.models["appointment.booking"]) {
                this.models["appointment.booking"].createOrReplace(res);
            }
            return res;
        } catch (error) {
            this.dialog.add(_t("Booking Error"), {
                body: error?.message?.data?.message || error?.message || _t("Failed to create booking."),
            });
            return null;
        }
    },

    async updateBookingFromPos(bookingId, vals) {
        if (!navigator.onLine) {
            this.dialog.add(_t("Network Offline"), {
                body: _t("Cannot update bookings while offline. Please check your connection."),
            });
            return null;
        }
        try {
            const res = await this.data.callRelated("pos.config", "pos_update_booking", [this.config.id, bookingId, vals]);
            if (res && this.models["appointment.booking"]) {
                this.models["appointment.booking"].createOrReplace(res);
            }
            return res;
        } catch (error) {
            this.dialog.add(_t("Update Error"), {
                body: error?.message?.data?.message || error?.message || _t("Failed to update booking."),
            });
            return null;
        }
    }
});

