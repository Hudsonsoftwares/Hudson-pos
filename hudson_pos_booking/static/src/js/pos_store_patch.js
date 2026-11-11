import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { getOnNotified } from "@point_of_sale/utils";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

function upsertBooking(posStore, data) {
    if (!data) return;
    const bookingData = (data["appointment.booking"] && Array.isArray(data["appointment.booking"]))
        ? data["appointment.booking"][0]
        : data;
    if (!bookingData || !bookingData.id) return;
    try {
        const bookingModel = posStore.models?.["appointment.booking"];
        if (bookingModel) {
            const existing = typeof bookingModel.get === "function" ? bookingModel.get(bookingData.id) : null;
            if (existing) {
                if (typeof existing.update === "function") {
                    existing.update(bookingData);
                }
                Object.assign(existing, bookingData);
            }
        }
        if (posStore.models && typeof posStore.models.connectNewData === "function") {
            posStore.models.connectNewData({ "appointment.booking": [bookingData] });
        }
    } catch (err) {
        console.warn("Could not upsert booking into pos model:", err);
    }
}

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
        upsertBooking(this, payload.booking_data);
    },

    ensureBookingSettledAndNamed(order) {
        if (!order || order.finalized) return;
        // 1. Resolve booking
        let booking = order.booking_id;
        if (typeof booking === "number") {
            booking = this.models["appointment.booking"]?.get?.(booking) || null;
            if (booking) order.booking_id = booking;
        }
        if (!booking && order.table_id) {
            const table = typeof order.table_id === "object" ? order.table_id : this.models["restaurant.table"]?.get?.(order.table_id);
            if (table && table.getUpcomingBooking) {
                booking = table.getUpcomingBooking();
                if (booking) order.booking_id = booking;
            }
        }
        if (!booking) return;

        // 2. Resolve guest partner (Never use internal company partner)
        const partnerId = typeof booking.partner_id === "object" && booking.partner_id ? (booking.partner_id.id || booking.partner_id[0]) : booking.partner_id;
        let partner = (partnerId && this.models["res.partner"]?.get) ? this.models["res.partner"].get(partnerId) : null;
        if (partner && (!order.partner_id || order.partner_id.id === 1 || order.partner_id.name === "Resto Cafe")) {
            if (typeof order.setPartner === "function") {
                order.setPartner(partner);
            } else {
                order.partner_id = partner;
            }
        }

        // 3. Customer count
        if (booking.party_size && !order.customer_count) {
            order.customer_count = booking.party_size;
        }

        // 4. Pre-ordered food items: If already prepaid online, discount them 100% (Free - Prepaid Online)
        // so the POS order total and payment screen only charge for newly added EXTRA items!
        const hasFood = Boolean(
            booking.has_food_order || 
            (parseFloat(booking.prepaid_food_total || booking.food_order_total) > 0) ||
            (Array.isArray(booking.food_order_details) && booking.food_order_details.length > 0)
        );
        const isPrepaid = hasFood && ["confirmed", "checked_in", "checked_out"].includes(booking.state);

        const orderLines = (typeof order.getOrderlines === "function" ? order.getOrderlines() : order.lines) || [];
        if (isPrepaid && orderLines.length > 0) {
            const details = Array.isArray(booking.food_order_details) ? booking.food_order_details : [];
            const preorderMap = new Map();
            for (const item of details) {
                const pid = typeof item.product_id === "object" ? (item.product_id?.id || item.product_id[0]) : item.product_id;
                if (pid) {
                    const numPid = Number(pid);
                    preorderMap.set(numPid, (preorderMap.get(numPid) || 0) + (parseFloat(item.qty) || 1));
                }
            }

            const usedQtyMap = new Map();
            for (const line of orderLines) {
                const pid = (typeof line.product_id === "object" && line.product_id) ? line.product_id.id : line.product_id;
                const numPid = Number(pid);
                const preQty = preorderMap.get(numPid) || 0;
                const used = usedQtyMap.get(numPid) || 0;
                const remainingPreQty = Math.max(0, preQty - used);

                if (remainingPreQty > 0 || line.is_booking_prepaid || preorderMap.has(numPid)) {
                    const lineQty = parseFloat(line.qty) || 0;
                    const matchQty = Math.min(lineQty, remainingPreQty > 0 ? remainingPreQty : lineQty);
                    usedQtyMap.set(numPid, used + matchQty);

                    line.is_booking_prepaid = true;
                    if (typeof line.setDiscount === "function") {
                        line.setDiscount(100);
                    } else {
                        line.discount = 100;
                    }
                    if (line.combo_line_ids) {
                        for (const cl of line.combo_line_ids) {
                            if (typeof cl.setDiscount === "function") cl.setDiscount(100);
                            else cl.discount = 100;
                        }
                    }
                    const noteText = "Prepaid Online (Booking #" + booking.id + ")";
                    if (!line.customer_note || !line.customer_note.includes("Prepaid Online")) {
                        if (typeof line.setCustomerNote === "function") {
                            line.setCustomerNote(noteText);
                        } else {
                            line.customer_note = noteText;
                        }
                    }
                }
            }

            // Remove any legacy artificial 'is_booking_prepaid' payment lines from the order
            if (order.payment_ids && order.payment_ids.length > 0) {
                const prepaidPaylines = order.payment_ids.filter(p => p.is_booking_prepaid);
                for (const pl of prepaidPaylines) {
                    try {
                        if (typeof order.removePaymentline === "function") {
                            order.removePaymentline(pl);
                        } else if (typeof pl.delete === "function") {
                            pl.delete();
                        }
                    } catch (e) {
                        console.warn("Could not remove prepaid payment line:", e);
                    }
                }
            }
        }
    },

    async setTableFromUi(table, orderUuid = null, isFromBooking = false) {
        if (!orderUuid && !isFromBooking && this.config.use_booking && table) {
            const existingOrders = this.getTableOrders(table.id) || [];
            // If there is an existing active order for this table, let standard POS handle it
            if (existingOrders.length > 0) {
                return super.setTableFromUi(table, orderUuid);
            }
            // Only auto-load if a booking on this table is ALREADY checked_in
            const booking = table.getUpcomingBooking ? table.getUpcomingBooking() : null;
            if (booking && booking.state === "checked_in") {
                await this.loadBookingIntoTable(booking, table);
                return;
            }
        }
        return super.setTableFromUi(table, orderUuid);
    },

    async loadBookingIntoTable(booking, table) {
        if (!booking || !table) return;

        // 1. Check in booking if confirmed
        if (booking.state === "confirmed") {
            await this.updateBookingFromPos(booking.id, { state: "checked_in" });
        }

        // 2. Clear any lingering stale draft order from table that is NOT for this booking
        const existingTableOrders = this.getTableOrders(table.id) || [];
        let matchingOrder = null;
        for (const o of existingTableOrders) {
            if (!o.finalized) {
                if (o.booking_id && o.booking_id.id === booking.id) {
                    matchingOrder = o;
                } else if (!o.lines || o.lines.length === 0) {
                    this.removeOrder(o);
                }
            }
        }

        // 3. Switch to table
        if (!matchingOrder) {
            await this.setTableFromUi(table, null, true);
        } else {
            this.setOrder(matchingOrder);
        }
        const order = matchingOrder || this.getOrder();
        if (!order) return;

        // 4. Attach booking to order
        order.booking_id = booking;

        // 5. Customer partner
        const partnerId = typeof booking.partner_id === "object" && booking.partner_id ? (booking.partner_id.id || booking.partner_id[0]) : booking.partner_id;
        let partner = (partnerId && this.models["res.partner"]?.get) ? this.models["res.partner"].get(partnerId) : null;
        if (partner) {
            if (typeof order.setPartner === "function") {
                order.setPartner(partner);
            } else {
                order.partner_id = partner;
            }
        }

        // 6. Customer count
        if (booking.party_size) {
            order.customer_count = booking.party_size;
        }

        // 7. Auto-load pre-ordered food items if cart is empty
        if (Array.isArray(booking.food_order_details) && booking.food_order_details.length > 0 && (!order.lines || order.lines.length === 0)) {
            const productModel = this.models["product.product"];
            const templateModel = this.models["product.template"];
            const hasFood = Boolean(
                booking.has_food_order || 
                (parseFloat(booking.prepaid_food_total || booking.food_order_total) > 0) ||
                (Array.isArray(booking.food_order_details) && booking.food_order_details.length > 0)
            );
            const isPrepaid = hasFood && ["confirmed", "checked_in", "checked_out"].includes(booking.state);
            for (const item of booking.food_order_details) {
                const pid = typeof item.product_id === "object" ? (item.product_id?.id || item.product_id[0]) : item.product_id;
                const product = productModel?.get ? productModel.get(pid) : (productModel?.getAll?.()?.find(p => p.id === pid));
                if (product) {
                    const tmplId = product.product_tmpl_id?.id || product.product_tmpl_id;
                    const productTemplate = (templateModel?.get ? templateModel.get(tmplId) : null) || product.product_tmpl_id;
                    try {
                        const lineVals = {
                            product_id: product,
                            product_tmpl_id: productTemplate,
                            qty: item.qty || 1,
                        };
                        if (isPrepaid) {
                            lineVals.discount = 100;
                            lineVals.customer_note = "Prepaid Online (Booking #" + booking.id + ")";
                        }
                        const line = await this.addLineToOrder(lineVals, order, {}, false);
                        if (line && isPrepaid) {
                            if (typeof line.setDiscount === "function") line.setDiscount(100);
                            else line.discount = 100;
                            if (line.combo_line_ids) {
                                for (const cl of line.combo_line_ids) {
                                    if (typeof cl.setDiscount === "function") cl.setDiscount(100);
                                    else cl.discount = 100;
                                }
                            }
                            line.is_booking_prepaid = true;
                        }
                    } catch (e) {
                        console.warn("Could not auto-add dish:", e);
                    }
                }
            }
        }

        // 8. Auto-settle prepaid booking
        this.ensureBookingSettledAndNamed(order);

        // 9. Navigate to ProductScreen to display order lines, guest name and total
        this.navigate("ProductScreen", { orderUuid: order.uuid });
    },

    async releaseTable(table, booking = null) {
        if (!table) return;
        const tableObj = (typeof table === "object" && table) ? table : (this.models["restaurant.table"]?.get?.(table) || { id: table });
        const tableId = tableObj.id || table;

        // 1. Resolve booking ID accurately
        let bId = booking ? (typeof booking === "object" ? booking.id : booking) : false;
        const currentOrder = this.getOrder();
        if (!bId && currentOrder) {
            const curTblId = typeof currentOrder.table_id === "object" ? currentOrder.table_id?.id : currentOrder.table_id;
            if (curTblId === tableId && currentOrder.booking_id) {
                bId = typeof currentOrder.booking_id === "object" ? currentOrder.booking_id.id : currentOrder.booking_id;
            }
        }
        if (!bId && tableObj.getUpcomingBooking) {
            const upB = tableObj.getUpcomingBooking();
            if (upB && (upB.state === "checked_in" || upB.state === "confirmed")) {
                bId = upB.id;
            }
        }

        try {
            const orm = this.data?.orm || this.env?.services?.orm;
            if (orm) {
                await orm.call("pos.config", "pos_release_table", [this.config.id, tableId, bId]);
            } else if (this.data?.call) {
                await this.data.call("pos.config", "pos_release_table", [this.config.id, tableId, bId]);
            }

            // 2. Remove all unfinalized orders on this table locally so the table is completely released and freed!
            const ordersToRemove = [];
            if (this.models["pos.order"]) {
                const tableOrders = this.models["pos.order"].filter(o => {
                    const oTblId = typeof o.table_id === "object" ? o.table_id?.id : o.table_id;
                    return oTblId === tableId && !o.finalized && o.state !== "cancel";
                });
                ordersToRemove.push(...tableOrders);
            }
            if (currentOrder) {
                const curTblId = typeof currentOrder.table_id === "object" ? currentOrder.table_id?.id : currentOrder.table_id;
                if (curTblId === tableId && !ordersToRemove.includes(currentOrder)) {
                    ordersToRemove.push(currentOrder);
                }
            }
            for (const o of ordersToRemove) {
                try {
                    o.state = "cancel";
                    this.removeOrder(o, false);
                    this.removePendingOrder(o);
                } catch (err) {
                    console.warn("Could not remove order on table release:", err);
                }
            }

            // 3. Update local booking state to checked_out for all bookings on this table
            if (bId && this.models["appointment.booking"]?.get) {
                const b = this.models["appointment.booking"].get(bId);
                if (b) {
                    b.state = "checked_out";
                }
            }
            if (this.models["appointment.booking"]?.getAll) {
                const allB = this.models["appointment.booking"].getAll();
                for (const b of allB) {
                    const bTblIds = Array.isArray(b.table_ids)
                        ? b.table_ids.map(t => (typeof t === "object" && t ? t.id : t))
                        : [];
                    if (bTblIds.includes(tableId) && ["confirmed", "checked_in"].includes(b.state)) {
                        b.state = "checked_out";
                    }
                }
            }
            if (tableObj.getUpcomingBooking) {
                const upB = tableObj.getUpcomingBooking();
                if (upB) {
                    upB.state = "checked_out";
                }
            }

            // 4. Reset table ui state so floor plan immediately renders table as free
            if (tableObj.uiState) {
                tableObj.uiState.orderCount = 0;
                tableObj.uiState.changeCount = 0;
            }
            if (typeof this.computeTableCount === "function") {
                this.computeTableCount();
            }

            // 5. Unset active order if it belonged to this table and navigate to FloorScreen
            if (this.getOrder() && ordersToRemove.includes(this.getOrder())) {
                this.setOrder(this.getOpenOrders().find(o => !ordersToRemove.includes(o)) || null);
            }
            this.navigate("FloorScreen");
        } catch (err) {
            console.error("Error releasing table:", err);
            if (tableObj.uiState) {
                tableObj.uiState.orderCount = 0;
            }
            if (typeof this.computeTableCount === "function") {
                this.computeTableCount();
            }
            this.navigate("FloorScreen");
        }
    },

    async orderDone(order) {
        super.orderDone(...arguments);
        if (this.config.module_pos_restaurant && order?.table_id) {
            this.navigate("FloorScreen");
        }
    },

    addNewOrder(vals = {}) {
        const order = super.addNewOrder(...arguments);
        if (this.config.use_booking && order) {
            this.ensureBookingSettledAndNamed(order);
        }
        return order;
    },

    setOrder(order) {
        super.setOrder(...arguments);
        if (order && !order.finalized && this.config.use_booking) {
            this.ensureBookingSettledAndNamed(order);
        }
    },

    async setTable(table, order = null) {
        await super.setTable(...arguments);
        if (this.config.use_booking && table) {
            const currentOrder = this.getOrder();
            if (currentOrder) {
                this.ensureBookingSettledAndNamed(currentOrder);
            }
        }
    },

    navigate(screen, props) {
        if (screen === "PaymentScreen" && this.config.use_booking) {
            const currentOrder = this.getOrder();
            if (currentOrder && !currentOrder.finalized) {
                this.ensureBookingSettledAndNamed(currentOrder);
            }
        }
        return super.navigate(...arguments);
    },

    async pay() {
        if (this.config.use_booking) {
            const currentOrder = this.getOrder();
            if (currentOrder && !currentOrder.finalized) {
                this.ensureBookingSettledAndNamed(currentOrder);
            }
        }
        return super.pay ? super.pay(...arguments) : null;
    },

    async createBookingFromPos(vals) {
        if (!navigator.onLine) {
            this.dialog.add(AlertDialog, {
                title: _t("Network Offline"),
                body: _t("Cannot create bookings while offline. Please check your connection."),
            });
            return null;
        }
        try {
            const orm = this.data?.orm || this.env?.services?.orm;
            const res = orm
                ? await orm.call("pos.config", "pos_create_booking", [this.config.id, vals])
                : await this.data.call("pos.config", "pos_create_booking", [this.config.id, vals]);
            if (res) {
                upsertBooking(this, res);
            }
            return res;
        } catch (error) {
            this.dialog.add(AlertDialog, {
                title: _t("Booking Error"),
                body: error?.message?.data?.message || error?.message || _t("Failed to create booking."),
            });
            return null;
        }
    },

    async updateBookingFromPos(bookingId, vals) {
        if (!navigator.onLine) {
            this.dialog.add(AlertDialog, {
                title: _t("Network Offline"),
                body: _t("Cannot update bookings while offline. Please check your connection."),
            });
            return null;
        }
        try {
            const orm = this.data?.orm || this.env?.services?.orm;
            const res = orm
                ? await orm.call("pos.config", "pos_update_booking", [this.config.id, bookingId, vals])
                : await this.data.call("pos.config", "pos_update_booking", [this.config.id, bookingId, vals]);
            if (res) {
                upsertBooking(this, res);
            }
            return res;
        } catch (error) {
            this.dialog.add(AlertDialog, {
                title: _t("Update Error"),
                body: error?.message?.data?.message || error?.message || _t("Failed to update booking."),
            });
            return null;
        }
    }
});
