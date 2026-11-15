/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, proxy, onWillStart, onWillDestroy, useProps } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";
import { useService } from "@web/core/utils/hooks";
import { browser } from "@web/core/browser/browser";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";

const STATION_KEY = "hudson_shopfloor.station_workcenter_ids";
const EMPLOYEES_KEY = "hudson_shopfloor.panel_employee_ids";
const REFRESH_INTERVAL = 30000;

function loadIds(key) {
    try {
        const ids = JSON.parse(browser.localStorage.getItem(key) || "[]");
        return Array.isArray(ids) ? ids : [];
    } catch {
        return [];
    }
}

function saveIds(key, ids) {
    try {
        browser.localStorage.setItem(key, JSON.stringify(ids));
    } catch {
        // Storage unavailable (private mode...): the selection only lasts for this session
    }
}

// "YYYY-MM-DD HH:MM:SS" (UTC, server format) → Date
function parseServerDatetime(value) {
    return value ? new Date(value.replace(" ", "T") + "Z") : null;
}

function formatSeconds(totalSeconds) {
    const secs = Math.max(0, Math.floor(totalSeconds));
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return h ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

export class ShopFloorApp extends Component {
    static template = "hudson_shopfloor.ShopFloorApp";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");

        this.state = proxy({
            // Tabs: "overview" | "my_wo" | workcenter id
            tab: "overview",
            workcenters: [],
            overviewCount: 0,
            myWoCount: 0,
            productions: [],
            workorders: [],
            highlightWoId: null,
            currentTime: new Date(),
            loading: false,

            // Station configuration (stored on this device)
            stationWorkcenterIds: loadIds(STATION_KEY),
            panelEmployeeIds: loadIds(EMPLOYEES_KEY),

            // Search & Filter
            searchQuery: "",
            showFilterPanel: false,
            showHamburgerPanel: false,
            filterMoReady: true,
            filterMoPending: false,
            filterThisStation: false,
            filterWoToDo: true,
            filterWoBlocked: false,
            filterWoInProgress: true,

            // Notification banner
            showBanner: true,

            // Operators
            employees: [],
            activeEmployee: null,

            // PIN modal
            showPinModal: false,
            pinEmployee: null,
            pinValue: "",

            // Generic multi-select modal (work centers / operators)
            selectModal: null, // { title, items: [{id, name}], selected: [ids], onSave }

            // Options modal
            showOptionsModal: false,
            optionsMoId: null,
            optionsWoId: null,

            // Register production modal
            showRegisterQtyModal: false,
            registerMo: null, // { id, name, product, uom, tracking, qty_production }
            registerQtyValue: 1,
            registerLotName: "",

            // Register component modal
            showComponentModal: false,
            componentMoId: null,
            componentMove: null,
            componentQty: 0,

            // ── Product Catalog (Add Component) ──────────────────────────────
            showCatalogModal: false,
            catalogMoId: null,
            catalogWoId: null,
            catalogSearch: "",
            catalogCategories: [],        // [{id, name, parent_id}]
            catalogSelectedCat: null,     // null → All
            catalogTags: [],              // [{id, name}]
            catalogSelectedTag: null,
            catalogProducts: [],          // current page of products
            catalogPage: 1,
            catalogTotalCount: 0,
            catalogCart: {},              // { productId: { qty, name, uom } }
            catalogLoading: false,

            // ── Add Work Order ────────────────────────────────────────────────
            showAddWorkOrderModal: false,
            addWorkOrderMoId: null,
            addWorkOrderInsertAfterId: null,   // workorder id to insert after
            addWorkOrderTitle: "",
            addWorkOrderWorkcenterId: null,
            addWorkOrderDurationMin: 0,        // stored in minutes internally
            addWorkOrderDateStart: "",
            addWorkOrderOperations: [],        // workorders of current MO
            addWorkOrderWorkcentersList: [],

            // Log Note modal
            showLogNoteModal: false,
            logNoteMoId: null,
            logNoteText: "",
        });

        // Opened from a work center card (Manufacturing > Overview): land on its tab,
        // adding it to this station's work centers when a selection is configured
        const workcenterId = this.props.action?.context?.default_workcenter_id;
        if (workcenterId) {
            const station = this.state.stationWorkcenterIds;
            if (station.length && !station.includes(workcenterId)) {
                this.state.stationWorkcenterIds = [...station, workcenterId];
                saveIds(STATION_KEY, this.state.stationWorkcenterIds);
            }
            this.state.tab = workcenterId;
        }

        onWillStart(async () => {
            await this.loadEmployees();
            await this.reload();
        });

        this.timerInterval = setInterval(() => {
            this.state.currentTime = new Date();
        }, 1000);
        this.refreshInterval = setInterval(() => {
            if (!this.anyModalOpen) {
                this.reload();
                this.loadEmployees();
            }
        }, REFRESH_INTERVAL);

        onWillDestroy(() => {
            clearInterval(this.timerInterval);
            clearInterval(this.refreshInterval);
            clearTimeout(this.searchTimeout);
        });
    }

    // =========================================================
    // Helpers
    // =========================================================

    get anyModalOpen() {
        const s = this.state;
        return s.showOptionsModal || s.showRegisterQtyModal || s.showComponentModal ||
            s.showCatalogModal || s.showAddWorkOrderModal || s.showLogNoteModal ||
            s.showPinModal || !!s.selectModal;
    }

    get tabs() {
        return [
            { id: "overview", name: "Overview", count: this.state.overviewCount, color: 0 },
            { id: "my_wo", name: "My WO", count: this.state.myWoCount, color: 0 },
            ...this.state.workcenters,
        ];
    }

    // Badge colour of a workcenter (tab counter + WO tag), from its Odoo color index
    getWorkcenterColorClass(workcenterId) {
        const wc = this.state.workcenters.find(w => w.id === workcenterId);
        return `sf-color-${(wc && wc.color) || 0}`;
    }

    getStatusBadge(mo) {
        if (mo.state === "to_close") return { label: "To Close", cls: "sf-badge-to-close" };
        if (mo.state === "progress") return { label: "In Progress", cls: "sf-badge-progress" };
        return { label: mo.state_label || "Confirmed", cls: "sf-badge-confirmed" };
    }

    pendingWorkorders(mo) {
        return mo.workorders.filter(wo => wo.state !== "done");
    }

    formatQty(qty) {
        qty = Number(qty) || 0;
        return Number.isInteger(qty) ? qty : parseFloat(qty.toFixed(3));
    }

    // Elapsed time on a work order: closed time lines + the running one
    woElapsedSeconds(wo) {
        let seconds = (wo.duration_closed || 0) * 60;
        const start = parseServerDatetime(wo.timer_start);
        if (wo.is_running && start) {
            seconds += (this.state.currentTime - start) / 1000;
        }
        return seconds;
    }

    formatWoTimer(wo) {
        const elapsed = formatSeconds(this.woElapsedSeconds(wo));
        return wo.duration_expected ? `${elapsed} / ${formatSeconds(wo.duration_expected * 60)}` : elapsed;
    }

    employeeSince(emp) {
        const start = parseServerDatetime(emp.working_since);
        return start ? formatSeconds((this.state.currentTime - start) / 1000) : "";
    }

    // Run an action returned by the server (wizard, details...) then refresh
    async handleResult(result) {
        if (result && typeof result === "object" && result.type) {
            await this.action.doAction(result, { onClose: () => this.refreshAll() });
        }
        await this.refreshAll();
    }

    async refreshAll() {
        await Promise.all([this.reload(), this.loadEmployees()]);
    }

    confirm(body, confirmLabel) {
        return new Promise((resolve) => {
            this.dialog.add(ConfirmationDialog, {
                body,
                confirmLabel,
                confirm: () => resolve(true),
                cancel: () => resolve(false),
            }, { onClose: () => resolve(false) });
        });
    }

    // =========================================================
    // Search & Filter panel
    // =========================================================

    closeAllPanels() {
        this.state.showFilterPanel = false;
        this.state.showHamburgerPanel = false;
    }

    toggleFilterPanel(ev) {
        if (ev) ev.stopPropagation();
        const wasOpen = this.state.showFilterPanel;
        this.closeAllPanels();
        this.state.showFilterPanel = !wasOpen;
    }

    openFilterPanel() {
        this.state.showHamburgerPanel = false;
        this.state.showFilterPanel = true;
    }

    toggleHamburgerPanel(ev) {
        if (ev) ev.stopPropagation();
        const wasOpen = this.state.showHamburgerPanel;
        this.closeAllPanels();
        this.state.showHamburgerPanel = !wasOpen;
    }

    // MO filters shown as one facet in the search bar, like Odoo's search view
    get moFacetValues() {
        const values = [];
        if (this.state.filterMoPending) values.push("MO Pending");
        if (this.state.filterMoReady) values.push("MO Ready");
        if (this.state.filterThisStation) values.push("This Station");
        return values;
    }

    get filterItems() {
        return [
            { key: "mo_pending", label: "MO Pending", active: this.state.filterMoPending },
            { key: "mo_ready", label: "MO Ready", active: this.state.filterMoReady },
            { key: "this_station", label: "This Station", active: this.state.filterThisStation },
        ];
    }

    get woFilterItems() {
        return [
            { key: "wo_todo", label: "To Do", active: this.state.filterWoToDo },
            { key: "wo_blocked", label: "Blocked", active: this.state.filterWoBlocked },
            { key: "wo_progress", label: "In Progress", active: this.state.filterWoInProgress },
        ];
    }

    toggleMoFilter(key) {
        if (key === "mo_ready") this.state.filterMoReady = !this.state.filterMoReady;
        if (key === "mo_pending") this.state.filterMoPending = !this.state.filterMoPending;
        if (key === "this_station") this.state.filterThisStation = !this.state.filterThisStation;
        this.reload();
    }

    toggleWoFilter(key) {
        if (key === "wo_todo") this.state.filterWoToDo = !this.state.filterWoToDo;
        if (key === "wo_blocked") this.state.filterWoBlocked = !this.state.filterWoBlocked;
        if (key === "wo_progress") this.state.filterWoInProgress = !this.state.filterWoInProgress;
        this.reload();
    }

    removeMoFacet() {
        this.state.filterMoReady = false;
        this.state.filterMoPending = false;
        this.state.filterThisStation = false;
        this.reload();
    }

    onSearchInput(ev) {
        this.state.searchQuery = ev.target.value;
        clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => this.reload(), 300);
    }

    onSearchKeydown(ev) {
        if (ev.key === "Backspace" && !ev.target.value && this.moFacetValues.length) {
            this.removeMoFacet();
        } else if (ev.key === "Escape") {
            this.closeAllPanels();
        }
    }

    // =========================================================
    // Core data loading
    // =========================================================

    async reload() {
        const woStates = [];
        if (this.state.filterWoToDo) woStates.push("ready");
        if (this.state.filterWoBlocked) woStates.push("blocked");
        if (this.state.filterWoInProgress) woStates.push("progress");

        const data = await this.orm.call("mrp.production", "get_shopfloor_data", [{
            tab: this.state.tab,
            employee_id: this.state.activeEmployee ? this.state.activeEmployee.id : false,
            mo_ready: this.state.filterMoReady,
            mo_pending: this.state.filterMoPending,
            this_station: this.state.filterThisStation,
            station_workcenter_ids: this.state.stationWorkcenterIds,
            wo_states: woStates,
            search: this.state.searchQuery,
        }]);
        this.state.workcenters = data.workcenters;
        this.state.overviewCount = data.overview_count;
        this.state.myWoCount = data.my_wo_count;
        this.state.productions = data.productions;
        this.state.workorders = data.workorders;
    }

    async loadEmployees() {
        const employees = await this.orm.call("hr.employee", "get_shopfloor_employees", [
            this.state.panelEmployeeIds,
        ]);
        this.state.employees = employees;
        if (this.state.activeEmployee) {
            this.state.activeEmployee = employees.find(e => e.id === this.state.activeEmployee.id) || null;
        }
    }

    async selectTab(tabId) {
        this.state.tab = tabId;
        this.state.highlightWoId = null;
        await this.reload();
    }

    // From an MO card: jump to the work order in its work center
    async openWorkorder(wo) {
        this.state.tab = wo.workcenter_id[0];
        await this.reload();
        this.state.highlightWoId = wo.id;
    }

    // =========================================================
    // Station configuration (work centers / operators shown here)
    // =========================================================

    async openWorkcenterSelection() {
        this.closeAllPanels();
        const all = await this.orm.searchRead("mrp.workcenter", [], ["id", "name"], { order: "sequence, id" });
        const current = this.state.stationWorkcenterIds.length
            ? this.state.stationWorkcenterIds
            : this.state.workcenters.map(wc => wc.id);
        this.state.selectModal = {
            title: "Work Centers on this station",
            items: all,
            selected: [...current],
            onSave: async (ids) => {
                this.state.stationWorkcenterIds = ids;
                saveIds(STATION_KEY, ids);
                if (typeof this.state.tab === "number" && !ids.includes(this.state.tab)) {
                    this.state.tab = "overview";
                }
                await this.reload();
            },
        };
    }

    async openEmployeeSelection() {
        const all = await this.orm.searchRead("hr.employee", [], ["id", "name"], { order: "name" });
        this.state.selectModal = {
            title: "Operators on this station",
            items: all,
            selected: this.state.employees.map(e => e.id),
            onSave: async (ids) => {
                this.state.panelEmployeeIds = ids;
                saveIds(EMPLOYEES_KEY, ids);
                await this.loadEmployees();
            },
        };
    }

    toggleSelectItem(id) {
        const modal = this.state.selectModal;
        modal.selected = modal.selected.includes(id)
            ? modal.selected.filter(x => x !== id)
            : [...modal.selected, id];
    }

    closeSelectModal() {
        this.state.selectModal = null;
    }

    async saveSelectModal() {
        const { selected, onSave } = this.state.selectModal;
        this.state.selectModal = null;
        await onSave(selected);
    }

    // =========================================================
    // Operators (with optional PIN)
    // =========================================================

    async clickEmployee(emp) {
        if (this.state.activeEmployee && this.state.activeEmployee.id === emp.id) {
            await this.logoutEmployee();
            return;
        }
        if (emp.has_pin) {
            this.state.pinEmployee = emp;
            this.state.pinValue = "";
            this.state.showPinModal = true;
            return;
        }
        await this.setActiveEmployee(emp);
    }

    async setActiveEmployee(emp) {
        this.state.activeEmployee = emp;
        await this.reload();
    }

    async logoutEmployee() {
        this.state.activeEmployee = null;
        this.closeAllPanels();
        await this.reload();
    }

    pinPress(key) {
        if (key === "back") {
            this.state.pinValue = this.state.pinValue.slice(0, -1);
        } else {
            this.state.pinValue += key;
        }
    }

    closePinModal() {
        this.state.showPinModal = false;
        this.state.pinEmployee = null;
        this.state.pinValue = "";
    }

    async submitPin() {
        const emp = this.state.pinEmployee;
        const ok = await this.orm.call("hr.employee", "check_shopfloor_pin", [emp.id, this.state.pinValue]);
        if (!ok) {
            this.notification.add("Wrong PIN", { type: "danger" });
            this.state.pinValue = "";
            return;
        }
        this.closePinModal();
        await this.setActiveEmployee(emp);
    }

    // =========================================================
    // Work order flow
    // =========================================================

    get employeeId() {
        return this.state.activeEmployee ? this.state.activeEmployee.id : false;
    }

    async toggleTimer(wo) {
        if (wo.state === "blocked") {
            this.notification.add("This work order is waiting for a previous operation.", { type: "warning" });
            return;
        }
        const method = wo.me_running ? "shopfloor_pause" : "shopfloor_start";
        await this.orm.call("mrp.workorder", method, [[wo.id]], { employee_id: this.employeeId });
        await this.refreshAll();
    }

    async markWorkorderDone(wo) {
        const result = await this.orm.call("mrp.workorder", "shopfloor_mark_done", [[wo.id]]);
        await this.handleResult(result);
    }

    async closeProductionFromWorkorder(wo) {
        const result = await this.orm.call("mrp.workorder", "shopfloor_close_production", [[wo.id]]);
        if (result === true) {
            this.notification.add(`${wo.production_id[1]} is done.`, { type: "success" });
        }
        await this.handleResult(result);
    }

    // =========================================================
    // Manufacturing order flow
    // =========================================================

    moMainButtonLabel(mo) {
        return mo.qty_producing > 0 || mo.state === "to_close" ? "Close Production" : "Produce";
    }

    // Produce / Close Production: registers the full quantity when nothing was
    // registered, finishes the remaining work orders and closes the MO.
    async closeProduction(mo) {
        const pending = this.pendingWorkorders(mo);
        if (pending.length) {
            const ok = await this.confirm(
                `${pending.length} operation(s) of ${mo.name} are not done yet. ` +
                "They will be marked as done with their expected duration.",
                "Produce"
            );
            if (!ok) return;
        }
        const result = await this.orm.call("mrp.production", "shopfloor_close_production", [[mo.id]]);
        if (result === true) {
            this.notification.add(`${mo.name} is done.`, { type: "success" });
        }
        await this.handleResult(result);
    }

    // Component line: register the full quantity in one tap
    async registerComponentFull(moId, move) {
        const result = await this.orm.call("mrp.production", "shopfloor_register_component", [[moId], move.id]);
        await this.handleResult(result);
    }

    async openComponentModal(moId, move) {
        if (move.tracking === "lot" || move.tracking === "serial") {
            // Tracked component: Odoo's detailed operations (lots / serials)
            await this.registerComponentFull(moId, move);
            return;
        }
        this.state.componentMoId = moId;
        this.state.componentMove = move;
        this.state.componentQty = move.picked ? move.quantity : move.product_uom_qty;
        this.state.showComponentModal = true;
    }

    closeComponentModal() {
        this.state.showComponentModal = false;
        this.state.componentMoId = null;
        this.state.componentMove = null;
    }

    async submitComponentModal() {
        const qty = parseFloat(this.state.componentQty);
        if (isNaN(qty) || qty < 0) {
            this.notification.add("Please enter a valid quantity", { type: "warning" });
            return;
        }
        const { componentMoId, componentMove } = this.state;
        this.closeComponentModal();
        const result = await this.orm.call(
            "mrp.production", "shopfloor_register_component", [[componentMoId], componentMove.id, qty]
        );
        await this.handleResult(result);
    }

    async actionScrap(moId, woId) {
        this.closeOptionsModal();
        const result = woId
            ? await this.orm.call("mrp.workorder", "action_scrap", [[woId]])
            : await this.orm.call("mrp.production", "action_scrap", [[moId]]);
        await this.handleResult(result);
    }

    actionOpenMO(moId) {
        this.closeOptionsModal();
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "mrp.production",
            res_id: moId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // =========================================================
    // Options modal (opened by ⋮ kebab button)
    // =========================================================

    openOptionsModal(moId, woId = null) {
        this.closeAllPanels();
        this.state.optionsMoId = moId;
        this.state.optionsWoId = woId;
        this.state.showOptionsModal = true;
    }

    closeOptionsModal() {
        this.state.showOptionsModal = false;
        this.state.optionsMoId = null;
        this.state.optionsWoId = null;
    }

    // =========================================================
    // Register Production (quantity / lot / serial)
    // =========================================================

    async openRegisterQtyModal(moId) {
        this.closeOptionsModal();
        const [mo] = await this.orm.read("mrp.production", [moId], [
            "name", "product_id", "product_qty", "qty_producing", "product_tracking", "uom_id", "lot_producing_ids",
        ]);
        let lotName = "";
        if (mo.lot_producing_ids.length === 1) {
            const [lot] = await this.orm.read("stock.lot", mo.lot_producing_ids, ["name"]);
            lotName = lot.name;
        }
        this.state.registerMo = {
            id: mo.id,
            name: mo.name,
            product: mo.product_id[1],
            uom: mo.uom_id[1],
            tracking: mo.product_tracking,
            qty_production: mo.product_qty,
        };
        this.state.registerQtyValue = mo.qty_producing || mo.product_qty;
        this.state.registerLotName = lotName;
        this.state.showRegisterQtyModal = true;
    }

    closeRegisterQtyModal() {
        this.state.showRegisterQtyModal = false;
        this.state.registerMo = null;
    }

    async submitRegisterQty() {
        const qty = parseFloat(this.state.registerQtyValue);
        if (!(qty > 0)) {
            this.notification.add("Please enter a quantity greater than 0", { type: "warning" });
            return;
        }
        const moId = this.state.registerMo.id;
        const lotName = this.state.registerLotName.trim() || false;
        this.closeRegisterQtyModal();
        const result = await this.orm.call(
            "mrp.production", "shopfloor_register_production", [[moId], qty, lotName]
        );
        if (result === true) {
            this.notification.add("Production registered", { type: "success" });
        }
        await this.handleResult(result);
    }

    // =========================================================
    // Product Catalog (Add Component)
    // =========================================================

    async openCatalogModal(moId, woId = null) {
        this.closeOptionsModal();
        this.state.catalogMoId = moId;
        this.state.catalogWoId = woId;
        this.state.catalogSearch = "";
        this.state.catalogSelectedCat = null;
        this.state.catalogSelectedTag = null;
        this.state.catalogPage = 1;
        this.state.catalogCart = {};
        this.state.catalogLoading = true;
        this.state.showCatalogModal = true;

        const [cats, tags] = await Promise.all([
            this.orm.searchRead("product.category", [], ["id", "name", "parent_id"], { order: "complete_name asc" }),
            this.orm.searchRead("product.tag", [], ["id", "name"], { limit: 50 }).catch(() => []),
        ]);
        this.state.catalogCategories = cats;
        this.state.catalogTags = tags;

        await this._loadCatalogPage();
        this.state.catalogLoading = false;
    }

    closeCatalogModal() {
        this.state.showCatalogModal = false;
        this.state.catalogMoId = null;
        this.state.catalogWoId = null;
        this.state.catalogCart = {};
        this.state.catalogProducts = [];
    }

    _buildCatalogDomain() {
        const domain = [["type", "=", "consu"]];
        if (this.state.catalogSelectedCat) {
            domain.push(["categ_id", "child_of", this.state.catalogSelectedCat]);
        }
        if (this.state.catalogSelectedTag) {
            domain.push(["product_tag_ids", "in", [this.state.catalogSelectedTag]]);
        }
        const q = this.state.catalogSearch.trim();
        if (q) {
            domain.push("|", ["name", "ilike", q], ["default_code", "ilike", q]);
        }
        return domain;
    }

    async _loadCatalogPage() {
        const domain = this._buildCatalogDomain();
        const offset = (this.state.catalogPage - 1) * 40;

        const [count, products] = await Promise.all([
            this.orm.call("product.product", "search_count", [domain]),
            this.orm.searchRead(
                "product.product", domain,
                ["id", "name", "display_name", "default_code", "qty_available", "virtual_available", "uom_id", "categ_id"],
                { limit: 40, offset, order: "name asc" }
            ),
        ]);
        this.state.catalogTotalCount = count;
        this.state.catalogProducts = products;
    }

    async catalogSelectCategory(catId) {
        this.state.catalogSelectedCat = catId;
        this.state.catalogSelectedTag = null;
        this.state.catalogPage = 1;
        this.state.catalogLoading = true;
        await this._loadCatalogPage();
        this.state.catalogLoading = false;
    }

    async catalogSelectTag(tagId) {
        this.state.catalogSelectedTag = tagId;
        this.state.catalogSelectedCat = null;
        this.state.catalogPage = 1;
        this.state.catalogLoading = true;
        await this._loadCatalogPage();
        this.state.catalogLoading = false;
    }

    async onCatalogSearchInput(ev) {
        this.state.catalogSearch = ev.target.value;
        this.state.catalogPage = 1;
        this.state.catalogLoading = true;
        await this._loadCatalogPage();
        this.state.catalogLoading = false;
    }

    async catalogPrevPage() {
        if (this.state.catalogPage > 1) {
            this.state.catalogPage -= 1;
            this.state.catalogLoading = true;
            await this._loadCatalogPage();
            this.state.catalogLoading = false;
        }
    }

    async catalogNextPage() {
        if (this.state.catalogPage * 40 < this.state.catalogTotalCount) {
            this.state.catalogPage += 1;
            this.state.catalogLoading = true;
            await this._loadCatalogPage();
            this.state.catalogLoading = false;
        }
    }

    get catalogCartCount() {
        return Object.keys(this.state.catalogCart).length;
    }

    get catalogPageStart() {
        return (this.state.catalogPage - 1) * 40 + 1;
    }

    get catalogPageEnd() {
        return Math.min(this.state.catalogPage * 40, this.state.catalogTotalCount);
    }

    catalogIsInCart(productId) {
        return !!this.state.catalogCart[productId];
    }

    catalogGetQty(productId) {
        return this.state.catalogCart[productId] ? this.state.catalogCart[productId].qty : 0;
    }

    catalogGetUom(productId) {
        return this.state.catalogCart[productId] ? this.state.catalogCart[productId].uom : "Units";
    }

    catalogAddToCart(product) {
        if (this.state.catalogCart[product.id]) {
            this.state.catalogCart[product.id].qty += 1;
        } else {
            this.state.catalogCart[product.id] = {
                qty: 1,
                name: product.display_name || product.name,
                uom: product.uom_id ? product.uom_id[1] : "Units",
                productId: product.id,
            };
        }
    }

    catalogIncreaseQty(productId) {
        if (this.state.catalogCart[productId]) this.state.catalogCart[productId].qty += 1;
    }

    catalogDecreaseQty(productId) {
        if (!this.state.catalogCart[productId]) return;
        if (this.state.catalogCart[productId].qty > 1) {
            this.state.catalogCart[productId].qty -= 1;
        } else {
            this.catalogRemoveFromCart(productId);
        }
    }

    catalogRemoveFromCart(productId) {
        const newCart = {};
        for (const [k, v] of Object.entries(this.state.catalogCart)) {
            if (parseInt(k) !== productId) newCart[k] = v;
        }
        this.state.catalogCart = newCart;
    }

    catalogSetQty(productId, ev) {
        const val = parseFloat(ev.target.value) || 1;
        if (this.state.catalogCart[productId]) {
            this.state.catalogCart[productId].qty = Math.max(1, val);
        }
    }

    async submitCatalog() {
        const items = Object.values(this.state.catalogCart);
        if (items.length === 0) {
            this.notification.add("No products selected", { type: "warning" });
            return;
        }
        const { catalogMoId, catalogWoId } = this.state;
        await this.orm.call("mrp.production", "shopfloor_add_components", [
            [catalogMoId],
            items.map(item => ({ product_id: item.productId, qty: item.qty })),
            catalogWoId || false,
        ]);
        this.notification.add(`${items.length} component(s) added.`, { type: "success" });
        this.closeCatalogModal();
        await this.reload();
    }

    // =========================================================
    // Add Work Order
    // =========================================================

    async openAddWorkOrderModal(moId) {
        this.closeOptionsModal();
        const workorders = await this.orm.searchRead(
            "mrp.workorder", [["production_id", "=", moId]], ["id", "name", "sequence"], { order: "sequence, id" }
        );

        this.state.addWorkOrderMoId = moId;
        this.state.addWorkOrderTitle = "";
        this.state.addWorkOrderWorkcenterId = null;
        this.state.addWorkOrderDurationMin = 0;
        this.state.addWorkOrderDateStart = "";
        this.state.addWorkOrderOperations = workorders;
        this.state.addWorkOrderInsertAfterId = workorders.length ? workorders[workorders.length - 1].id : null;
        this.state.addWorkOrderWorkcentersList = await this.orm.searchRead(
            "mrp.workcenter", [], ["id", "name"], { order: "sequence, id" }
        );
        this.state.showAddWorkOrderModal = true;
    }

    closeAddWorkOrderModal() {
        this.state.showAddWorkOrderModal = false;
        this.state.addWorkOrderMoId = null;
    }

    onAddWorkOrderWcChange(ev) {
        this.state.addWorkOrderWorkcenterId = parseInt(ev.target.value) || null;
    }

    onAddWorkOrderInsertAfterChange(ev) {
        this.state.addWorkOrderInsertAfterId = parseInt(ev.target.value) || null;
    }

    async submitAddWorkOrder() {
        if (!this.state.addWorkOrderTitle.trim()) {
            this.notification.add("Please enter a title", { type: "warning" });
            return;
        }
        if (!this.state.addWorkOrderWorkcenterId) {
            this.notification.add("Please select a work center", { type: "warning" });
            return;
        }
        const after = this.state.addWorkOrderOperations.find(wo => wo.id === this.state.addWorkOrderInsertAfterId);
        const vals = {
            name: this.state.addWorkOrderTitle.trim(),
            production_id: this.state.addWorkOrderMoId,
            workcenter_id: this.state.addWorkOrderWorkcenterId,
            duration_expected: parseInt(this.state.addWorkOrderDurationMin) || 0,
            sequence: after ? after.sequence + 1 : 0,
        };
        if (this.state.addWorkOrderDateStart) {
            // datetime-local is in the browser's timezone, the server expects UTC
            vals.date_start = new Date(this.state.addWorkOrderDateStart).toISOString().replace("T", " ").slice(0, 19);
        }
        await this.orm.create("mrp.workorder", [vals]);
        this.notification.add("Work order added", { type: "success" });
        this.closeAddWorkOrderModal();
        await this.reload();
    }

    // =========================================================
    // Log Note
    // =========================================================

    openLogNoteModal(moId) {
        this.closeOptionsModal();
        this.state.logNoteMoId = moId;
        this.state.logNoteText = "";
        this.state.showLogNoteModal = true;
    }

    closeLogNoteModal() {
        this.state.showLogNoteModal = false;
        this.state.logNoteMoId = null;
        this.state.logNoteText = "";
    }

    async submitLogNote() {
        if (!this.state.logNoteText.trim()) {
            this.notification.add("Please enter a note", { type: "warning" });
            return;
        }
        await this.orm.call("mrp.production", "message_post", [[this.state.logNoteMoId]], {
            body: this.state.logNoteText.trim(),
            message_type: "comment",
            subtype_xmlid: "mail.mt_note",
        });
        this.notification.add("Note logged", { type: "success" });
        this.closeLogNoteModal();
    }
}

registry.category("actions").add("hudson_shopfloor.shopfloor_app", ShopFloorApp);
