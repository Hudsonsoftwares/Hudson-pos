import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import OrderPaymentValidation from "@point_of_sale/app/utils/order_payment_validation";
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
        if (posStore.models && typeof posStore.models.connectNewData === "function") {
            posStore.models.connectNewData({ "appointment.booking": [bookingData] });
            return;
        }
        const bookingModel = posStore.models?.["appointment.booking"];
        const existing = typeof bookingModel?.get === "function" ? bookingModel.get(bookingData.id) : null;
        if (existing && typeof existing.update === "function") {
            existing.update(bookingData, { omitUnknownField: true });
        }
    } catch (err) {
        console.warn("Could not upsert booking into pos model:", err);
    }
}

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        if (this.config.use_booking && (this.data || this.bus)) {
            this._setupBookingBusListener();
        }
    },

    _setupBookingBusListener() {
        if (!this.config?.access_token) return;
        if (this.data && typeof this.data.connectWebSocket === "function") {
            this.data.connectWebSocket("BOOKING_UPDATE", (payload) => {
                this._onRemoteBookingUpdate(payload);
            });
        } else if (this.bus) {
            const onNotified = getOnNotified(this.bus, this.config.access_token);
            onNotified("BOOKING_UPDATE", (payload) => {
                this._onRemoteBookingUpdate(payload);
            });
        }
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
                const upcoming = table.getUpcomingBooking();
                if (upcoming && upcoming.state === "checked_in") {
                    booking = upcoming;
                    order.booking_id = booking;
                }
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

    async autoReleaseTableAfterPayment(order, { suggestToSync = true, extraTableIds = [] } = {}) {
        if (!order || order.is_refund) return;

        const rawTable = order.table_id;
        const primaryTableId = typeof rawTable === "object" && rawTable ? rawTable.id : rawTable;
        const tableModel = this.models?.["restaurant.table"];
        const tableObj = (typeof rawTable === "object" && rawTable)
            ? rawTable
            : (primaryTableId && tableModel?.get ? tableModel.get(primaryTableId) : null);

        // Collect the physical table and any merged parent/child tables involved
        const orderTableIds = new Set();
        const addTableId = (tbl) => {
            const tid = typeof tbl === "object" && tbl ? tbl.id : tbl;
            if (typeof tid === "number" && tid > 0) {
                orderTableIds.add(tid);
            }
        };
        addTableId(primaryTableId);
        if (tableObj?.parent_id) addTableId(tableObj.parent_id);
        if (tableObj?.rootTable) addTableId(tableObj.rootTable);
        if (Array.isArray(tableObj?.children)) {
            for (const ch of tableObj.children) addTableId(ch);
        }
        if (Array.isArray(extraTableIds)) {
            for (const eid of extraTableIds) addTableId(eid);
        }

        // Resolve linked booking on the order
        let linkedBooking = order.booking_id || null;
        if (typeof linkedBooking === "number") {
            linkedBooking = this.models?.["appointment.booking"]?.get?.(linkedBooking) || null;
        }
        const linkedBookingId = linkedBooking?.id || (typeof order.booking_id === "number" ? order.booking_id : null);

        const posOrderModel = this.models?.["pos.order"];
        const allPosOrders = posOrderModel?.getAll
            ? posOrderModel.getAll()
            : (Array.isArray(posOrderModel) ? posOrderModel : []);

        // 1. Guard against open split bills on the same table(s) or booking
        const otherDraftsOnTable = orderTableIds.size
            ? allPosOrders.filter(o => {
                if (!o || o.uuid === order.uuid || o.finalized || o.state === "cancel") return false;
                const oTblId = typeof o.table_id === "object" && o.table_id ? o.table_id.id : o.table_id;
                return Boolean(oTblId && orderTableIds.has(oTblId));
            })
            : [];
        const otherOpenWithLines = otherDraftsOnTable.filter(o => o.lines && o.lines.length > 0);
        if (otherOpenWithLines.length > 0) {
            if (typeof this.computeTableCount === "function") {
                this.computeTableCount();
            }
            return;
        }

        if (linkedBookingId) {
            const otherBookingOpen = allPosOrders.some(o => {
                if (!o || o.uuid === order.uuid || o.finalized || o.state === "cancel") return false;
                const oBookingId = typeof o.booking_id === "object" && o.booking_id ? o.booking_id.id : o.booking_id;
                return oBookingId === linkedBookingId && o.lines && o.lines.length > 0;
            });
            if (otherBookingOpen) {
                if (typeof this.computeTableCount === "function") {
                    this.computeTableCount();
                }
                return;
            }
        }

        // 2. Clear any lingering empty orphan draft orders on these tables (preserve paid `order` itself!)
        for (const orphan of otherDraftsOnTable) {
            try {
                if (orphan.isSynced) {
                    orphan.state = "cancel";
                    this.removeOrder?.(orphan, false);
                } else {
                    // Delete local unsynced draft before marking cancel so removeOrder cascades cleanly
                    this.removeOrder?.(orphan, false);
                    orphan.state = "cancel";
                }
                this.removePendingOrder?.(orphan);
            } catch (err) {
                console.warn("Could not clear empty draft order on table auto-release:", err);
            }
        }

        // 3. Check out linked booking and any actively checked_in bookings on the freed table(s)
        let hadServerCheckOutNeeded = false;
        if (linkedBooking && ["confirmed", "checked_in"].includes(linkedBooking.state)) {
            linkedBooking.state = "checked_out";
            hadServerCheckOutNeeded = true;
        }

        const bookingModel = this.models?.["appointment.booking"];
        const allBookings = bookingModel?.getAll
            ? bookingModel.getAll()
            : (Array.isArray(bookingModel) ? bookingModel : []);
        for (const b of allBookings) {
            if (!b || b.state !== "checked_in") continue;
            const rawTables = Array.isArray(b.tableRecords) && b.tableRecords.length
                ? b.tableRecords
                : (Array.isArray(b.table_ids)
                    ? b.table_ids
                    : (b.table_ids && typeof b.table_ids[Symbol.iterator] === "function"
                        ? Array.from(b.table_ids)
                        : []));
            const bTblIds = rawTables.map(t => (typeof t === "object" && t ? t.id : t));
            if (bTblIds.some(tid => orderTableIds.has(tid))) {
                b.state = "checked_out";
                hadServerCheckOutNeeded = true;
            }
        }

        // 4. Reset table UI counters so FloorScreen shows the table completely free immediately
        for (const tid of orderTableIds) {
            const tbl = tableModel?.get ? tableModel.get(tid) : (tid === primaryTableId ? tableObj : null);
            if (tbl?.uiState) {
                tbl.uiState.orderCount = 0;
                tbl.uiState.changeCount = 0;
            }
        }
        if (typeof this.computeTableCount === "function") {
            this.computeTableCount();
        }

        // 5. Fallback server release only if online sync_from_ui didn't run on validation (e.g. post_validate redirect)
        if (!suggestToSync && hadServerCheckOutNeeded && primaryTableId && typeof navigator !== "undefined" && navigator.onLine && !this.data?.network?.offline) {
            try {
                const orm = this.data?.orm || this.env?.services?.orm;
                if (orm) {
                    await orm.call("pos.config", "pos_release_table", [this.config.id, primaryTableId, linkedBookingId || false]);
                } else if (this.data?.call) {
                    await this.data.call("pos.config", "pos_release_table", [this.config.id, primaryTableId, linkedBookingId || false]);
                }
            } catch (err) {
                console.warn("Could not sync fallback table release on payment validation:", err);
            }
        }
    },

    orderDone(order) {
        super.orderDone(...arguments);
        if (this.config.module_pos_restaurant && order?.table_id) {
            if (typeof this.computeTableCount === "function") {
                this.computeTableCount();
            }
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

patch(OrderPaymentValidation.prototype, {
    async afterOrderValidation(suggestToSync = true) {
        const mergedChildIds = (this.order?.table_id?.children || []).map(
            (table) => (typeof table === "object" && table ? table.id : table)
        ).filter(Boolean);
        const res = await super.afterOrderValidation(...arguments);
        if (this.pos?.config?.use_booking && this.order) {
            await this.pos.autoReleaseTableAfterPayment(this.order, {
                suggestToSync,
                extraTableIds: mergedChildIds,
            });
        } else if (
            this.pos?.config?.module_pos_restaurant &&
            typeof this.pos?.computeTableCount === "function"
        ) {
            this.pos.computeTableCount();
        }
        return res;
    },
});
