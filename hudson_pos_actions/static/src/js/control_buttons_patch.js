import { patch } from "@web/core/utils/patch";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { NoteButton } from "@point_of_sale/app/screens/product_screen/control_buttons/orderline_note_button/orderline_note_button";
import { OrderDisplay } from "@point_of_sale/app/components/order_display/order_display";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";
import { _t } from "@web/core/l10n/translation";

patch(NoteButton.prototype, {
    async onClick() {
        const order = this.pos.getOrder();
        if (!order) return;
        const selectedOrderline = order.getSelectedOrderline ? order.getSelectedOrderline() : null;
        const selectedNote = this.currentNote || "";
        const payload = await this.openTextInput(selectedNote);

        if (typeof payload === "string") {
            const trimmedNote = payload.trim();
            if (selectedOrderline) {
                this.setChanges(selectedOrderline, trimmedNote);
            } else {
                order.general_customer_note = trimmedNote;
            }

            try {
                await this.pos.data.callRelated("pos.order", "save_customer_note_from_pos", [{
                    uuid: order.uuid,
                    note: trimmedNote,
                    partner_id: order.getPartner ? order.getPartner()?.id : (order.partner_id?.id || false),
                }]);
            } catch (err) {
                console.warn("Could not save customer note to server immediately:", err);
            }

            this.notification?.add?.(_t("Customer note saved."), { type: "success" });
            this.dialog?.closeAll?.();
        }
        return { confirmed: typeof payload === "string", inputNote: payload };
    },
});

