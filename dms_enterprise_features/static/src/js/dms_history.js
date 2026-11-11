/** @odoo-module **/

/**
 * DMS navigation core, shared by every Documents window.
 *
 * 1. Trash is a *mode* of the documents browser (dms.file views with the
 *    folder tree), not a separate action. Entering / leaving it only changes
 *    the search model's domain + context, so the sidebar, its scroll
 *    position and its expanded folders stay exactly as they are.
 *
 * 2. Browser history: every folder change (and Trash in/out) pushes a history
 *    entry, so Back/Forward walk through folders. Entries are tagged with the
 *    action they belong to, and a history entry is only honoured when the
 *    browser actually navigated to it (page load, Back/Forward). Opening a new
 *    window never inherits the folder of the previous one, which caused the
 *    Trash to open filtered on the last folder (showing "empty") and the first
 *    folder click after the Trash to land on that stale folder.
 */

import { patch } from "@web/core/utils/patch";
import { onMounted, onWillUnmount } from "@odoo/owl";
import { Domain } from "@web/core/domain";
import { SearchModel } from "@web/search/search_model";
import { router, routerBus } from "@web/core/browser/router";
import { FileKanbanController } from "@dms/js/views/file_kanban_controller.esm";
import { FileListController } from "@dms/js/views/file_list_controller.esm";

const DMS_KEYS = ["dmsDirectoryId", "dmsTrash", "dmsActionId"];
for (const key of DMS_KEYS) {
    router.hideKeyFromUrl?.(key);
}

//-----------------------------------------------------------------------------
// Search model: folder category helpers + Trash mode
//-----------------------------------------------------------------------------

patch(SearchModel.prototype, {
    /** The folder-tree category of a DMS view, if any. */
    dmsFolderCategory() {
        if (!this.sections) {
            return null;
        }
        const fieldName =
            this.resModel === "dms.file" ? "directory_id" :
            this.resModel === "dms.directory" ? "parent_id" : null;
        if (!fieldName) {
            return null;
        }
        return this.categories.find((c) => c.fieldName === fieldName) || null;
    },

    /** True for the documents browser (files + folder tree). */
    get dmsIsBrowser() {
        return this.resModel === "dms.file" && Boolean(this.dmsFolderCategory());
    },

    get dmsTrash() {
        return Boolean(this._dmsTrash) && this.dmsIsBrowser;
    },

    get dmsCurrentDirId() {
        return this.dmsFolderCategory()?.activeValueId || false;
    },

    /**
     * Single entry point to move around the documents browser.
     * @param {number|false} dirId folder to show (false = root)
     * @param {boolean} trash show the Trash (or a trashed folder inside it)
     */
    dmsNavigate(dirId, trash = this.dmsTrash, { fromHistory = false } = {}) {
        const category = this.dmsFolderCategory();
        if (!category) {
            return;
        }
        dirId = dirId || false;
        trash = Boolean(trash) && this.dmsIsBrowser;
        if ((category.activeValueId || false) === dirId && this.dmsTrash === trash) {
            return;
        }
        this._dmsTrash = trash;
        category.activeValueId = dirId;
        this._reset();
        if (!fromHistory) {
            dmsPushHistory(this);
        }
        this._notify();
    },

    async load(config) {
        await super.load(...arguments);
        // The "Trash" menu opens the documents browser directly in Trash mode
        if (!config.state && this.globalContext?.dms_is_trash) {
            delete this.globalContext.dms_is_trash;
            await this.sectionsPromise;
            if (this.dmsIsBrowser) {
                this._dmsTrash = true;
                const category = this.dmsFolderCategory();
                category.activeValueId = false;
                this._reset();
            }
        }
    },

    exportState() {
        const state = super.exportState(...arguments);
        state.dmsTrash = Boolean(this._dmsTrash);
        return state;
    },

    _importState(state) {
        super._importState(...arguments);
        this._dmsTrash = Boolean(state?.dmsTrash);
        // A restored DMS window (soft_reload after a card-menu "Send to
        // Trash" / "Restore", breadcrumb back...) must refetch its folder
        // tree instead of reusing the cached one, or a trashed folder stays
        // in the sidebar until a full page load. load() reloads the
        // sections when searchPanelInfo.loaded is false.
        if (this.resModel === "dms.file" || this.resModel === "dms.directory") {
            this.searchPanelInfo = { ...this.searchPanelInfo, loaded: false };
        }
    },

    toggleCategoryValue(sectionId, valueId) {
        const section = this.sections.get(sectionId);
        if (section && section === this.dmsFolderCategory() && this.resModel === "dms.file") {
            return this.dmsNavigate(valueId, this.dmsTrash);
        }
        return super.toggleCategoryValue(...arguments);
    },

    clearSections(sectionIds) {
        const category = this.dmsFolderCategory();
        if (category && this.resModel === "dms.file" && sectionIds.includes(category.id)) {
            // "clear" from the facet: back to the root of the current mode
            const others = sectionIds.filter((id) => id !== category.id);
            if (others.length) {
                super.clearSections(others);
            }
            return this.dmsNavigate(false, this.dmsTrash);
        }
        return super.clearSections(...arguments);
    },

    /** Inside the Trash, trashed folders are valid category values too. */
    _ensureCategoryValue(category) {
        if (this._dmsTrash && category.fieldName === "directory_id" && this.resModel === "dms.file") {
            return;
        }
        return super._ensureCategoryValue(...arguments);
    },

    _getContext() {
        const context = super._getContext(...arguments);
        if (this.dmsTrash) {
            // trashed files are archived
            return { ...context, active_test: false, dms_is_trash: true };
        }
        return context;
    },

    _getDomain(params = {}) {
        const domain = super._getDomain(...arguments);
        const withSearchPanel = "withSearchPanel" in params ? params.withSearchPanel : true;
        // Only the records shown are affected: sidebar counters stay normal
        if (!this.dmsTrash || !withSearchPanel) {
            return domain;
        }
        const leaves = [["is_trashed", "=", true]];
        if (!this.dmsCurrentDirId) {
            // Trash root: only top-level trashed items (a trashed folder's
            // content is shown when opening that folder)
            leaves.push(["directory_is_trashed", "=", false]);
        }
        const trashDomain = Domain.and([
            params.raw ? domain : new Domain(domain),
            new Domain(leaves),
        ]);
        return params.raw ? trashDomain : trashDomain.toList(this.domainEvalContext);
    },
});

