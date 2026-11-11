/** @odoo-module **/

import * as owl from "@odoo/owl";
import { Component, useProps, onWillStart, t, proxy } from "@odoo/owl";
import { listView } from "@web/views/list/list_view";
import { listRendererProps } from "@web/views/list/list_renderer";
import { registry } from "@web/core/registry";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { useService, useBus } from "@web/core/utils/hooks";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";
import { Dialog } from "@web/core/dialog/dialog";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { ListController } from "@web/views/list/list_controller";
import { session } from "@web/session";

const reactiveState = proxy || (typeof owl !== "undefined" && (owl.proxy || owl.useState)) || ((obj) => obj);

export const hudsonMatchJournalItemsDialogProps = {
    statementLineId: t.any(),
    statementLineDate: t.string(),
    statementLineLabel: t.string(),
    statementLineAmount: t.any(),
    currencySymbol: t.string().optional(),
    currencyPosition: t.string().optional(),
    onReconciled: t.any().optional(),
    close: t.any(),
};

export class HudsonMatchJournalItemsDialog extends Component {
    static template = "hudson_accounting_enhancements.MatchJournalItemsDialog";
    static components = { Dialog };
    props = useProps(hudsonMatchJournalItemsDialogProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = reactiveState({
            loading: true,
            searchTerm: "",
            candidates: [],
            totalCount: 0,
            limit: 30,
            offset: 0,
            selectedIds: new Set(),
        });

        this.searchTimeout = null;

        onWillStart(async () => {
            await this.loadCandidates();
        });
    }

    get formattedBalance() {
        const val = typeof this.props.statementLineAmount === "number" ? this.props.statementLineAmount : parseFloat(this.props.statementLineAmount) || 0;
        const absVal = Math.abs(val).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        const sym = this.props.currencySymbol || "$";
        const pos = this.props.currencyPosition || "before";
        const isNeg = val < 0;
        if (pos === "after") {
            return isNeg ? `-${absVal} ${sym}` : `${absVal} ${sym}`;
        }
        return isNeg ? `${sym} -${absVal}` : `${sym} ${absVal}`;
    }

    get paginationText() {
        if (!this.state.totalCount) return "0 / 0";
        const start = this.state.offset + 1;
        const end = Math.min(this.state.offset + this.state.limit, this.state.totalCount);
        return `${start}-${end} / ${this.state.totalCount}`;
    }

    get hasPrevious() {
        return this.state.offset > 0;
    }

    get hasNext() {
        return this.state.offset + this.state.limit < this.state.totalCount;
    }

    get isAllSelected() {
        if (!this.state.candidates.length) return false;
        return this.state.candidates.every((c) => this.state.selectedIds.has(c.id));
    }

    async loadCandidates() {
        this.state.loading = true;
        try {
            const res = await this.orm.call(
                "account.bank.statement.line",
                "get_hudson_matching_candidates",
                [],
                {
                    statement_line_id: this.props.statementLineId,
                    search_term: this.state.searchTerm,
                    limit: this.state.limit,
                    offset: this.state.offset,
                }
            );
            this.state.candidates = res.candidates || [];
            this.state.totalCount = res.total_count || 0;
        } finally {
            this.state.loading = false;
        }
    }

    onSearchInput(ev) {
        this.state.searchTerm = ev.target.value;
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }
        this.searchTimeout = setTimeout(async () => {
            this.state.offset = 0;
            await this.loadCandidates();
        }, 300);
    }

    async onPreviousPage() {
        if (!this.hasPrevious) return;
        this.state.offset = Math.max(0, this.state.offset - this.state.limit);
        await this.loadCandidates();
    }

    async onNextPage() {
        if (!this.hasNext) return;
        this.state.offset += this.state.limit;
        await this.loadCandidates();
    }

    onToggleSelectAll() {
        if (this.isAllSelected) {
            for (const c of this.state.candidates) {
                this.state.selectedIds.delete(c.id);
            }
        } else {
            for (const c of this.state.candidates) {
                this.state.selectedIds.add(c.id);
            }
        }
    }

    onToggleSelect(id) {
        if (this.state.selectedIds.has(id)) {
            this.state.selectedIds.delete(id);
        } else {
            this.state.selectedIds.add(id);
        }
    }

    onRowClick(item, ev) {
        this.onToggleSelect(item.id);
    }

    onViewCandidate(item, ev) {
        ev?.stopPropagation?.();
        ev?.preventDefault?.();
        if (item.move_id) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "account.move",
                res_id: item.move_id,
                views: [[false, "form"]],
                target: "new",
            });
        }
    }

    async onSelect() {
        const selectedIds = Array.from(this.state.selectedIds);
        if (!selectedIds.length) return;

        try {
            await this.orm.call(
                "account.bank.statement.line",
                "action_hudson_reconcile_items",
                [[this.props.statementLineId], selectedIds]
            );
            if (this.props.onReconciled) {
                await this.props.onReconciled();
            }
            this.props.close();
        } catch (err) {
            this.notification.add(err.message || "Failed to reconcile items.", { type: "danger" });
        }
    }
}

