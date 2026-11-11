# -*- coding: utf-8 -*-
import calendar
import logging
import threading
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrPayslipRun(models.Model):
    """Batch processing of multiple payslips for a given pay cycle with Department & Payment Advice support."""
    _name = 'hr.payslip.run'
    _inherit = ['mail.thread']
    _description = 'Payslip Batches / Pay Runs'
    _order = 'date_end desc, id desc'

    name = fields.Char(string='Batch Name', required=True, tracking=True)
    number = fields.Char(string='Reference', copy=False, readonly=True)
    date_start = fields.Date(
        string='Date From',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1)
    )
    date_end = fields.Date(
        string='Date To',
        required=True,
        default=lambda self: (datetime.now() + relativedelta(months=+1, day=1, days=-1)).date()
    )

    @api.onchange('date_start')
    def _onchange_date_start(self):
        if self.date_start:
            last_day = calendar.monthrange(self.date_start.year, self.date_start.month)[1]
            self.date_end = self.date_start.replace(day=last_day)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('paid', 'Paid'),
        ('close', 'Done'),
    ], string='Status', index=True, readonly=True, copy=False, default='draft', tracking=True)
    active_stage = fields.Selection([
        ('employees', 'Employees'),
        ('time', 'Time'),
        ('attendances', 'Attendances'),
        ('payslips', 'Payslips'),
    ], string='Active Stage', default='employees', required=True)

    # Scoping & Filtering
    department_ids = fields.Many2many(
        'hr.department',
        'hr_payslip_run_department_rel',
        'run_id',
        'department_id',
        string='Departments',
        help="Filter pay run by department(s). Leave empty to process all departments."
    )
    employee_type_ids = fields.Many2many(
        'hr.employee.type',
        'hr_payslip_run_employee_type_rel',
        'run_id',
        'type_id',
        string='Employee Types',
        help="Filter pay run by employee types. Leave empty for all types."
    )
    struct_id = fields.Many2one(
        'hr.payroll.structure',
        string='Salary Structure',
        help="Specific salary structure override. Leave empty to use employee contract structure."
    )

    # Payment Advice Link
    company_partner_id = fields.Many2one(
        'res.partner',
        string='Company Partner',
        related='company_id.partner_id',
        readonly=True
    )
    company_bank_id = fields.Many2one(
        'res.partner.bank',
        string='Company Bank Account',
        domain="['|', ('partner_id', '=', company_partner_id), ('company_id', '=', company_id)]",
        check_company=True,
        compute='_compute_company_bank_id',
        store=True,
        readonly=False,
        help="Disbursing bank account of the company for this pay run batch."
    )
    advice_id = fields.Many2one(
        'hudson.payroll.payment.advice',
        string='Payment Advice',
        copy=False,
        ondelete='set null'
    )
    advice_count = fields.Integer(
        string='Payment Advice Count',
        compute='_compute_advice_count'
    )

    slip_ids = fields.One2many(
        'hr.payslip',
        'payslip_run_id',
        string='Payslips'
    )
    payslip_count = fields.Integer(
        string='Payslip Count',
        compute='_compute_counts'
    )
    employee_count = fields.Integer(
        string='Eligible Employees',
        compute='_compute_counts'
    )
    department_count = fields.Integer(
        string='Departments Count',
        compute='_compute_counts'
    )
    department_names = fields.Char(
        string='Department Scoping',
        compute='_compute_counts'
    )

    dep_summary_ids = fields.One2many(
        'hr.payslip.run.dep.summary',
        'payslip_run_id',
        string='Department Summaries'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )

    # Progress Milestones & Attendance Anomaly Detection
    has_duplicate_payslips = fields.Boolean(
        string='Has Duplicate Payslips',
        compute='_compute_duplicate_payslips',
        store=True,
    )
    duplicate_payslip_count = fields.Integer(
        string='Duplicate Payslip Count',
        compute='_compute_duplicate_payslips',
        store=True,
    )
    duplicate_employee_names = fields.Char(
        string='Duplicate Employees',
        compute='_compute_duplicate_payslips',
    )
    has_attendance_shortage = fields.Boolean(
        string='Has Attendance Shortage',
        compute='_compute_milestones',
        store=True,
    )
    attendance_shortage_hours = fields.Float(
        string='Attendance Shortage Hours',
        compute='_compute_milestones',
        store=True,
    )
    milestone_employees = fields.Boolean(
        string='Milestone: Employees',
        compute='_compute_milestones',
        store=True,
    )
    milestone_time = fields.Boolean(
        string='Milestone: Time',
        compute='_compute_milestones',
        store=True,
    )
    milestone_attendances = fields.Boolean(
        string='Milestone: Attendances',
        compute='_compute_milestones',
        store=True,
    )
    milestone_payslips = fields.Boolean(
        string='Milestone: Payslips',
        compute='_compute_milestones',
        store=True,
    )
    is_fully_achieved = fields.Boolean(
        string='Is Fully Achieved',
        compute='_compute_milestones',
        store=True,
        help="True only when all milestones are completed, all payslips are done/paid, and batch is closed/confirmed without attendance shortages."
    )
    period_summary_str = fields.Char(
        string='Period Summary',
        compute='_compute_period_summary_str',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        readonly=True
    )
    employer_cost_total = fields.Monetary(
        string='Employer Cost',
        compute='_compute_financial_totals',
        currency_field='currency_id',
        store=True
    )
    basic_wage_total = fields.Monetary(
        string='Basic Wage Total',
        compute='_compute_financial_totals',
        currency_field='currency_id',
        store=True
    )
    gross_wage_total = fields.Monetary(
        string='Gross',
        compute='_compute_financial_totals',
        currency_field='currency_id',
        store=True
    )
    net_wage_total = fields.Monetary(
        string='Net',
        compute='_compute_financial_totals',
        currency_field='currency_id',
        store=True
    )
    has_done_slips = fields.Boolean(
        string='Has Done Slips',
        compute='_compute_slips_status',
    )
    slips_all_done = fields.Boolean(
        string='All Payslips Done',
        compute='_compute_slips_status',
    )
    show_payment_advice_btn = fields.Boolean(
        string='Show Payment Advice Button',
        compute='_compute_slips_status',
    )
    stepper_html = fields.Html(
        string='Progress Stepper',
        compute='_compute_stepper_html',
        sanitize=False,
    )
    is_test_printed = fields.Boolean(
        string='Test Printed',
        default=False,
        copy=False,
    )
    show_validate_btn = fields.Boolean(
        string='Show Validate Button',
        compute='_compute_kanban_buttons',
    )
    show_test_print_btn = fields.Boolean(
        string='Show Test Print Button',
        compute='_compute_kanban_buttons',
    )

    @api.depends('state')
    def _compute_kanban_buttons(self):
        for run in self:
            # No Test Print step on the dashboard: every draft pay run can be validated directly
            run.show_validate_btn = run.state == 'draft'
            run.show_test_print_btn = False

    def _get_active_slips(self):
        """Payslips of this run that count towards totals and progress (cancelled ones are excluded)."""
        self.ensure_one()
        return self.slip_ids.filtered(lambda s: s.state != 'cancel')

    @api.depends('slip_ids.state', 'state', 'active_stage')
    def _compute_slips_status(self):
        for run in self:
            slips = run._get_active_slips()
            has_done = any(s.state in ('done', 'paid') for s in slips)
            all_done = bool(slips) and all(s.state in ('done', 'paid') for s in slips)
            run.has_done_slips = has_done
            run.slips_all_done = all_done
            run.show_payment_advice_btn = (has_done or run.state in ('confirmed', 'close')) and run.state not in ('draft', 'paid')

    @api.depends('slip_ids.basic_wage', 'slip_ids.gross_wage', 'slip_ids.net_wage', 'slip_ids.state', 'state')
    def _compute_financial_totals(self):
        for run in self:
            slips = run._get_active_slips()
            basic = sum(slips.mapped('basic_wage'))
            gross = sum(slips.mapped('gross_wage'))
            net = sum(slips.mapped('net_wage'))
            comp_lines = slips.line_ids.filtered(lambda l: l.category_id and l.category_id.code == 'COMP')
            comp = sum(comp_lines.mapped('total'))
            run.basic_wage_total = basic
            run.gross_wage_total = gross
            run.net_wage_total = net
            run.employer_cost_total = (gross + comp) if comp > 0 else (gross if gross > 0 else net)

    @api.depends('milestone_employees', 'milestone_time', 'milestone_attendances', 'milestone_payslips', 'has_attendance_shortage', 'active_stage', 'state')
    def _compute_stepper_html(self):
        for run in self:
            if run.state == 'paid':
                # Paid state: all circles & connectors turn rose/orchid with checkmark on Payslips (Matching Screenshot)
                c_rose = '#c084fc'
                arr_emp = '<div style="height: 13px;"></div>'
                arr_time = '<div style="height: 13px;"></div>'
                arr_att = '<div style="height: 13px;"></div>'
                arr_pay = f'<i class="fa fa-chevron-down" style="color: {c_rose}; font-size: 11px; margin-bottom: 2px;"></i>'

                emp_circle = f'<div style="width: 18px; height: 18px; border-radius: 50%; background-color: {c_rose};"></div>'
                time_circle = f'<div style="width: 18px; height: 18px; border-radius: 50%; background-color: {c_rose};"></div>'
                att_circle = f'<div style="width: 18px; height: 18px; border-radius: 50%; background-color: {c_rose};"></div>'
                pay_circle = f'<div style="width: 18px; height: 18px; border-radius: 50%; background-color: {c_rose}; display: flex; align-items: center; justify-content: center; color: #ffffff; font-size: 9px;"><i class="fa fa-check"></i></div>'

                c_conn1 = c_rose
                c_conn2 = c_rose
                c_conn3 = c_rose
            else:
                is_validated = run.state in ('confirmed', 'paid', 'close') or (bool(run.slip_ids) and all(s.state in ('done', 'paid') for s in run.slip_ids))
                has_actual_shortage = any(s.attendance_shortage_display not in ('Normal', False, '') for s in run.slip_ids) if run.slip_ids else False

                c_emp = '#22c55e' if run.milestone_employees else '#3b82f6'
                c_conn1 = '#22c55e' if run.milestone_time else '#3b82f6'
                c_time = '#22c55e' if run.milestone_time else '#3b82f6'
                c_conn2 = '#22c55e' if (run.milestone_attendances or (bool(run.slip_ids) and not has_actual_shortage)) else '#3b82f6'
                c_conn3 = '#22c55e' if run.milestone_payslips else '#3b82f6'
                c_payslips = '#22c55e' if run.milestone_payslips else '#3b82f6'

                # Chevron indicators matching Screenshots 2, 3, 4
                arr_emp = '<i class="fa fa-chevron-down" style="color: #c084fc; font-size: 11px; margin-bottom: 2px;"></i>' if run.active_stage == 'employees' else '<div style="height: 13px;"></div>'
                arr_time = '<i class="fa fa-chevron-down" style="color: #c084fc; font-size: 11px; margin-bottom: 2px;"></i>' if run.active_stage == 'time' else '<div style="height: 13px;"></div>'
                arr_att = '<i class="fa fa-chevron-down" style="color: #c084fc; font-size: 11px; margin-bottom: 2px;"></i>' if run.active_stage == 'attendances' else '<div style="height: 13px;"></div>'
                arr_pay = '<i class="fa fa-chevron-down" style="color: #c084fc; font-size: 11px; margin-bottom: 2px;"></i>' if run.active_stage == 'payslips' else '<div style="height: 13px;"></div>'

                emp_circle = f'<div style="width: 18px; height: 18px; border-radius: 50%; background-color: {c_emp};"></div>'
                time_circle = f'<div style="width: 18px; height: 18px; border-radius: 50%; background-color: {c_time};"></div>'

                if has_actual_shortage and not is_validated:
                    att_circle = '<div style="width: 18px; height: 18px; border-radius: 50%; border: 2px solid #f59e0b; color: #f59e0b; display: inline-flex; align-items: center; justify-content: center; font-size: 10px; font-weight: bold; background: transparent;" title="Attendance Shortage Anomaly">!</div>'
                elif (run.milestone_attendances or is_validated or not has_actual_shortage) and bool(run.slip_ids):
                    att_circle = '<div style="width: 18px; height: 18px; border-radius: 50%; background-color: #22c55e;"></div>'
                else:
                    att_circle = '<div style="width: 18px; height: 18px; border-radius: 50%; background-color: #3b82f6;"></div>'

                pay_circle = f'<div style="width: 18px; height: 18px; border-radius: 50%; background-color: {c_payslips};"></div>'

            run.stepper_html = f"""
            <div style="display: flex; align-items: center; justify-content: flex-start; font-family: inherit; margin: 0; padding: 0;">
                <div style="display: flex; flex-direction: column; align-items: center; width: 90px;">
                    {arr_emp}
                    {emp_circle}
                </div>
                <div style="width: 20px; height: 2px; background-color: {c_conn1}; margin-top: 21px;"></div>
                <div style="display: flex; flex-direction: column; align-items: center; width: 90px;">
                    {arr_time}
                    {time_circle}
                </div>
                <div style="width: 20px; height: 2px; background-color: {c_conn2}; margin-top: 21px;"></div>
                <div style="display: flex; flex-direction: column; align-items: center; width: 90px;">
                    {arr_att}
                    {att_circle}
                </div>
                <div style="width: 20px; height: 2px; background-color: {c_conn3}; margin-top: 21px;"></div>
                <div style="display: flex; flex-direction: column; align-items: center; width: 90px;">
                    {arr_pay}
                    {pay_circle}
                </div>
            </div>
            """

    @api.depends('date_start', 'date_end', 'payslip_count', 'employee_count')
    def _compute_period_summary_str(self):
        for run in self:
            count = run.payslip_count or run.employee_count or 0
            if run.date_start and run.date_end:
                now_year = fields.Date.today().year
                if run.date_start.year != now_year or run.date_end.year != now_year:
                    d_start = run.date_start.strftime("%d %b %Y").lstrip("0")
                    d_end = run.date_end.strftime("%d %b %Y").lstrip("0")
                else:
                    d_start = run.date_start.strftime("%d %b").lstrip("0")
                    d_end = run.date_end.strftime("%d %b").lstrip("0")
            else:
                d_start = ""
                d_end = ""
            emp_label = _("Employees")
            run.period_summary_str = f"{d_start} \u2192 {d_end} | {count} {emp_label}"

    @api.depends('slip_ids', 'slip_ids.state', 'slip_ids.worked_days_line_ids', 'slip_ids.contract_id.pay_by_attendance', 'slip_ids.attendance_shortage_display', 'state')
    def _compute_milestones(self):
        for run in self:
            slips = run._get_active_slips()
            # 1. Employees milestone
            run.milestone_employees = bool(slips or run.employee_count > 0)

            # 2. Time milestone (worked days calculated or run confirmed)
            has_worked_days = any(bool(slip.worked_days_line_ids) for slip in slips) if slips else False
            run.milestone_time = has_worked_days or (bool(slips) and run.state in ('confirmed', 'paid', 'close'))

            # 3. Attendances & Shortage Anomaly
            is_validated = run.state in ('confirmed', 'paid', 'close') or (bool(slips) and all(s.state in ('done', 'paid') for s in slips))
            has_anomaly = any(s.attendance_shortage_display not in ('Normal', False, '') for s in slips) if slips else False
            total_shortage = 0.0
            for slip in slips:
                # Fixed-salary employees do not dock pay on attendance shortages and are not treated as anomalies
                is_pay_by_att = getattr(slip.contract_id, 'pay_by_attendance', False)
                if not is_pay_by_att:
                    continue
                shortage_lines = slip.worked_days_line_ids.filtered(lambda l: l.code == 'SHORTAGE' and l.number_of_hours > 0)
                if shortage_lines:
                    total_shortage += sum(shortage_lines.mapped('number_of_hours'))
                elif hasattr(slip, 'attendance_discrepancy_hours') and slip.attendance_discrepancy_hours < -0.01:
                    total_shortage += abs(slip.attendance_discrepancy_hours)

            run.attendance_shortage_hours = total_shortage
            run.has_attendance_shortage = has_anomaly and not is_validated

            # Attendances dot is filled (GREEN) if slips exist AND (no shortage OR validated)
            run.milestone_attendances = bool(slips) and (is_validated or not run.has_attendance_shortage)

            # 4. Payslips milestone (all payslips done or paid)
            has_done_slips = bool(slips) and all(s.state in ('done', 'paid') for s in slips)
            run.milestone_payslips = has_done_slips or (bool(slips) and run.state in ('confirmed', 'paid', 'close'))

            # Fully Achieved = batch is confirmed/paid/close or all slips done, AND no attendance shortage!
            run.is_fully_achieved = bool(slips) and (run.state in ('confirmed', 'paid', 'close') or has_done_slips) and not run.has_attendance_shortage

    @api.depends('slip_ids.has_duplicate_payslip', 'slip_ids.state')
    def _compute_duplicate_payslips(self):
        for run in self:
            dup_slips = run.slip_ids.filtered(lambda s: s.has_duplicate_payslip and s.state != 'cancel')
            run.has_duplicate_payslips = bool(dup_slips)
            run.duplicate_payslip_count = len(dup_slips)
            if dup_slips:
                emp_names = list(dict.fromkeys(dup_slips.mapped('employee_id.name')))
                run.duplicate_employee_names = ", ".join(emp_names[:5]) + ("..." if len(emp_names) > 5 else "")
            else:
                run.duplicate_employee_names = False

    @api.depends('advice_id')
    def _compute_advice_count(self):
        for run in self:
            count = self.env['hudson.payroll.payment.advice'].search_count([('payslip_run_id', '=', run.id)])
            run.advice_count = count if count else (1 if run.advice_id else 0)

    @api.depends('company_id')
    def _compute_company_bank_id(self):
        for run in self:
            if not run.company_bank_id and run.company_id:
                company = run.company_id
                bank_acc = company.partner_id.bank_ids and company.partner_id.bank_ids.filtered(lambda b: not b.company_id or b.company_id == company)[:1] or False
                if not bank_acc:
                    bank_acc = self.env['res.partner.bank'].search([
                        '|', ('partner_id', '=', company.partner_id.id), ('company_id', '=', company.id),
                    ], limit=1)
                run.company_bank_id = bank_acc

    def _get_eligible_employees_domain(self):
        self.ensure_one()
        domain = [
            ('company_id', '=', self.company_id.id),
            ('active', '=', True)
        ]
        if self.department_ids:
            domain.append(('department_id', 'in', self.department_ids.ids))
        if self.employee_type_ids:
            reg_type = self.env['hr.employee.type'].search([('code', '=', 'EMP')], limit=1)
            if reg_type and reg_type.id in self.employee_type_ids.ids:
                domain.append('|')
                domain.append(('employee_type_id', 'in', self.employee_type_ids.ids))
                domain.append(('employee_type_id', '=', False))
            else:
                domain.append(('employee_type_id', 'in', self.employee_type_ids.ids))
        return domain

    @api.depends('slip_ids', 'slip_ids.state', 'department_ids', 'employee_type_ids', 'company_id')
    def _compute_counts(self):
        for run in self:
            run.payslip_count = len(run._get_active_slips())
            domain = run._get_eligible_employees_domain()
            run.employee_count = self.env['hr.employee'].search_count(domain)
            run.department_count = len(run.department_ids) if run.department_ids else self.env['hr.department'].search_count([('company_id', '=', run.company_id.id)])
            if run.department_ids:
                run.department_names = ", ".join(run.department_ids.mapped('name'))
            else:
                run.department_names = _("All Departments")

    @api.onchange('department_ids', 'employee_type_ids')
    def _onchange_scoping_filters(self):
        """Immediately update counts and feedback when filters change in the form."""
        if self.company_id:
            domain = [
                ('company_id', '=', self.company_id.id),
                ('active', '=', True)
            ]
            if self.department_ids:
                domain.append(('department_id', 'in', self.department_ids.ids))
            if self.employee_type_ids:
                reg_type = self.env['hr.employee.type'].search([('code', '=', 'EMP')], limit=1)
                if reg_type and reg_type.id in self.employee_type_ids.ids:
                    domain.append('|')
                    domain.append(('employee_type_id', 'in', self.employee_type_ids.ids))
                    domain.append(('employee_type_id', '=', False))
                else:
                    domain.append(('employee_type_id', 'in', self.employee_type_ids.ids))
            self.employee_count = self.env['hr.employee'].search_count(domain)
            self.department_count = len(self.department_ids) if self.department_ids else self.env['hr.department'].search_count([('company_id', '=', self.company_id.id)])
            if self.department_ids:
                self.department_names = ", ".join(self.department_ids.mapped('name'))
            else:
                self.department_names = _("All Departments")

    def action_open_eligible_employees(self):
        self.ensure_one()
        domain = self._get_eligible_employees_domain()
        return {
            'name': _('Eligible Employees'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.employee',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': domain,
        }

    def action_open_departments(self):
        self.ensure_one()
        domain = [('id', 'in', self.department_ids.ids)] if self.department_ids else [('company_id', '=', self.company_id.id)]
        return {
            'name': _('Departments'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.department',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': domain,
        }

    def action_draft(self):
        return self.action_set_to_draft()

    def action_test_print(self):
        """Prints a test/sample payslip report for the first done payslip in this pay run (Draft state)."""
        self.ensure_one()
        self.write({'is_test_printed': True})
        # Find the first payslip with done/verify state for test print
        test_slip = self.slip_ids.filtered(lambda s: s.state in ('done', 'verify')) or self.slip_ids
        if not test_slip:
            raise UserError(_("No payslips found to print."))
        slip = test_slip[0]
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'res_id': slip.id,
            'target': 'current',
        }

    def action_generate_payslips(self):
        """Generates payslips for all eligible employees based on department and type filters."""
        self.ensure_one()
        domain = self._get_eligible_employees_domain()
        employees = self.env['hr.employee'].search(domain)
        if not employees:
            raise UserError(_("No eligible employees found for the specified department/type criteria."))

        # Existing employee IDs in batch to prevent duplication
        existing_emp_ids = self.slip_ids.mapped('employee_id.id')
        created_slips = self.env['hr.payslip']

        for emp in employees:
            if emp.id in existing_emp_ids:
                continue

            contract = False
            period_version = emp._hds_payroll_version(self.date_start, self.date_end)
            if period_version:
                c = period_version
                c_start = getattr(c, 'contract_date_start', False) or getattr(c, 'date_start', False)
                c_end = getattr(c, 'contract_date_end', False) or getattr(c, 'date_end', False)
                if (not c_start or c_start <= self.date_end) and (not c_end or c_end >= self.date_start):
                    contract = c

            if not contract:
                domain = [('employee_id', '=', emp.id)]
                if 'contract_date_start' in self.env['hr.version']._fields:
                    domain += [
                        '|', ('contract_date_start', '=', False), ('contract_date_start', '<=', self.date_end),
                        '|', ('contract_date_end', '=', False), ('contract_date_end', '>=', self.date_start),
                    ]
                contract = self.env['hr.version'].search(domain, limit=1, order='id desc')

            if not contract and period_version:
                contract = period_version

            if not contract:
                continue

            struct = self.struct_id or getattr(contract, 'struct_id', False)
            if not struct and hasattr(contract, 'structure_type_id') and contract.structure_type_id:
                struct = contract.structure_type_id.default_struct_id or self.env['hr.payroll.structure'].search([
                    ('type_id', '=', contract.structure_type_id.id)
                ], limit=1)

            if not struct:
                continue

            slip = self.env['hr.payslip'].create({
                'name': _('Salary Slip - %(emp)s - %(period)s') % {
                    'emp': emp.name,
                    'period': self.date_start.strftime('%B %Y')
                },
                'employee_id': emp.id,
                'contract_id': contract.id,
                'struct_id': struct.id,
                'date_from': self.date_start,
                'date_to': self.date_end,
                'payslip_run_id': self.id,
                'company_id': self.company_id.id,
            })
            slip._populate_worked_days()
            slip._populate_inputs()
            created_slips |= slip

        if created_slips:
            self.action_compute_all()

        dup_slips = self.slip_ids.filtered(lambda s: s.has_duplicate_payslip and s.state != 'cancel')
        if dup_slips:
            emp_names = ", ".join(list(dict.fromkeys(dup_slips.mapped('employee_id.name'))))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Warning: Duplicate Payslips Detected"),
                    'message': _(
                        "This pay run includes %(count)s employee(s) for whom a payslip was already generated for this month: %(emps)s.\n\n"
                        "They have been flagged as 'Duplicate' in this pay run."
                    ) % {
                        'count': len(dup_slips),
                        'emps': emp_names,
                    },
                    'type': 'warning',
                    'sticky': False,
                    'autocloseDelay': 5000,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }

        return True

    def action_compute_all(self, batch_size=50):
        """Batch compute all draft/verify payslips in this run with chunking and error isolation."""
        self.ensure_one()
        slips_to_compute = self.slip_ids.filtered(lambda s: s.state in ('draft', 'verify'))
        if not slips_to_compute:
            self._compute_department_summaries()
            self._compute_financial_totals()
            self._compute_milestones()
            return True

        total_slips = len(slips_to_compute)
        is_test_mode = (
            getattr(threading.current_thread(), 'testing', False)
            or getattr(self.env.registry, 'test_mode', False)
            or bool(self.env.context.get('test_mode'))
            or hasattr(self.env.cr, 'restore_cursor')
        )

        for offset in range(0, total_slips, batch_size):
            chunk = slips_to_compute[offset:offset + batch_size]
            for slip in chunk:
                try:
                    with self.env.cr.savepoint():
                        slip.with_context(no_statutory_audit=True).compute_sheet()
                except Exception as exc:
                    _logger.warning("Payslip computation warning for employee %s: %s", slip.employee_id.name, exc)
                    try:
                        slip.write({
                            'payslip_warning': _("Calculation Warning: %s") % str(exc)
                        })
                    except Exception:
                        pass

            if not is_test_mode:
                self.env.cr.commit()
                self.env.invalidate_all()

        self._compute_department_summaries()
        self._compute_financial_totals()
        self._compute_milestones()
        if not is_test_mode:
            self.env.cr.commit()
        return True

    def action_confirm_payrun(self):
        """Confirms batch, computes department summaries, and moves state to confirmed."""
        self.ensure_one()
        if not self.slip_ids:
            raise UserError(_("No payslips found in this batch to confirm."))

        if not self.number:
            self.number = self.env['ir.sequence'].next_by_code('hr.payslip.run') or _('New')

        for slip in self.slip_ids.filtered(lambda s: s.state != 'done'):
            try:
                with self.env.cr.savepoint():
                    slip.action_payslip_done()
            except Exception as exc:
                _logger.warning("Could not finalize payslip for %s: %s", slip.employee_id.name, exc)
                slip.write({'payslip_warning': _("Confirmation Issue: %s") % str(exc)})

        self._compute_department_summaries()
        return self.write({'state': 'confirmed'})

    def action_generate_payment_advice(self):
        """Generates Bank Payment Advice for all confirmed payslips in this batch."""
        self.ensure_one()
        if not self.slip_ids:
            raise UserError(_("No payslips to generate payment advice for."))
        payable_slips = self._get_payable_slips()

        slips_missing_bank = payable_slips.filtered(
            lambda s: not (s.bank_account_id or (s.employee_id and s.employee_id.bank_account_id))
        )
        if slips_missing_bank:
            emp_list = "\n • ".join(slips_missing_bank.mapped('employee_id.name'))
            raise UserError(_(
                "Payment Advice cannot be created!\n\n"
                "The following employee(s) do not have a bank account configured:\n"
                " • %(employees)s\n\n"
                "Please configure bank account details for these employee(s) before generating Payment Advice."
            ) % {'employees': emp_list})

        bank_acc = self.company_bank_id
        if not bank_acc:
            company = self.company_id or self.env.company
            bank_acc = company.partner_id.bank_ids and company.partner_id.bank_ids.filtered(lambda b: not b.company_id or b.company_id == company)[:1] or False
            if not bank_acc:
                bank_acc = self.env['res.partner.bank'].search([
                    '|', ('partner_id', '=', company.partner_id.id), ('company_id', '=', company.id),
                ], limit=1)
            if bank_acc:
                self.company_bank_id = bank_acc

        advice = self.advice_id
        if not advice:
            advice = self.env['hudson.payroll.payment.advice'].create({
                'payslip_run_id': self.id,
                'date': fields.Date.today(),
                'company_id': self.company_id.id,
                'company_bank_id': self.company_bank_id.id if self.company_bank_id else False,
            })
            self.advice_id = advice
        else:
            if self.company_bank_id and not advice.company_bank_id:
                advice.company_bank_id = self.company_bank_id.id

        # Build lines
        lines_vals = []
        for slip in payable_slips:
            net_amt = slip.net_wage or sum(l.total for l in slip.line_ids if l.category_id.code == 'NET')
            lines_vals.append((0, 0, {
                'payslip_id': slip.id,
                'employee_id': slip.employee_id.id,
                'net_amount': net_amt,
            }))

        advice.line_ids = [(5, 0, 0)] + lines_vals
        return self.action_view_payment_advice()

    def _get_payable_slips(self):
        """Validated (or already paid) payslips of this run that can go into a payment.

        Cancelled payslips are ignored. Draft / to-verify payslips block payment so that
        nobody is paid on an unvalidated (or failed) payslip.
        """
        self.ensure_one()
        slips = self.slip_ids.filtered(lambda s: s.state != 'cancel')
        pending = slips.filtered(lambda s: s.state in ('draft', 'verify'))
        if pending:
            raise UserError(_(
                "Cannot process payment: the following payslip(s) are not validated yet:\n • %(employees)s\n\n"
                "Validate or cancel them before paying this pay run."
            ) % {'employees': "\n • ".join(pending.mapped('employee_id.name'))})
        payable = slips.filtered(lambda s: s.state in ('done', 'paid'))
        if not payable:
            raise UserError(_("There are no validated payslips to pay in this pay run."))
        return payable

    def action_pay_payrun(self):
        """Marks pay run as paid."""
        self.ensure_one()
        payable_slips = self._get_payable_slips()
        slips_missing_bank = payable_slips.filtered(
            lambda s: not (s.bank_account_id or (s.employee_id and s.employee_id.bank_account_id))
        )
        if slips_missing_bank:
            emp_list = "\n • ".join(slips_missing_bank.mapped('employee_id.name'))
            raise UserError(_(
                "Cannot mark as Paid!\n\n"
                "The following employee(s) do not have a bank account configured:\n"
                " • %(employees)s\n\n"
                "Please configure bank account details for these employee(s) before proceeding."
            ) % {'employees': emp_list})
        payable_slips.action_payslip_paid()
        return self.write({'state': 'paid'})

    def unlink(self):
        for run in self:
            if run.state != 'draft':
                raise UserError(_(
                    "You cannot delete the pay run '%(name)s' because it is in '%(state)s' state.\n\n"
                    "Only pay runs in 'Draft' state can be deleted. "
                    "If you need to delete this pay run, please reset it to Draft first."
                ) % {
                    'name': run.name or '',
                    'state': dict(run._fields['state'].selection).get(run.state, run.state),
                })

            # Clean up child payslips
            for slip in run.slip_ids:
                if slip.state not in ('draft', 'cancel'):
                    slip.write({'state': 'draft'})
            run.slip_ids.unlink()

            # Clean up department summaries
            if run.dep_summary_ids:
                run.dep_summary_ids.unlink()

            # Clean up payment advice
            advices = self.env['hudson.payroll.payment.advice'].search([('payslip_run_id', '=', run.id)])
            if advices:
                advices.unlink()
        return super().unlink()

    def action_delete_payrun(self):
        """Permanently deletes this entire pay run and all its associated records, redirecting back to Pay Runs list."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_(
                "You cannot delete the pay run '%(name)s' because it is in '%(state)s' state.\n\n"
                "Only pay runs in 'Draft' state can be deleted. "
                "If you need to delete this pay run, please reset it to Draft first."
            ) % {
                'name': self.name or '',
                'state': dict(self._fields['state'].selection).get(self.state, self.state),
            })
        self.unlink()
        return self.env['ir.actions.act_window']._for_xml_id('hudson_payroll_base.action_hr_payslip_run')

    def action_close(self):
        """Aliases to action_delete_payrun so clicking Delete permanently deletes the pay run."""
        return self.action_delete_payrun()

    def action_set_stage_employees(self):
        self.ensure_one()
        self.active_stage = 'employees'

    def action_set_stage_time(self):
        self.ensure_one()
        self.active_stage = 'time'

    def action_set_stage_attendances(self):
        self.ensure_one()
        self.active_stage = 'attendances'

    def action_set_stage_payslips(self):
        self.ensure_one()
        self.active_stage = 'payslips'

    def action_stage_continue(self):
        self.ensure_one()
        stages = ['employees', 'time', 'attendances', 'payslips']
        curr_idx = stages.index(self.active_stage) if self.active_stage in stages else 0
        if curr_idx < len(stages) - 1:
            self.active_stage = stages[curr_idx + 1]
        elif self.active_stage == 'payslips':
            return self.action_batch_validate()
        return True

    def action_batch_validate(self):
        """Validates all payslips, marks payrun confirmed, and opens the individual payslips view (Screenshot 1)."""
        self.ensure_one()
        # Duplicate payslip interception popup
        if not self.env.context.get('skip_duplicate_check'):
            dup_slips = self.slip_ids.filtered(lambda s: s.has_duplicate_payslip and s.state in ('draft', 'verify'))
            if dup_slips:
                wizard = self.env['hr.payslip.run.duplicate.wizard'].create({
                    'payslip_run_id': self.id,
                    'duplicate_slip_ids': [(6, 0, dup_slips.ids)],
                })
                return {
                    'name': _('Duplicate Payslips Detected - Warning'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'hr.payslip.run.duplicate.wizard',
                    'view_mode': 'form',
                    'views': [(False, 'form')],
                    'res_id': wizard.id,
                    'target': 'new',
                }

        if not self._get_active_slips():
            raise UserError(_("There are no payslips to validate in this pay run."))

        failures = []
        for slip in self.slip_ids:
            if slip.state in ('draft', 'verify'):
                try:
                    with self.env.cr.savepoint():
                        slip.action_payslip_done()
                except Exception as exc:
                    _logger.warning("Could not validate payslip for %s: %s", slip.employee_id.name, exc)
                    reason = (exc.args[0] if exc.args else str(exc)) or exc.__class__.__name__
                    reason = str(reason).strip().lstrip('•').strip()
                    failures.append((slip, reason))
                    slip.write({'payslip_warning': _("Validation Error: %s") % reason})

        if failures:
            # Keep the run in Draft so the remaining payslips can be fixed and validated again
            self._compute_department_summaries()
            self._compute_milestones()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Pay run not validated"),
                    'message': _(
                        "%(count)s payslip(s) could not be validated, so the pay run stays in Draft:\n%(details)s\n\n"
                        "Fix these payslips and click Validate again; payslips already validated are kept."
                    ) % {
                        'count': len(failures),
                        'details': "\n".join(
                            f"• {slip.employee_id.name}: {reason}" for slip, reason in failures
                        ),
                    },
                    'type': 'danger',
                    'sticky': True,
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }

        if not self.number:
            self.number = self.env['ir.sequence'].next_by_code('hr.payslip.run') or _('New')
        self.write({
            'state': 'confirmed',
            'active_stage': 'payslips',
        })
        self._compute_department_summaries()
        self._compute_milestones()
        return True

    def action_open_duplicate_payslips(self):
        """Filters payslips with duplicate warning in this pay run."""
        self.ensure_one()
        dup_slips = self.slip_ids.filtered(lambda s: s.has_duplicate_payslip and s.state != 'cancel')
        return {
            'name': _('Duplicate Payslips - %s') % (self.name or ''),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', (dup_slips or self.slip_ids).ids)],
            'context': {'default_payslip_run_id': self.id},
        }

    def action_remove_duplicate_payslips(self):
        """Removes all duplicate payslips from this pay run batch (Draft only)."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("You can only remove duplicate payslips when the pay run is in Draft state."))
        dup_slips = self.slip_ids.filtered(lambda s: s.has_duplicate_payslip and s.state != 'cancel')
        if dup_slips:
            dup_slips.unlink()
            self._compute_counts()
            self._compute_financial_totals()
            self._compute_milestones()
            self._compute_duplicate_payslips()
        return True

    def action_open_pay_wizard(self):
        """Opens the Pay wizard modal (Screenshot 4)."""
        self.ensure_one()
        if self.state == 'draft' and self.has_done_slips:
            if not self.number:
                self.number = self.env['ir.sequence'].next_by_code('hr.payslip.run') or _('New')
            self.write({'state': 'confirmed'})
        company = self.company_id or self.env.company
        bank_acc = self.company_bank_id
        if not bank_acc:
            bank_acc = company.partner_id.bank_ids and company.partner_id.bank_ids.filtered(lambda b: not b.company_id or b.company_id == company)[:1] or False
        if not bank_acc:
            bank_acc = self.env['res.partner.bank'].search([
                '|', ('partner_id', '=', company.partner_id.id), ('company_id', '=', company.id),
            ], limit=1)
        if bank_acc and not self.company_bank_id:
            self.company_bank_id = bank_acc

        wizard = self.env['hr.payslip.run.pay.wizard'].create({
            'payslip_run_id': self.id,
            'payment_date': fields.Date.today(),
            'report_name': f"Payment Advice - {self.name}",
            'company_bank_id': bank_acc.id if bank_acc else False,
            'mode': 'advice',
            'include_unpaid': True,
            'by_neft': True,
            'by_cheque': False,
        })
        return {
            'name': _('Pay'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.run.pay.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'res_id': wizard.id,
            'target': 'new',
            'context': {
                'active_id': self.id,
                'active_ids': [self.id],
                'active_model': 'hr.payslip.run',
                'default_payslip_run_id': self.id,
            },
        }

    def action_set_to_draft(self):
        """Reverts confirmed or paid pay run and all its non-cancelled child payslips back to draft."""
        for run in self:
            # 1. Revert child payslips
            slips_to_draft = run.slip_ids.filtered(lambda s: s.state != 'cancel')
            done_or_paid = slips_to_draft.filtered(lambda s: s.state in ('done', 'paid'))
            if done_or_paid:
                done_or_paid.action_payslip_cancel()

            # Ensure any accounting move entries are unposted and deleted
            for slip in slips_to_draft:
                if hasattr(slip, 'move_id') and slip.move_id:
                    move = slip.move_id
                    if move.state == 'posted':
                        move.button_draft()
                    move.unlink()

            # Restore salary adjustments
            for slip in slips_to_draft:
                for inp in slip.input_line_ids.filtered(lambda l: l.adjustment_id):
                    adj = inp.adjustment_id
                    if adj.state == 'done':
                        other_done = adj.payslip_input_ids.filtered(
                            lambda i: i.payslip_id.id not in slips_to_draft.ids and i.payslip_id.state in ('done', 'paid')
                        )
                        if not other_done:
                            adj.with_context(skip_adjustment_sync=True).write({'state': 'running'})

            slips_to_draft.write({'state': 'draft', 'paid': False})

            # Clean up payment advice associated with the batch
            advices = self.env['hudson.payroll.payment.advice'].search([('payslip_run_id', '=', run.id)])
            if advices:
                advices.unlink()

            # 2. Revert run state and refresh status & metrics
            run.write({'state': 'draft', 'is_test_printed': False})
            run._compute_kanban_buttons()
            run._compute_slips_status()
            run._compute_counts()
            run._compute_financial_totals()
            run._compute_milestones()
            run._compute_department_summaries()
        return True

    def action_revert_paid(self):
        """Reverts paid pay run back to confirmed state.

        Only paid payslips go back to validated; cancelled and draft payslips are left untouched.
        """
        self.ensure_one()
        self.slip_ids.filtered(lambda s: s.state == 'paid').write({'paid': False, 'state': 'done'})
        # The run is no longer paid, so its bank advice must be editable/regenerable again
        if self.advice_id and self.advice_id.state == 'confirmed':
            self.advice_id.action_set_to_draft()
        self.write({'state': 'confirmed', 'active_stage': 'payslips'})
        self._compute_department_summaries()
        self._compute_milestones()
        return True

    def action_open_warning_payslips(self):
        """Filters payslips with warnings (Matching Screenshot 5)."""
        self.ensure_one()
        slips_with_warnings = self.slip_ids.filtered(lambda s: s.payslip_warning)
        return {
            'name': _('Payslips with Warnings'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('id', 'in', (slips_with_warnings or self.slip_ids).ids)],
            'context': {'default_payslip_run_id': self.id},
        }

    def action_view_work_entries(self):
        """Opens Payslip Work Days Lines Report (Pivot & List) matching Odoo Online."""
        self.ensure_one()
        return {
            'name': _('Payslip Work Days Lines Report'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.worked.days',
            'view_mode': 'pivot,list',
            'views': [(False, 'pivot'), (False, 'list')],
            'domain': [('payslip_id.payslip_run_id', '=', self.id)],
            'context': {
                'search_default_group_code': 1,
                'default_payslip_run_id': self.id,
            },
        }

    def action_view_payroll_journal(self):
        """Opens Payslip Lines Report (Pivot & List) matching Odoo Online."""
        self.ensure_one()
        action = self.env.ref('hudson_payroll_base.action_hr_payslip_line_report').read()[0]
        action['name'] = _("Payroll Journal - %s") % self.name
        action['domain'] = [('slip_id.payslip_run_id', '=', self.id)]
        action['context'] = {
            'search_default_group_category': 1,
            'search_default_group_employee': 1,
            'default_payslip_run_id': self.id,
        }
        return action

    def action_view_payslip_lines(self):
        return self.action_view_payroll_journal()

    def action_recompute_payslips(self):
        """Re-computes all draft payslips in this pay run batch (same functionality as compute sheet)."""
        self.ensure_one()
        slips_to_compute = self.slip_ids.filtered(lambda s: s.state in ('draft', 'verify'))
        if not slips_to_compute:
            raise UserError(_("No draft payslips found in this pay run to recompute."))
        for slip in slips_to_compute:
            slip.compute_sheet()
        self._compute_department_summaries()
        self._compute_financial_totals()
        self._compute_milestones()
        self._compute_counts()
        self._compute_duplicate_payslips()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Payslips Recomputed'),
                'message': _('%d payslip(s) successfully recomputed.') % len(slips_to_compute),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_add_employees(self):
        """Opens wizard to add employees to this pay run batch."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Employees can only be added to a Pay Run in Draft state."))
        action = self.env.ref('hudson_payroll_base.action_hr_payslip_by_employees').read()[0]
        ctx = dict(self.env.context or {})
        ctx.update({
            'active_id': self.id,
            'active_ids': [self.id],
            'active_model': 'hr.payslip.run',
            'default_payslip_run_id': self.id,
        })
        action['context'] = ctx
        return action

    def action_delete_payrun(self):
        """Deletes the current pay run batch if in draft state."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("You can only delete a Pay Run in Draft state."))
        self.unlink()
        return {
            'name': _('Pay Runs'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.run',
            'view_mode': 'kanban,list,form',
            'views': [[False, 'kanban'], [False, 'list'], [False, 'form']],
            'target': 'current',
        }

    def action_open_draft_journal_entry(self):
        """Opens Draft Journal Entries for this pay run batch."""
        self.ensure_one()
        if hasattr(self, 'action_open_account_moves'):
            # If account module installed, ensure draft moves exist for computed slips
            for slip in self.slip_ids:
                if not slip.move_id and slip.line_ids:
                    try:
                        slip._create_account_move()
                    except Exception as e:
                        _logger.debug("Draft move creation for slip %s: %s", slip.id, e)
            move_ids = self.slip_ids.mapped('move_id').ids
            if move_ids:
                return {
                    'name': _('Journal Entry (Draft) - %s') % self.name,
                    'type': 'ir.actions.act_window',
                    'res_model': 'account.move',
                    'view_mode': 'list,form',
                    'domain': [('id', 'in', move_ids)],
                    'context': {'create': False, 'search_default_posted': 0},
                }
        move_ids = self.slip_ids.mapped('move_id').ids if hasattr(self.slip_ids, 'move_id') else []
        return {
            'name': _('Journal Entry (Draft) - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', move_ids)],
            'context': {'create': False},
        }

    def _compute_department_summaries(self):
        """Generates aggregate department summaries for this batch."""
        for run in self:
            dep_map = {}
            for slip in run._get_active_slips():
                dep = slip.employee_id.department_id
                dep_id = dep.id if dep else False
                if dep_id not in dep_map:
                    dep_map[dep_id] = {
                        'department_id': dep_id,
                        'employee_count': 0,
                        'gross_total': 0.0,
                        'net_total': 0.0,
                    }
                dep_map[dep_id]['employee_count'] += 1
                dep_map[dep_id]['gross_total'] += slip.gross_wage
                dep_map[dep_id]['net_total'] += slip.net_wage

            run.dep_summary_ids = [(5, 0, 0)] + [(0, 0, vals) for vals in dep_map.values()]

    def action_send_payslips_email(self):
        """Email each employee their own validated / paid payslip of the run, with the same template
        (and PDF) as the payslip's Send By Email; logged in each payslip's chatter. Employees without
        an email address are skipped and listed."""
        self.ensure_one()
        slips = self.slip_ids.filtered(lambda slip: slip.state in ('done', 'paid'))
        if not slips:
            raise UserError(_("This pay run has no validated or paid payslips to send."))
        template = self.env.ref('hudson_payroll_base.mail_template_payslip', raise_if_not_found=False)
        if not template:
            raise UserError(_("The email template 'Salary Slip: Send by Email' is missing."))
        without_email = slips.filtered(lambda slip: not slip.employee_id.work_contact_id.email)
        to_send = slips - without_email
        comment_subtype = self.env.ref('mail.mt_comment')
        for slip in to_send:
            # One payslip at a time, as its own Send By Email does: the employee is the recipient
            # and the template renders that payslip's PDF
            composer = self.env['mail.compose.message'].create({
                'composition_mode': 'comment',
                'model': 'hr.payslip',
                'res_ids': str(slip.ids),
                'template_id': template.id,
                'partner_ids': [(6, 0, slip.employee_id.work_contact_id.ids)],
                'message_type': 'comment',
                'subtype_id': comment_subtype.id,
            })
            composer._action_send_mail()
        message = _("%(count)s payslip(s) emailed to the employees.", count=len(to_send))
        if without_email:
            message += '\n' + _("Not sent (no email address on the employee): %s",
                                ', '.join(without_email.mapped('employee_id.name')))
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Send Payslips by Email'),
                'message': message,
                'type': 'warning' if without_email else 'success',
                'sticky': bool(without_email),
            },
        }

    def action_open_payslips(self):
        self.ensure_one()
        return {
            'name': self.name or _('Employee Payslips'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip',
            'view_mode': 'list,form',
            'views': [(self.env.ref('hudson_payroll_base.hr_payslip_view_list').id, 'list'), (False, 'form')],
            'domain': [('payslip_run_id', '=', self.id)],
            'context': {
                'default_payslip_run_id': self.id,
                'search_default_group_by_state': 0,
            },
        }

    def action_print_payslips(self):
        """Generate a single multi-page PDF containing all payslips in this pay run, 1 page per employee."""
        self.ensure_one()
        if not self.slip_ids:
            raise UserError(_("No payslips found in this pay run to print."))
        report = self.env.ref('hudson_payroll_base.action_report_payslip', raise_if_not_found=False)
        if report:
            ctx = dict(self.env.context)
            ctx.pop('active_id', None)
            ctx['active_model'] = 'hr.payslip'
            ctx['active_ids'] = self.slip_ids.ids
            return report.with_context(ctx).report_action(self.slip_ids)
        raise UserError(_("Payslip report action not found."))

    def action_view_payment_advice(self):
        self.ensure_one()
        advice = self.advice_id
        if not advice:
            advice = self.env['hudson.payroll.payment.advice'].search([('payslip_run_id', '=', self.id)], limit=1)
            if advice:
                self.advice_id = advice
        if not advice:
            raise UserError(_("No Payment Advice created yet."))
        return {
            'name': _('Payment Advice'),
            'type': 'ir.actions.act_window',
            'res_model': 'hudson.payroll.payment.advice',
            'view_mode': 'form',
            'res_id': advice.id,
        }
