/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, proxy, onMounted, onWillUnmount, useProps } from "@odoo/owl";

// Helpers
function startOfDay(d) {
    const r = new Date(d);
    r.setHours(0, 0, 0, 0);
    return r;
}
function addDays(d, n) {
    const r = new Date(d);
    r.setDate(r.getDate() + n);
    return r;
}
function startOfWeek(d) {
    const r = startOfDay(d);
    const dow = r.getDay(); // 0=Sun
    const diff = dow === 0 ? -6 : 1 - dow;
    r.setDate(r.getDate() + diff);
    return r;
}
function isToday(d) {
    const t = new Date();
    return d.getFullYear() === t.getFullYear() && d.getMonth() === t.getMonth() && d.getDate() === t.getDate();
}
function isWeekend(d) {
    const dow = d.getDay();
    return dow === 0 || dow === 6;
}

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

export class FsBoard extends Component {
    static template = "hudson_field_service.FsBoard";
    props = useProps();

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        
        const myPlanningContext = this.props.action && this.props.action.context && this.props.action.context.default_my_planning;

        this.state = proxy({
            mode: "week",
            anchorDate: startOfDay(new Date()),
            customStartDate: new Date().toISOString().split('T')[0],
            customEndDate: new Date().toISOString().split('T')[0],
            loading: true,
            resources: [], // {id, name, checked}
            slots: [],     // slot records
            columns: [],   // grid columns
            dateLabel: "",
            monthLabel: "",
            searchQuery: "",
            filterMyPlanning: !!myPlanningContext,
        });

        // Bind event handlers used in inline arrow functions
        this.toggleMyPlanning = this.toggleMyPlanning.bind(this);
        this.onCellClick = this.onCellClick.bind(this);
        this.openSlot = this.openSlot.bind(this);
        this.setMode = this.setMode.bind(this);