export const hudsonEditLineDialogProps = {
    resId: t.any(),
    close: t.any(),
    onSaved: t.any().optional(),
};

export class HudsonEditLineDialog extends Component {
    static template = "hudson_accounting_enhancements.EditLineDialog";
    static components = { Dialog };
    props = useProps(hudsonEditLineDialogProps);

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.action = useService("action");
        this.state = reactiveState({
            loading: true,
            data: {},
            description: "",
            accountId: null,
            accountDisplayName: "",
            partnerId: null,
            partnerDisplayName: "",
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "account.bank.statement.line",
                "get_hudson_edit_line_data",
                [[this.props.resId]]
            );
            this.state.data = data || {};
            this.state.description = data.description || "";
            this.state.accountId = data.account_id || null;
            this.state.accountDisplayName = data.account_display_name || data.account_name || "";
            this.state.partnerId = data.partner_id || null;
            this.state.partnerDisplayName = data.partner_name || "";
        } finally {
            this.state.loading = false;
        }
    }

    onSelectAccount() {
        if (!this.state.data.is_account_editable) return;
        this.dialog.add(SelectCreateDialog, {
            resModel: "account.account",
            title: "Select Account",
            onSelected: async (resIds) => {
                if (resIds.length > 0) {
                    this.state.accountId = resIds[0];
                    const acc = await this.orm.read("account.account", [resIds[0]], ["display_name"]);
                    if (acc && acc.length > 0) {
                        this.state.accountDisplayName = acc[0].display_name;
                    }
                }
            },
        });
    }

    onSelectPartner() {
        if (!this.state.data.is_partner_editable) return;
        this.dialog.add(SelectCreateDialog, {
            resModel: "res.partner",
            title: "Select Partner",
            onSelected: async (resIds) => {
                if (resIds.length > 0) {
                    this.state.partnerId = resIds[0];
                    const p = await this.orm.read("res.partner", [resIds[0]], ["display_name"]);
                    if (p && p.length > 0) {
                        this.state.partnerDisplayName = p[0].display_name;
                    }
                }
            },
        });
    }

    onOpenPartner() {
        if (this.state.partnerId) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "res.partner",
                res_id: this.state.partnerId,
                views: [[false, "form"]],
                target: "current",
            });
            this.props.close();
        }
    }

    onOpenAccount() {
        if (this.state.accountId) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "account.account",
                res_id: this.state.accountId,
                views: [[false, "form"]],
                target: "current",
            });
            this.props.close();
        }
    }

    async onSave() {
        await this.orm.call(
            "account.bank.statement.line",
            "action_hudson_save_edit_line",
            [[this.props.resId], {
                description: this.state.description,
                account_id: this.state.accountId,
                partner_id: this.state.partnerId,
                is_locked: !this.state.data.is_account_editable,
            }]
        );
        if (this.props.onSaved) {
            await this.props.onSaved();
        }
        this.props.close();
    }
}

export class HudsonBankMatchingListRenderer extends Component {
    static template = "hudson_accounting_enhancements.BankMatchingListRenderer";
    static components = {
        Dropdown,
        DropdownItem,
    };
    props = useProps(listRendererProps);

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");

        const today = new Date();

        const initialShowNew = Boolean(
            this.props.list?.context?.show_new_transaction ||
            this.env.searchModel?.context?.show_new_transaction
        );

        this.state = reactiveState({
            showNewTransaction: initialShowNew,
            newDate: `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`,
            newLabel: "",
            newPartnerId: null,
            newPartnerName: "",
            newAmount: "",
            newModelId: "",
            reconcileModels: [],
        });

