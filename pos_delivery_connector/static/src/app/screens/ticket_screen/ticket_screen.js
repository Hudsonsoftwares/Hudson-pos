/** @odoo-module */

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";

patch(TicketScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.toggleDeliveryFilter = this.toggleDeliveryFilter.bind(this);
        if (this.state) {
            this.state.isDeliveryFilterActive = false;
        } else {
            this.isDeliveryFilterActive = false;
        }
    },

    get isDeliveryFilterOn() {
        if (this.state && this.state.isDeliveryFilterActive !== undefined) {
            return Boolean(this.state.isDeliveryFilterActive);
        }
        return Boolean(this.isDeliveryFilterActive);
    },

    toggleDeliveryFilter() {
        if (this.state) {
            this.state.isDeliveryFilterActive = !this.state.isDeliveryFilterActive;
        } else {
            this.isDeliveryFilterActive = !this.isDeliveryFilterActive;
        }
    },

    getFilteredOrderList() {
        let orderList = super.getFilteredOrderList ? super.getFilteredOrderList(...arguments) : [];
        if (!Array.isArray(orderList)) return orderList;

        if (this.isDeliveryFilterOn) {
            orderList = orderList.filter(order => order && (order.is_delivery_order || (order.delivery_platform_id && order.delivery_platform_id[0])));
        }
        
        return orderList;
    }
});
