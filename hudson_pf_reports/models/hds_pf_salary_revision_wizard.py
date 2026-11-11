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


class HdsPfSalaryRevisionWizard(models.TransientModel):
    _name = 'hds.pf.salary.revision.wizard'
    _inherit = 'hds.pf.report.wizard.base'
    _description = 'Salary Revision Impact Report Wizard'

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([('draft', 'Draft'), ('generated', 'Generated')], string='State', default='draft')
    xlsx_file = fields.Binary(string='Salary Revision Impact Excel (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    @api.depends('year')
    def _compute_name(self):
        for rec in self:
            rec.name = f"Salary Revision Impact / {rec.year}"

    def action_export_xlsx(self):
        self.ensure_one()
        if 'hds.hr.snapshot' not in self.env:
            raise UserError(_("HR Snapshot module (hudson_hr_snapshot) is not installed."))
        snapshots = self.env['hds.hr.snapshot'].search([
            ('company_id', '=', self.company_id.id),
        ], order='employee_id asc, snapshot_date asc')

        if not snapshots:
            raise UserError(_("No HR Snapshots found for company %s. HR Snapshots are generated when payslips are confirmed.") % self.company_id.name)

        # Group snapshots by employee and find revisions
        emp_snapshots = {}
        for s in snapshots:
            emp_snapshots.setdefault(s.employee_id.id, []).append(s)

        revision_rows = []
        for emp_id, s_list in emp_snapshots.items():
            if len(s_list) < 2:
                continue
            for i in range(1, len(s_list)):
                prev_s = s_list[i - 1]
                curr_s = s_list[i]

                # Check if basic salary changed
                if prev_s.basic_salary != curr_s.basic_salary:
                    emp_name = curr_s.employee_id.name or prev_s.employee_code or 'Employee'
                    eff_date = str(curr_s.snapshot_date.date()) if curr_s.snapshot_date else curr_s.payroll_period

                    revision_rows.append({
                        'employee': emp_name,
                        'code': curr_s.employee_code,
                        'old_basic': round(prev_s.basic_salary, 2),
                        'new_basic': round(curr_s.basic_salary, 2),
                        'old_pf': round(prev_s.snapshot_pf_wage, 2),
                        'new_pf': round(curr_s.snapshot_pf_wage, 2),
                        'effective_date': eff_date,
                    })

        xlsx_filename = f"Salary_Revision_Impact_{self.year}.xlsx"

        output = io.BytesIO()
        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('Salary Revision Impact')
            sheet.set_column(0, 0, 26)  # Employee
            sheet.set_column(1, 1, 16)  # Employee Code
            sheet.set_column(2, 2, 18)  # Old Basic Salary
            sheet.set_column(3, 3, 18)  # New Basic Salary
            sheet.set_column(4, 4, 18)  # Old PF Wage
            sheet.set_column(5, 5, 18)  # New PF Wage
            sheet.set_column(6, 6, 32)  # Effective Snapshot Date / Period

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
            headers = ['Employee', 'Employee Code', 'Old Basic Salary', 'New Basic Salary', 'Old PF Wage', 'New PF Wage', 'Effective Snapshot Date / Period']
            for col_idx, text in enumerate(headers):
                sheet.write(0, col_idx, text, header_fmt)

            for row_idx, r in enumerate(revision_rows, start=1):
                sheet.write(row_idx, 0, r['employee'], text_fmt)
                sheet.write(row_idx, 1, r['code'], text_fmt)
                sheet.write(row_idx, 2, r['old_basic'], num_fmt)
                sheet.write(row_idx, 3, r['new_basic'], num_fmt)
                sheet.write(row_idx, 4, r['old_pf'], num_fmt)
                sheet.write(row_idx, 5, r['new_pf'], num_fmt)
                sheet.write(row_idx, 6, r['effective_date'], text_fmt)

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
