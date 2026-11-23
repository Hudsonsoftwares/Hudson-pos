/** @odoo-module **/
import { onWillUnmount } from "@odoo/owl";
import { rpcBus } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";
import { setKitchenTerms } from "@hudson_kitchen_terms/js/kitchen_terms";

/**
 * Menus and client-side terms are loaded once per page load. After a Kitchen
 * Label is created/edited/archived/deleted, refresh them so the Manufacturing
 * menus show the new label immediately, without a manual browser refresh.
 */
function useKitchenTermsRefresh() {
    const menu = useService("menu");
    const orm = useService("orm");
    let dirty = false;
    const refresh = async () => {
        dirty = false;
        const terms = await orm.call("kitchen.label", "get_terms_dict", []);
        setKitchenTerms(terms);
        // Views (field/tab labels) are kept in the browser RPC cache; drop it
        // so Manufacturing screens are re-fetched with the new labels.
        rpcBus.trigger("CLEAR-CACHES");
        await menu.reload();
    };
    // Covers deletes/archives done from the action menu: refresh on leaving.
    onWillUnmount(() => {
        if (dirty) {
            refresh();
        }
    });
    return {
        markDirty() {
            dirty = true;
        },
        refresh,
    };
}

export class KitchenLabelListController extends ListController {
    setup() {
        super.setup();
        this.kitchenTerms = useKitchenTermsRefresh();
        this.kitchenTerms.markDirty();
    }
    async onRecordSaved(record) {
        await super.onRecordSaved(...arguments);
        await this.kitchenTerms.refresh();
        this.kitchenTerms.markDirty();
    }
}

export class KitchenLabelFormController extends FormController {
    setup() {
        super.setup();
        this.kitchenTerms = useKitchenTermsRefresh();
        this.kitchenTerms.markDirty();
    }
    async onRecordSaved(record, changes) {
        await super.onRecordSaved(...arguments);
        await this.kitchenTerms.refresh();
        this.kitchenTerms.markDirty();
    }
}

registry.category("views").add("kitchen_label_list", {
    ...listView,
    Controller: KitchenLabelListController,
});
registry.category("views").add("kitchen_label_form", {
    ...formView,
    Controller: KitchenLabelFormController,
});
