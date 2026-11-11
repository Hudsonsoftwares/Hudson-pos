# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class TdsEmployee80dDeclaration(models.Model):
    """
    Dedicated Section 80D Health & Medical Insurance Declaration Model.
    Provides a standalone form window matching the Housing Loan form layout for 80D insurance premiums
    (Self/Family, Parents, Preventive Health Checkup) and Senior Citizen age flags.
    """
    _name = 'tds.employee.80d.declaration'
    _description = 'Section 80D Health & Medical Insurance Declaration'
    _order = 'financial_year_id desc, employee_id, id'
    _sql_constraints = [
        ('emp_fy_80d_uniq', 'unique(employee_id, financial_year_id)',
         'An employee can have only one Section 80D Declaration per Financial Year!')
    ]

    name = fields.Char(
        string="Declaration Reference",
        compute='_compute_name',
        store=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        required=True,
        ondelete='cascade'
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        related='employee_id.company_id',
        store=True,
        readonly=True
    )
    financial_year_id = fields.Many2one(
        'tds.financial.year',
        string="Tax Year",
        required=True,
        ondelete='restrict'
    )
    tax_regime_id = fields.Many2one(
        'tds.tax.regime',
        string="Applied Tax Regime",
        compute='_compute_tax_regime_id',
        store=True,
        readonly=True
    )
    regime_code = fields.Selection(
        related='tax_regime_id.code',
        string="Regime Code",
        store=True,
        readonly=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('declared', 'Declared'),
        ('submitted', 'Submitted'),
        ('proof_submitted', 'Proof Submitted'),
        ('proof_under_review', 'Proof Under Review'),
        ('proof_verified', 'Proof Verified'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string="Declaration Status", default='draft', required=True, tracking=True)

    submission_date = fields.Date(string="Submission Date", readonly=True)
    approval_date = fields.Date(string="Approval Date", readonly=True)
    approved_by_id = fields.Many2one('res.users', string="Approved By", readonly=True)
    rejection_reason = fields.Text(string="Rejection Reason")

    currency_id = fields.Many2one('res.currency', related='company_id.currency_id', readonly=True)

    # -------------------------------------------------------------------------
    # SECTION 80D SPECIFIC FIELDS
    # -------------------------------------------------------------------------
    decl_80d_self = fields.Monetary(
        string="Self, Spouse & Children Premium (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Health insurance premium paid for Self, Spouse, and dependent Children."
    )
    decl_80d_self_is_senior = fields.Boolean(
        string="Self / Spouse is Senior Citizen (Age ≥ 60)",
        default=False,
        help="Check if Self or Spouse is 60 years or older (increases limit to ₹50,000)."
    )
    decl_80d_parents = fields.Monetary(
        string="Parents Health Insurance Premium (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Health insurance premium paid for Parents."
    )
    decl_80d_parents_is_senior = fields.Boolean(
        string="Parents are Senior Citizens (Age ≥ 60)",
        default=False,
        help="Check if Parents are 60 years or older (increases parents limit to ₹50,000)."
    )
    decl_80d_preventive = fields.Monetary(
        string="Preventive Health Checkup (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Preventive health checkup expenses (capped at ₹5,000 statutory sub-limit)."
    )

    total_declared_amount = fields.Monetary(
        string="Total Declared 80D Amount (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True
    )
    total_approved_amount = fields.Monetary(
        string="Statutory Approved 80D Deduction (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True
    )
    max_80d_limit = fields.Monetary(
        string="Maximum Statutory Limit (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_80d_decl_ir_attachment_rel',
        'decl_id',
        'attachment_id',
        string="Supporting Medical Insurance Receipts"
    )

    @api.depends('employee_id', 'financial_year_id')
    def _compute_name(self):
        for rec in self:
            emp_name = rec.employee_id.name if rec.employee_id else "New"
            fy_name = rec.financial_year_id.name if rec.financial_year_id else ""
            rec.name = f"Section 80D - {emp_name} [{fy_name}]"

    @api.depends('employee_id', 'financial_year_id')
    def _compute_tax_regime_id(self):
        for rec in self:
            if rec.employee_id and rec.financial_year_id:
                regime_rec = self.env['tds.employee.tax.regime'].search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('financial_year_id', '=', rec.financial_year_id.id)
                ], limit=1)
                rec.tax_regime_id = regime_rec.regime_id.id if regime_rec else False
            else:
                rec.tax_regime_id = False

    @api.depends(
        'decl_80d_self', 'decl_80d_self_is_senior', 'decl_80d_parents',
        'decl_80d_parents_is_senior', 'decl_80d_preventive', 'regime_code'
    )
    def _compute_totals(self):
        for rec in self:
            self_cap = 50000.0 if rec.decl_80d_self_is_senior else 25000.0
            parents_cap = 50000.0 if rec.decl_80d_parents_is_senior else 25000.0
            rec.max_80d_limit = self_cap + parents_cap

            preventive_val = min(rec.decl_80d_preventive or 0.0, 5000.0)
            self_claim = min(rec.decl_80d_self + preventive_val, self_cap)
            parents_claim = min(rec.decl_80d_parents, parents_cap)

            total_decl = rec.decl_80d_self + rec.decl_80d_parents + rec.decl_80d_preventive
            rec.total_declared_amount = total_decl

            is_post_proof = rec.declaration_id.state in ('proof_verified', 'approved') if hasattr(rec, 'declaration_id') and rec.declaration_id else (rec.state in ('proof_verified', 'approved') if hasattr(rec, 'state') else False)
            if rec.regime_code == 'old' and is_post_proof:
                rec.total_approved_amount = min(self_claim + parents_claim, rec.max_80d_limit)
            else:
                rec.total_approved_amount = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._sync_to_central_declaration()
        return records

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            rec._sync_to_central_declaration()
        return res

    def _sync_to_central_declaration(self):
        """Sync 80D fields with central tds.employee.declaration master."""
        for rec in self:
            if not rec.employee_id or not rec.financial_year_id:
                continue
            decl = self.env['tds.employee.declaration'].sudo().search([
                ('employee_id', '=', rec.employee_id.id),
                ('financial_year_id', '=', rec.financial_year_id.id)
            ], limit=1)
            if not decl:
                decl = self.env['tds.employee.declaration'].sudo().create({
                    'employee_id': rec.employee_id.id,
                    'financial_year_id': rec.financial_year_id.id,
                    'state': rec.state if rec.state in ['draft', 'declared', 'submitted', 'proof_submitted', 'proof_under_review', 'proof_verified', 'approved', 'rejected'] else 'draft',
                })
            
            decl.sudo().write({
                'decl_80d_self': rec.decl_80d_self,
                'decl_80d_self_is_senior': rec.decl_80d_self_is_senior,
                'decl_80d_parents': rec.decl_80d_parents,
                'decl_80d_parents_is_senior': rec.decl_80d_parents_is_senior,
                'decl_80d_preventive': rec.decl_80d_preventive,
            })

    def action_submit_declaration(self):
        self.write({'state': 'declared', 'submission_date': fields.Date.today()})
        self._sync_to_central_declaration()

    def action_submit(self):
        return self.action_submit_declaration()

    def action_submit_proofs(self):
        self.write({'state': 'proof_submitted'})
        self._sync_to_central_declaration()

    def action_start_review(self):
        self.write({'state': 'proof_under_review'})
        self._sync_to_central_declaration()

    def action_verify_proofs(self):
        self.write({'state': 'proof_verified', 'approval_date': fields.Date.today(), 'approved_by_id': self.env.user.id})
        self._sync_to_central_declaration()

    def action_approve(self):
        return self.action_verify_proofs()

    def action_reject(self):
        if not self.rejection_reason:
            raise ValidationError(_("Please enter a Rejection Reason before rejecting."))
        self.write({'state': 'rejected'})
        self._sync_to_central_declaration()

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})
        self._sync_to_central_declaration()
