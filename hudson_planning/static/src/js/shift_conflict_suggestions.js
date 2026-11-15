/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, t, useProps } from "@odoo/owl";

const { DateTime } = luxon;

/**
 * Suggestions of a shift in conflict (``conflict_suggestions``): employees
 * with the role of the shift free at that time, or on the nearest free day.
 * Clicking one moves the shift there in the form (saved with the form).
 *
 * Option ``replacement``: suggestions for a shift whose employee asked to be
 * replaced (``replacement_suggestions``); clicking one gives the shift to that
 * employee and saves at once.
 */
export class ShiftConflictSuggestionsField extends Component {
    static template = "hudson_planning.ShiftConflictSuggestions";
    props = useProps({
        ...standardFieldProps,
        replacement: t.boolean().optional(false),
    });

    get suggestions() {
        return (this.props.record.data[this.props.name] || []).map((suggestion) => {
            const start = deserializeDateTime(suggestion.date_start);
            const end = deserializeDateTime(suggestion.date_end);
            const time = (d) => d.toLocaleString(DateTime.TIME_SIMPLE).toLowerCase();
            return {
                ...suggestion,
                start,
                end,
                avatar: `/web/image/hr.employee.public/${suggestion.employee_id}/avatar_128`,
                when: suggestion.days
                    ? `${start.toFormat("ccc d LLL")}, ${time(start)} - ${time(end)}`
                    : _t("Same time"),
                action: suggestion.same_employee
                    ? _t("Move")
                    : this.props.replacement
                      ? _t("Replace")
                      : _t("Assign"),
            };
        });
    }

    get readonly() {
        return this.props.readonly;
    }

    async apply(suggestion) {
        await this.props.record.update({
            resource_id: { id: suggestion.employee_id, display_name: suggestion.employee_name },
            date_start: suggestion.start,
            date_end: suggestion.end,
        });
        if (this.props.replacement) {
            await this.props.record.save();
        }
    }
}

export const shiftConflictSuggestionsField = {
    component: ShiftConflictSuggestionsField,
    supportedTypes: ["json"],
    extractProps: ({ options }) => ({
        replacement: Boolean(options.replacement),
    }),
};

registry.category("fields").add("shift_conflict_suggestions", shiftConflictSuggestionsField);
