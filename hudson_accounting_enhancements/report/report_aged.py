# from odoo import api, models
from odoo import api, models


class ReportAgedReceivable(models.AbstractModel):
    _name = 'report.hudson_accounting_enhancements.report_aged_receivable'
    _description = 'Aged Receivable Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['account.aged.report'].browse(docids)
        report = docs[0] if docs else self.env['account.aged.report'].browse(data.get('id'))
        return {
            'doc_ids': docids,
            'doc_model': 'account.aged.report',
            'docs': docs,
            'report': report,
            'title': 'Aged Receivable',
        }


class ReportAgedPayable(models.AbstractModel):
    _name = 'report.hudson_accounting_enhancements.report_aged_payable'
    _description = 'Aged Payable Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['account.aged.report'].browse(docids)
        report = docs[0] if docs else self.env['account.aged.report'].browse(data.get('id'))
        return {
            'doc_ids': docids,
            'doc_model': 'account.aged.report',
            'docs': docs,
            'report': report,
            'title': 'Aged Payable',
        }
