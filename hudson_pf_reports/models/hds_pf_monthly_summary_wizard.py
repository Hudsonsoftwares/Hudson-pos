# -*- coding: utf-8 -*-
import base64
import calendar
import io
from datetime import date
# pyrefly: ignore [missing-import]
# pyrefly: ignore [missing-import]
from odoo import api, fields, models

try:
    # pyrefly: ignore [missing-import]
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HdsPfMonthlySummaryWizard(models.TransientModel):
    _name = 'hds.pf.monthly.summary.wizard'
    _inherit = 'hds.pf.report.wizard.base'
    _description = 'Monthly PF Summary Wizard'

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
    ], string='State', default='draft')

    xlsx_file = fields.Binary(string='Monthly PF Summary Excel (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    @api.depends('year')
    def _compute_name(self):
        for rec in self:
            rec.name = f"Monthly PF Summary / {rec.year}"

    def action_export_xlsx(self):
        self.ensure_one()
        year = int(self.year)

        month_rows = []
        tot_all_wages = 0.0
        tot_all_ee_epf = 0.0
        tot_all_er_epf = 0.0
        tot_all_er_eps = 0.0
        tot_all_edli = 0.0
        tot_all_admin = 0.0
        tot_all_cost = 0.0

        month_names = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']

        for m_idx in range(1, 13):
            last_day = calendar.monthrange(year, m_idx)[1]
            date_from = date(year, m_idx, 1)
            date_to = date(year, m_idx, last_day)

            payslips = self.env['hr.payslip'].search([
                ('state', '=', 'done'),
                ('company_id', '=', self.company_id.id),
                ('date_from', '>=', date_from),
                ('date_to', '<=', date_to),
                ('employee_id.hds_in_epf_applicable', '=', True),
            ])

            m_wages = 0.0
            m_ee_epf = 0.0
            m_er_epf = 0.0
            m_er_eps = 0.0
            m_edli = 0.0
            m_admin = 0.0
            m_cost = 0.0

            for p in payslips:
                pf_vals = self._get_pf_line_amounts(p)
                m_wages += pf_vals['pf_wage']
                m_ee_epf += pf_vals['ee_epf']
                m_er_epf += pf_vals['er_epf']
                m_er_eps += pf_vals['er_eps']
                m_edli += pf_vals['edli']
                m_admin += pf_vals['admin']
                m_cost += pf_vals['total_cost']

            month_rows.append({
                'month': month_names[m_idx - 1],
                'headcount': len(payslips.mapped('employee_id')),
                'pf_wages': round(m_wages, 2),
                'ee_epf': round(m_ee_epf, 2),
                'er_epf': round(m_er_epf, 2),
                'er_eps': round(m_er_eps, 2),
                'edli': round(m_edli, 2),
                'admin': round(m_admin, 2),
                'total_cost': round(m_cost, 2),
            })

            tot_all_wages += m_wages
            tot_all_ee_epf += m_ee_epf
            tot_all_er_epf += m_er_epf
            tot_all_er_eps += m_er_eps
            tot_all_edli += m_edli
            tot_all_admin += m_admin
            tot_all_cost += m_cost

        xlsx_filename = f"Monthly_PF_Summary_{year}.xlsx"

        output = io.BytesIO()
        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('Monthly PF Summary')
            sheet.set_column(0, 0, 16)  # Month
            sheet.set_column(1, 1, 14)  # Headcount
            sheet.set_column(2, 2, 20)  # Total PF Wages
            sheet.set_column(3, 3, 18)  # Employee EPF
            sheet.set_column(4, 4, 18)  # Employer EPF
            sheet.set_column(5, 5, 18)  # Employer EPS
            sheet.set_column(6, 6, 16)  # EDLI
            sheet.set_column(7, 7, 20)  # PF Admin Charges
            sheet.set_column(8, 8, 22)  # Total Employer Cost

            title_fmt = workbook.add_format({'bold': True, 'font_size': 14})
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
            text_fmt = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})
            total_fmt = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'bg_color': '#D9E1F2', 'border': 1, 'align': 'right', 'valign': 'vcenter'})

            sheet.write(0, 0, f"ANNUAL MONTHLY PF SUMMARY — {year} ({self.company_id.name})", title_fmt)

            sheet.set_row(2, 26)
            headers = [
                'Month', 'Headcount', 'Total PF Wages', 'Employee EPF',
                'Employer EPF', 'Employer EPS', 'EDLI', 'PF Admin Charges', 'Total Employer Cost'
            ]
            for col_idx, text in enumerate(headers):
                sheet.write(2, col_idx, text, header_fmt)

            for row_idx, r in enumerate(month_rows, start=3):
                sheet.write(row_idx, 0, r['month'], text_fmt)
                sheet.write(row_idx, 1, r['headcount'], text_fmt)
                sheet.write(row_idx, 2, r['pf_wages'], num_fmt)
                sheet.write(row_idx, 3, r['ee_epf'], num_fmt)
                sheet.write(row_idx, 4, r['er_epf'], num_fmt)
                sheet.write(row_idx, 5, r['er_eps'], num_fmt)
                sheet.write(row_idx, 6, r['edli'], num_fmt)
                sheet.write(row_idx, 7, r['admin'], num_fmt)
                sheet.write(row_idx, 8, r['total_cost'], num_fmt)

            tot_row = len(month_rows) + 3
            sheet.write(tot_row, 0, "ANNUAL TOTAL", total_fmt)
            sheet.write(tot_row, 1, "", total_fmt)
            sheet.write(tot_row, 2, tot_all_wages, total_fmt)
            sheet.write(tot_row, 3, tot_all_ee_epf, total_fmt)
            sheet.write(tot_row, 4, tot_all_er_epf, total_fmt)
            sheet.write(tot_row, 5, tot_all_er_eps, total_fmt)
            sheet.write(tot_row, 6, tot_all_edli, total_fmt)
            sheet.write(tot_row, 7, tot_all_admin, total_fmt)
            sheet.write(tot_row, 8, tot_all_cost, total_fmt)

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
