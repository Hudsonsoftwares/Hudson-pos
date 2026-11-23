import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { debounce } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

const WAITLIST_MODEL = "pos.waitlist.entry";
// Bus events sent by pos.waitlist.entry._notify_pos on this POS config's channel.
const WAITLIST_EVENTS = ["waitlist_created", "waitlist_updated"];
// Safety net if a bus message is ever missed (e.g. websocket reconnect).
const FALLBACK_REFRESH_MS = 60000;

function parseServerDatetime(value) {
    // Odoo sends naive UTC "YYYY-MM-DD HH:MM:SS".
    return value ? new Date(value.replace(" ", "T") + "Z").getTime() : 0;
}

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.waitlist = {
            enabled: false,
            loaded: false,
            entries: [],
            clockOffset: 0, // server time - terminal time, in ms
            busy: {}, // entry id -> true while a host action is in flight
        };
        this._waitlistReloadDebounced = debounce(() => this.loadWaitlist(), 250);
        for (const event of WAITLIST_EVENTS) {
            this.data.connectWebSocket(event, () => this._waitlistReloadDebounced());
        }
        this._waitlistTimer = setInterval(() => this.loadWaitlist(), FALLBACK_REFRESH_MS);
        // Never block the POS from opening on the waitlist.
        this.loadWaitlist();
    },

    get waitlistCount() {
        return this.waitlist?.entries.length || 0;
    },

    get showWaitlistButton() {
        return Boolean(this.waitlist && (this.waitlist.enabled || this.waitlistCount));
    },

    waitlistNow() {
        return Date.now() + (this.waitlist?.clockOffset || 0);
    },

    waitlistWaitedMinutes(entry) {
        const joined = parseServerDatetime(entry.join_time);
        return joined ? Math.max(0, Math.floor((this.waitlistNow() - joined) / 60000)) : 0;
    },

    _applyWaitlistQueue(queue) {
        if (!queue) {
            return;
        }
        this.waitlist.entries = queue.entries || [];
        this.waitlist.enabled = Boolean(queue.enabled);
        if (queue.server_time) {
            this.waitlist.clockOffset = parseServerDatetime(queue.server_time) - Date.now();
        }
        this.waitlist.loaded = true;
    },

    async loadWaitlist() {
        if (!this.config?.id) {
            return;
        }
        try {
            const queue = await this.data.call(WAITLIST_MODEL, "get_pos_queue", [this.config.id]);
            this._applyWaitlistQueue(queue);
        } catch (error) {
            // Offline or no access: keep the last known queue.
            console.warn("Waitlist: could not load the queue", error);
        }
    },

    /**
     * Host action. The server validates the transition and locks the row; when another
     * terminal got there first it answers ok=false with the latest queue.
     */
    async changeWaitlistState(entry, newState) {
        if (this.waitlist.busy[entry.id]) {
            return false;
        }
        this.waitlist.busy[entry.id] = true;
        try {
            const result = await this.data.call(WAITLIST_MODEL, "pos_change_state", [
                this.config.id,
                entry.id,
                entry.state,
                newState,
            ]);
            this._applyWaitlistQueue(result.queue);
            this.notification.add(result.message, { type: result.ok ? "success" : "warning" });
            return result.ok;
        } catch (error) {
            this.dialog.add(AlertDialog, {
                title: _t("Waitlist"),
                body:
                    error?.data?.message ||
                    _t("The waitlist could not be updated. Check the connection and try again."),
            });
            await this.loadWaitlist();
            return false;
        } finally {
            delete this.waitlist.busy[entry.id];
        }
    },

    /**
     * Server matching of the POS tables against one guest (floor, party size, sharing,
     * availability): {available_ids, busy, tables: [{id, status, reason, ...}], preferred_floor_id}.
     */
    async loadSeatableTables(entry = null) {
        return await this.data.call(WAITLIST_MODEL, "get_seatable_tables", [
            this.config.id,
            entry?.id || false,
        ]);
    },

    /** Same rule the floor plan uses: a table with an open order on this terminal is taken. */
    waitlistTableHasLocalOrder(table) {
        try {
            return this.getTableOrders(table.id).some((order) => !order.finalized);
        } catch {
            return false;
        }
    },

    /**
     * Seat a waiting guest at an existing table (Waiting -> Seated). The server re-checks the entry and the
     * table under a lock; on refusal the result carries fresh availability to pick again.
     */
    async seatWaitlistGuest(entry, tableId) {
        this.waitlist.busy[entry.id] = true;
        try {
            const result = await this.data.call(WAITLIST_MODEL, "pos_seat_guest", [
                this.config.id,
                entry.id,
                entry.state,
                tableId || false,
            ]);
            this._applyWaitlistQueue(result.queue);
            this.notification.add(result.message, { type: result.ok ? "success" : "warning" });
            return result;
        } finally {
            delete this.waitlist.busy[entry.id];
        }
    },

    /**
     * Continue with the normal restaurant flow: open the table exactly as tapping it on the
     * floor plan does (setTableFromUi), so ordering, kitchen, payment are the standard ones.
     *
     * Free table: its order is created up front the same way setTable would (addNewOrder
     * with the table) carrying the party size, and flagged as "guests set" so the standard
     * guest-count popup does not overwrite the waitlist party size.
     * Shared table: the table's existing order opens and the party is added to its guests.
     */
    async openWaitlistTable(tableId, partySize, shared = false) {
        let table = this.models["restaurant.table"]?.get(tableId);
        if (!table) {
            return;
        }
        if (table.parent_id) {
            table = table.getParent();
        }
        const openOrders = this.getTableOrders(table.id).filter((o) => !o.finalized);
        if (!openOrders.length && partySize) {
            const order = this.addNewOrder({ table_id: table });
            order.setCustomerCount(partySize);
            order.uiState.guestSetted = true;
            await this.setTableFromUi(table, order.uuid);
            return;
        }
        await this.setTableFromUi(table);
        const order = this.getOrder();
        if (order && order.table_id?.id === table.id && !order.finalized && partySize) {
            const base = shared ? order.customer_count || 0 : 0;
            order.setCustomerCount(base + partySize);
            order.uiState.guestSetted = true;
        }
    },
});
