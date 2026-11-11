# -*- coding: utf-8 -*-
import calendar
import pytz
from datetime import date, datetime, time
from dateutil.relativedelta import relativedelta
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError, ValidationError


class DummyInput:
    """Safe fallback for missing inputs or worked day lines in rule formulas."""
    def __init__(self):
        self.amount = 0.0
        self.number_of_days = 0.0
        self.number_of_hours = 0.0
        self.total = 0.0

    def __bool__(self):
        return False

    def __call__(self, *args, **kwargs):
        return self

    def __getattr__(self, name):
        return 0.0


class BrowsableObject:
    """Helper object for safe dot-notation access in salary rule formulas."""
    def __init__(self, dict_data):
        self._dict_data = dict_data

    def get(self, key, default=None):
        return self._dict_data.get(key, default)

    def keys(self):
        return self._dict_data.keys()

    def values(self):
        return self._dict_data.values()

    def items(self):
        return self._dict_data.items()

    def __getattr__(self, name):
        if name in self._dict_data:
            return self._dict_data[name]
        return DummyInput()

    def __getitem__(self, key):
        return self._dict_data.get(key, DummyInput())

    def __contains__(self, key):
        return key in self._dict_data

    def __iter__(self):
        return iter(self._dict_data)

    def __bool__(self):
        return bool(self._dict_data)


class CategoryAccumulator:
    """Accumulator for salary rule categories with automatic parent category rollups."""
    def __init__(self):
        self._totals = {}

    def add(self, category, amount):
        curr = category
        while curr:
            code = curr.code
            self._totals[code] = self._totals.get(code, 0.0) + amount
            curr = curr.parent_id

    def __getattr__(self, code):
        return self._totals.get(code, 0.0)

    def __getitem__(self, code):
        return self._totals.get(code, 0.0)

    def get(self, code, default=0.0):
        return self._totals.get(code, default)


class RuleResult:
    """Represents a computed rule result accessible via rules.<CODE>.total in formulas."""
    def __init__(self, amount=0.0, rate=100.0, quantity=1.0):
        self.amount = amount
        self.rate = rate
        self.quantity = quantity
        self.total = quantity * amount * rate / 100.0


