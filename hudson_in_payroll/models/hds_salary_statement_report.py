# -*- coding: utf-8 -*-
import base64
import calendar
import io
import json
import logging
from datetime import date, datetime

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


MONTH_SELECTION = [
    ('1', 'January'), ('2', 'February'), ('3', 'March'), ('4', 'April'),
    ('5', 'May'), ('6', 'June'), ('7', 'July'), ('8', 'August'),
    ('9', 'September'), ('10', 'October'), ('11', 'November'), ('12', 'December')
]


def format_inr(amount):
    """Format numeric values according to the Indian numbering system with Rupee symbol.
    Example: 150000 -> ₹ 1,50,000.00, -1800 -> ₹ -1,800.00
    """
    if amount is None:
        amount = 0.0
    val = float(amount)
    is_neg = val < 0
    val = abs(val)

    int_str = str(int(val))
    dec_str = f"{val:.2f}".split('.')[1]

    if len(int_str) > 3:
        last3 = int_str[-3:]
        rest = int_str[:-3]
        groups = []
        while rest:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        formatted_int = ",".join(groups) + "," + last3
    else:
        formatted_int = int_str

    formatted_num = f"{formatted_int}.{dec_str}"
    if is_neg:
        return f"₹ -{formatted_num}"
    return f"₹ {formatted_num}"


def _compute_pt_yearly_amount(env, emp, monthly_amt, eval_date, company):
    """
    Compute yearly Professional Tax amount based on employee's state periodicity and statutory rules.
    Statutory ceiling under Article 276(2) Constitution of India is Rs 2,500/year.
    """
    amt = abs(float(monthly_amt or 0.0))
    if amt == 0.0:
        return 0.0

    emp_state = False
    periodicity = None
    try:
        from ..services.payroll.work_location_service import PayrollWorkLocationService
        from ..services.professional_tax.pt_period_config_service import PTPeriodScheduleService
        from ..services.professional_tax.professional_tax_slab_service import ProfessionalTaxSlabService

        loc_svc = PayrollWorkLocationService(env)
        sched_svc = PTPeriodScheduleService(env)
        slab_svc = ProfessionalTaxSlabService(env)

        emp_state = loc_svc.get_work_state(emp)
        if emp_state:
            period_sched = sched_svc.resolve_schedule(emp_state, company=company, eval_date=eval_date)
            periodicity = period_sched.periodicity if period_sched else slab_svc.resolve_state_periodicity(emp_state, company=company)
    except Exception as e:
        _logger.debug("Could not resolve PT periodicity for employee %s: %s", getattr(emp, 'name', ''), e)

    if periodicity == 'half_yearly':
        yearly = amt * 2.0
    elif periodicity == 'quarterly':
        yearly = amt * 4.0
    elif periodicity == 'annual':
        yearly = amt * 1.0
    elif periodicity == 'monthly':
        yearly = amt * 12.0
        # If standard Maharashtra 200/month, Feb is 300, total is 2500
        state_code = getattr(emp_state, 'code', '') or ''
        if round(amt, 2) == 200.0 and state_code.upper() in ('MH', 'MAHARASHTRA'):
            yearly = 2500.0
    else:
        # Fallback heuristic based on standard Indian PT rules:
        # In India, monthly PT never exceeds Rs 300.
        # If amt >= 500 (e.g. 1000, 1250), it is a half-yearly or annual deduction
        if amt >= 500.0:
            yearly = amt * 2.0
        else:
            yearly = amt * 12.0

    # Constitutional cap under Article 276(2)
    return min(yearly, 2500.0)


def _compute_lwf_yearly_amount(env, emp, monthly_amt, eval_date, company):
    """
    Compute yearly Labour Welfare Fund amount based on state frequency (monthly, half-yearly, annual).
    """
    amt = abs(float(monthly_amt or 0.0))
    if amt == 0.0:
        return 0.0

    freq = None
    try:
        from ..services.payroll.work_location_service import PayrollWorkLocationService
        from ..services.lwf.lwf_rate_service import LWFRateService

        work_state = PayrollWorkLocationService(env).get_work_state(emp)
        rate_cfg = LWFRateService(env).get_rate_config(work_state, eval_date=eval_date, company=company)
        if rate_cfg:
            freq = rate_cfg.deduction_frequency
    except Exception as e:
        _logger.debug("Could not resolve LWF frequency for employee %s: %s", getattr(emp, 'name', ''), e)

    if freq == 'half_yearly':
        yearly = amt * 2.0
    elif freq == 'annual':
        yearly = amt * 1.0
    elif freq == 'monthly':
        yearly = amt * 12.0
    else:
        # Fallback: In India, LWF is almost always half-yearly (June & Dec) or annual (Dec).
        yearly = amt * 2.0

    return yearly


