/** @odoo-module **/

/**
 * Field Service Planning Board — OWL Client Action
 *
 * Renders a Gantt-style scheduling grid:
 *   - Left column  : all technicians (employees) as rows
 *   - Top axis     : hourly time slots (Day mode) or daily slots (Week mode)
 *   - Cards        : field service orders positioned by date_planned + duration_planned
 *
 * Access:
 *   - Managers (group_field_service_manager) → see ALL employees + ALL orders
 *   - Normal users  → redirected to standard calendar filtered to their own orders
 *     (handled server-side: the menu item for this board is manager-only)
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { Component, useState, onMounted, onWillUnmount, useRef, proxy } from "@odoo/owl";

const useStateHook = proxy || useState || ((obj) => obj);

// ─── Palette for avatar initials background ──────────────────────────────────
const AVATAR_COLORS = [
    "#714b67", "#0d6efd", "#198754", "#dc3545", "#fd7e14",
    "#6610f2", "#0dcaf0", "#d63384", "#20c997", "#ffc107",
];

function pickColor(id) {
    return AVATAR_COLORS[id % AVATAR_COLORS.length];
}

function initials(name) {
    if (!name) return "?";
    const parts = name.trim().split(/\s+/);
    if (parts.length === 1) return parts[0][0].toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// ─── Date helpers ────────────────────────────────────────────────────────────

/** Return a Date at midnight in LOCAL time for the given Date */
function startOfDay(d) {
    const r = new Date(d);
    r.setHours(0, 0, 0, 0);
    return r;
}

/** Add N whole days */
function addDays(d, n) {
    const r = new Date(d);
    r.setDate(r.getDate() + n);
    return r;
}

/** Monday of the week containing d */
function startOfWeek(d) {
    const r = startOfDay(d);
    const dow = r.getDay(); // 0=Sun
    const diff = dow === 0 ? -6 : 1 - dow;
    r.setDate(r.getDate() + diff);
    return r;
}

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

/** Format: "Mon, Jul 14" */
function fmtDate(d) {
    return `${DAY_NAMES[d.getDay()]}, ${MONTH_NAMES[d.getMonth()]} ${d.getDate()}`;
}

/** Format: "Jul 14 – Jul 20, 2025" */
function fmtWeekRange(start, end) {
    const s = `${MONTH_NAMES[start.getMonth()]} ${start.getDate()}`;
    const e = `${MONTH_NAMES[end.getMonth()]} ${end.getDate()}, ${end.getFullYear()}`;
    return `${s} – ${e}`;
}

function isToday(d) {
    const t = new Date();
    return d.getFullYear() === t.getFullYear()
        && d.getMonth() === t.getMonth()
        && d.getDate() === t.getDate();
}

function isWeekend(d) {
    const dow = d.getDay();
    return dow === 0 || dow === 6;
}

// ─── Day mode: hours 7 → 20 ──────────────────────────────────────────────────
const DAY_HOUR_START = 7;
const DAY_HOUR_END = 20; // exclusive

// ─── Main component ──────────────────────────────────────────────────────────

