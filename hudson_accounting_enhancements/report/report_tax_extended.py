from odoo import api, models, _
from odoo.exceptions import UserError


class ReportTaxExtended(models.AbstractModel):
    _name = 'report.hudson_accounting_enhancements.report_tax_ext'
    _description = 'Extended Tax Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data or not data.get('form'):
            raise UserError(_('Tax report data is missing.'))
        form = data['form']
        company_data = form.get('company')
        if isinstance(company_data, (list, tuple)):
            company = self.env['res.company'].browse(company_data[0])
        else:
            company = self.env['res.company'].browse(company_data)
        wizard_id = docids[0] if docids else False
        
        valid_fields = self.env['account.tax.extended.wizard']._fields.keys()
        clean_form = {k: v for k, v in form.items() if k in valid_fields}
        if 'company' in form and 'company_id' in valid_fields:
            clean_form['company_id'] = form['company']
        # Keep the Multi Ledger selection so the PDF matches the on-screen report
        if form.get('gaap_options'):
            clean_form['gaap_options'] = form['gaap_options']

        # Get dynamic report data
        report_data = self.env['hudson.dynamic.report'].get_report_data(
            'account.tax.extended.wizard', wizard_id, {'form': clean_form}
        )

        return {
            'doc_ids': docids,
            'doc_model': 'account.tax.extended.wizard',
            'data': form,
            'company': company,
            'currency': company.currency_id,
            'report_data': report_data,
        }
