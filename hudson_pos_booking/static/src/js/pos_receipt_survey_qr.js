/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { GeneratePrinterData } from "@point_of_sale/app/utils/printer/generate_printer_data";

patch(GeneratePrinterData.prototype, {
    generateReceiptData() {
        const res = super.generateReceiptData(...arguments);
        res.conditions = res.conditions || {};
        res.conditions.show_survey_qr = false;
        res.image = res.image || {};
        res.image.survey_qr_code = false;
        res.extra_data = res.extra_data || {};
        res.extra_data.survey_message = "";
        res.extra_data.survey_qr_size = 32;

        const company =
            this.company ||
            this.models?.["res.company"]?.get?.(odoo?.company_id) ||
            this.models?.["res.company"]?.getAll?.()?.[0] ||
            null;

        if (company && company.show_survey_qr && company.survey_url) {
            const url = (company.survey_url || "").trim();
            if (url) {
                const qrCode = this.generateQrCode(url);
                if (qrCode) {
                    res.image.survey_qr_code = qrCode;
                    res.conditions.show_survey_qr = true;
                    res.extra_data.survey_message =
                        company.survey_message ||
                        "Thank you for coming! Scan the QR code below to fill the survey and share your suggestions.";
                    res.extra_data.survey_qr_size = company.survey_qr_size || 32;
                }
            }
        }
        return res;
    },
});