export class FsPlanningBoard extends Component {
    static template = "hudson_planning.FsPlanningBoard";
    static props = {
        action: { type: Object, optional: true },
        actionId: { type: [Number, String], optional: true },
        updateActionState: { type: Function, optional: true },
        className: { type: String, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");

        this.gridWrapper = useRef("gridWrapper");

        this.state = useStateHook({
            mode: "week",          // "day" | "week"
            anchorDate: startOfDay(new Date()),
            loading: true,
            employees: [],         // [{id, employeeId, name, avatar, initials, color}]
            orders: [],            // [{id, name, title, employeeId, datePlanned, durationHours, state, partner}]
            slots: [],             // [{key, label, date, hour, cssClass}]
            dateLabel: "",
            dragState: null,       // { empId: null, startSlot: null, currentSlot: null }
        });

        this._refreshTimer = null;
        
        // Bind event handlers
        this.onDragStart = this.onDragStart.bind(this);
        this.onDragEnter = this.onDragEnter.bind(this);
        this.onDragEnd = this.onDragEnd.bind(this);
        this.onClickSlot = this.onClickSlot.bind(this);
        this.openOrder = this.openOrder.bind(this);

        onMounted(async () => {
            await this._loadData();
            this._startRefreshTimer();
        });

        onWillUnmount(() => {
            if (this._refreshTimer) clearInterval(this._refreshTimer);
        });
    }

    // ── Timer: refresh every 5 min ───────────────────────────────────────────
    _startRefreshTimer() {
        this._refreshTimer = setInterval(() => this._loadData(), 5 * 60 * 1000);
    }

    // ── Slot computation ─────────────────────────────────────────────────────

    _computeSlots() {
        const slots = [];
        if (this.state.mode === "day") {
            const d = this.state.anchorDate;
            for (let h = DAY_HOUR_START; h < DAY_HOUR_END; h++) {
                const cls = [];
                if (isToday(d)) cls.push("is-today");
                if (isWeekend(d)) cls.push("is-weekend");
                slots.push({
                    key: `h${h}`,
                    label: `${h}:00`,
                    date: d,
                    hour: h,
                    cssClass: cls.join(" "),
                });
            }
            this.state.dateLabel = fmtDate(d) + ", " + d.getFullYear();
        } else {
            // week: Mon–Sun
            const weekStart = startOfWeek(this.state.anchorDate);
            for (let i = 0; i < 7; i++) {
                const d = addDays(weekStart, i);
                const cls = [];
                if (isToday(d)) cls.push("is-today");
                if (isWeekend(d)) cls.push("is-weekend");
                slots.push({
                    key: `d${i}`,
                    label: `${DAY_NAMES[d.getDay()]} ${d.getDate()}`,
                    date: d,
                    hour: null,
                    cssClass: cls.join(" "),
                });
            }
            const weekEnd = addDays(weekStart, 6);
            this.state.dateLabel = fmtWeekRange(weekStart, weekEnd);
        }
        this.state.slots = slots;
    }

    // ── Grid CSS template columns ────────────────────────────────────────────

    get gridTemplateColumns() {
        const n = this.state.slots.length;
        // Use minmax with 1fr so the columns expand to fill any remaining blank space on the right
        return `var(--fs-board-employee-col-w) repeat(${n}, minmax(var(--fs-board-hour-col-w), 1fr))`;
    }

    // ── Data loading ─────────────────────────────────────────────────────────

    async _loadData() {
        this.state.loading = true;
        this._computeSlots();

        try {
            // Determine date range for slot fetch
            let dateFrom, dateTo;
            if (this.state.mode === "day") {
                dateFrom = new Date(this.state.anchorDate);
                dateTo = addDays(dateFrom, 1);
            } else {
                dateFrom = startOfWeek(this.state.anchorDate);
                dateTo = addDays(dateFrom, 7);
            }

            const [empRaw, slotsRaw] = await Promise.all([
                this._fetchEmployees(),
                this._fetchSlots(dateFrom, dateTo),
            ]);

            // Sum allocated hours per employee
            empRaw.forEach(emp => {
                const empSlots = slotsRaw.filter(s => s.employeeId === emp.id);
                emp.allocatedHours = empSlots.reduce((sum, s) => sum + (s.durationHours || 0), 0);
            });

            this.state.employees = empRaw;
            this.state.orders = slotsRaw; // we keep the state.orders name for now to minimize refactoring
        } catch (e) {
            console.error("Planning board load error:", e);
            this.notification.add(
                "Failed to load planning board data: " + (e.message || e),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async _fetchEmployees() {
        // Fetch active employees that have a linked user account
        const records = await this.orm.searchRead(
            "hr.employee",
            [["active", "=", true]],
            ["id", "name", "image_128", "resource_calendar_id"],
            { limit: 100, order: "name asc" }
        );

        // Fetch calendar working hours if any
        let calendars = {};
        const calendarIds = [...new Set(records.map(r => r.resource_calendar_id && r.resource_calendar_id[0]).filter(Boolean))];
        if (calendarIds.length > 0) {
            const calRecords = await this.orm.searchRead(
                "resource.calendar",
                [["id", "in", calendarIds]],
                ["id", "hours_per_week"]
            );
            calRecords.forEach(c => calendars[c.id] = c.hours_per_week);
        }

        const employees = records.map((r) => {
            const calId = r.resource_calendar_id ? r.resource_calendar_id[0] : null;
            const hoursPerWeek = calId ? calendars[calId] : 40.0;
            return {
                id: r.id,
                employeeId: r.id,
                name: r.name,
                avatar: r.image_128
                    ? `/web/image/hr.employee/${r.id}/image_128`
                    : null,
                initials: initials(r.name),
                color: pickColor(r.id),
                hoursPerWeek: hoursPerWeek,
                allocatedHours: 0.0, // Will be computed when fetching slots
            };
        });

        // Always add an "Unassigned" row at the end
        employees.push({
            id: 0,
            employeeId: null,
            name: "Unassigned",
            avatar: null,
            initials: "?",
            color: "#adb5bd",
        });

        return employees;
    }

    async _fetchSlots(dateFrom, dateTo) {
        // Fetch planning slots in the date range
        const domain = [
            "|",
            ["date_start", "=", false],
            "&",
            ["date_start", ">=", this._toOdooDatetime(dateFrom)],
            ["date_start", "<", this._toOdooDatetime(dateTo)],
        ];

        const records = await this.orm.searchRead(
            "fs.planning.slot",
            domain,
            ["id", "name", "resource_id", "date_start", "date_end", "allocated_hours", "state", "project_id", "partner_id", "role_id", "field_service_order_id"],
            { limit: 1000, order: "date_start asc" }
        );

        return records.map((r) => {
            const parseDate = (dStr) => dStr ? new Date(dStr.replace(' ', 'T') + 'Z') : null;
            const start = parseDate(r.date_start);
            const end = parseDate(r.date_end);
            
            const formatTime = (d) => {
                if (!d) return "";
                return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            };
            const timeString = (start && end) ? `${formatTime(start)} - ${formatTime(end)}` : "";

            let titleParts = [];
            if (r.role_id) titleParts.push(r.role_id[1]);
            if (r.project_id) titleParts.push(r.project_id[1]);
            if (r.field_service_order_id) titleParts.push(r.field_service_order_id[1]);
            let title = titleParts.join(' - ');
            if (!title) title = "Shift";
            
            return {
                id: r.id,
                name: r.name || "",
                title: title,
                timeString: timeString,
                employeeId: r.resource_id ? r.resource_id[0] : null,
                datePlanned: start,
                dateEnd: end,
                durationHours: r.allocated_hours || 0,
                state: r.state,
                partner: r.partner_id ? r.partner_id[1] : "",
                isPublished: r.state === 'published',
            };
        });
    }

    _toOdooDatetime(d) {
        // Odoo expects UTC datetimes as strings "YYYY-MM-DD HH:MM:SS"
        const pad = (n) => String(n).padStart(2, "0");
        return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
    }

    // ── Slot ↔ order matching ────────────────────────────────────────────────

    getOrdersForSlot(employeeId, slot) {
        return this.state.orders.filter((order) => {
            // Employee matching
            if (order.employeeId !== employeeId) return false;

            if (!order.datePlanned) {
                // Unscheduled orders: show in first slot of unassigned or first slot of employee
                return slot === this.state.slots[0];
            }

            if (this.state.mode === "day") {
                // Match by hour
                const orderHour = order.datePlanned.getHours();
                return orderHour === slot.hour;
            } else {
                // Match by day
                const orderDay = startOfDay(order.datePlanned);
                const slotDay = startOfDay(slot.date);
                return orderDay.getTime() === slotDay.getTime();
            }
        });
    }

    getCardStyle(order, slot) {
        if (!order.datePlanned) {
            return "left: 4px; right: 4px;";
        }
        
        if (this.state.mode === "day") {
            const startMin = order.datePlanned.getMinutes();
            const leftPercent = (startMin / 60) * 100;
            const widthPercent = (order.durationHours / 1) * 100;
            return `left: calc(${leftPercent}% + 2px); width: calc(${widthPercent}% - 4px);`;
        } else {
            // Week mode: 1 column = 24 hours
            const startHour = order.datePlanned.getHours() + (order.datePlanned.getMinutes() / 60);
            const leftPercent = (startHour / 24) * 100;
            const widthPercent = Math.max((order.durationHours / 24) * 100, 2); // At least 2% width
            return `left: calc(${leftPercent}% + 2px); width: calc(${widthPercent}% - 4px);`;
        }
    }

    // ── Navigation ───────────────────────────────────────────────────────────

    async prevPeriod() {
        if (this.state.mode === "day") {
            this.state.anchorDate = addDays(this.state.anchorDate, -1);
        } else {
            this.state.anchorDate = addDays(this.state.anchorDate, -7);
        }
        await this._loadData();
    }

    async nextPeriod() {
        if (this.state.mode === "day") {
            this.state.anchorDate = addDays(this.state.anchorDate, 1);
        } else {
            this.state.anchorDate = addDays(this.state.anchorDate, 7);
        }
        await this._loadData();
    }

    async goToday() {
        this.state.anchorDate = startOfDay(new Date());
        await this._loadData();
    }

    async setMode(mode) {
        this.state.mode = mode;
        await this._loadData();
    }

    // ── Interactions ─────────────────────────────────────────────────────────

    openOrder(ev, orderId) {
        ev.stopPropagation();
        // Dialog that can be expanded to the full form view
        this.dialog.add(FormViewDialog, {
            resModel: "fs.planning.slot",
            resId: orderId,
            title: "Edit Shift",
            onRecordSaved: () => this._loadData(),
        }, {
            onClose: () => this._loadData(),
        });
    }

    openNewOrder() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "fs.planning.slot",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_date_start: this._toOdooDatetime(this.state.anchorDate),
                default_date_end: this._toOdooDatetime(addDays(this.state.anchorDate, 1)),
            },
        }, {
            onClose: () => {
                this._loadData();
            }
        });
    }

