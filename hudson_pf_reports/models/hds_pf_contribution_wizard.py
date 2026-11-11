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


class HdsPfContributionWizard(models.TransientModel):
    _name = 'hds.pf.contribution.wizard'
    _inherit = 'hds.pf.report.wizard.base'
    _description = 'PF Contribution Report Wizard'

    report_type = fields.Selection([
        ('employee', 'Employee Contribution Report'),
        ('employer', 'Employer Contribution Report'),
        ('combined', 'Combined Contribution Report'),
    ], string='Report Type', default='combined', required=True)

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
    ], string='State', default='draft')

    xlsx_file = fields.Binary(string='Contribution Report Excel (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    @api.depends('month', 'year', 'report_type')
    def _compute_name(self):
        month_dict = dict(self._fields['month'].selection)
        type_dict = dict(self._fields['report_type'].selection)
        for rec in self:
            m_label = month_dict.get(rec.month, '')
            t_label = type_dict.get(rec.report_type, 'PF Contribution')
            rec.name = f"{t_label} / {m_label}-{rec.year}"

    def action_export_xlsx(self):
        self.ensure_one()
        payslips = self._get_confirmed_payslips([('employee_id.hds_in_epf_applicable', '=', True)])

        if not payslips:
            raise UserError(_("No confirmed payslips found for EPF-applicable employees in period (%s).") % self._get_month_label())

        rows = []
        for payslip in payslips:
            emp = payslip.employee_id
            uan = emp.hds_in_uan or ''

            pf_vals = self._get_pf_line_amounts(payslip)
            pf_wage = pf_vals['pf_wage']
            ee_epf = pf_vals['ee_epf']
            er_epf = pf_vals['er_epf']
            er_eps = pf_vals['er_eps']
            edli = pf_vals['edli']
            total_er = pf_vals['total_cost']

            rows.append({
                'employee': emp.name,
                'uan': uan,
                'pf_wage': round(pf_wage, 2),
                'ee_epf': round(ee_epf, 2),
                'er_epf': round(er_epf, 2),
                'er_eps': round(er_eps, 2),
                'edli': round(edli, 2),
                'total_er': round(total_er, 2),
            })

        month_label = self._get_month_label().replace('-', '_')
        xlsx_filename = f"PF_Contribution_{self.report_type}_{month_label}.xlsx"

        output = io.BytesIO()
        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('PF Contribution')
            sheet.set_column(0, 0, 26)  # Employee Name
            sheet.set_column(1, 1, 18)  # UAN
            sheet.set_column(2, 2, 22)  # PF Contribution Wage
            sheet.set_column(3, 7, 20)  # All contribution columns

            header_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#1F4E78',
                'font_color': '#FFFFFF',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'text_wrap': True,
            })
            num_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1, 'align': 'right', 'valign': 'vcenter'})
            text_fmt = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter'})

            sheet.set_row(0, 26)
            if self.report_type == 'employee':
                headers = ['Employee Name', 'UAN', 'PF Contribution Wage', 'Employee EPF Deduction']
            elif self.report_type == 'employer':
                headers = ['Employee Name', 'UAN', 'PF Contribution Wage', 'Employer EPF Share', 'Employer EPS Share', 'EDLI Contribution', 'Total Employer Share']
            else:
                headers = ['Employee Name', 'UAN', 'PF Contribution Wage', 'Employee EPF', 'Employer EPF', 'Employer EPS', 'EDLI', 'Total Employer Share']

            for col_idx, text in enumerate(headers):
                sheet.write(0, col_idx, text, header_fmt)

            for row_idx, r in enumerate(rows, start=1):
                sheet.write(row_idx, 0, r['employee'], text_fmt)
                sheet.write(row_idx, 1, r['uan'], text_fmt)
                sheet.write(row_idx, 2, r['pf_wage'], num_fmt)
                if self.report_type == 'employee':
                    sheet.write(row_idx, 3, r['ee_epf'], num_fmt)
                elif self.report_type == 'employer':
                    sheet.write(row_idx, 3, r['er_epf'], num_fmt)
                    sheet.write(row_idx, 4, r['er_eps'], num_fmt)
                    sheet.write(row_idx, 5, r['edli'], num_fmt)
                    sheet.write(row_idx, 6, r['total_er'], num_fmt)
                else:
                    sheet.write(row_idx, 3, r['ee_epf'], num_fmt)
                    sheet.write(row_idx, 4, r['er_epf'], num_fmt)
                    sheet.write(row_idx, 5, r['er_eps'], num_fmt)
                    sheet.write(row_idx, 6, r['edli'], num_fmt)
                    sheet.write(row_idx, 7, r['total_er'], num_fmt)

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
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=xlsx_file&filename_field=xlsx_filename&download=true',
            'target': 'self',
        }
