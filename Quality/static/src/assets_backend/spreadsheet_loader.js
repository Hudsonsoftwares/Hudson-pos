/** @odoo-module **/
import { addSpreadsheetActionLazyLoader } from "@spreadsheet/assets_backend/spreadsheet_action_loader";
import { _t } from "@web/core/l10n/translation";

addSpreadsheetActionLazyLoader("action_quality_spreadsheet", "quality_spreadsheet", _t("Quality Spreadsheet"));
