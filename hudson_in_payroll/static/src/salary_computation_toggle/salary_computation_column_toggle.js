/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";

export class SalaryComputationColumnToggle extends Component {
    static template = "hudson_in_payroll.SalaryComputationColumnToggle";
    static props = {
        columnState: Object,
        onVisibilityChange: Function,
    };

    setup() {
        this.dropdownRef = useRef("dropdownRef");
        this.buttonRef = useRef("buttonRef");

        this.state = useState({
            isOpen: false,
        });

        this.onDocumentClick = this.onDocumentClick.bind(this);
        this.onKeyDown = this.onKeyDown.bind(this);

        onMounted(() => {
            document.addEventListener("click", this.onDocumentClick, true);
            document.addEventListener("keydown", this.onKeyDown);
        });

        onWillUnmount(() => {
            document.removeEventListener("click", this.onDocumentClick, true);
            document.removeEventListener("keydown", this.onKeyDown);
        });
    }

    togglePopover(ev) {
        ev.stopPropagation();
        this.state.isOpen = !this.state.isOpen;
    }

    closePopover() {
        this.state.isOpen = false;
    }

    onDocumentClick(ev) {
        if (!this.state.isOpen) return;

        const dropdownEl = this.dropdownRef.el;
        const buttonEl = this.buttonRef.el;

        if (dropdownEl && dropdownEl.contains(ev.target)) {
            return;
        }

        if (buttonEl && buttonEl.contains(ev.target)) {
            return;
        }

        this.closePopover();
    }

    onKeyDown(ev) {
        if (ev.key === "Escape" && this.state.isOpen) {
            this.closePopover();
        }
    }

    get columns() {
        return this.props.columnState.getRegisteredColumns();
    }

    isColumnVisible(colName) {
        return this.props.columnState.isColumnVisible(colName);
    }

    onToggleColumn(colName, ev) {
        ev.stopPropagation();
        this.props.columnState.toggleColumn(colName);
        if (this.props.onVisibilityChange) {
            this.props.onVisibilityChange();
        }
    }

    onResetDefaults(ev) {
        ev.stopPropagation();
        this.props.columnState.resetToDefaults();
        if (this.props.onVisibilityChange) {
            this.props.onVisibilityChange();
        }
    }
}
