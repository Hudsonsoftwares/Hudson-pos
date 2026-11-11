/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";

// Buttons that generate payslips: show the full-screen loading overlay instead
// of leaving the dialog visible while the server works.
const PAYSLIP_GENERATION_BUTTONS = {
    "hr.payslip.employees": ["action_select"],
    "hr.salary.adjustment.wizard": ["action_create_adjustments"],
};

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.uiService = useService("ui");
    },

    async beforeExecuteActionButton(clickParams) {
        const result = await super.beforeExecuteActionButton(...arguments);
        const buttons = PAYSLIP_GENERATION_BUTTONS[this.model.root.resModel];
        if (result !== false && buttons?.includes(clickParams.name)) {
            this.uiService.block({ message: _t("Generating payslips...") });
            this._payslipGenerationBlocked = true;
        }
        return result;
    },

    async afterExecuteActionButton(clickParams) {
        if (this._payslipGenerationBlocked) {
            this._payslipGenerationBlocked = false;
            this.uiService.unblock();
        }
        return super.afterExecuteActionButton(...arguments);
    },
});
