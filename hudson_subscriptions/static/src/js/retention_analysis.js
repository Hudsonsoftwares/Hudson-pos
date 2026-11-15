/** @odoo-module **/

import { Component, proxy, onWillStart, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class RetentionAnalysis extends Component {
    static template = "hudson_subscriptions.RetentionAnalysis";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = proxy({
            loading: true,
            measure: "count", // 'count', 'recurring_monthly', 'recurring_total'
            interval: "month", // 'day', 'week', 'month', 'year'
            searchQuery: "",
            showMeasureDropdown: false,
            showIntervalDropdown: false,
            cohorts: [],
            periods: [],
            average: null,
            listViewId: false,
        });

        this._searchTimeout = null;

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => {
            // Close dropdowns on outside click
            document.addEventListener("click", (e) => {
                if (!e.target.closest(".position-relative")) {
                    this.state.showMeasureDropdown = false;
                    this.state.showIntervalDropdown = false;
                }
            });
        });
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "sale.order",
                "get_retention_cohort_data",
                [],
                {
                    measure: this.state.measure,
                    interval: this.state.interval,
                    search_query: this.state.searchQuery,
                }
            );

            this.state.cohorts = data.cohorts || [];
            this.state.periods = data.periods || [];
            this.state.average = data.average || null;
            this.state.listViewId = data.list_view_id || false;
        } catch (err) {
            console.error("Error loading retention cohort data:", err);
        } finally {
            this.state.loading = false;
        }
    }

    getMeasureLabel() {
        if (this.state.measure === "recurring_monthly") return "Recurring Monthly (MRR)";
        if (this.state.measure === "recurring_total") return "Recurring Total";
        return "Measures";
    }

    getIntervalLabel() {
        const map = {
            day: "Day",
            week: "Week",
            month: "Month",
            year: "Year",
        };
        return map[this.state.interval] || "Month";
    }

    toggleMeasureDropdown(ev) {
        ev.stopPropagation();
        this.state.showMeasureDropdown = !this.state.showMeasureDropdown;
        this.state.showIntervalDropdown = false;
    }

    toggleIntervalDropdown(ev) {
        ev.stopPropagation();
        this.state.showIntervalDropdown = !this.state.showIntervalDropdown;
        this.state.showMeasureDropdown = false;
    }

    async setMeasure(measure) {
        this.state.measure = measure;
        this.state.showMeasureDropdown = false;
        await this.loadData();
    }

    async setInterval(interval) {
        this.state.interval = interval;
        this.state.showIntervalDropdown = false;
        await this.loadData();
    }

    onSearchInput(ev) {
        if (this._searchTimeout) {
            clearTimeout(this._searchTimeout);
        }
        this._searchTimeout = setTimeout(async () => {
            await this.loadData();
        }, 300);
    }

    getTierClass(percentage) {
        if (percentage >= 100) return "retention-tier-100";
        if (percentage >= 75) return "retention-tier-75";
        if (percentage >= 50) return "retention-tier-50";
        if (percentage >= 25) return "retention-tier-25";
        if (percentage > 0) return "retention-tier-1";
        return "retention-tier-0";
    }

    onCellClick(orderIds) {
        if (!orderIds || !orderIds.length) return;

        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Subscription",
            res_model: "sale.order",
            views: [
                [this.state.listViewId || false, "list"],
                [false, "form"],
            ],
            domain: [["id", "in", orderIds]],
            context: {
                create: false,
            },
        });
    }

    exportData() {
        if (!this.state.cohorts.length) return;

        const measureTitle = this.state.measure === "count" ? "Count" : (this.state.measure === "recurring_monthly" ? "MRR" : "Recurring Total");
        const headers = ["First Contract Date", measureTitle, ...this.state.periods.map(p => `+${p}`)];
        const rows = [headers];

        for (const cohort of this.state.cohorts) {
            const row = [cohort.label, cohort.count];
            for (const cell of cohort.cells) {
                row.push(cell ? `${cell.percentage}%` : "");
            }
            rows.push(row);
        }

        if (this.state.average) {
            const avgRow = [this.state.average.label, this.state.average.count];
            for (const avgCell of this.state.average.cells) {
                avgRow.push(avgCell ? `${avgCell.percentage}%` : "");
            }
            rows.push(avgRow);
        }

        const csvContent = "data:text/csv;charset=utf-8," + rows.map(e => e.map(val => `"${val}"`).join(",")).join("\n");
        const encodedUri = encodeURI(csvContent);
        const link = document.createElement("a");
        link.setAttribute("href", encodedUri);
        link.setAttribute("download", `Retention_Analysis_${this.state.interval}_${new Date().toISOString().slice(0,10)}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
}

registry.category("actions").add("hudson_subscriptions.retention_analysis", RetentionAnalysis);
