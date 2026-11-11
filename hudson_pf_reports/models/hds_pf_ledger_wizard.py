# -*- coding: utf-8 -*-
import base64
import io
from odoo import api, fields, models, _# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError# pyrefly: ignore [missing-import]

try:
    import xlsxwriter# pyrefly: ignore [missing-import]
except ImportError:
    xlsxwriter = None


class HdsPfLedgerWizard(models.TransientModel):
    _name = 'hds.pf.ledger.wizard'
    _inherit = 'hds.pf.report.wizard.base'
    _description = 'Employee PF Ledger Wizard'

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        required=True,
        help="Target employee for PF ledger statement."
    )
    year_from = fields.Integer(
        string='From Year',
        default=lambda self: fields.Date.today().year,
        required=True
    )
    year_to = fields.Integer(
        string='To Year',
        default=lambda self: fields.Date.today().year,
        required=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
    ], string='State', default='draft')

    xlsx_file = fields.Binary(string='Employee PF Ledger Excel (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    @api.depends('employee_id', 'year_from', 'year_to')
    def _compute_name(self):
        for rec in self:
            emp_name = rec.employee_id.name or 'Employee'
            if rec.year_from == rec.year_to:
                rec.name = f"PF Ledger / {emp_name} ({rec.year_from})"
            else:
                rec.name = f"PF Ledger / {emp_name} ({rec.year_from}-{rec.year_to})"

    def action_export_xlsx(self):
        self.ensure_one()
        payslips = self.env['hr.payslip'].search([
            ('state', '=', 'done'),
            ('employee_id', '=', self.employee_id.id),
            ('company_id', '=', self.company_id.id),
            ('date_from', '>=', f"{self.year_from}-01-01"),
            ('date_to', '<=', f"{self.year_to}-12-31"),
        ], order='date_from asc')

        if not payslips:
            raise UserError(_("No confirmed payslips found for employee '%s' between %s and %s.") % (self.employee_id.name, self.year_from, self.year_to))

        ledger_rows = []
        cum_ee_epf = 0.0
        cum_er_epf = 0.0
        cum_er_eps = 0.0

        for payslip in payslips:
            period = payslip.date_from.strftime('%m/%Y') if payslip.date_from else ''
            pf_vals = self._get_pf_line_amounts(payslip)

            pf_wage = pf_vals['pf_wage']
            ee_epf = pf_vals['ee_epf']
            er_epf = pf_vals['er_epf']
            er_eps = pf_vals['er_eps']

            cum_ee_epf += ee_epf
            cum_er_epf += er_epf
            cum_er_eps += er_eps

            ledger_rows.append({
                'period': period,
                'pf_wage': round(pf_wage, 2),
                'ee_epf': round(ee_epf, 2),
                'er_epf': round(er_epf, 2),
                'er_eps': round(er_eps, 2),
                'cum_ee': round(cum_ee_epf, 2),
                'cum_er': round(cum_er_epf + cum_er_eps, 2),
            })

        emp_code = self.employee_id.identification_id or ''
        uan = self.employee_id.hds_in_uan or ''
        xlsx_filename = f"PF_Ledger_{self.employee_id.name.replace(' ', '_')}.xlsx"

        output = io.BytesIO()
        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('PF Ledger')
            sheet.set_column(0, 0, 18)  # Period (MM/YYYY)
            sheet.set_column(1, 1, 18)  # PF Wage
            sheet.set_column(2, 2, 18)  # Employee EPF
            sheet.set_column(3, 3, 18)  # Employer EPF
            sheet.set_column(4, 4, 18)  # Employer EPS
            sheet.set_column(5, 5, 26)  # Cumulative Employee EPF
            sheet.set_column(6, 6, 30)  # Cumulative Employer Contribution

            title_fmt = workbook.add_format({'bold': True, 'font_size': 14})
            sub_fmt = workbook.add_format({'bold': True, 'font_size': 11})
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

            sheet.write(0, 0, f"EMPLOYEE PF LEDGER STATEMENT", title_fmt)
            sheet.write(1, 0, f"Employee: {self.employee_id.name} | Code: {emp_code} | UAN: {uan}", sub_fmt)
            sheet.write(2, 0, f"Period: {self.year_from} to {self.year_to} | Company: {self.company_id.name}", sub_fmt)

            sheet.set_row(4, 26)
            headers = [
                'Period (MM/YYYY)', 'PF Wage', 'Employee EPF', 'Employer EPF',
                'Employer EPS', 'Cumulative Employee EPF', 'Cumulative Employer Contribution'
            ]
            for col_idx, text in enumerate(headers):
                sheet.write(4, col_idx, text, header_fmt)

            for row_idx, r in enumerate(ledger_rows, start=5):
                sheet.write(row_idx, 0, r['period'], text_fmt)
                sheet.write(row_idx, 1, r['pf_wage'], num_fmt)
                sheet.write(row_idx, 2, r['ee_epf'], num_fmt)
                sheet.write(row_idx, 3, r['er_epf'], num_fmt)
                sheet.write(row_idx, 4, r['er_eps'], num_fmt)
                sheet.write(row_idx, 5, r['cum_ee'], num_fmt)
                sheet.write(row_idx, 6, r['cum_er'], num_fmt)

            tot_row = len(ledger_rows) + 5
            sheet.write(tot_row, 0, "TOTAL", total_fmt)
            sheet.write(tot_row, 1, sum(r['pf_wage'] for r in ledger_rows), total_fmt)
            sheet.write(tot_row, 2, sum(r['ee_epf'] for r in ledger_rows), total_fmt)
            sheet.write(tot_row, 3, sum(r['er_epf'] for r in ledger_rows), total_fmt)
            sheet.write(tot_row, 4, sum(r['er_eps'] for r in ledger_rows), total_fmt)
            sheet.write(tot_row, 5, cum_ee_epf, total_fmt)
            sheet.write(tot_row, 6, cum_er_epf + cum_er_eps, total_fmt)

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
