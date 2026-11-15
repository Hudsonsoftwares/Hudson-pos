/** @odoo-module **/

import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime, serializeDateTime } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { usePopover } from "@web/core/popover/popover_hook";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { Layout } from "@web/search/layout";
import { SearchBar } from "@web/search/search_bar/search_bar";
import { useSearchBarToggler } from "@web/search/search_bar/search_bar_toggler";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import {
    Component,
    onMounted,
    onWillStart,
    onWillUnmount,
    onWillUpdateProps,
    proxy,
    signal,
    useProps,
} from "@odoo/owl";

const { DateTime } = luxon;

const SCALES = {
    day: { label: _t("Day"), unit: "day", step: { days: 1 }, colUnit: "hour", colCount: 24, colMinWidth: 48 },
    week: { label: _t("Week"), unit: "week", step: { weeks: 1 }, colUnit: "day", colCount: 7, colMinWidth: 120 },
    month: { label: _t("Month"), unit: "month", step: { months: 1 }, colUnit: "day", colMinWidth: 38 },
    year: { label: _t("Year"), unit: "year", step: { years: 1 }, colUnit: "month", colCount: 12, colMinWidth: 80 },
};
const LANE_HEIGHT = 30;
// Grouped fields a shift can be dragged between (dates groupings cannot).
const DRAGGABLE_GROUP_TYPES = ["many2one", "selection", "char"];

/** Summary of a shift shown when it is clicked: details and quick actions. */
export class FsSlotPopover extends Component {
    static template = "hudson_planning.FsSlotPopover";
    props = useProps();

    get dateLabel() {
        const start = deserializeDateTime(this.props.data.date_start);
        const end = deserializeDateTime(this.props.data.date_end);
        const time = (d) => d.toLocaleString(DateTime.TIME_SIMPLE);
        const day = (d) => d.toFormat("d MMM");
        const sameDay = start.hasSame(end, "day");
        const hours = Math.round((this.props.data.allocated_hours || 0) * 100) / 100;
        return `${day(start)}, ${time(start)} → ${sameDay ? "" : day(end) + ", "}${time(end)} (${hours}h)`;
    }

    get stars() {
        const priority = parseInt(this.props.data.priority || 0);
        return [1, 2, 3].map((i) => i <= priority);
    }
}

export class FsScheduleController extends Component {
    static template = "hudson_planning.FsScheduleView";
    static components = { Layout, SearchBar, CogMenu, Dropdown, DropdownItem };
    props = useProps();

    rootRef = signal.ref();

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.actionService = useService("action");
        this.popover = usePopover(FsSlotPopover, { position: "top" });
        this.searchBarToggler = useSearchBarToggler();
        this.scales = SCALES;
        this.scaleKeys = Object.keys(SCALES);

        const localState = this.props.state || {};
        this.state = proxy({
            scale: localState.scale || this.props.archInfo.defaultScale,
            // context.initial_date: e.g. the first shift of a sales order
            anchor: localState.anchor
                ? DateTime.fromISO(localState.anchor)
                : this.props.context?.initial_date
                    ? deserializeDateTime(this.props.context.initial_date).startOf("day")
                    : DateTime.local().startOf("day"),
            showSidePanel: localState.showSidePanel ?? true,
            rows: [],
            slots: [],
            toPlan: [],
            groupField: false,
            groupFields: [],
            // Two group bys (e.g. Role > Resources): {headerKey: collapsed}
            collapsed: localState.collapsed || {},
            loading: true,
            dragOver: null,
            // Cells selected by dragging: {startRow, startCol, endRow, endCol, active}
            selection: null,
        });

        useSetupAction({
            rootRef: this.rootRef,
            getLocalState: () => ({
                scale: this.state.scale,
                anchor: this.state.anchor.toISODate(),
                showSidePanel: this.state.showSidePanel,
                collapsed: this.state.collapsed,
            }),
        });

        onWillStart(async () => {
            this.isManager = await user.hasGroup("hudson_planning.group_planning_manager");
            await this.load(this.props);
        });
        onWillUpdateProps((nextProps) => this.load(nextProps));

