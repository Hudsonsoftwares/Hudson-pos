/** @odoo-module **/

// Payroll Dashboard: Odoo-style period search in the control panel.
// Facets "Month" and "Tax Year" replace the old in-page pickers. Choosing a value calls the
// existing window.hdsUpdatePeriod(month, fyId), which saves the period and swaps the dashboard
// HTML in place (no new data, no page reload). Removing a facet resets it to today's period.

import { Component, onWillStart, proxy, useListener } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";

export class PayrollPeriodSearch extends Component {
    static template = "hudson_in_payroll.PayrollPeriodSearch";

    setup() {
        this.orm = useService("orm");
        this.state = proxy({
            ready: false,
            months: [],
            fys: [],
            month: null,
            fyId: null,
            defaultMonth: null,
            defaultFyId: null,
            todayMonth: null,
            todayYear: null,
            query: "",
            menuOpen: false,
            activeIndex: 0,
        });
        onWillStart(async () => {
            try {
                const data = await this.orm.call("hds.payroll.dashboard", "get_period_search_data", []);
                Object.assign(this.state, {
                    months: data.months || [],
                    fys: data.fys || [],
                    month: data.month,
                    fyId: data.fy_id,
                    defaultMonth: data.default_month,
                    defaultFyId: data.default_fy_id,
                    todayMonth: data.today_month,
                    todayYear: data.today_year,
                    ready: true,
                });
            } catch {
                // No access / no data: the dashboard still works, only the search bar is hidden.
                this.state.ready = false;
            }
        });
        // Follow the saved period, whichever control changed it (search bar or header navigator)
        useListener(window, "hds-period-changed", (ev) => {
            const { month, fyId } = ev.detail || {};
            if (month) {
                this.state.month = String(month);
            }
            if (fyId) {
                this.state.fyId = fyId;
            }
        });
        // Close the menus when clicking anywhere outside the search bar
        useListener(
            window,
            "pointerdown",
            (ev) => {
                if (!(ev.target instanceof Element) || !ev.target.closest(".o_hds_period_search")) {
                    this.state.menuOpen = false;
                    this.state.query = "";
                }
            },
            true
        );
    }

    get fy() {
        return this.state.fys.find((fy) => fy.id === this.state.fyId);
    }

    // Calendar year of a month inside a tax year (April-March)
    yearOf(month, fy) {
        return fy ? (Number(month) >= 4 ? fy.start_year : fy.end_year) : "";
    }

    // Tax year that contains the given calendar month / year
    fyFor(month, year) {
        return this.state.fys.find((fy) => this.yearOf(month, fy) === year);
    }

    get monthLabel() {
        const month = this.state.months.find((m) => m.value === this.state.month);
        if (!month) {
            return "";
        }
        return `${month.name} ${this.yearOf(this.state.month, this.fy)}`.trim();
    }

    // "Month" column: the months of the selected tax year, April to March, split by quarter
    get monthItems() {
        const fy = this.fy;
        const items = [];
        [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3].forEach((num, index) => {
            const month = this.state.months.find((m) => Number(m.value) === num);
            if (month) {
                items.push({
                    value: month.value,
                    label: `${month.name} ${this.yearOf(num, fy)}`.trim(),
                    selected: month.value === this.state.month,
                    newQuarter: index > 0 && index % 3 === 0,
                });
            }
        });
        return items;
    }

    // "Filters" column: quick periods, resolved against the tax years that exist
    get quickFilters() {
        const state = this.state;
        const fy = this.fy;
        const item = (key, label, month, targetFy, newGroup = false) => ({
            key,
            label,
            newGroup,
            month: month ? String(month) : null,
            fyId: targetFy ? targetFy.id : null,
            disabled: !month || !targetFy,
            selected: !!month && !!targetFy && String(month) === state.month && targetFy.id === state.fyId,
        });
        let lastMonth = null;
        let lastMonthFy = null;
        if (state.todayMonth && state.todayYear) {
            const prevMonth = state.todayMonth === 1 ? 12 : state.todayMonth - 1;
            const prevYear = state.todayMonth === 1 ? state.todayYear - 1 : state.todayYear;
            lastMonth = prevMonth;
            lastMonthFy = this.fyFor(prevMonth, prevYear);
        }
        const previousFy = fy && state.fys.find((f) => f.start_year === fy.start_year - 1);
        return [
            item("this", "This Month", state.defaultMonth, state.fys.find((f) => f.id === state.defaultFyId)),
            item("last", "Last Month", lastMonth, lastMonthFy),
            item("last_year", "Same Month Last Year", state.month, previousFy),
            item("fy_start", "Tax Year Start (April)", 4, fy, true),
            item("fy_end", "Tax Year End (March)", 3, fy),
        ];
    }

