# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class TdsEmployee80cDeclaration(models.Model):
    """
    Dedicated Section 80C Investments Declaration Model.
    Provides a clean, standalone form window for Section 80C investments (PPF, ELSS, LIC, VPF, Tuition Fees, etc.)
    matching the Housing Loan & Section 80EEA form layout. Automatically syncs with central TDS declaration engine.
    """
    _name = 'tds.employee.80c.declaration'
    _description = 'Section 80C Investments Declaration'
    _order = 'financial_year_id desc, employee_id, id'
    _sql_constraints = [
        ('emp_fy_80c_uniq', 'unique(employee_id, financial_year_id)',
         'An employee can have only one Section 80C Declaration per Financial Year!')
    ]

    name = fields.Char(
        string="Declaration Reference",
        compute='_compute_name',
        store=True,
        help="Automated Section 80C declaration reference."
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        required=True,
        ondelete='cascade',
        help="Target employee submitting Section 80C declaration."
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
        ondelete='restrict',
        help="Target Tax Year for Section 80C investments."
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
    # SPECIFIED SECTION 80C INVESTMENT FIELDS
    # -------------------------------------------------------------------------
    decl_80c_ppf = fields.Monetary(string="Public Provident Fund (PPF) (₹)", currency_field='currency_id', default=0.0)
    decl_80c_epf = fields.Monetary(string="Voluntary EPF / VPF (₹)", currency_field='currency_id', default=0.0)
    decl_80c_lic = fields.Monetary(string="Life Insurance Premium (LIC) (₹)", currency_field='currency_id', default=0.0)
    decl_80c_elss = fields.Monetary(string="ELSS Mutual Funds (₹)", currency_field='currency_id', default=0.0)
    decl_80c_nsc = fields.Monetary(string="National Savings Certificate (NSC) (₹)", currency_field='currency_id', default=0.0)
    decl_80c_ssy = fields.Monetary(string="Sukanya Samriddhi Yojana (SSY) (₹)", currency_field='currency_id', default=0.0)
    decl_80c_fd = fields.Monetary(string="Tax Saving Fixed Deposit (5 Year) (₹)", currency_field='currency_id', default=0.0)
    decl_80c_tuition = fields.Monetary(string="Children Tuition Fees (₹)", currency_field='currency_id', default=0.0)
    decl_80c_housing_principal = fields.Monetary(string="Housing Loan Principal Repayment (₹)", currency_field='currency_id', default=0.0)
    decl_80c_other = fields.Monetary(string="Other 80C Investments (₹)", currency_field='currency_id', default=0.0)

    total_declared_amount = fields.Monetary(
        string="Total 80C Declared Amount (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        help="Sum of all declared Section 80C investment amounts."
    )
    total_approved_amount = fields.Monetary(
        string="Statutory Approved Deduction (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        help="Final Section 80C deduction allowed (capped at ₹1,50,000 ceiling)."
    )
    is_80c_capped = fields.Boolean(
        string="Is Capped at ₹1.5L",
        compute='_compute_totals',
        store=True,
        help="True if declared 80C investments exceed the statutory limit of ₹1,50,000."
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_80c_decl_ir_attachment_rel',
        'decl_id',
        'attachment_id',
        string="Supporting 80C Proof Receipts"
    )

    @api.depends('employee_id', 'financial_year_id')
    def _compute_name(self):
        for rec in self:
            emp_name = rec.employee_id.name if rec.employee_id else "New"
            fy_name = rec.financial_year_id.name if rec.financial_year_id else ""
            rec.name = f"Section 80C - {emp_name} [{fy_name}]"

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
        'decl_80c_ppf', 'decl_80c_epf', 'decl_80c_lic', 'decl_80c_elss', 'decl_80c_nsc',
        'decl_80c_ssy', 'decl_80c_fd', 'decl_80c_tuition', 'decl_80c_housing_principal', 'decl_80c_other',
        'regime_code'
    )
    def _compute_totals(self):
        for rec in self:
            total_decl = (
                rec.decl_80c_ppf + rec.decl_80c_epf + rec.decl_80c_lic + rec.decl_80c_elss +
                rec.decl_80c_nsc + rec.decl_80c_ssy + rec.decl_80c_fd + rec.decl_80c_tuition +
                rec.decl_80c_housing_principal + rec.decl_80c_other
            )
            rec.is_80c_capped = (total_decl > 150000.0)
            is_post_proof = rec.declaration_id.state in ('proof_verified', 'approved') if hasattr(rec, 'declaration_id') and rec.declaration_id else (rec.state in ('proof_verified', 'approved') if hasattr(rec, 'state') else False)
            rec.total_approved_amount = (min(total_decl, 150000.0) if rec.regime_code == 'old' else 0.0) if is_post_proof else 0.0

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
        """Sync 80C amounts with central tds.employee.declaration master."""
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
                'decl_80c_ppf': rec.decl_80c_ppf,
                'decl_80c_epf': rec.decl_80c_epf,
                'decl_80c_lic': rec.decl_80c_lic,
                'decl_80c_elss': rec.decl_80c_elss,
                'decl_80c_nsc': rec.decl_80c_nsc,
                'decl_80c_ssy': rec.decl_80c_ssy,
                'decl_80c_fd': rec.decl_80c_fd,
                'decl_80c_tuition': rec.decl_80c_tuition,
                'decl_80c_housing_principal': rec.decl_80c_housing_principal,
                'decl_80c_other': rec.decl_80c_other,
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