class HdsSalaryStatementReport(models.Model):
    _name = 'hds.salary.statement.report'
    _description = 'Salary Statement Report'
    _order = 'year desc, month desc, id desc'

    name = fields.Char(
        string='Description',
        compute='_compute_name',
        store=True,
        readonly=False,
        required=True
    )

    year = fields.Selection(
        selection=lambda self: [(str(y), str(y)) for y in range(2020, 2031)],
        string='Year',
        default=lambda self: str(date.today().year),
        required=True
    )

    month = fields.Selection(
        selection=MONTH_SELECTION,
        string='Month',
        default=lambda self: str(date.today().month),
        required=True
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    payslip_state = fields.Selection([
        ('paid', 'Paid'),
        ('confirmed', 'Confirmed & Paid (Done, Paid)'),
        ('done', 'Done'),
        ('all', 'All States (Draft, Verify, Done, Paid)'),
    ], string='Payslip Status Filter', default='confirmed', required=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Populated'),
    ], string='Status', default='draft', required=True)

    line_ids = fields.One2many(
        'hds.salary.statement.line',
        'statement_id',
        string='Salary Statement Lines'
    )

    employee_count = fields.Integer(
        string='Eligible Employees Count',
        compute='_compute_employee_count',
        store=True
    )

    xlsx_file = fields.Binary(string='Excel Report (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    @api.depends('year', 'month')
    def _compute_name(self):
        month_dict = dict(MONTH_SELECTION)
        for rec in self:
            m_label = month_dict.get(str(rec.month), '')
            y_label = rec.year or ''
            if m_label and y_label:
                rec.name = f"Salary Statement - {m_label}, {y_label}"
            elif not rec.name:
                rec.name = "Salary Statement"

    @api.model_create_multi
    def create(self, vals_list):
        month_dict = dict(MONTH_SELECTION)
        for vals in vals_list:
            if not vals.get('name'):
                m = month_dict.get(str(vals.get('month', date.today().month)), '')
                y = vals.get('year', str(date.today().year))
                vals['name'] = f"Salary Statement - {m}, {y}" if m and y else "Salary Statement"
        return super().create(vals_list)

    @api.depends('line_ids', 'line_ids.employee_id')
    def _compute_employee_count(self):
        for rec in self:
            rec.employee_count = len(rec.line_ids.mapped('employee_id'))

    def action_populate(self):
        self.ensure_one()
        y = int(self.year)
        m = int(self.month)

        month_start = date(y, m, 1)
        month_end = date(y, m, calendar.monthrange(y, m)[1])

        # Search matching payslips for company and period
        domain = [
            ('company_id', '=', self.company_id.id),
            ('date_from', '>=', month_start),
            ('date_to', '<=', month_end),
            ('state', 'in', ('done', 'paid')),
        ]
        payslips = self.env['hr.payslip'].search(domain, order='employee_id asc, date_to desc, id desc')
        if not payslips:
            domain_any = [
                ('company_id', '=', self.company_id.id),
                ('date_from', '>=', month_start),
                ('date_to', '<=', month_end),
                ('state', '!=', 'cancel'),
            ]
            payslips = self.env['hr.payslip'].search(domain_any, order='employee_id asc, date_to desc, id desc')

        # Deduplicate per employee: pick the best slip per employee
        state_prio = {'paid': 4, 'done': 3, 'verify': 2, 'draft': 1}
        emp_slips = {}
        for slip in payslips:
            if not slip.line_ids:
                continue
            emp_id = slip.employee_id.id
            if emp_id not in emp_slips:
                emp_slips[emp_id] = slip
            else:
                existing = emp_slips[emp_id]
                prio_new = (state_prio.get(slip.state, 0), slip.id)
                prio_old = (state_prio.get(existing.state, 0), existing.id)
                if prio_new > prio_old:
                    emp_slips[emp_id] = slip

        valid_slips = list(emp_slips.values())
        self.line_ids.unlink()

        month_name = dict(MONTH_SELECTION).get(str(self.month), '')
        month_label = f"{month_name} {self.year}"

        for slip in valid_slips:
            emp = slip.employee_id
            emp_ref = getattr(emp, 'registration_number', False) or getattr(emp, 'emp_id', False) or f"EMP{emp.id:04d}"

            # 1. Dates & Designations for Employee Info Box
            doj = getattr(emp, 'first_contract_date', False) or getattr(emp, 'date_start', False)
            if not doj and hasattr(emp, 'contract_id') and emp.contract_id:
                doj = emp.contract_id.date_start
            doj_str = doj.strftime('%d/%m/%Y') if doj else '-'

            eff_date = slip.date_from or (emp.contract_id.date_start if hasattr(emp, 'contract_id') and emp.contract_id else False)
            eff_str = eff_date.strftime('%d/%m/%Y') if eff_date else '-'

            designation_str = getattr(emp, 'job_title', None) or (emp.job_id.name if hasattr(emp, 'job_id') and emp.job_id else '') or '-'
            structure_str = slip.struct_id.name or 'India: Regular Pay'

            lines = slip.line_ids

            # Working days
            working_days = 0.0
            if slip.worked_days_line_ids:
                working_days = sum(float(w.number_of_days or 0.0) for w in slip.worked_days_line_ids if (w.code or '').upper() not in ('UNPAID', 'ABSENT', 'SHORTAGE', 'LEAVE_UNPAID'))
            if working_days <= 0:
                working_days = float(calendar.monthrange(y, m)[1])

            # 2. Earnings / Allowances Breakdown
            allowance_items = []
            for line in lines:
                code = (line.code or '').upper()
                cat_code = (line.category_id.code or '').upper() if line.category_id else ''
                amt = float(line.total or 0.0)

                # Skip deductions, employer contributions, intermediate calculations, and net
                if cat_code in ('DED', 'COMP', 'NET', 'PF_CALC', 'ESIC_CALC', 'CALC') or code in ('PF_WAGE', 'ESIC_WAGE', 'BASIC_PF', 'PF_BASE', 'ESI_WAGE', 'ESIC_BASE'):
                    continue

                if amt <= 0:
                    continue

                display_name = line.name
                if code == 'GROSS' and (not display_name or display_name == 'Gross'):
                    display_name = 'Taxable Salary'

                monthly_val = amt
                yearly_val = round(monthly_val * 12, 2)
                allowance_items.append({
                    'code': code,
                    'name': display_name,
                    'monthly': monthly_val,
                    'yearly': yearly_val,
                    'monthly_str': format_inr(monthly_val),
                    'yearly_str': format_inr(yearly_val),
                })

            # Sort allowances so BASIC, HRA, FIXED, other, GROSS, Reimbursement appear logically
            def alw_sort_key(item):
                c = item['code']
                if c == 'BASIC':
                    return 1
                if c == 'HRA':
                    return 2
                if c == 'FIXED':
                    return 3
                if c == 'GROSS':
                    return 8
                if 'REIMBURSE' in c or 'REIMB' in c:
                    return 9
                return 5
            allowance_items.sort(key=alw_sort_key)

            # 3. Deductions Breakdown
            deduction_items = []

            TOTAL_ER_EPF_CODES = {'EMPLOYER_EPF', 'ER_EPF', 'ER_PF', 'PF_ER', 'EMPR_PF'}
            all_line_codes = {(l.code or '').upper() for l in lines}
            has_total_er_epf = bool(all_line_codes.intersection(TOTAL_ER_EPF_CODES))
            seen_er_epf = False
            seen_er_esic = False
            seen_er_lwf = False

            for line in lines:
                code = (line.code or '').upper()
                cat_code = (line.category_id.code or '').upper() if line.category_id else ''
                amt = abs(float(line.total or 0.0))

                # Avoid duplicate / breakdown lines when aggregate employer EPF already exists
                if has_total_er_epf and code in ('EPF_SHARE', 'EPS', 'EDLI', 'EPF_ADMIN', 'EDLI_ADMIN', 'EDLI_ADMIN_CHARGE', 'EPF_ADMIN_CHARGE'):
                    continue

                is_ded = cat_code == 'DED'
                is_er_epf = cat_code == 'COMP' and (
                    code in TOTAL_ER_EPF_CODES or
                    (not has_total_er_epf and code == 'EPF_SHARE')
                )
                is_er_esic = cat_code == 'COMP' and code in ('ESIC_ER', 'ER_ESI', 'ESI_ER')
                is_er_lwf = cat_code == 'COMP' and code in ('LWF_ER', 'ER_LWF')

                if not (is_ded or is_er_epf or is_er_esic or is_er_lwf):
                    continue

                if is_er_epf:
                    if seen_er_epf:
                        continue
                    seen_er_epf = True
                elif is_er_esic:
                    if seen_er_esic:
                        continue
                    seen_er_esic = True
                elif is_er_lwf:
                    if seen_er_lwf:
                        continue
                    seen_er_lwf = True

                if amt == 0:
                    continue

                display_name = line.name
                if code in ('EPF', 'EE_PF', 'PF'):
                    display_name = 'Provident fund - Employee'
                elif is_er_epf or code in TOTAL_ER_EPF_CODES or code == 'EPF_SHARE':
                    display_name = 'Provident fund - Employer'
                elif code in ('ESIC_EE', 'EE_ESI', 'ESI', 'ESIC', 'ESI_EE') or (cat_code == 'DED' and 'ESI' in code):
                    display_name = "Employee's State Insurance Corporation"
                elif is_er_esic or code in ('ESIC_ER', 'ER_ESI', 'ESI_ER'):
                    display_name = "Employer ESIC Contribution"
                elif code in ('LWF_EE', 'EE_LWF', 'LWF', 'LWF_DED') or (cat_code == 'DED' and 'LWF' in code):
                    display_name = "Employee's Deduction Towards State Labour Welfare Fund"
                elif is_er_lwf or code in ('LWF_ER', 'ER_LWF'):
                    display_name = "Employer LWF Contribution"
                elif code in ('PT', 'PROF_TAX', 'PT_DED', 'PROFESSIONAL_TAX', 'HDS_IN_PT') or (cat_code == 'DED' and 'PT' in code):
                    display_name = 'Professional Tax'
                elif code in ('TDS', 'HDS_IN_TDS', 'INCOME_TAX', 'IT'):
                    display_name = 'Tax Deducted at Source'

                monthly_val = -amt
                eval_date = slip.date_from or date(y, m, 1)

                if 'Professional Tax' in display_name:
                    yearly_abs = _compute_pt_yearly_amount(self.env, emp, amt, eval_date, self.company_id)
                    yearly_val = -yearly_abs
                elif "Labour Welfare" in display_name or "LWF" in display_name:
                    yearly_abs = _compute_lwf_yearly_amount(self.env, emp, amt, eval_date, self.company_id)
                    yearly_val = -yearly_abs
                else:
                    yearly_val = round(monthly_val * 12, 2)

                deduction_items.append({
                    'code': code,
                    'name': display_name,
                    'monthly': monthly_val,
                    'yearly': yearly_val,
                    'monthly_str': format_inr(monthly_val),
                    'yearly_str': format_inr(yearly_val),
                })

            eval_date = slip.date_from or date(y, m, 1)

            # Ensure Employer ESIC Contribution is included if applicable and missing from slip lines
            if not seen_er_esic:
                ee_esic_item = next((d for d in deduction_items if any(k in d['name'] for k in ("State Insurance", "ESIC", "ESI")) or d['code'] in ('ESIC_EE', 'EE_ESI', 'ESI', 'ESIC', 'ESI_EE')), None)
                er_esic_amt = 0.0
                if hasattr(slip, 'hds_in_compute_esic_employer'):
                    try:
                        er_esic_amt = abs(float(slip.hds_in_compute_esic_employer() or 0.0))
                    except Exception:
                        er_esic_amt = 0.0
                if er_esic_amt == 0.0 and ee_esic_item:
                    ee_amt = abs(float(ee_esic_item.get('monthly', 0.0)))
                    if ee_amt > 0:
                        er_esic_amt = round((ee_amt / 0.0075) * 0.0325, 2)
                elif er_esic_amt == 0.0 and getattr(emp, 'hds_in_esic_applicable', False):
                    gross_wage = sum(a['monthly'] for a in allowance_items)
                    if 0 < gross_wage <= 21000.0:
                        er_esic_amt = round(gross_wage * 0.0325, 2)

                if er_esic_amt > 0.0:
                    monthly_val = -er_esic_amt
                    yearly_val = round(monthly_val * 12, 2)
                    deduction_items.append({
                        'code': 'ESIC_ER',
                        'name': 'Employer ESIC Contribution',
                        'monthly': monthly_val,
                        'yearly': yearly_val,
                        'monthly_str': format_inr(monthly_val),
                        'yearly_str': format_inr(yearly_val),
                    })

            # Ensure Employer LWF Contribution is included if applicable and missing from slip lines
            if not seen_er_lwf:
                ee_lwf_item = next((d for d in deduction_items if (any(k in d['name'] for k in ("Labour Welfare", "LWF")) or d['code'] in ('LWF_EE', 'EE_LWF', 'LWF', 'LWF_DED')) and not (any(e in d['name'] for e in ("Employer", "ER")) or d['code'] in ('LWF_ER', 'ER_LWF'))), None)
                er_lwf_amt = 0.0
                if hasattr(slip, 'hds_in_compute_lwf_employer'):
                    try:
                        er_lwf_amt = abs(float(slip.hds_in_compute_lwf_employer() or 0.0))
                    except Exception:
                        er_lwf_amt = 0.0
                # Fallback only when Employee LWF was deducted on slip and this is a statutory deduction month
                if er_lwf_amt == 0.0 and ee_lwf_item:
                    try:
                        from ..services.payroll.work_location_service import PayrollWorkLocationService
                        from ..services.lwf.lwf_rate_service import LWFRateService
                        work_state = PayrollWorkLocationService(self.env).get_work_state(emp)
                        rate_cfg = LWFRateService(self.env).get_rate_config(work_state, eval_date=eval_date, company=self.company_id)
                        if rate_cfg and rate_cfg.is_deduction_month(eval_date):
                            er_lwf_amt = float(rate_cfg.empl_contribution or 0.0)
                    except Exception:
                        pass
                    if er_lwf_amt == 0.0:
                        try:
                            work_state = PayrollWorkLocationService(self.env).get_work_state(emp)
                            rate_cfg = LWFRateService(self.env).get_rate_config(work_state, eval_date=eval_date, company=self.company_id)
                            if rate_cfg and rate_cfg.is_deduction_month(eval_date):
                                ee_amt = abs(float(ee_lwf_item.get('monthly', 0.0)))
                                er_lwf_amt = round(ee_amt * 3.0, 2) if ee_amt == 25.0 else ee_amt
                        except Exception:
                            pass

                if er_lwf_amt > 0.0:
                    monthly_val = -er_lwf_amt
                    yearly_abs = _compute_lwf_yearly_amount(self.env, emp, er_lwf_amt, eval_date, self.company_id)
                    yearly_val = -yearly_abs
                    deduction_items.append({
                        'code': 'LWF_ER',
                        'name': 'Employer LWF Contribution',
                        'monthly': monthly_val,
                        'yearly': yearly_val,
                        'monthly_str': format_inr(monthly_val),
                        'yearly_str': format_inr(yearly_val),
                    })

            def ded_sort_key(item):
                name = item['name']
                if 'Professional Tax' in name:
                    return 1
                if 'Provident fund - Employee' in name:
                    return 2
                if 'Provident fund - Employer' in name:
                    return 3
                if any(k in name for k in ("Employee's State Insurance", "Employee ESIC", "ESIC - Employee")):
                    return 4
                if any(k in name for k in ("Employer ESIC", "Employer's State Insurance", "ESIC - Employer")):
                    return 5
                if any(k in name for k in ("Employee's Deduction Towards State Labour Welfare", "Employee LWF", "LWF - Employee", "Labour Welfare Fund - Employee")):
                    return 6
                if any(k in name for k in ("Employer LWF", "Employer's Deduction Towards State Labour Welfare", "LWF - Employer", "Labour Welfare Fund - Employer")):
                    return 7
                if 'Tax Deducted at Source' in name:
                    return 8
                return 10
            deduction_items.sort(key=ded_sort_key)

            total_ded_monthly = sum(d['monthly'] for d in deduction_items)
            total_ded_yearly = sum(d['yearly'] for d in deduction_items)

            # 4. Net Salary
            net_line = lines.filtered(lambda l: (l.code or '').upper() == 'NET')
            if net_line:
                net_monthly = float(net_line[0].total or 0.0)
            else:
                net_monthly = float(getattr(slip, 'net_amount', None) or getattr(slip, 'net_wage', 0.0) or 0.0)
                if net_monthly <= 0:
                    net_monthly = sum(a['monthly'] for a in allowance_items) + total_ded_monthly

            net_yearly = round(net_monthly * 12, 2)

            statement_data = {
                'allowances': allowance_items,
                'deductions': deduction_items,
                'total_ded_monthly': total_ded_monthly,
                'total_ded_yearly': total_ded_yearly,
                'total_ded_monthly_str': format_inr(total_ded_monthly),
                'total_ded_yearly_str': format_inr(total_ded_yearly),
                'net_monthly': net_monthly,
                'net_yearly': net_yearly,
                'net_monthly_str': format_inr(net_monthly),
                'net_yearly_str': format_inr(net_yearly),
            }

            created_line = self.env['hds.salary.statement.line'].create({
                'statement_id': self.id,
                'employee_id': emp.id,
                'emp_ref': emp_ref,
                'department_id': emp.department_id.id if emp.department_id else False,
                'job_id': emp.job_id.id if emp.job_id else False,
                'designation': designation_str,
                'date_of_joining': doj_str,
                'salary_effective_from': eff_str,
                'structure_name': structure_str,
                'payslip_id': slip.id,
                'payroll_month': month_label,
                'working_days': round(working_days, 1),
                'statement_data_json': json.dumps(statement_data),
                'gross': sum(a['monthly'] for a in allowance_items),
                'total_deductions': abs(total_ded_monthly),
                'net_pay': net_monthly,
            })

            # Generate individual PDF report
            created_line.generate_pdf_report()

        self.state = 'done'
        return True

    def action_view_employees(self):
        self.ensure_one()
        return {
            'name': _('Employee Declarations'),
            'type': 'ir.actions.act_window',
            'res_model': 'hds.salary.statement.line',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('hudson_in_payroll.hds_salary_statement_line_view_tree').id, 'list'),
                (self.env.ref('hudson_in_payroll.hds_salary_statement_line_view_form').id, 'form'),
            ],
            'domain': [('statement_id', '=', self.id)],
            'context': {'default_statement_id': self.id},
            'target': 'current',
        }

    def action_print_pdf(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_populate()
        if not self.line_ids:
            raise UserError(_("No salary statement lines available to print."))
        return self.env.ref('hudson_in_payroll.action_report_salary_statement').report_action(self)

    def action_reset_to_draft(self):
        self.ensure_one()
        self.state = 'draft'
        return True

    def action_export_xlsx(self):
        self.ensure_one()
        if not self.line_ids:
            self.action_populate()

        if not self.line_ids:
            raise UserError(_("No salary statement lines available to export."))

        filename = f"Salary_Statement_{dict(MONTH_SELECTION).get(str(self.month))}_{self.year}.xlsx"
        output = io.BytesIO()

        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            sheet = workbook.add_worksheet('Salary Statement')

            title_fmt = workbook.add_format({'bold': True, 'font_size': 14})
            sub_title_fmt = workbook.add_format({'font_size': 10, 'italic': True, 'font_color': '#555555'})

            hdr_fmt = workbook.add_format({'bold': True, 'bg_color': '#2E75B6', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
            num_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
            text_fmt = workbook.add_format({'border': 1})
            total_fmt = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'bg_color': '#D9E1F2', 'border': 1})

            sheet.write(0, 0, f"SALARY STATEMENT REPORT — {self.company_id.name}", title_fmt)
            sheet.write(1, 0, f"{self.name} | Period: {dict(MONTH_SELECTION).get(str(self.month))} {self.year}", sub_title_fmt)

            sheet.set_column(0, 0, 16)
            sheet.set_column(1, 1, 24)
            sheet.set_column(2, 3, 20)
            sheet.set_column(4, 6, 16)

            headers = ['Employee Ref', 'Employee Name', 'Department', 'Designation', 'Gross Salary', 'Total Deductions', 'Net Salary']
            for col, h in enumerate(headers):
                sheet.write(3, col, h, hdr_fmt)

            row = 4
            for l in self.line_ids:
                sheet.write(row, 0, l.emp_ref or '', text_fmt)
                sheet.write(row, 1, l.employee_id.name or '', text_fmt)
                sheet.write(row, 2, l.department_id.name or '', text_fmt)
                sheet.write(row, 3, l.designation or '', text_fmt)
                sheet.write(row, 4, l.gross, num_fmt)
                sheet.write(row, 5, l.total_deductions, num_fmt)
                sheet.write(row, 6, l.net_pay, num_fmt)
                row += 1

            sheet.write(row, 3, 'TOTAL', total_fmt)
            sheet.write(row, 4, sum(l.gross for l in self.line_ids), total_fmt)
            sheet.write(row, 5, sum(l.total_deductions for l in self.line_ids), total_fmt)
            sheet.write(row, 6, sum(l.net_pay for l in self.line_ids), total_fmt)

            workbook.close()
            output.seek(0)
            self.xlsx_file = base64.b64encode(output.read())
            self.xlsx_filename = filename

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model=hds.salary.statement.report&id={self.id}&field=xlsx_file&download=true&filename={filename}',
            'target': 'self',
        }


