import { Component, proxy, t, useProps, onWillStart } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { _t } from "@web/core/l10n/translation";

// Server statuses (pos.waitlist.entry._match_tables). Only these may be picked.
const SELECTABLE = ["match", "shared", "too_small"];

/**
 * Pick an existing POS table for a waiting guest (Waiting -> Seated). The host always chooses.
 *
 * Uses the floors / tables already loaded in the POS (restaurant.floor / restaurant.table).
 * Each table is rated by the server against the guest (preferred floor, party size,
 * table sharing, open orders and waitlist holds): suitable tables come first, too-small
 * and shared ones are marked, occupied tables and tables on another floor than the guest
 * asked for are shown but cannot be picked. A table with an unsynced open order on this
 * terminal is treated as occupied too.
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
            tableId: null,
            matches: {}, // table id -> server row {status, reason, free_seats, ...}
            message: "",
            saving: false,
        });
        onWillStart(() => this.refresh());
    }

    get title() {
        const { token, guest_name } = this.props.entry;
        return _t("Choose a table for %(token)s · %(guest)s", { token, guest: guest_name });
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

    get preferredFloorId() {
        return this.props.entry.preferred_floor_id || false;
    }

    get floors() {
        const floors =
            this.pos.config.floor_ids || this.pos.models["restaurant.floor"]?.getAll?.() || [];
        // The guest's preferred floor first, then the POS order.
        return [...floors].sort(
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
        return Boolean(this.preferredFloorId) && floor.id !== this.preferredFloorId;
    }

    /** Server status, downgraded to "busy" when this terminal has an unsynced order there. */
    status(table) {
        const row = this.state.matches[table.id];
        if (!row || table.active === false || table.parent_id) {
            return "hidden";
        }
        if (
            (row.status === "match" || row.status === "too_small") &&
            this.pos.waitlistTableHasLocalOrder(table)
        ) {
            return "busy";
        }
        return row.status;
    }

    reason(table) {
        if (this.status(table) === "busy" && this.state.matches[table.id]?.status !== "busy") {
            return _t("Table %s has an open order on this terminal.", table.table_number);
        }
        return this.state.matches[table.id]?.reason || "";
    }

    isSelectable(table) {
        return SELECTABLE.includes(this.status(table));
    }

    /** Every table of the floor, suitable first (server rank), then the rest. */
    tablesOf(floor) {
        if (!floor) {
            return [];
        }
        const rank = (table) => this.state.matches[table.id]?.rank ?? 9999;
        return (floor.table_ids || [])
            .filter((table) => this.status(table) !== "hidden")
            .sort((a, b) => this.isSelectable(b) - this.isSelectable(a) || rank(a) - rank(b));
    }

    availableTables(floor) {
        return this.tablesOf(floor).filter((table) => this.isSelectable(table));
    }

    availableCount(floor) {
        return this.availableTables(floor).length;
    }

    suitableCount(floor) {
        return this.tablesOf(floor).filter((t) => ["match", "shared"].includes(this.status(t))).length;
    }

    get selectedTable() {
        return this.pos.models["restaurant.table"]?.get(this.state.tableId);
    }

    tooSmall(table) {
        return this.status(table) === "too_small";
    }

    _applyTables(tables) {
        const matches = {};
        (tables?.tables || []).forEach((row, index) => {
            matches[row.id] = { ...row, rank: index };
        });
        this.state.matches = matches;
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
        if (this.state.tableId && !this.isSelectable(this.selectedTable || {})) {
            this.state.tableId = null;
        }
    }

    _pickDefaultFloor() {
        if (this.state.floorId && this.availableCount(this.currentFloor)) {
            return;
        }
        const preferred = this.floors.find((f) => this.isPreferred(f));
        const best =
            preferred ||
            this.floors.find((f) => this.suitableCount(f)) ||
            this.floors.find((f) => this.availableCount(f));
        this.state.floorId = (best || this.floors[0])?.id || null;
    }

    selectFloor(floor) {
        this.state.floorId = floor.id;
        this.state.tableId = null;
    }

    selectTable(table) {
        if (!this.isSelectable(table)) {
            this.state.message = this.reason(table);
            return;
        }
        this.state.tableId = table.id;
        this.state.message = "";
    }

    async confirm(openOrder) {
        const table = this.selectedTable;
        if (!table || this.state.saving || !this.stillWaiting) {
            return;
        }
        if (!this.isSelectable(table)) {
            this.state.message = _t("Table %s is no longer available. Choose another table.", table.table_number);
            this.state.tableId = null;
            return;
        }
        this.state.saving = true;
        let result;
        try {
            result = await this.pos.seatWaitlistGuest(this.props.entry, table.id);
        } catch (error) {
            this.state.message =
                error?.data?.message || _t("The guest could not be seated. Check the connection and try again.");
            await this.refresh();
            return;
        } finally {
            this.state.saving = false;
        }
        if (result.ok) {
            this.props.close();
            this.props.onSeated({ openOrder, tableId: result.table_id });
            if (openOrder) {
                await this.pos.openWaitlistTable(
                    result.table_id,
                    this.props.entry.party_size,
                    result.shared
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
        this._applyTables(result.tables);
        this.state.tableId = null;
    }
}
