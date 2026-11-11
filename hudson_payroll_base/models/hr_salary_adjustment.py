# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrSalaryAdjustment(models.Model):
    """
    Employee-specific recurring or one-time payroll adjustment.
    Provides an Other Input to payroll; Salary Rules determine how that input impacts Net Salary.
    """
    _name = 'hr.salary.adjustment'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Salary Adjustment'
    _order = 'priority desc, date_start desc, id desc'

    name = fields.Char(
        string='Reference',
        compute='_compute_name',
        store=True,
        readonly=True
    )
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Very High'),
    ], string='Priority', default='0', tracking=True)

    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        tracking=True,
        index=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]"
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
        index=True
    )
    country_id = fields.Many2one(
        'res.country',
        string='Country',
        related='company_id.country_id',
        store=True,
        readonly=True,
        help="Country of company. Allows both global (country-independent) and country-specific input types."
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        readonly=True
    )
    contract_id = fields.Many2one(
        'hr.version',
        string='Contract',
        compute='_compute_contract_id',
        store=True,
        readonly=False,
        help="Contract to which this adjustment applies."
    )
    input_type_id = fields.Many2one(
        'hr.payslip.input.type',
        string='Type',
        required=True,
        tracking=True,
        index=True,
        domain="['|', ('country_id', '=', False), ('country_id', '=', country_id)]",
        help="Other Input Type linked to this adjustment (supports global and country-specific types)."
    )
    input_code = fields.Char(
        string='Input Code',
        related='input_type_id.code',
        store=True,
        readonly=True,
        index=True
    )
    amount = fields.Monetary(
        string='Amount',
        required=True,
        currency_field='currency_id',
        tracking=True,
        help="Adjustment amount applied per payslip period."
    )
    negative = fields.Boolean(
        string='Negative Value',
        default=False,
        tracking=True,
        help="If checked, the adjustment passes a negative value to the payslip input."
    )
    duration = fields.Selection([
        ('one_time', 'One Time'),
        ('limited', 'Limited'),
        ('unlimited', 'Unlimited'),
    ], string='Duration', default='one_time', required=True, tracking=True)
    repeat = fields.Boolean(
        string='Repeat',
        compute='_compute_repeat',
        inverse='_inverse_repeat',
        help="Apply on every payslip until the End Date, or until the end of the contract when no End Date is set."
    )

    date_start = fields.Date(
        string='Start Date',
        required=True,
        default=fields.Date.today,
        tracking=True
    )
    date_end = fields.Date(
        string='End Date',
        tracking=True,
        help="Final date of applicability for limited adjustments."
    )
    until_amount = fields.Monetary(
        string='Until',
        currency_field='currency_id',
        tracking=True,
        help="Maximum cumulative amount limit or target cap for this adjustment."
    )
    beneficiary_bank_id = fields.Many2one(
        'res.partner.bank',
        string='Beneficiary Bank Account',
        compute='_compute_beneficiary_bank',
        store=True,
        readonly=False,
        help="Destination bank account for this adjustment. Dynamically defaults to the employee's bank account from their profile, or can be set to an external beneficiary (e.g. child support, creditor)."
    )
    note = fields.Char(
        string='Note',
        tracking=True,
        help="Short description or reason for the adjustment."
    )
    state = fields.Selection([
        ('running', 'Active (Running)'),
        ('done', 'Completed / Closed'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='running', required=True, tracking=True, index=True)

    payslip_input_ids = fields.One2many(
        'hr.payslip.input',
        'adjustment_id',
        string='Applied Payslip Inputs',
        readonly=True
    )
    applied_count = fields.Integer(
        string='Applied Payslips Count',
        compute='_compute_applied_count'
    )

    @api.depends('employee_id', 'input_type_id', 'date_start')
    def _compute_name(self):
        for rec in self:
            emp = rec.employee_id.name or _('Employee')
            type_name = rec.input_type_id.name or _('Adjustment')
            date_str = rec.date_start.strftime('%b %Y') if rec.date_start else ''
            rec.name = f"{emp} - {type_name} ({date_str})" if date_str else f"{emp} - {type_name}"

    @api.depends('employee_id', 'company_id')
    def _compute_contract_id(self):
        for rec in self:
            if rec.employee_id:
                contract = rec.employee_id.version_id
                if not contract:
                    contract = self.env['hr.version'].search([
                        ('employee_id', '=', rec.employee_id.id),
                        ('company_id', '=', rec.company_id.id),
                    ], limit=1, order='id desc')
                rec.contract_id = contract
            else:
                rec.contract_id = False

    @api.depends('duration')
    def _compute_repeat(self):
        for rec in self:
            rec.repeat = rec.duration != 'one_time'

    def _inverse_repeat(self):
        for rec in self:
            if not rec.repeat:
                rec.duration = 'one_time'
            elif rec.duration == 'one_time':
                rec.duration = 'limited' if rec.date_end else 'unlimited'

    @api.onchange('repeat', 'date_end')
    def _onchange_repeat(self):
        """Repeat unticked -> one time; ticked with an End Date -> limited; without -> until contract end."""
        if not self.repeat:
            self.duration = 'one_time'
        elif self.date_end:
            self.duration = 'limited'
        elif self.duration == 'one_time' or self.env.context.get('payslip_adjustment_repeat_ui'):
            # The context flag comes from the employee 'Payslip Adjustments' tab, where Repeat replaces
            # the Duration selector; elsewhere keep a manually chosen duration untouched.
            self.duration = 'unlimited'

    @api.onchange('duration')
    def _onchange_duration(self):
        if self.duration != 'limited':
            self.date_end = False
            self.until_amount = 0.0

    @api.model
    def _get_employee_bank_account(self, employee):
        """Fetch the employee's primary bank account from hr.employee or related partner."""
        if not employee:
            return False
        # 1. Primary or computed bank_account_id on hr.employee
        if employee.bank_account_id:
            return employee.bank_account_id
        # 2. primary_bank_account_id (Odoo salary distribution)
        primary = getattr(employee, 'primary_bank_account_id', False)
        if primary:
            return primary
        # 3. First record in employee's bank_account_ids
        bank_accounts = getattr(employee, 'bank_account_ids', False)
        if bank_accounts:
            return bank_accounts[0]
        # 4. Fallback to work contact or private address partner bank accounts
        for partner in (getattr(employee, 'work_contact_id', False), getattr(employee, 'address_home_id', False)):
            if partner and getattr(partner, 'bank_ids', False) and partner.bank_ids:
                return partner.bank_ids[0]
        return False

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            if self.employee_id.company_id:
                self.company_id = self.employee_id.company_id
            self.beneficiary_bank_id = self._get_employee_bank_account(self.employee_id)
        else:
            self.beneficiary_bank_id = False

    @api.depends('employee_id', 'employee_id.bank_account_id', 'employee_id.bank_account_ids')
    def _compute_beneficiary_bank(self):
        for rec in self:
            if rec.employee_id:
                rec.beneficiary_bank_id = rec._get_employee_bank_account(rec.employee_id)
            else:
                rec.beneficiary_bank_id = False

    @api.depends('payslip_input_ids')
    def _compute_applied_count(self):
        for rec in self:
            rec.applied_count = len(rec.payslip_input_ids.mapped('payslip_id'))

    @api.onchange('company_id')
    def _onchange_company_id(self):
        if self.employee_id and self.employee_id.company_id and self.employee_id.company_id != self.company_id:
            self.employee_id = False

    @api.constrains('date_start', 'date_end', 'duration')
    def _check_dates(self):
        for rec in self:
            if rec.duration == 'limited':
                if not rec.date_end:
                    raise ValidationError(_("End Date is mandatory for Limited duration adjustments."))
                if rec.date_end < rec.date_start:
                    raise ValidationError(_("End Date cannot be before Start Date."))

    @api.constrains('amount', 'until_amount', 'duration')
    def _check_amounts(self):
        for rec in self:
            if rec.amount <= 0.0:
                raise ValidationError(_("Adjustment amount must be strictly greater than 0.0."))
            if rec.duration == 'limited' and rec.until_amount:
                if rec.until_amount <= 0.0:
                    raise ValidationError(_("Until Cap Amount must be strictly greater than 0.0 if specified."))

    @api.constrains('employee_id', 'company_id')
    def _check_company_consistency(self):
        for rec in self:
            if rec.employee_id and rec.company_id and rec.employee_id.company_id:
                if rec.employee_id.company_id != rec.company_id:
                    raise ValidationError(_(
                        "The Employee '%(employee)s' belongs to company '%(emp_comp)s', "
                        "which does not match the Adjustment Company '%(adj_comp)s'."
                    ) % {
                        'employee': rec.employee_id.name,
                        'emp_comp': rec.employee_id.company_id.name,
                        'adj_comp': rec.company_id.name,
                    })

    def _get_effective_date_end(self):
        """Last date this adjustment applies to.

        One-time: only the payslip whose period contains the Start Date.
        Repeating: its own End Date, else the end of the employee's contract.
        """
        self.ensure_one()
        if self.duration == 'one_time':
            return self.date_start
        if self.date_end:
            return self.date_end
        contract = (self.contract_id or self.employee_id.version_id).sudo()
        return contract.contract_date_end or False

    def _sync_to_draft_payslips(self):
        """Propagate adjustment changes immediately to any existing draft or verify payslips covering this adjustment period."""
        if self.env.context.get('skip_adjustment_sync'):
            return
        Payslip = self.env['hr.payslip']
        for adj in self:
            if not adj.employee_id:
                continue
            domain = [
                ('employee_id', '=', adj.employee_id.id),
                ('state', 'in', ('draft', 'verify')),
                ('date_to', '>=', adj.date_start),
            ]
            date_end = adj._get_effective_date_end()
            if date_end:
                domain.append(('date_from', '<=', date_end))
            if adj.company_id:
                domain.append(('company_id', '=', adj.company_id.id))
            draft_slips = Payslip.search(domain)
            for slip in draft_slips:
                slip._sync_salary_adjustments()
                if slip.line_ids:
                    slip.action_compute_sheet()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('duration') and vals['duration'] != 'limited':
                vals['date_end'] = False
                vals['until_amount'] = 0.0
        records = super().create(vals_list)
        records.filtered(lambda r: r.state == 'running')._sync_to_draft_payslips()
        return records

    def write(self, vals):
        if vals.get('duration') and vals['duration'] != 'limited':
            vals['date_end'] = False
            vals['until_amount'] = 0.0
        res = super().write(vals)
        if any(f in vals for f in ('amount', 'negative', 'state', 'input_type_id', 'date_start', 'date_end', 'until_amount', 'employee_id', 'company_id')):
            self._sync_to_draft_payslips()
        return res

    def unlink(self):
        # 1. Protect finalized payroll history: prevent deleting adjustments already applied to done or paid payslips
        for adj in self:
            finalized_slips = adj.payslip_input_ids.mapped('payslip_id').filtered(lambda p: p.state in ('done', 'paid'))
            if finalized_slips:
                raise ValidationError(_(
                    "You cannot delete the salary adjustment '%(name)s' because it has already been applied "
                    "to %(count)s finalized (validated/paid) payslip(s). Please cancel or close it instead."
                ) % {'name': adj.name, 'count': len(finalized_slips)})

        draft_slips = self.env['hr.payslip']
        for adj in self:
            if adj.employee_id:
                domain = [
                    ('employee_id', '=', adj.employee_id.id),
                    ('state', 'in', ('draft', 'verify')),
                    ('date_to', '>=', adj.date_start),
                ]
                date_end = adj._get_effective_date_end()
                if date_end:
                    domain.append(('date_from', '<=', date_end))
                if adj.company_id:
                    domain.append(('company_id', '=', adj.company_id.id))
                draft_slips |= self.env['hr.payslip'].search(domain)

        # Only clean up inputs on unconfirmed payslips
        input_lines = self.env['hr.payslip.input'].search([
            ('adjustment_id', 'in', self.ids),
            ('payslip_id.state', 'in', ('draft', 'verify')),
        ])
        draft_slips |= input_lines.mapped('payslip_id')
        input_lines.unlink()
        res = super().unlink()
        for slip in draft_slips:
            if slip.exists():
                slip._sync_salary_adjustments()
                if slip.line_ids:
                    slip.action_compute_sheet()
        return res

    def action_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_reset_running(self):
        self.write({'state': 'running'})

    def action_view_payslips(self):
        self.ensure_one()
        payslips = self.payslip_input_ids.mapped('payslip_id')
        action = {
            'name': _('Applied Payslips - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'hr.payslip',
            'view_mode': 'list,form',
            'domain': [('id', 'in', payslips.ids)],
            'target': 'current',
        }
        if len(payslips) == 1:
            action['res_id'] = payslips.id
            action['view_mode'] = 'form'
        return action