class HdsSalaryStatementLine(models.Model):
    _name = 'hds.salary.statement.line'
    _description = 'Salary Statement Report Line Item'
    _order = 'id asc'

    statement_id = fields.Many2one(
        'hds.salary.statement.report',
        string='Statement Header',
        ondelete='cascade',
        required=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='statement_id.company_id',
        store=True,
        index=True,
        readonly=True
    )

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    emp_ref = fields.Char(string='Employee ID / Reference')
    department_id = fields.Many2one('hr.department', string='Department')
    job_id = fields.Many2one('hr.job', string='Job Position')
    designation = fields.Char(string='Designation')
    date_of_joining = fields.Char(string='Date of Joining')
    salary_effective_from = fields.Char(string='Salary Effective from')
    structure_name = fields.Char(string='Salary Structure')

    payslip_id = fields.Many2one('hr.payslip', string='Payslip')
    payroll_month = fields.Char(string='Payroll Month')
    working_days = fields.Float(string='Paid Days / Working Days')

    statement_data_json = fields.Text(string='Statement Data JSON')

    pdf_file = fields.Binary(string='PDF File', readonly=True)
    pdf_filename = fields.Char(string='PDF Filename', readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated PDF'),
    ], string='State', default='generated')

    # Summary amounts
    gross = fields.Monetary(string='Gross Salary')
    total_deductions = fields.Monetary(string='Total Deductions')
    net_pay = fields.Monetary(string='Net Pay')

    currency_id = fields.Many2one(
        'res.currency',
        related='statement_id.company_id.currency_id',
        readonly=True
    )

    def get_statement_month_year(self):
        self.ensure_one()
        m_name = dict(MONTH_SELECTION).get(str(self.statement_id.month), '')
        return f"{m_name} {self.statement_id.year}"

    def get_statement_data(self):
        self.ensure_one()
        if self.statement_data_json:
            try:
                return json.loads(self.statement_data_json)
            except Exception:
                pass
        return {}

    def get_allowance_lines(self):
        return self.get_statement_data().get('allowances', [])

    def _sanitize_statement_data(self):
        """Sanitize statement_data_json to remove duplicate EPF_SHARE (917),
        recalculate PT and LWF yearly amounts based on employee cycles, and keep totals accurate."""
        self.ensure_one()
        data = self.get_statement_data()
        if not data:
            return
        deductions = data.get('deductions', [])
        has_total_epf = any(
            d.get('code') in ('EMPLOYER_EPF', 'ER_EPF', 'ER_PF', 'PF_ER', 'EMPR_PF') or
            (d.get('name') == 'Provident fund - Employer' and round(abs(d.get('monthly', 0.0)), 2) != 917.0 and abs(d.get('monthly', 0.0)) > 917.0)
            for d in deductions
        )
        has_duplicate_917 = any(
            d.get('code') == 'EPF_SHARE' or
            (d.get('name') == 'Provident fund - Employer' and round(abs(d.get('monthly', 0.0)), 2) == 917.0)
            for d in deductions
        )
        if has_total_epf and has_duplicate_917:
            deductions = [
                d for d in deductions
                if d.get('code') != 'EPF_SHARE'
                and not (d.get('name') == 'Provident fund - Employer' and round(abs(d.get('monthly', 0.0)), 2) == 917.0)
            ]

        eval_date = date(int(self.statement_id.year), int(self.statement_id.month), 1) if (self.statement_id and self.statement_id.year and self.statement_id.month) else fields.Date.today()
        emp = self.employee_id
        company = self.company_id or self.env.company

        # Statutory LWF schedule check
        lwf_rate_cfg = None
        is_lwf_month = False
        try:
            from ..services.payroll.work_location_service import PayrollWorkLocationService
            from ..services.lwf.lwf_rate_service import LWFRateService
            work_state = PayrollWorkLocationService(self.env).get_work_state(emp)
            lwf_rate_cfg = LWFRateService(self.env).get_rate_config(work_state, eval_date=eval_date, company=company)
            if lwf_rate_cfg:
                is_lwf_month = lwf_rate_cfg.is_deduction_month(eval_date)
        except Exception:
            pass

        slip = self.payslip_id
        slip_has_er_lwf = bool(slip and any(line.salary_rule_id.code in ('LWF_ER', 'ER_LWF') and abs(line.total) > 0 for line in slip.line_ids))
        has_ee_lwf_in_data = any(
            (any(k in d.get('name', '') for k in ("Labour Welfare", "LWF")) or d.get('code') in ('LWF_EE', 'EE_LWF', 'LWF'))
            and not (any(e in d.get('name', '') for e in ("Employer", "ER")) or d.get('code') in ('LWF_ER', 'ER_LWF'))
            for d in deductions
        )

        seen_er_epf = False
        seen_er_esic = False
        seen_er_lwf = False
        final_ded = []

        for d in deductions:
            name = d.get('name', '')
            m_val = float(d.get('monthly', 0.0))
            amt = abs(m_val)

            # Standardize names matching reference format
            if 'Provident fund - Employer' in name:
                if seen_er_epf:
                    continue
                seen_er_epf = True
            elif 'State Insurance' in name or 'ESIC' in name:
                if 'Employer' in name or 'ER' in d.get('code', ''):
                    if seen_er_esic:
                        continue
                    seen_er_esic = True
                    name = "Employer ESIC Contribution"
                else:
                    name = "Employee's State Insurance Corporation"
            elif 'Labour Welfare' in name or 'LWF' in name:
                if 'Employer' in name or 'ER' in d.get('code', ''):
                    # Statutory validation: Employer LWF should only exist if:
                    # 1) The payslip actually computed an LWF_ER salary rule, OR
                    # 2) This month is a statutory deduction month AND Employee LWF is present on the statement
                    if not slip_has_er_lwf and (not is_lwf_month or not has_ee_lwf_in_data):
                        continue  # Discard phantom Employer LWF in non-deduction / non-LWF month
                    if seen_er_lwf:
                        continue
                    seen_er_lwf = True
                    name = "Employer LWF Contribution"
                else:
                    name = "Employee's Deduction Towards State Labour Welfare Fund"

            # Recompute yearly amounts for PT and LWF based on employee cycle / state frequency
            y_val = float(d.get('yearly', 0.0))
            if 'Professional Tax' in name:
                y_val = -_compute_pt_yearly_amount(self.env, emp, amt, eval_date, company)
            elif 'Labour Welfare' in name or 'LWF' in name:
                y_val = -_compute_lwf_yearly_amount(self.env, emp, amt, eval_date, company)
            elif y_val == 0.0:
                y_val = round(m_val * 12, 2)

            d['name'] = name
            d['monthly'] = m_val
            d['yearly'] = y_val
            d['monthly_str'] = format_inr(m_val)
            d['yearly_str'] = format_inr(y_val)
            final_ded.append(d)

        # Check if Employer ESIC is missing but Employee ESIC is present on the record
        if not seen_er_esic:
            ee_esic_item = next((d for d in final_ded if (any(k in d.get('name', '') for k in ("State Insurance", "ESIC", "ESI")) or d.get('code') in ('ESIC_EE', 'EE_ESI', 'ESI', 'ESIC', 'ESI_EE')) and not (any(e in d.get('name', '') for e in ("Employer", "ER")) or d.get('code') in ('ESIC_ER', 'ER_ESI', 'ESI_ER'))), None)
            slip = self.payslip_id
            er_esic_amt = 0.0
            if slip and hasattr(slip, 'hds_in_compute_esic_employer'):
                try:
                    er_esic_amt = abs(float(slip.hds_in_compute_esic_employer() or 0.0))
                except Exception:
                    er_esic_amt = 0.0
            if er_esic_amt == 0.0 and ee_esic_item:
                ee_amt = abs(float(ee_esic_item.get('monthly', 0.0)))
                if ee_amt > 0:
                    er_esic_amt = round((ee_amt / 0.0075) * 0.0325, 2)
            elif er_esic_amt == 0.0 and getattr(emp, 'hds_in_esic_applicable', False):
                allowances = data.get('allowances', [])
                gross_wage = sum(float(a.get('monthly', 0.0)) for a in allowances)
                if 0 < gross_wage <= 21000.0:
                    er_esic_amt = round(gross_wage * 0.0325, 2)

            if er_esic_amt > 0.0:
                monthly_val = -er_esic_amt
                yearly_val = round(monthly_val * 12, 2)
                final_ded.append({
                    'code': 'ESIC_ER',
                    'name': 'Employer ESIC Contribution',
                    'monthly': monthly_val,
                    'yearly': yearly_val,
                    'monthly_str': format_inr(monthly_val),
                    'yearly_str': format_inr(yearly_val),
                })

        # Check if Employer LWF is missing but Employee LWF is present on the record
        if not seen_er_lwf:
            ee_lwf_item = next((d for d in final_ded if (any(k in d.get('name', '') for k in ("Labour Welfare", "LWF")) or d.get('code') in ('LWF_EE', 'EE_LWF', 'LWF', 'LWF_DED')) and not (any(e in d.get('name', '') for e in ("Employer", "ER")) or d.get('code') in ('LWF_ER', 'ER_LWF'))), None)
            slip = self.payslip_id
            er_lwf_amt = 0.0
            if slip and hasattr(slip, 'hds_in_compute_lwf_employer'):
                try:
                    er_lwf_amt = abs(float(slip.hds_in_compute_lwf_employer() or 0.0))
                except Exception:
                    er_lwf_amt = 0.0
            if er_lwf_amt == 0.0 and ee_lwf_item and is_lwf_month:
                if lwf_rate_cfg:
                    er_lwf_amt = float(lwf_rate_cfg.empl_contribution or 0.0)
                if er_lwf_amt == 0.0:
                    ee_amt = abs(float(ee_lwf_item.get('monthly', 0.0)))
                    er_lwf_amt = round(ee_amt * 3.0, 2) if ee_amt == 25.0 else ee_amt

            if er_lwf_amt > 0.0:
                monthly_val = -er_lwf_amt
                yearly_abs = _compute_lwf_yearly_amount(self.env, emp, er_lwf_amt, eval_date, company)
                yearly_val = -yearly_abs
                final_ded.append({
                    'code': 'LWF_ER',
                    'name': 'Employer LWF Contribution',
                    'monthly': monthly_val,
                    'yearly': yearly_val,
                    'monthly_str': format_inr(monthly_val),
                    'yearly_str': format_inr(yearly_val),
                })

        def ded_sort_key(item):
            n = item.get('name', '')
            if 'Professional Tax' in n:
                return 1
            if 'Provident fund - Employee' in n:
                return 2
            if 'Provident fund - Employer' in n:
                return 3
            if any(k in n for k in ("Employee's State Insurance", "Employee ESIC", "ESIC - Employee")):
                return 4
            if any(k in n for k in ("Employer ESIC", "Employer's State Insurance", "ESIC - Employer")):
                return 5
            if any(k in n for k in ("Employee's Deduction Towards State Labour Welfare", "Employee LWF", "LWF - Employee", "Labour Welfare Fund - Employee")):
                return 6
            if any(k in n for k in ("Employer LWF", "Employer's Deduction Towards State Labour Welfare", "LWF - Employer", "Labour Welfare Fund - Employer")):
                return 7
            if 'Tax Deducted at Source' in n:
                return 8
            return 10
        final_ded.sort(key=ded_sort_key)

        tot_monthly = sum(d.get('monthly', 0.0) for d in final_ded)
        tot_yearly = sum(d.get('yearly', 0.0) for d in final_ded)
        data['deductions'] = final_ded
        data['total_ded_monthly'] = tot_monthly
        data['total_ded_yearly'] = tot_yearly
        data['total_ded_monthly_str'] = format_inr(tot_monthly)
        data['total_ded_yearly_str'] = format_inr(tot_yearly)

        self.write({
            'statement_data_json': json.dumps(data),
            'total_deductions': abs(tot_monthly),
        })

    def get_deduction_lines(self):
        deductions = self.get_statement_data().get('deductions', [])
        needs_sanitize = False
        has_ee_esic = any(('State Insurance' in d.get('name', '') or 'ESIC' in d.get('name', '') or d.get('code') in ('ESIC_EE', 'EE_ESI', 'ESI', 'ESIC')) and not ('Employer' in d.get('name', '') or 'ER' in d.get('code', '')) for d in deductions)
        has_er_esic = any(('Employer' in d.get('name', '') and ('ESIC' in d.get('name', '') or 'Insurance' in d.get('name', ''))) or d.get('code') in ('ESIC_ER', 'ER_ESI', 'ESI_ER') for d in deductions)
        has_ee_lwf = any(('Labour Welfare' in d.get('name', '') or 'LWF' in d.get('name', '') or d.get('code') in ('LWF_EE', 'EE_LWF', 'LWF')) and not ('Employer' in d.get('name', '') or 'ER' in d.get('code', '')) for d in deductions)
        has_er_lwf = any(('Employer' in d.get('name', '') and ('LWF' in d.get('name', '') or 'Labour Welfare' in d.get('name', ''))) or d.get('code') in ('LWF_ER', 'ER_LWF') for d in deductions)

        if (has_ee_esic and not has_er_esic) or (has_ee_lwf and not has_er_lwf) or (has_er_lwf and not has_ee_lwf):
            needs_sanitize = True

        for d in deductions:
            n = d.get('name', '')
            m = abs(float(d.get('monthly', 0.0)))
            y = abs(float(d.get('yearly', 0.0)))
            if 'Professional Tax' in n and (y > 2500.0 or (m >= 500.0 and y > m * 2)):
                needs_sanitize = True
                break
            if ('Labour Welfare' in n or 'LWF' in n) and (m > 0 and round(y, 2) == round(m * 12, 2) and m >= 20):
                needs_sanitize = True
                break
            if d.get('code') == 'EPF_SHARE':
                needs_sanitize = True
                break
            if n in ("Employer's State Insurance Corporation", "Employer's Deduction Towards State Labour Welfare Fund"):
                needs_sanitize = True
                break

        if needs_sanitize:
            try:
                self._sanitize_statement_data()
                deductions = self.get_statement_data().get('deductions', [])
            except Exception:
                pass
        return deductions

    def get_total_ded_monthly_str(self):
        ded_lines = self.get_deduction_lines()
        if ded_lines:
            tot = sum(d.get('monthly', 0.0) for d in ded_lines)
            return format_inr(tot)
        return self.get_statement_data().get('total_ded_monthly_str', '₹ 0.00')

    def get_total_ded_yearly_str(self):
        ded_lines = self.get_deduction_lines()
        if ded_lines:
            tot = sum(d.get('yearly', 0.0) for d in ded_lines)
            return format_inr(tot)
        return self.get_statement_data().get('total_ded_yearly_str', '₹ 0.00')

    def get_net_monthly_str(self):
        return self.get_statement_data().get('net_monthly_str', '₹ 0.00')

    def get_net_yearly_str(self):
        return self.get_statement_data().get('net_yearly_str', '₹ 0.00')

    def generate_pdf_report(self):
        self.ensure_one()
        try:
            self._sanitize_statement_data()
        except Exception as e:
            _logger.debug("Non-blocking sanitize error during PDF generation: %s", e)
        report_action = self.env.ref('hudson_in_payroll.action_report_salary_statement_line', raise_if_not_found=False)
        m_name = dict(MONTH_SELECTION).get(str(self.statement_id.month), '')
        filename = f"{self.employee_id.name}-salary-statement-report-{m_name}-{self.statement_id.year}.pdf"
        if not report_action:
            self.write({
                'pdf_filename': filename,
                'state': 'generated',
            })
            return

        try:
            pdf_content, _ = report_action._render_qweb_pdf(report_action.report_name, [self.id])
            self.write({
                'pdf_file': base64.b64encode(pdf_content),
                'pdf_filename': filename,
                'state': 'generated',
            })
        except Exception as e:
            _logger.warning("Could not generate PDF for salary statement line %s: %s", self.id, e)
            self.write({
                'pdf_filename': filename,
                'state': 'generated',
            })

    def action_print_pdf(self):
        self.ensure_one()
        try:
            self._sanitize_statement_data()
        except Exception as e:
            _logger.debug("Non-blocking sanitize error during print PDF: %s", e)
        return self.env.ref('hudson_in_payroll.action_report_salary_statement_line').report_action(self)
