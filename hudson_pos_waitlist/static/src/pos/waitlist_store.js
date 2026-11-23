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
     * Server matching of the POS tables against one guest (party size, availability, floor,
     * sharing, hints): {available_ids, busy, tables: [{id, status, reason, ...}], floors,
     * combinations, preferred_floor_id, preference_relaxed}. Floors and tables are the
     * server's current ones, not the ones loaded when this POS session opened.
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
     * Seat a waiting guest at one existing table, or at several tables combined for a large
     * party (Waiting -> Seated). The server re-checks the entry and every table under a lock;
     * on refusal the result carries fresh availability to pick again.
     */
    async seatWaitlistGuest(entry, tableIds) {
        const ids = (Array.isArray(tableIds) ? tableIds : [tableIds]).filter(Boolean);
        this.waitlist.busy[entry.id] = true;
        try {
            const result = await this.data.call(WAITLIST_MODEL, "pos_seat_guest", [
                this.config.id,
                entry.id,
                entry.state,
                ids.length > 1 ? ids : ids[0] || false,
            ]);
            this._applyWaitlistQueue(result.queue);
            if (result.ok && result.merged_tables?.length) {
                await this.applyWaitlistTableMerge(result.merged_tables);
            }
            this.notification.add(result.message, { type: result.ok ? "success" : "warning" });
            return result;
        } finally {
            delete this.waitlist.busy[entry.id];
        }
    },

    /**
     * The server already merged the extra tables under the main one. Replay it through the
     * floor plan's own merge call so this terminal's floor plan (and the other devices, via
     * the standard device sync) show one combined table, released when its order is paid.
     */
    async applyWaitlistTableMerge(merges) {
        for (const merge of merges) {
            try {
                await this.data.callRelated("restaurant.table", "set_parent_id", [merge.id], {
                    parent_id: merge.parent_id,
                    parent_side: merge.parent_side,
                    config_id: this.config.id,
                });
            } catch (error) {
                console.warn("Waitlist: could not refresh merged table", merge.id, error);
            }
        }
    },

    /** The guest's res.partner (created / reused at QR join), loaded on demand. */
    async getWaitlistPartner(partnerId) {
        if (!partnerId) {
            return null;
        }
        const known = this.models["res.partner"]?.get(partnerId);
        if (known) {
            return known;
        }
        try {
            const found = await this.data.searchRead("res.partner", [["id", "=", partnerId]]);
            return found?.[0] || null;
        } catch {
            return null; // offline / no access: the order simply opens without a customer
        }
    },

    /**
     * Continue with the normal restaurant flow: open the table exactly as tapping it on the
     * floor plan does (setTableFromUi), so ordering, kitchen, payment are the standard ones.
     *
     * Free table: the guest's own order is created up front the same way setTable would
     * (addNewOrder with the table) carrying the party size, and flagged as "guests set" so the
     * standard guest-count popup does not overwrite the waitlist party size.
     * Shared table: the guest gets their OWN new order on the same table (never the other
     * party's order): separate bills, each paid on its own; the table stays taken until every
     * order on it is paid. The other orders of the table stay reachable from the order list.
     * Combined tables: the main table's order serves the whole party (the others are merged).
     * ``orderUuid`` is issued by the server when seating: it keeps this order separate on sync.
     * The waitlist customer is set on the guest's own order.
     */
    async openWaitlistTable(tableId, partySize, shared = false, partnerId = false, orderUuid = false) {
        let table = this.models["restaurant.table"]?.get(tableId);
        if (!table) {
            return;
        }
        if (table.parent_id) {
            table = table.getParent();
        }
        const openOrders = this.getTableOrders(table.id).filter((o) => !o.finalized);
        if ((!openOrders.length || shared) && partySize) {
            const data = { table_id: table };
            if (orderUuid && !this.models["pos.order"].getBy("uuid", orderUuid)) {
                data.uuid = orderUuid;
            }
            const order = this.addNewOrder(data);
            order.setCustomerCount(partySize);
            order.uiState.guestSetted = true;
            const partner = await this.getWaitlistPartner(partnerId);
            if (partner) {
                order.setPartner(partner);
            }
            if (shared) {
                // setTableFromUi would select the table's first order (the other party's).
                await this.setTable(table, order.uuid);
                this.setOrder(order);
                this.navigate("ProductScreen", { orderUuid: order.uuid });
                return;
            }
            await this.setTableFromUi(table, order.uuid);
            return;
        }
        await this.setTableFromUi(table);
        const order = this.getOrder();
        if (order && order.table_id?.id === table.id && !order.finalized && partySize) {
            order.setCustomerCount(partySize);
            order.uiState.guestSetted = true;
        }
    },
});
