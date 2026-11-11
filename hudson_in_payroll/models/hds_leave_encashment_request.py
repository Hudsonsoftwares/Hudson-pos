# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError, UserError
# pyrefly: ignore [missing-import]
from odoo.tools.float_utils import float_round
# pyrefly: ignore [missing-import]
from odoo.tools.safe_eval import safe_eval
import logging

_logger = logging.getLogger(__name__)


class HdsLeaveEncashmentRequest(models.Model):
    """
    Transaction Request for In-Service Leave Encashment.
    Captures employee leave encashment claims, evaluates policy compliance,
    maintains multi-stage approval lifecycle, and links with monthly payslip processing.
    """
    _name = 'hds.leave.encashment.request'
    _description = 'Leave Encashment Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'

    name = fields.Char(
        string="Request Number",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )

    # -------------------------------------------------------------------------
    # PARTIES & POLICY CONTEXT
    # -------------------------------------------------------------------------
    def _default_employee_id(self):
        return self.env.user.employee_id.id or False

    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        required=True,
        default=_default_employee_id,
        tracking=True,
        help="Select the employee requesting leave encashment."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        compute='_compute_company_id',
        store=True,
        readonly=True,
        compute_sudo=True,
        default=lambda self: self.env.company
    )
    is_officer = fields.Boolean(
        string="Is Officer",
        compute='_compute_is_officer',
        default=lambda self: self.env.user.has_group('hr_holidays.group_hr_holidays_user') or self.env.user.has_group('hudson_payroll_base.group_payroll_user') or self.env.is_superuser()
    )
    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        related='company_id.currency_id',
        readonly=True
    )
    policy_id = fields.Many2one(
        'hds.leave.encashment.policy',
        string="Encashment Policy",
        required=True,
        tracking=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id), ('active', '=', True)]",
        help="Applicable leave encashment policy governing this transaction."
    )
    eligible_leave_type_ids = fields.Many2many(
        'hr.work.entry.type',
        compute='_compute_eligible_leave_type_ids',
        string="Eligible Leave Types"
    )
    leave_type_id = fields.Many2one(
        'hr.work.entry.type',
        string="Leave Type",
        required=True,
        tracking=True,
        domain="[('id', 'in', eligible_leave_type_ids)]",
        help="Select which unavailed leave type is to be encashed (e.g. Earned Leave)."
    )
    request_date = fields.Date(
        string="Request Date",
        required=True,
        default=fields.Date.today,
        tracking=True
    )

    # -------------------------------------------------------------------------
    # BALANCES & DAYS
    # -------------------------------------------------------------------------
    available_balance = fields.Float(
        string="Available Balance (Days)",
        compute='_compute_balances',
        store=True,
        readonly=True,
        compute_sudo=True,
        help="Current unavailed leave days remaining as of the request date (excluding pending requests)."
    )
    requested_days = fields.Float(
        string="Requested Days",
        required=True,
        default=1.0,
        tracking=True,
        help="Number of leave days the employee wishes to encash."
    )
    remaining_balance_after = fields.Float(
        string="Balance After Encashment",
        compute='_compute_balances',
        store=True,
        readonly=True,
        compute_sudo=True,
        help="Projected leave balance after deducting requested days."
    )

    # -------------------------------------------------------------------------
    # MONETARY EVALUATION
    # -------------------------------------------------------------------------
    daily_rate = fields.Monetary(
        string="Daily Wage Rate",
        currency_field='currency_id',
        compute='_compute_projected_amount',
        store=True,
        readonly=True,
        compute_sudo=True,
        help="Evaluated daily wage rate based on the policy formula and active contract."
    )
    projected_amount = fields.Monetary(
        string="Encashment Amount",
        currency_field='currency_id',
        compute='_compute_projected_amount',
        store=True,
        readonly=True,
        compute_sudo=True,
        help="Total projected payout amount for the requested encashment days."
    )

    # -------------------------------------------------------------------------
    # LIFECYCLE & PAYROLL INTEGRATION
    # -------------------------------------------------------------------------
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('paid', 'Paid / Processed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default='draft', required=True, tracking=True, copy=False)

    payslip_id = fields.Many2one(
        'hr.payslip',
        string="Processed Payslip",
        readonly=True,
        copy=False,
        help="Payslip on which this encashment earning was paid."
    )
    allocation_id = fields.Many2one(
        'hr.leave.allocation',
        string="Deducted Leave Allocation",
        readonly=True,
        copy=False,
        help="Primary leave allocation from which unavailed days were deducted."
    )
    deducted_days = fields.Float(
        string="Deducted Days",
        readonly=True,
        copy=False,
        default=0.0,
        help="Number of days deducted from leave allocation(s)."
    )
    deducted_allocation_data = fields.Text(
        string="Deducted Allocation Breakdown",
        readonly=True,
        copy=False,
        help="JSON breakdown of allocations and days deducted."
    )
    leave_id = fields.Many2one(
        'hr.leave',
        string="Legacy Time Off Record",
        readonly=True,
        copy=False,
        help="Legacy Time Off record (deprecated in favor of direct allocation adjustment)."
    )

    # -------------------------------------------------------------------------
    # AUDIT & APPROVAL TRACKING
    # -------------------------------------------------------------------------
    approved_by = fields.Many2one(
        'res.users',
        string="Approved By",
        readonly=True,
        copy=False
    )
    approval_date = fields.Datetime(
        string="Approval Timestamp",
        readonly=True,
        copy=False
    )
    rejection_reason = fields.Char(
        string="Rejection Reason",
        readonly=True,
        copy=False
    )
    notes = fields.Text(string="Reason / Remarks")

    # -------------------------------------------------------------------------
    # ORM OVERRIDES & DEFAULTS
    # -------------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hds.leave.encashment.request') or _('New')
        return super().create(vals_list)

    @api.depends('employee_id')
    def _compute_company_id(self):
        for rec in self:
            rec.company_id = rec.employee_id.sudo().company_id.id if rec.employee_id else (self.env.company.id or False)

    def _compute_is_officer(self):
        is_officer = (
            self.env.user.has_group('hr_holidays.group_hr_holidays_user') or
            self.env.user.has_group('hudson_payroll_base.group_payroll_user') or
            self.env.is_superuser()
        )
        for rec in self:
            rec.is_officer = is_officer

    @api.depends('policy_id', 'policy_id.leave_type_ids')
    def _compute_eligible_leave_type_ids(self):
        all_encashable = self.env['hr.work.entry.type'].search([
            ('include_in_leave_encashment', '=', True)
        ])
        for rec in self:
            if rec.policy_id and rec.policy_id.leave_type_ids:
                rec.eligible_leave_type_ids = rec.policy_id.leave_type_ids
            else:
                rec.eligible_leave_type_ids = all_encashable

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            emp = self.employee_id.sudo()
            company = emp.company_id or self.env.company
            self.company_id = company.id
            policy = self.env['hds.leave.encashment.policy'].sudo().search([
                ('company_id', 'in', [company.id, False]),
                ('active', '=', True)
            ], order='company_id desc, id asc', limit=1)
            if policy:
                self.policy_id = policy.id
                if policy.leave_type_ids:
                    self.leave_type_id = policy.leave_type_ids[0].id
                else:
                    first_encashable = self.env['hr.work.entry.type'].search([
                        ('include_in_leave_encashment', '=', True)
                    ], limit=1)
                    if first_encashable:
                        self.leave_type_id = first_encashable.id
        self._compute_projected_amount()
        self._compute_balances()

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.company_id:
            policy = self.env['hds.leave.encashment.policy'].sudo().search([
                ('company_id', 'in', [self.company_id.id, False]),
                ('active', '=', True)
            ], order='company_id desc, id asc', limit=1)
            if policy:
                self.policy_id = policy.id

    @api.onchange('policy_id')
    def _onchange_policy_id(self):
        if self.policy_id and self.policy_id.leave_type_ids:
            if not self.leave_type_id or self.leave_type_id not in self.policy_id.leave_type_ids:
                self.leave_type_id = self.policy_id.leave_type_ids[0].id
        elif not self.leave_type_id or not self.leave_type_id.include_in_leave_encashment:
            first_encashable = self.env['hr.work.entry.type'].search([
                ('include_in_leave_encashment', '=', True)
            ], limit=1)
            if first_encashable:
                self.leave_type_id = first_encashable.id
        self._compute_projected_amount()
        self._compute_balances()

    @api.onchange('requested_days')
    def _onchange_requested_days(self):
        self._compute_projected_amount()
        self._compute_balances()

    # -------------------------------------------------------------------------
    # COMPUTED FIELDS: BALANCES & AMOUNTS
    # -------------------------------------------------------------------------
    @api.depends('employee_id', 'leave_type_id', 'request_date', 'requested_days')
    def _compute_balances(self):
        for rec in self:
            if not rec.employee_id or not rec.leave_type_id:
                rec.available_balance = 0.0
                rec.remaining_balance_after = 0.0
                continue

            try:
                # pyrefly: ignore [missing-import]
                from ..services.leave_encashment.leave_encashment_data_service import LeaveEncashmentDataService
                data_svc = LeaveEncashmentDataService(self.env(su=True))
                rem_leaves = data_svc._retrieve_remaining_leaves(
                    rec.leave_type_id.sudo(),
                    rec.employee_id.sudo(),
                    rec.request_date or fields.Date.today()
                )
            except Exception as e:
                _logger.warning("Could not retrieve leave balance for %s: %s", rec.employee_id.sudo().name, str(e))
                rem_leaves = 0.0

            # Subtract other approved encashments that have not yet deducted an allocation or created a leave record
            other_approved = self.sudo().search([
                ('employee_id', '=', rec.employee_id.id),
                ('leave_type_id', '=', rec.leave_type_id.id),
                ('state', '=', 'approved'),
                ('id', '!=', rec.id or 0),
                ('deducted_days', '=', 0.0),
                ('leave_id', '=', False),
            ])
            pending_days = sum(other_approved.mapped('requested_days'))

            # For an already approved/paid record, add back its own deducted days to reflect the pre-encashment available balance
            current_deducted = (
                rec.deducted_days or (rec.leave_id.number_of_days if rec.leave_id else 0.0)
            ) if rec.state in ('approved', 'paid') else 0.0
            base_balance = rem_leaves + current_deducted
            effective_balance = max(0.0, float(base_balance - pending_days))

            rec.available_balance = effective_balance
            rec.remaining_balance_after = max(0.0, effective_balance - (rec.requested_days or 0.0))

    @api.depends(
        'employee_id',
        'policy_id',
        'policy_id.calculation_basis',
        'policy_id.custom_formula_code',
        'requested_days'
    )
    def _compute_projected_amount(self):
        for rec in self:
            if not rec.employee_id or not rec.policy_id or rec.requested_days <= 0.0:
                rec.daily_rate = 0.0
                rec.projected_amount = 0.0
                continue

            contract = self._get_active_contract(rec.employee_id)
            if not contract:
                rec.daily_rate = 0.0
                rec.projected_amount = 0.0
                continue

            amount = rec.calculate_payout_amount(contract)
            rec.projected_amount = amount
            rec.daily_rate = float_round(amount / rec.requested_days, precision_digits=2) if rec.requested_days > 0 else 0.0

    def _get_active_contract(self, employee):
        """Resolves active contract or version record for the employee."""
        emp = employee.sudo()
        if getattr(emp, 'version_id', False):
            return emp.version_id
        contracts = self.env(su=True)['hr.version'].search([
            ('employee_id', '=', emp.id),
        ], order='id desc', limit=1)
        return contracts if contracts else None

    # -------------------------------------------------------------------------
    # STATUTORY CALCULATION ENGINE
    # -------------------------------------------------------------------------
    def calculate_payout_amount(self, contract=None):
        """
        Calculates exact leave encashment payable amount based on the selected policy formula.
        """
        self.ensure_one()
        policy = self.policy_id
        if not policy or self.requested_days <= 0.0:
            return 0.0

        ctr = contract or self._get_active_contract(self.employee_id)
        if not ctr:
            return 0.0

        basic = float(getattr(ctr, 'basic_salary', 0.0) or getattr(ctr, 'wage', 0.0) or 0.0)
        da = float(getattr(ctr, 'da', 0.0) or getattr(ctr, 'da_amount', 0.0) or 0.0)
        gross = float(getattr(ctr, 'gross_wage', 0.0) or getattr(ctr, 'wage', 0.0) or (basic + da) or 0.0)
        encash_days = float(self.requested_days)

        basis = policy.calculation_basis or 'statutory_26'

        if basis == 'statutory_26':
            daily_rate = (basic + da) / 26.0
            amount = daily_rate * encash_days
        elif basis == 'calendar_30':
            daily_rate = (basic + da) / 30.0
            amount = daily_rate * encash_days
        elif basis == 'gross_30':
            daily_rate = gross / 30.0
            amount = daily_rate * encash_days
        elif basis == 'custom_formula' and policy.custom_formula_code:
            eval_ctx = {
                'basic': basic,
                'da': da,
                'gross': gross,
                'encash_days': encash_days,
                'contract': ctr,
                'employee': self.employee_id,
                'result': 0.0,
            }
            try:
                safe_eval(policy.custom_formula_code, eval_ctx, mode="exec")
                amount = float(eval_ctx.get('result', 0.0) or 0.0)
            except Exception as e:
                _logger.error("Failed to evaluate custom formula for policy %s: %s", policy.name, str(e))
                # Fallback to statutory standard
                amount = ((basic + da) / 26.0) * encash_days
        else:
            amount = ((basic + da) / 26.0) * encash_days

        return float_round(max(0.0, amount), precision_digits=2)

    @api.constrains('employee_id')
    def _check_employee_submission(self):
        is_officer = (
            self.env.user.has_group('hr_holidays.group_hr_holidays_user') or
            self.env.user.has_group('hudson_payroll_base.group_payroll_user') or
            self.env.is_superuser()
        )
        if not is_officer:
            for rec in self:
                if rec.employee_id.user_id != self.env.user:
                    raise ValidationError(_("You can only submit leave encashment requests for yourself."))

    # -------------------------------------------------------------------------
    # VALIDATION GUARDS (TENURE, BUFFER, ANNUAL CAP, EMPLOYEE TYPE)
    # -------------------------------------------------------------------------
    def _validate_request_eligibility(self):
        """Enforces all business and statutory policy limits."""
        self.ensure_one()
        policy = self.policy_id.sudo()
        emp = self.employee_id.sudo()
        company = emp.company_id or self.env.company

        # 1. Company Enablement Guard
        if not getattr(company, 'hds_in_enable_leave_encashment', False):
            raise ValidationError(_(
                "Leave Encashment is disabled for company '%s'. Please enable it in Payroll Settings."
            ) % company.name)

        # 2. Employee Type Guard (mapped from Employee module > Payroll tab > Employee Type)
        if policy.employee_type_ids:
            emp_type = getattr(emp, 'employee_type_id', False)
            if not emp_type:
                contract = self._get_active_contract(emp)
                if contract and getattr(contract, 'employee_type_id', False):
                    emp_type = contract.employee_type_id

            if not emp_type or emp_type not in policy.employee_type_ids:
                allowed_types = ", ".join(policy.employee_type_ids.mapped('name'))
                current_type_name = emp_type.name if emp_type else _("Unassigned")
                raise ValidationError(_(
                    "Employee '%s' has Employee Type '%s'. Policy '%s' is only applicable to: %s."
                ) % (emp.name, current_type_name, policy.name, allowed_types))

        # 3. Minimum Tenure Guard
        if policy.min_service_period_days > 0:
            join_date = self._resolve_employee_joining_date(emp)
            if join_date:
                ref_date = self.request_date or fields.Date.today()
                service_days = (ref_date - join_date).days
                if service_days < policy.min_service_period_days:
                    raise ValidationError(_(
                        "Employee '%s' has %s days of service, which is below the policy minimum of %s days."
                    ) % (emp.name, service_days, policy.min_service_period_days))

        # 4. Requested Days Positive & Per-Request Limit
        if self.requested_days <= 0.0:
            raise ValidationError(_("Requested encashment days must be greater than zero."))
        if policy.max_encashable_days_per_request > 0.0 and self.requested_days > policy.max_encashable_days_per_request:
            raise ValidationError(_(
                "Requested %s days exceeds the maximum limit of %s days allowed per request under policy '%s'."
            ) % (self.requested_days, policy.max_encashable_days_per_request, policy.name))

        # 5. Leave Type Configured Guard
        if policy.leave_type_ids and self.leave_type_id not in policy.leave_type_ids:
            raise ValidationError(_(
                "Leave type '%s' is not allowed under policy '%s'."
            ) % (self.leave_type_id.name, policy.name))
        if not getattr(self.leave_type_id, 'include_in_leave_encashment', False):
            raise ValidationError(_(
                "Leave type '%s' does not have 'Include in Leave Encashment' enabled."
            ) % self.leave_type_id.name)

        # 6. Safety Buffer / Retention Guard (Preventing Encashment to Zero)
        self._compute_balances()
        if self.available_balance < self.requested_days:
            raise ValidationError(_(
                "Insufficient leave balance. Available: %s days, Requested: %s days."
            ) % (self.available_balance, self.requested_days))

        retained_balance = self.available_balance - self.requested_days
        if policy.min_balance_to_maintain > 0.0 and retained_balance < policy.min_balance_to_maintain:
            raise ValidationError(_(
                "Policy '%s' mandates retaining at least %s days in leave balance. Encashing %s days leaves only %s days."
            ) % (policy.name, policy.min_balance_to_maintain, self.requested_days, retained_balance))

        # 7. Annual Fiscal Year Encashment Cap Guard
        if policy.max_encashable_days_per_year > 0.0:
            req_date = self.request_date or fields.Date.today()
            # Indian Financial Year: April 1 to March 31
            fy_start = fields.Date.from_string(f"{req_date.year if req_date.month >= 4 else req_date.year - 1}-04-01")
            fy_end = fields.Date.from_string(f"{req_date.year + 1 if req_date.month >= 4 else req_date.year}-03-31")

            past_requests = self.sudo().search([
                ('employee_id', '=', emp.id),
                ('policy_id', '=', policy.id),
                ('state', 'in', ('approved', 'paid')),
                ('request_date', '>=', fy_start),
                ('request_date', '<=', fy_end),
                ('id', '!=', self.id),
            ])
            already_encashed = sum(past_requests.mapped('requested_days'))
            if (already_encashed + self.requested_days) > policy.max_encashable_days_per_year:
                raise ValidationError(_(
                    "Annual limit exceeded. Employee has already encashed %s days in FY %s-%s. "
                    "Adding %s days exceeds the maximum policy limit of %s days."
                ) % (already_encashed, fy_start.year, fy_end.year, self.requested_days, policy.max_encashable_days_per_year))

    def _resolve_employee_joining_date(self, employee):
        """Resolves employee joining or service start date using robust fallbacks."""
        emp = employee.sudo()
        for fname in ('first_contract_date', 'hds_in_gratuity_joining_date', 'joining_date', 'date_of_joining', 'hds_in_doj'):
            val = getattr(emp, fname, False)
            if val:
                return fields.Date.from_string(val)
        contracts = self.env(su=True)['hr.version'].search([
            ('employee_id', '=', emp.id)
        ], order='contract_date_start asc, date_version asc, id asc', limit=1)
        if contracts:
            start_val = contracts.contract_date_start or contracts.date_version or getattr(contracts, 'date_start', False)
            if start_val:
                return fields.Date.from_string(start_val)
        return fields.Date.from_string(emp.create_date) if emp.create_date else fields.Date.today()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not self.env.context.get('install_mode'):
                emp = self.env['hr.employee'].browse(vals.get('employee_id')) if vals.get('employee_id') else False
                comp = (emp.company_id if emp and emp.company_id else False) or self.env.company
                if comp and hasattr(comp, 'hds_in_enable_leave_encashment') and not comp.hds_in_enable_leave_encashment:
                    raise ValidationError(_(
                        "Leave Encashment is disabled for company '%s'. Please enable it in Company / Payroll Settings before submitting requests."
                    ) % comp.name)

            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hds.leave.encashment.request') or _('New')

        return super().create(vals_list)

    # -------------------------------------------------------------------------
    # WORKFLOW ACTIONS
    # -------------------------------------------------------------------------
    def action_submit(self):
        """Submit the request for management approval."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only draft requests can be submitted."))
            rec._validate_request_eligibility()
            rec.write({'state': 'submitted'})
        return True

    def action_approve(self):
        """Approve the request for payroll inclusion and deduct leave allocation balance immediately."""
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("Only submitted requests can be approved."))
            rec._validate_request_eligibility()
            # Deduct balance directly from leave allocation to prevent calendar collisions & double-dipping (Solution 1)
            rec._deduct_leave_allocation()
            rec.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'approval_date': fields.Datetime.now()
            })
        return True

    def _deduct_leave_allocation(self, payslip=None):
        """
        Deducts requested encashment days directly from the employee's active leave allocation(s).
        Uses FIFO order (soonest expiring allocations first) to deduct the unavailed balance.
        Creates ZERO hr.leave calendar records, completely eliminating work entry / attendance
        collisions and double payment under pay_by_attendance (Solution 1).
        """
        self.ensure_one()
        if self.deducted_days > 0.0:
            return self.allocation_id

        alloc_model = self.env['hr.leave.allocation'].sudo()
        alloc_field = 'work_entry_type_id' if 'work_entry_type_id' in alloc_model._fields else 'holiday_status_id'

        ref_date = self.request_date or fields.Date.today()
        domain = [
            ('employee_id', '=', self.employee_id.id),
            (alloc_field, '=', self.leave_type_id.id),
            ('state', '=', 'validate'),
            '|',
            ('date_from', '=', False),
            ('date_from', '<=', ref_date),
            '|',
            ('date_to', '=', False),
            ('date_to', '>=', ref_date),
        ]

        allocations = alloc_model.search(domain)
        if not allocations:
            raise ValidationError(_(
                "No active validated leave allocations found for employee '%s' and leave type '%s'."
            ) % (self.employee_id.name, self.leave_type_id.name))

        # FIFO ordering: expiring allocations first (chronological date_to), non-expiring last
        sorted_allocations = sorted(
            allocations,
            key=lambda a: (0, a.date_to) if a.date_to else (1, a.id)
        )

        days_needed = float(self.requested_days)
        deduction_records = []
        primary_alloc = None

        for alloc in sorted_allocations:
            if days_needed <= 0.0:
                break

            # Calculate remaining balance available in this allocation (in days)
            if hasattr(alloc, 'virtual_remaining_leaves'):
                rem_raw = float(alloc.virtual_remaining_leaves)
                uom = getattr(alloc.work_entry_type_id, 'unit_of_measure', 'day') if hasattr(alloc, 'work_entry_type_id') else 'day'
                if uom == 'hour':
                    hours_per_day = (
                        self.employee_id.resource_calendar_id.hours_per_day
                        if self.employee_id and getattr(self.employee_id, 'resource_calendar_id', None) and self.employee_id.resource_calendar_id.hours_per_day
                        else 8.0
                    )
                    avail_in_alloc = rem_raw / (hours_per_day or 8.0)
                else:
                    avail_in_alloc = rem_raw
            else:
                taken = float(getattr(alloc, 'leaves_taken', 0.0) or 0.0)
                avail_in_alloc = float(alloc.number_of_days - taken)

            # Cap avail_in_alloc at allocation's total days as upper bound
            avail_in_alloc = min(avail_in_alloc, float(alloc.number_of_days))

            if avail_in_alloc <= 0.0:
                continue

            to_deduct = min(days_needed, avail_in_alloc)
            new_number_of_days = max(0.0, float(alloc.number_of_days - to_deduct))

            alloc.write({'number_of_days': new_number_of_days})

            deduction_records.append({
                'allocation_id': alloc.id,
                'allocation_name': alloc.name or f"Allocation #{alloc.id}",
                'days': to_deduct,
                'original_number_of_days': alloc.number_of_days + to_deduct,
                'new_number_of_days': new_number_of_days,
            })

            if not primary_alloc:
                primary_alloc = alloc

            days_needed -= to_deduct

        total_deducted = sum(r['days'] for r in deduction_records)
        if total_deducted < self.requested_days:
            # Roll back any partial deductions before raising
            for r in deduction_records:
                a = alloc_model.browse(r['allocation_id'])
                if a.exists():
                    a.write({'number_of_days': r['original_number_of_days']})
            raise ValidationError(_(
                "Insufficient unavailed leave balance in active allocations for employee '%s'. "
                "Requested: %s days, Available across allocations: %s days."
            ) % (self.employee_id.name, self.requested_days, total_deducted))

        import json
        self.write({
            'allocation_id': primary_alloc.id if primary_alloc else False,
            'deducted_days': total_deducted,
            'deducted_allocation_data': json.dumps(deduction_records),
        })

        alloc_desc = f"{primary_alloc.name} (#{primary_alloc.id})" if primary_alloc else ""
        if len(deduction_records) > 1:
            alloc_desc = ", ".join(f"{r['allocation_name']} ({r['days']} days)" for r in deduction_records)
        try:
            self.message_post(body=_(
                "Leave balance deducted directly from allocation: %s days (%s)."
            ) % (total_deducted, alloc_desc))
        except Exception:
            pass

        return primary_alloc

    def _restore_leave_allocation(self):
        """
        Restores deducted days back to the employee's leave allocation(s).
        Called upon request rejection, cancellation, reset to draft, or deletion.
        """
        self.ensure_one()
        import json

        alloc_model = self.env['hr.leave.allocation'].sudo()
        restored_days = 0.0

        if self.deducted_allocation_data:
            try:
                breakdown = json.loads(self.deducted_allocation_data)
                for entry in breakdown:
                    alloc_id = entry.get('allocation_id')
                    days = float(entry.get('days', 0.0))
                    if alloc_id and days > 0.0:
                        alloc = alloc_model.browse(alloc_id)
                        if alloc.exists():
                            alloc.write({'number_of_days': alloc.number_of_days + days})
                            restored_days += days
            except Exception as e:
                _logger.error("Failed to restore allocation breakdown for request %s: %s", self.id, str(e))
                if self.allocation_id and self.deducted_days > 0:
                    if self.allocation_id.exists():
                        self.allocation_id.sudo().write({
                            'number_of_days': self.allocation_id.number_of_days + self.deducted_days
                        })
                        restored_days = self.deducted_days
        elif self.allocation_id and self.deducted_days > 0:
            if self.allocation_id.exists():
                self.allocation_id.sudo().write({
                    'number_of_days': self.allocation_id.number_of_days + self.deducted_days
                })
                restored_days = self.deducted_days

        # Also unlink legacy hr.leave record if present from pre-migration records
        if self.leave_id and self.leave_id.exists():
            try:
                if self.leave_id.state == 'validate' and hasattr(self.leave_id, 'action_refuse'):
                    self.leave_id.sudo().action_refuse()
                self.leave_id.sudo().unlink()
            except Exception as e:
                _logger.warning("Could not refuse/unlink legacy leave record %s: %s", self.leave_id.id, str(e))

        if restored_days > 0:
            try:
                self.message_post(body=_(
                    "Leave balance restored to allocation(s): %s days."
                ) % restored_days)
            except Exception:
                pass

        self.write({
            'allocation_id': False,
            'deducted_days': 0.0,
            'deducted_allocation_data': False,
            'leave_id': False,
        })
        return True

    def _create_or_validate_time_off_deduction(self, payslip=None):
        """
        Backwards compatibility alias for _deduct_leave_allocation.
        """
        return self._deduct_leave_allocation(payslip=payslip)

    def action_reject(self):
        """Reject the request and restore deducted leave allocation balance."""
        for rec in self:
            if rec.state not in ('submitted', 'approved'):
                raise UserError(_("Cannot reject request in state '%s'.") % rec.state)
            rec._restore_leave_allocation()
            rec.write({'state': 'rejected'})
        return True

    def action_cancel(self):
        """Cancel request and restore deducted leave allocation balance."""
        for rec in self:
            if rec.state == 'paid':
                raise UserError(_("Cannot cancel an already paid encashment request. Please cancel the payslip first."))
            rec._restore_leave_allocation()
            rec.write({'state': 'cancelled', 'payslip_id': False})
        return True

    def action_draft(self):
        """Reset request to draft and restore deducted leave allocation balance."""
        for rec in self:
            if rec.state in ('paid',):
                raise UserError(_("Cannot reset a paid encashment request to draft."))
            rec._restore_leave_allocation()
            rec.write({'state': 'draft', 'payslip_id': False})
        return True

    # -------------------------------------------------------------------------
    # PAYSLIP HOOKS: BALANCE DEDUCTION & ROLLBACK
    # -------------------------------------------------------------------------
    def action_finalize_payout(self, payslip):
        """
        Executed automatically when hr.payslip transitions to 'done'.
        Finalizes the payout and marks request state as 'paid'.
        """
        self.ensure_one()
        if self.state != 'approved':
            return False

        if not self.deducted_days:
            self._deduct_leave_allocation(payslip=payslip)

        self.write({
            'state': 'paid',
            'payslip_id': payslip.id,
        })
        return True

    def action_rollback_payout(self):
        """
        Executed automatically when hr.payslip is cancelled.
        Reverses the payout association and restores request state to 'approved'.
        The allocation deduction remains active while the request is still approved.
        """
        self.ensure_one()
        self.write({
            'state': 'approved',
            'payslip_id': False,
        })
        return True

    def unlink(self):
        """Guard against deleting paid encashments and restore allocations on approved requests."""
        for rec in self:
            if rec.state == 'paid':
                raise UserError(_("Cannot delete an encashment request that has already been paid. Please cancel the payslip first."))
            if rec.state == 'approved':
                rec._restore_leave_allocation()
        return super().unlink()
