import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { _t } from "@web/core/l10n/translation";

export class BookingScreen extends Component {
    static template = "hudson_pos_booking.BookingScreen";
    static components = {};

    setup() {
        this.pos = usePos();
        this.state = useState({
            isOnline: navigator.onLine,
            filterDate: "today", // 'today', 'tomorrow', 'all'
            showCreateModal: false,
            selectedBooking: null,
            draggedBookingId: null,
            newBooking: {
                customer_name: "",
                customer_phone: "",
                party_size: 2,
                table_id: "",
                start_time: "12:00",
                notes: "",
            }
        });

        onMounted(() => {
            window.addEventListener("online", () => { this.state.isOnline = true; });
            window.addEventListener("offline", () => { this.state.isOnline = false; });
        });
    }

    get isOnline() {
        return this.state.isOnline;
    }

    get allBookings() {
        const bookings = this.pos.models["appointment.booking"] || [];
        return bookings.filter(b => b.state !== "cancelled");
    }

    get filteredBookings() {
        const todayStr = luxon.DateTime.now().toFormat("yyyy-MM-dd");
        const tomorrowStr = luxon.DateTime.now().plus({ days: 1 }).toFormat("yyyy-MM-dd");

        return this.allBookings.filter(b => {
            const bDate = b.startDateStr;
            if (this.state.filterDate === "today") {
                return bDate === todayStr;
            } else if (this.state.filterDate === "tomorrow") {
                return bDate === tomorrowStr;
            }
            return true;
        });
    }

    get bookedList() {
        return this.filteredBookings.filter(b => b.state === "confirmed");
    }

    get checkedInList() {
        return this.filteredBookings.filter(b => b.state === "checked_in");
    }

    get noShowList() {
        return this.filteredBookings.filter(b => b.state === "no_show");
    }

    get availableTables() {
        return (this.pos.models["restaurant.table"] || []).filter(t => t.active);
    }

    backToFloor() {
        this.pos.navigate("FloorScreen");
    }

    // Drag and drop handlers
    onDragStart(ev, booking) {
        this.state.draggedBookingId = booking.id;
        ev.dataTransfer.setData("text/plain", booking.id.toString());
        ev.dataTransfer.effectAllowed = "move";
    }

    onDragOver(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
    }

    async onDrop(ev, targetState) {
        ev.preventDefault();
        const bookingId = this.state.draggedBookingId || parseInt(ev.dataTransfer.getData("text/plain"));
        this.state.draggedBookingId = null;

        if (!bookingId) return;
        const booking = this.pos.models["appointment.booking"].get(bookingId);
        if (!booking || booking.state === targetState) return;

        await this.pos.updateBookingFromPos(bookingId, { state: targetState });
    }

    // Status Actions
    async setBookingState(booking, newState) {
        await this.pos.updateBookingFromPos(booking.id, { state: newState });
    }

    async openTableOrder(booking) {
        const table = booking.tableRecords[0];
        if (!table) {
            this.pos.dialog.add(_t("No Table Assigned"), {
                body: _t("Please assign a table before opening the order."),
            });
            return;
        }
        await this.pos.setTableFromUi(table);
    }

    openCreateModal() {
        this.state.newBooking = {
            customer_name: "",
            customer_phone: "",
            party_size: 2,
            table_id: this.availableTables[0]?.id || "",
            start_time: luxon.DateTime.now().toFormat("HH:mm"),
            notes: "",
        };
        this.state.showCreateModal = true;
    }

    closeCreateModal() {
        this.state.showCreateModal = false;
    }

    async submitNewBooking() {
        const vals = {
            customer_name: this.state.newBooking.customer_name || _t("Walk-in Guest"),
            customer_phone: this.state.newBooking.customer_phone || "",
            party_size: parseInt(this.state.newBooking.party_size) || 1,
            table_id: parseInt(this.state.newBooking.table_id) || false,
            notes: this.state.newBooking.notes || "",
        };

        const todayStr = luxon.DateTime.now().toFormat("yyyy-MM-dd");
        vals.start_datetime = `${todayStr} ${this.state.newBooking.start_time}:00`;

        const res = await this.pos.createBookingFromPos(vals);
        if (res) {
            this.closeCreateModal();
        }
    }
}

registry.category("pos_pages").add("BookingScreen", {
    name: "BookingScreen",
    component: BookingScreen,
    route: `/pos/ui/${odoo.pos_config_id}/bookings`,
    params: {},
});

