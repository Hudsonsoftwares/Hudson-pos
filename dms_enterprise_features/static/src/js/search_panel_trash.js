/** @odoo-module **/

/**
 * One sidebar for every Documents window.
 *
 * The folder tree, the folder actions menu and the Trash entry behave the
 * same in the documents browser (dms.file) and in Configuration >
 * Directories (dms.directory). In the browser, Trash is a mode of the same
 * view (see dms_history.js), so opening / leaving it is instant and the
 * sidebar keeps its scroll position and expanded folders. From the
 * Directories window, Trash opens the documents browser in Trash mode.
 */

import { SearchPanel } from "@web/search/search_panel/search_panel";
import { patch } from "@web/core/utils/patch";
import { useService, useBus } from "@web/core/utils/hooks";
import { onWillStart, onWillUpdateProps, proxy } from "@odoo/owl";

const TRASH_ACTION = "dms_enterprise_features.action_dms_file_trash";

patch(SearchPanel.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.action = useService("action");
        this.dmsTrashState = proxy({ trashCount: 0 });

        const refresh = async () => {
            await this.env.searchModel?.sectionsPromise;
            if (this.isDmsView()) {
                await this.fetchTrashCount();
            }
        };
        onWillStart(refresh);
        onWillUpdateProps(refresh);
        if (this.env.searchModel) {
            useBus(this.env.searchModel, "update", refresh);
        }
    },

    /** The folder-tree section of a DMS window, if any. */
    dmsFolderSection() {
        return this.env.searchModel?.dmsFolderCategory?.() || null;
    },

    isDmsFolderSection(section) {
        const folder = this.dmsFolderSection();
        return Boolean(folder && section && section.id === folder.id);
    },

    /** Any Documents window with the folder tree (files or directories). */
    isDmsView() {
        try {
            return Boolean(this.dmsFolderSection());
        } catch {
            return false;
        }
    },

    isTrashActive() {
        return Boolean(this.env.searchModel?.dmsTrash);
    },

    updateActiveValues() {
        super.updateActiveValues(...arguments);
        if (this.isTrashActive()) {
            const folder = this.dmsFolderSection();
            if (folder) {
                // nothing highlighted in the tree while the Trash is shown
                this.state.active[folder.id] = false;
            }
        }
    },

    isCategoryActive(section, valueId) {
        if (this.isTrashActive() && this.isDmsFolderSection(section)) {
            return false;
        }
        return this.state.active[section.id] === valueId;
    },

    /** Trashed folders opened inside the Trash are not part of the tree. */
    getAncestorValueIds(category, categoryValueId) {
        if (!category.values.has(categoryValueId)) {
            return [];
        }
        return super.getAncestorValueIds(...arguments);
    },

    getCategorySelection() {
        if (this.isTrashActive()) {
            return [{ description: "Trash", values: ["Trash"] }];
        }
        return super.getCategorySelection(...arguments);
    },

    async fetchTrashCount() {
        // Same items as the Trash root shows: top-level trashed folders and
        // trashed files that are not inside a trashed folder.
        try {
            const [fileCount, dirCount] = await Promise.all([
                this.orm.searchCount(
                    "dms.file",
                    [["is_trashed", "=", true], ["directory_is_trashed", "=", false]],
                    { context: { active_test: false } }
                ),
                this.orm.searchCount("dms.directory", [
                    ["is_trashed", "=", true],
                    "|", ["parent_id", "=", false], ["parent_is_trashed", "=", false],
                ]),
            ]);
            this.dmsTrashState.trashCount = fileCount + dirCount;
        } catch {
            this.dmsTrashState.trashCount = 0;
        }
    },

    openTrash() {
        const sm = this.env.searchModel;
        if (sm?.dmsIsBrowser) {
            return sm.dmsNavigate(false, true);
        }
        // Directories window: show the Trash in the documents browser
        return this.action.doAction(TRASH_ACTION, { clearBreadcrumbs: true });
    },

    async toggleCategory(category, value) {
        const sm = this.env.searchModel;
        if (sm?.dmsTrash && this.isDmsFolderSection(category)) {
            // Clicking a folder in the tree always leaves the Trash
            if (value.childrenIds.length) {
                this.state.expanded[category.id] ||= {};
                this.state.expanded[category.id][value.id] = true;
            }
            return sm.dmsNavigate(value.id, false);
        }
        return super.toggleCategory(...arguments);
    },
});
