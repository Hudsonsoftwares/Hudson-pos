/** @odoo-module **/

import { registry } from "@web/core/registry";
import {
    BadgesMany2oneField,
    badgesMany2oneField,
} from "@web/views/fields/badges_many2one/badges_many2one_field";

/**
 * Shift templates on a shift: clicking a template always applies it (hours,
 * role, project...), also when it is already the shift's template, e.g. to
 * reset hours that were changed by hand. It is never "unselected".
 */
export class ShiftTemplateBadgesField extends BadgesMany2oneField {
    async onChange(value) {
        const current = this.value;
        if (value && value !== current) {
            return super.onChange(value);
        }
        if (!current) {
            return;
        }
        // Same template clicked again: set it anew so that it is applied again.
        const { record, name } = this.props;
        const template = { id: current, display_name: this.string };
        await record.update({ [name]: false });
        await record.update({ [name]: template });
    }
}

registry.category("fields").add("shift_template_badges", {
    ...badgesMany2oneField,
    component: ShiftTemplateBadgesField,
});
