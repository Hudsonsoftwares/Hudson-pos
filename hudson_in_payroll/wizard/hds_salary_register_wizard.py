# -*- coding: utf-8 -*-
import base64
import calendar
import io
from datetime import date
from odoo import api, fields, models, _
from odoo.exceptions import UserError

try:
    import xlsxwriter
    from xlsxwriter.utility import xl_col_to_name
except ImportError:
    xlsxwriter = None

    def xl_col_to_name(col_idx):
        result = ''
        col_idx += 1
        while col_idx > 0:
            col_idx, remainder = divmod(col_idx - 1, 26)
            result = chr(65 + remainder) + result
        return result


class HdsSalaryRegisterWizard(models.TransientModel):
    _name = 'hds.salary.register.wizard'
    _description = 'Salary Register'

    date_from = fields.Date(
        string='Start Date',
        default=lambda self: date(fields.Date.today().year, 1, 1),
        required=True
    )
    date_to = fields.Date(
        string='End Date',
        default=lambda self: date(
            fields.Date.today().year,
            fields.Date.today().month,
            calendar.monthrange(fields.Date.today().year, fields.Date.today().month)[1]
        ),
        required=True
    )

    struct_id = fields.Many2one(
        'hr.payroll.structure',
        string='Pay Structure',
        help='Optional pay structure filter.'
    )

    status_paid = fields.Boolean(string='Paid', default=True)
    status_done = fields.Boolean(string='Done', default=True)

    def _default_employee_ids(self):
        today = fields.Date.today()
        d_from = date(today.year, 1, 1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        d_to = date(today.year, today.month, last_day)
        comp = self.env.company
        domain = [
            ('company_id', '=', comp.id),
            ('date_from', '>=', d_from),
            ('date_to', '<=', d_to),
            ('state', 'in', ('paid', 'done')),
        ]
        payslips = self.env['hr.payslip'].search(domain, order='employee_id asc')
        return payslips.mapped('employee_id')

    employee_ids = fields.Many2many(
        'hr.employee',
        'hds_salary_register_wizard_employee_rel',
        'wizard_id',
        'employee_id',
        string='Employees',
        default=_default_employee_ids,
        help='Optional employee filter. Automatically fetched based on Payslip Status and Date Range.'
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    xlsx_file = fields.Binary(string='Salary Register Excel File (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    @api.onchange('date_from', 'date_to', 'status_paid', 'status_done', 'struct_id', 'company_id')
    def _onchange_payslip_criteria(self):
        if self.date_from and self.date_to and self.date_to < self.date_from:
            last_day = calendar.monthrange(self.date_from.year, self.date_from.month)[1]
            self.date_to = self.date_from.replace(day=last_day)

        if not self.date_from or not self.date_to:
            self.employee_ids = [(5, 0, 0)]
            return

        states = []
        if self.status_paid:
            states.append('paid')
        if self.status_done:
            states.append('done')

        if not states:
            self.employee_ids = [(5, 0, 0)]
            return

        domain = [
            ('company_id', '=', self.company_id.id if self.company_id else self.env.company.id),
            ('date_from', '>=', self.date_from),
            ('date_to', '<=', self.date_to),
            ('state', 'in', states),
        ]
        if self.struct_id:
            domain.append(('struct_id', '=', self.struct_id.id))

        payslips = self.env['hr.payslip'].search(domain, order='employee_id asc')
        matching_employees = payslips.mapped('employee_id')
        self.employee_ids = [(6, 0, matching_employees.ids)]

    def _get_target_payslips(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date_from', '>=', self.date_from),
            ('date_to', '<=', self.date_to),
        ]

        states = []
        if self.status_paid:
            states.append('paid')
        if self.status_done:
            states.append('done')
        if not states:
            raise UserError(_("Please select at least one Payslip Status (Paid or Done)."))

        domain.append(('state', 'in', states))

        if self.struct_id:
            domain.append(('struct_id', '=', self.struct_id.id))

        if self.employee_ids:
            domain.append(('employee_id', 'in', self.employee_ids.ids))

        payslips = self.env['hr.payslip'].search(domain, order='employee_id asc, date_from asc, id asc')
        if not payslips:
            raise UserError(_("No computed payslips found for the selected period and criteria."))
        return payslips

    def action_export_xlsx(self):
        self.ensure_one()
        payslips = self._get_target_payslips()

        # Group payslips by employee
        emp_slips_map = {}
        for slip in payslips:
            emp = slip.employee_id
            if not emp:
                continue
            if emp not in emp_slips_map:
                emp_slips_map[emp] = []
            emp_slips_map[emp].append(slip)

        data_rows = []
        for emp, slips in emp_slips_map.items():
            emp_code = (
                getattr(emp, 'registration_number', False) or
                getattr(emp, 'barcode', False) or
                getattr(emp, 'emp_id', False) or
                getattr(emp, 'identification_id', False) or ''
            )
            emp_name = emp.name or ''

            row_data = {
                'emp_code': emp_code,
                'emp_name': emp_name,
                'basic_salary': 0.0,
                'dearness_allowance': 0.0,
                'house_rent_allowance': 0.0,
                'standard_allowance': 0.0,
                'performance_bonus': 0.0,
                'leave_travel_allowance': 0.0,
                'fixed_allowance': 0.0,
                'overtime_pay': 0.0,
                'other_allowances': 0.0,
                'phone_subscription': 0.0,
                'internet_subscription': 0.0,
                'meal_vouchers': 0.0,
                'company_transport': 0.0,
                'taxable_salary': 0.0,
                'professional_tax': 0.0,
                'pf_employee': 0.0,
                'pf_employer': 0.0,
                'gratuity': 0.0,
                'medical_insurance': 0.0,
                'esic_employee': 0.0,
                'esic_employer': 0.0,
                'lwf_employee': 0.0,
                'lwf_employer': 0.0,
                'tds': 0.0,
                'attachment_of_salary': 0.0,
                'assignment_of_salary': 0.0,
                'child_support': 0.0,
                'expenses_reimbursement': 0.0,
                'deduction': 0.0,
                'other_deductions': 0.0,
                'reimbursement': 0.0,
                'net_salary': 0.0,
            }

            for slip in slips:
                lines = slip.line_ids
                slip_gross = 0.0
                has_gross_line = False
                slip_net = 0.0
                has_net_line = False

                has_er_epf_total = False
                er_epf_total_val = 0.0
                er_epf_breakdown_val = 0.0

                for line in lines:
                    code = (line.code or '').upper()
                    name = line.name or ''
                    cat = line.category_id
                    cat_code = (cat.code or '').upper() if cat else ''
                    parent_cat_code = (cat.parent_id.code or '').upper() if (cat and cat.parent_id) else ''
                    amt = float(line.total or 0.0)
                    abs_amt = abs(amt)

                    is_alw_cat = cat_code in ('ALW', 'ALLOWANCE') or parent_cat_code in ('ALW', 'ALLOWANCE')
                    is_ded_cat = cat_code in ('DED', 'DEDUCTION') or parent_cat_code in ('DED', 'DEDUCTION')

                    # Taxable / Gross line
                    if code in ('GROSS', 'TAXABLE', 'TAXABLE_SALARY') or cat_code == 'GROSS' or name in ('Taxable Salary', 'Gross Salary', 'Gross'):
                        has_gross_line = True
                        slip_gross += abs_amt
                        continue

                    # Net Salary line
                    if code in ('NET', 'NET_SALARY') or cat_code == 'NET' or name == 'Net Salary':
                        has_net_line = True
                        slip_net += float(amt)
                        continue

                    # Skip calculation base lines (PF_WAGE, ESIC_WAGE, etc.) - they are wage bases, NOT deductions or allowances
                    if cat_code in ('PF_CALC', 'ESIC_CALC', 'CALC') or code in ('PF_WAGE', 'ESIC_WAGE', 'BASIC_PF', 'PF_BASE', 'ESI_WAGE', 'ESIC_BASE', 'PT_WAGE', 'LWF_WAGE') or ('WAGE' in code and cat_code not in ('BASIC', 'ALW')):
                        continue

                    # 1. Basic Salary
                    if code == 'BASIC' or cat_code == 'BASIC' or name == 'Basic Salary':
                        row_data['basic_salary'] += abs_amt

                    # 2. Dearness Allowance (DA)
                    elif code in ('DA', 'DEARNESS', 'DEARNESS_ALLOWANCE') or 'Dearness' in name:
                        row_data['dearness_allowance'] += abs_amt

                    # 3. House Rent Allowance
                    elif code in ('HRA', 'HOUSE_RENT_ALLOWANCE') or 'HRA' in code or 'House Rent' in name:
                        row_data['house_rent_allowance'] += abs_amt

                    # 4. Standard Allowance
                    elif code in ('STD_ALW', 'STANDARD_ALLOWANCE', 'SA') or 'Standard Allowance' in name:
                        row_data['standard_allowance'] += abs_amt

                    # 5. Performance Bonus
                    elif code in ('PERF_BONUS', 'PERFORMANCE_BONUS', 'RETENTION_BONUS', 'BONUS') or 'Performance Bonus' in name or 'Retention Bonus' in name:
                        row_data['performance_bonus'] += abs_amt

                    # 6. Leave Travel Allowance
                    elif code in ('LTA', 'LEAVE_TRAVEL_ALLOWANCE') or 'Leave Travel' in name or code == 'LTA':
                        row_data['leave_travel_allowance'] += abs_amt

                    # 7. Fixed Allowance
                    elif code in ('FIXED', 'FIXED_ALW', 'FIXED_ALLOWANCE') or 'Fixed Allowance' in name:
                        row_data['fixed_allowance'] += abs_amt

                    # 8. Overtime Pay
                    elif code in ('OT', 'OVERTIME', 'OVERTIME_PAY', 'OTALL') or 'Overtime' in name:
                        row_data['overtime_pay'] += abs_amt

                    # 9. Phone Subscription
                    elif code in ('BENEFIT_PHONE', 'PHONE', 'PHONE_ALLOWANCE') or 'Phone' in name:
                        row_data['phone_subscription'] += abs_amt

                    # 10. Internet Subscription
                    elif code in ('BENEFIT_INTERNET', 'INTERNET', 'BROADBAND') or 'Internet' in name:
                        row_data['internet_subscription'] += abs_amt

                    # 11. Meal Vouchers
                    elif code in ('BENEFIT_MEAL', 'MEAL', 'MEAL_VOUCHERS', 'MEAL_VOUCHER') or 'Meal' in name:
                        row_data['meal_vouchers'] += abs_amt

                    # 12. Company Transport
                    elif code in ('BENEFIT_TRANSPORT', 'TRANSPORT', 'COMPANY_TRANSPORT') or 'Company Transport' in name:
                        row_data['company_transport'] += abs_amt

                    # 13. Professional Tax
                    elif code in ('PT', 'PROF_TAX', 'PT_DED', 'HDS_IN_RULE_PT') or 'Professional Tax' in name:
                        row_data['professional_tax'] += abs_amt

                    # 14. Gratuity
                    elif code in ('GRATUITY', 'HDS_IN_RULE_GRATUITY', 'GRAT') or 'Gratuity' in name:
                        row_data['gratuity'] += abs_amt

                    # 15. Medical Insurance
                    elif code in ('MED_INS', 'MEDICAL_INSURANCE', 'MEDICLAIM', 'INSURANCE') or 'Medical Insurance' in name:
                        row_data['medical_insurance'] += abs_amt

                    # 16. Attachment of Salary
                    elif code in ('ATTACH_SALARY', 'ATTACHMENT') or 'Attachment of Salary' in name:
                        row_data['attachment_of_salary'] += abs_amt

                    # 17. Assignment of Salary
                    elif code in ('ASSIG_SALARY', 'ASSIG_SALARY_PRIOR', 'ASSIGNMENT') or 'Assignment of Salary' in name:
                        row_data['assignment_of_salary'] += abs_amt

                    # 18. Child Support
                    elif code in ('CHILD_SUPPORT', 'CHILDSUPPORT') or 'Child Support' in name:
                        row_data['child_support'] += abs_amt

                    # 19. Expenses Reimbursement
                    elif code in ('EXPENSES', 'EXP_REIMB', 'EXPENSE_REIMBURSEMENT') or 'Expenses Reimbursement' in name or 'Expense Reimbursement' in name:
                        row_data['expenses_reimbursement'] += abs_amt

                    # 20. General Reimbursement
                    elif (code in ('REIMBURSEMENT', 'REIMB') or name == 'Reimbursement') and 'Expense' not in name:
                        row_data['reimbursement'] += abs_amt

                    # 21. Specific Deduction
                    elif (code in ('DEDUCTION', 'OTHER_DED') or name == 'Deduction') and is_ded_cat:
                        row_data['deduction'] += abs_amt

                    # 22. ESIC Employee vs Employer
                    elif any(k in name for k in ('State Insurance', 'ESIC', 'ESI')) or code in ('ESIC', 'ESI', 'ESIC_EE', 'EE_ESI', 'ESI_EE', 'ESIC_ER', 'ESI_ER', 'ER_ESI'):
                        if any(e in name for e in ('Employer', 'ER')) or code in ('ESIC_ER', 'ESI_ER', 'ER_ESI') or 'ER' in code:
                            row_data['esic_employer'] += abs_amt
                        elif 'Employer' not in name and 'WAGE' not in code and 'CALC' not in cat_code:
                            row_data['esic_employee'] += abs_amt

                    # 23. LWF Employee vs Employer
                    elif any(k in name for k in ('Labour Welfare', 'LWF')) or code in ('LWF', 'LWF_EE', 'EE_LWF', 'LWF_DED', 'LWF_ER', 'ER_LWF'):
                        if any(e in name for e in ('Employer', 'ER')) or code in ('LWF_ER', 'ER_LWF') or 'ER' in code:
                            row_data['lwf_employer'] += abs_amt
                        else:
                            row_data['lwf_employee'] += abs_amt

                    # 24. TDS
                    elif code in ('TDS', 'HDS_IN_TDS', 'INCOME_TAX', 'IT', 'HDS_IN_RULE_TDS') or 'Tax Deducted at Source' in name or cat_code == 'TDS':
                        row_data['tds'] += abs_amt

                    # 25. Provident Fund Employee vs Employer
                    elif any(k in name for k in ('Provident', 'EPF', 'PF')) or code in ('PF', 'EPF', 'EE_PF', 'PF_EE', 'EMPLOYER_EPF', 'ER_EPF', 'PF_ER', 'ER_PF', 'EMPR_PF', 'EPS', 'EPF_SHARE', 'EDLI', 'EPF_ADMIN', 'EDLI_ADMIN'):
                        if code in ('EMPLOYER_EPF', 'ER_EPF', 'PF_ER', 'ER_PF', 'EMPR_PF') or ('Provident' in name and 'Employer' in name):
                            has_er_epf_total = True
                            er_epf_total_val += abs_amt
                        elif code in ('EPS', 'EPF_SHARE', 'EDLI', 'EPF_ADMIN', 'EDLI_ADMIN'):
                            er_epf_breakdown_val += abs_amt
                        elif 'Employer' not in name and 'WAGE' not in code and 'CALC' not in cat_code:
                            row_data['pf_employee'] += abs_amt

                    # 26. Other Allowances Catch-All: Any allowance not specifically mapped above
                    elif is_alw_cat or code.startswith('ALW_'):
                        row_data['other_allowances'] += abs_amt

                    # 27. Other Deductions Catch-All: Any deduction not specifically mapped above
                    elif is_ded_cat or code.startswith('DED_'):
                        if not (any(e in name for e in ('Employer', 'ER')) or 'ER_' in code or '_ER' in code or cat_code == 'COMP'):
                            row_data['other_deductions'] += abs_amt

                # Finalize Employer EPF for this slip
                if has_er_epf_total and er_epf_total_val > 0:
                    row_data['pf_employer'] += er_epf_total_val
                elif er_epf_breakdown_val > 0:
                    row_data['pf_employer'] += er_epf_breakdown_val

                # Finalize Taxable Salary (Gross)
                if has_gross_line:
                    row_data['taxable_salary'] += slip_gross
                else:
                    g = float(getattr(slip, 'gross_amount', None) or getattr(slip, 'gross_wage', 0.0) or 0.0)
                    row_data['taxable_salary'] += g

                # Finalize Net Salary
                if has_net_line:
                    row_data['net_salary'] += slip_net
                else:
                    n = float(getattr(slip, 'net_amount', None) or getattr(slip, 'net_wage', 0.0) or 0.0)
                    row_data['net_salary'] += n

                # Contract benefit medical insurance fallback if not in lines
                if row_data['medical_insurance'] == 0.0 and getattr(slip, 'contract_id', False):
                    row_data['medical_insurance'] += float(getattr(slip.contract_id, 'benefit_medical_insurance_amount', 0.0) or 0.0)

            # Ensure Taxable Salary matches sum of individual allowance components if gross was 0 or uncomputed
            calc_gross = (
                row_data['basic_salary'] +
                row_data['dearness_allowance'] +
                row_data['house_rent_allowance'] +
                row_data['standard_allowance'] +
                row_data['performance_bonus'] +
                row_data['leave_travel_allowance'] +
                row_data['fixed_allowance'] +
                row_data['overtime_pay'] +
                row_data['other_allowances'] +
                row_data['phone_subscription'] +
                row_data['internet_subscription'] +
                row_data['meal_vouchers'] +
                row_data['company_transport']
            )
            if row_data['taxable_salary'] == 0.0 and calc_gross > 0.0:
                row_data['taxable_salary'] = calc_gross

            data_rows.append(row_data)

        # Setup xlsxwriter
        filename = f"Salary_Register_{self.date_from}_{self.date_to}.xlsx"
        output = io.BytesIO()

        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('Salary Register')

            # Formats matching Screenshot 2
            label_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#D9D9D9',
                'font_name': 'Calibri',
                'font_size': 11,
                'border': 1
            })
            top_val_fmt = workbook.add_format({
                'font_name': 'Calibri',
                'font_size': 11,
                'border': 1
            })
            header_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#D9D9D9',
                'font_name': 'Calibri',
                'font_size': 11,
                'border': 1,
                'align': 'left',
                'valign': 'vcenter'
            })
            data_text_fmt = workbook.add_format({
                'font_name': 'Calibri',
                'font_size': 11,
                'border': 1,
                'align': 'left'
            })
            data_num_fmt = workbook.add_format({
                'font_name': 'Calibri',
                'font_size': 11,
                'border': 1,
                'align': 'right',
                'num_format': '#,##0.00'
            })
            total_label_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#EAEAEA',
                'font_name': 'Calibri',
                'font_size': 11,
                'border': 1,
                'align': 'left'
            })
            total_num_fmt = workbook.add_format({
                'bold': True,
                'bg_color': '#EAEAEA',
                'font_name': 'Calibri',
                'font_size': 11,
                'border': 1,
                'align': 'right',
                'num_format': '#,##0.00'
            })

            # Top Section (Rows 1-4, indices 0-3)
            company_id_val = getattr(self.company_id, 'company_registry', False) or getattr(self.company_id, 'vat', False) or ''
            sheet.write(0, 0, "EMPLOYER ID", label_fmt)
            sheet.write(0, 1, company_id_val, top_val_fmt)

            sheet.write(1, 0, "EMPLOYER NAME", label_fmt)
            sheet.write(1, 1, (self.company_id.name or '').upper(), top_val_fmt)

            sheet.write(2, 0, "FROM DATE", label_fmt)
            sheet.write(2, 1, str(self.date_from), top_val_fmt)

            sheet.write(3, 0, "TO DATE", label_fmt)
            sheet.write(3, 1, str(self.date_to), top_val_fmt)

            # Row 6 (index 5): Headers
            headers = [
                "EMPLOYEE CODE",
                "EMPLOYEE NAME",
                "Basic Salary",
                "Dearness Allowance (DA)",
                "House Rent Allowance",
                "Standard Allowance",
                "Performance Bonus",
                "Leave Travel Allowance",
                "Fixed Allowance",
                "Overtime Pay",
                "Other Allowances",
                "Phone Subscription",
                "Internet Subscription",
                "Meal Vouchers",
                "Company Transport",
                "Taxable Salary",
                "Professional Tax",
                "Provident Fund - Employee",
                "Provident Fund - Employer",
                "Gratuity",
                "Medical Insurance",
                "Employee's State Insurance Corporation",
                "Employer's State Insurance Corporation",
                "Employee's Deduction Towards State Labour Welfare Fund",
                "Employer's Deduction Towards State Labour Welfare Fund",
                "Tax Deducted at Source (TDS)",
                "Attachment of Salary",
                "Assignment of Salary",
                "Child Support",
                "Expenses Reimbursement",
                "Deduction",
                "Other Deductions",
                "Reimbursement",
                "Net Salary"
            ]

            for col_idx, h in enumerate(headers):
                sheet.write(5, col_idx, h, header_fmt)

            # Column Widths
            col_widths = [
                18, 26, 16, 24, 22, 20, 20, 24, 18, 18,
                20, 20, 20, 16, 20, 16, 18, 26, 26, 14,
                18, 38, 38, 52, 52, 28, 22, 22, 16, 24,
                14, 18, 16, 14
            ]
            for col_idx, width in enumerate(col_widths):
                sheet.set_column(col_idx, col_idx, width)

            # Data Rows (Row 7 onwards, index 6)
            numeric_keys = [
                'basic_salary', 'dearness_allowance', 'house_rent_allowance',
                'standard_allowance', 'performance_bonus', 'leave_travel_allowance',
                'fixed_allowance', 'overtime_pay', 'other_allowances',
                'phone_subscription', 'internet_subscription', 'meal_vouchers',
                'company_transport', 'taxable_salary', 'professional_tax',
                'pf_employee', 'pf_employer', 'gratuity', 'medical_insurance',
                'esic_employee', 'esic_employer', 'lwf_employee', 'lwf_employer',
                'tds', 'attachment_of_salary', 'assignment_of_salary',
                'child_support', 'expenses_reimbursement', 'deduction',
                'other_deductions', 'reimbursement', 'net_salary'
            ]

            for row_offset, r in enumerate(data_rows):
                curr_row = 6 + row_offset
                sheet.write(curr_row, 0, r['emp_code'], data_text_fmt)
                sheet.write(curr_row, 1, r['emp_name'], data_text_fmt)

                for num_idx, k in enumerate(numeric_keys):
                    val = round(r[k], 2)
                    col_pos = 2 + num_idx
                    sheet.write_number(curr_row, col_pos, val, data_num_fmt)

            # Summary TOTAL row
            if data_rows:
                total_row_idx = 6 + len(data_rows)
                sheet.write(total_row_idx, 0, "TOTAL", total_label_fmt)
                sheet.write(total_row_idx, 1, f"{len(data_rows)} Employee(s)", total_label_fmt)

                first_data_row = 7  # 1-indexed for Excel formulas
                last_data_row = 6 + len(data_rows)  # 1-indexed for Excel formulas

                for num_idx, k in enumerate(numeric_keys):
                    col_pos = 2 + num_idx
                    col_letter = xl_col_to_name(col_pos)
                    formula = f"=SUM({col_letter}{first_data_row}:{col_letter}{last_data_row})"
                    sheet.write_formula(total_row_idx, col_pos, formula, total_num_fmt)

            workbook.close()
            output.seek(0)
            xlsx_content = output.read()
        else:
            xlsx_content = b"Excel export requires xlsxwriter library."

        try:
            from odoo.tools import BinaryBytes
            file_data = BinaryBytes(xlsx_content, filename=filename)
        except Exception:
            file_data = base64.b64encode(xlsx_content).decode('utf-8')

        self.write({
            'xlsx_file': file_data,
            'xlsx_filename': filename,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=xlsx_file&filename_field=xlsx_filename&download=true',
            'target': 'self',
        }
