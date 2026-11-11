# -*- coding: utf-8 -*-
base64_import = True
import base64
import calendar
import io
from datetime import date
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError
# pyrefly: ignore [missing-import]
from odoo.addons.hudson_in_payroll.services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
# pyrefly: ignore [missing-import]
from odoo.addons.hudson_in_payroll.services.lwf.lwf_service import LWFService

try:
    # pyrefly: ignore [missing-import]
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HdsLwfReportWizard(models.Model):
    _name = 'hds.lwf.report.wizard'
    _description = 'Labour Welfare Fund (LWF) Report'
    _order = 'id desc'

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
    ], string='State', default='draft')

    date_from = fields.Date(
        string='From Date',
        default=lambda self: date(fields.Date.today().year, 1, 1),
        required=True
    )
    date_to = fields.Date(
        string='To Date',
        default=lambda self: date(fields.Date.today().year, 12, 31),
        required=True
    )

    @api.depends('date_from', 'date_to', 'department_id')
    def _compute_name(self):
        for rec in self:
            f_str = rec.date_from.strftime('%d-%b-%Y') if rec.date_from else ''
            t_str = rec.date_to.strftime('%d-%b-%Y') if rec.date_to else ''
            dept_str = f" ({rec.department_id.name})" if rec.department_id else ""
            if f_str or t_str:
                rec.name = f"LWF Report / {f_str} to {t_str}{dept_str}"
            else:
                rec.name = "LWF Report"

    @api.onchange('date_from')
    def _onchange_date_from(self):
        if self.date_from:
            last_day = calendar.monthrange(self.date_from.year, self.date_from.month)[1]
            self.date_to = self.date_from.replace(day=last_day)

    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        help='Optional department filter. If left empty, all applicable employees are included.'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    payslip_state = fields.Selection([
        ('all', 'All States (Draft, Verify, Done, Paid)'),
        ('confirmed', 'Confirmed & Paid (Done, Paid)'),
    ], string='Payslip State', default='all', required=True)

    xlsx_file = fields.Binary(string='LWF Report Excel File (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    record_count = fields.Integer(string='Total Employees Covered', readonly=True)
    total_ee_contrib = fields.Float(string='Total Employee LWF', readonly=True)
    total_er_contrib = fields.Float(string='Total Employer LWF', readonly=True)
    total_contrib = fields.Float(string='Total LWF Payable', readonly=True)

    def _get_target_employees(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('hds_in_lwf_applicable', '=', True),
            ('active', '=', True)
        ]
        if self.department_id:
            domain.append(('department_id', '=', self.department_id.id))

        return self.env['hr.employee'].search(domain)

    def _get_lwf_data(self):
        self.ensure_one()
        employees = self._get_target_employees()

        if not employees:
            raise UserError(_("No active LWF-applicable employees found matching the selected criteria."))

        # Pre-export statutory LWF compliance validation
        compliance_service = StatutoryComplianceValidationService(self.env)
        compliance_service.validate_scope_compliance(
            employees=employees,
            statutory_type='lwf',
            report_title='Labour Welfare Fund (LWF) Report'
        )

        lwf_service = LWFService(self.env)
        lwf_rows = []

        tot_ee_contrib = 0.0
        tot_er_contrib = 0.0
        tot_total_contrib = 0.0

        if self.payslip_state == 'all':
            state_domain = [('state', 'in', ['draft', 'verify', 'done', 'paid'])]
        elif self.payslip_state == 'confirmed':
            state_domain = [('state', 'in', ['done', 'paid'])]
        elif self.payslip_state == 'done':
            state_domain = [('state', '=', 'done')]
        elif self.payslip_state == 'paid':
            state_domain = [('state', '=', 'paid')]
        else:
            state_domain = [('state', 'in', ['draft', 'verify', 'done', 'paid'])]

        for emp in employees:
            lwf_account_no = getattr(emp, 'hds_in_lwf_number', False) or ''
            emp_code = (
                getattr(emp, 'registration_number', False)
                or getattr(emp, 'employee_code', False)
                or getattr(emp, 'barcode', False)
                or getattr(emp, 'identification_id', False)
                or ''
            )
            lwf_no = lwf_account_no or emp_code or str(emp.id)
            emp_name = emp.name or ''
            dept_name = emp.department_id.name if emp.department_id else ''

            state_rec = False
            if emp.work_location_id:
                state_rec = getattr(emp.work_location_id, 'state_id', False) or getattr(getattr(emp.work_location_id, 'address_id', None), 'state_id', False)
            if not state_rec and self.company_id:
                state_rec = getattr(self.company_id, 'state_id', False) or getattr(getattr(self.company_id, 'partner_id', None), 'state_id', False)

            state_name = state_rec.name if state_rec else ''

            # Find matching payslips within the date range according to selected state filter
            domain = [
                ('employee_id', '=', emp.id),
                ('date_from', '>=', self.date_from),
                ('date_to', '<=', self.date_to)
            ] + state_domain
            payslips = self.env['hr.payslip'].search(domain)

            ee_contrib = 0.0
            er_contrib = 0.0

            if payslips:
                for payslip in payslips:
                    lines = payslip.line_ids
                    ee_lines = lines.filtered(lambda l: l.code in ('LWF_EE', 'LWF'))
                    er_lines = lines.filtered(lambda l: l.code in ('LWF_ER', 'EMPR_LWF'))

                    if ee_lines:
                        ee_contrib += abs(sum(ee_lines.mapped('total')))
                    else:
                        ee_contrib += lwf_service.compute_lwf_employee(payslip)

                    if er_lines:
                        er_contrib += abs(sum(er_lines.mapped('total')))
                    else:
                        er_contrib += lwf_service.compute_lwf_employer(payslip)
            else:
                # Calculate default scheduled contribution using LWFService
                ee_contrib = lwf_service.compute_lwf_employee({'employee': emp})
                er_contrib = lwf_service.compute_lwf_employer({'employee': emp})

            total_contrib = round(ee_contrib + er_contrib, 2)

            lwf_rows.append({
                'lwf_account_no': lwf_account_no,
                'emp_code': emp_code,
                'lwf_no': lwf_no,
                'emp_name': emp_name,
                'department': dept_name,
                'state': state_name,
                'ee_contrib': round(ee_contrib, 2),
                'er_contrib': round(er_contrib, 2),
                'total_contrib': total_contrib,
                'status': 'Compliant',
            })

            tot_ee_contrib += ee_contrib
            tot_er_contrib += er_contrib
            tot_total_contrib += total_contrib

        return {
            'lwf_rows': lwf_rows,
            'tot_ee_contrib': round(tot_ee_contrib, 2),
            'tot_er_contrib': round(tot_er_contrib, 2),
            'tot_total_contrib': round(tot_total_contrib, 2),
            'dept_label': self.department_id.name if self.department_id else 'All Departments',
        }

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref('hudson_in_payroll.action_report_lwf').report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        data = self._get_lwf_data()
        lwf_rows = data['lwf_rows']
        tot_ee_contrib = data['tot_ee_contrib']
        tot_er_contrib = data['tot_er_contrib']
        tot_total_contrib = data['tot_total_contrib']
        dept_label = data['dept_label']

        year_str = self.date_from.strftime('%Y') if self.date_from else str(fields.Date.today().year)
        xlsx_filename = f"Labour_Welfare_Fund_Summary_{year_str}.xlsx"

        output = io.BytesIO()
        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('Labour Welfare Fund Summary')

            # Ensure grid lines are visible on screen
            sheet.hide_gridlines(0)

            # Styling definitions
            title_fmt = workbook.add_format({
                'bold': True,
                'font_size': 18,
                'align': 'center',
                'valign': 'vcenter',
                'font_color': '#000000',
            })
            company_fmt = workbook.add_format({
                'font_size': 11,
                'valign': 'vcenter',
                'font_color': '#000000',
            })
            subheader_fmt = workbook.add_format({
                'font_size': 10,
                'valign': 'vcenter',
                'font_color': '#000000',
            })
            date_fmt = workbook.add_format({
                'font_size': 10,
                'align': 'center',
                'valign': 'vcenter',
                'font_color': '#000000',
            })
            header_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#E0E0E0',
                'font_color': '#000000',
                'font_size': 10,
                'border': 1,
                'border_color': '#D9D9D9',
                'align': 'left',
                'valign': 'vcenter',
            })
            text_fmt = workbook.add_format({
                'font_size': 10,
                'border': 1,
                'border_color': '#D9D9D9',
                'valign': 'vcenter',
                'align': 'left',
            })
            curr_fmt = workbook.add_format({
                'font_size': 10,
                'num_format': '[$₹-en-IN] #,##0.00; -[$₹-en-IN] #,##0.00',
                'border': 1,
                'border_color': '#D9D9D9',
                'align': 'right',
                'valign': 'vcenter',
            })

            # Row 1: Merged Title A1:F1
            sheet.merge_range(0, 0, 0, 5, "Labour Welfare Fund Summary", title_fmt)
            sheet.set_row(0, 36)

            # Row 2: Company Name in A2
            sheet.write(1, 0, self.company_id.name or '', company_fmt)
            sheet.set_row(1, 20)

            # Row 3: Labour Identification Number in A3, Date Range across D3:E3
            lin = (
                getattr(self.company_id, 'hds_in_lwf_registration_no', False)
                or getattr(self.company_id, 'hds_in_lin_number', False)
                or getattr(self.company_id, 'lin', False)
                or getattr(self.company_id, 'hds_in_lin', False)
                or ''
            )
            lin_text = f"Labour Identification Number: {lin}" if lin else "Labour Identification Number:"
            sheet.write(2, 0, lin_text, subheader_fmt)

            date_str = f"{self.date_from.strftime('%d/%m/%Y')} to {self.date_to.strftime('%d/%m/%Y')}"
            sheet.merge_range(2, 3, 2, 4, date_str, date_fmt)
            sheet.set_row(2, 20)

            # Column widths
            sheet.set_column(0, 0, 22)  # LWF Account Number
            sheet.set_column(1, 1, 16)  # Employee ID
            sheet.set_column(2, 2, 26)  # Employee Name
            sheet.set_column(3, 3, 24)  # Employees' Contribution
            sheet.set_column(4, 4, 24)  # Employer's Contribution
            sheet.set_column(5, 5, 20)  # Total Contribution

            # Row 4: Column Headers
            headers = [
                'LWF Account Number',
                'Employee ID',
                'Employee Name',
                "Employees' Contribution",
                "Employer's Contribution",
                'Total Contribution',
            ]
            sheet.set_row(3, 24)
            for col_idx, text in enumerate(headers):
                sheet.write(3, col_idx, text, header_fmt)

            # Rows 5+: Data Rows
            for idx, r in enumerate(lwf_rows):
                row_idx = 4 + idx
                sheet.set_row(row_idx, 20)
                sheet.write(row_idx, 0, r.get('lwf_account_no', '') or '', text_fmt)
                sheet.write(row_idx, 1, r.get('emp_code', '') or '', text_fmt)
                sheet.write(row_idx, 2, r.get('emp_name', '') or '', text_fmt)

                ee_val = -abs(r['ee_contrib']) if r['ee_contrib'] else 0.0
                er_val = -abs(r['er_contrib']) if r['er_contrib'] else 0.0
                tot_val = -abs(r['total_contrib']) if r['total_contrib'] else 0.0

                sheet.write(row_idx, 3, ee_val, curr_fmt)
                sheet.write(row_idx, 4, er_val, curr_fmt)
                sheet.write(row_idx, 5, tot_val, curr_fmt)

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
            'record_count': len(lwf_rows),
            'total_ee_contrib': round(tot_ee_contrib, 2),
            'total_er_contrib': round(tot_er_contrib, 2),
            'total_contrib': round(tot_total_contrib, 2),
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

    @api.onchange('date_from', 'date_to', 'department_id', 'company_id', 'payslip_state')
    def _onchange_report_filters(self):
        try:
            if not self.company_id:
                return
            employees = self._get_target_employees()
            self.record_count = len(employees)
        except Exception:
            pass
