import { Component, proxy, t, useProps, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { _t } from "@web/core/l10n/translation";

// Server statuses (pos.waitlist.entry._match_tables_full). These seat the whole party alone.
const SELECTABLE = ["match", "shared"];
// Only free tables can be combined for one party (merged under the first one). A too-small
// table is only usable combined: never offered alone.
const COMBINABLE = ["match", "too_small"];

/**
 * Pick existing POS table(s) for a waiting guest (Waiting -> Seated). The host always chooses.
 *
 * The picker answers "what is the closest suitable seating arrangement right now?": the
 * server ranks every arrangement that seats the whole party (one table, a shared table for a
 * guest willing to share, or free tables of one floor combined) by capacity fit, then fewer
 * tables, own table before shared, hints, then nearest on the floor plan. They are listed as
 * "Recommended" above the floor plan; an arrangement short of seats is never offered.
 *
 * Floors and tables come from the server on every refresh (pos.waitlist.entry
 * get_seatable_tables), so a floor or table created / renamed after this POS session opened
 * is offered too. Each table is rated by the server against the guest in this order: party
 * size, availability (open orders + waitlist holds), preferred floor (only when it can seat
 * the party), table sharing, then hints from the guest's tags / note. Suitable tables come
 * first, too-small and shared ones are marked, occupied tables and tables on another floor
 * than the guest asked for are shown but cannot be picked. A table with an unsynced open
 * order on this terminal is treated as occupied too.
 *
 * A party larger than every free table can be seated at several free tables of one floor:
 * the server suggests a combination, and the host may also add tables one by one while the
 * selection is still too small. The server re-checks and merges them like the floor plan.
 */
export class WaitlistTablePicker extends Component {
    static template = "hudson_pos_waitlist.WaitlistTablePicker";
    static components = { Dialog };
    props = useProps({
        entry: t.object(),
        onSeated: t.function().optional(() => {}),
        close: t.function(),
    });

    setup() {
        this.pos = usePos();
        this.state = proxy({
            loading: true,
            floorId: null,
            selected: [], // table ids, the first one is the main table
            matches: {}, // table id -> server row {status, reason, free_seats, ...}
            floors: [], // server floors [{id, name, sequence}]
            arrangements: [], // server ranked arrangements, best first
            preferenceRelaxed: false,
            message: "",
            saving: false,
        });
        onWillStart(() => this.refresh());
    }

    get title() {
        const { token, guest_name } = this.props.entry;
        return _t("Choose a table for %(token)s · %(guest)s", { token, guest: guest_name });
    }

    get partySize() {
        return this.props.entry.party_size || 1;
    }

    /**
     * The guest as the live queue sees it now. The queue is refreshed over the bus on every
     * change (POS, back office, guest), so a guest cancelled elsewhere while this picker is
     * open is noticed here at once.
     */
    get liveEntry() {
        return this.pos.waitlist.entries.find((e) => e.id === this.props.entry.id);
    }

    get stillWaiting() {
        return this.liveEntry?.state === "waiting";
    }

    get staleMessage() {
        const live = this.liveEntry;
        return live
            ? _t("%(token)s is now %(state)s on another screen.", {
                  token: live.token,
                  state: live.state,
              })
            : _t("%s is no longer on the waitlist (updated on another screen).", this.props.entry.token);
    }

    get guestNote() {
        return (this.liveEntry || this.props.entry).guest_note || "";
    }

    get guestTags() {
        return (this.liveEntry || this.props.entry).tags || [];
    }

    get preferredFloorId() {
        return this.props.entry.preferred_floor_id || false;
    }

    /** The preferred floor is honoured only when it can seat the party (server decision). */
    get preferenceHonoured() {
        return Boolean(this.preferredFloorId) && !this.state.preferenceRelaxed;
    }

    get preferredFloorName() {
        return this.props.entry.floor_pref_label || "";
    }

    get floors() {
        // The guest's preferred floor first, then the POS order.
        return [...this.state.floors].sort(
            (a, b) =>
                (b.id === this.preferredFloorId) - (a.id === this.preferredFloorId) ||
                (a.sequence || 0) - (b.sequence || 0) ||
                a.id - b.id
        );
    }

    get currentFloor() {
        return this.floors.find((f) => f.id === this.state.floorId) || this.floors[0];
    }

    isPreferred(floor) {
        return Boolean(this.preferredFloorId) && floor.id === this.preferredFloorId;
    }

    isOtherFloor(floor) {
        return this.preferenceHonoured && floor?.id !== this.preferredFloorId;
    }

    /** Server status, downgraded to "busy" when this terminal has an unsynced order there. */
    status(row) {
        if (!row) {
            return "hidden";
        }
        if (
            (row.status === "match" || row.status === "too_small") &&
            this.pos.waitlistTableHasLocalOrder({ id: row.id })
        ) {
            return "busy";
        }
        return row.status;
    }

    reason(row) {
        if (this.status(row) === "busy" && row.status !== "busy") {
            return _t("Table %s has an open order on this terminal.", row.table_number);
        }
        return row.reason || "";
    }

    /** Seats the whole party on its own. */
    isSelectable(row) {
        return SELECTABLE.includes(this.status(row));
    }

    isCombinable(row) {
        return COMBINABLE.includes(this.status(row)) && Boolean(row.seats);
    }

    /** May be tapped: alone, or as part of a combination. */
    isPickable(row) {
        return this.isSelectable(row) || this.isCombinable(row);
    }

    /** Seats a guest takes at this table now (free seats of a shared table). */
    availableSeats(row) {
        return this.status(row) === "shared" ? row.free_seats : row.seats;
    }

    isSelected(row) {
        return this.state.selected.includes(row.id);
    }

    /** Every table of the floor, best first (server rank). */
    tablesOf(floor) {
        if (!floor) {
            return [];
        }
        return Object.values(this.state.matches)
            .filter((row) => row.floor_id === floor.id)
            .sort((a, b) => this.isSelectable(b) - this.isSelectable(a) || a.rank - b.rank);
    }

    availableTables(floor) {
        return this.tablesOf(floor).filter((row) => this.isPickable(row));
    }

    availableCount(floor) {
        return this.availableTables(floor).length;
    }

    suitableCount(floor) {
        return this.tablesOf(floor).filter((r) => ["match", "shared"].includes(this.status(r))).length;
    }

    get selectedRows() {
        return this.state.selected.map((id) => this.state.matches[id]).filter(Boolean);
    }

    /** Seats of the selection; 0 when a table has no seat count (treated as big enough). */
    get selectedSeats() {
        const rows = this.selectedRows;
        if (rows.some((r) => !r.seats)) {
            return 0;
        }
        return rows.reduce((sum, r) => sum + this.availableSeats(r), 0);
    }

    /** The selection seats the whole party: one suitable table, or free tables that add up. */
    get selectionFits() {
        const rows = this.selectedRows;
        if (rows.length === 1) {
            return this.isSelectable(rows[0]);
        }
        return (
            rows.length > 1 &&
            rows.every((r) => this.isCombinable(r) && r.floor_id === rows[0].floor_id) &&
            (!this.selectedSeats || this.selectedSeats >= this.partySize)
        );
    }

    get canConfirm() {
        return this.selectionFits && !this.state.saving && this.stillWaiting;
    }

    get selectionLabel() {
        const rows = this.selectedRows;
        if (!rows.length) {
            return "";
        }
        const numbers = rows.map((r) => r.table_number).join(" + ");
        const label = rows.length > 1 ? _t("Tables %s", numbers) : _t("Table %s", numbers);
        return this.selectedSeats
            ? _t("%(tables)s · %(seats)s seats for %(party)s guests", {
                  tables: label,
                  seats: this.selectedSeats,
                  party: this.partySize,
              })
            : label;
    }

    /** Server-ranked arrangements, still valid on this terminal (no unsynced local order). */
    get arrangements() {
        return this.state.arrangements.filter((a) => {
            const rows = a.table_ids.map((id) => this.state.matches[id] || null);
            return rows.length === 1
                ? this.isSelectable(rows[0])
                : rows.every((row) => this.isCombinable(row));
        });
    }

    isArrangementSelected(arrangement) {
        const selected = this.state.selected;
        return (
            selected.length === arrangement.table_ids.length &&
            arrangement.table_ids.every((id) => selected.includes(id))
        );
    }

    arrangementTitle(arrangement) {
        const numbers = arrangement.table_numbers.join(" + ");
        return arrangement.table_ids.length > 1 ? _t("Tables %s", numbers) : _t("Table %s", numbers);
    }

    /** Why it suits the guest: occupancy / available seats per table and the total. */
    arrangementDetail(arrangement) {
        if (arrangement.table_ids.length > 1) {
            return _t("%(parts)s available · Total: %(total)s available", {
                parts: arrangement.available.join(" + "),
                total: arrangement.seats,
            });
        }
        if (!arrangement.capacity[0]) {
            return _t("Seats not set");
        }
        if (arrangement.shared) {
            return _t("%(occupied)s / %(seats)s occupied · %(free)s seats available", {
                occupied: arrangement.occupied[0],
                seats: arrangement.capacity[0],
                free: arrangement.available[0],
            });
        }
        return _t("%s seats available", arrangement.available[0]);
    }

    arrangementFit(arrangement) {
        if (!arrangement.seats) {
            return "";
        }
        return arrangement.spare ? _t("%s spare", arrangement.spare) : _t("Exact fit");
    }

    /** Seats line of a table tile: capacity, or occupied / capacity. */
    tableSeatsLabel(row) {
        if (!row.seats) {
            return "";
        }
        if (row.occupied) {
            return _t("%(occupied)s / %(seats)s occupied", { occupied: row.occupied, seats: row.seats });
        }
        return _t("%s seats", row.seats);
    }

    _applyTables(data) {
        const matches = {};
        (data?.tables || []).forEach((row, index) => {
            matches[row.id] = { ...row, rank: index };
        });
        this.state.matches = matches;
        this.state.floors = data?.floors || [];
        this.state.arrangements = data?.arrangements || [];
        this.state.preferenceRelaxed = Boolean(data?.preference_relaxed);
        // Drop selected tables that are gone or can no longer be picked.
        this.state.selected = this.state.selected.filter((id) => this.isPickable(matches[id]));
    }

    async refresh() {
        this.state.loading = true;
        try {
            this._applyTables(await this.pos.loadSeatableTables(this.props.entry));
        } catch {
            this.state.message = _t("Could not load table availability. Check the connection.");
        } finally {
            this.state.loading = false;
        }
        this._pickDefaultFloor();
    }

    _pickDefaultFloor() {
        if (this.state.floorId && this.availableCount(this.currentFloor)) {
            return;
        }
        const preferred = this.preferenceHonoured && this.floors.find((f) => this.isPreferred(f));
        const top = this.arrangements[0];
        const best =
            preferred ||
            (top && this.floors.find((f) => f.id === top.floor_id)) ||
            this.floors.find((f) => this.suitableCount(f)) ||
            this.floors.find((f) => this.availableCount(f));
        this.state.floorId = (best || this.floors[0])?.id || null;
    }

    selectFloor(floor) {
        this.state.floorId = floor.id;
        // A combination never spans floors.
        if (this.selectedRows.some((r) => r.floor_id !== floor.id)) {
            this.state.selected = [];
        }
    }

    /**
     * Tap a table: select it, or unselect it. While the current selection is too small for
     * the party, tapping another free table of the same floor adds it (combined tables);
     * otherwise the tap replaces the selection, as with a single table. A too-small table
     * starts a combination: Seat stays disabled until the selection holds the whole party.
     */
    selectTable(row) {
        if (!this.isPickable(row)) {
            this.state.message = this.reason(row);
            return;
        }
        this.state.message = "";
        if (this.isSelected(row)) {
            this.state.selected = this.state.selected.filter((id) => id !== row.id);
            return;
        }
        const current = this.selectedRows;
        const canAdd =
            current.length &&
            !this.selectionFits &&
            this.isCombinable(row) &&
            current.every((r) => this.isCombinable(r) && r.floor_id === row.floor_id);
        this.state.selected = canAdd ? [...this.state.selected, row.id] : [row.id];
    }

    selectArrangement(arrangement) {
        this.state.floorId = arrangement.floor_id;
        this.state.selected = [...arrangement.table_ids];
        this.state.message = "";
    }

    clearSelection() {
        this.state.selected = [];
    }

    async confirm(openOrder) {
        const rows = this.selectedRows;
        if (!rows.length || this.state.saving || !this.stillWaiting) {
            return;
        }
        const unavailable = rows.find((r) => (rows.length > 1 ? !this.isCombinable(r) : !this.isSelectable(r)));
        if (unavailable) {
            this.state.message = _t("Table %s is no longer available. Choose another table.", unavailable.table_number);
            this.state.selected = [];
            return;
        }
        if (!this.selectionFits) {
            this.state.message = _t("Not enough seats for a party of %s: add another free table.", this.partySize);
            return;
        }
        this.state.saving = true;
        let result;
        try {
            result = await this.pos.seatWaitlistGuest(
                this.props.entry,
                rows.map((r) => r.id)
            );
        } catch (error) {
            this.state.message =
                error?.data?.message || _t("The guest could not be seated. Check the connection and try again.");
            await this.refresh();
            return;
        } finally {
            this.state.saving = false;
        }
        if (result.ok) {
            // A guest at a shared table always gets their own order now: opening the table
            // later from the floor plan would show the other party's order.
            const open = openOrder || result.shared;
            this.props.close();
            this.props.onSeated({ openOrder: open, tableId: result.table_id, tableIds: result.table_ids });
            if (open) {
                await this.pos.openWaitlistTable(
                    result.table_id,
                    this.props.entry.party_size,
                    result.shared,
                    this.props.entry.partner_id,
                    result.order_uuid
                );
            }
            return;
        }
        if (result.state !== "waiting") {
            // Someone else already seated / cancelled this guest: nothing left to pick.
            this.props.close();
            return;
        }
        this.state.message = result.message;
        this.state.selected = [];
        this._applyTables(result.tables);
    }
}
