import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Balance Sheet: the equity was counted twice.

    accounting_pdf_reports 2.x puts its own "Equity" node ("Capital and
    Reserves" + "Profit (Loss) to report") under "Liabilities and Equity",
    while this module adds a separate Equity section to the Balance Sheet. Both
    were in the tree, so the equity accounts were counted under the Liabilities
    and again under the Equity, and Assets <> Liabilities + Equity.

    The data file now takes that node out of the tree, but it is skipped on
    update when its XML id is flagged no-update (accounting_pdf_reports sets it
    on databases whose Balance Sheet was "kept"), hence this script.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    equity_section = env.ref('hudson_accounting_enhancements.account_financial_report_equity_section',
                             raise_if_not_found=False)
    if not equity_section:
        return
    legacy_equity = env.ref('accounting_pdf_reports.account_financial_report_equity0', raise_if_not_found=False)
    if legacy_equity and legacy_equity.parent_id:
        _logger.info("Balance Sheet: taking the legacy Equity node (id %s) out of '%s', the equity is "
                     "reported in the Equity section only.", legacy_equity.id, legacy_equity.parent_id.name)
        legacy_equity.parent_id = False
    profit_to_report = env.ref('accounting_pdf_reports.account_financial_report_profitloss_toreport0',
                               raise_if_not_found=False)
    if profit_to_report and profit_to_report.parent_id != equity_section:
        profit_to_report.parent_id = equity_section
