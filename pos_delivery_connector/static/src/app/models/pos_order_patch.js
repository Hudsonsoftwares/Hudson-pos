/** @odoo-module **/

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    _doRecomputeAllPrices() {
        if (!this.lines || !Array.isArray(this.lines)) {
            return;
        }
        return super._doRecomputeAllPrices(...arguments);
    },

    _constructPriceData() {
        if (!this.lines || !Array.isArray(this.lines)) {
            return { raw: [], subtotal: 0, total: 0 };
        }
        return super._constructPriceData(...arguments);
    },

    _computeAllPrices(opts = {}) {
        if (!this.lines && !opts.lines) {
            opts.lines = [];
        }
        try {
            return super._computeAllPrices ? super._computeAllPrices(opts) : { raw: [], subtotal: 0, total: 0 };
        } catch (e) {
            return { raw: [], subtotal: 0, total: 0 };
        }
    },
});
