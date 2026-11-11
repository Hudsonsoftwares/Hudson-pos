from odoo import models, fields, api

class AccountCommonReport(models.TransientModel):
    _inherit = 'account.common.report'

    report_html = fields.Html(string="Report Output", compute="_compute_report_html", store=False)

    @api.depends('date_from', 'date_to', 'target_move', 'journal_ids', 'company_id')
    def _compute_report_html(self):
        for record in self:
            if not record.id:
                record.report_html = ""
                continue
                
            # Simulate a form dictionary for the dynamic report generator
            data = {
                'form': {
                    'date_from': record.date_from,
                    'date_to': record.date_to,
                    'target_move': record.target_move,
                    'journal_ids': record.journal_ids.ids,
                    'company_id': record.company_id.id,
                }
            }
            
            # Since account.common.report is inherited by many wizards, we check the model name
            model_name = self._name
            if model_name == 'accounting.report':
                data['form']['account_report_id'] = [record.account_report_id.id, record.account_report_id.name] if getattr(record, 'account_report_id', False) else False
                data['form']['enable_filter'] = record.enable_filter if hasattr(record, 'enable_filter') else False
                data['form']['debit_credit'] = record.debit_credit if hasattr(record, 'debit_credit') else False
                data['form']['label_filter'] = record.label_filter if hasattr(record, 'label_filter') else False
                data['form']['filter_cmp'] = record.filter_cmp if hasattr(record, 'filter_cmp') else False
                data['form']['date_from_cmp'] = record.date_from_cmp if hasattr(record, 'date_from_cmp') else False
                data['form']['date_to_cmp'] = record.date_to_cmp if hasattr(record, 'date_to_cmp') else False
            elif model_name == 'account.report.general.ledger':
                data['form']['display_account'] = record.display_account if hasattr(record, 'display_account') else 'all'
                data['form']['initial_balance'] = record.initial_balance if hasattr(record, 'initial_balance') else False
                data['form']['sortby'] = record.sortby if hasattr(record, 'sortby') else 'sort_date'
            
            try:
                # Use the dynamic report model to get the data
                report_data = self.env['hudson.dynamic.report'].get_report_data(model_name, record.id, data)
                
                # Render the HTML using the QWeb template
                # We can reuse the executive summary template or a generic one
                html_content = self.env['ir.qweb']._render('hudson_accounting_enhancements.dynamic_report_template', report_data)
                record.report_html = html_content
            except Exception as e:
                record.report_html = f"<div class='alert alert-danger'>Error rendering report: {str(e)}</div>"

