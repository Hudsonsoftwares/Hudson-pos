# -*- coding: utf-8 -*-
import base64
import io
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError

try:
    # pyrefly: ignore [missing-import]
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HdsPfCeilingExceptionWizard(models.TransientModel):
    _name = 'hds.pf.ceiling.exception.wizard'
    _inherit = 'hds.pf.report.wizard.base'
    _description = 'Wage Ceiling Exception Report Wizard'

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
    ], string='State', default='draft')

    xlsx_file = fields.Binary(string='Ceiling Exception Excel (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)
    exception_count = fields.Integer(string='Exceptions Found', readonly=True)

    @api.depends('month', 'year')
    def _compute_name(self):
        month_dict = dict(self._fields['month'].selection)
        for rec in self:
            m_label = month_dict.get(rec.month, '')
            rec.name = f"PF Ceiling Exceptions / {m_label}-{rec.year}"

    def action_export_xlsx(self):
        self.ensure_one()
        payslips = self._get_confirmed_payslips([('employee_id.hds_in_epf_applicable', '=', True)])

        if not payslips:
            raise UserError(_("No confirmed payslips found in period (%s).") % self._get_month_label())

        date_from, date_to = self._get_date_range()
        pf_ceiling = self.env['hr.rule.parameter'].get_pf_parameter('PF_WAGE_CEILING', date=date_to)

        rows = []
        for payslip in payslips:
            actual_pf_wage = payslip.hds_in_get_actual_pf_wage()
            if actual_pf_wage > pf_ceiling:
                emp = payslip.employee_id
                basis_code = getattr(emp, 'hds_in_pf_contribution_basis', False)
                basis_label = ''
                if basis_code and 'hds_in_pf_contribution_basis' in emp._fields:
                    field_obj = emp._fields['hds_in_pf_contribution_basis']
                    if hasattr(field_obj, '_description_selection') and callable(getattr(field_obj, '_description_selection')):
                        sel_dict = dict(field_obj._description_selection(self.env))
                        basis_label = sel_dict.get(basis_code, str(basis_code))
                    else:
                        basis_label = str(basis_code)

                pf_used = payslip.hds_in_get_pf_contribution_wage()
                excess = actual_pf_wage - pf_ceiling

                rows.append({
                    'employee': emp.name,
                    'basis': basis_label,
                    'actual_pf_wage': round(actual_pf_wage, 2),
                    'ceiling': round(pf_ceiling, 2),
                    'excess_wage': round(excess, 2),
                    'pf_used': round(pf_used, 2),
                })

        month_label = self._get_month_label().replace('-', '_')
        xlsx_filename = f"PF_Ceiling_Exceptions_{month_label}.xlsx"

        output = io.BytesIO()
        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('Ceiling Exceptions')
            sheet.set_column(0, 0, 26)  # Employee
            sheet.set_column(1, 1, 20)  # Contribution Basis
            sheet.set_column(2, 2, 18)  # Actual PF Wage
            sheet.set_column(3, 3, 18)  # Statutory Ceiling
            sheet.set_column(4, 4, 24)  # Excess Wage over Ceiling
            sheet.set_column(5, 5, 22)  # PF Wage Capped / Used

            header_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#C00000',
                'font_color': '#FFFFFF',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'text_wrap': True,
            })
            num_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1, 'align': 'right', 'valign': 'vcenter'})
            text_fmt = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter'})

            sheet.set_row(0, 26)
            headers = ['Employee', 'Contribution Basis', 'Actual PF Wage', 'Statutory Ceiling', 'Excess Wage over Ceiling', 'PF Wage Capped / Used']
            for col_idx, text in enumerate(headers):
                sheet.write(0, col_idx, text, header_fmt)

            for row_idx, r in enumerate(rows, start=1):
                sheet.write(row_idx, 0, r['employee'], text_fmt)
                sheet.write(row_idx, 1, r['basis'], text_fmt)
                sheet.write(row_idx, 2, r['actual_pf_wage'], num_fmt)
                sheet.write(row_idx, 3, r['ceiling'], num_fmt)
                sheet.write(row_idx, 4, r['excess_wage'], num_fmt)
                sheet.write(row_idx, 5, r['pf_used'], num_fmt)

            workbook.close()
            output.seek(0)
            xlsx_content = output.read()
        else:
            xlsx_content = b"Excel export requires xlsxwriter library."

        try:
            # pyrefly: ignore [missing-import]
            from odoo.tools import BinaryBytes
            file_data = BinaryBytes(xlsx_content, filename=xlsx_filename)
        except Exception:
            file_data = base64.b64encode(xlsx_content).decode('utf-8')

        self.write({
            'state': 'generated',
            'xlsx_file': file_data,
            'xlsx_filename': xlsx_filename,
            'exception_count': len(rows),
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=xlsx_file&filename_field=xlsx_filename&download=true',
            'target': 'self',
        }
