from odoo import api, models, _
from odoo.exceptions import UserError


class ReportExecutiveSummary(models.AbstractModel):
    _name = 'report.hudson_accounting_enhancements.report_exec_sum'
    _description = 'Executive Summary Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data or not data.get('form'):
            raise UserError(_('Executive Summary data is missing. Please use the wizard.'))
        form = data['form']
        company_data = form.get('company') or form.get('company_id')
        if isinstance(company_data, (list, tuple)):
            company = self.env['res.company'].browse(company_data[0])
        elif company_data:
            company = self.env['res.company'].browse(company_data)
        else:
            company = self.env.company
            
        wizard_id = docids[0] if docids else False
        
        # Clean form data to only include valid fields for the wizard, in case it needs to be created
        valid_fields = self.env['account.executive.summary.wizard']._fields.keys()
        clean_form = {k: v for k, v in form.items() if k in valid_fields}
        if 'company' in form and 'company_id' in valid_fields:
            clean_form['company_id'] = form['company']
        
        # Odoo's frontend sometimes injects 'used_context' and it causes create() to fail
        clean_form.pop('used_context', None)
        clean_form.pop('id', None)
        # Keep the Multi Ledger selection so the PDF matches the on-screen report
        if form.get('gaap_options'):
            clean_form['gaap_options'] = form['gaap_options']
            
        # Get the standard dynamic report data
        report_data = self.env['hudson.dynamic.report'].get_report_data(
            'account.executive.summary.wizard', wizard_id, {'form': clean_form}
        )
        
        return {
            'doc_ids': docids,
            'doc_model': 'account.executive.summary.wizard',
            'data': form,
            'company': company,
            'currency': company.currency_id,
            'report_data': report_data,
        }
