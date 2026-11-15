/** @odoo-module **/
import { CartService } from "@website_sale/js/cart_service";
import { patch } from "@web/core/utils/patch";

/**
 * Patch the CartService to inject the subscription_plan_id
 * selected by the user on the product page when adding to cart.
 */
patch(CartService.prototype, {
    async add(params, options) {
        // Look for a checked subscription plan radio on the page
        const checkedPlan = document.querySelector(
            'input[name="subscription_plan_id"]:checked'
        );
        if (checkedPlan && checkedPlan.value) {
            params = { ...params, subscription_plan_id: parseInt(checkedPlan.value) };
        }
        return super.add(params, options);
    },
});
