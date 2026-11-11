/** @odoo-module **/

import { Reactive } from "@web/core/utils/reactive";
import { salaryComputationColumnsRegistry } from "./salary_computation_column_registry";

const STORAGE_KEY = "hudson_payroll_salary_comp_column_visibility_v1";

export class SalaryComputationColumnState {
    constructor() {
        this.visibilityMap = {};
        this.init();
    }

    init() {
        const stored = this.loadFromStorage();
        const registryEntries = salaryComputationColumnsRegistry.getAll();

        for (const col of registryEntries) {
            if (col.mandatory) {
                this.visibilityMap[col.name] = true;
            } else if (stored && stored[col.name] !== undefined) {
                this.visibilityMap[col.name] = Boolean(stored[col.name]);
            } else {
                this.visibilityMap[col.name] = Boolean(col.defaultVisible);
            }
        }
    }

    loadFromStorage() {
        try {
            const raw = window.localStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : null;
        } catch (e) {
            console.warn("Failed to load Salary Computation column visibility from localStorage", e);
            return null;
        }
    }

    saveToStorage() {
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(this.visibilityMap));
        } catch (e) {
            console.warn("Failed to save Salary Computation column visibility to localStorage", e);
        }
    }

    isColumnVisible(colName) {
        const colDef = salaryComputationColumnsRegistry.contains(colName)
            ? salaryComputationColumnsRegistry.get(colName)
            : null;

        if (colDef && colDef.mandatory) {
            return true;
        }

        if (this.visibilityMap[colName] !== undefined) {
            return this.visibilityMap[colName];
        }

        return colDef ? Boolean(colDef.defaultVisible) : true;
    }

    toggleColumn(colName) {
        const colDef = salaryComputationColumnsRegistry.contains(colName)
            ? salaryComputationColumnsRegistry.get(colName)
            : null;

        if (colDef && colDef.mandatory) {
            return;
        }

        const current = this.isColumnVisible(colName);
        this.visibilityMap[colName] = !current;
        this.saveToStorage();
    }

    resetToDefaults() {
        const registryEntries = salaryComputationColumnsRegistry.getAll();
        for (const col of registryEntries) {
            this.visibilityMap[col.name] = col.mandatory || col.defaultVisible;
        }
        this.saveToStorage();
    }

    getRegisteredColumns() {
        const entries = salaryComputationColumnsRegistry.getAll();
        return entries.sort((a, b) => (a.sequence || 50) - (b.sequence || 50));
    }
}
