// /** ********************************************************************************
//     Copyright 2024 Subteno - Timothée Vannier (https://www.subteno.com).
//     License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl).
//  **********************************************************************************/
import {Component, onWillUpdateProps, useProps} from "@odoo/owl";
import {_t} from "@web/core/l10n/translation";
import {registry} from "@web/core/registry";
import {standardFieldProps} from "@web/views/fields/standard_field_props";
import {useService} from "@web/core/utils/hooks";

class DmsPathField extends Component {
    static template = "dms.DmsPathField";
    props = useProps(standardFieldProps);

    setup() {
        super.setup();
        this.action = useService("action");
    }

    get data() {
        const val = this.props.record?.data?.[this.props.name] || this.props.record?.data?.path_json;
        if (!val) {
            return [];
        }
        try {
            return typeof val === "string" ? JSON.parse(val) : (Array.isArray(val) ? val : []);
        } catch {
            return [];
        }
    }

    _onNodeClicked(event) {
        event.preventDefault();
        const target = event.currentTarget;
        const resModel = target.getAttribute("data-model");
        const resId = Number(target.getAttribute("data-id"));
        if (resModel && resId) {
            this.action.doAction({
                type: "ir.actions.act_window",
                res_model: resModel,
                res_id: resId,
                views: [[false, "form"]],
                target: "current",
                context: {},
            });
        }
    }
}

const dmsPathField = {
    component: DmsPathField,
    displayName: _t("Dms Path Field"),
    supportedTypes: ["text"],
};

registry.category("fields").add("path_json", dmsPathField);
