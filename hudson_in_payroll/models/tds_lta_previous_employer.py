# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class TdsLtaPreviousEmployer(models.Model):
    """
    Employee-level Previous Employer LTA History Model.
    Stores an employee's previous-employer LTA usage to determine whether a statutory
    carry-forward entitlement from the previous 4-calendar-year block exists.
    """
    _name = 'tds.lta.previous.employer'
    _description = 'Previous Employer LTA History'
    _order = 'employment_to desc, id desc'

    employee_id = fields.Many2one('hr.employee', string="Employee", required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')

    previous_employer_name = fields.Char(string="Previous Employer Name", required=True, default="Previous Employer")
    employment_from = fields.Date(string="Employment From")
    employment_to = fields.Date(string="Employment To")

    # Block Period Computation (Derived dynamically from employment_to or journey evaluation year)
    previous_block_start = fields.Integer(string="Previous Block Start Year", compute='_compute_block_period', store=True)
    previous_block_end = fields.Integer(string="Previous Block End Year", compute='_compute_block_period', store=True)
    previous_block_period = fields.Char(string="Previous LTA Block", compute='_compute_block_period', store=True, readonly=True)

    previous_lta_claims_used = fields.Selection([
        ('none', 'None'),
        ('one', 'One'),
        ('two', 'Two'),
        ('unknown', 'Unknown')
    ], string="LTA Journeys Used", default='unknown', required=True, help="Number of LTA claims claimed during employment at previous employer.")

    carry_forward_requested = fields.Boolean(string="Carry-Forward Requested", default=False)
    carry_forward_eligible = fields.Selection([
        ('pending', 'Pending Verification'),
        ('eligible', 'Eligible'),
        ('ineligible', 'Ineligible')
    ], string="Carry-Forward Eligibility", compute='_compute_verification_and_eligibility', store=True, readonly=True)

    # Verification Workflow
    verification_status = fields.Selection([
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected')
    ], string="Verification Status", default='pending', required=True, tracking=True)

    verification_remarks = fields.Text(string="Verification Remarks")
    verified_by = fields.Many2one('res.users', string="Verified By", readonly=True)
    verified_on = fields.Datetime(string="Verified On", readonly=True)

    attachment_ids = fields.Many2many('ir.attachment', 'tds_lta_prev_emp_attach_rel', 'prev_id', 'attachment_id', string="Supporting Documents")
    claim_ids = fields.One2many('tds.lta.previous.employer.claim', 'previous_history_id', string="Previous LTA Journey Claims")

    @api.depends('employment_to', 'employment_from')
    def _compute_block_period(self):
        for rec in self:
            ref_date = rec.employment_to or rec.employment_from or fields.Date.today()
            ref_year = ref_date.year if hasattr(ref_date, 'year') else int(str(ref_date)[:4])
            base_year = 1986 + ((ref_year - 1986) // 4) * 4
            rec.previous_block_start = base_year
            rec.previous_block_end = base_year + 3
            rec.previous_block_period = f"{base_year}-{base_year + 3}"

    @api.depends('verification_status', 'previous_lta_claims_used', 'carry_forward_requested')
    def _compute_verification_and_eligibility(self):
        for rec in self:
            if rec.verification_status != 'verified':
                if rec.verification_status == 'rejected':
                    rec.carry_forward_eligible = 'ineligible'
                else:
                    rec.carry_forward_eligible = 'pending'
            elif rec.previous_lta_claims_used == 'unknown':
                rec.carry_forward_eligible = 'pending'
            elif rec.previous_lta_claims_used in ('none', 'one') and rec.carry_forward_requested:
                rec.carry_forward_eligible = 'eligible'
            else:
                rec.carry_forward_eligible = 'ineligible'

    def action_verify(self):
        """HR action to verify previous employer LTA history."""
        self.write({
            'verification_status': 'verified',
            'verified_by': self.env.user.id,
            'verified_on': fields.Datetime.now(),
        })

    def action_reject(self):
        """HR action to reject previous employer LTA history."""
        self.write({
            'verification_status': 'rejected',
            'verified_by': self.env.user.id,
            'verified_on': fields.Datetime.now(),
        })

    def action_reset_pending(self):
        """Reset verification to pending."""
        self.write({
            'verification_status': 'pending',
            'verified_by': False,
            'verified_on': False,
        })


class TdsLtaPreviousEmployerClaim(models.Model):
    """
    Extensibility Model: Individual LTA Journey Claim Records under Previous Employer.
    """
    _name = 'tds.lta.previous.employer.claim'
    _description = 'Previous Employer LTA Individual Claim Line'

    previous_history_id = fields.Many2one('tds.lta.previous.employer', string="Previous History Record", ondelete='cascade', required=True)
    journey_date = fields.Date(string="Journey Date")
    amount = fields.Monetary(string="Exemption Amount (₹)", currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='previous_history_id.currency_id')
    travel_mode = fields.Selection([
        ('air', 'Air (Economy Class)'),
        ('rail', 'Rail (AC 1st Class)'),
        ('public_transport', 'Recognised Public Transport'),
        ('other', 'Other Mode')
    ], string="Travel Mode", default='air')
    status = fields.Char(string="Claim Status", default="Claimed at Previous Employer")
    verification_status = fields.Selection([
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected')
    ], string="Verification Status", default='pending')
    remarks = fields.Text(string="Remarks")
    attachment_ids = fields.Many2many('ir.attachment', 'tds_lta_prev_claim_attach_rel', 'claim_id', 'attachment_id', string="Attachments")
