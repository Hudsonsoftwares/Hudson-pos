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


class HdsPfRegisterWizard(models.TransientModel):
    _name = 'hds.pf.register.wizard'
    _inherit = 'hds.pf.report.wizard.base'
    _description = 'PF Register & Employee PF Statement Wizard'

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
    ], string='State', default='draft')

    xlsx_file = fields.Binary(string='PF Register Excel File (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    display_month_year = fields.Char(string='Payroll Period Label', compute='_compute_display_month_year')

    # Company Aggregate Summary Fields (Case 1: Employee NOT Selected)
    record_count = fields.Integer(string='Total Employees', readonly=True)
    total_pf_wages = fields.Float(string='Total PF Wages', readonly=True)
    total_employee_epf = fields.Float(string='Total Employee EPF', readonly=True)
    total_employer_epf = fields.Float(string='Total Employer EPF', readonly=True)
    total_employer_eps = fields.Float(string='Total Employer EPS', readonly=True)
    total_edli = fields.Float(string='Total EDLI', readonly=True)
    total_employer_cost = fields.Float(string='Total Employer Cost', readonly=True)

    # Employee PF Summary Fields (Case 2: Employee IS Selected)
    emp_summary_name = fields.Char(string='Employee Name', readonly=True)
    emp_summary_code = fields.Char(string='Employee ID', readonly=True)
    emp_summary_department = fields.Char(string='Department', readonly=True)
    emp_summary_designation = fields.Char(string='Designation', readonly=True)
    emp_summary_uan = fields.Char(string='UAN Number', readonly=True)
    emp_summary_pf_applicable = fields.Char(string='PF Applicable', readonly=True)
    emp_summary_basis = fields.Char(string='Contribution Basis', readonly=True)
    emp_summary_pf_wage = fields.Float(string='PF Wage', readonly=True)
    emp_summary_ee_epf = fields.Float(string='Employee EPF', readonly=True)
    emp_summary_er_epf = fields.Float(string='Employer EPF Share', readonly=True)
    emp_summary_er_eps = fields.Float(string='Employer EPS', readonly=True)
    emp_summary_edli_admin = fields.Float(string='EDLI & Admin Charges', readonly=True)
    emp_summary_total_cost = fields.Float(string='Employer Total Cost', readonly=True)

    @api.depends('month', 'year', 'employee_id')
    def _compute_name(self):
        month_dict = dict(self._fields['month'].selection)
        for rec in self:
            m_label = month_dict.get(rec.month, '')
            if rec.employee_id:
                rec.name = f"{m_label} {rec.year}"
            else:
                rec.name = f"PF Register / {m_label}-{rec.year}"

    @api.depends('month', 'year')
    def _compute_display_month_year(self):
        month_dict = dict(self._fields['month'].selection)
        for rec in self:
            m_label = month_dict.get(rec.month, '')
            rec.display_month_year = f"{m_label} {rec.year}"

    def action_reset_draft(self):
        self.ensure_one()
        self.write({'state': 'draft'})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_export_xlsx(self):
        self.ensure_one()
        payslips = self._get_confirmed_payslips([('employee_id.hds_in_epf_applicable', '=', True)])

        if not payslips:
            period_label = self._get_month_label()
            if self.employee_id:
                raise UserError(_("No confirmed payslip found for employee '%s' in period (%s).") % (self.employee_id.name, period_label))
            raise UserError(_("No confirmed payslips found for EPF-applicable employees in period (%s).") % period_label)

        if self.employee_id:
            # --------------------------------------------------
            # CASE 2: Employee Selected -> Employee PF Statement
            # --------------------------------------------------
            payslip_list = payslips.filtered(lambda p: p.employee_id == self.employee_id)
            if not payslip_list:
                raise UserError(_("No confirmed payslip found for employee '%s' in period (%s).") % (self.employee_id.name, self._get_month_label()))
            payslip = payslip_list[0]
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

            pf_vals = self._get_pf_line_amounts(payslip)
            pf_wage = pf_vals['pf_wage']
            ee_epf = pf_vals['ee_epf']
            er_epf = pf_vals['er_epf']
            er_eps = pf_vals['er_eps']
            edli_admin = pf_vals['edli'] + pf_vals['admin']
            total_cost = pf_vals['total_cost']

            emp_pf_app = 'Yes' if getattr(emp, 'hds_in_epf_applicable', False) else 'No'

            month_label = self._get_month_label().replace('-', '_')
            xlsx_filename = f"PF_Statement_{emp.name.replace(' ', '_')}_{month_label}.xlsx"

            output = io.BytesIO()
            if xlsxwriter:
                workbook = xlsxwriter.Workbook(output, {'in_memory': True})
                sheet = workbook.add_worksheet('Employee PF Statement')
                sheet.set_column(0, 0, 30)
                sheet.set_column(1, 1, 30)

                title_fmt = workbook.add_format({'bold': True, 'font_size': 14})
                label_fmt = workbook.add_format({'bold': True, 'bg_color': '#1F4E78', 'font_color': '#FFFFFF', 'border': 1})
                val_fmt = workbook.add_format({'border': 1})
                num_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1})

                sheet.write(0, 0, f"EMPLOYEE PF STATEMENT — {self._get_month_label()} ({emp.name})", title_fmt)
                sheet.write(2, 0, "Employee Name", label_fmt)
                sheet.write(2, 1, emp.name, val_fmt)
                sheet.write(3, 0, "Employee ID", label_fmt)
                sheet.write(3, 1, emp.identification_id or '', val_fmt)
                sheet.write(4, 0, "Department", label_fmt)
                sheet.write(4, 1, emp.department_id.name if emp.department_id else '', val_fmt)
                sheet.write(5, 0, "Designation", label_fmt)
                sheet.write(5, 1, emp.job_id.name if emp.job_id else '', val_fmt)
                sheet.write(6, 0, "UAN Number", label_fmt)
                sheet.write(6, 1, getattr(emp, 'hds_in_uan', '') or '', val_fmt)
                sheet.write(7, 0, "Contribution Basis", label_fmt)
                sheet.write(7, 1, basis_label, val_fmt)

                sheet.write(9, 0, "Contribution Type", label_fmt)
                sheet.write(9, 1, "Amount", label_fmt)

                sheet.write(10, 0, "PF Wage", val_fmt)
                sheet.write(10, 1, round(pf_wage, 2), num_fmt)
                sheet.write(11, 0, "Employee EPF", val_fmt)
                sheet.write(11, 1, round(ee_epf, 2), num_fmt)
                sheet.write(12, 0, "Employer EPF Share", val_fmt)
                sheet.write(12, 1, round(er_epf, 2), num_fmt)
                sheet.write(13, 0, "Employer EPS", val_fmt)
                sheet.write(13, 1, round(er_eps, 2), num_fmt)
                sheet.write(14, 0, "EDLI & Admin Charges", val_fmt)
                sheet.write(14, 1, round(edli_admin, 2), num_fmt)
                sheet.write(15, 0, "Employer Total Statutory Cost", label_fmt)
                sheet.write(15, 1, round(total_cost, 2), num_fmt)

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
                'emp_summary_name': emp.name,
                'emp_summary_code': emp.identification_id or '',
                'emp_summary_department': emp.department_id.name if emp.department_id else '',
                'emp_summary_designation': emp.job_id.name if emp.job_id else '',
                'emp_summary_uan': getattr(emp, 'hds_in_uan', '') or '',
                'emp_summary_pf_applicable': emp_pf_app,
                'emp_summary_basis': basis_label,
                'emp_summary_pf_wage': round(pf_wage, 2),
                'emp_summary_ee_epf': round(ee_epf, 2),
                'emp_summary_er_epf': round(er_epf, 2),
                'emp_summary_er_eps': round(er_eps, 2),
                'emp_summary_edli_admin': round(edli_admin, 2),
                'emp_summary_total_cost': round(total_cost, 2),
                'xlsx_file': file_data,
                'xlsx_filename': xlsx_filename,
            })

        else:
            # --------------------------------------------------
            # CASE 1: Employee NOT Selected -> Company PF Register
            # --------------------------------------------------
            rows = []
            tot_wages = 0.0
            tot_ee_epf = 0.0
            tot_er_epf = 0.0
            tot_er_eps = 0.0
            tot_edli = 0.0
            tot_er_cost = 0.0

            for payslip in payslips:
                emp = payslip.employee_id
                uan = emp.hds_in_uan or ''

                pf_vals = self._get_pf_line_amounts(payslip)
                pf_wage = pf_vals['pf_wage']
                ee_epf = pf_vals['ee_epf']
                er_epf = pf_vals['er_epf']
                er_eps = pf_vals['er_eps']
                edli = pf_vals['edli']
                er_cost = pf_vals['total_cost']

                rows.append({
                    'employee': emp.name,
                    'uan': uan,
                    'pf_wage': round(pf_wage, 2),
                    'ee_epf': round(ee_epf, 2),
                    'er_epf': round(er_epf, 2),
                    'er_eps': round(er_eps, 2),
                    'edli': round(edli, 2),
                    'er_cost': round(er_cost, 2),
                })

                tot_wages += pf_wage
                tot_ee_epf += ee_epf
                tot_er_epf += er_epf
                tot_er_eps += er_eps
                tot_edli += edli
                tot_er_cost += er_cost

            month_label = self._get_month_label().replace('-', '_')
            xlsx_filename = f"PF_Register_{month_label}.xlsx"

            output = io.BytesIO()
            if xlsxwriter:
                workbook = xlsxwriter.Workbook(output, {'in_memory': True})
                sheet = workbook.add_worksheet('PF Register')
                sheet.set_column(0, 0, 26)  # Employee
                sheet.set_column(1, 1, 18)  # UAN
                sheet.set_column(2, 2, 18)  # PF Wage
                sheet.set_column(3, 3, 16)  # Employee EPF
                sheet.set_column(4, 4, 16)  # Employer EPF
                sheet.set_column(5, 5, 16)  # Employer EPS
                sheet.set_column(6, 6, 16)  # EDLI
                sheet.set_column(7, 7, 22)  # Total Employer Cost

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
                text_fmt = workbook.add_format({'border': 1, 'align': 'left', 'valign': 'vcenter'})
                total_fmt = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'bg_color': '#D9E1F2', 'border': 1, 'align': 'right', 'valign': 'vcenter'})

                sheet.write(0, 0, f"PF REGISTER — {self._get_month_label()} ({self.company_id.name})", title_fmt)

                sheet.set_row(2, 26)
                headers = [
                    'Employee', 'UAN', 'PF Wage', 'Employee EPF',
                    'Employer EPF', 'Employer EPS', 'EDLI', 'Total Employer Cost'
                ]
                for col_idx, text in enumerate(headers):
                    sheet.write(2, col_idx, text, header_fmt)

                for row_idx, r in enumerate(rows, start=3):
                    sheet.write(row_idx, 0, r['employee'], text_fmt)
                    sheet.write(row_idx, 1, r['uan'], text_fmt)
                    sheet.write(row_idx, 2, r['pf_wage'], num_fmt)
                    sheet.write(row_idx, 3, r['ee_epf'], num_fmt)
                    sheet.write(row_idx, 4, r['er_epf'], num_fmt)
                    sheet.write(row_idx, 5, r['er_eps'], num_fmt)
                    sheet.write(row_idx, 6, r['edli'], num_fmt)
                    sheet.write(row_idx, 7, r['er_cost'], num_fmt)

                tot_row = len(rows) + 3
                sheet.write(tot_row, 0, "TOTAL", total_fmt)
                sheet.write(tot_row, 1, "", total_fmt)
                sheet.write(tot_row, 2, tot_wages, total_fmt)
                sheet.write(tot_row, 3, tot_ee_epf, total_fmt)
                sheet.write(tot_row, 4, tot_er_epf, total_fmt)
                sheet.write(tot_row, 5, tot_er_eps, total_fmt)
                sheet.write(tot_row, 6, tot_edli, total_fmt)
                sheet.write(tot_row, 7, tot_er_cost, total_fmt)

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
                'record_count': len(rows),
                'total_pf_wages': tot_wages,
                'total_employee_epf': tot_ee_epf,
                'total_employer_epf': tot_er_epf,
                'total_employer_eps': tot_er_eps,
                'total_edli': tot_edli,
                'total_employer_cost': tot_er_cost,
            })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=xlsx_file&filename_field=xlsx_filename&download=true',
            'target': 'self',
        }
