/** @odoo-module */

import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { patch } from "@web/core/utils/patch";

patch(ControlButtons.prototype, {
    _getEWalletRewards(order) {
        const appliedRewardIds = new Set(
            order?.active_payment_programs?.map((entry) => entry.reward_id) || []
        );
        const rewards = [];
        for (const program of this._getEWalletPrograms()) {
            const reward = program.reward_ids?.[0];
            if (!reward || appliedRewardIds.has(reward.id)) {
                // Already applied to this order or no reward configured
                continue;
            }
            const card = this.pos.models["loyalty.card"].find(
                (card) =>
                    card.program_id?.id === program.id &&
                    card.partner_id?.id === order?.partner_id?.id &&
                    !card.isExpired() &&
                    card.points > 0
            );
            if (card) {
                rewards.push({ reward, card_id: card.id });
            }
        }
        return rewards;
    },
});

