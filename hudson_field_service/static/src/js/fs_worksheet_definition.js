/** @odoo-module **/

import { registry } from "@web/core/registry";
import {
    PropertiesDefinitionField,
    propertiesDefinitionField,
} from "@web/views/fields/properties/properties_definition_field";
import { PROPERTIES_INFO } from "@web/views/fields/properties/property_definition";

/**
 * Fields of a worksheet template, like Online: each field shows its type
 * (icon and label) where the job will show its value.
 */
export class FsWorksheetDefinitionField extends PropertiesDefinitionField {
    static template = "hudson_field_service.FsWorksheetDefinitionField";

    // The widget root is "o_field_fs_worksheet_definition", not "o_field_properties_definition"
    _getClosestField() {
        return this.propertiesRef().closest(".o_field_widget");
    }

    getTypeLabel(type) {
        return PROPERTIES_INFO[type]?.label || type;
    }
}

registry.category("fields").add("fs_worksheet_definition", {
    ...propertiesDefinitionField,
    component: FsWorksheetDefinitionField,
});
