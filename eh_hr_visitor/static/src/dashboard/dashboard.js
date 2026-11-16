/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, proxy, onWillStart, onMounted, onWillUnmount, signal } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { getColor } from "@web/core/colors/colors";

export class VisitorDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        
        this.purposeChartCanvas = signal.ref();
        this.peakHoursChartCanvas = signal.ref();
        
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        // Format to naive UTC string which ORM expects for datetime, but we'll let the backend handle the UTC conversion cleanly. 
        // We will just pass the action or let the server compute "today" from timezone.
        // Actually, backend already computes today based on user's timezone if we don't pass domain for stats.
        // The domains used in onClick use `this.state.todayStart` string.
        
        // format date to Odoo string YYYY-MM-DD HH:MM:SS in UTC for the domain.
        // However, for simplicity we can just pass a string of today's date and use >= for date field matching.
        const todayStr = today.toISOString().split('T')[0] + ' 00:00:00';
        const todayEndStr = today.toISOString().split('T')[0] + ' 23:59:59';
        
        this.state = proxy({
            data: {},
            todayStart: todayStr,
            todayEnd: todayEndStr,
        });

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.fetchData();
        });

        onMounted(() => {
            this.renderCharts();
            this.interval = setInterval(() => {
                this.fetchData().then(() => this.updateCharts());
            }, 60000); // refresh every 60 seconds
        });
        
        onWillUnmount(() => {
            clearInterval(this.interval);
            if (this.purposeChart) {
                this.purposeChart.destroy();
            }
            if (this.peakHoursChart) {
                this.peakHoursChart.destroy();
            }
        });
    }

    async fetchData() {
        this.state.data = await this.orm.call(
            "eh.hr.visitor",
            "get_dashboard_data",
            []
        );
    }

    renderCharts() {
        if (!this.purposeChartCanvas() || !this.peakHoursChartCanvas()) {
            return;
        }

        const purposeData = this.state.data.visitors_by_purpose || {labels: [], data: []};
        const peakData = this.state.data.peak_hours || {labels: [], data: []};

        // Donut Chart
        this.purposeChart = new Chart(this.purposeChartCanvas(), {
            type: 'doughnut',
            data: {
                labels: purposeData.labels,
                datasets: [{
                    data: purposeData.data,
                    backgroundColor: [
                        getColor(0), getColor(1), getColor(2), 
                        getColor(3), getColor(4), getColor(5)
                    ],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                legend: {
                    position: 'right',
                },
                cutoutPercentage: 70,
            }
        });

        // Bar Chart
        this.peakHoursChart = new Chart(this.peakHoursChartCanvas(), {
            type: 'bar',
            data: {
                labels: peakData.labels,
                datasets: [{
                    label: 'Visitors',
                    data: peakData.data,
                    backgroundColor: getColor(0),
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                legend: {
                    display: false,
                },
                scales: {
                    yAxes: [{
                        ticks: {
                            beginAtZero: true,
                            precision: 0
                        }
                    }]
                }
            }
        });
    }

    updateCharts() {
        if (this.purposeChart) {
            const purposeData = this.state.data.visitors_by_purpose || {labels: [], data: []};
            this.purposeChart.data.labels = purposeData.labels;
            this.purposeChart.data.datasets[0].data = purposeData.data;
            this.purposeChart.update();
        }
        
        if (this.peakHoursChart) {
            const peakData = this.state.data.peak_hours || {labels: [], data: []};
            this.peakHoursChart.data.labels = peakData.labels;
            this.peakHoursChart.data.datasets[0].data = peakData.data;
            this.peakHoursChart.update();
        }
    }

    openVisitorList(domain) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Visitors",
            res_model: "eh.hr.visitor",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
        });
    }

    openVisitorRecord(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Visitor",
            res_model: "eh.hr.visitor",
            view_mode: "form",
            views: [[false, "form"]],
            res_id: id,
        });
    }
}

VisitorDashboard.template = "eh_hr_visitor.Dashboard";

registry.category("actions").add("eh_hr_visitor.dashboard", VisitorDashboard);