        this.currencyInfo = {
            id: null,
            name: "",
            symbol: "$",
            position: "before",
        };

        useBus(this.env.bus, "hudson-show-new-transaction", () => {
            this.state.showNewTransaction = true;
        });

        onWillStart(async () => {
            await this.loadMatchingContext();
        });
    }

    get journalId() {
        const defaultJournal = this.props.list?.context?.default_journal_id;
        if (defaultJournal) return defaultJournal;
        const searchJournal = this.env.searchModel?.context?.default_journal_id;
        if (searchJournal) return searchJournal;
        const activeModel = this.props.list?.context?.active_model;
        if (activeModel === "account.journal" && this.props.list?.context?.active_id) {
            return this.props.list.context.active_id;
        }
        const records = this.props.list?.records || [];
        if (records.length > 0) {
            const j = records[0].data?.journal_id;
            return Array.isArray(j) ? j[0] : j?.id || j;
        }
        return false;
    }

    get currencySymbol() {
        return this.currencyInfo.symbol || "$";
    }

    get currencyPosition() {
        return this.currencyInfo.position || "before";
    }

    get currencyPlaceholder() {
        return this.currencyPosition === "after" ? `0.00 ${this.currencySymbol}` : `${this.currencySymbol} 0.00`;
    }

    async loadMatchingContext() {
        try {
            const ctxData = await this.orm.call(
                "account.bank.statement.line",
                "get_hudson_bank_matching_context",
                [],
                { journal_id: this.journalId || false }
            );
            if (ctxData) {
                this.currencyInfo = {
                    id: ctxData.currency_id,
                    name: ctxData.currency_name,
                    symbol: ctxData.currency_symbol || "$",
                    position: ctxData.currency_position || "before",
                };
                this.state.reconcileModels = ctxData.reconcile_models || [];
            }
        } catch {
            this.state.reconcileModels = [];
        }
    }

    get totalBalanceFormatted() {
        let total = 0;
        const records = this.props.list?.records || [];
        for (const r of records) {
            const amt = r.data?.amount;
            const num = typeof amt === "number" ? amt : parseFloat(amt) || 0;
            total += num;
        }
        return this.formatAmount(total);
    }

    get statementGroups() {
        const groups = [];
        const records = this.props.list?.records || [];
        let currentStatementId = undefined;
        let currentGroup = null;

        for (const record of records) {
            const stmt = record.data?.statement_id;
            const stmtId = stmt ? (Array.isArray(stmt) ? stmt[0] : stmt.id || stmt) : false;
            const stmtName = stmt ? (Array.isArray(stmt) ? stmt[1] : stmt.display_name || stmt.name || "") : false;

            if (stmtId !== currentStatementId || !currentGroup) {
                currentStatementId = stmtId;
                currentGroup = {
                    key: `stmt_${stmtId || "unassigned"}_${groups.length}`,
                    statementId: stmtId,
                    statementName: stmtName,
                    records: [],
                    dateRange: "",
                    totalAmount: 0,
                    totalFormatted: "",
                };
                groups.push(currentGroup);
            }

            currentGroup.records.push(record);
            const amt = record.data?.amount;
            currentGroup.totalAmount += typeof amt === "number" ? amt : parseFloat(amt) || 0;
        }

        for (const g of groups) {
            g.totalFormatted = this.formatAmount(g.totalAmount);
            if (g.statementId && g.records.length > 0) {
                const dates = g.records.map((r) => r.data?.date).filter(Boolean).sort();
                if (dates.length > 0) {
                    const dMin = this.formatShortDate(dates[0]);
                    const dMax = this.formatShortDate(dates[dates.length - 1]);
                    g.dateRange = dMin === dMax ? dMin : `${dMin} - ${dMax}`;
                }
            }
        }

        return groups;
    }

    formatDisplayDate(dateStr) {
        if (!dateStr) return "";
        try {
            const d = new Date(dateStr);
            if (isNaN(d.getTime())) return dateStr;
            const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"];
            return `${d.getDate()} ${months[d.getMonth()]}`;
        } catch {
            return dateStr;
        }
    }

    formatShortDate(dateStr) {
        if (!dateStr) return "";
        try {
            const d = new Date(dateStr);
            if (isNaN(d.getTime())) return dateStr;
            return `${d.getDate()}/${d.getMonth() + 1}`;
        } catch {
            return dateStr;
        }
    }

    formatAmount(amount, customCurrencyId = null) {
        const val = typeof amount === "number" ? amount : parseFloat(amount) || 0;
        const isNegative = val < 0;
        const absVal = Math.abs(val).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });

        let sym = this.currencySymbol;
        let pos = this.currencyPosition;
        if (customCurrencyId && session.currencies && session.currencies[customCurrencyId]) {
            sym = session.currencies[customCurrencyId].symbol || sym;
            pos = session.currencies[customCurrencyId].position || pos;
        }

        if (pos === "after") {
            return isNegative ? `-${absVal} ${sym}` : `${absVal} ${sym}`;
        }
        return isNegative ? `${sym} -${absVal}` : `${sym} ${absVal}`;
    }

    formatRecordAmount(record) {
        let currId = null;
        const c = record.data?.currency_id;
        if (c) {
            currId = Array.isArray(c) ? c[0] : c.id || c;
        }
        return this.formatAmount(record.data?.amount, currId);
    }

    isNegative(record) {
        const amt = record.data?.amount;
        const num = typeof amt === "number" ? amt : parseFloat(amt) || 0;
        return num < 0;
    }

    hasAttachments(record) {
        const att = record.data?.attachment_ids;
        return Boolean((Array.isArray(att) && att.length > 0) || (record.data?.message_attachment_count && record.data.message_attachment_count > 0));
    }

    hasNotes(record) {
        return Boolean(record.data?.narration);
    }

    getPartnerName(record) {
        const p = record.data?.partner_id;
        if (!p) return "";
        if (Array.isArray(p) && p.length > 1) return p[1];
        if (typeof p === "object") return p.name || p.display_name || "";
        return String(p);
    }

    async reloadView() {
        if (this.props.list?.load) {
            await this.props.list.load();
        } else if (this.props.list?.model?.load) {
            await this.props.list.model.load();
        } else if (this.action?.doAction) {
            await this.action.doAction({ type: "ir.actions.client", tag: "reload" });
        }
    }

    toggleNewTransaction() {
        this.state.showNewTransaction = !this.state.showNewTransaction;
    }

    onSelectNewPartner() {
        this.dialog.add(SelectCreateDialog, {
            resModel: "res.partner",
            title: "Select Partner",
            onSelected: async (resIds) => {
                if (resIds.length > 0) {
                    this.state.newPartnerId = resIds[0];
                    const p = await this.orm.read("res.partner", [resIds[0]], ["display_name"]);
                    if (p && p.length > 0) {
                        this.state.newPartnerName = p[0].display_name;
                    }
                }
            },
        });
    }

    onClearNewPartner(ev) {
        ev?.stopPropagation?.();
        this.state.newPartnerId = null;
        this.state.newPartnerName = "";
    }

    async onSaveNewTransaction(closeAfter = false) {
        const label = (this.state.newLabel || "").trim();
        if (!label) {
            this.notification.add("Label is required to create a new transaction.", {
                type: "warning",
            });
            return;
        }

        const amt = parseFloat(this.state.newAmount);
        if (!this.state.newAmount || isNaN(amt) || amt === 0) {
            this.notification.add("Please provide a valid non-zero amount for the transaction.", {
                type: "warning",
            });
            return;
        }

        const _now = new Date();
        const todayStr = `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, '0')}-${String(_now.getDate()).padStart(2, '0')}`;
        const vals = {
            journal_id: this.journalId,
            date: this.state.newDate || todayStr,
            payment_ref: label,
            amount: amt,
            partner_id: this.state.newPartnerId || false,
            reconcile_model_id: this.state.newModelId ? parseInt(this.state.newModelId) : false,
        };

        await this.orm.call(
            "account.bank.statement.line",
            "action_hudson_create_inline_transaction",
            [vals]
        );

        await this.reloadView();

        if (closeAfter) {
            this.state.showNewTransaction = false;
        } else {
            this.state.newLabel = "";
            this.state.newAmount = "";
            this.state.newPartnerId = null;
            this.state.newPartnerName = "";
            this.state.newModelId = "";
        }
    }

    onDiscardNewTransaction() {
        this.state.showNewTransaction = false;
        this.state.newLabel = "";
        this.state.newAmount = "";
        this.state.newPartnerId = null;
        this.state.newPartnerName = "";
        this.state.newModelId = "";
    }

    onEditLine(record, ev) {
        ev?.stopPropagation?.();
        const resId = record.resId;
        if (!resId) return;
        this.dialog.add(HudsonEditLineDialog, {
            resId: resId,
            onSaved: async () => {
                await this.reloadView();
            },
        });
    }

    async onSetPartner(record, ev) {
        ev?.stopPropagation?.();
        const resId = record.resId;
        if (!resId) return;

        this.dialog.add(SelectCreateDialog, {
            resModel: "res.partner",
            title: "Search: Partner",
            onSelected: async (resIds) => {
                if (resIds.length > 0) {
                    await this.orm.write("account.bank.statement.line", [resId], {
                        partner_id: resIds[0],
                    });
                    await this.reloadView();
                }
            },
        });
    }

    async onClearPartner(record, ev) {
        ev?.stopPropagation?.();
        const resId = record.resId;
        if (!resId) return;
        await this.orm.write("account.bank.statement.line", [resId], {
            partner_id: false,
        });
        await this.reloadView();
    }

    async onSetAccount(record, ev) {
        ev?.stopPropagation?.();
        const resId = record.resId;
        if (!resId) return;

        this.dialog.add(SelectCreateDialog, {
            resModel: "account.account",
            title: "Search: Account",
            onSelected: async (resIds) => {
                if (resIds.length > 0) {
                    await this.orm.write("account.bank.statement.line", [resId], {
                        hudson_account_id: resIds[0],
                    });
                    await this.reloadView();
                }
            },
        });
    }

    async onApplySuggested(record, ev) {
        ev?.stopPropagation?.();
        const resId = record.resId;
        if (!resId) return;
        await this.orm.call(
            "account.bank.statement.line",
            "action_apply_suggested_account",
            [[resId]]
        );
        await this.reloadView();
    }

    async onReconcile(record, ev) {
        ev?.stopPropagation?.();
        const resId = record.resId;
        if (!resId) return;

        this.dialog.add(HudsonMatchJournalItemsDialog, {
            statementLineId: resId,
            statementLineDate: this.formatDisplayDate(record.data?.date),
            statementLineLabel: record.data?.payment_ref || "(No description)",
            statementLineAmount: record.data?.amount,
            currencySymbol: this.currencySymbol,
            currencyPosition: this.currencyPosition,
            onReconciled: async () => {
                await this.reloadView();
            },
        });
    }

    async onResetMatch(record, ev) {
        ev?.stopPropagation?.();
        const resId = record.resId;
        if (!resId) return;
        await this.orm.call(
            "account.bank.statement.line",
            "action_hudson_reset",
            [[resId]]
        );
        await this.reloadView();
    }

    async onOpenPartner(record, ev) {
        ev?.stopPropagation?.();
        const partner = record.data?.partner_id;
        const partnerId = Array.isArray(partner) ? partner[0] : partner?.id || partner;
        if (partnerId) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "res.partner",
                res_id: partnerId,
                views: [[false, "form"]],
                target: "current",
            });
        }
    }

    async onOpenRecord(record, ev) {
        ev?.stopPropagation?.();
        if (this.props.openRecord) {
            this.props.openRecord(record);
        } else {
            this.action.switchView("form", { resId: record.resId });
        }
    }

    async onUploadBills(record) {
        const resId = record.resId;
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

    async onDelete(record) {
        const resId = record.resId;
        if (!resId) return;
        this.dialog.add(ConfirmationDialog, {
            title: "Delete Transaction",
            body: "This will delete the bank transaction and its journal entry. Continue?",
            confirm: async () => {
                // Reset first so any reconciliation is undone; let failures surface.
                await this.orm.call("account.bank.statement.line", "action_hudson_reset", [[resId]]);
                await this.orm.unlink("account.bank.statement.line", [resId]);
                await this.reloadView();
            },
            cancel: () => {},
        });
    }

    async onInternalTransfers(record) {
        const resId = record.resId;
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

export class HudsonBankMatchingListController extends ListController {
    async createRecord() {
        this.env.bus.trigger("hudson-show-new-transaction");
    }
}

export const hudsonBankMatchingListView = {
    ...listView,
    Controller: HudsonBankMatchingListController,
    Renderer: HudsonBankMatchingListRenderer,
};

registry.category("views").add("hudson_bank_matching_list", hudsonBankMatchingListView);

