// /** ********************************************************************************
//     Copyright 2020 Creu Blanca
//     License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
//  **********************************************************************************/
import {FileKanbanRecord} from "./file_kanban_record.esm";
import {KanbanRenderer} from "@web/views/kanban/kanban_renderer";
import {useService} from "@web/core/utils/hooks";

export class FileKanbanRenderer extends KanbanRenderer {
    setup() {
        super.setup();
        this.notification = useService("notification");
        this.actionService = useService("action");
    }

    clearSelection() {
        if (this.props.list && this.props.list.selection) {
            this.props.list.selection.forEach((r) => r.toggleSelection(false));
        }
    }

    async onDmsAction(actionName) {
        const selectedRecords = this.props.list ? this.props.list.selection : [];
        const resIds = selectedRecords.map((r) => r.resId);

        if (actionName === "download") {
            if (resIds.length === 1) {
                window.location = `/web/content/dms.file/${resIds[0]}/content?download=true`;
            } else if (resIds.length > 1) {
                window.location = `/dms/download/files?ids=${resIds.join(",")}`;
            }
            return;
        }

        if (actionName === "trash") {
            if (resIds.length) {
                await this.env.model.orm.unlink("dms.file", resIds);
                await this.props.list.load();
            }
            return;
        }

        this.notification.add(
            `Action '${actionName}' selected for ${resIds.length} document(s).`,
            { type: "info" }
        );
    }
}

FileKanbanRenderer.components = {
    ...KanbanRenderer.components,
    KanbanRecord: FileKanbanRecord,
};