class HrPayslip(models.Model):
    """Core Payslip Model for computing and managing individual employee salary sheets."""
    _name = 'hr.payslip'
    _inherit = ['mail.thread']
    _description = 'Pay Slip'
    _order = 'date_to desc, id desc'

    name = fields.Char(string='Payslip Name', required=True)
    number = fields.Char(string='Reference', copy=False, readonly=True, index=True)
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True,
        index=True
    )
    contract_id = fields.Many2one(
        'hr.version',
        string='Contract',
        required=True,
        tracking=True,
        index=True
    )
    struct_id = fields.Many2one(
        'hr.payroll.structure',
        string='Structure',
        required=True
    )
    date_from = fields.Date(
        string='Date From',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1)
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        default=lambda self: (datetime.now() + relativedelta(months=+1, day=1, days=-1)).date()
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('verify', 'Waiting'),
        ('done', 'Validated'),
        ('paid', 'Paid'),
        ('cancel', 'Rejected'),
    ], string='Status', default='draft', readonly=True, copy=False, tracking=True, index=True)

    employee_avatar = fields.Binary(
        related='employee_id.image_128',
        string='Avatar',
        readonly=True
    )
    payment_date = fields.Date(
        string='Payment Date',
        default=fields.Date.context_today
    )
    hds_in_payment_mode = fields.Many2one(
        'hds.payment.mode',
        string="Payment Mode",
        compute='_compute_hds_in_payment_mode',
        store=True,
        readonly=False,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help="Mode of salary disbursement for this payslip. Auto-populated from employee profile."
    )

    @api.depends('employee_id', 'employee_id.hds_in_payment_mode', 'company_id')
    def _compute_hds_in_payment_mode(self):
        for slip in self:
            emp_mode = slip.employee_id.hds_in_payment_mode if slip.employee_id else False
            if emp_mode:
                slip.hds_in_payment_mode = emp_mode
            elif not slip.hds_in_payment_mode:
                # Default to first active Bank Transfer mode if available (scoped to company or global)
                company = slip.company_id or self.env.company
                domain = [
                    ('code', '=', 'bank_transfer'),
                    ('active', '=', True),
                    '|', ('company_id', '=', False), ('company_id', '=', company.id),
                ]
                default_mode = self.env['hds.payment.mode'].search(domain, limit=1)
                slip.hds_in_payment_mode = default_mode or False

    @api.constrains('hds_in_payment_mode', 'company_id')
    def _check_hds_in_payment_mode_company(self):
        for slip in self:
            if slip.hds_in_payment_mode and slip.company_id and slip.hds_in_payment_mode.company_id:
                if slip.hds_in_payment_mode.company_id != slip.company_id:
                    raise ValidationError(_(
                        "The payment mode '%(mode)s' belongs to %(mode_company)s and cannot be used for a payslip in %(slip_company)s.",
                        mode=slip.hds_in_payment_mode.name,
                        mode_company=slip.hds_in_payment_mode.company_id.name,
                        slip_company=slip.company_id.name,
                    ))
    no_worked_days = fields.Boolean(
        string='No Worked Days',
        default=False,
        help="If checked, the worked days lines will not be computed for this payslip."
    )
    bank_account_id = fields.Many2one(
        'res.partner.bank',
        string='Bank Account',
        compute='_compute_bank_account_id',
        store=True,
        readonly=False
    )
    has_bank_account = fields.Boolean(
        string='Has Bank Account',
        compute='_compute_has_bank_account'
    )
    advice_id = fields.Many2one(
        'hudson.payroll.payment.advice',
        string='Payment Advice',
        readonly=True,
        copy=False,
    )
    effective_advice_id = fields.Many2one(
        'hudson.payroll.payment.advice',
        string='Effective Payment Advice',
        compute='_compute_effective_advice_id',
    )

    @api.depends('advice_id', 'payslip_run_id', 'payslip_run_id.advice_id')
    def _compute_effective_advice_id(self):
        for slip in self:
            slip.effective_advice_id = slip.advice_id or (slip.payslip_run_id and slip.payslip_run_id.advice_id) or False
    total_worked_days = fields.Float(
        string='Worked Days',
        compute='_compute_worked_days_totals',
        store=True
    )
    total_worked_hours = fields.Float(
        string='Worked Hours',
        compute='_compute_worked_days_totals',
        store=True
    )

    line_ids = fields.One2many(
        'hr.payslip.line',
        'slip_id',
        string='Payslip Lines'
    )
    worked_days_line_ids = fields.One2many(
        'hr.payslip.worked.days',
        'payslip_id',
        string='Worked Days Lines',
        copy=True
    )
    input_line_ids = fields.One2many(
        'hr.payslip.input',
        'payslip_id',
        string='Input Lines',
        copy=True
    )
    payslip_run_id = fields.Many2one(
        'hr.payslip.run',
        string='Batch / Payrun',
        copy=False,
        ondelete='cascade',
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]"
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        readonly=True
    )
    paid = fields.Boolean(
        string='Paid',
        compute='_compute_paid',
        store=True,
        readonly=True,
        copy=False
    )

    @api.depends('state')
    def _compute_paid(self):
        for slip in self:
            slip.paid = (slip.state == 'paid')
    note = fields.Text(string='Note', help="Add a note on the printed payslip.")
    credit_note = fields.Boolean(
        string='Credit Note',
        help="Indicates if this payslip is a refund of another payslip"
    )

    # Basic totals computed for list view and quick overview
    gross_wage = fields.Monetary(
        string='Gross Wage',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id'
    )
    net_wage = fields.Monetary(
        string='Net Wage',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id'
    )
    total_cost = fields.Monetary(
        string='Total Cost',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
        help="Employer cost = Gross Wage + Employer statutory contributions (PF, ESI, etc.)."
    )
    basic_wage = fields.Monetary(
        string='Basic Wage',
        compute='_compute_basic_wage',
        store=True,
        currency_field='currency_id',
        help="Basic wage computed from salary rule lines or contract basic salary."
    )
    payslip_warning = fields.Char(
        string='Warnings',
        compute='_compute_payslip_warning',
        store=True,
        help="Warnings such as attendance shortage, duplicate payslip, or zero net pay."
    )
    display_status = fields.Char(
        string='Status',
        compute='_compute_display_status',
        store=True,
        help="Display status badge for pay run list (Warning, Draft, Done, Paid, Cancelled)."
    )

    # Backward compatibility aliases
    gross_amount = fields.Monetary(
        string='Gross Amount',
        related='gross_wage',
        store=False,
        currency_field='currency_id',
        help="Alias for gross_wage for backward compatibility."
    )
    net_amount = fields.Monetary(
        string='Net Amount',
        related='net_wage',
        store=False,
        currency_field='currency_id',
        help="Alias for net_wage for backward compatibility."
    )

    # Related Contract Breakdown Fields for Views & Reporting
    contract_wage = fields.Monetary(related='contract_id.wage', string='Contract Wage', currency_field='currency_id', readonly=True)
    contract_basic_salary = fields.Monetary(related='contract_id.basic_salary', string='Contract Basic Salary', currency_field='currency_id', readonly=True)
    contract_hra = fields.Monetary(related='contract_id.hra', string='Contract HRA', currency_field='currency_id', readonly=True)
    contract_da = fields.Monetary(related='contract_id.da', string='Contract DA', currency_field='currency_id', readonly=True)
    contract_fixed_allowance = fields.Monetary(related='contract_id.fixed_allowance', string='Contract Fixed Allowance', currency_field='currency_id', readonly=True)

    # Multi-Stage Dynamic Display Fields
    contract_working_hours = fields.Char(
        string='Working Hours',
        compute='_compute_stage_metrics',
        store=True,
    )
    contract_start_date = fields.Date(
        string='Start Date',
        related='contract_id.date_start',
        readonly=True,
    )
    contract_end_date = fields.Date(
        string='Termination',
        related='contract_id.date_end',
        readonly=True,
    )
    contract_review = fields.Char(
        string='Review',
        compute='_compute_stage_metrics',
        store=True,
    )
    time_off_days = fields.Float(
        string='Time Off (Days)',
        compute='_compute_stage_metrics',
        store=True,
    )
    time_off_summary = fields.Char(
        string='Time Off Type',
        compute='_compute_stage_metrics',
        store=True,
    )
    total_scheduled_days = fields.Float(
        string='Scheduled Days',
        compute='_compute_stage_metrics',
        store=True,
        help="Total scheduled working days for the payslip period based on the working schedule."
    )
    attendance_expected_hours = fields.Float(
        string='Expected Hours',
        compute='_compute_stage_metrics',
        store=True,
    )
    attendance_shortage_display = fields.Char(
        string='Anomaly / Shortage',
        compute='_compute_stage_metrics',
        store=True,
    )
    has_no_running_contract = fields.Boolean(
        string='No Running Contract',
        compute='_compute_contract_status',
        store=True,
    )
    has_zero_or_negative_net = fields.Boolean(
        string='Zero or Negative Net',
        compute='_compute_contract_status',
        store=True,
    )
    has_duplicate_payslip = fields.Boolean(
        string='Duplicate / Overlapping Payslip',
        compute='_compute_duplicate_payslip',
        store=True,
    )
    duplicate_payslip_id = fields.Many2one(
        'hr.payslip',
        string='Conflicting Payslip',
        compute='_compute_duplicate_payslip',
        store=True,
    )

    @api.depends('employee_id', 'date_from', 'date_to', 'state')
    def _compute_duplicate_payslip(self):
        for slip in self:
            if not slip.employee_id or not slip.date_from or not slip.date_to or slip.state == 'cancel':
                slip.has_duplicate_payslip = False
                slip.duplicate_payslip_id = False
                continue

            # Query all non-cancelled payslips for this employee that overlap with this payslip's dates
            domain = [
                ('employee_id', '=', slip.employee_id.id),
                ('state', '!=', 'cancel'),
                ('date_from', '<=', slip.date_to),
                ('date_to', '>=', slip.date_from),
            ]
            if slip.company_id:
                domain.append(('company_id', '=', slip.company_id.id))
            slip_real_id = slip._origin.id if slip._origin else (slip.id if isinstance(slip.id, int) else False)
            if slip_real_id:
                domain.append(('id', '!=', slip_real_id))

            candidates = self.search(domain, order='create_date desc, id desc')
            if candidates:
                slip.has_duplicate_payslip = True
                slip.duplicate_payslip_id = candidates[0].id
            else:
                slip.has_duplicate_payslip = False
                slip.duplicate_payslip_id = False

    def action_open_duplicate_payslip(self):
        """Open the conflicting primary payslip from the duplicate banner."""
        self.ensure_one()
        if self.duplicate_payslip_id:
            return {
                'name': _('Conflicting Payslip - %s') % (self.duplicate_payslip_id.name or self.duplicate_payslip_id.number or ''),
                'type': 'ir.actions.act_window',
                'res_model': 'hr.payslip',
                'view_mode': 'form',
                'views': [[False, 'form']],
                'res_id': self.duplicate_payslip_id.id,
                'target': 'current',
            }
        return False

    @api.depends('employee_id', 'contract_id', 'contract_id.date_start', 'contract_id.date_end',
                 'contract_id.contract_date_start', 'contract_id.contract_date_end',
                 'date_from', 'date_to', 'state', 'line_ids', 'net_wage')
    def _compute_contract_status(self):
        for slip in self:
            no_contract = False
            if not slip.employee_id:
                no_contract = False
            elif not slip.contract_id:
                no_contract = True
            elif slip.date_from and slip.date_to:
                c_start = getattr(slip.contract_id, 'contract_date_start', False) or getattr(slip.contract_id, 'date_start', False)
                c_end = getattr(slip.contract_id, 'contract_date_end', False) or getattr(slip.contract_id, 'date_end', False)
                if c_start and c_start > slip.date_to:
                    no_contract = True
                elif c_end and c_end < slip.date_from:
                    no_contract = True

            slip.has_no_running_contract = no_contract
            slip.has_zero_or_negative_net = bool(
                slip.employee_id and slip.state != 'cancel' and slip.line_ids and slip.net_wage <= 0.0
            )

    def action_open_contract(self):
        """Open the employee's payroll / contract section from the 'No running contract' banner."""
        self.ensure_one()
        employee = self.employee_id or (self.contract_id.employee_id if self.contract_id else False)
        if employee:
            return {
                'name': _('Employee - %s') % employee.name,
                'type': 'ir.actions.act_window',
                'res_model': 'hr.employee',
                'view_mode': 'form',
                'views': [[False, 'form']],
                'res_id': employee.id,
                'target': 'current',
                'context': dict(self.env.context, active_id=employee.id),
                'state': {
                    'activeNotebookPages': {
                        0: 'payroll_information',
                    }
                },
            }
        return False

    @api.depends('contract_id', 'contract_id.resource_calendar_id', 'contract_id.pay_by_attendance', 'employee_id.resource_calendar_id',
                 'worked_days_line_ids.number_of_days', 'worked_days_line_ids.number_of_hours', 'worked_days_line_ids.code', 'state')
    def _compute_stage_metrics(self):
        for slip in self:
            # 1. Working Hours & Review (Stage 1)
            cal = slip.contract_id.resource_calendar_id or slip.employee_id.resource_calendar_id
            slip.contract_working_hours = cal.name if cal else _("40 hours/week")
            slip.contract_review = _("Confirmed") if (slip.contract_id and getattr(slip.contract_id, 'state', 'draft') in ('open', 'confirmed')) else _("Draft")

            # 2. Time Off (Stage 2)
            leave_lines = slip.worked_days_line_ids.filtered(lambda l: l.code not in ('WORK100', 'SHORTAGE', 'OUT_OF_CONTRACT') and l.number_of_days > 0)
            slip.time_off_days = sum(leave_lines.mapped('number_of_days'))
            slip.time_off_summary = ", ".join(leave_lines.mapped('name')) if leave_lines else _("No Time Off")

            # 3. Attendances & Anomalies (Stage 3)
            work_lines = slip.worked_days_line_ids.filtered(lambda l: l.code == 'WORK100')
            shortage_lines = slip.worked_days_line_ids.filtered(lambda l: l.code == 'SHORTAGE' and l.number_of_hours > 0)
            worked_h = sum(work_lines.mapped('number_of_hours')) if work_lines else 0.0
            worked_d = sum(work_lines.mapped('number_of_days')) if work_lines else 0.0
            short_h = sum(shortage_lines.mapped('number_of_hours')) if shortage_lines else 0.0
            slip.attendance_expected_hours = worked_h
            slip.total_scheduled_days = worked_d
            is_pay_by_att = getattr(slip.contract_id, 'pay_by_attendance', False)
            if slip.state in ('done', 'paid'):
                slip.attendance_shortage_display = _("Normal")
            elif is_pay_by_att and short_h > 0:
                slip.attendance_shortage_display = _("Shortage: %s hrs") % round(short_h, 2)
            else:
                slip.attendance_shortage_display = _("Normal")

    def _get_localization_context(self, localdict):
        """Generic extension hook for country payroll localizations.
        Overridden by country modules (e.g. hudson_in_payroll, hudson_ae_payroll)
        to inject statutory calculation engines (EPF, ESIC, PT, TDS, EOSB) into localdict.
        """
        self.ensure_one()
        return localdict

    @api.depends('line_ids.total', 'line_ids.category_id.code')
    def _compute_totals(self):
        for slip in self:
            gross = sum(l.total for l in slip.line_ids if l.category_id and l.category_id.code == 'GROSS')
            net = sum(l.total for l in slip.line_ids if (l.category_id and l.category_id.code == 'NET') or l.code == 'NET')
            # Employer cost = Gross + Employer contributions (COMP category = employer statutory contributions)
            comp = sum(l.total for l in slip.line_ids if l.category_id and l.category_id.code == 'COMP')
            slip.gross_wage = gross
            slip.net_wage = max(0.0, net)
            slip.total_cost = (gross + comp) if comp > 0 else (gross if gross > 0 else max(0.0, net))

    @api.depends('line_ids.total', 'line_ids.category_id.code', 'contract_id.basic_salary', 'contract_id.wage', 'has_no_running_contract')
    def _compute_basic_wage(self):
        for slip in self:
            if slip.has_no_running_contract:
                slip.basic_wage = 0.0
                continue
            basic_lines = slip.line_ids.filtered(lambda l: (l.category_id and l.category_id.code == 'BASIC') or l.code == 'BASIC')
            if basic_lines:
                slip.basic_wage = sum(basic_lines.mapped('total'))
            elif slip.contract_id:
                slip.basic_wage = slip.contract_id.basic_salary or slip.contract_id.wage or 0.0
            else:
                slip.basic_wage = 0.0

    @api.depends('employee_id', 'contract_id.pay_by_attendance', 'worked_days_line_ids.number_of_hours', 'worked_days_line_ids.code', 'employee_id.bank_account_id', 'bank_account_id', 'has_no_running_contract', 'has_duplicate_payslip', 'net_wage', 'state')
    def _compute_payslip_warning(self):
        for slip in self:
            warnings = []
            if not slip.employee_id or slip.state == 'cancel':
                slip.payslip_warning = False
                continue
            if slip.has_duplicate_payslip:
                warnings.append(_("Duplicate payslips -> Duplicates"))
            if slip.net_wage <= 0.0 and slip.state not in ('done', 'paid'):
                warnings.append(_("Net pay is zero or negative."))
            if slip.state in ('done', 'paid'):
                slip.payslip_warning = "; ".join(warnings) if warnings else False
                continue
            if slip.has_no_running_contract:
                warnings.append(_("No running contract -> Contract"))
            is_pay_by_att = getattr(slip.contract_id, 'pay_by_attendance', False)
            if is_pay_by_att:
                shortage_lines = slip.worked_days_line_ids.filtered(lambda l: l.code == 'SHORTAGE' and l.number_of_hours > 0)
                if shortage_lines:
                    total_shortage = sum(shortage_lines.mapped('number_of_hours'))
                    warnings.append(_("Shortage: %s hrs") % round(total_shortage, 2))
                elif hasattr(slip, 'attendance_discrepancy_hours') and slip.attendance_discrepancy_hours < -0.01:
                    warnings.append(_("Discrepancy: %s hrs") % round(abs(slip.attendance_discrepancy_hours), 2))
            if not slip.has_bank_account:
                warnings.append(_("No bank account -> Employee"))
            slip.payslip_warning = "; ".join(warnings) if warnings else False

    @api.depends('state', 'payslip_warning')
    def _compute_display_status(self):
        for slip in self:
            if slip.state in ('done', 'paid'):
                slip.display_status = 'Done' if slip.state == 'done' else 'Paid'
            elif slip.state == 'cancel':
                slip.display_status = 'Cancelled'
            elif slip.payslip_warning:
                slip.display_status = 'Warning'
            else:
                slip.display_status = 'Draft'

    def action_detach_off_cycle(self):
        """Detach this payslip from the pay run to send it to the Off-Cycle (individual payslip)."""
        runs = self.mapped('payslip_run_id')
        for slip in self:
            slip.payslip_run_id = False
        if runs:
            runs._compute_counts()
            runs._compute_financial_totals()
            runs._compute_milestones()
        return True

    def action_remove_from_run(self):
        """Removes/deletes or detaches an employee payslip from the pay run."""
        for slip in self:
            run = slip.payslip_run_id
            if slip.state in ('draft', 'verify'):
                slip.unlink()
            else:
                slip.payslip_run_id = False
            if run:
                run._compute_counts()
                run._compute_financial_totals()
                run._compute_milestones()
        return True

    @api.constrains('employee_id', 'payslip_run_id')
    def _check_unique_employee_per_run(self):
        for slip in self:
            if slip.payslip_run_id and slip.employee_id:
                duplicate = self.search([
                    ('payslip_run_id', '=', slip.payslip_run_id.id),
                    ('employee_id', '=', slip.employee_id.id),
                    ('id', '!=', slip.id)
                ], limit=1)
                if duplicate:
                    raise UserError(_(
                        "Employee '%(emp)s' already has a payslip in this pay run batch! Duplicate payslips for the same employee are not allowed."
                    ) % {'emp': slip.employee_id.name})

    @api.constrains('payslip_run_id', 'company_id')
    def _check_company_alignment_per_run(self):
        for slip in self:
            if slip.payslip_run_id and slip.company_id and slip.payslip_run_id.company_id:
                if slip.company_id != slip.payslip_run_id.company_id:
                    raise ValidationError(_(
                        "Company Mismatch: Payslip '%(slip)s' belongs to company '%(slip_co)s', "
                        "while Pay Run batch '%(run)s' belongs to company '%(run_co)s'. "
                        "A payslip cannot be linked to a pay run of a different company."
                    ) % {
                        'slip': slip.name or slip.number or _('New'),
                        'slip_co': slip.company_id.name,
                        'run': slip.payslip_run_id.name,
                        'run_co': slip.payslip_run_id.company_id.name,
                    })

    @api.onchange('company_id')
    def _onchange_company_id_payslip_run(self):
        if self.payslip_run_id and self.payslip_run_id.company_id and self.company_id and self.payslip_run_id.company_id != self.company_id:
            self.payslip_run_id = False

    @api.onchange('payslip_run_id')
    def _onchange_payslip_run_id_company(self):
        if self.payslip_run_id and self.payslip_run_id.company_id:
            self.company_id = self.payslip_run_id.company_id

    @api.depends('worked_days_line_ids.number_of_days', 'worked_days_line_ids.number_of_hours', 'worked_days_line_ids.code')
    def _compute_worked_days_totals(self):
        for slip in self:
            work_days = sum(l.number_of_days for l in slip.worked_days_line_ids if l.code == 'WORK100')
            slip.total_worked_days = work_days

            work_hours = sum(l.number_of_hours for l in slip.worked_days_line_ids if l.code == 'WORK100')
            slip.total_worked_hours = work_hours

    @api.depends('employee_id', 'employee_id.bank_account_id')
    def _compute_bank_account_id(self):
        for slip in self:
            if not slip.bank_account_id and slip.employee_id and slip.employee_id.bank_account_id:
                slip.bank_account_id = slip.employee_id.bank_account_id

    @api.depends('employee_id', 'employee_id.bank_account_id', 'bank_account_id')
    def _compute_has_bank_account(self):
        for slip in self:
            slip.has_bank_account = bool(slip.bank_account_id or (slip.employee_id and slip.employee_id.bank_account_id))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            emp_id = vals.get('employee_id')
            if emp_id:
                emp = self.env['hr.employee'].browse(emp_id)
                if not vals.get('company_id'):
                    vals['company_id'] = emp.company_id.id or self.env.company.id
                period_version = emp._hds_payroll_version(vals.get('date_from'), vals.get('date_to'))
                if not vals.get('contract_id'):
                    contract = period_version or self.env['hr.version'].search([('employee_id', '=', emp.id)], limit=1, order='id desc')
                    if contract:
                        vals['contract_id'] = contract.id
                if not vals.get('struct_id'):
                    contract_id = vals.get('contract_id')
                    contract = self.env['hr.version'].browse(contract_id) if contract_id else (period_version or False)
                    struct = getattr(contract, 'struct_id', False) if contract else False
                    if not struct and contract and hasattr(contract, 'structure_type_id') and contract.structure_type_id:
                        struct = getattr(contract.structure_type_id, 'default_struct_id', False) or self.env['hr.payroll.structure'].search([
                            ('type_id', '=', contract.structure_type_id.id)
                        ], limit=1)
                    if not struct:
                        struct = self.env['hr.payroll.structure'].search([('code', '=', 'REGULAR')], limit=1) or self.env['hr.payroll.structure'].search([], limit=1)
                    if struct:
                        vals['struct_id'] = struct.id
                if not vals.get('name'):
                    date_from = vals.get('date_from') or fields.Date.today().replace(day=1)
                    date_str = fields.Date.from_string(date_from).strftime('%B %Y') if date_from else ''
                    vals['name'] = _('Salary Slip - %(emp)s - %(period)s') % {
                        'emp': emp.name,
                        'period': date_str
                    }
        slips = super().create(vals_list)
        for slip in slips:
            if not slip.worked_days_line_ids:
                slip._populate_worked_days()
            if not slip.input_line_ids:
                slip._populate_inputs()
            else:
                slip._sync_salary_adjustments()
            for inp in slip.input_line_ids:
                if not inp.payslip_id:
                    inp.payslip_id = slip.id
        slips._recompute_overlapping_duplicate_status()
        return slips

    def write(self, vals):
        res = super().write(vals)
        if any(f in vals for f in ('employee_id', 'date_from', 'date_to', 'state')):
            self._recompute_overlapping_duplicate_status()
        return res

    def unlink(self):
        emp_ids = self.mapped('employee_id').ids
        res = super().unlink()
        if emp_ids:
            remaining = self.search([
                ('employee_id', 'in', emp_ids),
                ('state', '!=', 'cancel'),
            ])
            if remaining:
                remaining._compute_duplicate_payslip()
        return res

    def _recompute_overlapping_duplicate_status(self):
        emp_ids = self.mapped('employee_id').ids
        if emp_ids:
            all_slips = self.search([
                ('employee_id', 'in', emp_ids),
                ('state', '!=', 'cancel'),
            ])
            if all_slips:
                all_slips._compute_duplicate_payslip()

    @api.onchange('date_from')
    def _onchange_date_from(self):
        if self.date_from:
            last_day = calendar.monthrange(self.date_from.year, self.date_from.month)[1]
            self.date_to = self.date_from.replace(day=last_day)

    @api.onchange('employee_id', 'date_from', 'date_to')
    def onchange_employee(self):
        if not self.employee_id:
            self.contract_id = False
            self.has_no_running_contract = False
            self.has_zero_or_negative_net = False
            self.has_duplicate_payslip = False
            self.duplicate_payslip_id = False
            self.payslip_warning = False
            return

        self.company_id = self.employee_id.company_id
        if not self.date_from:
            self.date_from = fields.Date.today().replace(day=1)
        if not self.date_to and self.date_from:
            last_day = calendar.monthrange(self.date_from.year, self.date_from.month)[1]
            self.date_to = self.date_from.replace(day=last_day)

        # 1. Automatic Contract Fetch
        contract = False
        period_version = self.employee_id._hds_payroll_version(self.date_from, self.date_to)
        if period_version:
            c = period_version
            c_start = getattr(c, 'contract_date_start', False) or getattr(c, 'date_start', False)
            c_end = getattr(c, 'contract_date_end', False) or getattr(c, 'date_end', False)
            if (not c_start or c_start <= self.date_to) and (not c_end or c_end >= self.date_from):
                contract = c

        if not contract:
            domain = [('employee_id', '=', self.employee_id.id)]
            if 'contract_date_start' in self.env['hr.version']._fields:
                domain += [
                    '|', ('contract_date_start', '=', False), ('contract_date_start', '<=', self.date_to),
                    '|', ('contract_date_end', '=', False), ('contract_date_end', '>=', self.date_from),
                ]
            contract = self.env['hr.version'].search(domain, limit=1, order='id desc')

        if not contract and period_version:
            contract = period_version

        if not contract:
            contract = self.env['hr.version'].search([('employee_id', '=', self.employee_id.id)], limit=1, order='id desc')

        if contract:
            self.contract_id = contract
            # 2. Automatic Structure Fetch from Contract or Structure Type
            struct = getattr(contract, 'struct_id', False)
            if not struct and hasattr(contract, 'structure_type_id') and contract.structure_type_id:
                struct = getattr(contract.structure_type_id, 'default_struct_id', False) or self.env['hr.payroll.structure'].search([
                    ('type_id', '=', contract.structure_type_id.id)
                ], limit=1)
            if not struct:
                struct = self.env['hr.payroll.structure'].search([('code', '=', 'REGULAR')], limit=1) or self.env['hr.payroll.structure'].search([], limit=1)
            self.struct_id = struct

        # Update payslip name
        date_str = self.date_from.strftime('%B %Y') if self.date_from else ''
        self.name = _('Salary Slip - %(emp)s - %(period)s') % {
            'emp': self.employee_id.name,
            'period': date_str
        }

        # Automatically populate worked days and inputs
        self._populate_worked_days()
        self._populate_inputs()
        self._compute_duplicate_payslip()

    @api.onchange('contract_id')
    def _onchange_contract_id(self):
        if self.contract_id:
            if not self.struct_id:
                struct = getattr(self.contract_id, 'struct_id', False)
                if not struct and hasattr(self.contract_id, 'structure_type_id') and self.contract_id.structure_type_id:
                    struct = getattr(self.contract_id.structure_type_id, 'default_struct_id', False) or self.env['hr.payroll.structure'].search([
                        ('type_id', '=', self.contract_id.structure_type_id.id)
                    ], limit=1)
                if not struct:
                    struct = self.env['hr.payroll.structure'].search([('code', '=', 'REGULAR')], limit=1) or self.env['hr.payroll.structure'].search([], limit=1)
                self.struct_id = struct
            self._populate_worked_days()
            self._populate_inputs()

    @api.onchange('struct_id')
    def _onchange_struct_id(self):
        if self.struct_id:
            self._populate_inputs()

    def compute_sheet(self):
        """Standard method for computing payslip sheet."""
        return self.action_compute_sheet()

    def _get_attendance_vs_schedule(self, contract, date_from, date_to):
        """Base schedule calculation using employee working schedule (resource.calendar).
        Overridden by attendance/leave modules to incorporate biometric attendance, unpaid leave, etc.
        """
        hours_per_day = 8.0
        calendar = contract.resource_calendar_id or contract.employee_id.resource_calendar_id
        if calendar and calendar.hours_per_day:
            hours_per_day = calendar.hours_per_day

        tz_name = getattr(calendar, 'tz', False) or getattr(contract.employee_id, 'tz', False) or (contract.company_id and contract.company_id.tz) or self.env.company.tz or 'UTC'
        tz = pytz.timezone(tz_name)
        d_from = fields.Date.from_string(date_from)
        d_to = fields.Date.from_string(date_to)

        c_start = getattr(contract, 'contract_date_start', False) or getattr(contract, 'date_start', False)
        c_end = getattr(contract, 'contract_date_end', False) or getattr(contract, 'date_end', False)

        eval_start = d_from
        eval_end = d_to
        schedule_pay = getattr(getattr(contract, 'structure_type_id', None), 'schedule_pay', 'monthly') or 'monthly'
        if schedule_pay == 'monthly' and d_from.year == d_to.year and d_from.month == d_to.month:
            cal_start = d_from.replace(day=1)
            cal_end = (d_from + relativedelta(months=1, day=1)) - relativedelta(days=1)
            if d_from > cal_start or d_to < cal_end:
                eval_start = cal_start
                eval_end = cal_end

        in_days = 0.0
        in_hours = 0.0
        out_days = 0.0
        out_hours = 0.0

        cur = eval_start
        while cur <= eval_end:
            day_start = tz.localize(datetime.combine(cur, time.min))
            day_end = tz.localize(datetime.combine(cur, time.max))
            if calendar:
                day_h = calendar.get_work_hours_count(day_start, day_end, compute_leaves=False)
                day_d = min(1.0, day_h / hours_per_day) if day_h > 0 else 0.0
            else:
                day_h = hours_per_day
                day_d = 1.0

            is_out = False
            if cur < d_from or cur > d_to:
                is_out = True
            elif c_start and cur < c_start:
                is_out = True
            elif c_end and cur > c_end:
                is_out = True

            if is_out:
                out_hours += day_h
                out_days += day_d
            else:
                in_hours += day_h
                in_days += day_d
            cur += relativedelta(days=1)

        total_sched_hours = in_hours + out_hours
        total_sched_days = in_days + out_days

        return {
            'scheduled_hours': in_hours,
            'scheduled_days': in_days,
            'out_of_contract_hours': out_hours,
            'out_of_contract_days': out_days,
            'total_period_scheduled_hours': total_sched_hours,
            'total_period_scheduled_days': total_sched_days,
            'unpaid_hours': 0.0,
            'unpaid_days': 0.0,
            'earned_hours': in_hours,
            'earned_days': in_days,
        }

    def _get_fixed_salary_attendance_factor(self, contract, date_from=None, date_to=None):
        """
        Computes the salary proration factor (0.0 to 1.0) for fixed-salary contracts
        (pay_by_attendance is OFF) using the Hybrid Attendance Threshold (Option B).

        Logic:
          - If worked hours/days <= 0.01: factor = 0.0 (Full month unpaid / absent -> ₹0 salary).
          - If enable_attendance_threshold is False:
              - Standard behavior: if mid-month joiner/leaver, factor = active_worked_hours / total_sched_hours; else 1.0.
          - If enable_attendance_threshold is True:
              - Calculate effective threshold days (pro-rated for mid-month joiner/leaver if out_of_contract_days > 0).
              - If active worked days < effective threshold:
                  Salary is pro-rated to actual days worked:
                  factor = active_worked_hours / total_sched_hours
              - If active worked days >= effective threshold:
                  Employee receives 100% of their eligible fixed salary:
                  factor = scheduled_hours / total_sched_hours (1.0 if full month).
        """
        d_from = date_from or getattr(self, 'date_from', False)
        d_to = date_to or getattr(self, 'date_to', False)
        if not d_from or not d_to:
            return 1.0

        sched_data = self._get_attendance_vs_schedule(contract, d_from, d_to)
        sched_hours = float(sched_data.get('scheduled_hours', 0.0) or 0.0)
        sched_days = float(sched_data.get('scheduled_days', 0.0) or 0.0)
        out_hours = float(sched_data.get('out_of_contract_hours', 0.0) or 0.0)
        out_days = float(sched_data.get('out_of_contract_days', 0.0) or 0.0)
        unpaid_hours = float(sched_data.get('unpaid_hours', 0.0) or 0.0)
        unpaid_days = float(sched_data.get('unpaid_days', 0.0) or 0.0)

        total_sched_hours = float(sched_data.get('total_period_scheduled_hours') or (sched_hours + out_hours) or 0.0)
        total_sched_days = float(sched_data.get('total_period_scheduled_days') or (sched_days + out_days) or 0.0)

        active_worked_hours = max(0.0, sched_hours - unpaid_hours)
        active_worked_days = max(0.0, sched_days - unpaid_days)

        # 1. 0 days worked -> ₹0 salary
        if active_worked_hours <= 0.01 or active_worked_days <= 0.01:
            return 0.0

        # 2. If threshold is disabled on contract
        if not getattr(contract, 'enable_attendance_threshold', True):
            if out_hours > 0.0 and total_sched_hours > 0.0:
                return min(1.0, max(0.0, active_worked_hours / total_sched_hours))
            return 1.0

        # 3. Attendance Threshold calculation
        thresh_days = float(getattr(contract, 'min_attendance_threshold_days', 14.0) or 14.0)
        if out_hours > 0.0 and total_sched_days > 0.0:
            effective_thresh = thresh_days * (sched_days / total_sched_days)
        else:
            effective_thresh = thresh_days

        # Case A: Below threshold -> Prorate to actual worked hours
        if active_worked_days < effective_thresh:
            if total_sched_hours > 0.0:
                return min(1.0, max(0.0, active_worked_hours / total_sched_hours))
            return 0.0

        # Case B: Threshold met or exceeded -> 100% of eligible fixed salary
        if out_hours > 0.0 and total_sched_hours > 0.0:
            return min(1.0, max(0.0, sched_hours / total_sched_hours))
        return 1.0

    @api.model
    def get_worked_day_lines(self, contracts, date_from, date_to):
        """Standard method for computing worked days lines.
        Uses employee working schedule (resource.calendar) to compute scheduled work days and hours.
        Extended by attendance and leave modules (e.g. hudson_attendance_payroll_link).
        """
        res = []
        for contract in contracts:
            hours_per_day = 8.0
            calendar = contract.resource_calendar_id or contract.employee_id.resource_calendar_id
            if calendar and calendar.hours_per_day:
                hours_per_day = calendar.hours_per_day

            tz_name = getattr(calendar, 'tz', False) or getattr(contract.employee_id, 'tz', False) or (contract.company_id and contract.company_id.tz) or self.env.company.tz or 'UTC'
            tz = pytz.timezone(tz_name)
            d_from = fields.Date.from_string(date_from)
            d_to = fields.Date.from_string(date_to)

            c_start = getattr(contract, 'contract_date_start', False) or getattr(contract, 'date_start', False)
            c_end = getattr(contract, 'contract_date_end', False) or getattr(contract, 'date_end', False)

            eval_start = d_from
            eval_end = d_to
            schedule_pay = getattr(getattr(contract, 'structure_type_id', None), 'schedule_pay', 'monthly') or 'monthly'
            if schedule_pay == 'monthly' and d_from.year == d_to.year and d_from.month == d_to.month:
                cal_start = d_from.replace(day=1)
                cal_end = (d_from + relativedelta(months=1, day=1)) - relativedelta(days=1)
                if d_from > cal_start or d_to < cal_end:
                    eval_start = cal_start
                    eval_end = cal_end

            in_days = 0.0
            in_hours = 0.0
            out_days = 0.0
            out_hours = 0.0

            cur = eval_start
            while cur <= eval_end:
                day_start = tz.localize(datetime.combine(cur, time.min))
                day_end = tz.localize(datetime.combine(cur, time.max))
                if calendar:
                    day_h = calendar.get_work_hours_count(day_start, day_end, compute_leaves=False)
                    day_d = min(1.0, day_h / hours_per_day) if day_h > 0 else 0.0
                else:
                    day_h = hours_per_day
                    day_d = 1.0

                is_out = False
                if cur < d_from or cur > d_to:
                    is_out = True
                elif c_start and cur < c_start:
                    is_out = True
                elif c_end and cur > c_end:
                    is_out = True

                if is_out:
                    out_hours += day_h
                    out_days += day_d
                else:
                    in_hours += day_h
                    in_days += day_d
                cur += relativedelta(days=1)

            is_india = (getattr(contract, '_is_india_localization', None) and contract._is_india_localization()) or (contract.company_id and contract.company_id.country_id and contract.company_id.country_id.code == 'IN')
            out_type_name = _('Out of Contract (India)') if is_india else _('Out of Contract')

            if out_days > 0.0 or out_hours > 0.0:
                res.append({
                    'name': out_type_name,
                    'sequence': 1,
                    'code': 'OUT_OF_CONTRACT',
                    'description': _('Out of Contract'),
                    'number_of_days': out_days,
                    'number_of_hours': out_hours,
                    'contract_id': contract.id,
                    'amount': 0.0,
                })

            total_sched_hours = in_hours + out_hours
            wage = float(getattr(contract, 'wage', 0.0) or getattr(contract, 'basic_salary', 0.0) or 0.0)
            if in_days <= 0.01 or in_hours <= 0.01:
                work100_amount = 0.0
            elif total_sched_hours > 0.0 and out_hours > 0.0:
                work100_amount = round(wage * (in_hours / total_sched_hours), 2)
            else:
                work100_amount = wage

            res.append({
                'name': _("Normal Working Days"),
                'sequence': 2,
                'code': 'WORK100',
                'description': _("Normal Working Days"),
                'number_of_days': in_days,
                'number_of_hours': in_hours,
                'contract_id': contract.id,
                'amount': work100_amount,
            })
        return res

    def _populate_worked_days(self):
        """Populates standard worked days lines using get_worked_day_lines."""
        self.ensure_one()
        if not self.contract_id:
            return
        if self.no_worked_days:
            self.worked_days_line_ids = [(5, 0, 0)]
            return
        worked_days = self.get_worked_day_lines(self.contract_id, self.date_from, self.date_to)
        self.worked_days_line_ids = [(5, 0, 0)] + [(0, 0, vals) for vals in worked_days]

    @api.onchange('no_worked_days')
    def _onchange_no_worked_days(self):
        if self.no_worked_days:
            self.worked_days_line_ids = [(5, 0, 0)]
        elif self.contract_id and self.date_from and self.date_to:
            self._populate_worked_days()

    def _populate_inputs(self):
        """Populates configured external inputs for the structure without wiping existing user amounts."""
        self.ensure_one()
        if self.struct_id:
            input_types = self.env['hr.payslip.input.type'].search([
                ('input_line_type_ids', 'in', self.struct_id.id)
            ])
            existing_codes = set(self.input_line_ids.mapped('code'))
            new_lines = []
            for itype in input_types:
                if itype.code not in existing_codes:
                    new_lines.append((0, 0, {
                        'name': itype.name,
                        'code': itype.code,
                        'input_type_id': itype.id,
                        'contract_id': self.contract_id.id if self.contract_id else False,
                        'sequence': itype.sequence,
                        'amount': 0.0,
                    }))
            if new_lines:
                if self.id and isinstance(self.id, int) and self.exists():
                    self.write({'input_line_ids': new_lines})
                else:
                    for line_cmd in new_lines:
                        self.input_line_ids += self.env['hr.payslip.input'].new(line_cmd[2])
        self._sync_salary_adjustments()

    def _sync_salary_adjustments(self):
        """
        Synchronizes active Salary Adjustments (hr.salary.adjustment) to this payslip's Other Inputs.
        - Identifies applicable running adjustments overlapping this payslip period.
        - Idempotently updates or creates hr.payslip.input lines tagged with adjustment_id.
        - Preserves existing manually entered inputs.
        - Cleans up adjustment-linked input lines if the adjustment was cancelled or no longer active.
        """
        self.ensure_one()
        if self.state in ('done', 'paid') or not self.employee_id or not self.date_from or not self.date_to:
            return

        is_saved = bool(self.id and isinstance(self.id, int) and self.exists())

        # Unsaved payslip (form onchange): its input lines exist only in memory. Change them in memory;
        # write()/unlink() on such lines flushes and invalidates the cache, which wipes the unsaved form
        # (employee, dates, ...). Saved payslips keep using write()/unlink().
        def _set_lines(lines, vals):
            if is_saved:
                lines.write(vals)
            else:
                for line in lines:
                    line.update(vals)

        def _drop_lines(lines):
            if not lines:
                return
            if is_saved:
                lines.unlink()
            else:
                self.input_line_ids -= lines

        adj_model = self.env['hr.salary.adjustment']
        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'running'),
            ('date_start', '<=', self.date_to),
            '|', ('date_end', '=', False), ('date_end', '>=', self.date_from),
        ]
        if self.company_id:
            domain += ['|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)]
        active_adjustments = adj_model.search(domain)

        applicable_adjustments = self.env['hr.salary.adjustment']
        for adj in active_adjustments:
            # Repeating adjustments without an End Date stop at the end of the employee's contract
            effective_end = adj._get_effective_date_end()
            if effective_end and effective_end < self.date_from:
                continue

            # For one-time adjustments, ensure not already applied on another finalized payslip
            if adj.duration == 'one_time':
                finalized_slips = adj.payslip_input_ids.mapped('payslip_id').filtered(
                    lambda p: p.id != self.id and p.state in ('done', 'paid')
                )
                if finalized_slips:
                    adj.with_context(skip_adjustment_sync=True).write({'state': 'done'})
                    continue

            # For limited adjustments with until_amount cap, check if limit already met
            if adj.duration == 'limited' and adj.until_amount:
                prior_applied = sum(
                    inp.amount for inp in adj.payslip_input_ids.filtered(
                        lambda i: i.payslip_id.id != self.id and i.payslip_id.state in ('done', 'paid')
                    )
                )
                if abs(prior_applied) >= abs(adj.until_amount):
                    adj.with_context(skip_adjustment_sync=True).write({'state': 'done'})
                    continue

            applicable_adjustments |= adj

        # Clean up any leftover orphan input records with no payslip_id for these adjustments
        if is_saved:
            orphan_inputs = self.env['hr.payslip.input'].search([
                ('payslip_id', '=', False),
                ('adjustment_id', 'in', applicable_adjustments.ids),
            ])
            if orphan_inputs:
                orphan_inputs.unlink()

        # 1. Update or create inputs for applicable adjustments
        for adj in applicable_adjustments:
            eff_amount = -adj.amount if adj.negative else adj.amount

            # If limited with until_amount cap, cap this period's amount so it doesn't exceed cap
            if adj.duration == 'limited' and adj.until_amount:
                prior_applied = sum(
                    inp.amount for inp in adj.payslip_input_ids.filtered(
                        lambda i: i.payslip_id.id != self.id and i.payslip_id.state in ('done', 'paid')
                    )
                )
                rem_cap = abs(adj.until_amount) - abs(prior_applied)
                if rem_cap > 0 and abs(eff_amount) > rem_cap:
                    eff_amount = -rem_cap if adj.negative else rem_cap

            existing_linked = self.input_line_ids.filtered(
                lambda l: l.adjustment_id and (l.adjustment_id == adj or l.adjustment_id.id == adj.id)
            )
            if existing_linked:
                _set_lines(existing_linked[0], {
                    'amount': eff_amount,
                    'name': adj.note or adj.input_type_id.name,
                    'code': adj.input_code,
                    'sequence': adj.input_type_id.sequence or 10,
                })
                # If there are duplicate linked lines for the same adjustment, keep only the first
                if len(existing_linked) > 1:
                    _drop_lines(existing_linked[1:])
                # Also clean up any unlinked duplicate lines with the same code to prevent duplicate entries
                unlinked_dups = self.input_line_ids.filtered(
                    lambda l: not l.adjustment_id and l.code == adj.input_code
                )
                _drop_lines(unlinked_dups)
            else:
                # Check for an unlinked input with same code (from onchange without adjustment_id or structure defaults)
                unlinked_same_code = self.input_line_ids.filtered(
                    lambda l: not l.adjustment_id and l.code == adj.input_code
                )
                if unlinked_same_code:
                    _set_lines(unlinked_same_code[0], {
                        'adjustment_id': adj.id,
                        'amount': eff_amount,
                        'name': adj.note or adj.input_type_id.name,
                        'sequence': adj.input_type_id.sequence or 10,
                    })
                    if len(unlinked_same_code) > 1:
                        _drop_lines(unlinked_same_code[1:])
                else:
                    input_vals = {
                        'adjustment_id': adj.id,
                        'input_type_id': adj.input_type_id.id,
                        'name': adj.note or adj.input_type_id.name,
                        'code': adj.input_code,
                        'amount': eff_amount,
                        'contract_id': self.contract_id.id if self.contract_id else False,
                        'sequence': adj.input_type_id.sequence or 10,
                    }
                    if is_saved:
                        # Target payslip is saved: link using 'payslip_id': self.id
                        input_vals['payslip_id'] = self.id
                        self.env['hr.payslip.input'].create(input_vals)
                    else:
                        # Unsaved in-memory payslip: pass adjustment inside input_line_ids
                        self.input_line_ids += self.env['hr.payslip.input'].new(input_vals)

        # 2. Clean up inputs previously linked to adjustments that are no longer applicable
        stale_linked = self.input_line_ids.filtered(
            lambda l: l.adjustment_id and l.adjustment_id not in applicable_adjustments
        )
        _drop_lines(stale_linked)

        if is_saved:
            self.invalidate_recordset(['input_line_ids'])

    def _get_eval_context(self):
        """Prepares the clean Python safe_eval dictionary context."""
        self.ensure_one()
        
        # Format worked days dict
        worked_days_dict = {}
        for wd in self.worked_days_line_ids:
            worked_days_dict[wd.code] = wd

        # Format inputs dict (aggregating multiple inputs of the same code)
        inputs_dict = {}
        for inp in self.input_line_ids:
            if inp.code in inputs_dict:
                old_inp = inputs_dict[inp.code]
                combined_amount = old_inp.amount + inp.amount
                inputs_dict[inp.code] = BrowsableObject({
                    'code': inp.code,
                    'name': inp.name,
                    'amount': combined_amount,
                    'contract_id': inp.contract_id,
                })
            else:
                inputs_dict[inp.code] = inp

        categories = CategoryAccumulator()
        rules_dict = {}

        return {
            'payslip': self,
            'payslip_record': self,
            'employee': self.employee_id,
            'contract': self.contract_id,
            'worked_days': BrowsableObject(worked_days_dict),
            'inputs': BrowsableObject(inputs_dict),
            'categories': categories,
            'rules': BrowsableObject(rules_dict),
            '_rules_dict': rules_dict,
            'env': self.env,
            'getattr': getattr,
            'hasattr': hasattr,
        }

    def action_compute_sheet(self):
        """Main computation engine for calculating salary rules in topological order."""
        for slip in self:
            if slip.state in ('done', 'paid'):
                continue
            slip._sync_salary_adjustments()
            slip.invalidate_recordset(['input_line_ids'])
            if not slip.struct_id:
                raise UserError(_("Please assign a Salary Structure to payslip %(name)s") % {'name': slip.name})


            if slip.has_no_running_contract:
                # Employee has no running contract during this payslip period.
                # Net wage and gross wage must be 0.0.
                rules = slip.struct_id.get_all_rules()
                net_rule = rules.filtered(lambda r: r.code == 'NET') or self.env['hr.salary.rule'].search([('code', '=', 'NET')], limit=1)
                lines_vals = []
                if net_rule:
                    lines_vals.append((0, 0, {
                        'name': net_rule.name or _('Net Salary'),
                        'code': net_rule.code,
                        'sequence': net_rule.sequence or 200,
                        'salary_rule_id': net_rule.id,
                        'employee_id': slip.employee_id.id,
                        'contract_id': slip.contract_id.id if slip.contract_id else False,
                        'amount': 0.0,
                        'rate': 100.0,
                        'quantity': 1.0,
                        'appears_on_payslip': True,
                    }))
                slip.line_ids = [(5, 0, 0)] + lines_vals
                slip._compute_totals()
                slip._compute_contract_status()
                continue

            rules = slip.struct_id.get_all_rules()
            localdict = slip._get_eval_context()
            localdict = slip._get_localization_context(localdict)
            categories = localdict['categories']
            rules_dict = localdict['_rules_dict']

            lines_vals = []
            for rule in rules:
                if not rule._satisfies_condition(localdict):
                    continue

                amount, rate, qty = rule._compute_rule(localdict)
                total = qty * amount * rate / 100.0

                # Register in localdict for subsequent rules
                rule_res = RuleResult(amount=amount, rate=rate, quantity=qty)
                rules_dict[rule.code] = rule_res
                localdict[rule.code] = total
                categories.add(rule.category_id, total)

                lines_vals.append((0, 0, {
                    'name': rule.name,
                    'code': rule.code,
                    'sequence': rule.sequence,
                    'salary_rule_id': rule.id,
                    'employee_id': slip.employee_id.id,
                    'contract_id': slip.contract_id.id,
                    'amount': amount,
                    'rate': rate,
                    'quantity': qty,
                    'appears_on_payslip': (True if rule.appears_on_payslip == 'always' else False if rule.appears_on_payslip == 'never' else bool(amount)),
                }))

            slip.line_ids = [(5, 0, 0)] + lines_vals
        return True

    def action_payslip_draft(self):
        for slip in self:
            # Reopen any adjustments that were marked done solely by this payslip
            for inp in slip.input_line_ids.filtered(lambda l: l.adjustment_id):
                adj = inp.adjustment_id
                if adj.state == 'done':
                    other_done = adj.payslip_input_ids.filtered(
                        lambda i: i.payslip_id.id != slip.id and i.payslip_id.state in ('done', 'paid')
                    )
                    if not other_done:
                        adj.with_context(skip_adjustment_sync=True).write({'state': 'running'})
        res = self.write({'state': 'draft'})
        for slip in self:
            slip._sync_salary_adjustments()
            if slip.line_ids:
                slip.action_compute_sheet()
        # A previously cancelled payslip counts again in its pay run's department breakdown
        self.mapped('payslip_run_id')._compute_department_summaries()
        return res

    def action_payslip_verify(self):
        return self.write({'state': 'verify'})

    def action_payslip_done(self):
        for slip in self:
            if slip.has_no_running_contract:
                raise ValidationError(_("• No running contract"))
            if not slip.number:
                slip.number = self.env['ir.sequence'].next_by_code('hr.payslip') or _('New')

        # 1. Finalize payslip state first so that all lines and inputs remain permanently locked
        res = self.write({'state': 'done'})

        # 2. Update applied salary adjustments with skip_adjustment_sync context
        for slip in self:
            for inp in slip.input_line_ids.filtered(lambda l: l.adjustment_id):
                adj = inp.adjustment_id
                if adj.duration == 'one_time':
                    adj.with_context(skip_adjustment_sync=True).write({'state': 'done'})
                else:
                    # Check if total cap met
                    if adj.duration == 'limited' and adj.until_amount:
                        total_applied = sum(
                            l.amount for l in adj.payslip_input_ids.filtered(
                                lambda i: i.payslip_id.state in ('done', 'paid')
                            )
                        )
                        if abs(total_applied) >= abs(adj.until_amount):
                            adj.with_context(skip_adjustment_sync=True).write({'state': 'done'})
                    # Check if End Date (or contract end for open-ended repeats) passed
                    effective_end = adj._get_effective_date_end()
                    if effective_end and slip.date_to and slip.date_to >= effective_end:
                        adj.with_context(skip_adjustment_sync=True).write({'state': 'done'})
        return res

    def action_payslip_paid(self):
        """Mark validated payslips as paid. Draft, to-verify and cancelled payslips cannot be paid."""
        not_validated = self.filtered(lambda s: s.state not in ('done', 'paid'))
        if not_validated:
            raise UserError(_(
                "Only validated payslips can be marked as paid.\n\n"
                "The following payslip(s) are not validated:\n • %(slips)s"
            ) % {'slips': "\n • ".join(
                f"{s.employee_id.name} ({dict(s._fields['state']._description_selection(self.env)).get(s.state)})"
                for s in not_validated
            )})
        # Payment Date records the day the salary was paid (the Pay wizard passes its payment date)
        payment_date = self.env.context.get('hds_payment_date') or fields.Date.context_today(self)
        return self.filtered(lambda s: s.state == 'done').write({'paid': True, 'state': 'paid', 'payment_date': payment_date})

    def action_open_pay_wizard(self):
        """Opens Payment Advice Wizard for this individual payslip."""
        self.ensure_one()
        return {
            'name': _('Pay'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip.run.pay.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {
                'default_payslip_id': self.id,
                'default_payslip_run_id': self.payslip_run_id.id if self.payslip_run_id else False,
                'active_id': self.id,
                'active_model': 'hr.payslip',
            },
        }

    def action_open_payment_advice(self):
        """Opens the related Payment Advice for this payslip."""
        self.ensure_one()
        advice = self.effective_advice_id
        if not advice:
            return False
        return {
            'name': _('Payment Advice'),
            'type': 'ir.actions.act_window',
            'res_model': 'hudson.payroll.payment.advice',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'res_id': advice.id,
            'target': 'current',
        }

    def action_payslip_send_email(self):
        """Open mail composer to send the payslip to the employee with PDF attached."""
        self.ensure_one()
        template = self.env.ref('hudson_payroll_base.mail_template_payslip', raise_if_not_found=False)
        ctx = {
            'default_model': 'hr.payslip',
            'default_res_ids': [self.id],
            'default_use_template': bool(template),
            'default_template_id': template.id if template else False,
            'default_composition_mode': 'comment',
            'mark_so_as_sent': True,
        }
        emp_partner = (
            getattr(self.employee_id, 'work_contact_id', False)
            or getattr(self.employee_id, 'address_home_id', False)
            or (self.employee_id.user_id and self.employee_id.user_id.partner_id)
        )
        if emp_partner:
            ctx['default_partner_ids'] = [emp_partner.id]
        if self.employee_id.work_email:
            ctx['default_email_to'] = self.employee_id.work_email

        return {
            'type': 'ir.actions.act_window',
            'name': _('Send Payslip by Email'),
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(False, 'form')],
            'target': 'new',
            'context': ctx,
        }

    def action_print_payslip(self):
        report = self.env.ref('hudson_payroll_base.action_report_payslip', raise_if_not_found=False)
        if report:
            ctx = dict(self.env.context)
            ctx.pop('active_id', None)
            ctx['active_model'] = 'hr.payslip'
            ctx['active_ids'] = self.ids
            if len(self) == 1:
                ctx['active_id'] = self.id
            return report.with_context(ctx).report_action(self)
        return True

    def action_print_payslips(self):
        """Batch print payslips: Generates a single multi-page PDF (1 page per selected employee)."""
        return self.action_print_payslip()

    def action_payslip_cancel(self):
        res = self.write({'state': 'cancel'})
        for slip in self:
            for inp in slip.input_line_ids.filtered(lambda l: l.adjustment_id):
                adj = inp.adjustment_id
                if adj.state == 'done':
                    other_done = adj.payslip_input_ids.filtered(
                        lambda i: i.payslip_id.id != slip.id and i.payslip_id.state in ('done', 'paid')
                    )
                    if not other_done:
                        adj.with_context(skip_adjustment_sync=True).write({'state': 'running'})
        # Cancelled payslips no longer count in their pay run's department breakdown
        self.mapped('payslip_run_id')._compute_department_summaries()
        return res

    def refund_sheet(self):
        """Create a reverse/refund credit note payslip."""
        for slip in self:
            copied_slip = slip.copy({
                'credit_note': True,
                'name': _('Refund: ') + slip.name,
                'state': 'draft',
            })
            copied_slip.compute_sheet()
            for line in copied_slip.line_ids:
                line.amount = -line.amount
        return True
