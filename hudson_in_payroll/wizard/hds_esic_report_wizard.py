# -*- coding: utf-8 -*-
import base64
import calendar
import io
import math
from datetime import date
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError
# pyrefly: ignore [missing-import]
from odoo.addons.hudson_in_payroll.services.esic.validator import ESICValidator

try:
    # pyrefly: ignore [missing-import]
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HdsEsicReportWizard(models.Model):
    _name = 'hds.esic.report.wizard'
    _description = 'Employees State Insurance (ESI) Report Wizard'
    _order = 'id desc'

    @api.model
    def _default_year(self):
        return fields.Date.today().year

    @api.model
    def _default_month(self):
        return str(fields.Date.today().month)

    year = fields.Integer(
        string='Year',
        default=_default_year,
        required=True
    )
    month = fields.Selection([
        ('1', 'January'),
        ('2', 'February'),
        ('3', 'March'),
        ('4', 'April'),
        ('5', 'May'),
        ('6', 'June'),
        ('7', 'July'),
        ('8', 'August'),
        ('9', 'September'),
        ('10', 'October'),
        ('11', 'November'),
        ('12', 'December'),
    ], string='Month', default=_default_month, required=True)

    report_type = fields.Selection([
        ('esic_report', 'ESIC Report'),
        ('esi_summary', 'ESI Summary'),
    ], string='Report Type', default='esic_report', required=True)

    payslip_state = fields.Selection([
        ('all', 'All States (Draft, Verify, Done, Paid)'),
        ('confirmed', 'Confirmed & Paid (Done, Paid)'),
        ('done', 'Done Only'),
        ('paid', 'Paid Only'),
    ], string='Payslip Status', default='all', required=True)

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

    xlsx_file = fields.Binary(string='ESI Excel File (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    record_count = fields.Integer(string='Total Employees Covered', readonly=True)
    total_esi_wages = fields.Float(string='Total ESI Wages', readonly=True)
    total_ee_esic = fields.Float(string='Total Employee Contribution', readonly=True)
    total_er_esic = fields.Float(string='Total Employer Contribution', readonly=True)

    @api.depends('month', 'year', 'report_type')
    def _compute_name(self):
        month_dict = dict(self._fields['month'].selection)
        report_dict = dict(self._fields['report_type'].selection)
        for rec in self:
            m_label = month_dict.get(rec.month, '')
            r_label = report_dict.get(rec.report_type, 'ESI Report')
            rec.name = f"{r_label} / {m_label}-{rec.year}"

    def _get_date_range(self):
        self.ensure_one()
        year = int(self.year)
        month = int(self.month)
        last_day = calendar.monthrange(year, month)[1]
        date_from = date(year, month, 1)
        date_to = date(year, month, last_day)
        return date_from, date_to

    def _get_month_label(self):
        self.ensure_one()
        month_dict = dict(self._fields['month'].selection)
        return f"{month_dict.get(self.month, '')} {self.year}"

    def _get_esic_data(self):
        self.ensure_one()
        date_from, date_to = self._get_date_range()

        state_sel = getattr(self, 'payslip_state', 'all')
        if state_sel == 'done':
            states = ['done']
        elif state_sel == 'paid':
            states = ['paid']
        elif state_sel == 'confirmed':
            states = ['done', 'paid']
        else:
            states = ['draft', 'verify', 'done', 'paid']

        domain = [
            ('state', 'in', states),
            ('company_id', '=', self.company_id.id),
            ('date_from', '>=', date_from),
            ('date_to', '<=', date_to),
            ('employee_id.hds_in_esic_applicable', '=', True),
        ]
        all_slips = self.env['hr.payslip'].search(domain, order='date_to desc, id desc')

        priority = {'paid': 4, 'done': 3, 'verify': 2, 'draft': 1}
        best_slip_by_emp = {}
        for slip in all_slips:
            emp_id = slip.employee_id.id
            if emp_id not in best_slip_by_emp:
                best_slip_by_emp[emp_id] = slip
            else:
                curr_prio = priority.get(slip.state, 0)
                best_prio = priority.get(best_slip_by_emp[emp_id].state, 0)
                if curr_prio > best_prio:
                    best_slip_by_emp[emp_id] = slip

        payslips = self.env['hr.payslip'].browse([s.id for s in best_slip_by_emp.values()])

        if not payslips:
            raise UserError(_("No payslips found for ESIC-applicable employees in the selected period (%s).") % self._get_month_label())

        # Pre-export statutory ESIC compliance validation
        validator = ESICValidator(self.env)
        from odoo.addons.hudson_in_payroll.services.esic.employee_calculator import ESICEmployeeCalculator
        calc = ESICEmployeeCalculator(self.env)

        # Pre-export statutory ESIC compliance validation for active covered employees
        from odoo.addons.hudson_in_payroll.services.compliance.statutory_compliance_service import StatutoryComplianceValidationService
        compliance_service = StatutoryComplianceValidationService(self.env)
        covered_employees = payslips.filtered(
            lambda p: p.employee_id.hds_in_esic_applicable and (
                p.line_ids.filtered(lambda l: l.code in ('ESIC_EE', 'ESI_EE', 'EMPLOYEE_ESIC', 'ESIC_DED', 'ESI', 'ESIC'))
                or validator.is_esic_eligible(p)
            )
        ).mapped('employee_id')
        if covered_employees:
            compliance_service.validate_scope_compliance(
                employees=covered_employees,
                statutory_type='esic',
                report_title='ESIC Report'
            )

        esic_rows = []
        tot_wages = 0.0
        tot_ee = 0.0
        tot_er = 0.0

        for payslip in payslips:
            emp = payslip.employee_id
            lines = payslip.line_ids

            # Statutory Registration Number: ESIC Number from employee personal details
            ip_number = (
                getattr(emp, 'hds_in_esic_ip_number', False)
                or getattr(emp, 'hds_in_esic_number', False)
                or getattr(emp, 'esic_number', False)
                or '-'
            )
            emp_name = emp.name or ''
            clean_ip_name = ''.join(c for c in emp_name if c.isalpha() or c.isspace()).strip()
            if not clean_ip_name:
                clean_ip_name = emp_name

            # Employee Number: Employee Code from employee module
            emp_number = (
                getattr(emp, 'employee_code', False)
                or getattr(emp, 'registration_number', False)
                or getattr(emp, 'barcode', False)
                or getattr(emp, 'identification_id', False)
                or '-'
            )

            # Dynamically determine exact payable / worked days using pure statutory engine
            if getattr(payslip, 'hds_in_esic_paid_days', False):
                paid_days_val = payslip.hds_in_esic_paid_days
            else:
                paid_days_val = calc.get_paid_days(payslip)
            worked_days = int(math.ceil(paid_days_val)) if paid_days_val > 0 else 0

            # ESI Contributable Wage
            wage_lines = lines.filtered(lambda l: l.code in ('ESIC_WAGE', 'ESI_WAGE', 'ESIC_CONTRIBUTABLE_WAGE'))
            if wage_lines:
                esi_wage = abs(wage_lines[0].total)
            else:
                gross_lines = lines.filtered(lambda l: l.code == 'GROSS')
                esi_wage = abs(gross_lines[0].total) if gross_lines else (payslip.contract_id.wage if payslip.contract_id else 0.0)

            # Dynamic statutory ceiling and date-effective contribution rates
            eval_date = payslip.date_to or date_to
            applicable_ceiling = validator.get_applicable_ceiling(payslip)
            ee_rate = self.env['hr.rule.parameter'].get_parameter('hds_in_esic_employee_rate', date=eval_date, as_decimal=True)
            er_rate = self.env['hr.rule.parameter'].get_parameter('hds_in_esic_employer_rate', date=eval_date, as_decimal=True)
            is_covered = emp.hds_in_esic_applicable and (esi_wage <= applicable_ceiling or validator.is_esic_eligible(payslip, gross_wage=esi_wage))

            # Employee ESI Deduction
            ee_lines = lines.filtered(lambda l: l.code in ('ESIC_EE', 'ESI_EE', 'EMPLOYEE_ESIC', 'ESIC_DED', 'ESI', 'ESIC'))
            if ee_lines:
                ee_contrib = abs(sum(ee_lines.mapped('total')))
            else:
                ee_contrib = round(esi_wage * ee_rate, 2) if is_covered else 0.0

            # Employer ESI Contribution
            er_lines = lines.filtered(lambda l: l.code in ('ESIC_ER', 'ESI_ER', 'EMPLOYER_ESIC'))
            if er_lines:
                er_contrib = abs(sum(er_lines.mapped('total')))
            else:
                er_contrib = round(esi_wage * er_rate, 2) if is_covered else 0.0

            tot_contrib = round(ee_contrib + er_contrib, 2)

            # Determine Reason Code for zero working days and Last Working Day
            reason_code = 0
            last_working_day = ''

            if worked_days == 0:
                dep_reason = getattr(emp, 'departure_reason_id', None)
                reason_name = (dep_reason.name or '').lower() if dep_reason else ''
                dep_date = getattr(emp, 'departure_date', False) or getattr(emp, 'resign_date', False)

                if 'retire' in reason_name:
                    reason_code = 3
                elif any(k in reason_name for k in ('death', 'deceased', 'expire')):
                    reason_code = 5
                elif 'retrench' in reason_name:
                    reason_code = 10
                elif any(k in reason_name for k in ('resigned', 'left', 'departure')):
                    reason_code = 2
                elif 'leave' in reason_name:
                    reason_code = 1
                elif dep_date and dep_date <= date_to:
                    reason_code = 2
                else:
                    reason_code = 0

                if reason_code in (2, 3, 4, 5, 10):
                    resolved_exit = dep_date or (payslip.contract_id.date_end if payslip.contract_id else False)
                    if resolved_exit:
                        if isinstance(resolved_exit, str):
                            resolved_exit = fields.Date.from_string(resolved_exit)
                        last_working_day = resolved_exit.strftime('%d/%m/%Y')

            esic_rows.append({
                'ip_number': ip_number,
                'employee_name': emp_name,
                'ip_name': clean_ip_name,
                'employee_number': emp_number,
                'number_of_days': worked_days,
                'total_monthly_wages': round(esi_wage, 2),
                'employee_contribution': round(ee_contrib, 2),
                'employer_contribution': round(er_contrib, 2),
                'total_contribution': tot_contrib,
                'reason_code': reason_code,
                'last_working_day': last_working_day,
            })

            tot_wages += esi_wage
            tot_ee += ee_contrib
            tot_er += er_contrib

        # Establishment ID: ESIC IP Number from company settings
        est_code = (
            getattr(self.company_id, 'hds_in_esic_employer_code', False)
            or getattr(self.company_id, 'hds_in_esic_registration_no', False)
            or getattr(self.company_id, 'vat', False)
            or getattr(self.company_id, 'company_registry', False)
            or '-'
        )
        return {
            'esic_rows': esic_rows,
            'tot_wages': round(tot_wages, 2),
            'tot_ee': round(tot_ee, 2),
            'tot_er': round(tot_er, 2),
            'total_payable': round(tot_ee + tot_er, 2),
            'record_count': len(esic_rows),
            'est_name': self.company_id.name or '',
            'est_code': est_code,
        }

    def action_print_pdf(self):
        self.ensure_one()
        data = self._get_esic_data()
        if not data.get('esic_rows'):
            raise UserError(_("No employee records found for the selected period (%s).") % self._get_month_label())
        return self.env.ref('hudson_in_payroll.action_report_esic').report_action(self)

    def action_generate_xlsx(self):
        self.ensure_one()
        data = self._get_esic_data()
        esic_rows = data['esic_rows']
        tot_wages = data['tot_wages']
        tot_ee = data['tot_ee']
        tot_er = data['tot_er']

        month_label = self._get_month_label().replace(' ', '_')
        if self.report_type == 'esic_report':
            xlsx_filename = f"ESIC_Monthly_Statement_{month_label}.xlsx"
        else:
            xlsx_filename = f"ESIC_Summary_{month_label}.xlsx"

        output = io.BytesIO()
        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            title_fmt = workbook.add_format({
                'bold': True,
                'align': 'center',
                'valign': 'vcenter',
                'font_size': 13,
            })
            meta_bold_fmt = workbook.add_format({
                'bold': True,
                'font_size': 10,
                'valign': 'vcenter',
            })
            meta_val_fmt = workbook.add_format({
                'font_size': 10,
                'valign': 'vcenter',
            })
            header_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#D9D9D9',
                'font_color': '#000000',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'font_size': 9,
                'text_wrap': True,
            })
            text_left_fmt = workbook.add_format({
                'border': 1,
                'align': 'left',
                'valign': 'vcenter',
                'font_size': 9,
            })
            text_center_fmt = workbook.add_format({
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'font_size': 9,
            })
            num_center_fmt = workbook.add_format({
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'font_size': 9,
            })
            wage_fmt = workbook.add_format({
                'num_format': '0.00',
                'border': 1,
                'align': 'right',
                'valign': 'vcenter',
                'font_size': 9,
            })
            reason_code_fmt = workbook.add_format({
                'num_format': '0',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'font_size': 9,
            })
            num_fmt = workbook.add_format({
                'num_format': '#,##0.00',
                'border': 1,
                'align': 'right',
                'valign': 'vcenter',
                'font_size': 9,
            })

            if self.report_type == 'esic_report':
                # ═════════════════════════════════════════════════════════════
                # Sheet 1: Employees' State Insurance Corp (Portal Upload Format)
                # ═════════════════════════════════════════════════════════════
                sheet = workbook.add_worksheet("Employees' State Insurance Corp")
                sheet.set_column(0, 0, 24)  # IP Number (10 Digits)
                sheet.set_column(1, 1, 32)  # IP Name (Only alphabets and space)
                sheet.set_column(2, 2, 24)  # No of Days for which wages paid/payable during the month
                sheet.set_column(3, 3, 20)  # Total Monthly Wages
                sheet.set_column(4, 4, 32)  # Reason Code for Zero workings days
                sheet.set_column(5, 5, 26)  # Last Working Day

                # Row 1 (Index 0): Title banner
                sheet.set_row(0, 26)
                sheet.merge_range(0, 0, 0, 5, 'ESIC - Monthly Statement', title_fmt)

                # Row 2 (Index 1): Establishment Name
                sheet.set_row(1, 20)
                sheet.write(1, 0, 'Establishment Name', meta_bold_fmt)
                sheet.write(1, 1, data.get('est_name') or self.company_id.name or '', meta_val_fmt)

                # Row 3 (Index 2): Establishment ID
                sheet.set_row(2, 20)
                sheet.write(2, 0, 'Establishment ID', meta_bold_fmt)
                sheet.write_string(2, 1, str(data.get('est_code') or '-'), meta_val_fmt)

                # Row 4 (Index 3): Blank separator row
                sheet.set_row(3, 16)

                # Row 5 (Index 4): Table Headers
                sheet.set_row(4, 36)
                headers = [
                    'IP Number (10 Digits)',
                    'IP Name (Only alphabets and space)',
                    'No of Days for which wages paid/payable during the month',
                    'Total Monthly Wages',
                    'Reason Code for Zero workings days(Numeric Only: provide 0 for all other reasons)',
                    'Last Working Day (Format DD/MM/YYYY or DD-MM-YYYY)',
                ]
                for col_idx, text in enumerate(headers):
                    sheet.write(4, col_idx, text, header_fmt)

                # Rows 6+ (Index 5+): Employee data rows
                for row_idx, r in enumerate(esic_rows, start=5):
                    sheet.set_row(row_idx, 20)
                    sheet.write_string(row_idx, 0, str(r['ip_number'] or ''), text_left_fmt)
                    sheet.write(row_idx, 1, str(r.get('ip_name') or r['employee_name'] or ''), text_left_fmt)
                    sheet.write(row_idx, 2, r['number_of_days'], num_center_fmt)
                    sheet.write(row_idx, 3, r['total_monthly_wages'], wage_fmt)
                    sheet.write(row_idx, 4, int(r.get('reason_code', 0) or 0), reason_code_fmt)
                    sheet.write_string(row_idx, 5, str(r.get('last_working_day') or ''), text_center_fmt)

                # ═════════════════════════════════════════════════════════════
                # Sheet 2: Reason & Upload Instructions
                # ═════════════════════════════════════════════════════════════
                reason_sheet = workbook.add_worksheet('Instructions & Reason Codes')
                reason_sheet.set_column(0, 0, 36)
                reason_sheet.set_column(1, 1, 10)
                reason_sheet.set_column(2, 2, 95)

                reason_header_fmt = workbook.add_format({
                    'bold': True,
                    'border': 1,
                    'align': 'center',
                    'valign': 'vcenter',
                    'font_size': 10,
                })
                reason_text_fmt = workbook.add_format({
                    'border': 1,
                    'align': 'left',
                    'valign': 'vcenter',
                    'font_size': 9,
                })
                reason_code_fmt = workbook.add_format({
                    'border': 1,
                    'align': 'center',
                    'valign': 'vcenter',
                    'font_size': 9,
                })
                inst_title_fmt = workbook.add_format({
                    'bold': True,
                    'font_size': 11,
                    'valign': 'vcenter',
                })
                inst_text_fmt = workbook.add_format({
                    'font_size': 9,
                    'valign': 'vcenter',
                })

                # Row 1 (Index 0): Headers
                reason_sheet.set_row(0, 20)
                reason_sheet.write(0, 0, 'Reason', reason_header_fmt)
                reason_sheet.write(0, 1, 'Code', reason_header_fmt)
                reason_sheet.write(0, 2, 'Note', reason_header_fmt)

                # Rows 2 to 15 (Index 1 to 14): Reason Code Table
                reason_table = [
                    ('Without Reason', 0, 'Leave last working day as blank'),
                    ('On Leave', 1, 'Leave last working day as blank'),
                    ('Left Service', 2, 'Please provide last working day (dd/mm/yyyy). IP will not appear from next wage period'),
                    ('Retired', 3, 'Please provide last working day (dd/mm/yyyy). IP will not appear from next wage period'),
                    ('Out of Coverage', 4, 'Please provide last working day (dd/mm/yyyy). IP will not appear from next contribution period. This option is valid only if Wage Period is April/October. In case any other month then IP will continue to appear in the list'),
                    ('Expired', 5, 'Please provide last working day (dd/mm/yyyy). IP will not appear from next wage period'),
                    ('Non Implemented area', 6, 'Please provide last working day (dd/mm/yyyy)'),
                    ('Compliance by Immediate Employer', 7, 'Leave last working day as blank'),
                    ('Suspension of work', 8, 'Leave last working day as blank'),
                    ('Strike/Lockout', 9, 'Leave last working day as blank'),
                    ('Retrenchment', 10, 'Please provide last working day (dd/mm/yyyy). IP will not appear from next wage period'),
                    ('No Work', 11, 'Leave last working day as blank'),
                    ('Doesnt Belong To This Employer', 12, 'Leave last working day as blank'),
                    ('Duplicate IP', 13, 'Leave last working day as blank'),
                ]

                for idx, (reason_desc, code_val, note_text) in enumerate(reason_table, start=1):
                    reason_sheet.set_row(idx, 18)
                    reason_sheet.write(idx, 0, reason_desc, reason_text_fmt)
                    reason_sheet.write(idx, 1, code_val, reason_code_fmt)
                    reason_sheet.write(idx, 2, note_text, reason_text_fmt)

                # Row 16 (Index 15): Blank row
                reason_sheet.set_row(15, 15)

                # Row 17 (Index 16): Section title
                reason_sheet.set_row(16, 22)
                reason_sheet.write(16, 0, 'Instructions to fill in the excel file:', inst_title_fmt)

                # Rows 18 to 32 (Index 17 to 31): Instructions 1 to 11
                instructions = [
                    "1. Enter the IP number, IP name, No. of Days, Total Monthly Wages, Reason for 0 wages(If Wages '0') & Last Working Day(only if employee has left service, Retired, Out of coverage, Expired, Non-Implementedarea or Retrenchment. For other reasons, last working day must be left BLANK)",
                    "2. Number of days must me a whole number. Fractions should be rounded up to next higher whole number/integer",
                    "3. Excel sheet upload will lead to successful transaction only when all the Employees' (who are currently mapped in the system) details are entered perfectly in the excel sheet",
                    "4. Reasons are to be assigned numeric code and date has to be provided as mentioned in the table above",
                    "5. Once 0 wages given and last working day is mentioned as in reason codes (2,3,4,5,10) IP will be removed from the employer's record. Subsequent months will not have this IP listed under the employer.Last working day should be mentioned only if 'Number of days wages paid/payable' is '0'",
                    "6. In case IP has worked for part of the month(i.e. atleast 1 day wage is paid/payable) and left in between of the month, then last working day shouldn't be mentioned",
                    "7. Calculations - IP Contribution and Employer contribution calculation will be automatically done by the system",
                    "8. Date column format is dd/mm/yyyy or dd-mm-yyyy. Pad single digit dates with 0. Eg:- 2/5/2010 or 2-May-2010 is NOT acceptable. Correct format is 02/05/2010 or 02-05-2010",
                    "9. Excel file should be saved in .xls format (Excel 97-2003)",
                    "10. Note that all the column including date column should be in 'Text' format",
                    "10a. To convert all columns to text",
                    "a. Select column A; Click Data in Menu Bar on top; Select Text to Columns ; Click Next (keep default selection of Delimited); Click Next (keep default selection of Tab); Select TEXT; Click FINISH.",
                    "b. Repeat the above step for each of the 6 columns. (Columns A - F )",
                    "10b. Another method that can be used to text conversion is - copy the column with data and paste it in NOTEPAD.Select the column (in excel) and convert to text. Copy the data back from notepad to excel",
                    "11. If problem continues while upload, download a fresh template by clicking 'Sample MC Excel Template'. Then copy the data area from Step 8a.a - eg: copy Cell A2 to F8 (if there is data in 8 rows); Paste it in cell A2 in the fresh template. Upload it",
                ]

                for idx, inst_line in enumerate(instructions, start=17):
                    reason_sheet.set_row(idx, 18)
                    reason_sheet.write(idx, 0, inst_line, inst_text_fmt)

            else:
                # ═════════════════════════════════════════════════════════════
                # ESI Summary Report (Format unchanged)
                # ═════════════════════════════════════════════════════════════
                sheet = workbook.add_worksheet('ESIC - Summary')
                sheet.set_column(0, 0, 26)  # EMPLOYEE NAME
                sheet.set_column(1, 1, 20)  # EMPLOYEE NUMBER
                sheet.set_column(2, 2, 34)  # STATUTORY REGISTRATION NUMBER
                sheet.set_column(3, 3, 16)  # ESI WAGES
                sheet.set_column(4, 4, 24)  # EMPLOYEE CONTRIBUTION
                sheet.set_column(5, 5, 24)  # EMPLOYER CONTRIBUTION
                sheet.set_column(6, 6, 20)  # TOTAL REMITTED

                # Row 1 (Index 0): Title banner
                sheet.set_row(0, 24)
                sheet.merge_range(0, 0, 0, 6, 'ESIC - Summary', title_fmt)

                # Row 2 (Index 1): Establishment Name
                sheet.set_row(1, 20)
                sheet.write(1, 0, 'Establishment Name', meta_bold_fmt)
                sheet.write(1, 1, data.get('est_name') or self.company_id.name or '', meta_val_fmt)

                # Row 3 (Index 2): Establishment ID
                sheet.set_row(2, 20)
                sheet.write(2, 0, 'Establishment ID', meta_bold_fmt)
                sheet.write_string(2, 1, str(data.get('est_code') or '-'), meta_val_fmt)

                # Row 4 (Index 3): Blank separator row
                sheet.set_row(3, 15)

                # Row 5 (Index 4): Table Headers
                sheet.set_row(4, 22)
                headers = [
                    'EMPLOYEE NAME',
                    'EMPLOYEE NUMBER',
                    'STATUTORY REGISTRATION NUMBER',
                    'ESI WAGES',
                    'EMPLOYEE CONTRIBUTION',
                    'EMPLOYER CONTRIBUTION',
                    'TOTAL REMITTED',
                ]
                for col_idx, text in enumerate(headers):
                    sheet.write(4, col_idx, text, header_fmt)

                # Rows 6+ (Index 5+): Data rows
                for row_idx, r in enumerate(esic_rows, start=5):
                    sheet.write(row_idx, 0, r['employee_name'], text_left_fmt)
                    sheet.write_string(row_idx, 1, str(r['employee_number'] or '-'), text_center_fmt)
                    sheet.write_string(row_idx, 2, str(r['ip_number'] or '-'), text_left_fmt)
                    sheet.write(row_idx, 3, r['total_monthly_wages'], num_fmt)
                    sheet.write(row_idx, 4, r['employee_contribution'], num_fmt)
                    sheet.write(row_idx, 5, r['employer_contribution'], num_fmt)
                    sheet.write(row_idx, 6, r['total_contribution'], num_fmt)

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
            'record_count': len(esic_rows),
            'total_esi_wages': tot_wages,
            'total_ee_esic': tot_ee,
            'total_er_esic': tot_er,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=xlsx_file&filename_field=xlsx_filename&download=true',
            'target': 'self',
        }

    def web_save(self, vals, specification: dict, next_id=None):
        res = super().web_save(vals, specification, next_id=next_id)
        for rec in self:
            try:
                data = rec._get_esic_data()
                rec.write({
                    'record_count': data.get('record_count', 0),
                    'total_esi_wages': data.get('tot_wages', 0.0),
                    'total_ee_esic': data.get('tot_ee', 0.0),
                    'total_er_esic': data.get('tot_er', 0.0),
                })
            except Exception:
                pass
        return super().web_save({}, specification, next_id=next_id)
