import { onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";

// Sent by pos.waitlist.entry._notify_backend on the POS User group channel whenever an
// entry is created, changes (state, table, ...) or is deleted, from the POS, a guest's
// phone or another backend tab. The record on the server stays the only source of truth:
// the views simply re-read it.
const EVENT = "hudson_waitlist_changed";

/** Re-read the view when the waitlist changes elsewhere. */
function useWaitlistLiveReload(onChange) {
    const bus = useService("bus_service");
    const run = debounce((payload) => onChange(payload || {}), 300);
    const unsubscribe = bus.subscribe(EVENT, (payload) => run(payload));
    onWillUnmount(() => {
        unsubscribe?.();
        run.cancel?.();
    });
}

export class WaitlistListController extends ListController {
    setup() {
        super.setup();
        useWaitlistLiveReload(() => this.model.load());
    }
}

export class WaitlistFormController extends FormController {
    setup() {
        super.setup();
        this.notification = useService("notification");
        useWaitlistLiveReload(async ({ entry_ids = [] }) => {
            const record = this.model.root;
            if (!record?.resId || !entry_ids.includes(record.resId)) {
                return;
            }
            if (await record.isDirty()) {
                // Never throw away what the user is typing.
                this.notification.add(
                    _t("This waitlist entry was updated on another screen. Save or discard to see the latest status."),
                    { type: "warning" }
                );
                return;
            }
            try {
                await this.model.load();
            } catch {
                // Deleted elsewhere: nothing left to show, keep the form as it is.
            }
        });
    }
}

registry.category("views").add("hudson_waitlist_list", {
    ...listView,
    Controller: WaitlistListController,
});

registry.category("views").add("hudson_waitlist_form", {
    ...formView,
    Controller: WaitlistFormController,
});
