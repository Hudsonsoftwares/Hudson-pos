# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class TdsEmployeeHraDeclaration(models.Model):
    """
    Dedicated House Rent Allowance (HRA / Section 10(13A)) Declaration Model.
    Provides a standalone form window matching the Housing Loan form layout for Rent Paid,
    Landlord Name, Landlord PAN, Landlord Address, and Metro/Non-Metro City status.
    """
    _name = 'tds.employee.hra.declaration'
    _description = 'House Rent Allowance (HRA) Declaration'
    _order = 'financial_year_id desc, employee_id, id'
    _sql_constraints = [
        ('emp_fy_hra_uniq', 'unique(employee_id, financial_year_id)',
         'An employee can have only one HRA Declaration per Financial Year!')
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
    # HRA SPECIFIED FIELDS
    # -------------------------------------------------------------------------
    annual_rent_paid = fields.Monetary(
        string="Annual Rent Paid (₹)",
        currency_field='currency_id',
        default=0.0,
        required=True,
        help="Total annual rent paid by employee for residential accommodation."
    )
    monthly_rent_paid = fields.Monetary(
        string="Monthly Rent Equivalent (₹)",
        currency_field='currency_id',
        compute='_compute_monthly_rent',
        store=True
    )
    is_metro_city = fields.Boolean(
        string="Rented House in Metro City?",
        default=False,
        help="Check if house is located in Mumbai, Delhi, Kolkata, or Chennai (50% Basic salary statutory cap vs 40% non-metro)."
    )
    landlord_name = fields.Char(
        string="Landlord Full Name",
        help="Full legal name of the landlord."
    )
    landlord_pan = fields.Char(
        string="Landlord PAN Number",
        help="10-character PAN number of landlord. Mandatory if annual rent exceeds ₹1,00,000."
    )
    landlord_address = fields.Text(
        string="Rented Accommodation Address",
        help="Complete residential address of rented premises."
    )
    own_residential_property_at_workplace = fields.Boolean(
        string="Own Residential Property at Place of Work/Residence",
        default=False,
        help="Section 10(13A) - Mark True if employee owns residential accommodation at the place of work/residence."
    )
    rent_period_from = fields.Date(
        string="Rent Period From",
        help="Section 10(13A) - Start date of the claimed rent period."
    )
    rent_period_to = fields.Date(
        string="Rent Period To",
        help="Section 10(13A) - End date of the claimed rent period."
    )
    is_pan_required = fields.Boolean(
        string="Is PAN Required?",
        compute='_compute_is_pan_required',
        store=True
    )
    summary_html = fields.Html(
        string="Section 10(13A) HRA Status",
        compute='_compute_hra_status',
        store=False
    )

    @api.depends(
        'annual_rent_paid', 'is_metro_city', 'own_residential_property_at_workplace',
        'rent_period_from', 'rent_period_to', 'regime_code', 'employee_id', 'financial_year_id'
    )
    def _compute_hra_status(self):
        from ..services.tds.section10_hra_exemption_service import Section10HraExemptionService
        from ..services.tds.salary_projection_service import SalaryProjectionService
        hra_svc = Section10HraExemptionService(self.env)
        sal_proj_svc = SalaryProjectionService(self.env)

        for rec in self:
            if not rec.employee_id or not rec.financial_year_id:
                rec.summary_html = False
                continue

            sal_res = sal_proj_svc.project_salary(rec.employee_id, rec.financial_year_id)
            annual_basic_salary = (sal_res.total_basic or 0.0) + (sal_res.total_da or 0.0)
            actual_hra_received = sal_res.total_hra or 0.0
            annual_rent_paid = float(rec.annual_rent_paid or 0.0)
            is_metro = bool(rec.is_metro_city)

            res = hra_svc.calculate_exemption(
                annual_rent_paid=annual_rent_paid,
                actual_hra_received=actual_hra_received,
                annual_basic_salary=annual_basic_salary,
                is_metro=is_metro,
                employee=rec.employee_id,
                financial_year=rec.financial_year_id,
                regime_code=rec.regime_code or 'old',
                own_residential_property_at_workplace=rec.own_residential_property_at_workplace,
                rent_period_from=rec.rent_period_from,
                rent_period_to=rec.rent_period_to,
                annual_basic_component=sal_res.total_basic,
                annual_da_component=sal_res.total_da
            )

            r_from_str = rec.rent_period_from.strftime('%d-%m-%Y') if rec.rent_period_from else (rec.financial_year_id.start_date.strftime('%d-%m-%Y') if rec.financial_year_id and rec.financial_year_id.start_date else 'N/A')
            r_to_str = rec.rent_period_to.strftime('%d-%m-%Y') if rec.rent_period_to else (rec.financial_year_id.end_date.strftime('%d-%m-%Y') if rec.financial_year_id and rec.financial_year_id.end_date else 'N/A')
            own_prop_str = "Yes" if rec.own_residential_property_at_workplace else "No"

            if not res.is_eligible:
                rec.summary_html = f"""
                <div style="padding: 10px; border-radius: 6px; background-color: #fdf2f2; border: 1px solid #f8b4b4; margin-top: 8px;">
                    <div style="font-weight: bold; color: #9b1c1c; margin-bottom: 4px;">Section 10(13A) HRA Status: ❌ NOT ELIGIBLE</div>
                    <div style="color: #771d1d; font-size: 13px;"><strong>Reason:</strong> {res.rejection_reason}</div>
                    <div style="color: #771d1d; font-size: 12px; margin-top: 4px;"><strong>Allowed HRA Exemption:</strong> ₹0.00</div>
                </div>
                """
            else:
                rec.summary_html = f"""
                <div style="padding: 10px; border-radius: 6px; background-color: #f3faf7; border: 1px solid #84e1bc; margin-top: 8px;">
                    <div style="font-weight: bold; color: #03543f; margin-bottom: 4px;">Section 10(13A) HRA Status: ✅ ELIGIBLE</div>
                    <div style="font-size: 13px; color: #046c4e;">
                        <div>• <strong>HRA Received:</strong> ₹{actual_hra_received:,.2f}</div>
                        <div>• <strong>Rent Paid:</strong> ₹{annual_rent_paid:,.2f}</div>
                        <div>• <strong>Rent Period:</strong> {r_from_str} to {r_to_str}</div>
                        <div>• <strong>Own Residential Property:</strong> {own_prop_str}</div>
                        <div style="margin-top: 4px; font-weight: bold; color: #03543f;">• <strong>Allowed HRA Exemption:</strong> ₹{res.exempt_amount:,.2f}</div>
                    </div>
                </div>
                """

    @api.constrains('rent_period_from', 'rent_period_to')
    def _check_rent_period_dates(self):
        for rec in self:
            if rec.rent_period_from and rec.rent_period_to and rec.rent_period_to < rec.rent_period_from:
                raise ValidationError(_("Invalid HRA rent period: Rent To date cannot be before Rent From date."))
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_hra_decl_ir_attachment_rel',
        'decl_id',
        'attachment_id',
        string="Rent Receipts / Rent Agreement"
    )

    @api.depends('employee_id', 'financial_year_id')
    def _compute_name(self):
        for rec in self:
            emp_name = rec.employee_id.name if rec.employee_id else "New"
            fy_name = rec.financial_year_id.name if rec.financial_year_id else ""
            rec.name = f"HRA Declaration - {emp_name} [{fy_name}]"

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

    @api.depends('annual_rent_paid', 'rent_period_from', 'rent_period_to', 'employee_id', 'financial_year_id')
    def _compute_monthly_rent(self):
        for rec in self:
            months = 0
            if rec.rent_period_from and rec.rent_period_to:
                months = (rec.rent_period_to.year - rec.rent_period_from.year) * 12 + (rec.rent_period_to.month - rec.rent_period_from.month) + 1
            if months <= 0 and rec.employee_id and rec.financial_year_id:
                from ..services.tds.payroll_period_service import PayrollPeriodService
                period_svc = PayrollPeriodService(self.env)
                months = period_svc.calculate_total_periods_in_fy(rec.employee_id, rec.financial_year_id)
            divisor = float(max(1, min(12, months or 12)))
            rec.monthly_rent_paid = (rec.annual_rent_paid or 0.0) / divisor

    @api.depends('annual_rent_paid')
    def _compute_is_pan_required(self):
        for rec in self:
            rec.is_pan_required = (rec.annual_rent_paid or 0.0) > 100000.0

    @api.constrains('annual_rent_paid', 'landlord_pan')
    def _check_landlord_pan(self):
        for rec in self:
            if rec.annual_rent_paid > 100000.0 and not rec.landlord_pan:
                raise ValidationError(_("Landlord PAN Number is mandatory when annual rent paid exceeds ₹1,00,000."))

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
        """Sync HRA fields with central tds.employee.declaration master."""
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
                'decl_hra_annual_rent': rec.annual_rent_paid,
                'decl_hra_is_metro': rec.is_metro_city,
                'decl_hra_landlord_name': rec.landlord_name,
                'decl_hra_landlord_pan': rec.landlord_pan,
                'decl_hra_landlord_address': rec.landlord_address,
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
