# -*- coding: utf-8 -*-
from datetime import date, timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class HrResignation(models.Model):
    """
    Country-Agnostic Model for Employee Resignation & Exit Lifecycle.
    Provides standard notice period calculation, multi-tier approvals,
    department clearances, and pluggable settlement hooks.
    """
    _name = 'hr.resignation'
    _description = 'Employee Resignation & Exit'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'display_name'

    name = fields.Char(
        string='Reference',
        copy=False,
        readonly=True,
        index=True,
        default=lambda self: _('New')
    )
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        default=lambda self: self.env.user.employee_id,
        tracking=True
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
        readonly=True
    )
    manager_id = fields.Many2one(
        'hr.employee',
        string='Manager',
        related='employee_id.parent_id',
        store=True,
        readonly=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        readonly=True
    )

    resignation_type = fields.Selection([
        ('resigned', 'Normal Resignation'),
        ('terminated', 'Termination / Fired'),
        ('retired', 'Retirement'),
        ('end_of_contract', 'End of Contract'),
        ('mutual', 'Mutual Agreement'),
    ], string='Exit Type', default='resigned', required=True, tracking=True)

    request_date = fields.Date(
        string='Request Date',
        default=fields.Date.context_today,
        required=True,
        tracking=True
    )
    resign_confirm_date = fields.Date(
        string='Confirmed Date',
        readonly=True,
        tracking=True,
        help="Date when employee/HR confirmed the resignation request."
    )
    joined_date = fields.Date(
        string='Joining Date',
        compute='_compute_joined_date',
        store=True,
        readonly=False,
        help="Date when employee joined the organization."
    )
    expected_revealing_date = fields.Date(
        string='Requested Last Working Day',
        required=True,
        tracking=True,
        help="Date requested by the employee as their last working day."
    )
    approved_revealing_date = fields.Date(
        string='Approved Last Working Day',
        tracking=True,
        help="Final approved last working day confirmed by management/HR."
    )
    notice_period = fields.Integer(
        string='Notice Period (Days)',
        compute='_compute_notice_period',
        store=True,
        readonly=False,
        help="Applicable notice period in days from active contract."
    )
    employee_contract = fields.Char(
        string='Contract / Template',
        compute='_compute_employee_contract',
        store=True,
        help="Name of active employment contract version."
    )
    notice_shortage_days = fields.Integer(
        string='Notice Shortage (Days)',
        compute='_compute_notice_shortage',
        store=True,
        help="Shortfall in days if employee leaves before completing required notice period."
    )
    reason = fields.Text(
        string='Reason for Leaving',
        required=True,
        tracking=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
        ('approved', 'Approved'),
        ('done', 'Relieved / Completed'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, required=True)

    # Department Clearances
    clearance_line_ids = fields.One2many(
        'hudson.exit.clearance',
        'resignation_id',
        string='Clearance Checklist'
    )
    clearance_status = fields.Selection([
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('cleared', 'All Cleared'),
        ('rejected', 'Issues Pending'),
    ], string='Clearance Status', compute='_compute_clearance_status', store=True)

    # Pluggable settlement hook (overridden by country modules e.g. hudson_in_final_settlement)
    settlement_count = fields.Integer(
        string='Settlements Count',
        compute='_compute_settlement_count'
    )

    notes = fields.Html(string='Internal Notes')

    @api.depends('name', 'employee_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.name or _('New')} - {rec.employee_id.name or ''}"

    @api.depends('employee_id')
    def _compute_joined_date(self):
        for rec in self:
            emp = rec.employee_id
            if emp:
                rec.joined_date = (
                    getattr(emp, 'joining_date', False) or
                    getattr(emp, 'first_contract_date', False) or
                    (emp.create_date.date() if emp.create_date else fields.Date.today())
                )
            else:
                rec.joined_date = False

    @api.depends('employee_id')
    def _compute_employee_contract(self):
        for rec in self:
            emp = rec.employee_id
            version = False
            if emp and 'hr.version' in self.env:
                version = getattr(emp, 'version_id', None) or self.env['hr.version'].sudo().search([
                    ('employee_id', '=', emp.id)
                ], order='id desc', limit=1)
            if version:
                template = getattr(version, 'contract_template_id', None)
                rec.employee_contract = template.name if template else version.name
            else:
                rec.employee_contract = _('Standard')

    @api.depends('employee_id')
    def _compute_notice_period(self):
        for rec in self:
            emp = rec.employee_id
            version = False
            if emp and 'hr.version' in self.env:
                version = getattr(emp, 'version_id', None) or self.env['hr.version'].sudo().search([
                    ('employee_id', '=', emp.id)
                ], order='id desc', limit=1)
            if version:
                rec.notice_period = getattr(version, 'notice_days', 30) or 30
            else:
                rec.notice_period = 30

    @api.depends('request_date', 'expected_revealing_date', 'approved_revealing_date', 'notice_period')
    def _compute_notice_shortage(self):
        """Calculate shortage days if exiting earlier than full notice period."""
        for rec in self:
            relieving_date = rec.approved_revealing_date or rec.expected_revealing_date
            if rec.request_date and relieving_date and rec.notice_period:
                served_days = (relieving_date - rec.request_date).days
                shortage = rec.notice_period - served_days
                rec.notice_shortage_days = max(0, shortage)
            else:
                rec.notice_shortage_days = 0

    @api.depends('clearance_line_ids', 'clearance_line_ids.state')
    def _compute_clearance_status(self):
        for rec in self:
            lines = rec.clearance_line_ids
            if not lines:
                rec.clearance_status = 'not_started'
            elif any(l.state == 'rejected' for l in lines):
                rec.clearance_status = 'rejected'
            elif all(l.state == 'cleared' for l in lines):
                rec.clearance_status = 'cleared'
            else:
                rec.clearance_status = 'in_progress'

    def _compute_settlement_count(self):
        """Extensible hook for settlement modules."""
        for rec in self:
            rec.settlement_count = 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('hr.resignation') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        self.ensure_one()
        if not self.expected_revealing_date:
            raise UserError(_("Please provide the requested last working day."))
        self.write({
            'state': 'confirm',
            'resign_confirm_date': fields.Date.today()
        })
        self.message_post(body=_("Resignation request confirmed and submitted for review."))

    def action_approve(self):
        self.ensure_one()
        if not self.approved_revealing_date:
            self.approved_revealing_date = self.expected_revealing_date
        self.write({'state': 'approved'})
        self._generate_default_clearances()
        self.message_post(body=_(
            "Resignation approved. Final last working day set to %s. Clearance tasks generated.",
            self.approved_revealing_date
        ))

    def action_done(self):
        """Mark employee as relieved."""
        self.ensure_one()
        if self.clearance_status not in ('cleared', 'not_started'):
            raise UserError(_("Cannot complete exit process while department clearances are pending or rejected."))
        self.write({'state': 'done'})
        # Update employee status / archive if appropriate
        if self.employee_id and self.approved_revealing_date:
            self.employee_id.message_post(body=_(
                "Employee formally relieved on %s following resignation %s.",
                self.approved_revealing_date, self.name
            ))
        self.message_post(body=_("Exit process completed."))

    def action_cancel(self):
        self.ensure_one()
        self.write({'state': 'cancel'})
        self.message_post(body=_("Resignation request cancelled."))

    def action_draft(self):
        self.ensure_one()
        self.write({'state': 'draft'})

    def _generate_default_clearances(self):
        """Generate standard department clearance checklist if empty."""
        self.ensure_one()
        if self.clearance_line_ids:
            return
        default_departments = [
            ('it', _('IT Department'), _('Handover of Laptop, Peripherals, Revoke Email, VPN and System Access')),
            ('finance', _('Finance & Accounts'), _('Settle Travel Advances, Company Loans, Pending Expense Claims')),
            ('admin', _('Administration / Facilities'), _('Handover of Company ID Card, Access Keys, Parking Pass')),
            ('hr', _('Human Resources'), _('Exit Interview, Document Returns, Signed Non-Disclosure Agreement')),
        ]
        lines = []
        for dept_code, dept_name, item_desc in default_departments:
            lines.append((0, 0, {
                'department_type': dept_code,
                'name': dept_name,
                'description': item_desc,
                'state': 'pending',
            }))
        self.write({'clearance_line_ids': lines})

    def action_open_final_settlement(self):
        """Pluggable hook overridden by country localization modules."""
        self.ensure_one()
        raise UserError(_("No statutory settlement engine is configured for this jurisdiction. Install the country-specific final settlement module (e.g. hudson_in_final_settlement)."))

    def action_create_final_settlement(self):
        """Pluggable hook overridden by country localization modules."""
        self.ensure_one()
        raise UserError(_("No statutory settlement engine is configured for this jurisdiction. Install the country-specific final settlement module (e.g. hudson_in_final_settlement)."))
