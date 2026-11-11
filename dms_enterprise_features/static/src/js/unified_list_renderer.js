/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { onWillStart, onWillUpdateProps, onMounted, onWillUnmount, proxy } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { FileListRenderer } from "@dms/js/views/file_list_renderer.esm";
import { FileListController } from "@dms/js/views/file_list_controller.esm";
import { FileListView } from "@dms/js/views/file_list_view.esm";
import { ListController } from "@web/views/list/list_controller";
import { dmsCanUploadHere } from "@dms_enterprise_features/js/dms_upload_permission";

// Bind Controller on FileListView
FileListView.Controller = FileListController;

patch(FileListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.action = useService("action");
        this.dmsDirectoriesState = proxy({ data: [], currentDir: false });
        this._onSmUpdateDir = async () => {
            await this.fetchDirectories(this.props);
            this.render?.();
        };

        this._reloadDirectories = async () => {
            await this.fetchDirectories(this.props);
            this.render?.();
        };

        onWillStart(async () => {
            this.isDmsManagerOrAdmin = (
                user.isAdmin ||
                await user.hasGroup("dms.group_dms_manager") ||
                await user.hasGroup("dms_enterprise_features.group_dms_administrator")
            );
            await this.fetchDirectories(this.props);
        });

        onWillUpdateProps(async (nextProps) => {
            await this.fetchDirectories(nextProps);
            this.render?.();
        });

        onMounted(() => {
            this.env.searchModel?.addEventListener("update", this._onSmUpdateDir);
            this.env.bus?.addEventListener("dms-reload-directories", this._reloadDirectories);
        });

        onWillUnmount(() => {
            this.env.searchModel?.removeEventListener("update", this._onSmUpdateDir);
            this.env.bus?.removeEventListener("dms-reload-directories", this._reloadDirectories);
        });
    },

    highlight(ev) {
        if (!this.isDmsManagerOrAdmin && !this._dmsCanUpload) return;
        super.highlight(...arguments);
    },

    onDrop(ev) {
        if (!this.isDmsManagerOrAdmin && !this._dmsCanUpload) return;
        super.onDrop(...arguments);
    },

    async fetchDirectories(props) {
        if (this.env.searchModel?.resModel !== "dms.file") {
            return;
        }
        this._dmsCanUpload = await dmsCanUploadHere(this.orm, this.env.searchModel, this.isDmsManagerOrAdmin);

        const domain = (props?.list?.domain)
            || (typeof this.env.searchModel.getGlobalDomain === 'function' ? this.env.searchModel.getGlobalDomain() : this.env.searchModel.domain)
            || [];
        let directoryId = false;
        let isTrashAction = false;

        const category = this.env.searchModel?.getSections?.()?.find(s => s.fieldName === 'directory_id');
        if (category && category.activeValueId) {
            directoryId = category.activeValueId;
        }

        // Detect directoryId and isTrashAction first
        for (const d of domain) {
            if (Array.isArray(d) && d.length >= 3) {
                if (!category?.activeValueId && d[0] === 'directory_id' && (d[1] === '=' || d[1] === 'child_of')) {
                    directoryId = d[2];
                }
                if (d[0] === 'is_trashed' && d[2] === true) {
                    isTrashAction = true;
                }
            }
        }

        if (this.env.searchModel?.dmsTrash) {
            isTrashAction = true;
        }
        this.dmsDirectoriesState.isTrash = isTrashAction;

        // Fields strictly specific to files that directories can NEVER have or match
        const FILE_ONLY_FIELDS = new Set([
            "approval_state",
            "current_approver_ids",
            "mimetype",
            "extension",
            "size",
            "human_size",
            "content",
            "content_binary",
            "is_locked",
            "locked_by",
            "is_lock_editor",
            "current_revision_id",
            "revision_ids",
            "document_number",
            "document_owner_id",
            "department_id",
            "confidentiality",
            "expiry_date",
        ]);

        const DIRECTORY_FIELDS = new Set([
            "name",
            "category_id",
            "tag_ids",
            "starred",
            "create_date",
            "write_date",
            "create_uid",
            "storage_id",
            "activity_state",
            "activity_ids",
            "activity_type_id",
            "activity_user_id",
            "activity_date_deadline",
            "activity_summary",
        ]);

        let canApplyToDirectories = true;
        const extraDirDomain = [];

        for (const d of domain) {
            if (Array.isArray(d) && d.length >= 3) {
                const field = d[0];
                const op = d[1];
                const val = d[2];

                // Skip navigation/system leaves
                if (field === 'directory_id' || field === 'is_hidden' || field === 'is_trashed' || field === 'directory_is_trashed') {
                    continue;
                }

                // Archived filter: [('active', '=', False)]
                // Folders cannot be archived. If filtering for inactive/archived items (and not in Trash), folders do not match.
                if (field === 'active') {
                    if (val === false && !isTrashAction) {
                        const isAllFilter = domain.some(item => Array.isArray(item) && item[0] === 'active' && (item[1] === '!=' || item[2] !== false));
                        if (!isAllFilter) {
                            canApplyToDirectories = false;
                            break;
                        }
                    }
                    continue;
                }

                const baseField = typeof field === 'string' ? field.split('.')[0] : field;
                if (FILE_ONLY_FIELDS.has(baseField)) {
                    canApplyToDirectories = false;
                    break;
                }

                // "My Files" filter: [('is_my_file', '=', True)]
                if (field === 'is_my_file') {
                    if (val === true) {
                        const currentUid = user.userId || this.env.user?.userId;
                        if (currentUid) {
                            extraDirDomain.push(['create_uid', '=', currentUid]);
                        }
                    }
                    continue;
                }

                if (DIRECTORY_FIELDS.has(baseField)) {
                    extraDirDomain.push([field, op, val]);
                } else {
                    canApplyToDirectories = false;
                    break;
                }
            }
        }

        // If the applied filter cannot match directories (e.g. Archived, Approval, Mimetype), hide folders
        if (!canApplyToDirectories) {
            this.dmsDirectoriesState.data = [];
            if (directoryId) {
                const fieldsToRead = isTrashAction ? ["parent_id", "name", "parent_is_trashed"] : ["parent_id", "name"];
                const currentDir = await this.orm.read("dms.directory", [directoryId], fieldsToRead);
                if (currentDir && currentDir.length > 0) {
                    this.dmsDirectoriesState.currentDir = currentDir[0];
                }
            } else {
                this.dmsDirectoriesState.currentDir = false;
            }
            return;
        }

        let dirDomain;
        if (isTrashAction) {
            dirDomain = [['is_trashed', '=', true]];
            if (directoryId) {
                dirDomain.push(['parent_id', '=', directoryId]);
                const currentDir = await this.orm.read("dms.directory", [directoryId], ["parent_id", "name", "parent_is_trashed"]);
                if (currentDir && currentDir.length > 0) {
                    this.dmsDirectoriesState.currentDir = currentDir[0];
                }
            } else {
                if (extraDirDomain.length === 0) {
                    dirDomain.push('|', ['parent_id', '=', false], ['parent_is_trashed', '=', false]);
                }
                this.dmsDirectoriesState.currentDir = false;
            }
        } else {
            dirDomain = [['is_trashed', '=', false]];
            if (directoryId) {
                dirDomain.push(['parent_id', '=', directoryId]);
                const currentDir = await this.orm.read("dms.directory", [directoryId], ["parent_id", "name"]);
                if (currentDir && currentDir.length > 0) {
                    this.dmsDirectoriesState.currentDir = currentDir[0];
                }
            } else {
                if (extraDirDomain.length === 0) {
                    dirDomain.push(['is_root_directory', '=', true]);
                }
                this.dmsDirectoriesState.currentDir = false;
            }
        }

        if (extraDirDomain.length > 0) {
            dirDomain.push(...extraDirDomain);
        }
        const dirs = await this.orm.searchRead(
            "dms.directory",
            dirDomain,
            ["name", "display_name", "company_id", "color", "starred", "count_files", "count_directories", "icon_url", "write_date", "permission_download", "permission_write", "permission_edit", "permission_unlink", "permission_move", "is_trashed", "activity_ids", "activity_state", "activity_summary", "activity_type_id"]
        );

        const isStarredFilterActive = extraDirDomain.some(d => d[0] === 'starred' && (d[1] === '=' || d[1] === 'in') && Boolean(d[2]));
        if (isStarredFilterActive) {
            this.dmsDirectoriesState.data = dirs.filter(d => Boolean(d.starred));
        } else {
            this.dmsDirectoriesState.data = dirs;
        }
        this.render?.();
    },

    async _syncSearchPanelAndDirs() {
        const sm = this.env?.searchModel;
        if (sm) {
            if (sm.categories && typeof sm._fetchCategories === "function") {
                try {
                    await sm._fetchCategories(sm.categories);
                } catch (err) {}
            }
            sm._reset?.();
            sm.trigger("update");
        }
        this.env.bus?.trigger("dms-reload-directories");
        await this.fetchDirectories(this.props);
        this.render?.();
        if (this.props.list) {
            await this.props.list.load();
        }
    },

    openDirectory(dirId) {
        if (this.env.searchModel) {
            const category = this.env.searchModel.getSections().find(s => s.fieldName === 'directory_id');
            if (category) {
                this.env.searchModel.toggleCategoryValue(category.id, dirId || false);
            }
        }
    },

    async setColor(dirId, colorIdx) {
        await this.orm.write("dms.directory", [dirId], { color: colorIdx });
        await this.fetchDirectories(this.props);
    },

    navigateUp() {
        if (this.dmsDirectoriesState.currentDir) {
            const cur = this.dmsDirectoriesState.currentDir;
            const leavesTrash = this.env.searchModel?.dmsTrash && !cur.parent_is_trashed;
            const parentId = cur.parent_id && !leavesTrash ? cur.parent_id[0] : false;
            this.openDirectory(parentId);
        }
    },

    navigateToBreadcrumb(dirId) {
        this.openDirectory(dirId || false);
    },

    createSubdirectory(dirId) {
        this.action.doAction({
            name: "New Subfolder",
            type: "ir.actions.act_window",
            res_model: "dms.directory",
            views: [[false, "form"]],
            target: "new",
            context: {
                default_parent_id: dirId,
                default_is_root_directory: false,
            },
        }, {
            onClose: () => {
                this._syncSearchPanelAndDirs();
            }
        });
    },

    editDirectory(dirId) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "dms.directory",
            res_id: dirId,
            views: [[false, "form"]],
            target: "new",
        }, {
            onClose: () => {
                this._syncSearchPanelAndDirs();
            }
        });
    },

    scheduleActivityDirectory(dirId) {
        if (!dirId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Schedule Activity",
            res_model: "mail.activity.schedule",
            view_mode: "form",
            views: [[false, "form"]],
            target: "new",
            context: {
                active_model: "dms.directory",
                active_ids: [dirId],
                active_id: dirId,
            },
        }, {
            onClose: () => {
                this.fetchDirectories(this.props);
            }
        });
    },

    async trashDirectory(dirId) {
        await this.orm.call("dms.directory", "action_send_to_trash", [[dirId]]);
        await this._syncSearchPanelAndDirs();
    },

    async restoreDirectory(dirId) {
        await this.orm.call("dms.directory", "action_restore", [[dirId]]);
        await this._syncSearchPanelAndDirs();
    },

    async deleteDirectoryPermanently(dirId) {
        await this.orm.call("dms.directory", "unlink", [[dirId]]);
        await this._syncSearchPanelAndDirs();
    },

    async downloadDirectory(dirId) {
        const action = await this.orm.call("dms.directory", "action_download_directory_zip", [[dirId]]);
        if (action) {
            this.action.doAction(action);
        }
    }
});

