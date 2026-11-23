import { patch } from "@web/core/utils/patch";
import { LandingPage } from "@pos_self_order/app/pages/landing_page/landing_page";
import { CartPage } from "@pos_self_order/app/pages/cart_page/cart_page";
import { OrdersHistoryPage } from "@pos_self_order/app/pages/order_history_page/order_history_page";
import { ConfirmationPage } from "@pos_self_order/app/pages/confirmation_page/confirmation_page";
import { SelfOrder } from "@pos_self_order/app/services/self_order_service";
import { CancelPopup } from "@pos_self_order/app/components/cancel_popup/cancel_popup";
import { _t } from "@web/core/l10n/translation";

patch(LandingPage.prototype, {
    get draftOrder() {
        // Only treat an order as an active local draft if it is not yet synced to backend and has items
        return this.selfOrder.models["pos.order"].filter(
            (o) => !o.isSynced && o.lines && o.lines.length > 0
        );
    },

    hideBtn(link) {
        const arrayLink = link.url.split("/");
        const routeName = arrayLink[arrayLink.length - 1];

        // Keep "Order Now" (/products) visible at all times so customers can make multiple orders
        if (routeName === "products") {
            return false;
        }

        return super.hideBtn(...arguments);
    },

    start() {
        if (
            this.draftOrder.length > 0 &&
            this.selfOrder.config.self_ordering_pay_after === "each"
        ) {
            const currentOrder = this.selfOrder.currentOrder;
            if (!currentOrder || currentOrder.lines.length > 0) {
                const newOrder = this.selfOrder.createNewOrder();
                this.selfOrder.selectedOrderUuid = newOrder.uuid;
            }
        }

        if (this.selfOrder.config.use_presets && !this.selfOrder.currentOrder.preset_id) {
            const availablePresets = this.selfOrder.availablePresets;
            if (availablePresets.length === 1) {
                this.selfOrder.currentOrder.setPreset(availablePresets[0]);
            } else if (availablePresets.length > 1) {
                this.router.navigate("location");
                return;
            }
        }

        this.router.navigate("product_list");
    },

    async clickMyOrder() {
        if (this.selfOrder.access_token) {
            await this.selfOrder.getUserDataFromServer();
        }

        // If the customer has an un-synced local cart with items, navigate to cart
        const localDraftOrder = this.selfOrder.models["pos.order"].find(
            (o) => !o.isSynced && o.lines && o.lines.length > 0
        );

        if (localDraftOrder) {
            this.selfOrder.selectedOrderUuid = localDraftOrder.uuid;
            this.router.navigate("cart", {}, { fromLanding: true });
        } else {
            // Otherwise, navigate to Order History / Tracking where completed, paid, and placed orders are tracked
            this.router.navigate("orderHistory");
        }
    },
});

patch(CartPage.prototype, {
    setup() {
        super.setup(...arguments);
        // If the cart has no items in it (0 lines), never show an empty ₹0.00 screen
        // Automatically redirect to Order History (if customer has placed orders) or to product list
        if (this.lines.length === 0) {
            const hasOrders = this.selfOrder.models["pos.order"].some((o) => o.access_token);
            if (hasOrders) {
                this.router.navigate("orderHistory");
            } else {
                this.router.navigate("product_list");
            }
        }
    },

    get showCancelButton() {
        return (
            this.selfOrder.config.self_ordering_mode === "mobile" &&
            this.selfOrder.config.self_ordering_pay_after === "each" &&
            (this.selfOrder.currentOrder?.isSynced || this.selfOrder.currentOrder?.lines?.length > 0)
        );
    },

    async cancelOrder() {
        this.dialog.add(CancelPopup, {
            title: _t("Cancel order"),
            confirm: async () => {
                if (this.selfOrder.currentOrder.isSynced) {
                    await this.selfOrder.cancelBackendOrder();
                } else {
                    this.selfOrder.currentOrder.delete();
                    this.selfOrder.selectedOrderUuid = null;
                    this.router.navigate("default");
                }
            },
        });
    },
});

patch(SelfOrder.prototype, {
    initProducts() {
        // Stock bug: with "Restrict categories" on but no category selected, productCategories IS the
        // config's iface_available_categ_ids array, and products without a POS category (e.g. the
        // pos_self_order_event dummy products) make it push "Uncategorised" into that read-only
        // array -> "The 'iface_available_categ_ids' array cannot be modified". An empty restriction
        // restricts nothing, so load the products as if the restriction were off.
        const config = this.config;
        if (!config?.limit_categories || config.iface_available_categ_ids?.length) {
            return super.initProducts(...arguments);
        }
        this.config = new Proxy(config, {
            get: (target, key) => (key === "limit_categories" ? false : target[key]),
        });
        try {
            return super.initProducts(...arguments);
        } finally {
            this.config = config;
        }
    },

    async _sendDraftOrderToServer() {
        const order = await super._sendDraftOrderToServer(...arguments);
        if (
            this.config.self_ordering_mode === "mobile" &&
            this.config.self_order_online_payment_method_id &&
            this.config.self_ordering_pay_after === "each" &&
            order
        ) {
            // Keep the order selected so CartPage never flashes an empty 0-item cart
            this.selectedOrderUuid = order.uuid;
        }
        return order;
    },

    async confirmOrder() {
        const payAfter = this.config.self_ordering_pay_after;
        const device = this.config.self_ordering_mode;

        // In mobile mode with online payment in pay-after-each:
        // After creating the backend order, directly redirect to the online payment portal
        // instead of hitting the kiosk PaymentPage which resets and kicks back to default
        if (
            device === "mobile" &&
            this.config.self_order_online_payment_method_id &&
            payAfter === "each"
        ) {
            const order = await this.sendDraftOrderToServer();
            if (!order) {
                return;
            }
            if (this.hasPaymentMethod() && order.priceIncl > 0 && order.state === "draft") {
                this.selectedOrderUuid = order.uuid;
                this.data.synchronizeLocalDataInIndexedDB(order);
                const onlinePaymentUrl = this.getOnlinePaymentUrl(order, true);
                window.location.replace(onlinePaymentUrl);
                // Keep rpcLoading active so the Pay button spinner stays on and
                // the UI does not glitch/flash an empty cart while navigating
                await new Promise(() => {});
                return;
            }
        }
        return super.confirmOrder(...arguments);
    },
});

patch(ConfirmationPage.prototype, {
    async initOrder(retry = true) {
        if (this.props.orderAccessToken) {
            // Always fetch the freshest order state from backend to ensure 'paid' state is reflected
            await this.selfOrder.getUserDataFromServer([this.props.orderAccessToken]);
        }
        return super.initOrder(false);
    },
});

patch(OrdersHistoryPage.prototype, {
    async setup() {
        await super.setup(...arguments);
        if (this.selfOrder.access_token) {
            await this.selfOrder.getUserDataFromServer();
        }
    },

    editOrder(order) {
        if (order.state === "draft") {
            // If this is a pending mobile online payment order, resume payment directly
            if (
                this.selfOrder.config.self_ordering_mode === "mobile" &&
                this.selfOrder.config.self_order_online_payment_method_id
            ) {
                const onlinePaymentUrl = this.selfOrder.getOnlinePaymentUrl(order, true);
                if (onlinePaymentUrl) {
                    window.location.replace(onlinePaymentUrl);
                    return;
                }
            }
            this.selfOrder.selectedOrderUuid = order.uuid;
            this.router.navigate("cart");
        }
    },
});
