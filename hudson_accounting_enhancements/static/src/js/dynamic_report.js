/** @odoo-module **/

import { Component, proxy, onWillStart, onWillUnmount, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

export class DynamicReport extends Component {
    props = useProps(standardActionServiceProps);

    _ensureCurrentParams() {
        if (!this._currentParams) {
            const initial = this.props?.action?.params ? JSON.parse(JSON.stringify(this.props.action.params)) : {};
            this._currentParams = initial;
        }
        if (!this._currentParams.data) {
            this._currentParams.data = {};
        }
        if (!this._currentParams.data.form) {
            this._currentParams.data.form = {};
        }
        return this._currentParams;
    }

    _saveParams() {
        const params = this._ensureCurrentParams();
        const action = this.props?.action || {};
        const actionId = action.id || action.tag || this.props?.actionId || 'default';
        const actionStorageKey = 'hudson_report_params_action_' + actionId;
        sessionStorage.setItem(actionStorageKey, JSON.stringify(params));
        if (params.model_name) {
            sessionStorage.setItem('hudson_report_params_' + params.model_name, JSON.stringify(params));
        }
    }

    get reportParams() {
        return this._ensureCurrentParams();
    }

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({
            title: "Loading...",
            columns: [],
            lines: [],
            expandedLines: {},
            currencyId: null,
            alert_message: null,
            filterSummary: {
                date: 'Fiscal Year',
                date_type: 'this_year',
                aged_date_type: 'end_last_year',
                comparison: 'no_comparison',
                previous_periods: 1,
                date_from_cmp: '',
                date_to_cmp: '',
                percentage_base: 'revenue',
                period_order: 'descending',
                comparison_in: 'amount',
                rounding: '.',
                target_move: 'Posted Entries',
                account_type: 'receivable',
                account_types: ['receivable', 'payable'],
                partner_accounts: {
                    receivable: true,
                    non_trade_receivable: false,
                    payable: true,
                    non_trade_payable: false,
                },
                date_basis: 'date_maturity',
                period_length: 30,
                show_draft: false,
                show_currency: false,
                show_account: false,
                hide_lines_at_0: false,
                split_horizontally: false,
                analytic_simulations: false,
                subtotals: false,
                partners: [],
                tags: [],
                analytic_accounts: [],
                analytic_plans: [],
                asset_categories: [],
                gaap: 'Local Gaap',
                gaap_options: {
                    local_gaap: true
                }
            },
            available_ledgers: [],
            percentageMenuOpen: false,
            customDateFrom: '',
            customDateTo: '',
            partnerSearch: '',
            tagSearch: '',
            analyticSearch: '',
            analyticPlanSearch: '',
            assetCategorySearch: '',
            partnerResults: [],
            tagResults: [],
            analyticResults: [],
            analyticPlanResults: [],
            assetCategoryResults: [],
            unfoldAll: false,
            model_name: null,
            openDropdownLineId: null,
            dropdownIsDropup: false,
            searchQuery: '',
            selectedSplitLineId: null,
            splitSearchQuery: '',
            currency_symbol: '₹',
            integrations: { dms: false, knowledge: false },
        });

        // Stack of saved param objects for in-place sub-report navigation
        this._paramStack = [];
        // Active params (single source of truth — avoids OWL read-only props mutation)
        this._currentParams = null;

        this.handleClickOutside = (ev) => {
            if (this.state.openDropdownLineId) {
                if (!ev.target.closest('.o_dynamic_report_dropdown')) {
                    this.state.openDropdownLineId = null;
                }
            }
        };
        document.addEventListener('click', this.handleClickOutside);

        onWillStart(async () => {
            await this.fetchData();
        });

        onWillUnmount(() => {
            document.removeEventListener('click', this.handleClickOutside);
        });
    }

    toggleLineDropdown(lineId, ev = null) {
        if (this.state.openDropdownLineId === lineId) {
            this.state.openDropdownLineId = null;
            return;
        }
        this.state.openDropdownLineId = lineId;
        if (ev && ev.target) {
            const rect = ev.target.getBoundingClientRect();
            const spaceBelow = window.innerHeight - rect.bottom;
            this.state.dropdownIsDropup = (spaceBelow < 200);
        } else {
            this.state.dropdownIsDropup = false;
        }
    }

    formatDateLocal(date) {
        if (!date) return '';
        if (typeof date === 'string') {
            if (/^\d{4}-\d{2}-\d{2}$/.test(date)) return date;
            date = new Date(date);
        }
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    }

    detectDateType(dateFrom, dateTo) {
        if (!dateFrom || !dateTo) return 'this_year';
        const now = new Date();
        const y = now.getFullYear();
        const m = now.getMonth();
        const q = Math.floor(m / 3);

        const todayStr = this.formatDateLocal(now);
        if (dateFrom === todayStr && dateTo === todayStr) return 'today';

        const thisMonthStart = this.formatDateLocal(new Date(y, m, 1));
        const thisMonthEnd = this.formatDateLocal(new Date(y, m + 1, 0));
        if (dateFrom === thisMonthStart && dateTo === thisMonthEnd) return 'this_month';

        const thisQuarterStart = this.formatDateLocal(new Date(y, q * 3, 1));
        const thisQuarterEnd = this.formatDateLocal(new Date(y, q * 3 + 3, 0));
        if (dateFrom === thisQuarterStart && dateTo === thisQuarterEnd) return 'this_quarter';

        const thisYearStart = `${y}-01-01`;
        const thisYearEnd = `${y}-12-31`;
        if (dateFrom === thisYearStart && dateTo === thisYearEnd) return 'this_year';

        const lastMonthStart = this.formatDateLocal(new Date(y, m - 1, 1));
        const lastMonthEnd = this.formatDateLocal(new Date(y, m, 0));
        if (dateFrom === lastMonthStart && dateTo === lastMonthEnd) return 'last_month';

        const lastQ = q === 0 ? 3 : q - 1;
        const lastQYear = q === 0 ? y - 1 : y;
        const lastQuarterStart = this.formatDateLocal(new Date(lastQYear, lastQ * 3, 1));
        const lastQuarterEnd = this.formatDateLocal(new Date(lastQYear, lastQ * 3 + 3, 0));
        if (dateFrom === lastQuarterStart && dateTo === lastQuarterEnd) return 'last_quarter';

        const lastYearStart = `${y - 1}-01-01`;
        const lastYearEnd = `${y - 1}-12-31`;
        if (dateFrom === lastYearStart && dateTo === lastYearEnd) return 'last_year';

        return 'custom';
    }

    formatDateDisplay(dateStr) {
        if (!dateStr) {
            const today = new Date();
            const d = String(today.getDate()).padStart(2, '0');
            const m = String(today.getMonth() + 1).padStart(2, '0');
            const y = today.getFullYear();
            return `${d}/${m}/${y}`;
        }
        if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
            const parts = dateStr.split('-');
            return `${parts[2]}/${parts[1]}/${parts[0]}`;
        }
        return dateStr;
    }

    isNegativeValue(val) {
        if (val === null || val === undefined || val === '') return false;
        if (typeof val === 'number') return val < -0.00001;
        const clean = String(val).replace(/[^0-9.-]/g, '');
        const num = parseFloat(clean);
        return !isNaN(num) && num < -0.00001;
    }

    isZeroValue(val) {
        if (val === null || val === undefined || val === '') return true;
        if (typeof val === 'number') return Math.abs(val) < 0.00001;
        const clean = String(val).replace(/[^0-9.-]/g, '');
        const num = parseFloat(clean);
        return isNaN(num) || Math.abs(num) < 0.00001;
    }

    async fetchData() {
        const action = this.props?.action || {};
        // Use _currentParams if set (in-place navigation), otherwise fall back to props
        let params = this.reportParams;
        let model_name = params.model_name || this.state.model_name || null;

        // Primary storage key is based on model_name; secondary/fallback key is the action ID.
        // We always write to BOTH keys so that back-navigation (where model_name may be missing
        // from the restored props) can still find the full params via the action ID.
        const actionId = action.id || action.tag || this.props?.actionId || 'default';
        const actionStorageKey = 'hudson_report_params_action_' + actionId;

        if (params.model_name) {
            // Params are fully specified — persist them under both keys
            const modelStorageKey = 'hudson_report_params_' + params.model_name;
            sessionStorage.setItem(modelStorageKey, JSON.stringify(params));
            sessionStorage.setItem(actionStorageKey, JSON.stringify(params));
            this._currentParams = params;
        } else {
            // Try to recover params: first from action-ID key (works after back-navigation),
            // then from model-name key if model_name is already known in state.
            let saved = sessionStorage.getItem(actionStorageKey);
            if (!saved && model_name) {
                saved = sessionStorage.getItem('hudson_report_params_' + model_name);
            }
            if (saved) {
                params = JSON.parse(saved);
                model_name = params.model_name || model_name;
                this._currentParams = params;
            }
        }
        
        const wizard_id = params.wizard_id || null;
        const data = params.data || {};
        
        this.state.model_name = model_name;
        
        if (!data.form) data.form = {};
        if (data.date_from && !data.form.date_from) data.form.date_from = data.date_from;
        if (data.date_to && !data.form.date_to) data.form.date_to = data.date_to;
        if (data.form.date_from && !data.date_from) data.date_from = data.form.date_from;
        if (data.form.date_to && !data.date_to) data.date_to = data.form.date_to;

        // Auto-heal old cached buggy UTC date skew (e.g. 2025-12-31 to 2026-12-30) from previous versions
        if (data.form.date_from === '2025-12-31' && (data.form.date_to === '2026-12-30' || data.form.date_to === '2026-12-31')) {
            data.form.date_from = false;
            data.form.date_to = false;
            data.date_from = false;
            data.date_to = false;
        }

        if (!data.form.date_from && !data.form.date_to && model_name !== 'account.aged.report') {
            const now = new Date();
            if (['account.deferred.revenue.report', 'account.deferred.expense.report'].includes(model_name)) {
                const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
                const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0);
                data.form.date_from = this.formatDateLocal(firstDay);
                data.form.date_to = this.formatDateLocal(lastDay);
                data.date_from = data.form.date_from;
                data.date_to = data.form.date_to;
                this.state.filterSummary.date_type = 'this_month';
                const monthName = now.toLocaleString('default', { month: 'long' });
                this.state.filterSummary.date = `${monthName} ${now.getFullYear()}`;
            } else {
                const firstDay = new Date(now.getFullYear(), 0, 1);
                const lastDay = new Date(now.getFullYear(), 11, 31);
                data.form.date_from = this.formatDateLocal(firstDay);
                data.form.date_to = this.formatDateLocal(lastDay);
                data.date_from = data.form.date_from;
                data.date_to = data.form.date_to;
                this.state.filterSummary.date_type = 'this_year';
                this.state.filterSummary.date = `${now.getFullYear()}`;
            }
            if (data.form.used_context) {
                data.form.used_context.date_from = data.form.date_from;
                data.form.used_context.date_to = data.form.date_to;
            }
        }

        if (data.form.date_from) {
            this.state.customDateFrom = data.form.date_from;
            this.state.filterSummary.date_from = data.form.date_from;
        }
        if (data.form.date_to) {
            this.state.customDateTo = data.form.date_to;
            this.state.filterSummary.date_to = data.form.date_to;
        }
        if (!this.state.filterSummary.date_type && data.form.date_from && data.form.date_to) {
            this.state.filterSummary.date_type = this.detectDateType(data.form.date_from, data.form.date_to);
        }

        // If it's an aged report, try to read the wizard's actual values to populate filterSummary
        if (model_name === 'account.aged.report') {
            const formData = data.form || data;
            if (formData.as_of_date || formData.date_to) {
                this.state.filterSummary.date = formData.as_of_date || formData.date_to;
            }
            if (formData.account_type) {
                this.state.filterSummary.account_type = formData.account_type;
            }
            if (formData.date_basis) {
                this.state.filterSummary.date_basis = formData.date_basis;
            }
            if (formData.period_length) {
                this.state.filterSummary.period_length = formData.period_length;
            }
            
            if (wizard_id) {
                try {
                    const wizData = await this.orm.read(model_name, [wizard_id], ['as_of_date', 'account_type', 'date_basis', 'period_length', 'show_draft', 'show_currency', 'show_account', 'hide_lines_at_0', 'partner_ids', 'partner_category_ids']);
                    if (wizData && wizData.length > 0) {
                        const wiz = wizData[0];
                        if (wiz.as_of_date) this.state.filterSummary.date = wiz.as_of_date;
                        if (wiz.account_type) this.state.filterSummary.account_type = wiz.account_type;
                        if (wiz.date_basis) this.state.filterSummary.date_basis = wiz.date_basis;
                        if (wiz.period_length) this.state.filterSummary.period_length = wiz.period_length;
                        this.state.filterSummary.show_draft = wiz.show_draft;
                        this.state.filterSummary.show_currency = wiz.show_currency;
                        this.state.filterSummary.show_account = wiz.show_account;
                        this.state.filterSummary.hide_lines_at_0 = wiz.hide_lines_at_0;
                        
                        if (wiz.partner_ids && wiz.partner_ids.length > 0) {
                            const partners = await this.orm.read('res.partner', wiz.partner_ids, ['id', 'name']);
                            this.state.filterSummary.partners = partners;
                        }
                        if (wiz.partner_category_ids && wiz.partner_category_ids.length > 0) {
                            const tags = await this.orm.read('res.partner.category', wiz.partner_category_ids, ['id', 'name']);
                            this.state.filterSummary.tags = tags;
                        }
                        if (wiz.analytic_account_ids && wiz.analytic_account_ids.length > 0) {
                            const anAccs = await this.orm.read('account.analytic.account', wiz.analytic_account_ids, ['id', 'name']);
                            this.state.filterSummary.analytic_accounts = anAccs;
                        }
                    }
                } catch (e) {
                    console.warn("Could not read wizard data", e);
                }
            }
        }

        // Also restore analytic accounts/plans from form data if not yet populated
        const currAnAccIds = data.form?.analytic_account_ids || data.analytic_account_ids || [];
        if (currAnAccIds.length > 0 && (!this.state.filterSummary.analytic_accounts || !this.state.filterSummary.analytic_accounts.length)) {
            try {
                const anAccs = await this.orm.read('account.analytic.account', currAnAccIds, ['id', 'name']);
                this.state.filterSummary.analytic_accounts = anAccs;
            } catch (e) { }
        }
        const currAnPlanIds = data.form?.analytic_plan_ids || data.analytic_plan_ids || [];
        if (currAnPlanIds.length > 0 && (!this.state.filterSummary.analytic_plans || !this.state.filterSummary.analytic_plans.length)) {
            try {
                const anPlans = await this.orm.read('account.analytic.plan', currAnPlanIds, ['id', 'name']);
                this.state.filterSummary.analytic_plans = anPlans;
            } catch (e) { }
        }

        if (['account.partner.ledger', 'account.report.partner.ledger'].includes(model_name)) {
            const formData = data.form || data;
            let types = ['receivable', 'payable'];
            if (formData.account_types && Array.isArray(formData.account_types) && formData.account_types.length > 0) {
                types = [...formData.account_types];
            } else if (formData.account_type) {
                if (formData.account_type === 'receivable') {
                    types = ['receivable'];
                } else if (formData.account_type === 'payable') {
                    types = ['payable'];
                } else if (formData.account_type === 'all') {
                    types = ['receivable', 'non_trade_receivable', 'payable', 'non_trade_payable'];
                } else {
                    types = ['receivable', 'payable'];
                }
            } else {
                types = ['receivable', 'payable'];
            }
            this.state.filterSummary.account_types = types;
            this.state.filterSummary.partner_accounts = {
                receivable: types.includes('receivable'),
                non_trade_receivable: types.includes('non_trade_receivable'),
                payable: types.includes('payable'),
                non_trade_payable: types.includes('non_trade_payable'),
            };
            formData.account_types = types;
            data.account_types = types;
        }

        const result = await this.orm.call("hudson.dynamic.report", "get_report_data", [
            model_name,
            wizard_id,
            data
        ]);

        try {
            const integrations = await this.orm.call("hudson.dynamic.report", "get_installed_integrations", []);
            this.state.integrations = integrations;
        } catch (e) {
            console.warn("Could not fetch integrations", e);
        }

        this.state.title = result.title;
        this.state.columns = result.columns;
        this.state.column_groups = result.column_groups || [];
        const lines = result.lines || [];
        for (let i = 0; i < lines.length; i++) {
            lines[i]._index = i;
            lines[i].has_children = (i < lines.length - 1) && (lines[i + 1].level > lines[i].level);
        }
        this.state.lines = lines;
        this.state.currencyId = result.currency_id;
        this.state.currency_symbol = result.currency_symbol || '₹';
        this.state.alert_message = result.alert_message || null;
        this.state.companies_description = result.companies_description || '';
        this.state.available_ledgers = result.available_ledgers || [];
        
        if (result.date_from && result.date_to) {
            this.state.filterSummary.date_from = result.date_from;
            this.state.filterSummary.date_to = result.date_to;
            this.state.customDateFrom = result.date_from;
            this.state.customDateTo = result.date_to;
        } else if (result.date_to) {
            this.state.filterSummary.date_to = result.date_to;
            this.state.customDateTo = result.date_to;
        }
        if (result.target_move) {
            this.state.filterSummary.target_move = (result.target_move === 'posted') ? 'Posted Entries' : 'All Entries';
        }
        
        // Setup smart line expansion matching standard ERP reporting
        const expanded = {};
        if (model_name === 'account.aged.report' || model_name === 'account.report.partner.ledger') {
            // In Aged reports and Partner Ledger, groups/partners are collapsed by default unless Unfold All is active
            if (this.state.unfoldAll) {
                for (const line of lines) {
                    expanded[line.id] = true;
                }
            }
        } else if (model_name === 'account.print.journal') {
            // In Journal Audit, journals (Level 1) are expanded by default so accounts are visible matching Odoo Online
            for (const line of lines) {
                if (this.state.unfoldAll || line.level === 1) {
                    expanded[line.id] = true;
                }
            }
        } else if (model_name === 'account.cash.flow.wizard') {
            // In Cash Flow Statement, expand Level 1 & 2 by default so sections & sub-lines are visible, while accounts & transactions (Level 3+) stay collapsed
            for (const line of lines) {
                if (this.state.unfoldAll || line.level <= 2) {
                    expanded[line.id] = true;
                }
            }
        } else if (model_name === 'account.report.general.ledger' || model_name === 'account.balance.report') {
            // In General Ledger and Trial Balance, collapse by default so the initial view is compact and clean.
            // Users can expand individual groups and accounts on demand or use Unfold All.
            if (this.state.unfoldAll) {
                for (const line of lines) {
                    expanded[line.id] = true;
                }
            }
        } else {
            for (const line of lines) {
                expanded[line.id] = true;
            }
        }
        this.state.expandedLines = expanded;
    }

    async onDateFilter(type) {
        const params = this._ensureCurrentParams();
        const data = params.data;
        const form_data = data.form || data;
        const now = new Date();
        const y = now.getFullYear();
        const m = now.getMonth();
        const q = Math.floor(m / 3);
        
        if (type === 'today') {
            const today = this.formatDateLocal(now);
            form_data.date_from = today;
            form_data.date_to = today;
            this.state.filterSummary.date = 'Today';
            this.state.filterSummary.date_type = 'today';
        } else if (type === 'this_month') {
            const firstDay = new Date(y, m, 1);
            const lastDay = new Date(y, m + 1, 0);
            form_data.date_from = this.formatDateLocal(firstDay);
            form_data.date_to = this.formatDateLocal(lastDay);
            const monthName = now.toLocaleString('default', { month: 'long' });
            this.state.filterSummary.date = `${monthName} ${y}`;
            this.state.filterSummary.date_type = 'this_month';
        } else if (type === 'this_quarter') {
            const firstDay = new Date(y, q * 3, 1);
            const lastDay = new Date(y, q * 3 + 3, 0);
            form_data.date_from = this.formatDateLocal(firstDay);
            form_data.date_to = this.formatDateLocal(lastDay);
            this.state.filterSummary.date = `Q${q + 1} ${y}`;
            this.state.filterSummary.date_type = 'this_quarter';
        } else if (type === 'this_year') {
            const firstDay = new Date(y, 0, 1);
            const lastDay = new Date(y, 11, 31);
            form_data.date_from = this.formatDateLocal(firstDay);
            form_data.date_to = this.formatDateLocal(lastDay);
            this.state.filterSummary.date = `${y}`;
            this.state.filterSummary.date_type = 'this_year';
        } else if (type === 'last_month') {
            const firstDay = new Date(y, m - 1, 1);
            const lastDay = new Date(y, m, 0);
            form_data.date_from = this.formatDateLocal(firstDay);
            form_data.date_to = this.formatDateLocal(lastDay);
            const lastMonthName = firstDay.toLocaleString('default', { month: 'long' });
            this.state.filterSummary.date = `${lastMonthName} ${firstDay.getFullYear()}`;
            this.state.filterSummary.date_type = 'last_month';
        } else if (type === 'last_quarter') {
            const targetQuarter = q === 0 ? 3 : q - 1;
            const targetYear = q === 0 ? y - 1 : y;
            const firstDay = new Date(targetYear, targetQuarter * 3, 1);
            const lastDay = new Date(targetYear, targetQuarter * 3 + 3, 0);
            form_data.date_from = this.formatDateLocal(firstDay);
            form_data.date_to = this.formatDateLocal(lastDay);
            this.state.filterSummary.date = `Q${targetQuarter + 1} ${targetYear}`;
            this.state.filterSummary.date_type = 'last_quarter';
        } else if (type === 'last_year') {
            const prevYear = y - 1;
            const firstDay = new Date(prevYear, 0, 1);
            const lastDay = new Date(prevYear, 11, 31);
            form_data.date_from = this.formatDateLocal(firstDay);
            form_data.date_to = this.formatDateLocal(lastDay);
            this.state.filterSummary.date = `${prevYear}`;
            this.state.filterSummary.date_type = 'last_year';
        }
        data.date_from = form_data.date_from;
        data.date_to = form_data.date_to;
        form_data.date_type = this.state.filterSummary.date_type;
        data.date_type = this.state.filterSummary.date_type;
        this.state.filterSummary.date_from = form_data.date_from;
        this.state.filterSummary.date_to = form_data.date_to;
        this.state.customDateFrom = form_data.date_from;
        this.state.customDateTo = form_data.date_to;
        
        if (form_data.used_context) {
            form_data.used_context.date_from = form_data.date_from;
            form_data.used_context.date_to = form_data.date_to;
        }
        
        this._saveParams();
        
        const wizard_id = params.wizard_id;
        const model_name = params.model_name;
        if (wizard_id && model_name) {
            try {
                await this.orm.write(model_name, [wizard_id], {
                    date_from: form_data.date_from,
                    date_to: form_data.date_to,
                });
            } catch (e) {
                console.warn("Could not write date fields to wizard", e);
            }
        }
        
        await this.fetchData();
    }

    async applyCustomDates() {
        let fromDate = this.state.customDateFrom;
        let toDate = this.state.customDateTo;
        
        if (!fromDate) fromDate = this.state.filterSummary.date_from || toDate;
        if (!toDate) toDate = this.state.filterSummary.date_to || fromDate;
        if (!fromDate && !toDate) return;
        
        this.state.customDateFrom = fromDate;
        this.state.customDateTo = toDate;
        
        const params = this._ensureCurrentParams();
        const data = params.data;
        const form_data = data.form || data;
        
        form_data.date_from = fromDate;
        form_data.date_to = toDate;
        data.date_from = fromDate;
        data.date_to = toDate;
        
        const detectedType = this.detectDateType(fromDate, toDate);
        this.state.filterSummary.date_type = detectedType;
        form_data.date_type = detectedType;
        data.date_type = detectedType;
        this.state.filterSummary.date = `${this.formatDateDisplay(fromDate)} to ${this.formatDateDisplay(toDate)}`;
        this.state.filterSummary.date_from = fromDate;
        this.state.filterSummary.date_to = toDate;
        
        if (form_data.used_context) {
            form_data.used_context.date_from = fromDate;
            form_data.used_context.date_to = toDate;
        }
        
        this._saveParams();
        
        const wizard_id = params.wizard_id;
        const model_name = params.model_name;
        if (wizard_id && model_name) {
            try {
                await this.orm.write(model_name, [wizard_id], {
                    date_from: fromDate,
                    date_to: toDate,
                });
            } catch (e) {
                console.warn("Could not write date fields to wizard", e);
            }
        }
        
        await this.fetchData();
    }

    async onTargetMove(type) {
        const params = this._ensureCurrentParams();
        const data = params.data;
        const form_data = data.form || data;
        
        form_data.target_move = type;
        data.target_move = type;
        this.state.filterSummary.target_move = type === 'posted' ? 'Posted Entries' : 'All Entries';
        
        this._saveParams();
        
        const wizard_id = params.wizard_id;
        const model_name = params.model_name;
        if (wizard_id && model_name) {
            try {
                await this.orm.write(model_name, [wizard_id], {
                    target_move: form_data.target_move,
                });
            } catch (e) { }
        }
        
        await this.fetchData();
    }

    async onComparisonFilter(type) {
        this.state.filterSummary.comparison = type;
        if (type !== 'percentage') {
            this.state.percentageMenuOpen = false;
        }
        const params = this._ensureCurrentParams ? this._ensureCurrentParams() : this.reportParams;
        const data = params.data || {};
        const form_data = data.form || data;

        if (!this.state.filterSummary.percentage_base) {
            this.state.filterSummary.percentage_base = this.isBalanceSheetReport() ? 'total_assets' : 'revenue';
        }

        form_data.comparison = type;
        data.comparison = type;
        form_data.previous_periods = this.state.filterSummary.previous_periods || 1;
        data.previous_periods = form_data.previous_periods;
        form_data.percentage_base = this.state.filterSummary.percentage_base;
        data.percentage_base = form_data.percentage_base;
        form_data.period_order = this.state.filterSummary.period_order || 'descending';
        data.period_order = form_data.period_order;
        form_data.comparison_in = this.state.filterSummary.comparison_in || 'amount';
        data.comparison_in = form_data.comparison_in;

        if (type === 'custom_dates' || type === 'specific_date') {
            if (!this.state.filterSummary.date_from_cmp || !this.state.filterSummary.date_to_cmp) {
                const df = form_data.date_from || this.state.customDateFrom;
                const dt = form_data.date_to || this.state.customDateTo;
                if (df && dt) {
                    const d1 = new Date(df + 'T00:00:00');
                    const d2 = new Date(dt + 'T00:00:00');
                    d1.setFullYear(d1.getFullYear() - 1);
                    d2.setFullYear(d2.getFullYear() - 1);
                    this.state.filterSummary.date_from_cmp = this.formatDateLocal(d1);
                    this.state.filterSummary.date_to_cmp = this.formatDateLocal(d2);
                }
            }
            form_data.date_from_cmp = this.state.filterSummary.date_from_cmp;
            form_data.date_to_cmp = this.state.filterSummary.date_to_cmp;
            data.date_from_cmp = form_data.date_from_cmp;
            data.date_to_cmp = form_data.date_to_cmp;
        } else {
            form_data.date_to_cmp = false;
            form_data.date_from_cmp = false;
            data.date_to_cmp = false;
            data.date_from_cmp = false;
        }
        
        if (this._saveParams) this._saveParams();

        const wizard_id = params.wizard_id;
        const model_name = params.model_name;
        if (wizard_id && model_name) {
            try {
                // If model supports these fields
                await this.orm.write(model_name, [wizard_id], {
                    comparison: form_data.comparison,
                    previous_periods: form_data.previous_periods,
                    date_to_cmp: form_data.date_to_cmp || false
                });
            } catch (e) { }
        }
        await this.fetchData();
    }

    async onPercentageBaseChange(ev) {
        this.state.filterSummary.percentage_base = ev.target.value;
        await this.onComparisonFilter('percentage');
    }

    async onComparisonOptionsChange() {
        const data = this.reportParams.data || {};
        const form_data = data.form || data;
        form_data.period_order = this.state.filterSummary.period_order || 'descending';
        form_data.comparison_in = this.state.filterSummary.comparison_in || 'amount';
        await this.onComparisonFilter(this.state.filterSummary.comparison || 'no_comparison');
    }

    async onPreviousPeriodsChange(ev) {
        const val = parseInt(ev.target.value, 10) || 1;
        this.state.filterSummary.previous_periods = Math.max(1, val);
        await this.onComparisonFilter('previous_period');
    }

    async onDateFromCmpChange(ev) {
        this.state.filterSummary.date_from_cmp = ev.target.value;
        await this.onComparisonFilter('custom_dates');
    }

    async onDateToCmpChange(ev) {
        this.state.filterSummary.date_to_cmp = ev.target.value;
        await this.onComparisonFilter('custom_dates');
    }

    async onPeriodOrderChange(ev) {
        this.state.filterSummary.period_order = ev.target.value;
        await this.onComparisonOptionsChange();
    }

    async onComparisonInChange(ev) {
        this.state.filterSummary.comparison_in = ev.target.value;
        await this.onComparisonOptionsChange();
    }

    async onRounding(type) {
        this.state.filterSummary.rounding = type;
        const data = this.reportParams.data || {};
        const form_data = data.form || data;
        form_data.rounding = type;
        await this.fetchData();
    }

    closeBanner() {
        this.state.bannerClosed = true;
    }

    async onAgedDateFilter(type) {
        let newDate = '';
        const today = new Date();
        
        if (type === 'today') {
            newDate = this.formatDateLocal(today);
        } else if (type === 'end_last_month') {
            const date = new Date(today.getFullYear(), today.getMonth(), 0);
            newDate = this.formatDateLocal(date);
        } else if (type === 'end_last_quarter') {
            const q = Math.floor(today.getMonth() / 3);
            const date = new Date(today.getFullYear(), q * 3, 0);
            newDate = this.formatDateLocal(date);
        } else if (type === 'end_last_year') {
            const date = new Date(today.getFullYear(), 0, 0);
            newDate = this.formatDateLocal(date);
        } else if (type === 'custom') {
            newDate = this.state.customDateFrom || this.state.filterSummary.date || this.formatDateLocal(today);
        }

        this.state.filterSummary.date = newDate;
        this.state.filterSummary.aged_date_type = type;
        this.state.customDateFrom = newDate;
        
        const params = this._ensureCurrentParams();
        const data = params.data;
        const form_data = data.form || data;
        form_data.as_of_date = newDate;
        form_data.date_to = newDate;
        data.as_of_date = newDate;
        data.date_to = newDate;

        this._saveParams();

        const wizard_id = params.wizard_id;
        const model_name = params.model_name;
        if (wizard_id && model_name === 'account.aged.report') {
            try {
                await this.orm.write(model_name, [wizard_id], { as_of_date: newDate });
            } catch (e) {}
        }
        await this.fetchData();
    }

    async onAgedAccountFilter(type) {
        this.state.filterSummary.account_type = type;
        const data = this.reportParams.data || {};
        const form_data = data.form || data;
        form_data.account_type = type;

        const wizard_id = this.reportParams.wizard_id;
        const model_name = this.reportParams.model_name;
        if (wizard_id && model_name === 'account.aged.report') {
            try {
                await this.orm.write(model_name, [wizard_id], { account_type: type });
            } catch (e) {}
        }
        await this.fetchData();
    }

    getPartnerAccountLabel() {
        const types = this.state.filterSummary.account_types || ['receivable', 'payable'];
        const hasRec = types.includes('receivable');
        const hasPay = types.includes('payable');
        const hasNtRec = types.includes('non_trade_receivable');
        const hasNtPay = types.includes('non_trade_payable');

        if (types.length === 4) {
            return 'Account: All';
        }
        if (hasRec && hasPay && !hasNtRec && !hasNtPay) {
            return 'Account: Trade Partners';
        }
        if (!hasRec && !hasPay && hasNtRec && hasNtPay) {
            return 'Account: Non-Trade Partners';
        }
        if (types.length === 1) {
            if (hasRec) return 'Account: Receivable';
            if (hasPay) return 'Account: Payable';
            if (hasNtRec) return 'Account: Non Trade Receivable';
            if (hasNtPay) return 'Account: Non Trade Payable';
        }
        const labels = [];
        if (hasRec) labels.push('Receivable');
        if (hasNtRec) labels.push('Non Trade Receivable');
        if (hasPay) labels.push('Payable');
        if (hasNtPay) labels.push('Non Trade Payable');
        return 'Account: ' + labels.join(', ');
    }

    isPartnerAccountTypeSelected(type) {
        if (this.state.filterSummary.partner_accounts) {
            return Boolean(this.state.filterSummary.partner_accounts[type]);
        }
        const types = this.state.filterSummary.account_types || ['receivable', 'payable'];
        return types.includes(type);
    }

    async togglePartnerAccountType(type, ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        let types = [...(this.state.filterSummary.account_types || ['receivable', 'payable'])];
        if (types.includes(type)) {
            if (types.length === 1) {
                return;
            }
            types = types.filter(t => t !== type);
        } else {
            types.push(type);
        }
        this.state.filterSummary.account_types = types;
        this.state.filterSummary.partner_accounts = {
            receivable: types.includes('receivable'),
            non_trade_receivable: types.includes('non_trade_receivable'),
            payable: types.includes('payable'),
            non_trade_payable: types.includes('non_trade_payable'),
        };

        const params = this._ensureCurrentParams();
        const data = params.data || {};
        if (!data.form) data.form = {};
        data.form.account_types = types;
        data.account_types = types;

        if (types.includes('receivable') && types.includes('payable') && !types.includes('non_trade_receivable') && !types.includes('non_trade_payable')) {
            data.form.account_type = 'trade';
        } else if (types.length === 1 && types[0] === 'receivable') {
            data.form.account_type = 'receivable';
        } else if (types.length === 1 && types[0] === 'payable') {
            data.form.account_type = 'payable';
        } else {
            data.form.account_type = 'custom';
        }
        this.state.filterSummary.account_type = data.form.account_type;

        this._saveParams();
        await this.fetchData();
    }

    async onPartnerAccountFilter(type) {
        let types = ['receivable', 'payable'];
        if (type === 'receivable') {
            types = ['receivable'];
        } else if (type === 'payable') {
            types = ['payable'];
        } else if (type === 'all') {
            types = ['receivable', 'non_trade_receivable', 'payable', 'non_trade_payable'];
        }
        this.state.filterSummary.account_types = types;
        this.state.filterSummary.partner_accounts = {
            receivable: types.includes('receivable'),
            non_trade_receivable: types.includes('non_trade_receivable'),
            payable: types.includes('payable'),
            non_trade_payable: types.includes('non_trade_payable'),
        };
        const params = this._ensureCurrentParams();
        const data = params.data || {};
        if (!data.form) data.form = {};
        data.form.account_types = types;
        data.account_types = types;
        data.form.account_type = type;
        this.state.filterSummary.account_type = type;
        this._saveParams();
        await this.fetchData();
    }

    async onAgedBasisFilter(type) {
        this.state.filterSummary.date_basis = type;
        const data = this.reportParams.data || {};
        const form_data = data.form || data;
        form_data.date_basis = type;

        const wizard_id = this.reportParams.wizard_id;
        const model_name = this.reportParams.model_name;
        if (wizard_id && model_name === 'account.aged.report') {
            try {
                await this.orm.write(model_name, [wizard_id], { date_basis: type });
            } catch (e) {}
        }
        await this.fetchData();
    }

    async onAgedPeriodFilter(days) {
        const p = parseInt(days);
        this.state.filterSummary.period_length = p;
        const data = this.reportParams.data || {};
        const form_data = data.form || data;
        form_data.period_length = p;

        const wizard_id = this.reportParams.wizard_id;
        const model_name = this.reportParams.model_name;
        if (wizard_id && model_name === 'account.aged.report') {
            try {
                await this.orm.write(model_name, [wizard_id], { period_length: p });
            } catch (e) {}
        }
        await this.fetchData();
    }

    async onAgedToggleOption(option) {
        this.state.filterSummary[option] = !this.state.filterSummary[option];
        const wizard_id = this.reportParams.wizard_id;
        const model_name = this.reportParams.model_name;
        if (wizard_id && model_name === 'account.aged.report') {
            const vals = {};
            vals[option] = this.state.filterSummary[option];
            await this.orm.write(model_name, [wizard_id], vals);
        }
        await this.fetchData();
    }

    onUnfoldAllToggle() {
        this.state.unfoldAll = !this.state.unfoldAll;
        const newExpanded = {};
        const model_name = this.state.model_name;
        if (this.state.unfoldAll) {
            this.state.lines.forEach(l => {
                newExpanded[l.id] = true;
            });
        } else if (model_name === 'account.cash.flow.wizard') {
            this.state.lines.forEach(l => {
                if (l.level <= 2) {
                    newExpanded[l.id] = true;
                }
            });
        } else if (model_name === 'account.print.journal') {
            this.state.lines.forEach(l => {
                if (l.level === 1) {
                    newExpanded[l.id] = true;
                }
            });
        }
        this.state.expandedLines = newExpanded;
    }

    async onPartnerSearch(ev) {
        const val = ev.target.value;
        if (!val) {
            await this.loadDefaultPartners();
            return;
        }
        if (val.length < 2) {
            this.state.partnerResults = [];
            return;
        }
        // Basic debounce
        if (this.partnerTimeout) clearTimeout(this.partnerTimeout);
        this.partnerTimeout = setTimeout(async () => {
            const results = await this.orm.searchRead('res.partner', [['name', 'ilike', val]], ['id', 'name'], { limit: 10 });
            this.state.partnerResults = results;
        }, 300);
    }

    async loadDefaultPartners() {
        if (!this.state.partnerResults || this.state.partnerResults.length === 0) {
            const results = await this.orm.searchRead('res.partner', [], ['id', 'name'], { limit: 20, order: 'name asc' });
            this.state.partnerResults = results;
        }
    }

    async onTagSearch(ev) {
        const val = ev.target.value;
        if (!val || val.length < 2) {
            this.state.tagResults = [];
            return;
        }
        if (this.tagTimeout) clearTimeout(this.tagTimeout);
        this.tagTimeout = setTimeout(async () => {
            const results = await this.orm.searchRead('res.partner.category', [['name', 'ilike', val]], ['id', 'name'], { limit: 10 });
            this.state.tagResults = results;
        }, 300);
    }

    selectPartner(p) {
        const partners = this.state.filterSummary.partners || [];
        if (!partners.some(x => x.id === p.id)) {
            this.state.filterSummary.partners = [...partners, p];
        }
        this.state.partnerSearch = '';
        this.state.partnerResults = [];
    }

    selectTag(t) {
        const tags = this.state.filterSummary.tags || [];
        if (!tags.some(x => x.id === t.id)) {
            this.state.filterSummary.tags = [...tags, t];
        }
        this.state.tagSearch = '';
        this.state.tagResults = [];
    }

    async removePartner(pid) {
        this.state.filterSummary.partners = (this.state.filterSummary.partners || []).filter(p => p.id !== pid);
        await this.applyPartnerFilters();
    }

    async removeTag(tid) {
        this.state.filterSummary.tags = (this.state.filterSummary.tags || []).filter(t => t.id !== tid);
        await this.applyPartnerFilters();
    }

    async applyPartnerFilters() {
        const wizard_id = this.reportParams.wizard_id;
        const model_name = this.reportParams.model_name;
        const partnerIds = (this.state.filterSummary.partners || []).map(p => p.id);
        const tagIds = (this.state.filterSummary.tags || []).map(t => t.id);
        if (wizard_id && model_name) {
            try {
                await this.orm.write(model_name, [wizard_id], { 
                    partner_ids: [[6, 0, partnerIds]],
                    partner_category_ids: [[6, 0, tagIds]]
                });
            } catch (e) { }
        }
        const data = this.reportParams.data || {};
        const form_data = data.form || data;
        form_data.partner_ids = partnerIds;
        form_data.partner_category_ids = tagIds;
        if (!form_data.used_context) form_data.used_context = {};
        form_data.used_context.partner_ids = partnerIds.length > 0 ? partnerIds : false;
        if (data.form && data.form.used_context) {
            data.form.used_context.partner_ids = partnerIds.length > 0 ? partnerIds : false;
        }
        await this.fetchData();
    }

    async onAnalyticSearch(ev) {
        const val = ev.target.value;
        if (!val) {
            await this.loadDefaultAnalytics();
            return;
        }
        if (val.length < 2) {
            this.state.analyticResults = [];
            return;
        }
        if (this.analyticTimeout) clearTimeout(this.analyticTimeout);
        this.analyticTimeout = setTimeout(async () => {
            const results = await this.orm.searchRead('account.analytic.account', [['name', 'ilike', val]], ['id', 'name'], { limit: 10 });
            this.state.analyticResults = results;
        }, 300);
    }

    async loadDefaultAnalytics() {
        if (!this.state.analyticResults || this.state.analyticResults.length === 0) {
            const results = await this.orm.searchRead('account.analytic.account', [], ['id', 'name'], { limit: 20, order: 'name asc' });
            this.state.analyticResults = results;
        }
    }

    selectAnalyticAccount(a) {
        if (!this.state.filterSummary.analytic_accounts) {
            this.state.filterSummary.analytic_accounts = [];
        }
        if (!this.state.filterSummary.analytic_accounts.some(x => x.id === a.id)) {
            this.state.filterSummary.analytic_accounts = [...this.state.filterSummary.analytic_accounts, a];
        }
        this.state.analyticSearch = '';
        this.state.analyticResults = [];
    }

    async removeAnalyticAccount(aid) {
        if (this.state.filterSummary.analytic_accounts) {
            this.state.filterSummary.analytic_accounts = this.state.filterSummary.analytic_accounts.filter(a => a.id !== aid);
        }
        await this.applyAnalyticFilters();
    }

    async applyAnalyticFilters() {
        const wizard_id = this.reportParams.wizard_id;
        const model_name = this.reportParams.model_name;
        const accountIds = (this.state.filterSummary.analytic_accounts || []).map(a => a.id);
        const planIds = (this.state.filterSummary.analytic_plans || []).map(p => p.id);
        if (wizard_id && model_name) {
            try {
                await this.orm.write(model_name, [wizard_id], { 
                    analytic_account_ids: [[6, 0, accountIds]]
                });
            } catch (e) { }
        }
        const data = this.reportParams.data || {};
        const form_data = data.form || data;
        form_data.analytic_account_ids = accountIds;
        form_data.analytic_plan_ids = planIds;
        if (!form_data.used_context) form_data.used_context = {};
        form_data.used_context.analytic_account_ids = accountIds.length > 0 ? accountIds : false;
        if (data.form && data.form.used_context) {
            data.form.used_context.analytic_account_ids = accountIds.length > 0 ? accountIds : false;
        }
        await this.fetchData();
    }

    async onAnalyticPlanSearch(ev) {
        const val = ev.target.value;
        if (!val) {
            await this.loadDefaultAnalyticPlans();
            return;
        }
        if (val.length < 2) {
            this.state.analyticPlanResults = [];
            return;
        }
        if (this.analyticPlanTimeout) clearTimeout(this.analyticPlanTimeout);
        this.analyticPlanTimeout = setTimeout(async () => {
            const results = await this.orm.searchRead('account.analytic.plan', [['name', 'ilike', val]], ['id', 'name'], { limit: 10 });
            this.state.analyticPlanResults = results;
        }, 300);
    }

    async loadDefaultAnalyticPlans() {
        if (!this.state.analyticPlanResults || this.state.analyticPlanResults.length === 0) {
            const results = await this.orm.searchRead('account.analytic.plan', [], ['id', 'name'], { limit: 20, order: 'name asc' });
            this.state.analyticPlanResults = results;
        }
    }

    selectAnalyticPlan(p) {
        if (!this.state.filterSummary.analytic_plans) {
            this.state.filterSummary.analytic_plans = [];
        }
        if (!this.state.filterSummary.analytic_plans.some(x => x.id === p.id)) {
            this.state.filterSummary.analytic_plans = [...this.state.filterSummary.analytic_plans, p];
        }
        this.state.analyticPlanSearch = '';
        this.state.analyticPlanResults = [];
    }

    async removeAnalyticPlan(pid) {
        if (this.state.filterSummary.analytic_plans) {
            this.state.filterSummary.analytic_plans = this.state.filterSummary.analytic_plans.filter(p => p.id !== pid);
        }
        await this.applyAnalyticFilters();
    }

    async onAssetCategorySearch(ev) {
        const val = ev.target.value;
        if (!val) {
            await this.loadDefaultAssetCategories();
            return;
        }
        if (this.assetCatTimeout) clearTimeout(this.assetCatTimeout);
        this.assetCatTimeout = setTimeout(async () => {
            const results = await this.orm.searchRead('account.asset.category', [['name', 'ilike', val], ['type', '=', 'purchase']], ['id', 'name'], { limit: 10 });
            this.state.assetCategoryResults = results;
        }, 300);
    }

    async loadDefaultAssetCategories() {
        if (!this.state.assetCategoryResults || this.state.assetCategoryResults.length === 0) {
            const results = await this.orm.searchRead('account.asset.category', [['type', '=', 'purchase']], ['id', 'name'], { limit: 20, order: 'name asc' });
            this.state.assetCategoryResults = results;
        }
    }

    selectAssetCategory(c) {
        if (!this.state.filterSummary.asset_categories) {
            this.state.filterSummary.asset_categories = [];
        }
        if (!this.state.filterSummary.asset_categories.some(x => x.id === c.id)) {
            this.state.filterSummary.asset_categories = [...this.state.filterSummary.asset_categories, c];
        }
        this.state.assetCategorySearch = '';
        this.state.assetCategoryResults = [];
    }

    async removeAssetCategory(catId) {
        if (this.state.filterSummary.asset_categories) {
            this.state.filterSummary.asset_categories = this.state.filterSummary.asset_categories.filter(c => c.id !== catId);
        }
        await this.applyAssetCategoryFilters();
    }

    async applyAssetCategoryFilters() {
        const params = this.reportParams;
        const data = params.data || {};
        const form_data = data.form || data;
        form_data.category_ids = (this.state.filterSummary.asset_categories || []).map(c => c.id);
        this._saveParams();
        await this.fetchData();
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
    }

    getGaapButtonLabel() {
        const gaap = this.state.filterSummary.gaap_options || { local_gaap: true };
        let selectedCount = 0;
        let lastName = '';
        
        if (gaap.local_gaap) {
            selectedCount++;
            lastName = 'Local Gaap';
        }
        
        if (this.state.available_ledgers) {
            for (const ledger of this.state.available_ledgers) {
                if (gaap[ledger.id]) {
                    selectedCount++;
                    lastName = ledger.name;
                }
            }
        }
        
        if (selectedCount === 0) return 'All Ledgers';
        if (selectedCount === 1) return lastName;
        return 'Multiple Ledgers';
    }

    async toggleGaap(option) {
        if (!this.state.filterSummary.gaap_options) {
            this.state.filterSummary.gaap_options = { local_gaap: true };
        }
        if (option === 'local_gaap') {
            this.state.filterSummary.gaap_options = { local_gaap: true };
            if (this.state.available_ledgers) {
                for (const ledger of this.state.available_ledgers) {
                    this.state.filterSummary.gaap_options[ledger.id] = false;
                }
            }
        } else {
            this.state.filterSummary.gaap_options[option] = !this.state.filterSummary.gaap_options[option];
            if (this.state.filterSummary.gaap_options[option]) {
                this.state.filterSummary.gaap_options.local_gaap = false;
            }
            let anySelected = false;
            if (this.state.available_ledgers) {
                for (const ledger of this.state.available_ledgers) {
                    if (this.state.filterSummary.gaap_options[ledger.id]) anySelected = true;
                }
            }
            if (!anySelected) {
                this.state.filterSummary.gaap_options.local_gaap = true;
            }
        }
        
        this.state.filterSummary.gaap = this.getGaapButtonLabel();
        
        const params = this._ensureCurrentParams();
        const data = params.data || {};
        const form_data = data.form || data;
        form_data.gaap_options = this.state.filterSummary.gaap_options;
        this._saveParams();
        await this.fetchData();
    }

    onGaapFilter(type) {
        this.state.filterSummary.gaap = type;
    }

    async onPartnerAccountFilter(type) {
        this.state.filterSummary.account_type = type;
        const data = this.reportParams.data || {};
        const form_data = data.form || data;
        form_data.account_type = type;
        await this.fetchData();
    }

    async switchReport(newModelName) {
        if (this.state.model_name === newModelName) return;
        this.state.model_name = newModelName;
        if (!this._currentParams) {
            this._currentParams = Object.assign({}, this.reportParams);
        }
        this._currentParams.model_name = newModelName;
        this._currentParams.wizard_id = null;
        if (this.props?.action?.params) {
            this.props.action.params.model_name = newModelName;
            this.props.action.params.wizard_id = null;
        }
        await this.fetchData();
    }

    toggleHideLinesAt0() {
        this.state.filterSummary.hide_lines_at_0 = !this.state.filterSummary.hide_lines_at_0;
    }

    toggleSplitHorizontally() {
        this.state.filterSummary.split_horizontally = !this.state.filterSummary.split_horizontally;
    }

    async toggleDraftEntries() {
        const isDraft = this.state.filterSummary.target_move === 'All Entries';
        await this.onTargetMove(isDraft ? 'posted' : 'all');
    }

    async toggleAnalyticSimulations() {
        this.state.filterSummary.analytic_simulations = !this.state.filterSummary.analytic_simulations;
        const data = this.reportParams.data || {};
        const form_data = data.form || data;
        form_data.analytic_simulations = this.state.filterSummary.analytic_simulations;
        await this.fetchData();
    }

    getTargetMoveButtonLabel() {
        const isDraft = this.state.filterSummary.target_move === 'All Entries';
        const isAnalyticSim = Boolean(this.state.filterSummary.analytic_simulations);
        if (isDraft && isAnalyticSim) {
            return "With Draft Entries, Including Analytic Simulations";
        } else if (isDraft) {
            return "With Draft Entries";
        } else if (isAnalyticSim) {
            return "Including Analytic Simulations";
        }
        return "Posted Entries";
    }

    isTargetMoveActive() {
        return this.state.filterSummary.target_move === 'All Entries' || Boolean(this.state.filterSummary.analytic_simulations);
    }

    isComparisonActive() {
        const c = this.state.filterSummary.comparison;
        return Boolean(c && c !== 'no_comparison');
    }

    getComparisonButtonLabel() {
        const c = this.state.filterSummary.comparison;
        if (!c || c === 'no_comparison') return 'Comparison';
        if (c === 'previous_period') {
            const periods = this.state.filterSummary.previous_periods || 1;
            return `Previous Period (${periods})`;
        }
        if (c === 'same_last_year') {
            return 'Same Period Last Year';
        }
        if (c === 'percentage') {
            return `% of ${this.getPercentageBaseLabel()}`;
        }
        if (c === 'custom_dates' || c === 'specific_date') {
            const df = this.state.filterSummary.date_from_cmp;
            const dt = this.state.filterSummary.date_to_cmp;
            if (df && dt && df !== dt) {
                return `${this.formatDateDisplay(df)} to ${this.formatDateDisplay(dt)}`;
            } else if (dt) {
                return `As of ${this.formatDateDisplay(dt)}`;
            }
            return 'Custom Dates';
        }
        return 'Comparison';
    }

    isComparisonSelected(type) {
        const c = this.state.filterSummary.comparison;
        if (type === 'no_comparison') {
            return !c || c === 'no_comparison';
        }
        if (type === 'custom_dates') {
            return c === 'custom_dates' || c === 'specific_date';
        }
        return c === type;
    }

    isCustomDatesSelected() {
        return this.isComparisonSelected('custom_dates');
    }

    onPercentageRowClick() {
        if (!this.isComparisonSelected('percentage')) {
            this.state.percentageMenuOpen = true;
            this.onComparisonFilter('percentage');
        } else {
            this.state.percentageMenuOpen = !this.state.percentageMenuOpen;
        }
    }

    togglePercentageMenu(ev) {
        if (ev) ev.stopPropagation();
        this.state.percentageMenuOpen = !this.state.percentageMenuOpen;
        if (!this.isComparisonSelected('percentage')) {
            this.onComparisonFilter('percentage');
        }
    }

    async selectPercentageBase(baseId, ev) {
        if (ev) ev.stopPropagation();
        this.state.filterSummary.percentage_base = baseId;
        this.state.percentageMenuOpen = false;
        await this.onComparisonFilter('percentage');
    }

    getPercentageBaseName(id) {
        const opts = this.getPercentageBaseOptions();
        const match = opts.find(o => o.id === id);
        if (match) return match.name;
        return (id || '').replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) || 'Revenue';
    }

    getPercentageBaseLabel() {
        if (!this.isComparisonSelected('percentage') && !this.state.percentageMenuOpen) {
            return '';
        }
        let base = this.state.filterSummary.percentage_base;
        if (!base) {
            base = this.isBalanceSheetReport() ? 'total_assets' : 'revenue';
            this.state.filterSummary.percentage_base = base;
        }
        return this.getPercentageBaseName(base);
    }

    getPercentageBaseOptions() {
        const options = [
            // Standard P&L sections / account types (exact match with user's image)
            { id: 'revenue', name: 'Revenue' },
            { id: 'costs_of_revenue', name: 'Costs of Revenue' },
            { id: 'gross_profit', name: 'Gross Profit' },
            { id: 'operating_expenses', name: 'Operating Expenses' },
            { id: 'operating_income', name: 'Operating Income (or Loss)' },
            { id: 'other_income', name: 'Other Income' },
            { id: 'other_expenses', name: 'Other Expenses' },
            { id: 'net_profit', name: 'Net Profit' },
            { id: 'allocations', name: 'Allocations and Withdrawals' },

            // Standard Balance Sheet sections / account types
            { id: 'total_assets', name: 'Total Assets' },
            { id: 'current_assets', name: 'Current Assets' },
            { id: 'bank_and_cash', name: 'Bank and Cash' },
            { id: 'receivables', name: 'Receivables' },
            { id: 'prepayments', name: 'Prepayments' },
            { id: 'fixed_assets', name: 'Fixed Assets' },
            { id: 'non_current_assets', name: 'Non-current Assets' },
            { id: 'total_liabilities', name: 'Total Liabilities' },
            { id: 'current_liabilities', name: 'Current Liabilities' },
            { id: 'payables', name: 'Payables' },
            { id: 'non_current_liabilities', name: 'Non-current Liabilities' },
            { id: 'total_equity', name: 'Total Equity' },
            { id: 'retained_earnings', name: 'Retained Earnings' },
            { id: 'total_liabilities_equity', name: 'Total Liabilities & Equity' },
        ];

        // Dynamically append any report sections from active report lines
        if (this.state.lines && this.state.lines.length) {
            for (const l of this.state.lines) {
                if ((l.level === 1 || l.level === 2) && l.name && !l.is_summary_banner) {
                    const cleanName = l.name.trim();
                    const cleanId = cleanName.toLowerCase().replace(/[^a-z0-9]+/g, '_');
                    if (cleanName && !options.some(o => o.id === cleanId || o.name.toLowerCase() === cleanName.toLowerCase())) {
                        options.push({ id: cleanId, name: cleanName });
                    }
                }
            }
        }

        return options;
    }

    isBalanceSheetReport() {
        const title = (this.state.title || '').toLowerCase();
        const model = this.state.model_name || '';
        if (title.includes('balance sheet')) return true;
        if (model === 'account.financial.report' && !title.includes('profit') && !title.includes('loss') && !title.includes('income')) return true;
        return false;
    }

    isProfitAndLossReport() {
        if (this.isBalanceSheetReport()) return false;
        const title = (this.state.title || '').toLowerCase();
        const model = this.state.model_name || '';
        return title.includes('profit') || title.includes('loss') || title.includes('income') ||
               model === 'account.profit.and.loss';
    }

    formatDateRangeLabel(dateFrom, dateTo) {
        if (!dateFrom || !dateTo) return `${new Date().getFullYear()}`;
        const d1 = new Date(dateFrom + 'T00:00:00');
        const d2 = new Date(dateTo + 'T00:00:00');
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const m1 = months[d1.getMonth()];
        const y1 = d1.getFullYear();
        const m2 = months[d2.getMonth()];
        const y2 = d2.getFullYear();
        if (y1 === y2) {
            if (m1 === 'Jan' && m2 === 'Dec' && d1.getDate() === 1 && d2.getDate() >= 30) {
                return `${y1}`;
            }
            if (m1 === m2 && d1.getDate() === 1) {
                const fullMonth = d1.toLocaleString('default', { month: 'long' });
                return `${fullMonth} ${y1}`;
            }
            return `${m1} - ${m2} ${y1}`;
        }
        return `${m1} ${y1} - ${m2} ${y2}`;
    }

    getDateButtonLabel() {
        const t = this.state.filterSummary.date_type;
        const now = new Date();
        const y = now.getFullYear();
        if (t === 'today') {
            return 'Today';
        }
        if (t === 'this_month') {
            const monthName = now.toLocaleString('default', { month: 'long' });
            return `${monthName} ${y}`;
        }
        if (t === 'this_quarter') {
            const quarter = Math.floor(now.getMonth() / 3) + 1;
            return `Q${quarter} ${y}`;
        }
        if (t === 'this_year') {
            return `${y}`;
        }
        if (t === 'last_month') {
            const prevMonthDate = new Date(y, now.getMonth() - 1, 1);
            const monthName = prevMonthDate.toLocaleString('default', { month: 'long' });
            return `${monthName} ${prevMonthDate.getFullYear()}`;
        }
        if (t === 'last_quarter') {
            const currentQuarter = Math.floor(now.getMonth() / 3);
            const targetQuarter = currentQuarter === 0 ? 4 : currentQuarter;
            const targetYear = currentQuarter === 0 ? y - 1 : y;
            return `Q${targetQuarter} ${targetYear}`;
        }
        if (t === 'last_year') {
            return `${y - 1}`;
        }
        if (t === 'custom') {
            if (this.state.filterSummary.date_from && this.state.filterSummary.date_to) {
                return `${this.formatDateDisplay(this.state.filterSummary.date_from)} to ${this.formatDateDisplay(this.state.filterSummary.date_to)}`;
            }
            return this.state.filterSummary.date || 'Custom Dates';
        }
        if (this.state.filterSummary.date_from && this.state.filterSummary.date_to) {
            return this.formatDateRangeLabel(this.state.filterSummary.date_from, this.state.filterSummary.date_to);
        }
        return this.state.filterSummary.date || `${y}`;
    }

    getAgedDateButtonLabel() {
        const t = this.state.filterSummary.aged_date_type;
        if (t === 'today') return 'Today';
        if (t === 'end_last_month') return 'End of Last Month';
        if (t === 'end_last_quarter') return 'End of Last Quarter';
        if (t === 'end_last_year') return 'End of Last Financial Year';
        if (t === 'custom') return `As of: ${this.formatDateDisplay(this.state.filterSummary.date)}`;
        if (this.state.filterSummary.date) {
            const todayStr = this.formatDateLocal(new Date());
            if (this.state.filterSummary.date === todayStr) return 'Today';
            return `As of: ${this.formatDateDisplay(this.state.filterSummary.date)}`;
        }
        return 'Today';
    }

    toggleSubtotals() {
        this.state.filterSummary.subtotals = !this.state.filterSummary.subtotals;
    }

    isLineZero(line) {
        const checkFields = ['balance', 'debit', 'credit', 'tax', 'net', 'total', 'p0', 'p1', 'p2', 'p3', 'p4', 'not_due', 'amount_currency'];
        for (const f of checkFields) {
            if (line[f] !== undefined && line[f] !== null && Math.abs(Number(line[f])) > 0.0001) {
                return false;
            }
        }
        for (let i = 1; i <= 10; i++) {
            if (line[`balance_cmp_${i}`] !== undefined && Math.abs(Number(line[`balance_cmp_${i}`])) > 0.0001) {
                return false;
            }
        }
        return true;
    }

    hasNonZeroChildren(line) {
        const lines = this.state.lines;
        const index = this.getLineIndex(line);
        if (index === -1) return false;
        for (let i = index + 1; i < lines.length; i++) {
            if (lines[i].level <= line.level) break;
            if (!this.isLineZero(lines[i])) return true;
        }
        return false;
    }

    isSplitHorizontally() {
        return !!this.state.filterSummary.split_horizontally;
    }

    getLeftSplitLines() {
        if (!this.state.lines || !this.state.lines.length) return [];
        const lines = this.state.lines;

        // 1. Balance sheet: Assets on Left
        const titleUpper = (this.state.title || '').toUpperCase();
        if (titleUpper.includes('BALANCE SHEET') || lines.some(l => (l.name || '').toUpperCase().includes('ASSET') && l.level === 1)) {
            let left = [];
            let inLeft = false;
            for (let i = 0; i < lines.length; i++) {
                const l = lines[i];
                const nameUpper = (l.name || '').toUpperCase().trim();
                if (l.level === 1 || l.is_summary_total) {
                    if (nameUpper.includes('ASSET') && !nameUpper.includes('LIABILIT') && !nameUpper.includes('EQUITY')) {
                        inLeft = true;
                        left.push(l);
                    } else if (nameUpper.includes('LIABILIT') || nameUpper.includes('EQUITY') || nameUpper.includes('PASSIV') || nameUpper.includes('CAPITAL')) {
                        inLeft = false;
                    } else if (inLeft) {
                        left.push(l);
                    }
                } else if (inLeft) {
                    left.push(l);
                }
            }
            if (left.length > 0) return left;
        }

        // 2. All other reports (General Ledger, Trial Balance, Partner Ledger, Profit & Loss, Cash Flow, Tax, Aged, etc.):
        // Group into complete hierarchical blocks starting at the minimum level (e.g. Level 1 parent groups/accounts)
        const nonSummary = lines.filter(l => !l.is_summary_total);
        const minLevel = nonSummary.length ? Math.min(...nonSummary.map(l => l.level || 1)) : 1;

        const blocks = [];
        let currentBlock = [];
        for (let i = 0; i < lines.length; i++) {
            const l = lines[i];
            if (l.level === minLevel && currentBlock.length > 0) {
                blocks.push(currentBlock);
                currentBlock = [];
            }
            currentBlock.push(l);
        }
        if (currentBlock.length > 0) blocks.push(currentBlock);

        if (blocks.length > 1) {
            const mid = Math.ceil(blocks.length / 2);
            return blocks.slice(0, mid).flat();
        }

        // If only 1 root block exists, split at the direct children (minLevel + 1)
        if (blocks.length === 1 && lines.length > 1) {
            const root = lines[0];
            const subBlocks = [];
            let subCurrent = [];
            for (let i = 1; i < lines.length; i++) {
                const l = lines[i];
                if (l.level === minLevel + 1 && subCurrent.length > 0) {
                    subBlocks.push(subCurrent);
                    subCurrent = [];
                }
                subCurrent.push(l);
            }
            if (subCurrent.length > 0) subBlocks.push(subCurrent);
            if (subBlocks.length > 1) {
                const midSub = Math.ceil(subBlocks.length / 2);
                return [root, ...subBlocks.slice(0, midSub).flat()];
            }
        }

        const mid = Math.ceil(lines.length / 2);
        return lines.slice(0, mid);
    }

    getRightSplitLines() {
        if (!this.state.lines || !this.state.lines.length) return [];
        const lines = this.state.lines;

        // 1. Balance sheet: Liabilities & Equity on Right
        const titleUpper = (this.state.title || '').toUpperCase();
        if (titleUpper.includes('BALANCE SHEET') || lines.some(l => (l.name || '').toUpperCase().includes('LIABILIT') || (l.name || '').toUpperCase().includes('EQUITY'))) {
            let right = [];
            let inRight = false;
            for (let i = 0; i < lines.length; i++) {
                const l = lines[i];
                const nameUpper = (l.name || '').toUpperCase().trim();
                if (l.level === 1 || l.is_summary_total) {
                    if (nameUpper.includes('LIABILIT') || nameUpper.includes('EQUITY') || nameUpper.includes('PASSIV') || nameUpper.includes('CAPITAL')) {
                        inRight = true;
                        right.push(l);
                    } else if (nameUpper.includes('ASSET') && !nameUpper.includes('LIABILIT') && !nameUpper.includes('EQUITY')) {
                        inRight = false;
                    } else if (inRight) {
                        right.push(l);
                    }
                } else if (inRight) {
                    right.push(l);
                }
            }
            if (right.length > 0) return right;
        }

        // 2. All other reports:
        const nonSummary = lines.filter(l => !l.is_summary_total);
        const minLevel = nonSummary.length ? Math.min(...nonSummary.map(l => l.level || 1)) : 1;

        const blocks = [];
        let currentBlock = [];
        for (let i = 0; i < lines.length; i++) {
            const l = lines[i];
            if (l.level === minLevel && currentBlock.length > 0) {
                blocks.push(currentBlock);
                currentBlock = [];
            }
            currentBlock.push(l);
        }
        if (currentBlock.length > 0) blocks.push(currentBlock);

        if (blocks.length > 1) {
            const mid = Math.ceil(blocks.length / 2);
            return blocks.slice(mid).flat();
        }

        if (blocks.length === 1 && lines.length > 1) {
            const subBlocks = [];
            let subCurrent = [];
            for (let i = 1; i < lines.length; i++) {
                const l = lines[i];
                if (l.level === minLevel + 1 && subCurrent.length > 0) {
                    subBlocks.push(subCurrent);
                    subCurrent = [];
                }
                subCurrent.push(l);
            }
            if (subCurrent.length > 0) subBlocks.push(subCurrent);
            if (subBlocks.length > 1) {
                const midSub = Math.ceil(subBlocks.length / 2);
                return subBlocks.slice(midSub).flat();
            }
        }

        const mid = Math.ceil(lines.length / 2);
        return lines.slice(mid);
    }

    getLineIndex(line) {
        if (!line) return -1;
        if (line._index !== undefined) return line._index;
        const lines = this.state.lines;
        if (!lines || !lines.length) return -1;
        const idx = lines.indexOf(line);
        if (idx !== -1) return idx;
        return lines.findIndex(l => l.id === line.id);
    }

    toggleExpand(lineId) {
        const isExp = !this.state.expandedLines[lineId];
        this.state.expandedLines = Object.assign({}, this.state.expandedLines, { [lineId]: isExp });
    }

    isVisible(line) {
        if (this.state.filterSummary.hide_lines_at_0) {
            if (this.isLineZero(line) && !this.hasNonZeroChildren(line)) {
                return false;
            }
        }

        if (this.state.searchQuery) {
            const q = this.state.searchQuery.toLowerCase().trim();
            if (q) {
                const matches = (l) => {
                    for (const key of ['name', 'partner', 'account', 'journal', 'matching']) {
                        if (l[key] && String(l[key]).toLowerCase().includes(q)) return true;
                    }
                    return false;
                };
                
                if (matches(line)) return true;
                
                // If it's a parent line and has children matching, show parent
                const lines = this.state.lines;
                const index = this.getLineIndex(line);
                if (index !== -1) {
                    for (let i = index + 1; i < lines.length; i++) {
                        if (lines[i].level <= line.level) break;
                        if (matches(lines[i])) return true;
                    }
                }
                return false;
            }
        }

        if (line.level === 1) return true;
        
        const lines = this.state.lines;
        const index = this.getLineIndex(line);
        if (index === -1) return true;
        for (let i = index - 1; i >= 0; i--) {
            if (lines[i].level < line.level) {
                if (!this.state.expandedLines[lines[i].id]) {
                    return false;
                }
                if (!this.isVisible(lines[i])) {
                    return false;
                }
                break;
            }
        }
        return true;
    }

    getAgedAccountLabel() {
        const t = this.state.filterSummary.account_type;
        if (t === 'payable') return 'Account: Payable';
        if (t === 'receivable') return 'Account: Receivable';
        if (t === 'non_trade_payable') return 'Account: Non-Trade Payable';
        if (t === 'non_trade_receivable') return 'Account: Non-Trade Receivable';
        return 'Account: ' + (t ? t.replace(/_/g, ' ') : 'Payable');
    }

    formatDateDisplay(dateStr) {
        if (!dateStr) {
            const now = new Date();
            const d = String(now.getDate()).padStart(2, '0');
            const m = String(now.getMonth() + 1).padStart(2, '0');
            const y = now.getFullYear();
            return `${d}/${m}/${y}`;
        }
        if (typeof dateStr === 'string' && dateStr.includes('-')) {
            const parts = dateStr.split('-');
            if (parts.length === 3) {
                return `${parts[2]}/${parts[1]}/${parts[0]}`;
            }
        }
        return dateStr;
    }

    parseNumericValue(val) {
        if (val === undefined || val === null || val === '' || val === '—' || val === '-') return null;
        if (typeof val === 'number') return val;
        let s = String(val).replace(/[%$₹€£,\s]/g, '').trim();
        if (s === '' || s === '-' || s === '—') return null;
        let num = parseFloat(s);
        return isNaN(num) ? null : num;
    }

    isNegativeValue(val) {
        const num = this.parseNumericValue(val);
        if (num === null) return false;
        return num < -0.005;
    }

    isZeroValue(val) {
        const num = this.parseNumericValue(val);
        if (num === null) return true;
        return Math.abs(num) < 0.005;
    }

    isPositiveValue(val) {
        const num = this.parseNumericValue(val);
        if (num === null) return false;
        return num > 0.005;
    }

    getColumnClass(col) {
        if (!col) return '';
        const field = (col.field || '').replace(/_/g, '-');
        const fieldClass = field ? `col-${field}` : '';
        if (col.type === 'monetary' || col.type === 'percentage') {
            return `col-monetary ${fieldClass}`.trim();
        }
        if (col.type === 'integer') {
            return `text-center ${fieldClass}`.trim();
        }
        return fieldClass;
    }

    getMonetaryValueClass(val) {
        if (this.isZeroValue(val)) return 'o_report_val_zero';
        if (this.isNegativeValue(val)) return 'o_report_val_negative';
        return 'o_report_val_positive';
    }

    getCellValueClass(val, col) {
        if (!col) return '';
        if (col.type === 'percentage' || (col.field && (col.field === 'percentage_val' || col.field.endsWith('_pct')))) {
            if (this.isZeroValue(val)) return 'o_report_val_zero';
            if (this.isNegativeValue(val)) return 'o_report_pct_negative text-danger fw-semibold';
            if (this.isPositiveValue(val)) return 'o_report_pct_positive text-success fw-semibold';
            return 'o_report_val_zero';
        }
        if (col.type === 'monetary') {
            if (this.isZeroValue(val)) return 'o_report_val_zero';
            if (this.isNegativeValue(val)) return 'o_report_val_negative';
            return 'o_report_val_positive';
        }
        return '';
    }

    formatCellValue(value, line, col) {
        if (!col) return value || '';
        if (col.type === 'monetary') {
            return this.formatMonetary(value, line, col);
        }
        if (col.type === 'percentage' || (col.field && (col.field === 'percentage_val' || col.field.endsWith('_pct')))) {
            if (value === null || value === undefined || value === '') return '';
            if (typeof value === 'string' && value.includes('%')) {
                let num = this.parseNumericValue(value);
                if (num !== null && (Math.abs(num) < 0.005 || Object.is(num, -0))) {
                    return '0.00 %';
                }
                return value;
            }
            let num = this.parseNumericValue(value);
            if (num === null) return value || '';
            if (Math.abs(num) < 0.005 || Object.is(num, -0)) num = 0;
            return `${num.toFixed(2)} %`;
        }
        if (col.type === 'integer') {
            if (value === null || value === undefined || value === '') return '';
            let num = Number(value);
            if (isNaN(num)) return value;
            if (Math.abs(num) < 0.005 || Object.is(num, -0)) num = 0;
            return String(num);
        }
        return value || '';
    }

    formatMonetary(value, line, col) {
        if (value === undefined || value === null || value === '') return "";
        let num = Number(value);
        if (isNaN(num)) return value;
        if (Math.abs(num) < 0.005 || Object.is(num, -0)) {
            num = 0;
        }
        const rounding = this.state.filterSummary.rounding !== undefined ? this.state.filterSummary.rounding : '.';
        if (rounding === 'K') {
            num = num / 1000;
        } else if (rounding === 'L') {
            num = num / 100000;
        } else if (rounding === 'M') {
            num = num / 1000000;
        }
        if (Math.abs(num) < 0.005 || Object.is(num, -0)) {
            num = 0;
        }
        const decimals = (rounding === '.') ? 2 : 0;
        const formatted = num.toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
        let symbol = this.state.currency_symbol || '₹';
        if (col && col.field === 'amount_currency' && line && line.foreign_currency_symbol) {
            symbol = line.foreign_currency_symbol;
        }
        return `${symbol} ${formatted}`;
    }

    async openExchangeRates() {
        await this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Exchange Rates',
            res_model: 'res.currency.rate',
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
        });
    }

    async createAdjustmentEntry() {
        const date = this.state.filterSummary.date || '';
        await this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Make Adjustment Entry',
            res_model: 'account.unrealized.currency.adjustment.wizard',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
            context: {
                'default_date': (date && date !== 'Fiscal Year') ? date : undefined,
            }
        });
    }

    hasChildren(line) {
        if (!line) return false;
        if (line.has_children !== undefined) {
            return Boolean(line.has_children);
        }
        const lines = this.state.lines;
        const index = this.getLineIndex(line);
        if (index !== -1 && index < lines.length - 1) {
            return lines[index + 1].level > line.level;
        }
        return false;
    }
    
    async onLineClicked(line) {
        const params = this.reportParams;
        const model_name = params.model_name;
        const data = params.data || {};
        const form_data = data.form || data;
        
        // Toggle expand for expandable lines when row is clicked (if not clicking directly into a transaction/move)
        if (this.hasChildren(line) && !line.move_id && line.type !== 'move_line' && !line.move_line_id) {
            this.toggleExpand(line.id);
            return;
        }
        
        // 1. Click on a transaction / move line (in Cash Flow, General Ledger, Partner Ledger, Trial Balance)
        if (line.move_id || line.type === 'move_line' || line.move_line_id) {
            if (line.move_id) {
                let docTitle = 'Journal Entry';
                if (['out_invoice', 'out_refund', 'out_receipt'].includes(line.move_type)) {
                    docTitle = 'Customer Invoice';
                } else if (['in_invoice', 'in_refund', 'in_receipt'].includes(line.move_type)) {
                    docTitle = 'Vendor Bill';
                }
                
                await this.action.doAction({
                    type: 'ir.actions.act_window',
                    name: docTitle,
                    res_model: 'account.move',
                    res_id: line.move_id,
                    view_mode: 'form',
                    views: [[false, 'form']],
                });
                return;
            } else if (line.move_line_id) {
                await this.action.doAction({
                    type: 'ir.actions.act_window',
                    name: 'Journal Item',
                    res_model: 'account.move.line',
                    res_id: line.move_line_id,
                    view_mode: 'form',
                    views: [[false, 'form']],
                });
                return;
            }
        }

        // Click on an Asset line (Depreciation Schedule)
        if (line.asset_id || (line.res_model === 'account.asset.asset' && line.res_id)) {
            const assetId = line.asset_id || line.res_id;
            await this.action.doAction({
                type: 'ir.actions.act_window',
                name: line.name || 'Asset',
                res_model: 'account.asset.asset',
                res_id: assetId,
                view_mode: 'form',
                views: [[false, 'form']],
            });
            return;
        }
        
        // 2. Click on an Account line or component line (Trial Balance, General Ledger, Cash Flow, Balance Sheet, P&L)
        if (line.type === 'account' || line.account_id || (line.account_ids && line.account_ids.length)) {
            const date_from = form_data.date_from || form_data.date_from_cmp;
            const date_to = form_data.date_to || form_data.date_to_cmp;
            
            const domain = [];
            if (line.account_id) {
                domain.push(['account_id', '=', line.account_id]);
            } else if (line.account_ids && line.account_ids.length) {
                domain.push(['account_id', 'in', line.account_ids]);
            } else if (line.name && line.type === 'account') {
                const code = line.name.trim().split(' ')[0];
                if (/^\d+$/.test(code)) {
                    domain.push(['account_id.code', '=', code]);
                } else {
                    return;
                }
            } else {
                return;
            }
            if (line.journal_id) {
                domain.push(['journal_id', '=', line.journal_id]);
            }
            
            if (date_from) domain.push(['date', '>=', date_from]);
            if (date_to) domain.push(['date', '<=', date_to]);
            if (form_data.target_move === 'posted') domain.push(['parent_state', '=', 'posted']);
            
            await this.action.doAction({
                type: 'ir.actions.act_window',
                name: `Journal Items - ${line.name}`,
                res_model: 'account.move.line',
                view_mode: 'list,form',
                views: [[false, 'list'], [false, 'form']],
                domain: domain,
                context: {
                    'search_default_posted': form_data.target_move === 'posted' ? 1 : 0,
                    'search_default_group_by_move': 1,
                }
            });
        }
    }

    async onAuditTax(line) {
        if (!line.tax_id) return;
        
        const params = this.reportParams;
        const data = params.data || {};
        const form_data = data.form || data;
        
        const date_from = form_data.date_from;
        const date_to = form_data.date_to;
        
        const action = {
            type: 'ir.actions.act_window',
            name: 'Journal Items for Tax Audit',
            res_model: 'account.move.line',
            view_mode: 'list,form',
            views: [[false, 'list'], [false, 'form']],
            domain: ['|', ['tax_line_id', '=', line.tax_id], ['tax_ids', 'in', [line.tax_id]]],
            context: {
                'search_default_group_by_account': 1,
            }
        };
        
        if (date_from) action.domain.push(['date', '>=', date_from]);
        if (date_to) action.domain.push(['date', '<=', date_to]);
        
        await this.action.doAction(action);
    }

    async onActionClicked(line, actionName) {
        const params = this.reportParams;
        const data = params.data || {};
        const form_data = data.form || data;
        
        if (actionName === 'open_asset' && (line.asset_id || line.res_id)) {
            await this.action.doAction({
                type: 'ir.actions.act_window',
                name: line.name || 'Asset',
                res_model: 'account.asset.asset',
                res_id: line.asset_id || line.res_id,
                view_mode: 'form',
                views: [[false, 'form']],
            });
            return;
        } else if (actionName === 'open_partner' && line.partner_id) {
            await this.action.doAction({
                type: 'ir.actions.act_window',
                name: 'Partner',
                res_model: 'res.partner',
                res_id: line.partner_id,
                view_mode: 'form',
                views: [[false, 'form']],
            });
        } else if (actionName === 'open_journal_items') {
            const date_from = form_data.date_from;
            const date_to = form_data.date_to;
            
            const domain = [];
            if (line.account_id) {
                domain.push(['account_id', '=', line.account_id]);
            } else if (line.account_ids && line.account_ids.length) {
                domain.push(['account_id', 'in', line.account_ids]);
            } else if (line.name && line.type === 'account') {
                const code = line.name.trim().split(' ')[0];
                if (/^\d+$/.test(code)) {
                    domain.push(['account_id.code', '=', code]);
                }
            }
            if (line.partner_id) domain.push(['partner_id', '=', line.partner_id]);
            if (line.journal_id) domain.push(['journal_id', '=', line.journal_id]);
            if (date_from) domain.push(['date', '>=', date_from]);
            if (date_to) domain.push(['date', '<=', date_to]);
            if (form_data.target_move === 'posted') domain.push(['parent_state', '=', 'posted']);
            
            const action = {
                type: 'ir.actions.act_window',
                name: `Journal Items - ${line.name}`,
                res_model: 'account.move.line',
                view_mode: 'list,form',
                views: [[false, 'list'], [false, 'form']],
                domain: domain,
                context: {
                    'search_default_posted': form_data.target_move === 'posted' ? 1 : 0,
                    'search_default_group_by_move': 1,
                }
            };
            
            await this.action.doAction(action);
        } else if (actionName === 'open_documents' && line.journal_id) {
            const date_from = form_data.date_from;
            const date_to = form_data.date_to;
            const domain = [['journal_id', '=', line.journal_id]];
            if (date_from) domain.push(['date', '>=', date_from]);
            if (date_to) domain.push(['date', '<=', date_to]);
            if (form_data.target_move === 'posted') domain.push(['state', '=', 'posted']);
            await this.action.doAction({
                type: 'ir.actions.act_window',
                name: `Journal Entries - ${line.name}`,
                res_model: 'account.move',
                view_mode: 'list,form',
                views: [[false, 'list'], [false, 'form']],
                domain: domain,
            });
        } else if (actionName === 'open_to_review' && line.journal_id) {
            const date_from = form_data.date_from;
            const date_to = form_data.date_to;
            const domain = [
                ['journal_id', '=', line.journal_id],
                '|', ['state', '=', 'draft'], ['review_state', '=', 'todo']
            ];
            if (date_from) domain.push(['date', '>=', date_from]);
            if (date_to) domain.push(['date', '<=', date_to]);
            await this.action.doAction({
                type: 'ir.actions.act_window',
                name: `Entries To Review - ${line.name}`,
                res_model: 'account.move',
                view_mode: 'list,form',
                views: [[false, 'list'], [false, 'form']],
                domain: domain,
            });
        } else if (actionName === 'open_general_ledger') {
            const date_from = form_data.date_from;
            const date_to = form_data.date_to;
            
            const domain = [];
            if (line.account_id) {
                domain.push(['account_id', '=', line.account_id]);
            } else if (line.account_ids && line.account_ids.length) {
                domain.push(['account_id', 'in', line.account_ids]);
            } else if (line.name) {
                const code = line.name.trim().split(' ')[0];
                if (/^\d+$/.test(code)) {
                    domain.push(['account_id.code', '=', code]);
                }
            }
            if (date_from) domain.push(['date', '>=', date_from]);
            if (date_to) domain.push(['date', '<=', date_to]);
            if (form_data.target_move === 'posted') domain.push(['parent_state', '=', 'posted']);
            
            const action = {
                type: 'ir.actions.act_window',
                name: `General Ledger - ${line.name}`,
                res_model: 'account.move.line',
                view_mode: 'list,form',
                views: [[false, 'list'], [false, 'form']],
                domain: domain,
                context: {
                    'search_default_group_by_account': 1,
                    'search_default_posted': form_data.target_move === 'posted' ? 1 : 0,
                },
            };
            
            await this.action.doAction(action);
        } else if (actionName === 'open_journal_entry' && line.move_id) {
            let docTitle = 'Journal Entry';
            if (['out_invoice', 'out_refund'].includes(line.move_type)) {
                docTitle = 'Customer Invoice';
            } else if (['in_invoice', 'in_refund'].includes(line.move_type)) {
                docTitle = 'Vendor Bill';
            }
            await this.action.doAction({
                type: 'ir.actions.act_window',
                name: docTitle,
                res_model: 'account.move',
                res_id: line.move_id,
                view_mode: 'form',
                views: [[false, 'form']],
            });
        } else if (actionName === 'open_statement' && line.partner_id) {
            const action = await this.orm.call("hudson.dynamic.report", "action_open_statement", [
                line.partner_id
            ]);
            if (action) {
                await this.action.doAction(action);
            }
        }
    }

    async exportPDF() {
        const params = this.reportParams;
        const model_name = params.model_name;
        const wizard_id = params.wizard_id;
        const data = params.data || {};
        
        if (model_name && wizard_id) {
            try {
                const context = {
                    active_model: data.model || this.props?.action?.context?.active_model || model_name,
                    active_ids: data.ids || this.props?.action?.context?.active_ids || [wizard_id],
                    active_id: (data.ids && data.ids[0]) || this.props?.action?.context?.active_id || wizard_id,
                };
                const action = await this.orm.call(model_name, "check_report", [[wizard_id]], { context });
                if (action) {
                    if (!action.context) {
                        action.context = {};
                    }
                    Object.assign(action.context, context);
                    await this.action.doAction(action);
                    return;
                }
            } catch (e) {
                console.warn("Could not execute check_report, falling back to window.print", e);
            }
        }
        window.print();
    }

    /**
     * The report as currently displayed, for the "Copy to Documents" and
     * "Insert in Article" wizards.
     *  - lines: every line with raw values (same input as the XLSX button)
     *  - rows: the visible lines, with values formatted as on screen
     *    (rounding, currency symbol, percentages), for the PDF and the article
     */
    _getExportPayload() {
        const columns = (this.state.columns || []).map((col) => ({
            field: col.field,
            label: col.label,
            type: col.type,
        }));
        // Only the lines visible on screen (folding, search, hidden zero lines),
        // with raw values: the server formats them (hudson.report.snapshot).
        const lines = (this.state.lines || []).filter((line) => this.isVisible(line)).map((line) => {
            const out = {
                level: line.level,
                is_summary_total: !!line.is_summary_total,
                is_summary_banner: !!line.is_summary_banner,
            };
            for (const col of columns) {
                out[col.field] = line[col.field];
            }
            return out;
        });
        return {
            title: this.state.title,
            date_str: this.state.filterSummary.date === 'Fiscal Year' ? new Date().toLocaleDateString() : this.state.filterSummary.date,
            columns,
            lines,
        };
    }

    async onExportToDocuments() {
        await this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Export',
            res_model: 'hudson.report.export.dms.wizard',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_name: this.state.title,
                default_report_data: JSON.stringify(this._getExportPayload()),
            }
        });
    }

    async onInsertInArticle() {
        await this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Select an article',
            res_model: 'hudson.report.export.knowledge.wizard',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
            context: {
                default_name: this.state.title,
                default_report_data: JSON.stringify(this._getExportPayload()),
            }
        });
    }

    exportCSV() {
        const columns = this.state.columns || [];
        const lines = this.state.lines || [];
        
        // Build CSV header
        const headers = columns.map(c => `"${(c.label || '').replace(/"/g, '""')}"`);
        const rows = [headers.join(',')];
        
        for (const line of lines) {
            const row = columns.map(col => {
                let val = line[col.field];
                if (val === undefined || val === null) {
                    val = '';
                } else if (col.type === 'monetary') {
                    val = typeof val === 'number' ? val.toFixed(2) : String(val);
                } else {
                    val = String(val);
                }
                return `"${val.replace(/"/g, '""')}"`;
            });
            rows.push(row.join(','));
        }
        
        const csvContent = "\uFEFF" + rows.join('\r\n'); // Add UTF-8 BOM for Excel
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement("a");
        const url = URL.createObjectURL(blob);
        link.setAttribute("href", url);
        const filename = `${(this.state.title || 'report').replace(/[\s\/\\?%*:|"<>]/g, '_')}_${this.formatDateLocal(new Date())}.csv`;
        link.setAttribute("download", filename);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }

    exportXLSX() {
        // Export all lines regardless of expansion state
        const lines = this.state.lines;
        
        // Prepare data for backend
        const reportData = {
            title: this.state.title,
            columns: this.state.columns,
            lines: lines,
            date_str: this.state.filterSummary.date === 'Fiscal Year' ? new Date().toLocaleDateString() : this.state.filterSummary.date
        };
        
        // Create a hidden form to submit via POST for file download
        const form = document.createElement("form");
        form.method = "POST";
        form.action = "/hudson_dynamic_reports/export_xlsx";
        
        const dataInput = document.createElement("input");
        dataInput.type = "hidden";
        dataInput.name = "data";
        dataInput.value = JSON.stringify(reportData);
        form.appendChild(dataInput);
        
        document.body.appendChild(form);
        form.submit();
        document.body.removeChild(form);
    }

    exportJSON() {
        const data = {
            title: this.state.title,
            columns: this.state.columns,
            lines: this.state.lines
        };
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const link = document.createElement("a");
        const url = URL.createObjectURL(blob);
        link.setAttribute("href", url);
        link.setAttribute("download", `${this.state.title.replace(/\s+/g, '_')}.json`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }
}

DynamicReport.template = "hudson_dynamic_reports.DynamicReport";

registry.category("actions").add("hudson_dynamic_reports.dynamic_report", DynamicReport);
registry.category("actions").add("hudson_accounting_enhancements.dynamic_report", DynamicReport);

