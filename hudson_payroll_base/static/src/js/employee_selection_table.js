/** @odoo-module **/

import { onMounted, onWillUpdateProps, proxy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { useService } from "@web/core/utils/hooks";

export class EmployeeSelectionTableField extends X2ManyField {
    static components = {
        ...X2ManyField.components,
    };
    static template = "hudson_payroll_base.EmployeeSelectionTableField";

    setup() {
        super.setup();
        this.actionService = useService("action");
        this.notificationService = useService("notification");
        this.state = proxy({ searchTerm: "" });
        this._hasInitializedSelection = false;

        this.patchList(this.list);

        onMounted(() => {
            this.patchList(this.list);
            this.initSelection();
        });

        onWillUpdateProps(() => {
            this.patchList(this.list);
            if (!this._hasInitializedSelection && this.list?.records?.length > 0) {
                this.initSelection();
            }
        });
    }

    patchList(list) {
        if (!list) return;

        // 1. Hook master selection toggle
        list.toggleSelection = () => {
            const anySelected = (list.records || []).some((r) => r.selected);
            for (const record of list.records || []) {
                if (typeof record._toggleSelection === "function") {
                    record._toggleSelection(!anySelected);
                } else {
                    record.selected = !anySelected;
                }
            }
            this.syncSelected();
        };

        // 2. Hook unselectAll for header badge
        list.unselectAll = () => {
            for (const record of list.records || []) {
                if (typeof record._toggleSelection === "function") {
                    record._toggleSelection(false);
                } else {
                    record.selected = false;
                }
            }
            this.syncSelected();
        };

        // 3. Hook each individual record's _toggleSelection so row clicks/checkbox clicks immediately sync
        for (const record of list.records || []) {
            if (!record._syncPatched) {
                record._syncPatched = true;
                const orig = record._toggleSelection ? record._toggleSelection.bind(record) : null;
                if (orig) {
                    record._toggleSelection = (selected) => {
                        orig(selected);
                        this.syncSelected();
                    };
                }
            }
        }

        try {
            Object.defineProperty(list, "selection", {
                get: () => (list.records || []).filter((r) => r.selected),
                configurable: true,
            });
        } catch (e) {
            // Already defined
        }
    }

    initSelection() {
        if (!this.list || !this.list.records || !this.list.records.length) {
            return;
        }
        // Restore ticks already saved on the wizard (e.g. when coming back from Payslip Adjustment);
        // a fresh wizard has an empty list, so everything starts unchecked.
        let savedIds = [];
        try {
            savedIds = JSON.parse(this.props.record?.data?.selected_employee_ids_json || "[]");
        } catch {
            savedIds = [];
        }
        for (const record of this.list.records) {
            const selected = Array.isArray(savedIds) && savedIds.includes(record.resId);
            if (typeof record._toggleSelection === "function") {
                record._toggleSelection(selected);
            } else {
                record.selected = selected;
            }
        }
        this._hasInitializedSelection = true;
        this.syncSelected();
    }

    get rendererProps() {
        this.patchList(this.list);
        const props = super.rendererProps;
        // Standard Odoo prop on ListRenderer to show checkboxes
        props.allowSelectors = true;
        return props;
    }

    get hasSelectedRecords() {
        return this.selectedCount > 0;
    }

    get selectedCount() {
        return (this.list?.records || []).filter((r) => r.selected).length;
    }

    get totalCount() {
        return this.list?.count || this.list?.records?.length || 0;
    }

    syncSelected() {
        if (!this.list) return;
        const selectedRecords = (this.list.records || []).filter((r) => r.selected);
        const selectedIds = selectedRecords
            .map((r) => r.resId || (r.data && r.data.id))
            .filter((id) => typeof id === "number" && id > 0);

        if (this.props.record) {
            if (this.props.record.data) {
                this.props.record.data.selected_employee_ids_json = JSON.stringify(selectedIds);
            }
            try {
                this.props.record.update({
                    selected_employee_ids_json: JSON.stringify(selectedIds),
                });
            } catch (err) {
                // Ignore benign concurrency
            }
        }
    }

    onUnselectAll(ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        if (!this.list) return;
        this.list.unselectAll();
    }

    onSearchInput(ev) {
        const val = (ev.target.value || "").trim().toLowerCase();
        this.state.searchTerm = val;
        const rows = document.querySelectorAll(".o_dialog .o_list_table tbody tr.o_data_row");
        rows.forEach((row) => {
            const text = (row.textContent || "").toLowerCase();
            if (!val || text.includes(val)) {
                row.style.display = "";
            } else {
                row.style.display = "none";
            }
        });
    }

    async onHeaderAction(actionName) {
        if (this.props.record && actionName) {
            this.syncSelected();
            // Persist the latest ticks so the server reads an up-to-date selection
            await this.props.record.save();
            const res = await this.props.record.model.orm.call(
                this.props.record.resModel,
                actionName,
                [this.props.record.resId],
                { context: this.props.context }
            );
            if (res && typeof res === "object") {
                const options = {};
                if (actionName === "action_launch_plan") {
                    // Opening Launch Plan replaces this dialog; bring it back (ticks kept) once the plan wizard closes
                    const { resModel, resId } = this.props.record;
                    const orm = this.props.record.model.orm;
                    const actionService = this.actionService;
                    options.onClose = async () => {
                        const reopen = await orm.call(resModel, "action_reopen_selection", [[resId]]);
                        if (reopen && typeof reopen === "object") {
                            await actionService.doAction(reopen);
                        }
                    };
                }
                this.actionService.doAction(res, options);
            }
        }
    }
}

export const employeeSelectionTableField = {
    ...x2ManyField,
    component: EmployeeSelectionTableField,
};

registry.category("fields").add("employee_selection_table", employeeSelectionTableField);
