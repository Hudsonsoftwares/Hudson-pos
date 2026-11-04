import { patch } from "@web/core/utils/patch";
import { RestaurantTable } from "@pos_restaurant/app/models/restaurant_table";

patch(RestaurantTable.prototype, {
    getActiveBookings() {
        if (!this.models["appointment.booking"]) {
            return [];
        }
        return this.models["appointment.booking"].filter(b => {
            if (!["confirmed", "checked_in"].includes(b.state)) {
                return false;
            }
            const tableIds = Array.isArray(b.table_ids)
                ? b.table_ids.map(t => (typeof t === "object" && t ? t.id : t))
                : [];
            return tableIds.includes(this.id);
        });
    },

    getUpcomingBooking() {
        const bookings = this.getActiveBookings();
        if (!bookings.length) {
            return null;
        }
        // Prioritize checked_in, then earliest confirmed
        const checkedIn = bookings.find(b => b.state === "checked_in");
        if (checkedIn) {
            return checkedIn;
        }
        return bookings.sort((a, b) => (a.start_datetime > b.start_datetime ? 1 : -1))[0];
    }
});

