/** @odoo-module **/

import { Component, xml, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class DmsRevisionStatusField extends Component {
    static template = xml`
        <span t-if="this.isActive" class="badge rounded-pill text-bg-success">
            Active
        </span>
    `;
    props = useProps({
        ...standardFieldProps,
    });

    get isActive() {
        return !!(this.props.record && this.props.record.data && this.props.record.data[this.props.name]);
    }
}

export const dmsRevisionStatusField = {
    component: DmsRevisionStatusField,
    supportedTypes: ["boolean"],
};

registry.category("fields").add("dms_revision_status", dmsRevisionStatusField);
