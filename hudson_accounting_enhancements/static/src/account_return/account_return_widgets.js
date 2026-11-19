import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, useProps } from "@odoo/owl";

/**
 * Progress of a tax return (Reviewed -> Submitted -> Paid), rendered from the
 * `progress_steps` Json field.
 */
export class AccountReturnProgress extends Component {
    static template = "hudson_accounting_enhancements.AccountReturnProgress";
    props = useProps({ ...standardFieldProps });

    get steps() {
        return this.props.record.data[this.props.name] || [];
    }
}

registry.category("fields").add("account_return_progress", {
    component: AccountReturnProgress,
    supportedTypes: ["json"],
});

/**
 * Checklist cards of a tax return, rendered from the `checks_data` Json field.
 * Every action goes straight to the server, then the return is reloaded.
 */
export class AccountReturnChecks extends Component {
    static template = "hudson_accounting_enhancements.AccountReturnChecks";
    props = useProps({ ...standardFieldProps });

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
    }

    get checks() {
        return this.props.record.data[this.props.name] || [];
    }

    avatarUrl(check) {
        return `/web/image/res.users/${check.reviewer_id}/avatar_128`;
    }

    resultLabel(check) {
        return check.result === "reviewed" ? _t("Reviewed") : _t("To Review");
    }

    async ensureSaved() {
        if (this.props.record.isNew || this.props.record.dirty) {
            return this.props.record.save();
        }
        return true;
    }

    async toggle(check) {
        if (check.readonly || !(await this.ensureSaved())) {
            return;
        }
        await this.orm.call("account.return.check", "action_toggle_review", [[check.id]]);
        await this.props.record.load();
    }

    async saveNotes(check, value) {
        if (check.readonly || value === check.notes) {
            return;
        }
        await this.orm.call("account.return.check", "action_set_notes", [[check.id], value]);
        check.notes = value;
    }

    async openRecords(check) {
        if (!(await this.ensureSaved())) {
            return;
        }
        const action = await this.orm.call("account.return.check", "action_open_records", [[check.id]]);
        if (action) {
            await this.action.doAction(action);
        }
    }
}

registry.category("fields").add("account_return_checks", {
    component: AccountReturnChecks,
    supportedTypes: ["json"],
});
