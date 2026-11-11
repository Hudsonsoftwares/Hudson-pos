import { Component, proxy, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog, ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { useService } from "@web/core/utils/hooks";

export class BookingScreen extends Component {
    static template = "hudson_pos_booking.BookingScreen";
    static components = {};

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
        const initialDate = luxon.DateTime.now().startOf("day");

        this.state = proxy({
            isOnline: navigator.onLine,
            currentDate: initialDate,
            viewMode: "gantt", // Default to 'gantt' timeline view matching latest screenshot
            calendarPeriod: "day", // 'day', 'week', 'month', 'quarter', 'year', 'custom'
            showPeriodDropdown: false,
            customStartDate: initialDate.toFormat("yyyy-MM-dd"),
            customEndDate: initialDate.toFormat("yyyy-MM-dd"),
            showFilterDropdown: false,
            filterStatus: "all", // 'all', 'confirmed', 'checked_in', 'prepaid', 'checked_out'
            searchQuery: "",
            showAllDates: false,
            showBookingModal: false,
            showClosingDayModal: false,
            closingDate: initialDate.toFormat("yyyy-MM-dd"),
            closingReason: "",
            editingBookingId: null,
            draggedBookingId: null,
            currentTimeHourFraction: this._getCurrentHourFraction(),
            newBooking: {
                customer_name: "",
                customer_phone: "",
                customer_email: "",
                party_size: 2,
                table_id: "",
                date_str: initialDate.toFormat("yyyy-MM-dd"),
                start_time: "16:00",
                duration_hours: 2.0,
                notes: "",
                state: "confirmed",
            },
        });

        this.hours = [
            { hour: 0, label: "12am" },
            { hour: 1, label: "1am" },
            { hour: 2, label: "2am" },
            { hour: 3, label: "3am" },
            { hour: 4, label: "4am" },
            { hour: 5, label: "5am" },
            { hour: 6, label: "6am" },
            { hour: 7, label: "7am" },
            { hour: 8, label: "8am" },
            { hour: 9, label: "9am" },
            { hour: 10, label: "10am" },
            { hour: 11, label: "11am" },
            { hour: 12, label: "12pm" },
            { hour: 13, label: "1pm" },
            { hour: 14, label: "2pm" },
            { hour: 15, label: "3pm" },
            { hour: 16, label: "4pm" },
            { hour: 17, label: "5pm" },
            { hour: 18, label: "6pm" },
            { hour: 19, label: "7pm" },
            { hour: 20, label: "8pm" },
            { hour: 21, label: "9pm" },
            { hour: 22, label: "10pm" },
            { hour: 23, label: "11pm" },
        ];

        this.slotWidth = 80; // px per hour

        onMounted(() => {
            this._onlineHandler = () => { this.state.isOnline = true; };
            this._offlineHandler = () => { this.state.isOnline = false; };
            window.addEventListener("online", this._onlineHandler);
            window.addEventListener("offline", this._offlineHandler);

            this._timer = setInterval(() => {
                this.state.currentTimeHourFraction = this._getCurrentHourFraction();
            }, 60000);

            this._clickOutsideHandler = (ev) => {
                if (!ev.target.closest(".pos-booking-period-dropdown-container")) {
                    this.state.showPeriodDropdown = false;
                }
                if (!ev.target.closest(".pos-booking-filter-dropdown-container")) {
                    this.state.showFilterDropdown = false;
                }
            };
            window.addEventListener("click", this._clickOutsideHandler);
        });

        onWillUnmount(() => {
            window.removeEventListener("online", this._onlineHandler);
            window.removeEventListener("offline", this._offlineHandler);
            if (this._clickOutsideHandler) {
                window.removeEventListener("click", this._clickOutsideHandler);
            }
            if (this._timer) clearInterval(this._timer);
        });
    }

    _getCurrentHourFraction() {
        const now = luxon.DateTime.now();
        return now.hour + now.minute / 60.0;
    }

    get isOnline() {
        return this.state.isOnline;
    }

    get isViewingToday() {
        return this.state.currentDate.hasSame(luxon.DateTime.now(), "day");
    }

    get nowMarkerLeft() {
        if (!this.isViewingToday) return null;
        return `${this.state.currentTimeHourFraction * this.slotWidth}px`;
    }

    get calendarPeriodLabel() {
        const p = this.state.calendarPeriod;
        if (p === "day") return _t("Day");
        if (p === "week") return _t("Week");
        if (p === "month") return _t("Month");
        if (p === "quarter") return _t("Quarter");
        if (p === "year") return _t("Year");
        if (p === "custom") return _t("Custom Range");
        return _t("Day");
    }

    get filterStatusLabel() {
        const s = this.state.filterStatus;
        if (s === "confirmed" || s === "booked") return _t("Booked");
        if (s === "checked_in") return _t("Checked In");
        if (s === "prepaid") return _t("Prepaid Food");
        if (s === "checked_out") return _t("Released");
        if (s === "no_show") return _t("No Show");
        return _t("All");
    }

    get periodTitle() {
        const cur = this.state.currentDate;
        const p = this.state.calendarPeriod;
        if (p === "day") {
            return cur.toFormat("EEEE, MMMM d, yyyy");
        } else if (p === "week") {
            const start = cur.startOf("week");
            const end = cur.endOf("week");
            return `${start.toFormat("MMM d")} - ${end.toFormat("MMM d, yyyy")}`;
        } else if (p === "month") {
            return cur.toFormat("MMMM yyyy");
        } else if (p === "quarter") {
            const q = Math.ceil(cur.month / 3);
            return `Q${q} ${cur.year}`;
        } else if (p === "year") {
            return cur.toFormat("yyyy");
        } else if (p === "custom") {
            return `${this.state.customStartDate} → ${this.state.customEndDate}`;
        }
        return cur.toFormat("EEEE, MMMM d, yyyy");
    }

    togglePeriodDropdown() {
        this.state.showPeriodDropdown = !this.state.showPeriodDropdown;
        if (this.state.showPeriodDropdown) {
            this.state.showFilterDropdown = false;
        }
    }

    selectPeriod(period) {
        this.state.calendarPeriod = period;
        this.state.showPeriodDropdown = false;
    }

    applyCustomDateRange() {
        if (!this.state.customStartDate || !this.state.customEndDate) return;
        this.state.calendarPeriod = "custom";
        this.state.showPeriodDropdown = false;
    }

    toggleFilterDropdown() {
        this.state.showFilterDropdown = !this.state.showFilterDropdown;
        if (this.state.showFilterDropdown) {
            this.state.showPeriodDropdown = false;
        }
    }

    setFilterStatus(status) {
        this.state.filterStatus = status;
        this.state.showFilterDropdown = false;
    }

    get currentFormattedDate() {
        return this.state.currentDate.toFormat("EEEE, MMMM d, yyyy");
    }

    get activeTables() {
        const tableModel = this.pos.models["restaurant.table"];
        if (!tableModel) return [];
        const list = typeof tableModel.getAll === "function" ? tableModel.getAll() : (Array.isArray(tableModel) ? tableModel : []);
        const tables = list.filter(t => t && t.active);
        return tables.sort((a, b) => {
            const numA = parseInt(a.table_number) || 0;
            const numB = parseInt(b.table_number) || 0;
            return numA - numB;
        });
    }

    get totalRestaurantSeats() {
        return this.activeTables.reduce((sum, t) => sum + (t.seats || 0), 0) || 88;
    }

    get totalAvailableSeats() {
        const curDateStr = this.state.currentDate.toFormat("yyyy-MM-dd");
        const occupied = this.allBookings
            .filter(b => b && b.startDateStr === curDateStr && ["confirmed", "checked_in"].includes(b.state))
            .reduce((sum, b) => sum + (b.party_size || 0), 0);
        return Math.max(0, this.totalRestaurantSeats - occupied);
    }

    get allBookings() {
        const bookingModel = this.pos.models["appointment.booking"];
        if (!bookingModel) return [];
        const list = typeof bookingModel.getAll === "function" ? bookingModel.getAll() : (Array.isArray(bookingModel) ? bookingModel : []);
        return list.filter(b => b && b.state !== "cancelled");
    }

    get displayedBookings() {
        const query = (this.state.searchQuery || "").trim().toLowerCase();
        const filterStatus = this.state.filterStatus;
        let list = this.state.showAllDates ? this.allBookings : this.dateBookings;

        if (this.state.showAllDates) {
            if (filterStatus !== "all") {
                if (filterStatus === "confirmed" || filterStatus === "booked") list = list.filter(b => b.state === "confirmed" || b.state === "booked");
                else if (filterStatus === "checked_in") list = list.filter(b => b.state === "checked_in");
                else if (filterStatus === "checked_out" || filterStatus === "released") list = list.filter(b => b.state === "checked_out" || b.state === "completed");
                else if (filterStatus === "no_show") list = list.filter(b => b.state === "no_show");
                else if (filterStatus === "prepaid") list = list.filter(b => b.has_food_order || b.food_order_total > 0);
            }

            if (query) {
                list = list.filter(b => {
                    const name = (b.customerDisplayName || "").toLowerCase();
                    const phone = (b.customerDisplayPhone || "").toLowerCase();
                    const tables = (b.tableDisplayNames || "").toLowerCase();
                    const notes = (b.guest_details || "").toLowerCase();
                    const ref = (b.name || "").toLowerCase();
                    return name.includes(query) || phone.includes(query) || tables.includes(query) || notes.includes(query) || ref.includes(query);
                });
            }
        }

        return list.slice().sort((a, b) => {
            const tsA = a.startTimestamp || (a.startDateStr ? `${a.startDateStr} ${a.startTimeStr}` : "");
            const tsB = b.startTimestamp || (b.startDateStr ? `${b.startDateStr} ${b.startTimeStr}` : "");
            if (typeof tsA === "number" && typeof tsB === "number" && (tsA || tsB)) {
                return tsA - tsB;
            }
            return String(tsA || "").localeCompare(String(tsB || ""));
        });
    }

    get dateBookings() {
        const cur = this.state.currentDate;
        const p = this.state.calendarPeriod;
        const curDateStr = cur.toFormat("yyyy-MM-dd");
        const query = (this.state.searchQuery || "").trim().toLowerCase();
        const filterStatus = this.state.filterStatus;

        return this.allBookings.filter(b => {
            const bDate = b.startDateStr;
            if (!bDate) return false;

            // Period check
            if (p === "day") {
                if (bDate !== curDateStr) return false;
            } else if (p === "week") {
                const s = cur.startOf("week").toFormat("yyyy-MM-dd");
                const e = cur.endOf("week").toFormat("yyyy-MM-dd");
                if (bDate < s || bDate > e) return false;
            } else if (p === "month") {
                const s = cur.startOf("month").toFormat("yyyy-MM-dd");
                const e = cur.endOf("month").toFormat("yyyy-MM-dd");
                if (bDate < s || bDate > e) return false;
            } else if (p === "quarter") {
                const s = cur.startOf("quarter").toFormat("yyyy-MM-dd");
                const e = cur.endOf("quarter").toFormat("yyyy-MM-dd");
                if (bDate < s || bDate > e) return false;
            } else if (p === "year") {
                const s = cur.startOf("year").toFormat("yyyy-MM-dd");
                const e = cur.endOf("year").toFormat("yyyy-MM-dd");
                if (bDate < s || bDate > e) return false;
            } else if (p === "custom") {
                if (bDate < this.state.customStartDate || bDate > this.state.customEndDate) return false;
            }

            // Status filter check
            if (filterStatus === "confirmed" && b.state !== "confirmed" && b.state !== "booked") return false;
            if (filterStatus === "checked_in" && b.state !== "checked_in") return false;
            if (filterStatus === "checked_out" && b.state !== "checked_out" && b.state !== "completed") return false;
            if (filterStatus === "no_show" && b.state !== "no_show") return false;
            if (filterStatus === "prepaid" && (!b.has_food_order && !(b.food_order_total > 0))) return false;

            // Search query check
            if (query) {
                const name = (b.customerDisplayName || "").toLowerCase();
                const phone = (b.customerDisplayPhone || "").toLowerCase();
                const tables = (b.tableDisplayNames || "").toLowerCase();
                const ref = (b.name || "").toLowerCase();
                if (!name.includes(query) && !phone.includes(query) && !tables.includes(query) && !ref.includes(query)) {
                    return false;
                }
            }
            return true;
        });
    }

    get upcomingBookingsSummary() {
        const curDateStr = this.state.currentDate.toFormat("yyyy-MM-dd");
        const future = this.allBookings.filter(b => b.startDateStr && b.startDateStr > curDateStr);
        if (!future.length) return null;
        future.sort((a, b) => {
            const dA = a.startDateStr || "";
            const dB = b.startDateStr || "";
            return String(dA).localeCompare(String(dB));
        });
        const earliestDate = future[0].startDateStr;
        const count = future.filter(b => b.startDateStr === earliestDate).length;
        const dt = luxon.DateTime.fromISO(earliestDate);
        return {
            dateStr: earliestDate,
            formattedDate: dt.isValid ? dt.toFormat("ccc, LLL d") : earliestDate,
            count: count,
        };
    }

    jumpToDate(dateStr) {
        if (!dateStr) return;
        const dt = luxon.DateTime.fromISO(dateStr);
        if (dt.isValid) {
            this.state.currentDate = dt.startOf("day");
        }
    }

    getBookingsForTable(tableId) {
        const tid = parseInt(tableId);
        return this.dateBookings.filter(b => {
            if (b.tableRecords && b.tableRecords.length) {
                if (b.tableRecords.some(t => t && (t.id === tid || t.id === tableId))) {
                    return true;
                }
            }
            const raw = b.table_ids;
            if (Array.isArray(raw)) {
                return raw.some(t => {
                    const id = typeof t === "object" && t ? t.id : t;
                    return id === tid || id === tableId;
                });
            } else if (raw instanceof Set) {
                return Array.from(raw).some(t => {
                    const id = typeof t === "object" && t ? t.id : t;
                    return id === tid || id === tableId;
                });
            } else if (raw && typeof raw === "object") {
                return raw.id === tid || raw.id === tableId;
            } else if (raw) {
                return raw === tid || raw === tableId;
            }
            return false;
        });
    }

    get unassignedBookings() {
        return this.dateBookings.filter(b => {
            const hasRecs = b.tableRecords && b.tableRecords.length > 0;
            const hasRaw = b.table_ids && (Array.isArray(b.table_ids) ? b.table_ids.length > 0 : (b.table_ids instanceof Set ? b.table_ids.size > 0 : Boolean(b.table_ids)));
            return !hasRecs && !hasRaw;
        });
    }

    get bookedList() {
        const list = this.state.showAllDates ? this.displayedBookings : this.dateBookings;
        return list.filter(b => b.state === "confirmed");
    }

    get checkedInList() {
        const list = this.state.showAllDates ? this.displayedBookings : this.dateBookings;
        return list.filter(b => b.state === "checked_in");
    }

    get noShowList() {
        const list = this.state.showAllDates ? this.displayedBookings : this.dateBookings;
        return list.filter(b => b.state === "no_show");
    }

    get checkedOutList() {
        const list = this.state.showAllDates ? this.displayedBookings : this.dateBookings;
        return list.filter(b => b.state === "checked_out");
    }

    get modalSelectedTable() {
        const tid = parseInt(this.state.newBooking.table_id);
        if (!tid) return null;
        return this.activeTables.find(t => t.id === tid);
    }

    get modalFormattedTimeRange() {
        const { date_str, start_time, duration_hours } = this.state.newBooking;
        if (!date_str || !start_time) return "";
        try {
            const dt = luxon.DateTime.fromFormat(`${date_str} ${start_time}`, "yyyy-MM-dd HH:mm");
            if (!dt.isValid) return `${date_str} ${start_time}`;
            const dtEnd = dt.plus({ hours: parseFloat(duration_hours || 2.0) });
            return `${dt.toFormat("d MMM, h:mm a")} → ${dtEnd.toFormat("h:mm a")}`;
        } catch {
            return `${date_str} ${start_time}`;
        }
    }

    // ==========================================
    // Calendar Month Grid Computation
    // ==========================================
    get calendarWeeks() {
        try {
            if (!this.state.currentDate || typeof this.state.currentDate.startOf !== "function") {
                this.state.currentDate = luxon.DateTime.now().startOf("day");
            }
            const startOfMonth = this.state.currentDate.startOf("month");
            const endOfMonth = this.state.currentDate.endOf("month");

            let curr = startOfMonth;
            let safetyCount = 0;
            while (curr.weekday !== 7 && safetyCount < 7) {
                curr = curr.minus({ days: 1 });
                safetyCount++;
            }

            const weeks = [];
            const allBookings = this.allBookings || [];
            const query = (this.state.searchQuery || "").trim().toLowerCase();

            for (let w = 0; w < 6; w++) {
                const days = [];
                const weekNumber = curr.weekNumber || (w + 1);
                for (let d = 0; d < 7; d++) {
                    const dateStr = curr.toFormat("yyyy-MM-dd");
                    const isCurrentMonth = curr.month === this.state.currentDate.month;
                    const isToday = curr.hasSame(luxon.DateTime.now(), "day");
                    const isSelected = curr.hasSame(this.state.currentDate, "day");

                    const dayBookings = allBookings.filter(b => {
                        if (!b || b.startDateStr !== dateStr) return false;
                        if (query) {
                            const name = (b.customerDisplayName || "").toLowerCase();
                            const phone = (b.customerDisplayPhone || "").toLowerCase();
                            const tables = (b.tableDisplayNames || "").toLowerCase();
                            if (!name.includes(query) && !phone.includes(query) && !tables.includes(query)) {
                                return false;
                            }
                        }
                        return true;
                    });

                    days.push({
                        date: curr,
                        dateStr: dateStr,
                        dayNumber: curr.day,
                        isCurrentMonth,
                        isToday,
                        isSelected,
                        bookings: dayBookings,
                    });
                    curr = curr.plus({ days: 1 });
                }
                weeks.push({
                    weekNumber,
                    days,
                });
                if (curr > endOfMonth && w >= 4) {
                    break;
                }
            }
            return weeks;
        } catch (err) {
            console.error("Error in calendarWeeks:", err);
            return [];
        }
    }

    // Mini Calendar Month Widget for Right Sidebar
    get miniCalendarWeeks() {
        const startOfMonth = this.state.currentDate.startOf("month");
        const endOfMonth = this.state.currentDate.endOf("month");
        let curr = startOfMonth;
        while (curr.weekday !== 7) {
            curr = curr.minus({ days: 1 });
        }
        const weeks = [];
        for (let w = 0; w < 6; w++) {
            const days = [];
            for (let d = 0; d < 7; d++) {
                days.push({
                    date: curr,
                    dateStr: curr.toFormat("yyyy-MM-dd"),
                    dayNumber: curr.day,
                    isCurrentMonth: curr.month === this.state.currentDate.month,
                    isToday: curr.hasSame(luxon.DateTime.now(), "day"),
                    isSelected: curr.hasSame(this.state.currentDate, "day"),
                });
                curr = curr.plus({ days: 1 });
            }
            weeks.push(days);
            if (curr > endOfMonth && w >= 4) break;
        }
        return weeks;
    }

    get miniCalendarMonthTitle() {
        return this.state.currentDate.toFormat("MMM yyyy");
    }

    // Navigation
    prevPeriod() {
        const p = this.state.calendarPeriod;
        if (p === "year") {
            this.state.currentDate = this.state.currentDate.minus({ years: 1 });
        } else if (p === "quarter") {
            this.state.currentDate = this.state.currentDate.minus({ months: 3 });
        } else if (p === "month" || this.state.viewMode === "calendar") {
            this.state.currentDate = this.state.currentDate.minus({ months: 1 });
        } else if (p === "week") {
            this.state.currentDate = this.state.currentDate.minus({ weeks: 1 });
        } else {
            this.state.currentDate = this.state.currentDate.minus({ days: 1 });
        }
    }

    nextPeriod() {
        const p = this.state.calendarPeriod;
        if (p === "year") {
            this.state.currentDate = this.state.currentDate.plus({ years: 1 });
        } else if (p === "quarter") {
            this.state.currentDate = this.state.currentDate.plus({ months: 3 });
        } else if (p === "month" || this.state.viewMode === "calendar") {
            this.state.currentDate = this.state.currentDate.plus({ months: 1 });
        } else if (p === "week") {
            this.state.currentDate = this.state.currentDate.plus({ weeks: 1 });
        } else {
            this.state.currentDate = this.state.currentDate.plus({ days: 1 });
        }
    }

    today() {
        this.state.currentDate = luxon.DateTime.now().startOf("day");
    }

    setCalendarPeriod(period) {
        this.state.calendarPeriod = period;
    }

    selectDate(dateObj) {
        this.state.currentDate = dateObj;
    }

    setViewMode(mode) {
        this.state.viewMode = mode;
    }

    // ==========================================
    // Double Booking & Merged/Linked Table Logic
    // ==========================================
    getRelatedTableIds(tableId) {
        const id = parseInt(tableId);
        if (!id) return [];
        const tableModel = this.pos.models["restaurant.table"];
        if (!tableModel) return [id];
        const tables = typeof tableModel.getAll === "function" ? tableModel.getAll() : (Array.isArray(tableModel) ? tableModel : []);
        const targetTable = (typeof tableModel.get === "function" ? tableModel.get(id) : null) || tables.find(t => t && t.id === id);
        if (!targetTable) return [id];

        const related = new Set([id]);

        // 1. Follow parent_id up to root
        let curr = targetTable;
        const visited = new Set([id]);
        while (curr && curr.parent_id) {
            const parentId = typeof curr.parent_id === "object" ? curr.parent_id.id : curr.parent_id;
            if (!parentId || visited.has(parentId)) break;
            visited.add(parentId);
            related.add(parentId);
            curr = (typeof tableModel.get === "function" ? tableModel.get(parentId) : null) || tables.find(t => t && t.id === parentId);
        }
        const rootId = curr ? curr.id : id;

        // 2. Add all children / merged tables
        for (const t of tables) {
            if (!t) continue;
            const pId = typeof t.parent_id === "object" ? t.parent_id.id : t.parent_id;
            if (pId === rootId || related.has(pId)) {
                related.add(t.id);
            }
        }

        return Array.from(related);
    }

    get tableConflictWarning() {
        const { table_id, date_str, start_time, duration_hours } = this.state.newBooking;
        if (!table_id || !date_str || !start_time) return null;

        const relatedTableIds = this.getRelatedTableIds(table_id);
        const [h, m] = start_time.split(":").map(Number);
        const reqStartMinutes = h * 60 + m;
        const reqEndMinutes = reqStartMinutes + Math.round(parseFloat(duration_hours || 2.0) * 60);

        const allBookings = this.allBookings;
        for (const b of allBookings) {
            if (this.state.editingBookingId && b.id === this.state.editingBookingId) {
                continue;
            }
            if (b.startDateStr !== date_str) continue;
            if (!["confirmed", "checked_in"].includes(b.state)) continue;

            const bTableIds = Array.isArray(b.table_ids)
                ? b.table_ids.map(t => (typeof t === "object" && t ? t.id : t))
                : [];

            const touches = bTableIds.some(tid => relatedTableIds.includes(tid));
            if (!touches) continue;

            const bStartMin = Math.round(b.startHourFraction * 60);
            const bEndMin = Math.round(b.endHourFraction * 60);

            if (reqStartMinutes < bEndMin && reqEndMinutes > bStartMin) {
                const tableObj = this.activeTables.find(t => t.id === parseInt(table_id));
                const tableName = tableObj ? `Table ${tableObj.table_number || tableObj.name} (🪑 ${tableObj.seats || 2})` : (b.tableDisplayNames || `Table #${table_id}`);
                return `Not available at the selected time: ${tableName}`;
            }
        }
        return null;
    }

    // Positioning and color calculation for Gantt timeline
    getBookingPosition(booking) {
        if (!booking.start_datetime) return null;

        const startFraction = booking.startHourFraction;
        const endFraction = booking.endHourFraction;
        const duration = Math.max(endFraction - startFraction, 0.5);

        const left = Math.round(startFraction * this.slotWidth);
        const width = Math.max(Math.round(duration * this.slotWidth), 48);

        return {
            left: `${left}px`,
            width: `${width}px`,
            startStr: booking.startTimeStr,
            endStr: booking.endTimeStr,
        };
    }

    getBookingStyle(booking) {
        const pos = this.getBookingPosition(booking);
        if (!pos) return "display: none;";
        return `left: ${pos.left}; width: ${pos.width};`;
    }

    // Gantt Drag & Drop
    onGanttPillDragStart(ev, booking) {
        this.state.draggedBookingId = booking.id;
        ev.dataTransfer.setData("text/plain", booking.id.toString());
        ev.dataTransfer.effectAllowed = "move";
    }

    onGanttSlotDragOver(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
    }

    async onGanttSlotDrop(ev, table, hour) {
        ev.preventDefault();
        const bookingId = this.state.draggedBookingId || parseInt(ev.dataTransfer.getData("text/plain"));
        this.state.draggedBookingId = null;
        if (!bookingId) return;

        const booking = this.pos.models["appointment.booking"]?.get
            ? this.pos.models["appointment.booking"].get(bookingId)
            : this.allBookings.find(b => b && b.id === bookingId);
        if (!booking) return;

        const targetTableId = table ? table.id : false;
        const hourStr = hour < 10 ? `0${hour}:00` : `${hour}:00`;
        const dateStr = this.state.currentDate.toFormat("yyyy-MM-dd");
        const newStartDatetime = `${dateStr} ${hourStr}:00`;
        const duration = parseFloat(booking.duration) || 1.5;

        await this.pos.updateBookingFromPos(booking.id, {
            table_id: targetTableId,
            start_datetime: newStartDatetime,
            duration: duration,
        });
    }

    // Gantt Duration Resizing
    onResizeStart(ev, booking) {
        ev.preventDefault();
        ev.stopPropagation();

        const startX = ev.clientX;
        const initialDuration = parseFloat(booking.duration) || (booking.endHourFraction - booking.startHourFraction) || 1.5;
        const slotWidth = this.slotWidth;
        let currentNewDuration = initialDuration;
        const pillEl = ev.target.closest(".pos-gantt-pill");

        const onMouseMove = (moveEv) => {
            const deltaX = moveEv.clientX - startX;
            const deltaHours = deltaX / slotWidth;
            const rawDuration = initialDuration + deltaHours;
            const snapped = Math.max(0.5, Math.round(rawDuration * 2) / 2);
            currentNewDuration = snapped;
            if (pillEl) {
                pillEl.style.width = `${Math.max(Math.round(snapped * slotWidth), 48)}px`;
            }
        };

        const onMouseUp = async (upEv) => {
            window.removeEventListener("mousemove", onMouseMove);
            window.removeEventListener("mouseup", onMouseUp);

            if (currentNewDuration !== initialDuration) {
                await this.pos.updateBookingFromPos(booking.id, {
                    duration: currentNewDuration,
                });
            }
        };

        window.addEventListener("mousemove", onMouseMove);
        window.addEventListener("mouseup", onMouseUp);
    }

    onSlotClick(table, hour) {
        const hourStr = hour < 10 ? `0${hour}:00` : `${hour}:00`;
        this.openCreateModal(this.state.currentDate.toFormat("yyyy-MM-dd"), table ? table.id : "");
        this.state.newBooking.start_time = hourStr;
    }

    onCalendarDayClick(day) {
        this.openCreateModal(day.dateStr);
    }

    openCreateModal(prefillDateStr = null, prefillTableId = null) {
        const dateStr = prefillDateStr || this.state.currentDate.toFormat("yyyy-MM-dd");
        const defaultHour = "16:00";
        this.state.editingBookingId = null;
        this.state.newBooking = {
            customer_name: "",
            customer_phone: "",
            customer_email: "",
            party_size: 2,
            table_id: prefillTableId || (this.activeTables[0]?.id || ""),
            date_str: dateStr,
            start_time: defaultHour,
            duration_hours: "2.0",
            notes: "",
            state: "confirmed",
        };
        this.state.showBookingModal = true;
    }

    openEditModal(booking) {
        this.state.editingBookingId = booking.id;
        const tableId = (booking.table_ids && booking.table_ids.length)
            ? (typeof booking.table_ids[0] === "object" ? booking.table_ids[0].id : booking.table_ids[0])
            : "";
        let guestName = booking.customer_name || "";
        if (!guestName && booking.customerDisplayName && !booking.customerDisplayName.startsWith("Table Booking") && booking.customerDisplayName !== "Walk-in Guest") {
            guestName = booking.customerDisplayName;
        } else if (!guestName && booking.partner_id && booking.partner_id.name && !booking.partner_id.name.startsWith("Table Booking") && booking.partner_id.name !== "Resto Cafe") {
            guestName = booking.partner_id.name;
        }

        this.state.newBooking = {
            customer_name: guestName,
            customer_phone: booking.customerDisplayPhone || "",
            customer_email: booking.customerDisplayEmail || "",
            party_size: booking.party_size || 2,
            table_id: tableId,
            date_str: booking.startDateStr || this.state.currentDate.toFormat("yyyy-MM-dd"),
            start_time: booking.startTimeStr || "16:00",
            duration_hours: (booking.duration || 2.0).toString(),
            notes: booking.guest_details || "",
            state: booking.state || "confirmed",
        };
        this.state.showBookingModal = true;
    }

    closeBookingModal() {
        this.state.showBookingModal = false;
        this.state.editingBookingId = null;
    }

    openClosingDayModal() {
        this.state.closingDate = this.state.currentDate.toFormat("yyyy-MM-dd");
        this.state.closingReason = "";
        this.state.showClosingDayModal = true;
    }

    closeClosingDayModal() {
        this.state.showClosingDayModal = false;
    }

    confirmClosingDay() {
        const date = this.state.closingDate;
        const reason = this.state.closingReason || _t("Closed / Holiday");
        this.closeClosingDayModal();
        this.pos.dialog.add(AlertDialog, {
            title: _t("Closing Day"),
            body: _t(`Bookings closed for ${date}: ${reason}`),
        });
    }

    unassignModalTable() {
        this.state.newBooking.table_id = "";
    }

    async setModalBookingState(targetState) {
        this.state.newBooking.state = targetState;
        if (this.state.editingBookingId) {
            await this.pos.updateBookingFromPos(this.state.editingBookingId, { state: targetState });
        }
    }

    async saveBooking() {
        if (this.tableConflictWarning) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("Double Booking Error"),
                body: this.tableConflictWarning,
            });
            return;
        }

        const b = this.state.newBooking;
        const duration = parseFloat(b.duration_hours || 2.0);
        const vals = {
            customer_name: b.customer_name || _t("Walk-in Guest"),
            customer_phone: b.customer_phone || "",
            customer_email: b.customer_email || "",
            party_size: parseInt(b.party_size) || 1,
            table_id: parseInt(b.table_id) || false,
            notes: b.notes || "",
            start_datetime: `${b.date_str} ${b.start_time}:00`,
            duration: duration,
            state: b.state || "confirmed",
        };

        if (this.state.editingBookingId) {
            const res = await this.pos.updateBookingFromPos(this.state.editingBookingId, vals);
            if (res) {
                this.closeBookingModal();
            }
        } else {
            const res = await this.pos.createBookingFromPos(vals);
            if (res) {
                this.closeBookingModal();
            }
        }
    }

    get currentModalBooking() {
        if (!this.state.editingBookingId) return null;
        return (this.pos.models["appointment.booking"]?.get
            ? this.pos.models["appointment.booking"].get(this.state.editingBookingId)
            : this.allBookings.find(b => b.id === this.state.editingBookingId)) || null;
    }

    async checkInBooking(booking) {
        if (!booking) return;
        await this.pos.updateBookingFromPos(booking.id, { state: "checked_in" });
    }

    async releaseBookingTable(booking) {
        if (!booking) return;

        if (this.dialog) {
            const confirmed = await new Promise(resolve => {
                this.dialog.add(ConfirmationDialog, {
                    title: _t("Release Table"),
                    body: _t("Are you sure you want to release this table and check out the booking?"),
                    confirm: () => resolve(true),
                    cancel: () => resolve(false),
                });
            });
            if (!confirmed) return;
        }

        const tableRecord = (booking.tableRecords && booking.tableRecords.length > 0)
            ? booking.tableRecords[0]
            : this.activeTables.find(t => {
                const tableIds = Array.isArray(booking.table_ids)
                    ? booking.table_ids.map(x => (typeof x === "object" && x ? x.id : x))
                    : [booking.table_ids];
                return tableIds.includes(t.id);
            });
        if (tableRecord) {
            await this.pos.releaseTable(tableRecord, booking);
        } else {
            await this.pos.updateBookingFromPos(booking.id, { state: "checked_out" });
        }
    }

    async releaseModalTable() {
        if (this.currentModalBooking) {
            await this.releaseBookingTable(this.currentModalBooking);
        }
        this.closeBookingModal();
    }

    async openBookingOrder(booking) {
        if (!booking) return;

        // 1. Identify table
        const tableRecord = (booking.tableRecords && booking.tableRecords.length > 0)
            ? booking.tableRecords[0]
            : this.activeTables.find(t => {
                const tableIds = Array.isArray(booking.table_ids)
                    ? booking.table_ids.map(x => (typeof x === "object" && x ? x.id : x))
                    : [booking.table_ids];
                return tableIds.includes(t.id);
            });

        if (!tableRecord) {
            this.pos.dialog.add(AlertDialog, {
                title: _t("No Table Assigned"),
                body: _t("Please assign a restaurant table to this booking first."),
            });
            this.openEditModal(booking);
            return;
        }

        // 2. Close modal if open
        if (this.state.showBookingModal) {
            this.closeBookingModal();
        }

        // 3. Load booking directly onto the table with dishes and prepayment
        await this.pos.loadBookingIntoTable(booking, tableRecord);
    }

    async openTableOrderFromModal() {
        if (this.currentModalBooking) {
            await this.openBookingOrder(this.currentModalBooking);
            return;
        }
        const tableId = parseInt(this.state.newBooking.table_id);
        if (!tableId) return;
        const table = this.activeTables.find(t => t.id === tableId);
        if (!table) return;

        this.closeBookingModal();
        await this.pos.setTableFromUi(table);
    }

    // Drag and Drop (Kanban)
    onDragStart(ev, booking) {
        this.state.draggedBookingId = booking.id;
        ev.dataTransfer.setData("text/plain", booking.id.toString());
        ev.dataTransfer.effectAllowed = "move";
    }

    onDragOver(ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
    }

    async onDrop(ev, targetState) {
        ev.preventDefault();
        const bookingId = this.state.draggedBookingId || parseInt(ev.dataTransfer.getData("text/plain"));
        this.state.draggedBookingId = null;

        if (!bookingId) return;
        const booking = this.pos.models["appointment.booking"]?.get
            ? this.pos.models["appointment.booking"].get(bookingId)
            : this.allBookings.find(b => b && b.id === bookingId);
        if (!booking || booking.state === targetState) return;

        await this.pos.updateBookingFromPos(booking.id, { state: targetState });
    }
}

registry.category("pos_pages").add("BookingScreen", {
    name: "BookingScreen",
    component: BookingScreen,
    route: `/pos/ui/${odoo.pos_config_id}/booking`,
    params: {},
});