        onMounted(async () => {
            await this._loadData();
        });
    }

    get autoPlanEnabled() {
        return Boolean(this.props?.autoPlanEnabled);
    }

    get filteredResources() {
        let res = this.state.resources.filter(r => r.checked);
        if (this.state.searchQuery) {
            const q = this.state.searchQuery.toLowerCase();
            res = res.filter(r => r.name.toLowerCase().includes(q));
        }
        return res;
    }

    getSlots(resourceId, col) {
        // Return slots for this resource on this specific date/month
        return this.state.slots.filter(s => {
            const sd = new Date(s.date_start.replace(' ', 'T') + 'Z');
            if (s.resource_id !== resourceId) return false;
            
            if (col.isMonth) {
                return sd.getFullYear() === col.date.getFullYear() &&
                       sd.getMonth() === col.date.getMonth();
            } else {
                return sd.getFullYear() === col.date.getFullYear() &&
                       sd.getMonth() === col.date.getMonth() &&
                       sd.getDate() === col.date.getDate();
            }
        });
    }

    formatTime(dateStr) {
        if (!dateStr) return "";
        const d = new Date(dateStr.replace(' ', 'T') + 'Z');
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    async _loadData() {
        this.state.loading = true;
        
        // Setup columns based on mode
        const cols = [];
        let dateFromStr, dateToStr;
        
        if (this.state.mode === "day") {
            const d = startOfDay(this.state.anchorDate);
            cols.push({
                key: 'd0',
                date: d,
                labelTop: DAY_NAMES[d.getDay()],
                labelBottom: String(d.getDate()),
                cssClass: isToday(d) ? 'is-today' : ''
            });
            this.state.columns = cols;
            this.state.dateLabel = `${MONTH_NAMES[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`;
            this.state.monthLabel = `${MONTH_NAMES[d.getMonth()]} ${d.getFullYear()}`;
            
            const pad = (n) => String(n).padStart(2, "0");
            const toUtcStr = (dateObj) => `${dateObj.getUTCFullYear()}-${pad(dateObj.getUTCMonth()+1)}-${pad(dateObj.getUTCDate())} 00:00:00`;
            dateFromStr = toUtcStr(d);
            dateToStr = toUtcStr(addDays(d, 1));
        } else if (this.state.mode === "month") {
            const y = this.state.anchorDate.getFullYear();
            const m = this.state.anchorDate.getMonth();
            const daysInMonth = new Date(y, m + 1, 0).getDate();
            const mStart = new Date(y, m, 1);
            for (let i = 0; i < daysInMonth; i++) {
                const d = addDays(mStart, i);
                cols.push({
                    key: `d${i}`,
                    date: d,
                    labelTop: DAY_NAMES[d.getDay()],
                    labelBottom: String(d.getDate()),
                    cssClass: `${isToday(d) ? 'is-today' : ''} ${isWeekend(d) ? 'is-weekend' : ''}`.trim()
                });
            }
            this.state.columns = cols;
            this.state.dateLabel = `${MONTH_NAMES[m]} ${y}`;
            this.state.monthLabel = this.state.dateLabel;
            
            const pad = (n) => String(n).padStart(2, "0");
            const toUtcStr = (dateObj) => `${dateObj.getUTCFullYear()}-${pad(dateObj.getUTCMonth()+1)}-${pad(dateObj.getUTCDate())} 00:00:00`;
            dateFromStr = toUtcStr(mStart);
            dateToStr = toUtcStr(addDays(new Date(y, m, daysInMonth), 1));
            
        } else if (this.state.mode === "quarter") {
            const y = this.state.anchorDate.getFullYear();
            const m = this.state.anchorDate.getMonth();
            const qMonth = Math.floor(m / 3) * 3;
            const qStart = new Date(y, qMonth, 1);
            const qEnd = new Date(y, qMonth + 3, 0);
            const daysInQuarter = Math.round((qEnd - qStart) / (1000*60*60*24)) + 1;
            for (let i = 0; i < daysInQuarter; i++) {
                const d = addDays(qStart, i);
                cols.push({
                    key: `d${i}`,
                    date: d,
                    labelTop: DAY_NAMES[d.getDay()],
                    labelBottom: String(d.getDate()),
                    cssClass: `${isToday(d) ? 'is-today' : ''} ${isWeekend(d) ? 'is-weekend' : ''}`.trim()
                });
            }
            this.state.columns = cols;
            this.state.dateLabel = `Q${Math.floor(m / 3) + 1} ${y}`;
            this.state.monthLabel = this.state.dateLabel;
            
            const pad = (n) => String(n).padStart(2, "0");
            const toUtcStr = (dateObj) => `${dateObj.getUTCFullYear()}-${pad(dateObj.getUTCMonth()+1)}-${pad(dateObj.getUTCDate())} 00:00:00`;
            dateFromStr = toUtcStr(qStart);
            dateToStr = toUtcStr(addDays(qEnd, 1));
            
        } else if (this.state.mode === "year") {
            const y = this.state.anchorDate.getFullYear();
            const yStart = new Date(y, 0, 1);
            const yEnd = new Date(y + 1, 0, 0); // last day of year
            const daysInYear = Math.round((yEnd - yStart) / (1000*60*60*24)) + 1;
            for (let i = 0; i < daysInYear; i++) {
                const d = addDays(yStart, i);
                cols.push({
                    key: `d${i}`,
                    date: d,
                    labelTop: DAY_NAMES[d.getDay()],
                    labelBottom: String(d.getDate()),
                    cssClass: `${isToday(d) ? 'is-today' : ''} ${isWeekend(d) ? 'is-weekend' : ''}`.trim()
                });
            }
            this.state.columns = cols;
            this.state.dateLabel = `${y}`;
            this.state.monthLabel = `${y}`;
            
            const pad = (n) => String(n).padStart(2, "0");
            const toUtcStr = (dateObj) => `${dateObj.getUTCFullYear()}-${pad(dateObj.getUTCMonth()+1)}-${pad(dateObj.getUTCDate())} 00:00:00`;
            dateFromStr = toUtcStr(new Date(y, 0, 1));
            dateToStr = toUtcStr(new Date(y + 1, 0, 1));
            
        } else if (this.state.mode === "custom") {
            const dStart = startOfDay(new Date(this.state.customStartDate));
            let dEnd = startOfDay(new Date(this.state.customEndDate));
            if (dEnd < dStart) dEnd = dStart;
            
            const days = Math.min(Math.round((dEnd - dStart) / (1000*60*60*24)) + 1, 90);
            for (let i = 0; i < days; i++) {
                const d = addDays(dStart, i);
                cols.push({
                    key: `d${i}`,
                    date: d,
                    labelTop: DAY_NAMES[d.getDay()],
                    labelBottom: String(d.getDate()),
                    cssClass: `${isToday(d) ? 'is-today' : ''} ${isWeekend(d) ? 'is-weekend' : ''}`.trim()
                });
            }
            this.state.columns = cols;
            this.state.dateLabel = `${dStart.toLocaleDateString()} - ${dEnd.toLocaleDateString()}`;
            this.state.monthLabel = this.state.dateLabel;
            
            const pad = (n) => String(n).padStart(2, "0");
            const toUtcStr = (dateObj) => `${dateObj.getUTCFullYear()}-${pad(dateObj.getUTCMonth()+1)}-${pad(dateObj.getUTCDate())} 00:00:00`;
            dateFromStr = toUtcStr(dStart);
            dateToStr = toUtcStr(addDays(addDays(dStart, days - 1), 1));
            
        } else {
            const weekStart = startOfWeek(this.state.anchorDate);
            for (let i = 0; i < 7; i++) {
                const d = addDays(weekStart, i);
                cols.push({
                    key: `d${i}`,
                    date: d,
                    labelTop: DAY_NAMES[d.getDay()],
                    labelBottom: String(d.getDate()),
                    cssClass: `${isToday(d) ? 'is-today' : ''} ${isWeekend(d) ? 'is-weekend' : ''}`.trim()
                });
            }
            this.state.columns = cols;
            const weekEnd = addDays(weekStart, 6);
            this.state.dateLabel = `${MONTH_NAMES[weekStart.getMonth()]} ${weekStart.getDate()} – ${MONTH_NAMES[weekEnd.getMonth()]} ${weekEnd.getDate()}, ${weekEnd.getFullYear()}`;
            this.state.monthLabel = `${MONTH_NAMES[weekStart.getMonth()]} ${weekStart.getFullYear()}`;
            
            const pad = (n) => String(n).padStart(2, "0");
            const toUtcStr = (dateObj) => `${dateObj.getUTCFullYear()}-${pad(dateObj.getUTCMonth()+1)}-${pad(dateObj.getUTCDate())} 00:00:00`;
            dateFromStr = toUtcStr(weekStart);
            dateToStr = toUtcStr(addDays(weekEnd, 1));
        }

        try {
            // Fetch employees and materials
            let empDomain = [["active", "=", true]];
            if (this.state.filterMyPlanning) {
                empDomain.push(["user_id", "=", this.env.uid]);
            }
            const employees = await this.orm.searchRead("hr.employee", empDomain, ["id", "name"]);
            const materials = await this.orm.searchRead("field.service.material", [], ["id", "name"]);
            
            const currentChecked = new Set(this.state.resources.filter(r => r.checked).map(r => r.id));
            this.state.resources = [
                ...employees.map(e => ({
                    id: "emp_" + e.id, dbId: e.id, name: e.name, type: 'employee', 
                    checked: this.state.resources.length === 0 || currentChecked.has("emp_" + e.id)
                })),
                ...materials.map(m => ({
                    id: "mat_" + m.id, dbId: m.id, name: m.name, type: 'material', 
                    checked: this.state.resources.length === 0 || currentChecked.has("mat_" + m.id)
                }))
            ];

            const orderDomain = [
                ["date_planned", ">=", dateFromStr],
                ["date_planned", "<", dateToStr]
            ];
            
            const [orders, shifts] = await Promise.all([
                this.orm.searchRead(
                    "field.service.order",
                    orderDomain,
                    ["id", "name", "employee_id", "extra_employee_ids", "material_ids", "date_planned", "date_deadline", "state", "partner_id", "duration_planned", "is_published"]
                ),
                // Planning shifts, shown as availability behind the jobs
                this.orm.call("field.service.order", "get_board_shifts", [dateFromStr, dateToStr]),
            ]);

            this.state.slots = [];
            for (const shift of shifts) {
                this.state.slots.push({
                    ...shift,
                    key: "shift_" + shift.id,
                    is_shift: true,
                    resource_id: "emp_" + shift.resource_id[0],
                    role_name: shift.role_id ? shift.role_id[1] : "Shift",
                    partner_name: shift.partner_id ? shift.partner_id[1] : "",
                });
            }
            for (const order of orders) {
                const baseSlot = {
                    ...order,
                    key: "order_" + order.id,
                    date_start: order.date_planned,
                    date_end: order.date_deadline,
                    allocated_hours: order.duration_planned,
                    role_name: order.state,
                    partner_name: order.partner_id ? order.partner_id[1] : "",
                    color: order.state === 'in_progress' ? 3 : (order.state === 'done' ? 10 : 2),
                };
                if (order.employee_id) {
                    this.state.slots.push({ ...baseSlot, resource_id: "emp_" + order.employee_id[0] });
                }
                if (order.extra_employee_ids) {
                    for (const exId of order.extra_employee_ids) {
                        this.state.slots.push({ ...baseSlot, resource_id: "emp_" + exId });
                    }
                }
                if (order.material_ids) {
                    for (const matId of order.material_ids) {
                        this.state.slots.push({ ...baseSlot, resource_id: "mat_" + matId });
                    }
                }
            }

            // Calculate total allocated hours per resource. A job planned
            // inside one of the technician's shifts is not counted twice.
            const hoursByResource = {};
            const shiftSlots = this.state.slots.filter(s => s.is_shift);
            for (const slot of this.state.slots) {
                if (!slot.resource_id) {
                    continue;
                }
                if (!slot.is_shift && shiftSlots.some(sh =>
                    sh.resource_id === slot.resource_id && sh.date_start <= slot.date_start && sh.date_end >= slot.date_end
                )) {
                    continue;
                }
                hoursByResource[slot.resource_id] = (hoursByResource[slot.resource_id] || 0) + (slot.allocated_hours || 0);
            }
            
            // Assign to resources
            for (const res of this.state.resources) {
                res.allocatedHours = hoursByResource[res.id] || 0;
            }

        } catch (e) {
            console.error(e);
            this.notification.add("Failed to load planning data", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async toggleMyPlanning(val) {
        this.state.filterMyPlanning = val;
        this.state.resources = []; // Reset resources to reload based on filter
        await this._loadData();
    }

    async setMode(mode) {
        this.state.mode = mode;
        await this._loadData();
    }

    async onPrevPeriod() {
        if (this.state.mode === "day") {
            this.state.anchorDate = addDays(this.state.anchorDate, -1);
        } else if (this.state.mode === "week") {
            this.state.anchorDate = addDays(this.state.anchorDate, -7);
        } else if (this.state.mode === "month") {
            this.state.anchorDate = new Date(this.state.anchorDate.getFullYear(), this.state.anchorDate.getMonth() - 1, 1);
        } else if (this.state.mode === "quarter") {
            this.state.anchorDate = new Date(this.state.anchorDate.getFullYear(), this.state.anchorDate.getMonth() - 3, 1);
        } else if (this.state.mode === "year") {
            this.state.anchorDate = new Date(this.state.anchorDate.getFullYear() - 1, 0, 1);
        } else if (this.state.mode === "custom") {
            return; // No prev period for custom range
        }
        await this._loadData();
    }

    async onNextPeriod() {
        if (this.state.mode === "day") {
            this.state.anchorDate = addDays(this.state.anchorDate, 1);
        } else if (this.state.mode === "week") {
            this.state.anchorDate = addDays(this.state.anchorDate, 7);
        } else if (this.state.mode === "month") {
            this.state.anchorDate = new Date(this.state.anchorDate.getFullYear(), this.state.anchorDate.getMonth() + 1, 1);
        } else if (this.state.mode === "quarter") {
            this.state.anchorDate = new Date(this.state.anchorDate.getFullYear(), this.state.anchorDate.getMonth() + 3, 1);
        } else if (this.state.mode === "year") {
            this.state.anchorDate = new Date(this.state.anchorDate.getFullYear() + 1, 0, 1);
        } else if (this.state.mode === "custom") {
            return; // No next period for custom range
        }
        await this._loadData();
    }

    async onApplyCustomDate() {
        this.state.mode = "custom";
        await this._loadData();
        
        // Try to close dropdown by clicking body
        document.body.click();
    }

    async onToday() {
        this.state.anchorDate = startOfDay(new Date());
        await this._loadData();
    }

    async onSearch(ev) {
        if (ev.key === "Enter") {
            // Already handled by getter filteredResources via v-model bound
        }
    }

    async onCellClick(resourceId, col) {
        // resourceId is like "emp_5" or "mat_2"
        const [resType, resIdStr] = resourceId.split('_');
        const resId = parseInt(resIdStr);
        
        let context = {
            default_date_planned: this._localToUtcStr(col.date, 8), // default 8am
            default_date_deadline: this._localToUtcStr(col.date, 12),  // default 12pm
        };
        
        if (resType === 'emp') {
            context.default_employee_id = resId;
        } else if (resType === 'mat') {
            context.default_material_ids = [resId];
        }

        const action = {
            type: "ir.actions.act_window",
            res_model: "field.service.order",
            views: [[false, "form"]],
            target: "new",
            context: context,
        };
        this.action.doAction(action, {
            onClose: () => this._loadData(),
        });
    }
    
    _localToUtcStr(date, hour) {
        const d = new Date(date);
        d.setHours(hour, 0, 0, 0);
        const pad = (n) => String(n).padStart(2, "0");
        return `${d.getUTCFullYear()}-${pad(d.getUTCMonth()+1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
    }

    async openSlot(slot) {
        if (slot.is_shift) {
            return; // Shifts are managed in the Planning app
        }
        const slotId = slot.id;
        const action = {
            type: "ir.actions.act_window",
            res_model: "field.service.order",
            res_id: slotId,
            views: [[false, "form"]],
            target: "current",
        };
        this.action.doAction(action, {
            onClose: () => this._loadData(),
        });
    }

    async onPublish() {
        // Publish all new/scheduled slots in current view
        const draftIds = [...new Set(this.state.slots.filter(s => !s.is_shift && !s.is_published).map(s => s.id))];
        if (draftIds.length > 0) {
            await this.orm.call("field.service.order", "action_publish_order", [draftIds]);
            this.notification.add(`Orders published`, { type: "success" });
            await this._loadData();
        } else {
            this.notification.add("No unpublished orders to publish in the current view", { type: "warning" });
        }
    }
    
    async onCopyPrevious() {
        this.notification.add("Copy previous week feature is under construction", { type: "info" });
    }
    
    async onAutoPlan() {
        const action = {
            type: "ir.actions.act_window",
            res_model: "fs.auto.plan.wizard",
            views: [[false, "form"]],
            target: "new",
        };
        this.action.doAction(action, {
            onClose: () => this._loadData(),
        });
    }
    
    async onPrint() {
        window.print();
    }
}

registry.category("actions").add("hudson_field_service.fs_board", FsBoard);
