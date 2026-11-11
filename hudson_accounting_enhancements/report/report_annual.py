from odoo import api, models, _
from odoo.exceptions import UserError


def _clean_zero(val):
    if val is None or val is False:
        return 0.0
    if isinstance(val, (int, float)):
        return 0.0 if abs(val) < 0.005 else val
    elif isinstance(val, dict):
        return {k: _clean_zero(v) for k, v in val.items()}
    elif isinstance(val, (list, tuple)):
        return [_clean_zero(v) for v in val]
    return val


class ReportAnnual(models.AbstractModel):
    _name = 'report.hudson_accounting_enhancements.report_annual'
    _description = 'Annual Financial Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        form = {}
        docs = None
        if data and data.get('form'):
            form = dict(data['form'])

        if docids:
            if self.env.context.get('active_model') == 'account.annual.report.wizard':
                docs = self.env['account.annual.report.wizard'].browse(docids)
            else:
                docs = self.env['account.annual.report'].browse(docids)
                if not docs.exists():
                    docs = self.env['account.annual.report.wizard'].browse(docids)

            if not form and docs and hasattr(docs[0], '_compute_annual_data'):
                form = docs[0]._compute_annual_data()

        if not form and not docs:
            raise UserError(_('Annual Report data is missing. Please use the wizard.'))

        form = _clean_zero(form)

        company_data = form.get('company') or form.get('company_id')
        if isinstance(company_data, (list, tuple)):
            company = self.env['res.company'].browse(company_data[0])
        elif isinstance(company_data, int):
            company = self.env['res.company'].browse(company_data)
        elif docs and hasattr(docs[0], 'company_id') and docs[0].company_id:
            company = docs[0].company_id
        else:
            company = self.env.company

        if company and company not in self.env.companies:
            raise UserError(_("You are not authorized to view or print the Annual Report for %s.") % company.name)

        # Make logo available as base64 string for template
        logo_b64 = False
        if company and company.logo:
            try:
                logo_b64 = company.logo.decode('utf-8')
            except Exception:
                logo_b64 = False

        if not docs and form:
            doc_model = (data and data.get('doc_model')) or 'account.annual.report'
            if doc_model in self.env:
                docs = self.env[doc_model].browse(docids)

        return {
            'doc_ids': docids,
            'doc_model': 'account.annual.report',
            'docs': docs,
            'data': form,
            'company': company,
            'currency': company.currency_id,
            'logo_b64': logo_b64,
            'fmt_curr': lambda val: '0.00' if abs(val or 0.0) < 0.005 else '{:,.2f}'.format(val),
        }
