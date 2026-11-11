/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ActivityController } from "@mail/views/web/activity/activity_controller";
import { useService } from "@web/core/utils/hooks";
import { onMounted, onWillUpdateProps, onWillUnmount } from "@odoo/owl";
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog";
import { _t } from "@web/core/l10n/translation";

patch(ActivityController.prototype, {
    setup() {
        super.setup(...arguments);

        if (this.props.resModel === "dms.file") {
            this._bcOrmService = useService("orm");
            this._bcSeq = 0;
            this.activeDirectoryInfo = null;
            this._initialBreadcrumbs = [...(this.env.config?.breadcrumbs || [])];
            this._ancestorCrumbs = this._initialBreadcrumbs.length > 1
                ? this._initialBreadcrumbs.slice(0, -1)
                : [];
            this._rootCrumb = this._initialBreadcrumbs.length
                ? this._initialBreadcrumbs[this._initialBreadcrumbs.length - 1]
                : null;

            onMounted(() => {
                this._buildBreadcrumbs();
            });

            onWillUpdateProps(() => {
                this._buildBreadcrumbs();
            });

            onWillUnmount(() => {
                if (this.env.config?.breadcrumbs && this._initialBreadcrumbs.length) {
                    this.env.config.breadcrumbs.splice(
                        0,
                        this.env.config.breadcrumbs.length,
                        ...this._initialBreadcrumbs
                    );
                    this.env.config.breadcrumbs.push(undefined);
                    this.env.config.breadcrumbs.pop();
                }
            });
        }
    },

    getActiveDirectoryId() {
        let activeDirectoryId = false;

        // 1. Check searchModel categories
        if (this.env.searchModel?.categories) {
            const dirCategory = this.env.searchModel.categories.find(
                (c) => c.fieldName === "directory_id"
            );
            if (dirCategory && dirCategory.activeValueId) {
                activeDirectoryId = dirCategory.activeValueId;
            }
        }

        // 2. Check searchModel sections
        if (!activeDirectoryId && this.env.searchModel?.getSections) {
            const dirSection = this.env.searchModel
                .getSections()
                .find((s) => s.fieldName === "directory_id");
            if (dirSection && dirSection.activeValueId) {
                activeDirectoryId = dirSection.activeValueId;
            }
        }

        // 3. Fallback from model original domain
        if (!activeDirectoryId && this.model?.originalDomain) {
            for (const d of this.model.originalDomain) {
                if (
                    Array.isArray(d) &&
                    d.length >= 3 &&
                    d[0] === "directory_id" &&
                    (d[1] === "=" || d[1] === "child_of")
                ) {
                    activeDirectoryId = d[2];
                    break;
                }
            }
        }

        return activeDirectoryId;
    },

    get getSelectCreateDialogProps() {
        const dialogProps = super.getSelectCreateDialogProps;
        if (this.props.resModel === "dms.file") {
            const activeDirectoryId = this.getActiveDirectoryId();

            // Inject active directory into dialog domain and context
            if (activeDirectoryId) {
                dialogProps.context = {
                    ...(dialogProps.context || {}),
                    default_directory_id: activeDirectoryId,
                };

                const currentDomain = dialogProps.domain || [];
                const hasDirFilter = currentDomain.some(
                    (d) => Array.isArray(d) && d.length >= 3 && d[0] === "directory_id"
                );
                if (!hasDirFilter) {
                    dialogProps.domain = [
                        ...currentDomain,
                        ["directory_id", "child_of", activeDirectoryId],
                    ];
                }
            }
        }
        return dialogProps;
    },

    scheduleFolderActivity() {
        const activeDirId = this.getActiveDirectoryId();
        if (activeDirId) {
            this.action.doAction(
                {
                    type: "ir.actions.act_window",
                    name: _t("Schedule Activity"),
                    res_model: "mail.activity.schedule",
                    view_mode: "form",
                    views: [[false, "form"]],
                    target: "new",
                    context: {
                        active_model: "dms.directory",
                        active_ids: [activeDirId],
                        active_id: activeDirId,
                    },
                },
                {
                    onClose: () => {
                        this.model.load(this.getSearchProps());
                    },
                }
            );
        } else {
            this.dialog.add(
                SelectCreateDialog,
                {
                    resModel: "dms.directory",
                    title: _t("Select Folder to Schedule Activity"),
                    multiSelect: false,
                    noCreate: true,
                    onSelected: async (resIds) => {
                        if (resIds && resIds.length > 0) {
                            this.action.doAction(
                                {
                                    type: "ir.actions.act_window",
                                    name: _t("Schedule Activity"),
                                    res_model: "mail.activity.schedule",
                                    view_mode: "form",
                                    views: [[false, "form"]],
                                    target: "new",
                                    context: {
                                        active_model: "dms.directory",
                                        active_ids: resIds,
                                        active_id: resIds[0],
                                    },
                                },
                                {
                                    onClose: () => {
                                        this.model.load(this.getSearchProps());
                                    },
                                }
                            );
                        }
                    },
                },
                {
                    onClose: () => this.model.load(this.getSearchProps()),
                }
            );
        }
    },

    get rendererProps() {
        const props = super.rendererProps;
        if (this.props.resModel === "dms.file") {
            props.activeDirectory = this.activeDirectoryInfo;
            props.scheduleFolderActivity = this.scheduleFolderActivity.bind(this);
        }
        return props;
    },

    async _buildBreadcrumbs() {
        if (!this.env.config?.breadcrumbs) {
            return;
        }
        const reqSeq = ++this._bcSeq;
        const sm = this.env.searchModel;
        if (!sm || sm.resModel !== "dms.file") {
            return;
        }

        const directoryId = this.getActiveDirectoryId();

        const rootCrumb = {
            jsId: this._rootCrumb?.jsId || "dms_root",
            name: this._rootCrumb?.name || this.env.config?.getDisplayName?.() || "My Documents",
            isFormView: false,
            url: "#",
            onSelected: () => this.navigateToBreadcrumb(false),
        };

        if (!directoryId) {
            this.activeDirectoryInfo = null;
            const resetCrumbs = [...this._ancestorCrumbs, rootCrumb];
            this.env.config.breadcrumbs.splice(
                0,
                this.env.config.breadcrumbs.length,
                ...resetCrumbs
            );
            this.env.config.breadcrumbs.push(undefined);
            this.env.config.breadcrumbs.pop();
            return;
        }

        const crumbs = [];
        let currentId = directoryId;
        for (let i = 0; i < 20 && currentId; i++) {
            const res = await this._bcOrmService.read(
                "dms.directory",
                [currentId],
                ["name", "parent_id"]
            );
            if (!res?.length) break;
            crumbs.unshift({ id: res[0].id, name: res[0].name });
            currentId = res[0].parent_id ? res[0].parent_id[0] : false;
        }

        if (reqSeq !== this._bcSeq) {
            return;
        }

        this.activeDirectoryInfo = crumbs.length ? crumbs[crumbs.length - 1] : null;

        const folderCrumbs = crumbs.map((crumb) => ({
            jsId: `dms_dir_${crumb.id}`,
            name: crumb.name,
            isFormView: false,
            url: "#",
            onSelected: () => this.navigateToBreadcrumb(crumb.id),
        }));

        const newBreadcrumbs = [
            ...this._ancestorCrumbs,
            rootCrumb,
            ...folderCrumbs,
        ];

        this.env.config.breadcrumbs.splice(
            0,
            this.env.config.breadcrumbs.length,
            ...newBreadcrumbs
        );
        this.env.config.breadcrumbs.push(undefined);
        this.env.config.breadcrumbs.pop();
    },

    navigateToBreadcrumb(dirId) {
        const sm = this.env.searchModel;
        if (!sm) return;
        const category = sm.getSections?.()?.find((s) => s.fieldName === "directory_id");
        if (category) {
            sm.toggleCategoryValue(category.id, dirId || false);
        }
    },
});