//-----------------------------------------------------------------------------
// Browser history
//-----------------------------------------------------------------------------

let activeDmsSearchModel = null;
let cleanupTimeout = null;
// A history entry may only be applied when the browser navigated to it
// (initial page load or Back/Forward), never when a new window is opened.
let honourHistoryEntry = true;
let applyingHistory = false;

function dmsActionId(searchModel) {
    return searchModel.env?.config?.actionId || false;
}

function readEntry(state) {
    if (!state || !("dmsDirectoryId" in state)) {
        return null;
    }
    return {
        dir: state.dmsDirectoryId || false,
        trash: Boolean(state.dmsTrash),
        actionId: state.dmsActionId || false,
    };
}

function entryFor(searchModel) {
    return {
        dmsDirectoryId: searchModel.dmsCurrentDirId,
        dmsTrash: searchModel.dmsTrash,
        dmsActionId: dmsActionId(searchModel),
        skipRouteChange: true,
    };
}

function dmsPushHistory(searchModel) {
    if (applyingHistory || searchModel !== activeDmsSearchModel) {
        return;
    }
    window.history.pushState(
        { nextState: router.current, ...entryFor(searchModel) },
        ""
    );
}

function initDmsHistory(searchModel) {
    if (!searchModel?.dmsIsBrowser) {
        return;
    }
    const entry = honourHistoryEntry ? readEntry(window.history.state) : null;
    honourHistoryEntry = false;
    if (entry && entry.actionId === dmsActionId(searchModel)) {
        applyingHistory = true;
        try {
            searchModel.dmsNavigate(entry.dir, entry.trash, { fromHistory: true });
        } finally {
            applyingHistory = false;
        }
    }
    // Tag the window's own history entry once the router has pushed it
    // (its push is debounced), so Back to it restores this location.
    setTimeout(() => {
        if (activeDmsSearchModel !== searchModel) {
            return;
        }
        const current = readEntry(window.history.state);
        if (current && current.actionId === dmsActionId(searchModel)) {
            return;
        }
        window.history.replaceState(
            { ...window.history.state, ...entryFor(searchModel) },
            ""
        );
    }, 50);
}

function setActiveDmsSearchModel(searchModel) {
    if (cleanupTimeout) {
        clearTimeout(cleanupTimeout);
        cleanupTimeout = null;
    }
    if (activeDmsSearchModel === searchModel) {
        return;
    }
    activeDmsSearchModel = searchModel;
    initDmsHistory(searchModel);
}

function unregisterDmsSearchModel(searchModel) {
    if (activeDmsSearchModel === searchModel) {
        cleanupTimeout = setTimeout(() => {
            if (activeDmsSearchModel === searchModel) {
                activeDmsSearchModel = null;
            }
        }, 100);
    }
}

window.addEventListener("popstate", (ev) => {
    const entry = readEntry(ev.state);
    const searchModel = activeDmsSearchModel;
    if (entry && searchModel && entry.actionId === dmsActionId(searchModel)) {
        // Back/Forward between folders of the window on screen
        honourHistoryEntry = false;
        applyingHistory = true;
        try {
            searchModel.dmsNavigate(entry.dir, entry.trash, { fromHistory: true });
        } finally {
            applyingHistory = false;
        }
        return;
    }
    // Another window: let the web client load it, then honour the entry
    honourHistoryEntry = true;
    if (entry && ev.state?.skipRouteChange) {
        routerBus.trigger("ROUTE_CHANGE");
    }
});

for (const Controller of [FileKanbanController, FileListController]) {
    patch(Controller.prototype, {
        setup() {
            super.setup(...arguments);
            onMounted(() => setActiveDmsSearchModel(this.env.searchModel));
            onWillUnmount(() => unregisterDmsSearchModel(this.env.searchModel));
        },
    });
}
