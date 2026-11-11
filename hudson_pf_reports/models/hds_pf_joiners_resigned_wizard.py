# -*- coding: utf-8 -*-
import base64
import io
# pyrefly: ignore [missing-import]
from odoo import api, fields, models
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError

try:
    # pyrefly: ignore [missing-import]
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HdsPfJoinersResignedWizard(models.TransientModel):
    _name = 'hds.pf.joiners.resigned.wizard'
    _inherit = 'hds.pf.report.wizard.base'
    _description = 'New Joiners & Resigned Employees PF Report Wizard'

    report_type = fields.Selection([
        ('joiners', 'New Joiners PF Report'),
        ('resigned', 'Resigned Employees PF Report'),
    ], string='Report Type', default='joiners', required=True)

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([('draft', 'Draft'), ('generated', 'Generated')], string='State', default='draft')
    xlsx_file = fields.Binary(string='Report Excel (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    @api.depends('month', 'year', 'report_type')
    def _compute_name(self):
        m_dict = dict(self._fields['month'].selection)
        t_dict = dict(self._fields['report_type'].selection)
        for rec in self:
            rec.name = f"{t_dict.get(rec.report_type, '')} / {m_dict.get(rec.month, '')}-{rec.year}"

    def action_export_xlsx(self):
        self.ensure_one()
        date_from, date_to = self._get_date_range()

        if self.report_type == 'joiners':
            # Check joining_date or contract.date_start
            emp_domain = [
                ('company_id', '=', self.company_id.id),
                '|',
                '&', ('joining_date', '>=', date_from), ('joining_date', '<=', date_to),
                '&', ('create_date', '>=', date_from), ('create_date', '<=', date_to)
            ]
            if 'joining_date' not in self.env['hr.employee']._fields:
                emp_domain = [('company_id', '=', self.company_id.id)]
            employees = self.env['hr.employee'].search(emp_domain)
            # Filter employees joining in month
            filtered_emps = []
            for emp in employees:
                j_date = getattr(emp, 'joining_date', False)
                if not j_date:
                    contracts = self.env['hr.version'].search([('employee_id', '=', emp.id)], order='id asc', limit=1)
                    if contracts:
                        j_date = contracts.date_start
                if j_date and date_from <= j_date <= date_to:
                    filtered_emps.append((emp, j_date))
        else:
            # Resigned employees
            employees = self.env['hr.employee'].with_context(active_test=False).search([('company_id', '=', self.company_id.id)])
            filtered_emps = []
            for emp in employees:
                r_date = getattr(emp, 'resign_date', False) or getattr(emp, 'departure_date', False)
                if r_date and date_from <= r_date <= date_to:
                    filtered_emps.append((emp, r_date))

        rows = []
        for emp, event_date in filtered_emps:
            # Find confirmed payslip in this period if exists
            payslip = self.env['hr.payslip'].search([
                ('state', '=', 'done'),
                ('employee_id', '=', emp.id),
                ('date_from', '>=', date_from),
                ('date_to', '<=', date_to),
            ], limit=1)

            pf_wage = payslip.hds_in_get_pf_contribution_wage() if payslip else 0.0
            ee_epf = abs(sum(payslip.line_ids.filtered(lambda l: l.code == 'EPF').mapped('total'))) if payslip else 0.0
            er_epf = abs(sum(payslip.line_ids.filtered(lambda l: l.code == 'EPF_ER').mapped('total'))) if payslip else 0.0
            er_eps = abs(sum(payslip.line_ids.filtered(lambda l: l.code == 'EPS').mapped('total'))) if payslip else 0.0

            rows.append({
                'employee': emp.name,
                'code': emp.identification_id or '',
                'uan': getattr(emp, 'hds_in_uan', '') or '',
                'event_date': str(event_date) if event_date else '',
                'pf_applicable': 'Yes' if getattr(emp, 'hds_in_epf_applicable', False) else 'No',
                'pf_wage': round(pf_wage, 2),
                'ee_epf': round(ee_epf, 2),
                'er_epf': round(er_epf, 2),
                'er_eps': round(er_eps, 2),
            })

        month_label = self._get_month_label().replace('-', '_')
        xlsx_filename = f"PF_{self.report_type.capitalize()}_{month_label}.xlsx"

        output = io.BytesIO()
        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('Report')
            sheet.set_column(0, 0, 26)  # Employee
            sheet.set_column(1, 1, 16)  # Employee Code
            sheet.set_column(2, 2, 18)  # UAN
            sheet.set_column(3, 3, 22)  # Joining / Exit Date
            sheet.set_column(4, 4, 16)  # EPF Applicable
            sheet.set_column(5, 5, 18)  # PF Wage
            sheet.set_column(6, 6, 16)  # Employee EPF
            sheet.set_column(7, 7, 16)  # Employer EPF
            sheet.set_column(8, 8, 16)  # Employer EPS

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
            date_col_header = 'Joining Date' if self.report_type == 'joiners' else 'Exit / Resignation Date'
            headers = ['Employee', 'Employee Code', 'UAN', date_col_header, 'EPF Applicable', 'PF Wage', 'Employee EPF', 'Employer EPF', 'Employer EPS']
            for col_idx, text in enumerate(headers):
                sheet.write(0, col_idx, text, header_fmt)

            for row_idx, r in enumerate(rows, start=1):
                sheet.write(row_idx, 0, r['employee'], text_fmt)
                sheet.write(row_idx, 1, r['code'], text_fmt)
                sheet.write(row_idx, 2, r['uan'], text_fmt)
                sheet.write(row_idx, 3, r['event_date'], text_fmt)
                sheet.write(row_idx, 4, r['pf_applicable'], text_fmt)
                sheet.write(row_idx, 5, r['pf_wage'], num_fmt)
                sheet.write(row_idx, 6, r['ee_epf'], num_fmt)
                sheet.write(row_idx, 7, r['er_epf'], num_fmt)
                sheet.write(row_idx, 8, r['er_eps'], num_fmt)

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
