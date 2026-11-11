/** @odoo-module **/

import * as owl from "@odoo/owl";
import { Component, onWillStart, useProps, proxy } from "@odoo/owl";
import { Layout } from "@web/search/layout";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { useService, useBus } from "@web/core/utils/hooks";

const useState = proxy || (typeof owl !== "undefined" && (owl.proxy || owl.useState)) || ((obj) => obj);
const reactiveState = useState;

export class GridController extends Component {
    static template = "hudson_accounting_enhancements.GridView";
    static components = { Layout, SearchBar, CogMenu };
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.searchBarToggler = useSearchBarToggler();

        this.onAddLine = this.onAddLine.bind(this);
        this.onToday = this.onToday.bind(this);
        this.onPrevPeriod = this.onPrevPeriod.bind(this);
        this.onNextPeriod = this.onNextPeriod.bind(this);
        this.formatCurrency = this.formatCurrency.bind(this);
        this.isCellSelected = this.isCellSelected.bind(this);
        this.isRowExpanded = this.isRowExpanded.bind(this);
        this.toggleRow = this.toggleRow.bind(this);
        this.onCellClick = this.onCellClick.bind(this);
        this.onCellDblClick = this.onCellDblClick.bind(this);
        this.onAccountClick = this.onAccountClick.bind(this);
        this.onRangeChange = this.onRangeChange.bind(this);

        const today = new Date();
        const y = today.getFullYear();
        const m = String(today.getMonth() + 1).padStart(2, "0");
        const d = String(today.getDate()).padStart(2, "0");

        this.state = reactiveState({
            isLoading: true,
            anchorDate: `${y}-${m}-${d}`,
            rangeType: "year",
            periodLabel: String(y),
            columns: [],
            rows: [],
            columnTotals: {},
            grandTotal: 0.0,
            currencySymbol: "$",
            currencyPosition: "before",
            expandedRows: {},
            selectedCell: null,
        });

        if (this.env.searchModel) {
            useBus(this.env.searchModel, "update", async () => {
                await this.loadGridData();
            });
        }

        onWillStart(async () => {
            await this.loadGridData();
        });
    }

    get display() {
        return this.props.display || {};
    }

    get searchDomain() {
        if (this.env.searchModel && this.env.searchModel.domain) {
            return this.env.searchModel.domain;
        }
        return this.props.domain || [];
    }

    async loadGridData() {
        this.state.isLoading = true;
        try {
            const data = await this.orm.call(
                "account.analytic.line",
                "get_grid_data",
                [],
                {
                    domain: this.searchDomain,
                    anchor_date: this.state.anchorDate,
                    range_type: this.state.rangeType,
                }
            );
            this.state.columns = data.columns || [];
            this.state.rows = data.rows || [];
            this.state.columnTotals = data.column_totals || {};
            this.state.grandTotal = data.grand_total || 0.0;
            this.state.currencySymbol = data.currency_symbol || "$";
            this.state.currencyPosition = data.currency_position || "before";
            this.state.periodLabel = data.period_label || this.state.anchorDate.slice(0, 4);
        } catch (error) {
            console.error("Error loading analytic grid data:", error);
            this.notification.add("Failed to load analytic grid data.", { type: "danger" });
        } finally {
            this.state.isLoading = false;
        }
    }

    formatCurrency(value) {
        if (value === undefined || value === null) {
            return "0.00";
        }
        const val = Number(value);
        const formatted = Math.abs(val).toLocaleString("en-US", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
        return val < 0 ? `-${formatted}` : formatted;
    }

    isCellSelected(rowId, colKey) {
        return (
            this.state.selectedCell &&
            this.state.selectedCell.rowId === rowId &&
            this.state.selectedCell.colKey === colKey
        );
    }

    isRowExpanded(rowId) {
        return Boolean(this.state.expandedRows[rowId]);
    }

    toggleRow(rowId) {
        const isExp = !this.state.expandedRows[rowId];
        this.state.expandedRows = Object.assign({}, this.state.expandedRows, { [rowId]: isExp });
    }

    onCellClick(row, col) {
        this.state.selectedCell = { rowId: row.id, colKey: col.key };
    }

    onCellDblClick(row, col) {
        this.state.selectedCell = { rowId: row.id, colKey: col.key };
        this.actionService.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "account.analytic.line",
                views: [[false, "form"]],
                target: "new",
                context: {
                    default_account_id: row.id,
                    default_date: col.start_date,
                },
            },
            {
                onClose: () => this.loadGridData(),
            }
        );
    }

    onAddLine() {
        this.actionService.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "account.analytic.line",
                views: [[false, "form"]],
                target: "new",
                context: {
                    default_date: this.state.anchorDate,
                },
            },
            {
                onClose: () => this.loadGridData(),
            }
        );
    }

    onAccountClick(accountId) {
        if (!accountId) return;
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "account.analytic.account",
            res_id: accountId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    onToday() {
        const today = new Date();
        const y = today.getFullYear();
        const m = String(today.getMonth() + 1).padStart(2, "0");
        const d = String(today.getDate()).padStart(2, "0");
        this.state.anchorDate = `${y}-${m}-${d}`;
        this.loadGridData();
    }

    onPrevPeriod() {
        const parts = this.state.anchorDate.split("-").map(Number);
        let year = parts[0];
        let month = parts[1];
        let day = parts[2] || 1;

        if (this.state.rangeType === "month") {
            month -= 1;
            if (month < 1) {
                month = 12;
                year -= 1;
            }
        } else {
            year -= 1;
        }

        this.state.anchorDate = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        this.loadGridData();
    }

    onNextPeriod() {
        const parts = this.state.anchorDate.split("-").map(Number);
        let year = parts[0];
        let month = parts[1];
        let day = parts[2] || 1;

        if (this.state.rangeType === "month") {
            month += 1;
            if (month > 12) {
                month = 1;
                year += 1;
            }
        } else {
            year += 1;
        }

        this.state.anchorDate = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        this.loadGridData();
    }

    onRangeChange(type) {
        if (this.state.rangeType !== type) {
            this.state.rangeType = type;
            this.loadGridData();
        }
    }
}
