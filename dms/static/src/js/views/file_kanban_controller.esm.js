// /** ********************************************************************************
//     Copyright 2020 Creu Blanca
//     Copyright 2017-2019 MuK IT GmbH
//     License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
//  **********************************************************************************/

import {KanbanController} from "@web/views/kanban/kanban_controller";
import {useService} from "@web/core/utils/hooks";

export class FileKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.actionService = useService("action");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.ui = useService("ui");
    }

    get isSmall() {
        return this.ui.isSmall;
    }

    /** Signing is provided by the Sign app, which enables this. */
    get hasSignFeature() {
        return false;
    }

    get isSignVisible() {
        if (!this.hasSignFeature) return false;
        const selected = this.model.root.selection;
        if (!selected || selected.length !== 1) return false;
        return selected.every((r) => {
            const isLocked = r.data.is_locked && !r.data.is_lock_editor;
            const hasWrite = r.data.permission_write;
            if (isLocked || !hasWrite) return false;

            const mimetype = r.data.mimetype || "";
            const name = (r.data.name || "").toLowerCase();
            const isImage = mimetype.startsWith("image/") || /\.(png|jpe?g|gif|webp|svg|bmp|ico|tiff?)$/i.test(name);
            const isPdf = mimetype === "application/pdf" || name.endsWith(".pdf");
            return isPdf && !isImage;
        });
    }

    get isShareVisible() {
        const selected = this.model.root.selection;
        if (!selected || !selected.length) return false;
        return selected.every((r) => {
            const isLocked = r.data.is_locked && !r.data.is_lock_editor;
            const canShare = r.data.permission_share !== false;
            return !isLocked && canShare;
        });
    }

    get isDownloadVisible() {
        const selected = this.model.root.selection;
        if (!selected || !selected.length) return false;
        return selected.every((r) => r.data.permission_download !== false);
    }

    get isMoreVisible() {
        const selected = this.model.root.selection;
        if (!selected || !selected.length) return false;
        return selected.every((r) => {
            const isLocked = r.data.is_locked && !r.data.is_lock_editor;
            const hasWrite = r.data.permission_write;
            return !isLocked && hasWrite;
        });
    }

    async onDownload() {
        const selectedIds = this.model.root.selection.map((r) => r.resId);
        if (!selectedIds.length) return;
        if (selectedIds.length === 1) {
            window.location = `/web/content/dms.file/${selectedIds[0]}/content?download=true`;
        } else {
            selectedIds.forEach((id, idx) => {
                setTimeout(() => {
                    const iframe = document.createElement("iframe");
                    iframe.style.display = "none";
                    iframe.src = `/web/content/dms.file/${id}/content?download=true`;
                    document.body.appendChild(iframe);
                    setTimeout(() => iframe.remove(), 5000);
                }, idx * 300);
            });
        }
    }

    async onShare() {
        const selectedIds = this.model.root.selection.map((r) => r.resId);
        if (!selectedIds.length) return;
        return this.actionService.doAction("dms_enterprise_features.action_dms_file_share_wizard", {
            additionalContext: {
                active_ids: selectedIds,
                active_id: selectedIds[0],
                default_file_id: selectedIds[0],
            },
        });
    }

    async onSign() {
        const selectedIds = this.model.root.selection.map((r) => r.resId);
        if (!selectedIds.length) return;
        try {
            const action = await this.orm.call(
                "dms.file",
                "action_setup_signatures",
                [selectedIds]
            );
            if (action) {
                return this.actionService.doAction(action);
            }
        } catch (e) {
            let errorMsg = "Sign action triggered. Note: Document must have a revision.";
            if (e && e.data && e.data.message) {
                errorMsg = e.data.message;
            } else if (e && e.message) {
                errorMsg = e.message;
            }
            this.notification.add(errorMsg, { type: "danger" });
        }
    }

    async onAccountingAction(moveType) {
        const selectedIds = this.model.root.selection.map((r) => r.resId);
        if (!selectedIds.length) return;
        try {
            const action = await this.orm.call(
                "dms.file",
                "action_create_account_move",
                [selectedIds[0], moveType]
            );
            if (action) {
                return this.actionService.doAction(action);
            }
        } catch (e) {
            this.notification.add(e.message || "Failed to create accounting move.", { type: "danger" });
        }
    }

    async onDmsAction(actionName) {
        const selectedIds = this.model.root.selection.map((r) => r.resId);
        if (!selectedIds.length) return;

        if (actionName === "download") {
            return this.onDownload();
        } else if (actionName === "share") {
            return this.onShare();
        } else if (actionName === "sign") {
            return this.onSign();
        } else if (actionName === "trash") {
            await this.orm.unlink("dms.file", selectedIds);
            await this.model.root.load();
            return;
        } else if (actionName === "duplicate") {
            await this.orm.call("dms.file", "action_duplicate_file", [selectedIds]);
            await this.model.root.load();
            return;
        } else if (actionName === "lock") {
            await this.orm.call("dms.file", "action_toggle_lock", [selectedIds]);
            await this.model.root.load();
            return;
        } else if (actionName === "rename" || actionName === "info") {
            return this.actionService.doAction({
                type: "ir.actions.act_window",
                res_model: "dms.file",
                res_id: selectedIds[0],
                views: [[false, "form"]],
                target: "current",
            });
        } else if (actionName === "move" || actionName === "shortcut") {
            return this.actionService.doAction("dms.wizard_dms_file_move_action", {
                additionalContext: {
                    active_ids: selectedIds,
                    active_id: selectedIds[0],
                },
            });
        }
    }
}
