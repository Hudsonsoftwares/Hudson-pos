# -*- coding: utf-8 -*-
import base64
import io
import logging
from datetime import date
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError
# pyrefly: ignore [missing-import]
from odoo.addons.hudson_in_payroll.services.gratuity.gratuity_validator import GratuityValidator# pyrefly: ignore [missing-import]
from odoo.addons.hudson_in_payroll.services.gratuity.gratuity_data_service import GratuityDataService# pyrefly: ignore [missing-import]
from odoo.addons.hudson_in_payroll.services.gratuity.gratuity_calculator import GratuityCalculator# pyrefly: ignore [missing-import]

_logger = logging.getLogger(__name__)

try:
    # pyrefly: ignore [missing-import]
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HdsGratuityReportWizard(models.Model):
    _name = 'hds.gratuity.report.wizard'
    _description = 'Gratuity Calculation Report'
    _order = 'id desc'

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
    ], string='State', default='draft')

    selection_mode = fields.Selection([
        ('by_employee', 'By Employee'),
        ('by_department', 'By Department'),
        ('by_job', 'By Job Position'),
        ('by_structure', 'By Salary Structure'),
        ('by_tag', 'By Employee Tag'),
    ], string='Selection Mode', default='by_employee', required=True)

    @api.depends('selection_mode', 'create_date')
    def _compute_name(self):
        mode_dict = dict(self._fields['selection_mode'].selection)
        for rec in self:
            m_label = mode_dict.get(rec.selection_mode, 'Gratuity')
            d_str = fields.Date.today().strftime('%d-%b-%Y')
            rec.name = f"Gratuity Report ({m_label}) / {d_str}"

    employee_ids = fields.Many2many(
        'hr.employee',
        'hds_gratuity_wiz_emp_rel',
        'wiz_id',
        'emp_id',
        string='Employees',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]"
    )
    department_ids = fields.Many2many(
        'hr.department',
        'hds_gratuity_wiz_dept_rel',
        'wiz_id',
        'dept_id',
        string='Departments',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]"
    )
    job_ids = fields.Many2many(
        'hr.job',
        'hds_gratuity_wiz_job_rel',
        'wiz_id',
        'job_id',
        string='Job Positions',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]"
    )
    structure_ids = fields.Many2many(
        'hr.payroll.structure',
        'hds_gratuity_wiz_struct_rel',
        'wiz_id',
        'struct_id',
        string='Salary Structures',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]"
    )
    category_ids = fields.Many2many(
        'hr.employee.category',
        'hds_gratuity_wiz_cat_rel',
        'wiz_id',
        'cat_id',
        string='Employee Tags'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    @api.onchange('company_id')
    def _onchange_company_id(self):
        for wiz in self:
            if wiz.state == 'draft':
                wiz.employee_ids = [(5, 0, 0)]
                wiz.department_ids = [(5, 0, 0)]
                wiz.job_ids = [(5, 0, 0)]
                wiz.structure_ids = [(5, 0, 0)]

    xlsx_file = fields.Binary(string='Gratuity Excel File (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    record_count = fields.Integer(
        string='Total Employees Evaluated',
        compute='_compute_summary_statistics',
        store=True,
        readonly=True
    )
    eligible_count = fields.Integer(
        string='Eligible Employees',
        compute='_compute_summary_statistics',
        store=True,
        readonly=True
    )
    ineligible_count = fields.Integer(
        string='Ineligible Employees',
        compute='_compute_summary_statistics',
        store=True,
        readonly=True
    )
    total_wage_base = fields.Float(
        string='Total Wage Base',
        compute='_compute_summary_statistics',
        store=True,
        readonly=True
    )
    total_gratuity_payable = fields.Float(
        string='Total Payable Gratuity',
        compute='_compute_summary_statistics',
        store=True,
        readonly=True
    )

    def _get_target_employees(self):
        self.ensure_one()
        if not self.company_id:
            return self.env['hr.employee'].browse()

        domain = [('company_id', '=', self.company_id.id)]

        if self.selection_mode == 'by_employee':
            if self.employee_ids:
                return self.employee_ids.filtered(lambda e: not e.company_id or e.company_id == self.company_id)
            return self.env['hr.employee'].browse()
        elif self.selection_mode == 'by_department':
            if self.department_ids:
                domain.append(('department_id', 'in', self.department_ids.ids))
                return self.env['hr.employee'].search(domain)
            return self.env['hr.employee'].browse()
        elif self.selection_mode == 'by_job':
            if self.job_ids:
                domain.append(('job_id', 'in', self.job_ids.ids))
                return self.env['hr.employee'].search(domain)
            return self.env['hr.employee'].browse()
        elif self.selection_mode == 'by_structure':
            if self.structure_ids:
                contract_model = 'hr.version' if 'hr.version' in self.env else ('hr.contract' if 'hr.contract' in self.env else False)
                contracts = self.env[contract_model].search([
                    ('struct_id', 'in', self.structure_ids.ids),
                    '|', ('company_id', '=', False), ('company_id', '=', self.company_id.id),
                ]) if contract_model else False
                if contracts:
                    domain.append(('id', 'in', contracts.mapped('employee_id').ids))
                    return self.env['hr.employee'].search(domain)
            return self.env['hr.employee'].browse()
        elif self.selection_mode == 'by_tag':
            if self.category_ids:
                domain.append(('category_ids', 'in', self.category_ids.ids))
                return self.env['hr.employee'].search(domain)
            return self.env['hr.employee'].browse()

        return self.env['hr.employee'].browse()

    def _calculate_gratuity_rows(self, employees):
        if not employees:
            return {
                'gratuity_rows': [],
                'tot_wage_base': 0.0,
                'tot_raw_gratuity': 0.0,
                'tot_final_gratuity': 0.0,
                'record_count': 0,
                'eligible_count': 0,
                'ineligible_count': 0,
            }

        validator = GratuityValidator(self.env)
        data_service = GratuityDataService(self.env)
        calculator = GratuityCalculator()

        eval_date = fields.Date.today()
        gratuity_rows = []

        tot_wage_base = 0.0
        tot_raw_gratuity = 0.0
        tot_final_gratuity = 0.0
        elig_cnt = 0

        contract_model = 'hr.version' if 'hr.version' in self.env else ('hr.contract' if 'hr.contract' in self.env else False)

        for emp in employees:
            try:
                emp_code = getattr(emp, 'registration_number', False) or getattr(emp, 'barcode', False) or str(emp.id)
                emp_name = emp.name or ''
                dept_name = emp.department_id.name if emp.department_id else ''
                job_name = emp.job_id.name if emp.job_id else ''

                joining_date = getattr(emp, 'hds_in_gratuity_joining_date', False) or getattr(emp, 'first_contract_date', False) or (emp.create_date.date() if emp.create_date else fields.Date.today())

                emp_origin_id = emp._origin.id if hasattr(emp, '_origin') and emp._origin else (emp.id if isinstance(emp.id, int) else False)
                contract = getattr(emp, 'contract_id', False) or (self.env[contract_model].search([('employee_id', '=', emp_origin_id)], limit=1) if (contract_model and emp_origin_id) else False)

                val_res = validator.validate(
                    employee=emp,
                    contract=contract,
                    calc_date=eval_date
                )

                calc_data = data_service.prepare_calculation_data(
                    employee=emp,
                    contract=contract,
                    separation_date=eval_date,
                    calc_date=eval_date
                )

                calc_res = calculator.calculate(calc_data)
                is_eligible = val_res.is_eligible
                raw_gratuity = round(calc_res.raw_gratuity_amount, 2) if is_eligible else 0.0
                final_gratuity = round(calc_res.final_gratuity_amount, 2) if is_eligible else 0.0
                if is_eligible:
                    elig_cnt += 1

                gratuity_rows.append({
                    'emp_code': emp_code,
                    'emp_name': emp_name,
                    'department': dept_name,
                    'job': job_name,
                    'joining_date': str(joining_date) if joining_date else '',
                    'completed_years': calc_data.completed_years,
                    'wage_base': round(calc_data.wage_base, 2),
                    'status': 'Eligible' if is_eligible else 'Not Eligible',
                    'raw_gratuity': raw_gratuity,
                    'final_gratuity': final_gratuity,
                })

                tot_wage_base += calc_data.wage_base
                tot_raw_gratuity += raw_gratuity
                tot_final_gratuity += final_gratuity
            except Exception as e:
                _logger.warning("Error computing gratuity for employee %s: %s", emp.name, e)
                continue

        rec_count = len(gratuity_rows)
        return {
            'gratuity_rows': gratuity_rows,
            'tot_wage_base': round(tot_wage_base, 2),
            'tot_raw_gratuity': round(tot_raw_gratuity, 2),
            'tot_final_gratuity': round(tot_final_gratuity, 2),
            'record_count': rec_count,
            'eligible_count': elig_cnt,
            'ineligible_count': rec_count - elig_cnt,
        }

    @api.depends('selection_mode', 'employee_ids', 'department_ids', 'job_ids', 'structure_ids', 'category_ids', 'company_id')
    def _compute_summary_statistics(self):
        for rec in self:
            employees = rec._get_target_employees()
            summary = rec._calculate_gratuity_rows(employees)
            rec.record_count = summary['record_count']
            rec.eligible_count = summary['eligible_count']
            rec.ineligible_count = summary['ineligible_count']
            rec.total_wage_base = summary['tot_wage_base']
            rec.total_gratuity_payable = summary['tot_final_gratuity']

    @api.onchange('selection_mode', 'employee_ids', 'department_ids', 'job_ids', 'structure_ids', 'category_ids', 'company_id')
    def _onchange_selection_criteria(self):
        employees = self._get_target_employees()
        summary = self._calculate_gratuity_rows(employees)
        self.record_count = summary['record_count']
        self.eligible_count = summary['eligible_count']
        self.ineligible_count = summary['ineligible_count']
        self.total_wage_base = summary['tot_wage_base']
        self.total_gratuity_payable = summary['tot_final_gratuity']

    def _get_gratuity_data(self):
        self.ensure_one()
        employees = self._get_target_employees()

        if not employees:
            raise UserError(_("No active employees found matching the selected scope criteria. Please select at least one employee or selection filter."))

        summary = self._calculate_gratuity_rows(employees)
        mode_label = dict(self._fields['selection_mode'].selection).get(self.selection_mode, '')

        return {
            'gratuity_rows': summary['gratuity_rows'],
            'tot_wage_base': summary['tot_wage_base'],
            'tot_raw_gratuity': summary['tot_raw_gratuity'],
            'tot_final_gratuity': summary['tot_final_gratuity'],
            'mode_label': mode_label,
            'record_count': summary['record_count'],
            'eligible_count': summary['eligible_count'],
            'ineligible_count': summary['ineligible_count'],
        }

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('hudson_in_payroll.action_report_gratuity').report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        data = self._get_gratuity_data()
        gratuity_rows = data['gratuity_rows']
        tot_wage_base = data['tot_wage_base']
        tot_raw_gratuity = data['tot_raw_gratuity']
        tot_final_gratuity = data['tot_final_gratuity']
        mode_label = data['mode_label']

        today_str = fields.Date.today().strftime('%d_%b_%Y')
        xlsx_filename = f"Gratuity_Calculation_Report_{today_str}.xlsx"

        output = io.BytesIO()
        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('Gratuity Calculation')

            title_fmt = workbook.add_format({'bold': True, 'font_size': 14})
            sub_title_fmt = workbook.add_format({'font_size': 10, 'italic': True, 'font_color': '#555555'})
            header_fmt = workbook.add_format({'bold': True, 'bg_color': '#1F4E78', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
            num_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
            text_fmt = workbook.add_format({'border': 1})
            status_elig_fmt = workbook.add_format({'border': 1, 'bold': True, 'font_color': '#1E4620', 'bg_color': '#D4EDDA', 'align': 'center'})
            status_not_fmt = workbook.add_format({'border': 1, 'font_color': '#856404', 'bg_color': '#FFF3CD', 'align': 'center'})
            total_fmt = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'bg_color': '#D9E1F2', 'border': 1})

            sheet.write(0, 0, f"GRATUITY CALCULATION REPORT — {self.company_id.name}", title_fmt)
            mode_label = dict(self._fields['selection_mode'].selection).get(self.selection_mode, '')
            sheet.write(1, 0, f"Scope Mode: {mode_label} | Total Employees: {len(gratuity_rows)} | Date: {fields.Date.today()}", sub_title_fmt)

            # Explicit column widths to prevent ### overflow on currency amounts and long names
            sheet.set_column(0, 0, 14)
            sheet.set_column(1, 1, 24)
            sheet.set_column(2, 3, 20)
            sheet.set_column(4, 4, 16)
            sheet.set_column(5, 5, 22)
            sheet.set_column(6, 6, 24)
            sheet.set_column(7, 7, 18)
            sheet.set_column(8, 8, 24)

            headers = [
                'Employee ID', 'Employee Name', 'Department', 'Job Position',
                'Date of Joining', 'Service Tenure (Years)', 'Last Drawn Basic + DA (INR)',
                'Eligibility Status', 'Calculated Gratuity (INR)'
            ]
            for col_idx, text in enumerate(headers):
                sheet.write(3, col_idx, text, header_fmt)

            for row_idx, r in enumerate(gratuity_rows, start=4):
                sheet.write(row_idx, 0, r['emp_code'], text_fmt)
                sheet.write(row_idx, 1, r['emp_name'], text_fmt)
                sheet.write(row_idx, 2, r['department'], text_fmt)
                sheet.write(row_idx, 3, r['job'], text_fmt)
                sheet.write(row_idx, 4, r['joining_date'], text_fmt)
                sheet.write(row_idx, 5, r['completed_years'], text_fmt)
                sheet.write(row_idx, 6, r['wage_base'], num_fmt)

                s_fmt = status_elig_fmt if r['status'] == 'Eligible' else status_not_fmt
                sheet.write(row_idx, 7, r['status'], s_fmt)
                sheet.write(row_idx, 8, r['raw_gratuity'], num_fmt)

            tot_row = len(gratuity_rows) + 4
            sheet.write(tot_row, 0, "TOTAL", total_fmt)
            for c in range(1, 6):
                sheet.write(tot_row, c, "", total_fmt)
            sheet.write(tot_row, 6, round(tot_wage_base, 2), total_fmt)
            sheet.write(tot_row, 7, "", total_fmt)
            sheet.write(tot_row, 8, round(tot_raw_gratuity, 2), total_fmt)

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

        elig_cnt = sum(1 for r in gratuity_rows if r.get('status') == 'Eligible')
        inel_cnt = len(gratuity_rows) - elig_cnt

        self.write({
            'state': 'generated',
            'xlsx_file': file_data,
            'xlsx_filename': xlsx_filename,
            'record_count': len(gratuity_rows),
            'eligible_count': elig_cnt,
            'ineligible_count': inel_cnt,
            'total_wage_base': round(tot_wage_base, 2),
            'total_gratuity_payable': round(tot_final_gratuity, 2),
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=xlsx_file&filename_field=xlsx_filename&download=true',
            'target': 'new',
        }

    def action_download_xlsx(self):
        self.ensure_one()
        if not self.xlsx_file:
            return self.action_export_xlsx()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=xlsx_file&filename_field=xlsx_filename&download=true',
            'target': 'self',
        }


