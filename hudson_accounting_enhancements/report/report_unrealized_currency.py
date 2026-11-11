from odoo import api, models, _
from odoo.exceptions import UserError


class ReportUnrealizedCurrency(models.AbstractModel):
    _name = 'report.hudson_accounting_enhancements.report_unreal_ccy'
    _description = 'Unrealized Currency Gains/Losses Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data or not data.get('form'):
            raise UserError(_('Unrealized Currency data is missing.'))
        form = data['form']
        company_data = form.get('company')
        if isinstance(company_data, (list, tuple)):
            company = self.env['res.company'].browse(company_data[0])
        else:
            company = self.env['res.company'].browse(company_data)
        return {
            'doc_ids': docids,
            'doc_model': 'account.unrealized.currency.wizard',
            'data': form,
            'company': company,
            'currency': company.currency_id,
        }
