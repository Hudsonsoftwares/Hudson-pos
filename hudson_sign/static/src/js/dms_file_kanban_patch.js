/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FileKanbanController } from "@dms/js/views/file_kanban_controller.esm";

// "Sign" in the Documents app opens the Sign template editor (dms.file.action_setup_signatures)
patch(FileKanbanController.prototype, {
    get hasSignFeature() {
        return true;
    },
});