    get fyLabel() {
        return this.fy ? this.fy.short : "";
    }

    get suggestions() {
        const query = this.state.query.trim().toLowerCase();
        if (!query) {
            return [];
        }
        const months = this.state.months
            .filter((m) => m.name.toLowerCase().includes(query))
            .map((m) => ({ key: `m${m.value}`, type: "month", value: m.value, field: "Month", label: m.name }));
        const fys = this.state.fys
            .filter((fy) => fy.short.toLowerCase().includes(query) || fy.name.toLowerCase().includes(query))
            .map((fy) => ({ key: `f${fy.id}`, type: "fy", value: fy.id, field: "Tax Year", label: fy.short }));
        return [...months, ...fys];
    }

    apply(type, value) {
        if (type === "month") {
            this.applyPeriod(value, null);
        } else if (type === "fy") {
            this.applyPeriod(null, value);
        }
    }

    // Month and/or tax year in one update; only changed values are sent
    applyPeriod(month, fyId) {
        this.state.query = "";
        this.state.menuOpen = false;
        this.state.activeIndex = 0;
        const newMonth = month && month !== this.state.month ? month : null;
        const newFyId = fyId && fyId !== this.state.fyId ? fyId : null;
        if (!newMonth && !newFyId) {
            return;
        }
        if (newMonth) {
            this.state.month = newMonth;
        }
        if (newFyId) {
            this.state.fyId = newFyId;
        }
        window.hdsUpdatePeriod?.(newMonth, newFyId);
    }

    selectQuickFilter(item) {
        if (!item.disabled) {
            this.applyPeriod(item.month, item.fyId);
        }
    }

    removeFacet(type) {
        this.apply(type, type === "month" ? this.state.defaultMonth : this.state.defaultFyId);
    }

    toggleMenu() {
        this.state.menuOpen = !this.state.menuOpen;
        this.state.query = "";
    }

    onInput(ev) {
        this.state.query = ev.target.value;
        this.state.activeIndex = 0;
        this.state.menuOpen = false;
    }

    onKeydown(ev) {
        const suggestions = this.suggestions;
        if (ev.key === "ArrowDown" && suggestions.length) {
            ev.preventDefault();
            this.state.activeIndex = Math.min(this.state.activeIndex + 1, suggestions.length - 1);
        } else if (ev.key === "ArrowUp" && suggestions.length) {
            ev.preventDefault();
            this.state.activeIndex = Math.max(this.state.activeIndex - 1, 0);
        } else if (ev.key === "Enter") {
            ev.preventDefault();
            const item = suggestions[this.state.activeIndex];
            if (item) {
                this.apply(item.type, item.value);
                ev.target.value = "";
            }
        } else if (ev.key === "Escape") {
            this.state.query = "";
            this.state.menuOpen = false;
            ev.target.value = "";
        } else if (ev.key === "Backspace" && !ev.target.value) {
            // Like Odoo: backspace on an empty input removes the last facet (Tax Year)
            this.removeFacet("fy");
        }
    }

    selectSuggestion(item, ev) {
        this.apply(item.type, item.value);
        const input = ev.target.closest(".o_hds_period_search")?.querySelector("input");
        if (input) {
            input.value = "";
        }
    }
}

export class PayrollDashboardFormController extends FormController {
    static template = "hudson_in_payroll.PayrollDashboardFormView";
    static components = { ...FormController.components, PayrollPeriodSearch };
}

registry.category("views").add("hds_payroll_dashboard_form", {
    ...formView,
    Controller: PayrollDashboardFormController,
});