    get hasUnpublishedDrafts() {
        return this.state.orders.some(o => !o.isPublished);
    }

    async publishDrafts() {
        const draftIds = this.state.orders.filter(o => !o.isPublished).map(o => o.id);
        if (draftIds.length === 0) return;

        try {
            await this.orm.call("fs.planning.slot", "action_publish", [draftIds]);
            this.notification.add("Drafts published successfully!", { type: "success" });
            await this._loadData();
        } catch (e) {
            this.notification.add("Failed to publish drafts: " + e.message, { type: "danger" });
        }
    }

    // ── Drag Selection ───────────────────────────────────────────────────────

    onDragStart(ev, emp, slot) {
        if (ev.button !== 0) return; // Only left click
        this.state.dragState = {
            empId: emp.id,
            startSlot: slot,
            currentSlot: slot
        };
    }

    onDragEnter(ev, emp, slot) {
        if (this.state.dragState && this.state.dragState.empId === emp.id) {
            this.state.dragState.currentSlot = slot;
        }
    }

    onDragEnd(ev, emp, slot) {
        if (!this.state.dragState) return;
        
        const state = this.state.dragState;
        this.state.dragState = null;

        // Ensure we dropped on the same employee
        if (state.empId !== emp.id) return;

        // Calculate slot indices
        const startIndex = this.state.slots.indexOf(state.startSlot);
        const endIndex = this.state.slots.indexOf(slot);
        
        if (startIndex === -1 || endIndex === -1) return;

        const minIdx = Math.min(startIndex, endIndex);
        const maxIdx = Math.max(startIndex, endIndex);
        const slotCount = maxIdx - minIdx + 1;

        const firstSlot = this.state.slots[minIdx];
        const defaultDatetime = this._slotToDatetime(firstSlot);

        const context = {};
        if (emp.employeeId) {
            context.default_resource_id = emp.employeeId;
        }
        if (defaultDatetime) {
            context.default_date_start = this._toOdooDatetime(defaultDatetime);
            // Default to 1 hour duration or slot count
            const duration = this.state.mode === "day" ? slotCount : slotCount * 8;
            context.default_date_end = this._toOdooDatetime(new Date(defaultDatetime.getTime() + duration * 60 * 60 * 1000));
            context.default_allocated_hours = duration;
        }

        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "fs.planning.slot",
            views: [[false, "form"]],
            target: "new",
            context: context,
        }, {
            onClose: () => {
                this._loadData();
            }
        });
    }

    isSlotSelected(emp, slot) {
        const ds = this.state.dragState;
        if (!ds || ds.empId !== emp.id) return false;

        const sIdx = this.state.slots.indexOf(ds.startSlot);
        const cIdx = this.state.slots.indexOf(ds.currentSlot);
        const myIdx = this.state.slots.indexOf(slot);

        if (sIdx === -1 || cIdx === -1 || myIdx === -1) return false;

        const minIdx = Math.min(sIdx, cIdx);
        const maxIdx = Math.max(sIdx, cIdx);

        return myIdx >= minIdx && myIdx <= maxIdx;
    }

    onClickSlot(ev, emp, slot) {
        // Handled by onDragEnd now to support multi-select.
        // We keep this empty just in case any leftover references exist, 
        // though the XML was updated to use mouse events instead.
    }

    openNewOrder() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "field.service.order",
            views: [[false, "form"]],
            target: "new",
        });
    }

    _slotToDatetime(slot) {
        if (this.state.mode === "day") {
            const d = new Date(slot.date);
            d.setHours(slot.hour, 0, 0, 0);
            return d;
        } else {
            return new Date(slot.date);
        }
    }
}

registry.category("actions").add("field_service_planning_board", FsPlanningBoard);
