/** @odoo-module **/

import { KanbanController } from "@web/views/kanban/kanban_controller";
import { ListController } from "@web/views/list/list_controller";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanRecord } from "@web/views/kanban/kanban_record";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { listView } from "@web/views/list/list_view";
import { Component } from "@odoo/owl";

function triggerDirectUpload(orm, action, fromTemplates = false) {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "application/pdf";
    input.style.display = "none";
    document.body.appendChild(input);
    
    input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) {
            document.body.removeChild(input);
            return;
        }
        
        const reader = new FileReader();
        reader.onload = async (event) => {
            let base64 = event.target.result;
            // Remove data url prefix
            if (base64.indexOf("base64,") !== -1) {
                base64 = base64.split("base64,")[1];
            }
            try {
                const res = await orm.call("hudson.sign.template", "create_template_from_file", [file.name, base64], {
                    from_templates: fromTemplates,
                });
                if (res) {
                    action.doAction(res);
                }
            } catch (err) {
                console.error("Upload failed", err);
            }
            document.body.removeChild(input);
        };
        reader.readAsDataURL(file);
    };
    
    input.click();
}

// Extension for Kanban
export class HudsonSignTemplateKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.action = useService("action");
        this.orm = useService("orm");
    }

    async uploadPdf() {
        triggerDirectUpload(this.orm, this.action, this.props.resModel === "hudson.sign.template");
    }
}

// Archive / Restore from the card menu: Odoo only reloads the card itself, so an
// archived template stayed in the list until the page was refreshed
export class HudsonSignTemplateKanbanRecord extends KanbanRecord {
    async archiveRecord(record, active) {
        const reloadList = () => record.model.root.load();
        if (active) {
            this.dialog.add(ConfirmationDialog, {
                body: _t("Are you sure that you want to archive this record?"),
                confirmLabel: _t("Archive"),
                confirm: async () => {
                    await record.archive();
                    await reloadList();
                },
                cancel: () => {},
            });
        } else {
            await record.unarchive();
            await reloadList();
        }
    }
}

export class HudsonSignTemplateKanbanRenderer extends KanbanRenderer {
    static components = { ...KanbanRenderer.components, KanbanRecord: HudsonSignTemplateKanbanRecord };
}

export const hudsonSignTemplateKanbanView = {
    ...kanbanView,
    Controller: HudsonSignTemplateKanbanController,
    Renderer: HudsonSignTemplateKanbanRenderer,
    buttonTemplate: "hudson_sign.KanbanButtons",
};

registry.category("views").add("hudson_sign_template_kanban", hudsonSignTemplateKanbanView);

// Extension for List
export class HudsonSignTemplateListController extends ListController {
    setup() {
        super.setup();
        this.action = useService("action");
        this.orm = useService("orm");
    }

    async uploadPdf() {
        triggerDirectUpload(this.orm, this.action, this.props.resModel === "hudson.sign.template");
    }
}

export const hudsonSignTemplateListView = {
    ...listView,
    Controller: HudsonSignTemplateListController,
    buttonTemplate: "hudson_sign.ListButtons",
};

registry.category("views").add("hudson_sign_template_list", hudsonSignTemplateListView);