patch(ControlButtons.prototype, {
    get showAddCourse() {
        // Course button is strictly for bar/restaurant POS configurations
        return (
            Boolean(this.pos.config?.module_pos_restaurant) &&
            !this.props.showRemainingButtons &&
            !this.pos.getOrder()?.isRefund
        );
    },

    get showRetailQuotation() {
        // Quotation / Order button is directly shown for retail POS (Clothes, Furniture, etc.)
        return (
            !this.pos.config?.module_pos_restaurant &&
            !this.props.showRemainingButtons
        );
    },

    async clickRetailQuotation() {
        // 1. Try standard pos_sale onClickQuotation if available
        if (typeof this.onClickQuotation === "function") {
            try {
                return await this.onClickQuotation();
            } catch (err) {
                console.warn("onClickQuotation threw an error, using direct SelectCreateDialog fallback:", err);
            }
        }

        // 2. Direct resilient fallback to SelectCreateDialog for sale.order
        const order = this.pos.getOrder();
        const partner = this.partner || (order?.getPartner ? order?.getPartner() : order?.partner_id);
        const context = {};
        if (partner && partner.id) {
            context["search_default_partner_id"] = partner.id;
        }

        const currencyId = this.pos.currency?.id || this.pos.config?.currency_id?.[0] || this.pos.config?.currency_id || this.pos.company?.currency_id?.[0] || this.pos.company?.currency_id;
        const domain = [
            ["state", "!=", "cancel"],
            ["invoice_status", "!=", "invoiced"],
            ["amount_unpaid", ">", 0],
        ];
        if (currencyId) {
            domain.push(["currency_id", "=", currencyId]);
        }

        const saleOrderIds = order?.lines?.map((l) => l.sale_order_origin_id?.id).filter(Boolean);
        if (saleOrderIds && saleOrderIds.length) {
            domain.push(["id", "not in", saleOrderIds]);
        }

        this.dialog.add(SelectCreateDialog, {
            title: _t("Quotation / Order"),
            resModel: "sale.order",
            noCreate: true,
            multiSelect: false,
            domain,
            context: context,
            onSelected: async (resIds) => {
                if (resIds && resIds.length && typeof this.pos.onClickSaleOrder === "function") {
                    await this.pos.onClickSaleOrder(resIds[0]);
                }
            },
        });
    },

    async saveCurrentOrderAsQuotation() {
        const order = this.pos.getOrder();
        if (!order || !order.lines || !order.lines.length) {
            this.notification?.add?.(_t("Cart is empty."), { type: "warning" });
            return;
        }

        const partner = order.getPartner ? order.getPartner() : (order.partner_id || false);
        if (!partner) {
            this.notification?.add?.(_t("Please select a Customer first before saving as quotation."), { type: "warning" });
            return;
        }

        const linesData = order.lines.map((line) => ({
            product_id: line.product_id?.id || line.product?.id,
            qty: line.get_quantity ? line.get_quantity() : (line.qty || 1.0),
            price_unit: line.get_unit_price ? line.get_unit_price() : (line.price_unit || 0.0),
            discount: line.get_discount ? line.get_discount() : (line.discount || 0.0),
        })).filter((l) => Boolean(l.product_id));

        try {
            const res = await this.pos.data.callRelated("pos.order", "create_sale_quotation_from_pos", [{
                partner_id: partner.id,
                company_id: this.pos.company?.id,
                pricelist_id: order.pricelist_id?.id || false,
                pos_reference: order.name || _t("Retail Cart"),
                lines: linesData,
            }]);

            if (res && res.success) {
                this.notification?.add?.(res.message || _t("Quotation created successfully!"), { type: "success" });
            } else {
                this.notification?.add?.(res?.message || _t("Could not create quotation."), { type: "danger" });
            }
        } catch (err) {
            console.error("Failed to save quotation:", err);
            this.notification?.add?.(_t("Failed to create quotation in Sales: ") + (err?.message || ""), { type: "danger" });
        }
    },

    clickAddCourse() {
        const order = this.pos.getOrder();
        if (!order) return;

        if (typeof this.pos.addCourse === "function") {
            this.pos.addCourse();
        } else {
            // Direct fallback
            const nextIdx = order.getNextCourseIndex ? order.getNextCourseIndex() : ((order.course_ids?.length || 0) + 1);
            const courseModel = this.pos.data?.models?.["restaurant.order.course"];
            if (courseModel) {
                const course = courseModel.create({
                    order_id: order,
                    index: nextIdx,
                    name: _t("Course ") + nextIdx,
                });
                if (order.course_ids?.length === 1 && order.lines?.length > 0) {
                    order.lines.forEach((line) => {
                        if (!line.isServiceFeeLine || !line.isServiceFeeLine()) {
                            line.course_id = course;
                        }
                    });
                    const course2 = courseModel.create({
                        order_id: order,
                        index: order.getNextCourseIndex ? order.getNextCourseIndex() : 2,
                        name: _t("Course 2"),
                    });
                    order.selectCourse(course2);
                } else {
                    order.selectCourse(course);
                }
            }
        }
    },

    async clickPrintBill() {
        this.dialog?.closeAll?.();
        const order = this.pos.getOrder();
        if (!order || !order.getOrderlines()?.length) {
            this.notification.add(_t("Please add items to the order before printing a bill."), { type: "warning" });
            return;
        }
        await this.pos.ticketPrinter.printOrderReceipt({
            order: order,
            printBillActionTriggered: true,
        });
    },

    async clickPromoCode() {
        const order = this.pos.getOrder();
        this.dialog.add(TextInputPopup, {
            title: _t("Enter Code"),
            placeholder: _t("Gift card or Discount code"),
            size: "md",
            removeNewLines: true,
            getPayload: async (code) => {
                code = (code || "").trim();
                if (code === "") {
                    return;
                }
                if (typeof this.pos.loadCode === "function") {
                    const loadError = await this.pos.loadCode(code);
                    if (loadError) {
                        this.notification.add(loadError, { type: "danger" });
                        return;
                    }
                    if (typeof this.pos.applyCode === "function") {
                        await this.pos.applyCode(code);
                    }
                    if (typeof order.recomputeRewards === "function") {
                        order.recomputeRewards();
                    }
                    this.notification.add(_t("Code '%s' applied successfully!", code), { type: "success" });
                    this.dialog?.closeAll?.();
                    return;
                }

                // Fallback RPC validation
                try {
                    const res = await this.pos.data.callRelated("pos.order", "validate_code_from_pos", [code, this.pos.config.id]);
                    if (res && res.valid) {
                        this.notification.add(res.message, { type: "success" });
                        this.dialog?.closeAll?.();
                    } else {
                        this.notification.add(res?.message || _t("Invalid code."), { type: "danger" });
                    }
                } catch (err) {
                    this.notification.add(err?.message || _t("Failed to validate code."), { type: "danger" });
                }
            },
        });
    },
});

patch(OrderDisplay.prototype, {
    get displayCourses() {
        if (!this.pos?.config?.module_pos_restaurant || this.props.mode !== "display" || this.order?.finalized) {
            return false;
        }
        return Boolean(this.order?.course_ids?.length > 0);
    },
});
