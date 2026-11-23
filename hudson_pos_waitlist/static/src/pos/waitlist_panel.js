import { Component, proxy, t, useProps, onMounted, onWillUnmount } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { WaitlistTablePicker } from "./waitlist_table_picker";

// Label, button style and whether the host must confirm, per target state.
const ACTIONS = {
    seated: { label: _t("Seat Guest"), icon: "check", cls: "btn-success" },
    no_show: { label: _t("Mark No Show"), icon: "person", cls: "btn-outline-danger", confirm: true },
    left: { label: _t("Mark Left"), icon: "person", cls: "btn-outline-secondary", confirm: true },
    cancelled: { label: _t("Cancel"), icon: "close", cls: "btn-outline-danger", confirm: true },
};

/** Live Waitlist panel opened from the POS top bar. Never leaves the current screen. */
export class WaitlistPanel extends Component {
    static template = "hudson_pos_waitlist.WaitlistPanel";
    static components = { Dialog };
    props = useProps({ close: t.function() });

    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
        // Re-render "waited" times every 30s.
        this.clock = proxy({ tick: 0 });
        onMounted(() => {
            this.pos.loadWaitlist();
            this.interval = setInterval(() => this.clock.tick++, 30000);
        });
        onWillUnmount(() => clearInterval(this.interval));
    }

    get entries() {
        return this.pos.waitlist.entries;
    }

    get waitingCount() {
        return this.entries.filter((e) => e.state === "waiting").length;
    }

    actionsFor(entry) {
        return (entry.allowed_states || [])
            .filter((state) => ACTIONS[state])
            .map((state) => ({ state, ...ACTIONS[state], label: String(ACTIONS[state].label) }));
    }

    waited(entry) {
        this.clock.tick; // dependency for the 30s refresh
        return this.formatMinutes(this.pos.waitlistWaitedMinutes(entry));
    }

    formatMinutes(minutes) {
        if (minutes < 1) {
            return _t("< 1 min");
        }
        if (minutes < 60) {
            return _t("%s min", minutes);
        }
        const h = Math.floor(minutes / 60);
        const m = minutes % 60;
        return m ? _t("%(h)sh %(m)sm", { h, m }) : _t("%sh", h);
    }

    isBusy(entry) {
        return Boolean(this.pos.waitlist.busy[entry.id]);
    }

    async onAction(entry, action) {
        if (action.state === "seated" && this.pos.config.floor_ids?.length) {
            // Seat Guest -> pick an existing POS table -> confirm -> seated.
            this.dialog.add(WaitlistTablePicker, {
                entry,
                onSeated: ({ openOrder }) => {
                    if (openOrder) {
                        this.props.close(); // leave the panel for the table's order
                    }
                },
            });
            return;
        }
        if (action.confirm) {
            const confirmed = await new Promise((resolve) => {
                this.dialog.add(
                    ConfirmationDialog,
                    {
                        title: _t("%(action)s - %(token)s", { action: action.label, token: entry.token }),
                        body: _t("%(action)s for %(guest)s (party of %(size)s)?", {
                            action: action.label,
                            guest: entry.guest_name,
                            size: entry.party_size,
                        }),
                        confirmLabel: String(action.label),
                        confirm: () => resolve(true),
                        cancel: () => resolve(false),
                    },
                    { onClose: () => resolve(false) }
                );
            });
            if (!confirmed) {
                return;
            }
        }
        await this.pos.changeWaitlistState(entry, action.state);
    }

    refresh() {
        this.pos.loadWaitlist();
    }
}
