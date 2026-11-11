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


MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
]


class HdsYearlySalaryEmployeeWizard(models.Model):
    _name = 'hds.yearly.salary.employee.wizard'
    _description = 'Yearly Salary by Employee Report'
    _order = 'id desc'

    name = fields.Char(string='Report Name', compute='_compute_name', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('generated', 'Generated'),
    ], string='State', default='draft')

    year = fields.Selection(
        selection=lambda self: [(str(y), str(y)) for y in range(2020, 2031)],
        string='Year',
        default=lambda self: str(date.today().year),
        required=True
    )

    @api.depends('year', 'department_id')
    def _compute_name(self):
        for rec in self:
            dept_str = f" ({rec.department_id.name})" if rec.department_id else ""
            rec.name = f"Yearly Salary by Employee / {rec.year}{dept_str}" if rec.year else "Yearly Salary by Employee"

    department_id = fields.Many2one(
        'hr.department',
        string='Department'
    )

    job_id = fields.Many2one(
        'hr.job',
        string='Job Position'
    )

    employee_ids = fields.Many2many(
        'hr.employee',
        'hds_yearly_salary_wizard_emp_rel',
        'wizard_id',
        'employee_id',
        string='Employees'
    )

    available_employee_ids = fields.Many2many(
        'hr.employee',
        compute='_compute_available_employee_ids',
        string='Available Employees'
    )

    @api.depends('company_id', 'department_id', 'job_id')
    def _compute_available_employee_ids(self):
        for rec in self:
            domain = [('company_id', '=', rec.company_id.id)]
            if rec.department_id:
                domain.append(('department_id', '=', rec.department_id.id))
            if rec.job_id:
                domain.append(('job_id', '=', rec.job_id.id))
            rec.available_employee_ids = self.env['hr.employee'].search(domain)

    @api.onchange('department_id')
    def _onchange_department_id(self):
        if self.department_id and self.job_id and self.job_id.department_id and self.job_id.department_id != self.department_id:
            self.job_id = False
        if self.employee_ids:
            self.employee_ids = self.employee_ids.filtered(
                lambda e: (not self.department_id or e.department_id == self.department_id) and
                          (not self.job_id or e.job_id == self.job_id)
            )

    @api.onchange('job_id')
    def _onchange_job_id(self):
        if self.job_id and self.job_id.department_id and not self.department_id:
            self.department_id = self.job_id.department_id
        if self.employee_ids:
            self.employee_ids = self.employee_ids.filtered(
                lambda e: (not self.department_id or e.department_id == self.department_id) and
                          (not self.job_id or e.job_id == self.job_id)
            )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )

    payslip_state = fields.Selection([
        ('confirmed', 'Confirmed & Paid (Done, Paid)'),
        ('all', 'All States (Draft, Verify, Done, Paid)'),
    ], string='Payslip Status', default='confirmed', required=True)

    xlsx_file = fields.Binary(string='Excel Report (.xlsx)', readonly=True)
    xlsx_filename = fields.Char(string='Excel Filename', readonly=True)

    record_count = fields.Integer(string='Employees Covered', readonly=True)
    total_annual_gross = fields.Float(string='Total Annual Gross', readonly=True)
    total_annual_deductions = fields.Float(string='Total Annual Deductions', readonly=True)
    total_annual_net = fields.Float(string='Total Annual Net Pay', readonly=True)
    total_annual_cost = fields.Float(string='Total Annual CTC', readonly=True)

    def _get_target_employees(self):
        self.ensure_one()
        y = int(self.year)
        year_start = date(y, 1, 1)
        year_end = date(y, 12, 31)

        domain = [
            ('company_id', '=', self.company_id.id),
            ('date_from', '>=', year_start),
            ('date_to', '<=', year_end),
        ]
        if self.payslip_state == 'done':
            domain.append(('state', '=', 'done'))
        elif self.payslip_state == 'paid':
            domain.append(('state', '=', 'paid'))
        elif self.payslip_state == 'confirmed':
            domain.append(('state', 'in', ('done', 'paid')))
        else:
            domain.append(('state', '!=', 'cancel'))

        if self.department_id:
            domain.append(('employee_id.department_id', '=', self.department_id.id))
        if self.job_id:
            domain.append(('employee_id.job_id', '=', self.job_id.id))

        payslips = self.env['hr.payslip'].search(domain)
        paid_emp_ids = payslips.filtered(lambda s: bool(s.line_ids)).mapped('employee_id').ids

        if not paid_emp_ids:
            return self.env['hr.employee']

        if self.employee_ids:
            target_ids = list(set(self.employee_ids.ids).intersection(paid_emp_ids))
            return self.env['hr.employee'].browse(target_ids)
        else:
            return self.env['hr.employee'].browse(paid_emp_ids)

    def _get_yearly_data(self):
        self.ensure_one()
        employees = self._get_target_employees()
        if not employees:
            return {
                'employees': employees,
                'summary_rows': [],
                'annual_totals': [0.0] * 16,
                'detail_rows': [],
                'emp_data_map': {},
            }

        y = int(self.year)
        state_domain = []
        if self.payslip_state == 'done':
            state_domain = [('state', '=', 'done')]
        elif self.payslip_state == 'paid':
            state_domain = [('state', '=', 'paid')]
        elif self.payslip_state == 'confirmed':
            state_domain = [('state', 'in', ('done', 'paid'))]
        else:
            state_domain = [('state', '!=', 'cancel')]

        summary_rows = []
        detail_rows = []
        emp_data_map = {}
        employee_reports = []
        annual_totals = [0.0] * 16  # 12 months Net + 4 annual totals
        month_abbrs = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sept', 'Oct', 'Nov', 'Dec']
        sym = self.company_id.currency_id.symbol or '₹'

        def _cur_fmt(val):
            return f"{sym} {val:,.2f}"

        for emp in employees:
            emp_ref = getattr(emp, 'registration_number', False) or getattr(emp, 'emp_id', False) or f"EMP{emp.id:04d}"
            emp_months = {}
            ann_gross = 0.0
            ann_ded = 0.0
            ann_net = 0.0
            ann_ctc = 0.0
            month_net_list = []

            for m in range(1, 13):
                m_start = date(y, m, 1)
                m_end = date(y, m, calendar.monthrange(y, m)[1])

                slips = self.env['hr.payslip'].search([
                    ('employee_id', '=', emp.id),
                    ('company_id', '=', self.company_id.id),
                    ('date_from', '>=', m_start),
                    ('date_to', '<=', m_end),
                ] + state_domain, order='date_to desc, id desc')

                # Filter slips having computed lines
                slips = slips.filtered(lambda s: bool(s.line_ids))

                if not slips:
                    month_net_list.append(0.0)
                    emp_months[m] = False
                    continue

                # Deduplicate per month: select the best slip (paid > done > verify > draft, latest id)
                state_prio = {'paid': 4, 'done': 3, 'verify': 2, 'draft': 1}
                target_slip = slips[0]
                for s in slips[1:]:
                    prio_new = (state_prio.get(s.state, 0), s.id)
                    prio_cur = (state_prio.get(target_slip.state, 0), target_slip.id)
                    if prio_new > prio_cur:
                        target_slip = s

                struct_name = target_slip.struct_id.name if target_slip.struct_id else ''
                lines = target_slip.line_ids

                # 1. Earnings Breakdown
                basic_v = 0.0
                hra_v = 0.0
                alw_v = 0.0
                other_earn_v = 0.0

                for line in lines:
                    code = (line.code or '').upper()
                    cat_code = (line.category_id.code or '').upper() if line.category_id else ''
                    amt = float(line.total or 0.0)

                    if cat_code in ('GROSS', 'NET', 'DED', 'COMP', 'PF_CALC', 'ESIC_CALC', 'CALC') or code in ('PF_WAGE', 'ESIC_WAGE', 'BASIC_PF', 'PF_BASE', 'ESI_WAGE', 'ESIC_BASE'):
                        continue

                    if code == 'BASIC' or cat_code == 'BASIC':
                        basic_v += amt
                    elif code == 'HRA':
                        hra_v += amt
                    elif cat_code == 'ALW' or code in ('DA', 'CONV', 'SPECIAL_ALW', 'SPL_ALW', 'CHILD_EDU', 'BONUS', 'OT', 'OTHER_ALW'):
                        alw_v += amt
                    elif amt > 0:
                        other_earn_v += amt

                gross_line = lines.filtered(lambda l: (l.code or '').upper() == 'GROSS' or (l.category_id and l.category_id.code == 'GROSS'))
                if gross_line:
                    gross_v = float(gross_line[0].total or 0.0)
                else:
                    gross_v = float(getattr(target_slip, 'gross_amount', None) or getattr(target_slip, 'gross_wage', 0.0) or 0.0)
                    if gross_v <= 0:
                        gross_v = basic_v + hra_v + alw_v + other_earn_v

                # 2. Employee Deductions Breakdown
                pf_ee_v = 0.0
                esi_ee_v = 0.0
                pt_v = 0.0
                lwf_ee_v = 0.0
                tds_v = 0.0
                other_ded_v = 0.0

                for line in lines:
                    code = (line.code or '').upper()
                    cat_code = (line.category_id.code or '').upper() if line.category_id else ''
                    amt = abs(float(line.total or 0.0))

                    if cat_code in ('COMP', 'BASIC', 'ALW', 'GROSS', 'NET', 'PF_CALC', 'ESIC_CALC', 'CALC') or code in ('PF_WAGE', 'ESIC_WAGE', 'BASIC_PF', 'PF_BASE', 'ESI_WAGE', 'ESIC_BASE'):
                        continue

                    if code in ('PF', 'EPF', 'EE_PF', 'PF_EMPLOYEE', 'PF_EE') or (cat_code == 'DED' and 'PF' in code):
                        pf_ee_v += amt
                    elif code in ('ESI', 'ESIC', 'EE_ESI', 'ESIC_EE', 'ESI_EE') or (cat_code == 'DED' and 'ESI' in code):
                        esi_ee_v += amt
                    elif code in ('PT', 'PROF_TAX', 'PT_DED', 'PROFESSIONAL_TAX') or (cat_code == 'DED' and 'PT' in code):
                        pt_v += amt
                    elif code in ('LWF', 'LWF_EE', 'EE_LWF') or (cat_code == 'DED' and 'LWF' in code):
                        lwf_ee_v += amt
                    elif code in ('TDS', 'HDS_IN_TDS', 'INCOME_TAX', 'IT') or 'TDS' in code or cat_code == 'TDS':
                        tds_v += amt
                    elif cat_code == 'DED':
                        other_ded_v += amt

                tot_ded_v = pf_ee_v + esi_ee_v + pt_v + lwf_ee_v + tds_v + other_ded_v

                # 3. Net Pay
                net_line = lines.filtered(lambda l: (l.code or '').upper() == 'NET' or (l.category_id and l.category_id.code == 'NET'))
                if net_line:
                    net_v = float(net_line[0].total or 0.0)
                else:
                    net_v = float(getattr(target_slip, 'net_amount', None) or getattr(target_slip, 'net_wage', 0.0) or 0.0)
                    if net_v <= 0:
                        net_v = gross_v - tot_ded_v

                # 4. Employer Contributions Breakdown
                comp_lines = lines.filtered(lambda l: l.category_id and l.category_id.code == 'COMP')
                comp_map = {(l.code or '').upper(): abs(float(l.total or 0.0)) for l in comp_lines}

                if 'EMPLOYER_EPF' in comp_map:
                    pf_er_base = comp_map['EMPLOYER_EPF']
                elif 'EPS' in comp_map or 'EPF_SHARE' in comp_map:
                    pf_er_base = comp_map.get('EPS', 0.0) + comp_map.get('EPF_SHARE', 0.0)
                else:
                    pf_er_base = comp_map.get('ER_PF', 0.0) or comp_map.get('PF_ER', 0.0) or comp_map.get('EMPR_PF', 0.0)

                pf_er_eps = comp_map.get('EPS', 0.0)
                pf_er_share = comp_map.get('EPF_SHARE', 0.0)
                if pf_er_base > 0 and pf_er_eps == 0.0 and pf_er_share == 0.0:
                    eval_date = target_slip.date_to or target_slip.date_from or fields.Date.today()
                    eps_ceiling = self.env['hr.rule.parameter'].get_pf_parameter('EPS_WAGE_CEILING', date=eval_date) or 25000.0
                    pf_er_eps = round(min(pf_er_base / 0.12, eps_ceiling) * 0.0833, 2)
                    pf_er_share = round(pf_er_base - pf_er_eps, 2)

                pf_er_admin = (
                    comp_map.get('EDLI', 0.0) +
                    comp_map.get('EPF_ADMIN', 0.0) +
                    comp_map.get('EDLI_ADMIN', 0.0) +
                    comp_map.get('EDLI_ADMIN_CHARGE', 0.0) +
                    comp_map.get('EPF_ADMIN_CHARGE', 0.0)
                )
                pf_er_v = pf_er_base + pf_er_admin

                esi_er_v = comp_map.get('ESIC_ER', 0.0) or comp_map.get('ESI_ER', 0.0) or comp_map.get('ER_ESI', 0.0)
                lwf_er_v = comp_map.get('LWF_ER', 0.0) or comp_map.get('ER_LWF', 0.0)

                accounted_codes = {
                    'EMPLOYER_EPF', 'EPS', 'EPF_SHARE', 'EDLI', 'EPF_ADMIN', 'EDLI_ADMIN',
                    'EDLI_ADMIN_CHARGE', 'EPF_ADMIN_CHARGE',
                    'ER_PF', 'PF_ER', 'EMPR_PF', 'ESIC_ER', 'ESI_ER', 'ER_ESI', 'LWF_ER', 'ER_LWF'
                }
                other_er_v = sum(amt for code, amt in comp_map.items() if code not in accounted_codes)

                tot_er_v = pf_er_v + esi_er_v + lwf_er_v + other_er_v
                ctc_v = gross_v + tot_er_v

                month_net_list.append(round(net_v, 2))
                annual_totals[m - 1] += net_v

                ann_gross += gross_v
                ann_ded += tot_ded_v
                ann_net += net_v
                ann_ctc += ctc_v

                m_dict = {
                    'struct_name': struct_name,
                    'basic': round(basic_v, 2),
                    'hra': round(hra_v, 2),
                    'allowances': round(alw_v, 2),
                    'other_earnings': round(other_earn_v, 2),
                    'gross': round(gross_v, 2),
                    'pf_ee': round(pf_ee_v, 2),
                    'esi_ee': round(esi_ee_v, 2),
                    'pt': round(pt_v, 2),
                    'lwf_ee': round(lwf_ee_v, 2),
                    'tds': round(tds_v, 2),
                    'other_deductions': round(other_ded_v, 2),
                    'total_deductions': round(tot_ded_v, 2),
                    'net_pay': round(net_v, 2),
                    'pf_er_eps': round(pf_er_eps, 2),
                    'pf_er_share': round(pf_er_share, 2),
                    'pf_er_admin': round(pf_er_admin, 2),
                    'pf_er': round(pf_er_v, 2),
                    'esi_er': round(esi_er_v, 2),
                    'lwf_er': round(lwf_er_v, 2),
                    'other_er_contrib': round(other_er_v, 2),
                    'total_employer_cost': round(ctc_v, 2),
                }
                emp_months[m] = m_dict

                detail_rows.append({
                    'emp_ref': emp_ref,
                    'emp_name': emp.name or '',
                    'department': emp.department_id.name if emp.department_id else '',
                    'month': MONTH_NAMES[m - 1],
                    'struct_name': struct_name,
                    'basic': m_dict['basic'],
                    'hra': m_dict['hra'],
                    'allowances': m_dict['allowances'],
                    'other_earnings': m_dict['other_earnings'],
                    'gross': m_dict['gross'],
                    'pf_ee': m_dict['pf_ee'],
                    'esi_ee': m_dict['esi_ee'],
                    'pt': m_dict['pt'],
                    'lwf_ee': m_dict['lwf_ee'],
                    'tds': m_dict['tds'],
                    'other_deductions': m_dict['other_deductions'],
                    'total_deductions': m_dict['total_deductions'],
                    'net_pay': m_dict['net_pay'],
                    'pf_er_eps': m_dict['pf_er_eps'],
                    'pf_er_share': m_dict['pf_er_share'],
                    'pf_er_admin': m_dict['pf_er_admin'],
                    'pf_er': m_dict['pf_er'],
                    'esi_er': m_dict['esi_er'],
                    'lwf_er': m_dict['lwf_er'],
                    'other_er_contrib': m_dict['other_er_contrib'],
                    'total_employer_cost': m_dict['total_employer_cost'],
                })

            annual_totals[12] += ann_gross
            annual_totals[13] += ann_ded
            annual_totals[14] += ann_net
            annual_totals[15] += ann_ctc

            summary_rows.append({
                'emp_ref': emp_ref,
                'emp_name': emp.name or '',
                'department': emp.department_id.name if emp.department_id else '',
                'job_position': emp.job_id.name if emp.job_id else '',
                'months': month_net_list,
                'ann_gross': round(ann_gross, 2),
                'ann_ded': round(ann_ded, 2),
                'ann_net': round(ann_net, 2),
                'ann_ctc': round(ann_ctc, 2),
            })
            emp_data_map[emp.id] = (emp, emp_ref, emp_months, ann_gross, ann_ded, ann_net, ann_ctc)

            # Per-employee vertical month breakdown matching statutory report theme
            emp_month_rows = []
            e_tot_basic = 0.0
            e_tot_hra = 0.0
            e_tot_alw = 0.0
            e_tot_gross = 0.0
            e_tot_pf = 0.0
            e_tot_esi = 0.0
            e_tot_pt = 0.0
            e_tot_tds = 0.0
            e_tot_ded = 0.0
            e_tot_net = 0.0

            for m_idx in range(1, 13):
                m_info = emp_months.get(m_idx)
                m_label = month_abbrs[m_idx - 1]
                if m_info:
                    b = m_info.get('basic', 0.0)
                    h = m_info.get('hra', 0.0)
                    alw = m_info.get('allowances', 0.0) + m_info.get('other_earnings', 0.0)
                    g = m_info.get('gross', 0.0)
                    pf = m_info.get('pf_ee', 0.0)
                    esi = m_info.get('esi_ee', 0.0)
                    pt = m_info.get('pt', 0.0)
                    tds = m_info.get('tds', 0.0) + m_info.get('other_deductions', 0.0) + m_info.get('lwf_ee', 0.0)
                    ded = m_info.get('total_deductions', 0.0)
                    net = m_info.get('net_pay', 0.0)
                else:
                    b = h = alw = g = pf = esi = pt = tds = ded = net = 0.0

                e_tot_basic += b
                e_tot_hra += h
                e_tot_alw += alw
                e_tot_gross += g
                e_tot_pf += pf
                e_tot_esi += esi
                e_tot_pt += pt
                e_tot_tds += tds
                e_tot_ded += ded
                e_tot_net += net

                emp_month_rows.append({
                    'month': m_label,
                    'basic': b,
                    'basic_str': _cur_fmt(b),
                    'hra': h,
                    'hra_str': _cur_fmt(h),
                    'allowances': alw,
                    'allowances_str': _cur_fmt(alw),
                    'gross': g,
                    'gross_str': _cur_fmt(g),
                    'pf': pf,
                    'pf_str': _cur_fmt(pf),
                    'esi': esi,
                    'esi_str': _cur_fmt(esi),
                    'pt': pt,
                    'pt_str': _cur_fmt(pt),
                    'tds': tds,
                    'tds_str': _cur_fmt(tds),
                    'deductions': ded,
                    'deductions_str': _cur_fmt(ded),
                    'net': net,
                    'net_str': _cur_fmt(net),
                })

            employee_reports.append({
                'emp_id': emp.id,
                'name': emp.name or '',
                'code': getattr(emp, 'registration_number', False) or getattr(emp, 'emp_id', False) or '',
                'job': emp.job_id.name if emp.job_id else '',
                'department': emp.department_id.name if emp.department_id else '',
                'month_rows': emp_month_rows,
                'total': {
                    'basic': e_tot_basic,
                    'basic_str': _cur_fmt(e_tot_basic),
                    'hra': e_tot_hra,
                    'hra_str': _cur_fmt(e_tot_hra),
                    'allowances': e_tot_alw,
                    'allowances_str': _cur_fmt(e_tot_alw),
                    'gross': e_tot_gross,
                    'gross_str': _cur_fmt(e_tot_gross),
                    'pf': e_tot_pf,
                    'pf_str': _cur_fmt(e_tot_pf),
                    'esi': e_tot_esi,
                    'esi_str': _cur_fmt(e_tot_esi),
                    'pt': e_tot_pt,
                    'pt_str': _cur_fmt(e_tot_pt),
                    'tds': e_tot_tds,
                    'tds_str': _cur_fmt(e_tot_tds),
                    'deductions': e_tot_ded,
                    'deductions_str': _cur_fmt(e_tot_ded),
                    'net': e_tot_net,
                    'net_str': _cur_fmt(e_tot_net),
                }
            })

        return {
            'employees': employees,
            'summary_rows': summary_rows,
            'annual_totals': [round(t, 2) for t in annual_totals],
            'detail_rows': detail_rows,
            'emp_data_map': emp_data_map,
            'employee_reports': employee_reports,
        }

    def action_print_pdf(self):
        self.ensure_one()
        data = self._get_yearly_data()
        if not data.get('summary_rows'):
            raise UserError(_("No payslips found for the selected criteria in %s.") % self.year)
        self.write({
            'state': 'generated',
            'record_count': len(data['summary_rows']),
            'total_annual_gross': round(data['annual_totals'][12], 2),
            'total_annual_deductions': round(data['annual_totals'][13], 2),
            'total_annual_net': round(data['annual_totals'][14], 2),
            'total_annual_cost': round(data['annual_totals'][15], 2),
        })
        return self.env.ref('hudson_in_payroll.action_report_yearly_salary_employee').report_action(self)

    def action_print_xlsx(self):
        self.ensure_one()
        yearly_data = self._get_yearly_data()
        employees = yearly_data['employees']

        if not employees or not yearly_data['summary_rows']:
            raise UserError(_("No payslips found for the selected criteria in %s.") % self.year)

        y = int(self.year)
        filename = f"Yearly_Salary_by_Employee_{self.year}.xlsx"
        output = io.BytesIO()

        if xlsxwriter:
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})

            # Formatting styles
            title_fmt = workbook.add_format({'bold': True, 'font_size': 14})
            sub_title_fmt = workbook.add_format({'font_size': 10, 'italic': True, 'font_color': '#555555'})

            hdr_main_fmt = workbook.add_format({'bold': True, 'bg_color': '#1F4E78', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
            hdr_month_fmt = workbook.add_format({'bold': True, 'bg_color': '#2E75B6', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
            hdr_tot_fmt = workbook.add_format({'bold': True, 'bg_color': '#70AD47', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
            hdr_ded_fmt = workbook.add_format({'bold': True, 'bg_color': '#C55A11', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
            hdr_er_fmt = workbook.add_format({'bold': True, 'bg_color': '#548235', 'font_color': '#FFFFFF', 'border': 1, 'align': 'center', 'valign': 'vcenter'})

            num_fmt = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
            text_fmt = workbook.add_format({'border': 1})
            total_fmt = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'bg_color': '#D9E1F2', 'border': 1})
            total_text_fmt = workbook.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1})

            # SHEET 1: Yearly Summary Matrix
            sheet_sum = workbook.add_worksheet('Yearly Summary')
            sheet_sum.write(0, 0, f"YEARLY SALARY SUMMARY BY EMPLOYEE — {self.year}", title_fmt)
            sheet_sum.write(1, 0, f"Company: {self.company_id.name} | Generated: {fields.Date.today()}", sub_title_fmt)

            # Explicit column widths to prevent ### overflow on currency amounts and long names
            sheet_sum.set_column(0, 0, 12)       # Emp Ref
            sheet_sum.set_column(1, 1, 24)       # Employee Name
            sheet_sum.set_column(2, 2, 20)       # Department
            sheet_sum.set_column(3, 3, 20)       # Job Position
            sheet_sum.set_column(4, 15, 15)      # Monthly Net Pays (Jan - Dec)
            sheet_sum.set_column(16, 19, 18)     # Annual Gross, Deductions, Net Pay, CTC

            sum_headers = ['Emp Ref', 'Employee Name', 'Department', 'Job Position'] + MONTH_NAMES + ['Annual Gross', 'Annual Deductions', 'Annual Net Pay', 'Annual CTC']
            for col_idx, h_text in enumerate(sum_headers):
                fmt = hdr_main_fmt if col_idx < 4 else (hdr_tot_fmt if col_idx >= 16 else hdr_month_fmt)
                sheet_sum.write(3, col_idx, h_text, fmt)

            sum_row = 4
            for s_row in yearly_data['summary_rows']:
                sheet_sum.write(sum_row, 0, s_row['emp_ref'], text_fmt)
                sheet_sum.write(sum_row, 1, s_row['emp_name'], text_fmt)
                sheet_sum.write(sum_row, 2, s_row['department'], text_fmt)
                sheet_sum.write(sum_row, 3, s_row['job_position'], text_fmt)
                for m_idx, m_net in enumerate(s_row['months']):
                    sheet_sum.write(sum_row, 4 + m_idx, m_net, num_fmt)
                sheet_sum.write(sum_row, 16, s_row['ann_gross'], num_fmt)
                sheet_sum.write(sum_row, 17, s_row['ann_ded'], num_fmt)
                sheet_sum.write(sum_row, 18, s_row['ann_net'], num_fmt)
                sheet_sum.write(sum_row, 19, s_row['ann_ctc'], num_fmt)
                sum_row += 1

            # Total row on Summary sheet
            sheet_sum.write(sum_row, 0, "TOTAL", total_text_fmt)
            for c in range(1, 4):
                sheet_sum.write(sum_row, c, "", total_text_fmt)
            for c, tot_val in enumerate(yearly_data['annual_totals']):
                sheet_sum.write(sum_row, 4 + c, tot_val, total_fmt)

            # SHEET 2: Month-by-Month Component Breakdown Details
            sheet_dtl = workbook.add_worksheet('Detailed Breakdown')
            sheet_dtl.write(0, 0, f"YEARLY SALARY DETAILED BREAKDOWN — {self.year}", title_fmt)

            # Explicit column widths to prevent ### overflow on currency amounts and long names
            sheet_dtl.set_column(0, 0, 12)       # Emp Ref
            sheet_dtl.set_column(1, 1, 24)       # Employee Name
            sheet_dtl.set_column(2, 2, 20)       # Department
            sheet_dtl.set_column(3, 3, 12)       # Month
            sheet_dtl.set_column(4, 4, 22)       # Salary Structure
            sheet_dtl.set_column(5, 8, 15)       # Basic, HRA, Allowances, Other Earnings
            sheet_dtl.set_column(9, 9, 18)       # Gross Salary
            sheet_dtl.set_column(10, 15, 15)     # EE PF, EE ESI, PT, LWF, TDS, Other Ded.
            sheet_dtl.set_column(16, 17, 18)     # Total Deductions, Net Pay
            sheet_dtl.set_column(18, 21, 18)     # Employer EPS, EPF Share, Admin & Total PF
            sheet_dtl.set_column(22, 24, 16)     # Employer ESI, LWF, Other Contrib.
            sheet_dtl.set_column(25, 25, 20)     # Total Employer Cost (CTC)

            dtl_headers = [
                'Emp Ref', 'Employee Name', 'Department', 'Month', 'Salary Structure',
                'Basic', 'HRA', 'Allowances', 'Other Earnings', 'Gross Salary',
                'EE PF', 'EE ESI', 'PT', 'LWF', 'TDS', 'Other Ded.', 'Total Deductions',
                'Net Pay', 'Employer EPS (8.33%)', 'Employer EPF Share (3.67%)', 'EPF Admin & EDLI (1.0%)',
                'Total Employer PF', 'Employer ESI (3.25%)', 'Employer LWF', 'Other Employer Contrib.', 'Total Employer Cost (CTC)'
            ]
            for col_idx, h_text in enumerate(dtl_headers):
                fmt = hdr_main_fmt if col_idx < 5 else (hdr_ded_fmt if 10 <= col_idx <= 16 else (hdr_er_fmt if 18 <= col_idx <= 24 else (hdr_tot_fmt if col_idx in (9, 17, 25) else hdr_month_fmt)))
                sheet_dtl.write(2, col_idx, h_text, fmt)

            d_row = 3
            for d in yearly_data['detail_rows']:
                sheet_dtl.write(d_row, 0, d['emp_ref'], text_fmt)
                sheet_dtl.write(d_row, 1, d['emp_name'], text_fmt)
                sheet_dtl.write(d_row, 2, d['department'], text_fmt)
                sheet_dtl.write(d_row, 3, d['month'], text_fmt)
                sheet_dtl.write(d_row, 4, d['struct_name'], text_fmt)

                sheet_dtl.write(d_row, 5, d['basic'], num_fmt)
                sheet_dtl.write(d_row, 6, d['hra'], num_fmt)
                sheet_dtl.write(d_row, 7, d['allowances'], num_fmt)
                sheet_dtl.write(d_row, 8, d['other_earnings'], num_fmt)
                sheet_dtl.write(d_row, 9, d['gross'], num_fmt)

                sheet_dtl.write(d_row, 10, d['pf_ee'], num_fmt)
                sheet_dtl.write(d_row, 11, d['esi_ee'], num_fmt)
                sheet_dtl.write(d_row, 12, d['pt'], num_fmt)
                sheet_dtl.write(d_row, 13, d['lwf_ee'], num_fmt)
                sheet_dtl.write(d_row, 14, d['tds'], num_fmt)
                sheet_dtl.write(d_row, 15, d['other_deductions'], num_fmt)
                sheet_dtl.write(d_row, 16, d['total_deductions'], num_fmt)

                sheet_dtl.write(d_row, 17, d['net_pay'], num_fmt)

                sheet_dtl.write(d_row, 18, d['pf_er_eps'], num_fmt)
                sheet_dtl.write(d_row, 19, d['pf_er_share'], num_fmt)
                sheet_dtl.write(d_row, 20, d['pf_er_admin'], num_fmt)
                sheet_dtl.write(d_row, 21, d['pf_er'], num_fmt)
                sheet_dtl.write(d_row, 22, d['esi_er'], num_fmt)
                sheet_dtl.write(d_row, 23, d['lwf_er'], num_fmt)
                sheet_dtl.write(d_row, 24, d['other_er_contrib'], num_fmt)
                sheet_dtl.write(d_row, 25, d['total_employer_cost'], num_fmt)

                d_row += 1

            workbook.close()
            output.seek(0)
            xlsx_content = output.read()
        else:
            xlsx_content = b"Excel export requires xlsxwriter library."

        try:
            from odoo.tools import BinaryBytes# pyrefly: ignore [missing-import]
            file_data = BinaryBytes(xlsx_content, filename=filename)
        except Exception:
            file_data = base64.b64encode(xlsx_content).decode('utf-8')

        self.write({
            'state': 'generated',
            'xlsx_file': file_data,
            'xlsx_filename': filename,
            'record_count': len(yearly_data.get('summary_rows', [])),
            'total_annual_gross': round(yearly_data['annual_totals'][12], 2),
            'total_annual_deductions': round(yearly_data['annual_totals'][13], 2),
            'total_annual_net': round(yearly_data['annual_totals'][14], 2),
            'total_annual_cost': round(yearly_data['annual_totals'][15], 2),
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=xlsx_file&filename_field=xlsx_filename&download=true',
            'target': 'self',
        }

    action_export_xlsx = action_print_xlsx

    def action_download_xlsx(self):
        self.ensure_one()
        if not self.xlsx_file:
            return self.action_print_xlsx()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/?model={self._name}&id={self.id}&field=xlsx_file&filename_field=xlsx_filename&download=true',
            'target': 'self',
        }

