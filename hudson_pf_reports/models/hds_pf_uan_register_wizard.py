# -*- coding: utf-8 -*-
import base64
import io
from odoo import api, fields, models, _# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError# pyrefly: ignore [missing-import]

try:
    import xlsxwriter# pyrefly: ignore [missing-import]
except ImportError:
    xlsxwriter = None


class HdsPfUanRegisterWizard(models.TransientModel):
    _name = 'hds.pf.uan.register.wizard'
    _description = 'UAN Register Wizard'

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, required=True)
    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([('draft', 'Draft'), ('generated', 'Generated')], string='State', default='draft')
    xlsx_file = fields.Binary(string='UAN Register Excel (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    @api.depends('company_id')
    def _compute_name(self):
        for rec in self:
            rec.name = f"UAN Register / {rec.company_id.name}"

    def action_export_xlsx(self):
        self.ensure_one()
        employees = self.env['hr.employee'].with_context(active_test=False).search([
            ('company_id', '=', self.company_id.id),
        ], order='name asc')

        if not employees:
            raise UserError(_("No employees found for company %s.") % self.company_id.name)

        rows = []
        for emp in employees:
            j_date = getattr(emp, 'joining_date', False)
            if not j_date:
                contracts = self.env['hr.version'].search([('employee_id', '=', emp.id)], order='id asc', limit=1)
                if contracts:
                    j_date = contracts.date_start

            exit_date = getattr(emp, 'resign_date', False) or getattr(emp, 'departure_date', False)

            rows.append({
                'employee': emp.name,
                'code': emp.identification_id or '',
                'uan': getattr(emp, 'hds_in_uan', '') or '',
                'pf_member_id': getattr(emp, 'hds_in_pf_member_id', '') or '',
                'doj': str(j_date) if j_date else '',
                'exit_date': str(exit_date) if exit_date else '',
                'epf_applicable': 'Yes' if getattr(emp, 'hds_in_epf_applicable', False) else 'No',
                'eps_applicable': 'Yes' if getattr(emp, 'hds_in_eps_applicable', False) else 'No',
                'active': 'Active' if emp.active else 'Archived/Resigned',
            })

        xlsx_filename = f"UAN_Register_{self.company_id.name.replace(' ', '_')}.xlsx"

        output = io.BytesIO()
        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('UAN Register')
            sheet.set_column(0, 0, 26)  # Employee Name
            sheet.set_column(1, 1, 16)  # Employee Code
            sheet.set_column(2, 2, 18)  # UAN
            sheet.set_column(3, 3, 22)  # PF Member ID
            sheet.set_column(4, 4, 20)  # Date of Joining (DOJ)
            sheet.set_column(5, 5, 16)  # Date of Exit
            sheet.set_column(6, 6, 16)  # EPF Applicable
            sheet.set_column(7, 7, 16)  # EPS Applicable
            sheet.set_column(8, 8, 18)  # Employment Status

            header_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#1F4E78',
                'font_color': '#FFFFFF',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'text_wrap': True,
            })
            text_fmt = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter'})
            text_center_fmt = workbook.add_format({'border': 1, 'align': 'center', 'valign': 'vcenter'})

            sheet.set_row(0, 26)
            headers = [
                'Employee Name', 'Employee Code', 'UAN', 'PF Member ID',
                'Date of Joining (DOJ)', 'Date of Exit', 'EPF Applicable', 'EPS Applicable', 'Employment Status'
            ]
            for col_idx, text in enumerate(headers):
                sheet.write(0, col_idx, text, header_fmt)

            for row_idx, r in enumerate(rows, start=1):
                sheet.write(row_idx, 0, r['employee'], text_fmt)
                sheet.write(row_idx, 1, r['code'], text_fmt)
                sheet.write(row_idx, 2, r['uan'], text_fmt)
                sheet.write(row_idx, 3, r['pf_member_id'], text_fmt)
                sheet.write(row_idx, 4, r['doj'], text_fmt)
                sheet.write(row_idx, 5, r['exit_date'], text_fmt)
                sheet.write(row_idx, 6, r['epf_applicable'], text_fmt)
                sheet.write(row_idx, 7, r['eps_applicable'], text_fmt)
                sheet.write(row_idx, 8, r['active'], text_fmt)

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
