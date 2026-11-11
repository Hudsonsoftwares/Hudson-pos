# -*- coding: utf-8 -*-
import base64
import calendar
import io
from datetime import date
from odoo import api, fields, models, _# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError# pyrefly: ignore [missing-import]

try:
    import xlsxwriter# pyrefly: ignore [missing-import]
except ImportError:
    xlsxwriter = None


class HdsPfVarianceWizard(models.TransientModel):
    _name = 'hds.pf.variance.wizard'
    _description = 'PF Variance Report Wizard'

    from_year = fields.Integer(string='From Year', default=lambda self: fields.Date.today().year, required=True)
    from_month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'), ('4', 'April'),
        ('5', 'May'), ('6', 'June'), ('7', 'July'), ('8', 'August'),
        ('9', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December'),
    ], string='From Month', default=lambda self: str(fields.Date.today().month), required=True)

    to_year = fields.Integer(string='To Year', default=lambda self: fields.Date.today().year, required=True)
    to_month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'), ('4', 'April'),
        ('5', 'May'), ('6', 'June'), ('7', 'July'), ('8', 'August'),
        ('9', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December'),
    ], string='To Month', default=lambda self: str(fields.Date.today().month), required=True)

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, required=True)

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([('draft', 'Draft'), ('generated', 'Generated')], string='State', default='draft')
    xlsx_file = fields.Binary(string='Variance Report Excel (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    @api.depends('from_month', 'from_year', 'to_month', 'to_year')
    def _compute_name(self):
        m_dict = dict(self._fields['from_month'].selection)
        for rec in self:
            p1 = f"{m_dict.get(rec.from_month, '')}-{rec.from_year}"
            p2 = f"{m_dict.get(rec.to_month, '')}-{rec.to_year}"
            rec.name = f"PF Variance / {p1} vs {p2}"

    def _get_payslips_for_period(self, year, month):
        y = int(year)
        m = int(month)
        last_day = calendar.monthrange(y, m)[1]
        df = date(y, m, 1)
        dt = date(y, m, last_day)
        return self.env['hr.payslip'].search([
            ('state', '=', 'done'),
            ('company_id', '=', self.company_id.id),
            ('date_from', '>=', df),
            ('date_to', '<=', dt),
        ])

    def action_export_xlsx(self):
        self.ensure_one()
        slips_p1 = self._get_payslips_for_period(self.from_year, self.from_month)
        slips_p2 = self._get_payslips_for_period(self.to_year, self.to_month)

        if not slips_p1 and not slips_p2:
            raise UserError(_("No confirmed payslips found in either selected period."))

        p1_map = {p.employee_id.id: p for p in slips_p1}
        p2_map = {p.employee_id.id: p for p in slips_p2}
        all_emp_ids = set(p1_map.keys()) | set(p2_map.keys())

        employees = self.env['hr.employee'].browse(sorted(list(all_emp_ids)))

        rows = []
        for emp in employees:
            p1 = p1_map.get(emp.id)
            p2 = p2_map.get(emp.id)

            w1 = p1.hds_in_get_pf_contribution_wage() if p1 else 0.0
            epf1 = abs(sum(p1.line_ids.filtered(lambda l: l.code == 'EPF').mapped('total'))) if p1 else 0.0

            w2 = p2.hds_in_get_pf_contribution_wage() if p2 else 0.0
            epf2 = abs(sum(p2.line_ids.filtered(lambda l: l.code == 'EPF').mapped('total'))) if p2 else 0.0

            diff_epf = epf2 - epf1

            # Heuristic Reason Analysis
            reason = "No Change"
            if not p1 and p2:
                reason = "New Joining / First Payslip"
            elif p1 and not p2:
                reason = "Resigned / Missing Payslip"
            elif diff_epf != 0.0:
                lop1 = sum(p1.worked_days_line_ids.filtered(lambda l: l.code == 'UNPAID').mapped('number_of_days')) if p1 else 0
                lop2 = sum(p2.worked_days_line_ids.filtered(lambda l: l.code == 'UNPAID').mapped('number_of_days')) if p2 else 0
                if lop1 != lop2:
                    reason = f"LOP Days Changed ({lop1} → {lop2})"
                elif getattr(p1.contract_id, 'basic_salary', 0.0) != getattr(p2.contract_id, 'basic_salary', 0.0):
                    reason = "Salary Increase / Decrease"
                else:
                    reason = "PF Wage Basis / Rate Change"

            rows.append({
                'employee': emp.name,
                'uan': emp.hds_in_uan or '',
                'w1': round(w1, 2),
                'epf1': round(epf1, 2),
                'w2': round(w2, 2),
                'epf2': round(epf2, 2),
                'diff': round(diff_epf, 2),
                'reason': reason,
            })

        xlsx_filename = f"PF_Variance_{self.from_year}_{self.from_month}_vs_{self.to_year}_{self.to_month}.xlsx"

        output = io.BytesIO()
        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('PF Variance')
            sheet.set_column(0, 0, 26)  # Employee
            sheet.set_column(1, 1, 18)  # UAN
            sheet.set_column(2, 2, 18)  # Period 1 PF Wage
            sheet.set_column(3, 3, 16)  # Period 1 EPF
            sheet.set_column(4, 4, 18)  # Period 2 PF Wage
            sheet.set_column(5, 5, 16)  # Period 2 EPF
            sheet.set_column(6, 6, 16)  # EPF Variance
            sheet.set_column(7, 7, 30)  # Heuristic Reason

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
            headers = [
                'Employee', 'UAN', 'Period 1 PF Wage', 'Period 1 EPF',
                'Period 2 PF Wage', 'Period 2 EPF', 'EPF Variance', 'Heuristic Reason (Best Guess)'
            ]
            for col_idx, text in enumerate(headers):
                sheet.write(0, col_idx, text, header_fmt)

            for row_idx, r in enumerate(rows, start=1):
                sheet.write(row_idx, 0, r['employee'], text_fmt)
                sheet.write(row_idx, 1, r['uan'], text_fmt)
                sheet.write(row_idx, 2, r['w1'], num_fmt)
                sheet.write(row_idx, 3, r['epf1'], num_fmt)
                sheet.write(row_idx, 4, r['w2'], num_fmt)
                sheet.write(row_idx, 5, r['epf2'], num_fmt)
                sheet.write(row_idx, 6, r['diff'], num_fmt)
                sheet.write(row_idx, 7, r['reason'], text_fmt)

            workbook.close()
            output.seek(0)
            xlsx_content = output.read()
        else:
            xlsx_content = b"Excel export requires xlsxwriter library."

        try:
            from odoo.tools import BinaryBytes# pyrefly: ignore [missing-import]
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
