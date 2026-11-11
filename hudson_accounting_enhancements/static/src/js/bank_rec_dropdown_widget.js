/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { useService } from "@web/core/utils/hooks";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";
import { session } from "@web/session";
import { HudsonMatchJournalItemsDialog } from "./bank_matching_list_renderer";

export class BankRecActionDropdown extends Component {
    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.dialog = useService("dialog");
    }

    get record() {
        return this.props?.record;
    }

    get recordData() {
        return this.record?.data || {};
    }

    get isReconciled() {
        return Boolean(this.recordData.is_reconciled);
    }

    get hasPartner() {
        const p = this.recordData.partner_id;
        return Boolean(p && (Array.isArray(p) ? p.length > 0 : (p.id || typeof p === 'number')));
    }

    get hasMatches() {
        return Boolean(this.recordData.hudson_has_matches);
    }

    get matchCount() {
        return this.recordData.hudson_match_count || 0;
    }

    get suggestedAccountName() {
        return this.recordData.hudson_suggested_account_name || (this.hasPartner ? 'Receivable' : '');
    }

    get matchedAccountName() {
        return this.recordData.hudson_matched_account_name || 'Reconciled';
    }

    async reloadView() {
        if (this.record?.model?.load) {
            await this.record.model.load();
        } else if (this.action?.doAction) {
            await this.action.doAction({ type: "ir.actions.client", tag: "reload" });
        }
    }

    async onApplySuggestedAccount() {
        const resId = this.record?.resId;
        if (!resId) return;
        await this.orm.call(
            "account.bank.statement.line",
            "action_apply_suggested_account",
            [[resId]]
        );
        await this.reloadView();
    }

    async onSetPartner() {
        const resId = this.record?.resId;
        if (!resId) return;
        this.dialog.add(SelectCreateDialog, {
            resModel: "res.partner",
            title: "Search: Partner",
            onSelected: async (resIds) => {
                if (resIds.length > 0) {
                    await this.orm.write("account.bank.statement.line", [resId], {
                        partner_id: resIds[0]
                    });
                    await this.reloadView();
                }
            }
        });
    }

    async onSetAccount() {
        const resId = this.record?.resId;
        if (!resId) return;
        this.dialog.add(SelectCreateDialog, {
            resModel: "account.account",
            title: "Search: Account",
            onSelected: async (resIds) => {
                if (resIds.length > 0) {
                    await this.orm.write("account.bank.statement.line", [resId], {
                        hudson_account_id: resIds[0]
                    });
                    await this.reloadView();
                }
            }
        });
    }

    async onResetMatch() {
        const resId = this.record?.resId;
        if (!resId) return;
        await this.orm.call(
            "account.bank.statement.line",
            "action_hudson_reset",
            [[resId]]
        );
        await this.reloadView();
    }

    async onReconcile() {
        const domain = [
            ['account_id.reconcile', '=', true],
            ['reconciled', '=', false],
            ['move_id.state', '=', 'posted'],
            ['journal_id.type', 'not in', ['bank', 'cash']]
        ];
        
        let amount = this.recordData.amount;
        if (typeof amount === 'object' && amount !== null) {
            amount = amount.value !== undefined ? amount.value : (amount.amount !== undefined ? amount.amount : 0);
        }
        amount = typeof amount === 'number' ? amount : (parseFloat(amount) || 0.0);
        const roundedAmount = Math.round(amount * 100) / 100;
        
        let partnerId = false;
        const partner = this.recordData.partner_id;
        if (Array.isArray(partner) && partner.length > 0) {
            partnerId = partner[0];
        } else if (typeof partner === 'object' && partner !== null) {
            partnerId = partner.id || false;
        } else if (typeof partner === 'number') {
            partnerId = partner;
        }
        
        const resId = this.record?.resId;
        if (!resId) return;

        let dateStr = "";
        if (this.recordData.date) {
            try {
                const d = new Date(this.recordData.date);
                const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"];
                dateStr = `${d.getDate()} ${months[d.getMonth()]}`;
            } catch {
                dateStr = this.recordData.date;
            }
        }

        let sym = "$";
        let pos = "before";
        const curr = this.recordData.currency_id;
        const currId = curr ? (Array.isArray(curr) ? curr[0] : curr.id || curr) : null;
        if (currId && session.currencies && session.currencies[currId]) {
            sym = session.currencies[currId].symbol || "$";
            pos = session.currencies[currId].position || "before";
        }

        this.dialog.add(HudsonMatchJournalItemsDialog, {
            statementLineId: resId,
            statementLineDate: dateStr,
            statementLineLabel: this.recordData.payment_ref || "(No description)",
            statementLineAmount: roundedAmount,
            currencySymbol: sym,
            currencyPosition: pos,
            onReconciled: async () => {
                await this.reloadView();
            },
        });
    }

    async onUploadBills() {
        const resId = this.record?.resId;
        if (!resId) return;
        const action = await this.orm.call(
            "account.bank.statement.line",
            "action_hudson_upload_bills",
            [[resId]]
        );
        if (action) {
            this.action.doAction(action);
        }
    }

    async onDelete() {
        const resId = this.record?.resId;
        if (!resId) return;
        await this.orm.unlink("account.bank.statement.line", [resId]);
        await this.reloadView();
    }
    
    async onInternalTransfers() {
        const resId = this.record?.resId;
        if (!resId) return;
        await this.orm.call(
            "account.bank.statement.line",
            "action_hudson_internal_transfer",
            [[resId]]
        );
        await this.reloadView();
    }
    
    async onManageModels() {
        this.action.doAction("account.action_account_reconcile_model");
    }
}

BankRecActionDropdown.template = "hudson_accounting_enhancements.BankRecActionDropdown";
BankRecActionDropdown.components = { Dropdown, DropdownItem };

export const bankRecActionDropdown = {
    component: BankRecActionDropdown,
};

registry.category("fields").add("bank_rec_action_dropdown", bankRecActionDropdown);

function hudsonSetPartnerAction(env, action) {
    env.services.dialog.add(SelectCreateDialog, {
        resModel: "res.partner",
        title: "Search: Partner",
        onSelected: async (resIds) => {
            if (resIds.length > 0) {
                const partnerId = resIds[0];
                const statementLineId = action.context.default_statement_line_id;
                await env.services.orm.write("account.bank.statement.line", [statementLineId], {
                    partner_id: partnerId
                });
                await env.services.action.doAction({ type: "ir.actions.client", tag: "reload" });
            }
        }
    });
}
registry.category("actions").add("hudson_set_partner", hudsonSetPartnerAction);

function hudsonSetAccountAction(env, action) {
    env.services.dialog.add(SelectCreateDialog, {
        resModel: "account.account",
        title: "Search: Account",
        onSelected: async (resIds) => {
            if (resIds.length > 0) {
                const accountId = resIds[0];
                const statementLineId = action.context.default_statement_line_id;
                await env.services.orm.write("account.bank.statement.line", [statementLineId], {
                    hudson_account_id: accountId
                });
                await env.services.action.doAction({ type: "ir.actions.client", tag: "reload" });
            }
        }
    });
}
registry.category("actions").add("hudson_set_account", hudsonSetAccountAction);
