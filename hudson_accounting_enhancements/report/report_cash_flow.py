from odoo import api, models, _
from odoo.exceptions import UserError


class ReportCashFlow(models.AbstractModel):
    _name = 'report.hudson_accounting_enhancements.report_cf'
    _description = 'Cash Flow Statement Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data or not data.get('form'):
            raise UserError(_('Cash Flow report data is missing. Please use the wizard.'))

        form = data['form']
        company = self.env['res.company'].browse(form['company'][0] if isinstance(form['company'], (list, tuple)) else form['company'])

        return {
            'doc_ids': docids,
            'doc_model': 'account.cash.flow.wizard',
            'data': form,
            'company': company,
            'currency': company.currency_id,
        }