        // The selection ends wherever the mouse is released
        const onMouseUp = () => this.onSelectionEnd();
        const onKeyDown = (ev) => {
            if (ev.key === "Escape" && this.state.selection?.active) {
                this.state.selection = null;
            }
        };
        onMounted(() => {
            window.addEventListener("mouseup", onMouseUp);
            window.addEventListener("keydown", onKeyDown);
        });
        onWillUnmount(() => {
            window.removeEventListener("mouseup", onMouseUp);
            window.removeEventListener("keydown", onKeyDown);
        });
    }

    // -------------------------------------------------------------------------
    // Period and columns
    // -------------------------------------------------------------------------

    get scaleInfo() {
        return SCALES[this.state.scale];
    }

    get periodStart() {
        const anchor = this.state.anchor;
        if (this.state.scale === "week") {
            // Locale's first day of the week (1 = Monday ... 7 = Sunday)
            const weekStart = localization.weekStart || 1;
            return anchor.minus({ days: (anchor.weekday - weekStart + 7) % 7 }).startOf("day");
        }
        return anchor.startOf(this.scaleInfo.unit);
    }

    get periodEnd() {
        return this.periodStart.plus(this.scaleInfo.step);
    }

    get columns() {
        const start = this.periodStart;
        const end = this.periodEnd;
        const unit = this.scaleInfo.colUnit;
        const columns = [];
        const today = DateTime.local();
        for (let col = start; col < end; col = col.plus({ [unit + "s"]: 1 })) {
            const colEnd = col.plus({ [unit + "s"]: 1 });
            columns.push({
                key: col.toISO(),
                start: col,
                end: colEnd,
                date: col.toISODate(),
                isToday: unit === "month" ? col.hasSame(today, "month") : col.hasSame(today, unit === "hour" ? "hour" : "day"),
                isWeekend: unit === "day" && [6, 7].includes(col.weekday),
                label: this._columnLabel(col),
            });
        }
        return columns;
    }

    _columnLabel(col) {
        switch (this.state.scale) {
            case "day":
                return col.toFormat("h a");
            case "week":
                return col.toFormat("cccc d");
            case "month":
                return col.toFormat("d");
            default:
                return col.toFormat("MMMM");
        }
    }

    get periodLabel() {
        const start = this.periodStart;
        const last = this.periodEnd.minus({ days: 1 });
        switch (this.state.scale) {
            case "day":
                return start.toFormat("cccc d MMMM yyyy");
            case "week":
                return _t("Week %(week)s, %(start)s - %(end)s", {
                    week: start.plus({ days: 3 }).weekNumber,
                    start: start.toFormat("d MMM"),
                    end: last.toFormat("d MMM"),
                });
            case "month":
                return start.toFormat("MMMM yyyy");
            default:
                return start.toFormat("yyyy");
        }
    }

    get gridStyle() {
        const count = this.columns.length;
        return `--fs-col-count: ${count}; --fs-col-min: ${this.scaleInfo.colMinWidth}px;`;
    }

    // -------------------------------------------------------------------------
    // Data
    // -------------------------------------------------------------------------

    async load(props = this.props) {
        this.state.loading = true;
        const data = await this.orm.call("fs.planning.slot", "get_schedule_view_data", [
            props.domain,
            props.groupBy,
            serializeDateTime(this.periodStart),
            serializeDateTime(this.periodEnd),
        ], { context: props.context });
        this.state.groupField = data.group_field;
        this.state.groupFields = data.group_fields || [];
        this.state.toPlan = data.to_plan;
        this.state.slots = data.slots;
        this.state.rows = data.rows;
        this.state.loading = false;
    }

    get groupFieldName() {
        return this.state.groupField ? this.state.groupField.split(":")[0] : false;
    }

    get canDropOnRows() {
        const groupFields = this.state.groupFields;
        if (!groupFields.length) {
            return false;
        }
        return groupFields.every((groupField) => {
            if (groupField.includes(":")) {
                return false;
            }
            const field = this.props.fields[groupField];
            return field && DRAGGABLE_GROUP_TYPES.includes(field.type) && !field.readonly;
        });
    }

    // -------------------------------------------------------------------------
    // Two group bys: collapsible groups (e.g. Role > Resources)
    // -------------------------------------------------------------------------

    get isNested() {
        return this.state.groupFields.length === 2;
    }

    /** Collapsed by default: the groups without shifts in the period. */
    isCollapsed(header) {
        const collapsed = this.state.collapsed[header.key];
        return collapsed === undefined ? !header.has_slots : collapsed;
    }

    toggleGroup(header) {
        this.state.collapsed = { ...this.state.collapsed, [header.key]: !this.isCollapsed(header) };
    }

    /** Rows shown: the rows of the collapsed groups are hidden. */
    get visibleRows() {
        if (!this.isNested) {
            return this.state.rows;
        }
        const collapsedKeys = new Set(
            this.state.rows.filter((row) => row.type === "group" && this.isCollapsed(row)).map((row) => row.key)
        );
        return this.state.rows.filter((row) => row.type === "group" || !collapsedKeys.has(row.group_key));
    }

    /** Hours planned per column in the rows of a group (header summary). */
    groupColumnHours(header) {
        const rowKeys = new Set(this.state.rows.filter((row) => row.group_key === header.key).map((row) => row.key));
        const columns = this.columns;
        const hours = columns.map(() => 0);
        for (const slot of this.state.slots) {
            if (!rowKeys.has(slot.row_key)) {
                continue;
            }
            const start = deserializeDateTime(slot.date_start);
            const end = deserializeDateTime(slot.date_end);
            const duration = end - start;
            if (duration <= 0) {
                continue;
            }
            columns.forEach((col, index) => {
                const overlap = Math.min(end, col.end) - Math.max(start, col.start);
                if (overlap > 0) {
                    hours[index] += (slot.allocated_hours || 0) * overlap / duration;
                }
            });
        }
        return columns.map((col, index) => ({ key: col.key, hours: hours[index] }));
    }

    formatSummaryHours(hours) {
        const minutes = Math.round(hours * 60);
        const h = Math.floor(minutes / 60);
        const m = minutes % 60;
        return m ? `${h}h ${m}m` : `${h}h`;
    }

    /** Field values of a row (fields of the group bys -> value). */
    rowValues(row) {
        return row.values || (this.groupFieldName ? { [this.groupFieldName]: row.key } : {});
    }

    /** Pills of a row: position in the period and lane (to avoid overlaps). */
    rowPills(row) {
        const columns = this.columns;
        const pills = this.state.slots
            .filter((slot) => slot.row_key === row.key)
            .map((slot) => {
                const start = deserializeDateTime(slot.date_start);
                const end = deserializeDateTime(slot.date_end);
                // Hours are drawn to scale; in days and months, a shift fills the cells it covers.
                const snap = this.scaleInfo.colUnit !== "hour";
                return {
                    slot, start, end,
                    left: this._position(start, columns, snap && "floor"),
                    right: this._position(end, columns, snap && "ceil"),
                };
            })
            .sort((a, b) => a.left - b.left || b.right - a.right);
        const lanes = [];
        for (const pill of pills) {
            let lane = lanes.findIndex((laneEnd) => laneEnd <= pill.left + 1e-9);
            if (lane === -1) {
                lane = lanes.length;
                lanes.push(0);
            }
            lanes[lane] = pill.right;
            pill.lane = lane;
            const width = Math.max(pill.right - pill.left, 100 / columns.length / 4);
            pill.style = `left: ${pill.left}%; width: calc(${width}% - 4px); top: ${4 + lane * LANE_HEIGHT}px;`;
            pill.timeLabel = this._pillTime(pill.start, pill.end);
        }
        return { pills, height: Math.max(lanes.length, 1) * LANE_HEIGHT + 10 };
    }

    /** Position (in % of the period) of a datetime, column by column,
     * optionally snapped to the column bounds ("floor" or "ceil"). */
    _position(datetime, columns, snap = false) {
        if (datetime <= columns[0].start) {
            return 0;
        }
        const last = columns[columns.length - 1];
        if (datetime >= last.end) {
            return 100;
        }
        const index = columns.findIndex((col) => datetime < col.end);
        const col = columns[index];
        let fraction = (datetime - col.start) / (col.end - col.start);
        if (snap === "floor") {
            fraction = 0;
        } else if (snap === "ceil") {
            fraction = fraction > 0 ? 1 : 0;
        }
        return ((index + fraction) / columns.length) * 100;
    }

    _pillTime(start, end) {
        if (this.state.scale === "year") {
            return "";
        }
        const fmt = (d) => d.toLocaleString(DateTime.TIME_SIMPLE).toLowerCase();
        if (start.hasSame(end, "day")) {
            return `${fmt(start)} - ${fmt(end)}`;
        }
        return `${start.toFormat("d MMM")} - ${end.toFormat("d MMM")}`;
    }

    pillClass(slot) {
        const classes = [`o_fs_pill_color_${(slot.color || 0) % 12}`];
        if (slot.state === "draft") {
            classes.push("o_fs_pill_draft");
        }
        if (slot.is_job && !slot.color) {
            classes.push("o_fs_pill_job");
        }
        if (slot.request_to_switch) {
            classes.push("o_fs_pill_switch");
        }
        if (slot.has_conflict) {
            classes.push("o_fs_pill_conflict");
        }
        return classes.join(" ");
    }

    cellClass(row, col, rowIndex, colIndex) {
        const classes = [];
        if (this.isCellSelected(rowIndex, colIndex)) {
            classes.push("o_fs_cell_selected");
        }
        if (col.isToday) {
            classes.push("o_fs_today");
        }
        const daysOff = row.days_off;
        if (daysOff ? daysOff.includes(col.date) && this.scaleInfo.colUnit === "day" : col.isWeekend) {
            classes.push("o_fs_unavailable");
        }
        if (this.state.dragOver === `${row.key}|${col.key}`) {
            classes.push("o_fs_drag_over");
        }
        return classes.join(" ");
    }

    progress(row) {
        if (!row.capacity_hours) {
            return 0;
        }
        return Math.min((row.planned_hours / row.capacity_hours) * 100, 100);
    }

    formatHours(hours) {
        return `${Math.round(hours || 0)}h`;
    }

    // -------------------------------------------------------------------------
    // Navigation
    // -------------------------------------------------------------------------

    async setScale(scale) {
        this.state.scale = scale;
        await this.load();
    }

    async onPrevious() {
        this.state.anchor = this.periodStart.minus(this.scaleInfo.step);
        await this.load();
    }

    async onNext() {
        this.state.anchor = this.periodStart.plus(this.scaleInfo.step);
        await this.load();
    }

    async onToday() {
        this.state.anchor = DateTime.local().startOf("day");
        await this.load();
    }

    toggleSidePanel() {
        this.state.showSidePanel = !this.state.showSidePanel;
    }

    // -------------------------------------------------------------------------
    // Shifts
    // -------------------------------------------------------------------------

    /** Default start/end of a new shift in a column. */
    _columnInterval(col) {
        if (this.scaleInfo.colUnit === "hour") {
            return [col.start, col.end];
        }
        const day = col.start.startOf("day");
        return [day.set({ hour: 8 }), day.set({ hour: 17 })];
    }

    _rowDefaults(row) {
        const context = {};
        if (this.canDropOnRows) {
            for (const [fname, value] of Object.entries(this.rowValues(row))) {
                if (value !== false) {
                    context[`default_${fname}`] = value;
                }
            }
        }
        return context;
    }

    openFormDialog(resId, title, context = {}) {
        this.dialog.add(FormViewDialog, {
            resModel: this.props.resModel,
            resId,
            title,
            context: { ...this.props.context, ...context },
            onRecordSaved: () => this.load(),
        }, {
            onClose: () => this.load(),
        });
    }

    // -------------------------------------------------------------------------
    // Selection of cells (drag over rows and columns)
    // -------------------------------------------------------------------------

    get selectionBounds() {
        const sel = this.state.selection;
        return {
            r0: Math.min(sel.startRow, sel.endRow),
            r1: Math.max(sel.startRow, sel.endRow),
            c0: Math.min(sel.startCol, sel.endCol),
            c1: Math.max(sel.startCol, sel.endCol),
        };
    }

    isCellSelected(rowIndex, colIndex) {
        if (!this.state.selection) {
            return false;
        }
        const { r0, r1, c0, c1 } = this.selectionBounds;
        return rowIndex >= r0 && rowIndex <= r1 && colIndex >= c0 && colIndex <= c1;
    }

    onCellMouseDown(rowIndex, colIndex, ev) {
        if (!this.isManager || ev.button !== 0) {
            return; // only administrators plan shifts
        }
        ev.preventDefault(); // no text selection while dragging
        this.state.selection = { startRow: rowIndex, startCol: colIndex, endRow: rowIndex, endCol: colIndex, active: true };
    }

    onCellMouseEnter(rowIndex, colIndex) {
        const sel = this.state.selection;
        if (sel?.active) {
            sel.endRow = rowIndex;
            // Rows can only be combined when the shifts can be assigned to them
            if (!this.canDropOnRows) {
                sel.endRow = sel.startRow;
            }
            sel.endCol = colIndex;
        }
    }

    onSelectionEnd() {
        const sel = this.state.selection;
        if (!sel?.active) {
            return;
        }
        sel.active = false;
        const { r0, r1, c0, c1 } = this.selectionBounds;
        const rows = this.visibleRows.slice(r0, r1 + 1).filter((row) => row.type !== "group");
        if (!rows.length) {
            this.state.selection = null;
            return;
        }
        const columns = this.columns.slice(c0, c1 + 1);
        if ((rows.length === 1 && columns.length === 1) || this.state.scale === "year") {
            this.state.selection = null;
            this.onCellClick(rows[0], columns[0]);
            return;
        }
        // Like a single cell: the shift form opens directly, spanning the
        // selected columns (first column's start to last column's end).
        const [start] = this._columnInterval(columns[0]);
        const [, end] = this._columnInterval(columns[columns.length - 1]);
        const [firstRow, ...otherRows] = rows;
        this.dialog.add(FormViewDialog, {
            resModel: this.props.resModel,
            title: _t("Add Shift"),
            context: {
                ...this.props.context,
                ...this._rowDefaults(firstRow),
                default_date_start: serializeDateTime(start),
                default_date_end: serializeDateTime(end),
            },
            // Several rows selected: the saved shift is repeated on each other row
            onRecordSaved: (record) => this._copyToRows(record.resId, otherRows),
        }, {
            onClose: () => {
                this.state.selection = null;
                this.load();
            },
        });
    }

    async _copyToRows(slotId, rows) {
        if (!rows.length || !this.canDropOnRows) {
            return;
        }
        const errors = [];
        for (const row of rows) {
            try {
                await this.orm.call(this.props.resModel, "copy", [[slotId]], {
                    default: this.rowValues(row),
                });
            } catch (error) {
                errors.push(error.data?.message || error.message);
            }
        }
        if (errors.length) {
            this.notification.add(
                _t("%(count)s shift(s) were not created: %(reasons)s", {
                    count: errors.length,
                    reasons: [...new Set(errors)].join(" "),
                }),
                { type: "warning", sticky: true },
            );
        }
    }

    onCellClick(row, col) {
        if (!this.isManager) {
            return; // only administrators plan shifts
        }
        const [start, end] = this._columnInterval(col);
        this.openFormDialog(false, _t("Add Shift"), {
            ...this._rowDefaults(row),
            default_date_start: serializeDateTime(start),
            default_date_end: serializeDateTime(end),
        });
    }

    onClickNew() {
        const [start, end] = this._columnInterval(this.columns.find((c) => c.isToday) || this.columns[0]);
        this.openFormDialog(false, _t("Add Shift"), {
            default_date_start: serializeDateTime(start),
            default_date_end: serializeDateTime(end),
        });
    }

    async onPillClick(slot, ev) {
        const target = ev.currentTarget;
        const data = await this.orm.call("fs.planning.slot", "get_popover_data", [[slot.id]]);
        if (!target.isConnected) {
            return;
        }
        this.popover.open(target, {
            data,
            onEdit: () => {
                this.popover.close();
                this.openFormDialog(slot.id, _t("Edit Shift"));
            },
            onAction: (action) => this._runSlotAction(slot.id, action),
            onDelete: () => this._deleteSlot(slot.id),
        });
    }

    async _runSlotAction(slotId, action) {
        this.popover.close();
        const args = [[slotId]];
        if (action.geolocate) {
            const { latitude, longitude } = await this._fetchLocation();
            args.push(latitude, longitude);
        }
        const result = await this.orm.call("fs.planning.slot", action.method, args);
        if (result && typeof result === "object" && result.type) {
            await this.actionService.doAction(result, { onClose: () => this.load() });
        }
        await this.load();
    }

    _fetchLocation() {
        return new Promise((resolve) => {
            if (!navigator.geolocation) {
                resolve({ latitude: 0, longitude: 0 });
                return;
            }
            navigator.geolocation.getCurrentPosition(
                (position) => resolve({ latitude: position.coords.latitude, longitude: position.coords.longitude }),
                () => resolve({ latitude: 0, longitude: 0 }),
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
            );
        });
    }

    _deleteSlot(slotId) {
        this.popover.close();
        this.dialog.add(ConfirmationDialog, {
            body: _t("Are you sure you want to delete this shift?"),
            confirmLabel: _t("Delete"),
            confirmClass: "btn-danger",
            confirm: async () => {
                await this.orm.unlink("fs.planning.slot", [slotId]);
                await this.load();
            },
            cancel: () => {},
        });
    }

    // -------------------------------------------------------------------------
    // Drag and drop: move shifts, plan the side panel's work
    // -------------------------------------------------------------------------

    onPillDragStart(pill, ev) {
        this.popover.close();
        const startColumn = this.columns.find((col) => pill.start < col.end) || this.columns[0];
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", JSON.stringify({
            type: "slot",
            id: pill.slot.id,
            rowKey: pill.slot.row_key,
            columnStart: startColumn.start.toISO(),
        }));
    }

    onToPlanDragStart(item, ev) {
        ev.dataTransfer.effectAllowed = "copy";
        ev.dataTransfer.setData("text/plain", JSON.stringify({ type: "to_plan", ref: item.ref, hours: item.hours }));
    }

    onCellDragOver(row, col, ev) {
        ev.preventDefault();
        this.state.dragOver = `${row.key}|${col.key}`;
    }

    onCellDragLeave(row, col) {
        if (this.state.dragOver === `${row.key}|${col.key}`) {
            this.state.dragOver = null;
        }
    }

    async onCellDrop(row, col, ev) {
        ev.preventDefault();
        this.state.dragOver = null;
        let payload;
        try {
            payload = JSON.parse(ev.dataTransfer.getData("text/plain"));
        } catch {
            return;
        }
        if (payload.type === "slot") {
            await this._moveSlot(payload, row, col);
        } else if (payload.type === "to_plan") {
            const [start] = this._columnInterval(col);
            const end = start.plus({ hours: payload.hours || 1 });
            // With two group bys, the employee of the row (else the first field)
            const values = this.rowValues(row);
            const dropField = "resource_id" in values ? "resource_id" : this.groupFieldName;
            await this.orm.call("fs.planning.slot", "action_plan_from_schedule", [
                payload.ref,
                this.canDropOnRows ? dropField : false,
                this.canDropOnRows ? values[dropField] : false,
                serializeDateTime(start),
                serializeDateTime(end),
            ]);
        }
        await this.load();
    }

    async _moveSlot(payload, row, col) {
        const slot = this.state.slots.find((s) => s.id === payload.id);
        if (!slot) {
            return;
        }
        const delta = col.start.diff(DateTime.fromISO(payload.columnStart));
        const values = {};
        if (delta.toMillis()) {
            values.date_start = serializeDateTime(deserializeDateTime(slot.date_start).plus(delta));
            values.date_end = serializeDateTime(deserializeDateTime(slot.date_end).plus(delta));
        }
        if (this.canDropOnRows && row.key !== payload.rowKey) {
            Object.assign(values, this.rowValues(row));
        }
        if (Object.keys(values).length) {
            await this.orm.write("fs.planning.slot", [slot.id], values);
        }
    }

    // -------------------------------------------------------------------------
    // Control panel actions
    // -------------------------------------------------------------------------

    get periodArgs() {
        return [this.props.domain, serializeDateTime(this.periodStart), serializeDateTime(this.periodEnd)];
    }

    get copyPreviousLabel() {
        return _t("Copy previous %s", this.scaleInfo.label.toLowerCase());
    }

    async onPublish() {
        const count = await this.orm.call("fs.planning.slot", "action_publish_period", this.periodArgs);
        this.notification.add(
            count ? _t("%s shift(s) published.", count) : _t("There are no draft shifts to publish in this period."),
            { type: count ? "success" : "warning" }
        );
        await this.load();
    }

    async onCopyPrevious() {
        const [domain, dateFrom, dateTo] = this.periodArgs;
        const previousFrom = serializeDateTime(this.periodStart.minus(this.scaleInfo.step));
        const count = await this.orm.call("fs.planning.slot", "action_copy_previous_period", [domain, dateFrom, dateTo, previousFrom]);
        this.notification.add(
            count ? _t("%s shift(s) copied from the previous period.", count) : _t("There are no shifts to copy from the previous period."),
            { type: count ? "success" : "warning" }
        );
        await this.load();
    }

    async onAutoPlan() {
        const result = await this.orm.call("fs.planning.slot", "action_auto_plan", this.periodArgs);
        if (!result.open && !result.sale_to_plan) {
            this.notification.add(_t("There are no open shifts or sales orders to plan in this period."), { type: "warning" });
        } else {
            const messages = [];
            if (result.open) {
                messages.push(_t("%(assigned)s of %(open)s open shift(s) assigned.", result));
            }
            if (result.sale_to_plan) {
                messages.push(result.sale_hours
                    ? _t("%(hours)s hour(s) of sales orders planned.", { hours: Math.round(result.sale_hours * 100) / 100 })
                    : _t("No employee with the role of the services sold is available in this period."));
            }
            this.notification.add(messages.join(" "), {
                type: result.assigned || result.sale_hours ? "success" : "warning",
            });
        }
        await this.load();
    }

    /** PDF of the schedule as shown (period, filters, grouping), downloaded directly. */
    async onPrint() {
        await this.actionService.doAction({
            type: "ir.actions.report",
            report_type: "qweb-pdf",
            report_name: "hudson_planning.report_fs_schedule",
            name: _t("Schedule - %s", this.periodLabel),
            data: {
                domain: this.props.domain,
                group_by: this.props.groupBy,
                date_from: serializeDateTime(this.periodStart),
                date_to: serializeDateTime(this.periodEnd),
                title: this.periodLabel,
                columns: this.columns.map((col) => ({
                    label: this.state.scale === "month" ? col.start.toFormat("ccc d") : col.label,
                    start: serializeDateTime(col.start),
                    end: serializeDateTime(col.end),
                    is_weekend: col.isWeekend,
                })),
            },
            context: this.props.context,
        });
    }

    onGenerateShifts() {
        this.actionService.doAction("hudson_planning.action_fs_shift_template_apply_wizard", {
            onClose: () => this.load(),
        });
    }
}

class FsScheduleArchParser {
    parse(arch) {
        return {
            dateStart: arch.getAttribute("date_start") || "date_start",
            dateStop: arch.getAttribute("date_stop") || "date_end",
            defaultScale: SCALES[arch.getAttribute("default_scale")] ? arch.getAttribute("default_scale") : "week",
        };
    }
}

export const fsScheduleView = {
    type: "fs_schedule",
    Controller: FsScheduleController,
    ArchParser: FsScheduleArchParser,
    searchMenuTypes: ["filter", "groupBy", "favorite"],
    props: (genericProps, view) => ({
        ...genericProps,
        archInfo: new view.ArchParser().parse(genericProps.arch),
    }),
};

registry.category("views").add("fs_schedule", fsScheduleView);