patch(FileListController.prototype, {
    setup() {
        super.setup(...arguments);
        this.actionService = useService("action");
        this.isDmsManagerOrAdmin = false;
        this._bcOrmService = useService("orm");
        this._bcSeq = 0;

        // Capture initial action breadcrumbs
        this._initialBreadcrumbs = [...(this.env.config?.breadcrumbs || [])];
        const lastCrumb = this._initialBreadcrumbs.at(-1);
        this._ancestorCrumbs = this._initialBreadcrumbs.slice(0, -1);
        this._rootCrumb = {
            jsId: lastCrumb?.jsId || "dms_root",
            name: lastCrumb?.name || this.env.config?.getDisplayName?.() || "My Documents",
            isFormView: false,
            url: "#",
            onSelected: () => this.navigateToBreadcrumb(false),
        };

        this.dmsUpload = proxy({ allowed: false });
        this._onSmUpdate = () => {
            this._buildBreadcrumbs();
            this._refreshDmsUpload();
        };

        onWillStart(async () => {
            this.isDmsManagerOrAdmin = (
                user.isAdmin ||
                await user.hasGroup("dms.group_dms_manager") ||
                await user.hasGroup("dms_enterprise_features.group_dms_administrator")
            );
            await this._buildBreadcrumbs();
            await this._refreshDmsUpload();
        });

        onMounted(() => {
            this.env.searchModel?.addEventListener("update", this._onSmUpdate);
        });

        onWillUnmount(() => {
            this.env.searchModel?.removeEventListener("update", this._onSmUpdate);
            if (this.env.config?.breadcrumbs && this._initialBreadcrumbs.length) {
                this.env.config.breadcrumbs.splice(0, this.env.config.breadcrumbs.length, ...this._initialBreadcrumbs);
                this.env.config.breadcrumbs.push(undefined);
                this.env.config.breadcrumbs.pop();
            }
        });
    },

    async _refreshDmsUpload() {
        const allowed = await dmsCanUploadHere(this._bcOrmService, this.env.searchModel, this.isDmsManagerOrAdmin);
        if (this.dmsUpload.allowed !== allowed) {
            this.dmsUpload.allowed = allowed;
            this.render?.();
        }
    },

    get canCreate() {
        return Boolean(super.canCreate && !this.env.searchModel?.dmsTrash && (this.isDmsManagerOrAdmin || this.dmsUpload?.allowed));
    },

    uploadDocument() {
        if (!this.isDmsManagerOrAdmin && !this.dmsUpload?.allowed) {
            return;
        }
        super.uploadDocument(...arguments);
    },

    async createDirectory(targetParentId = false) {
        if (!this.isDmsManagerOrAdmin) {
            return;
        }

        let directoryId = (typeof targetParentId === 'number' || (typeof targetParentId === 'string' && targetParentId)) ? targetParentId : false;
        if (!directoryId) {
            const category = this.env.searchModel?.getSections?.()?.find(s => s.fieldName === 'directory_id');
            if (category && category.activeValueId) {
                directoryId = category.activeValueId;
            }
        }
        if (!directoryId) {
            const domain = [
                ...(this.env.searchModel?.domain || []),
                ...(typeof this.env.searchModel?.getGlobalDomain === 'function' ? this.env.searchModel.getGlobalDomain() : []),
            ];
            for (const d of domain) {
                if (Array.isArray(d) && d.length >= 3) {
                    if (d[0] === 'directory_id' && (d[1] === '=' || d[1] === 'child_of')) {
                        directoryId = d[2];
                        break;
                    }
                }
            }
        }
        if (!directoryId && this.env.searchModel?.context?.default_directory_id) {
            directoryId = this.env.searchModel.context.default_directory_id;
        }

        const context = {};
        if (directoryId) {
            context.default_parent_id = directoryId;
            context.default_is_root_directory = false;
        }

        this.actionService.doAction({
            name: "New Folder",
            type: "ir.actions.act_window",
            res_model: "dms.directory",
            views: [[false, "form"]],
            target: "new",
            context: context,
        }, {
            onClose: async () => {
                const sm = this.env?.searchModel;
                if (sm) {
                    if (sm.categories && typeof sm._fetchCategories === "function") {
                        try {
                            await sm._fetchCategories(sm.categories);
                        } catch (err) {
                            console.warn("Could not reload searchModel categories:", err);
                        }
                    }
                    sm._reset?.();
                    sm.trigger("update");
                }
                this.env.bus?.trigger("dms-reload-directories");
                if (this.model && this.model.root) {
                    try {
                        await this.model.root.load();
                    } catch (err) {
                        console.warn("Could not reload model root:", err);
                    }
                }
            }
        });
    },

    /** Walk parent chain to build ordered breadcrumb trail in ControlPanel. */
    async _buildBreadcrumbs() {
        if (!this.env.config?.breadcrumbs) {
            return;
        }
        const reqSeq = ++this._bcSeq;
        const sm = this.env.searchModel;
        if (!sm || sm.resModel !== "dms.file") {
            return;
        }
        let directoryId = false;
        const category = sm.getSections?.()?.find(s => s.fieldName === 'directory_id');
        if (category?.activeValueId) directoryId = category.activeValueId;
        if (!directoryId) {
            const domain = (typeof sm.getGlobalDomain === 'function' ? sm.getGlobalDomain() : sm.domain) || [];
            for (const d of domain) {
                if (Array.isArray(d) && d[0] === 'directory_id' && (d[1] === '=' || d[1] === 'child_of')) {
                    directoryId = d[2];
                }
            }
        }

        const trash = Boolean(sm.dmsTrash);
        const rootCrumb = {
            jsId: this._rootCrumb?.jsId || "dms_root",
            name: this._rootCrumb?.name || this.env.config?.getDisplayName?.() || "My Documents",
            isFormView: false,
            url: "#",
            onSelected: () => (trash ? sm.dmsNavigate(false, false) : this.navigateToBreadcrumb(false)),
        };
        const baseCrumbs = [...this._ancestorCrumbs, rootCrumb];
        if (trash) {
            baseCrumbs.push({
                jsId: "dms_trash",
                name: "Trash",
                isFormView: false,
                url: "#",
                onSelected: () => sm.dmsNavigate(false, true),
            });
        }

        if (!directoryId) {
            const resetCrumbs = baseCrumbs;
            this.env.config.breadcrumbs.splice(0, this.env.config.breadcrumbs.length, ...resetCrumbs);
            this.env.config.breadcrumbs.push(undefined);
            this.env.config.breadcrumbs.pop();
            return;
        }

        const crumbs = [];
        let currentId = directoryId;
        for (let i = 0; i < 20 && currentId; i++) {
            const res = await this._bcOrmService.read("dms.directory", [currentId], ["name", "parent_id", "is_trashed"]);
            if (!res?.length) break;
            // inside the Trash the path starts at the top-level trashed folder
            if (trash && !res[0].is_trashed) break;
            crumbs.unshift({ id: res[0].id, name: res[0].name });
            currentId = res[0].parent_id ? res[0].parent_id[0] : false;
        }

        if (reqSeq !== this._bcSeq) {
            return;
        }

        const folderCrumbs = crumbs.map((crumb) => ({
            jsId: `dms_dir_${crumb.id}`,
            name: crumb.name,
            isFormView: false,
            url: "#",
            onSelected: () => this.navigateToBreadcrumb(crumb.id),
        }));

        const newBreadcrumbs = [...baseCrumbs, ...folderCrumbs];

        this.env.config.breadcrumbs.splice(0, this.env.config.breadcrumbs.length, ...newBreadcrumbs);
        this.env.config.breadcrumbs.push(undefined);
        this.env.config.breadcrumbs.pop();
    },

    navigateToBreadcrumb(dirId) {
        const sm = this.env.searchModel;
        if (!sm) return;
        const category = sm.getSections().find(s => s.fieldName === 'directory_id');
        if (category) sm.toggleCategoryValue(category.id, dirId || false);
    },
});

patch(ListController.prototype, {
    setup() {
        super.setup(...arguments);
        if (this.props.resModel === "dms.file") {
            this.isDmsManagerOrAdmin = false;
            this.dmsUploadGeneric = proxy({ allowed: false });
            const orm = useService("orm");
            onWillStart(async () => {
                this.isDmsManagerOrAdmin = (
                    user.isAdmin ||
                    await user.hasGroup("dms.group_dms_manager") ||
                    await user.hasGroup("dms_enterprise_features.group_dms_administrator")
                );
                this.dmsUploadGeneric.allowed = await dmsCanUploadHere(orm, this.env.searchModel, this.isDmsManagerOrAdmin);
            });
        }
    },

    get canCreate() {
        if (this.props.resModel === "dms.file") {
            if (this.dmsUpload) {
                // DMS FileListController: it applies the per-folder check itself
                return super.canCreate;
            }
            return Boolean(super.canCreate && (this.isDmsManagerOrAdmin || this.dmsUploadGeneric?.allowed));
        }
        return super.canCreate;
    },
});
