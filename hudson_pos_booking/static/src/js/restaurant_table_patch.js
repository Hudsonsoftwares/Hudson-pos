import { patch } from "@web/core/utils/patch";
import { LazyTranslatedString } from "@web/core/l10n/translation";
import { RestaurantTable } from "@pos_restaurant/app/models/restaurant_table";
import { FloorPlan } from "@pos_restaurant/app/screens/floor_screen/floor_plan/floor_plan";
import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { OrderDisplay } from "@point_of_sale/app/components/order_display/order_display";
import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { PosDataPlugin } from "@point_of_sale/app/plugins/pos_data_plugin";

// Guard against TypeError in pos_loyalty sanitizeData when order.lines is undefined
patch(PosDataPlugin.prototype, {
    sanitizeData() {
        if (!this.models?.["pos.order"]) return;
        const order_to_delete = this.models["pos.order"].filter((order) =>
            order.lines && Array.isArray(order.lines) && order.lines.some((line) => line && line.is_reward_line && !line.card_id && !line.reward_id)
        );
        for (const order of order_to_delete) {
            if (order.lines) {
                for (let i = order.lines.length - 1; i >= 0; i--) {
                    order.lines[i]?.delete?.();
                }
            }
        }
    },
});

// Safely handle internal_note in OrderDisplay to prevent JSON.parse SyntaxError when plain text is present
patch(OrderDisplay.prototype, {
    getInternalNotes() {
        const raw = this.props.order?.internal_note;
        if (!raw) return [];
        try {
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed)) return parsed;
            return [{ text: String(parsed), colorIndex: 1 }];
        } catch {
            return [{ text: String(raw), colorIndex: 1 }];
        }
    },
});

// Guard against TypeError when lines relation is undefined during initial setup of PosOrder
// and ensure guest customer name is displayed on orders
patch(PosOrder.prototype, {
    _computeAllPrices(opts = {}) {
        const lines = (opts && opts.lines) || this.lines;
        if (!lines || !Array.isArray(lines)) {
            opts = { ...opts, lines: [] };
        }
        return super._computeAllPrices(opts);
    },

    getPartner() {
        const partner = super.getPartner();
        if ((!partner || partner.id === 1 || partner.name === "Resto Cafe") && this.booking_id) {
            const bPartner = this.booking_id.partner_id;
            if (bPartner && bPartner.name !== "Resto Cafe") {
                return bPartner;
            }
        }
        return partner;
    },

    getPartnerName() {
        if (this.booking_id && this.booking_id.customerDisplayName) {
            return this.booking_id.customerDisplayName;
        }
        return super.getPartnerName();
    },

    getName() {
        const base = super.getName();
        if (this.booking_id && this.booking_id.customerDisplayName) {
            const guest = this.booking_id.customerDisplayName;
            if (guest && !base.includes(guest)) {
                return `${base} (${guest})`;
            }
        }
        return base;
    },
});

// Auto-settle payment and prioritize guest partner on TicketScreen Load Order
patch(TicketScreen.prototype, {
    async setOrder(order) {
        if (order && this.pos.ensureBookingSettledAndNamed) {
            this.pos.ensureBookingSettledAndNamed(order);
        }
        await super.setOrder(...arguments);
        if (order && order.booking_id && order.booking_id.has_food_order && (order.orderHasZeroRemaining || (order.remainingDue <= 0 && order.payment_ids.length > 0))) {
            this.pos.navigate("PaymentScreen", { orderUuid: order.uuid });
        }
    },
});

// Ensure payment lines and guest partner are ready upon entering PaymentScreen
patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.currentOrder && this.pos.ensureBookingSettledAndNamed) {
            this.pos.ensureBookingSettledAndNamed(this.currentOrder);
        }
    },
});

// Safely handle string translation calls before translations finish loading (prevents startup crash)
patch(LazyTranslatedString.prototype, {
    translate() {
        try {
            return super.translate();
        } catch {
            return super.valueOf();
        }
    },
});

patch(RestaurantTable.prototype, {
    // Null-safe getOrder() to avoid TypeError when backLink("<-pos.order.table_id") is undefined during floor plan render
    getOrder() {
        const parentOrder = this.parent_id?.getOrder?.();
        if (parentOrder) {
            return parentOrder;
        }
        const backOrders = this.backLink?.("<-pos.order.table_id");
        if (Array.isArray(backOrders)) {
            return backOrders.find((o) => !o.finalized);
        }
        if (this.models?.["pos.order"]) {
            return this.models["pos.order"].find((o) => o.table_id?.id === this.id && !o.finalized);
        }
        return null;
    },

    getOrders() {
        if (!this.models?.["pos.order"]) {
            return [];
        }
        return super.getOrders();
    },

    getActiveBookings() {
        if (!this.models["appointment.booking"]) {
            return [];
        }
        const todayStr = luxon.DateTime.now().toFormat("yyyy-MM-dd");
        return this.models["appointment.booking"].filter(b => {
            if (!b || !["confirmed", "checked_in"].includes(b.state)) {
                return false;
            }
            // Strictly ONLY bookings for TODAY are active on the POS floor plan
            const bDate = b.startDateStr;
            if (!bDate || bDate !== todayStr) {
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
        // Prioritize checked_in today, then earliest confirmed today
        const checkedIn = bookings.find(b => b.state === "checked_in");
        if (checkedIn) {
            return checkedIn;
        }
        return bookings.sort((a, b) => ((a.startTimestamp || 0) - (b.startTimestamp || 0)))[0];
    }
});

// Fix upstream Odoo bug where window resize triggers ensureBoardFits when containerRef is null/unmounted
patch(FloorPlan.prototype, {
    ensureBoardFits() {
        const scrollContainer = this.containerRef?.();
        if (!this.selectedFloor || this.isKanban || !scrollContainer || !this.canvasRef?.()) {
            return;
        }
        super.ensureBoardFits();
    },
});
