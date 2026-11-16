/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { GeneratePrinterData } from "@point_of_sale/app/utils/printer/generate_printer_data";
import { generateQRCodeDataUrl } from "@point_of_sale/utils";

const SURVEY_FIELDS = ["show_survey_qr", "survey_url", "survey_message", "survey_qr_size"];
const DEFAULT_MESSAGE =
    "Thank you for coming! Scan the Customer Survey QR code to share your feedback and suggestions.";

// Survey settings fetched directly from the server when the POS starts, so the
// receipt does not depend on the company fields being part of the POS data load.
let surveySettings = null;

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        await this._loadSurveyQrSettings();
    },

    async _loadSurveyQrSettings() {
        const companyId = this.config?.company_id?.id || this.company?.id;
        if (!companyId || !this.data?.call) {
            return;
        }
        try {
            const [rec] = await this.data.call("res.company", "read", [[companyId], SURVEY_FIELDS]);
            surveySettings = rec || null;
        } catch (e) {
            console.warn("Survey QR: could not load company survey settings", e);
        }
    },
});

patch(GeneratePrinterData.prototype, {
    generateReceiptData() {
        const res = super.generateReceiptData(...arguments);
        res.conditions = res.conditions || {};
        res.image = res.image || {};
        res.extra_data = res.extra_data || {};
        res.conditions.show_survey_qr = false;
        res.image.survey_qr_code = false;
        res.extra_data.survey_message = "";
        res.extra_data.survey_qr_size = 32;

        const company = this.company || {};
        const pick = (field) => company[field] ?? surveySettings?.[field];

        const surveyUrl = (pick("survey_url") || "").trim();
        if (!pick("show_survey_qr") || !surveyUrl) {
            return res;
        }
        try {
            const qrCode = generateQRCodeDataUrl(surveyUrl);
            if (qrCode) {
                res.image.survey_qr_code = qrCode;
                res.conditions.show_survey_qr = true;
                res.extra_data.survey_message = pick("survey_message") || DEFAULT_MESSAGE;
                res.extra_data.survey_qr_size = pick("survey_qr_size") || 32;
            }
        } catch (e) {
            console.error("Survey QR: error generating QR code for receipt", e);
        }
        return res;
    },
});
