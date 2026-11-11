import json
import logging
import math
import re
# pyrefly: ignore [missing-import]
from markupsafe import Markup
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError, ValidationError
from ..services.tds.other_income_aggregation_service import OtherIncomeAggregationService

_logger = logging.getLogger(__name__)

DECLARATION_BUSINESS_REGISTRY = [
    # Section 80C
    {'category': '80c', 'field_name': 'decl_80c_ppf', 'statutory_section': 'Section 80C', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80C_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80c', 'field_name': 'decl_80c_elss', 'statutory_section': 'Section 80C', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80C_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80c', 'field_name': 'decl_80c_epf', 'statutory_section': 'Section 80C', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80C_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80c', 'field_name': 'decl_80c_lic', 'statutory_section': 'Section 80C', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80C_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80c', 'field_name': 'decl_80c_nsc', 'statutory_section': 'Section 80C', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80C_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80c', 'field_name': 'decl_80c_ssy', 'statutory_section': 'Section 80C', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80C_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80c', 'field_name': 'decl_80c_fd', 'statutory_section': 'Section 80C', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80C_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80c', 'field_name': 'decl_80c_tuition', 'statutory_section': 'Section 80C', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80C_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80c', 'field_name': 'decl_80c_housing_principal', 'statutory_section': 'Section 80C', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80C_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80c', 'field_name': 'decl_80c_other', 'statutory_section': 'Section 80C', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80C_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    # Section 80CCD(1B)
    {'category': '80ccd1b', 'field_name': 'decl_80ccd1b_nps', 'statutory_section': 'Section 80CCD(1B)', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80CCD1B_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    # Section 80D
    {'category': '80d_self', 'field_name': 'decl_80d_self', 'statutory_section': 'Section 80D', 'eligibility_strategy': 'MEDICAL_INSURANCE_SELF_BUCKET', 'parameter_code': 'HDS_IN_TDS_80D_SELF_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80d_parents', 'field_name': 'decl_80d_parents', 'statutory_section': 'Section 80D', 'eligibility_strategy': 'MEDICAL_INSURANCE_PARENTS_BUCKET', 'parameter_code': 'HDS_IN_TDS_80D_PARENTS_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'is_senior_field': 'decl_80d_parents_is_senior', 'deduction_group': 'chapter6a'},
    {'category': '80d_preventive', 'field_name': 'decl_80d_preventive', 'statutory_section': 'Section 80D', 'eligibility_strategy': 'PREVENTIVE_CHECKUP_SUB_LIMIT', 'parameter_code': 'HDS_IN_TDS_80D_PREVENTIVE_CHECKUP_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    # Section 24(b) & Section 80EEA
    {'category': '24b', 'field_name': 'decl_24b_self_interest', 'alt_field_name': 'decl_home_loan_interest', 'statutory_section': 'Section 24(b)', 'eligibility_strategy': 'HOME_LOAN_INTEREST', 'parameter_code': 'HDS_IN_TDS_24B_HOME_LOAN_INTEREST_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'home_loan'},
    {'category': '80eea', 'field_name': 'decl_80eea_interest_amount', 'alt_field_name': 'decl_80eea_interest', 'statutory_section': 'Section 80EEA', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80EEA_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'home_loan'},
    # Section 10(13A) HRA
    {'category': 'hra', 'field_name': 'decl_hra_annual_rent', 'statutory_section': 'Section 10(13A)', 'eligibility_strategy': 'HRA_EXEMPTION', 'parameter_code': 'HDS_IN_TDS_HRA_METRO_PERCENT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'hra'},
    # Section 10(5) LTA
    {'category': 'lta', 'field_name': 'decl_lta_declared_fare', 'statutory_section': 'Section 10(5)', 'eligibility_strategy': 'LTA_EXEMPTION', 'parameter_code': 'LTA_AIR_FARE_CEILING', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'hra'},
    # Other Chapter VI-A
    {'category': '80tta', 'field_name': 'decl_80tta_interest', 'statutory_section': 'Section 80TTA', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80TTA_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80ttb', 'field_name': 'decl_80ttb_interest', 'statutory_section': 'Section 80TTB', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80TTB_MAX_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80e', 'field_name': 'decl_80e_interest', 'statutory_section': 'Section 80E', 'eligibility_strategy': 'UNLIMITED', 'parameter_code': None, 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80g', 'field_name': 'decl_80g_donation', 'statutory_section': 'Section 80G', 'eligibility_strategy': 'UNLIMITED', 'parameter_code': None, 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80gg', 'field_name': 'decl_80gg_rent', 'statutory_section': 'Section 80GG', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80GG_MAX_MONTHLY_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80dd', 'field_name': 'decl_80dd_expenditure_amount', 'statutory_section': 'Section 80DD', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80DD_NORMAL_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    {'category': '80u', 'field_name': 'decl_80u_amount', 'statutory_section': 'Section 80U', 'eligibility_strategy': 'CAP_LIMIT', 'parameter_code': 'HDS_IN_TDS_80U_NORMAL_LIMIT', 'allowed_regimes': ['old'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'chapter6a'},
    # Shared Deductions (Both Regimes)
    {'category': '57iia', 'field_name': 'decl_57iia_family_pension', 'statutory_section': 'Family Pension Section 93(1)(d)', 'eligibility_strategy': 'FAMILY_PENSION_CAP', 'parameter_code': 'HDS_IN_TDS_FAMILY_PENSION_LIMIT', 'allowed_regimes': ['old', 'new'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'other_sources_income'},
    {'category': '80cch', 'field_name': 'decl_80cch_agniveer', 'statutory_section': 'Section 80CCH', 'eligibility_strategy': 'UNLIMITED', 'parameter_code': None, 'allowed_regimes': ['old', 'new'], 'workflow': {'planning_supported': True, 'proof_required': True, 'hr_verification_required': True}, 'deduction_group': 'statutory_earning_deduction'},
]

DECLARATION_UI_REGISTRY = {
    'decl_80c_ppf': {'label': 'Public Provident Fund (PPF)', 'display_order': 10},
    'decl_80c_elss': {'label': 'ELSS Mutual Funds', 'display_order': 20},
    'decl_80c_epf': {'label': 'Voluntary EPF (VPF)', 'display_order': 30},
    'decl_80c_lic': {'label': 'Life Insurance Premium (LIC)', 'display_order': 40},
    'decl_80c_nsc': {'label': 'National Savings Certificate (NSC)', 'display_order': 50},
    'decl_80c_ssy': {'label': 'Sukanya Samriddhi Yojana (SSY)', 'display_order': 60},
    'decl_80c_fd': {'label': 'Tax Saving Fixed Deposit', 'display_order': 70},
    'decl_80c_tuition': {'label': 'Children Tuition Fees', 'display_order': 80},
    'decl_80c_housing_principal': {'label': 'Housing Loan Principal Repayment', 'display_order': 90},
    'decl_80c_other': {'label': 'Other 80C Specified Investments', 'display_order': 100},
    'decl_80ccd1b_nps': {'label': 'Employee Voluntary NPS', 'display_order': 110},
    'decl_80d_self': {'label': 'Medical Insurance (Self & Family)', 'display_order': 120},
    'decl_80d_parents': {'label': 'Medical Insurance (Parents)', 'display_order': 130},
    'decl_80d_preventive': {'label': 'Preventive Health Checkup', 'display_order': 140},
    'decl_24b_self_interest': {'label': 'Interest on Housing Loan (Self-Occupied)', 'display_order': 150},
    'decl_24b_loan_purpose': {'label': 'Loan Taken For', 'display_order': 152},
    'decl_24b_completion_date': {'label': 'Construction/Purchase Completion Date', 'display_order': 154},
    'decl_80eea_interest': {'label': 'First-Time Home Buyer Interest (80EEA)', 'display_order': 160},
    'decl_80eea_lender_type': {'label': '80EEA Lending Institution Type', 'display_order': 162},
    'decl_80eea_interest_amount': {'label': '80EEA Interest Amount', 'display_order': 164},
    'decl_80eea_claimed_under_24b': {'label': 'Interest Already Claimed under Section 24(b)', 'display_order': 166},
    'decl_hra_annual_rent': {'label': 'Annual House Rent Paid', 'display_order': 170},
    'decl_lta_declared_fare': {'label': 'Leave Travel Allowance (LTA)', 'display_order': 175},
    'decl_80tta_interest': {'label': 'Savings Interest Deduction (80TTA)', 'display_order': 180},
    'decl_80ttb_interest': {'label': 'Senior Citizen Interest (80TTB)', 'display_order': 190},
    'decl_80e_interest': {'label': 'Education Loan Interest (80E)', 'display_order': 200},
    'decl_80g_donation': {'label': 'Charitable Donations (80G)', 'display_order': 210},
    'decl_80gg_rent': {'label': 'Rent Paid without HRA (80GG)', 'display_order': 220},
    'decl_80dd_expenditure_amount': {'label': 'Dependent Disability Deduction (80DD)', 'display_order': 230},
    'decl_57iia_family_pension': {'label': 'Family Pension Received (annual) — Section 93(1)(d)', 'display_order': 250},
    'decl_80cch_agniveer': {'label': 'Agniveer Corpus Fund Contribution (80CCH)', 'display_order': 260},
}


class TdsEmployeeDeclaration(models.Model):
    """
    TDS Employee Tax Declaration Header Model.
    Captures annual employee tax investment proofs and Section 10 / Chapter VI-A statutory exemption declarations.
    Enforces multi-stage approval workflow (Draft -> Submitted -> Under Review -> Approved / Rejected).
    Only APPROVED declarations are consumed by downstream TDS calculation engines.
    """
    _name = 'tds.employee.declaration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Employee Annual Tax Declaration Header'
    _order = 'financial_year_id desc, employee_id, id'

    _DECLARATION_AUDIT_FIELDS = [
        'decl_80c_ppf',
        'decl_80c_elss',
        'decl_80c_epf',
        'decl_80c_lic',
        'decl_80c_nsc',
        'decl_80c_ssy',
        'decl_80c_fd',
        'decl_80c_tuition',
        'decl_80c_housing_principal',
        'decl_80c_other',
        'decl_80ccd1b_nps',
        'decl_80d_self',
        'decl_80d_parents',
        'decl_80d_preventive',
        'decl_24b_self_interest',
        'decl_80eea_interest_amount',
        'decl_80eea_interest',
        'decl_hra_annual_rent',
        'decl_lta_declared_fare',
        'decl_80tta_interest',
        'decl_80ttb_interest',
        'decl_80e_interest',
        'decl_80g_donation',
        'decl_80gg_rent',
        'decl_80dd_expenditure_amount',
        'decl_80u_amount',
        'decl_80ccd2_employer_nps',
        'decl_57iia_family_pension',
        'decl_80cch_agniveer',
        'total_declared_amount',
        'total_approved_amount',
        'state',
        'tax_regime_id',
        # Income from Other Sources
        'savings_bank_interest',
        'fixed_deposit_interest',
        'dividend_income',
        'other_sources_income',
        'total_other_sources_income',
        # House Property (Let-Out Property)
        'annual_let_out_rent',
        'municipal_taxes_paid',
        'let_out_interest_paid',
        'net_house_property_income_loss',
        # Previous Employer Details
        'prev_employer_taxable_gross',
        'prev_employer_tds',
        'prev_employer_pt',
        'prev_employer_pf',
    ]

    _sql_constraints = [
        ('emp_fy_decl_uniq', 'unique(employee_id, financial_year_id)',
         'An employee can have only one Tax Declaration header per Financial Year!')
    ]

    name = fields.Char(
        string="Declaration Reference",
        compute='_compute_name',
        store=True,
        help="Automated declaration title."
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        required=True,
        ondelete='cascade',
        help="Target employee submitting tax declaration."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        related='employee_id.company_id',
        store=True,
        readonly=True
    )
    resident_status = fields.Selection(
        related='employee_id.resident_status',
        string="Income Tax Resident Status",
        store=True,
        readonly=True,
        help="Centralized Income Tax residential status derived directly from Employee Profile."
    )
    @api.model
    def _default_financial_year_id(self):
        company = self.env.company
        if company and company.hds_in_default_tax_year:
            return company.hds_in_default_tax_year.id
        today = fields.Date.today()
        fy = self.env['tds.financial.year'].search([
            ('start_date', '<=', today),
            ('end_date', '>=', today),
            ('active', '=', True),
            ('is_closed', '=', False)
        ], limit=1)
        return fy.id if fy else False

    financial_year_id = fields.Many2one(
        'tds.financial.year',
        string="Tax Year",
        required=True,
        default=_default_financial_year_id,
        ondelete='restrict',
        help="Target Financial Year for investment declarations."
    )
    is_proof_window_open = fields.Boolean(
        string="Proof Submission Window Open",
        compute='_compute_is_proof_window_open',
        help="Returns True if HR manually opened proof submission toggle OR current date falls within December proof submission window."
    )

    @api.depends('financial_year_id', 'financial_year_id.is_closed', 'financial_year_id.proof_submission_start_date', 'financial_year_id.proof_submission_end_date')
    def _compute_is_proof_window_open(self):
        for rec in self:
            fy = rec.financial_year_id
            rec.is_proof_window_open = bool(fy and fy.is_proof_submission_active())

    hds_in_tds_applicable = fields.Boolean(
        string="TDS Applicable",
        compute='_compute_hds_in_tds_applicable',
        store=False,
    )

    @api.depends('company_id.hds_in_tds_applicable', 'employee_id.hds_in_tds_applicable')
    def _compute_hds_in_tds_applicable(self):
        for rec in self:
            comp_tds = bool(rec.company_id and rec.company_id.hds_in_tds_applicable)
            emp_tds = bool(rec.employee_id and rec.employee_id.hds_in_tds_applicable)
            rec.hds_in_tds_applicable = comp_tds and emp_tds

    hds_in_is_agnipath = fields.Boolean(
        string="Employee under Agnipath Scheme",
        related='employee_id.hds_in_is_agnipath',
        store=True,
        readonly=True,
        help="Indicates whether the employee is enrolled under the Agnipath Scheme (enables Section 80CCH Agniveer Corpus Fund deduction)."
    )

    def action_print_statutory_report(self):
        """
        Triggers PDF generation of the Statutory Tax Calculation Report.
        """
        self.ensure_one()
        company = self.company_id or self.employee_id.company_id or self.env.company
        if not company.hds_in_tds_applicable:
            raise UserError(_("Tax Calculation Report is not available because TDS is disabled in Company Settings."))
        if not getattr(self.employee_id, 'hds_in_tds_applicable', False):
            raise UserError(_("Tax Calculation Report is not available because TDS is disabled for employee '%s'.") % (self.employee_id.name or ''))
        return self.env.ref('hudson_in_payroll.action_report_statutory_tax_declaration').report_action(self)

    tax_regime_id = fields.Many2one(
        'tds.tax.regime',
        string="Applied Tax Regime",
        compute='_compute_tax_regime_id',
        store=True,
        readonly=True,
        help="Active Tax Regime for this employee in the selected Financial Year."
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

    submission_date = fields.Date(
        string="Submission Date",
        readonly=True,
        help="Date when employee submitted declaration."
    )
    proof_submission_date = fields.Date(
        string="Proof Submission Date",
        readonly=True,
        copy=False,
        help="Date when the employee submitted the proof documents."
    )
    approval_date = fields.Date(
        string="Approval Date",
        readonly=True,
        help="Date when Payroll Manager approved declaration."
    )
    approved_by_id = fields.Many2one(
        'res.users',
        string="Approved By",
        readonly=True,
        help="Payroll Officer/Manager who approved declaration."
    )
    rejection_reason = fields.Text(
        string="Rejection Reason",
        help="Detailed reason for declaration rejection."
    )

    total_declared_amount = fields.Monetary(
        string="Total Declared Amount (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        help="Sum of all declared investment amounts across lines."
    )
    total_approved_amount = fields.Monetary(
        string="Total Approved Amount (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        help="Sum of all approved statutory exemption amounts across lines."
    )
    total_rejected_amount = fields.Monetary(
        string="Total Rejected Amount (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        help="Sum of all rejected investment amounts across lines."
    )
    total_eligible_amount = fields.Monetary(
        string="Total Eligible Deduction (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=False,
        help="Sum of all system-calculated allowable statutory deductions."
    )
    total_excess_amount = fields.Monetary(
        string="Total Excess / Non-Eligible Amount (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=False,
        help="Sum of all investment portions exceeding statutory limits (Display only)."
    )
    proof_rule_guide_html = fields.Html(
        string="Proof Documentation & Rule Guide",
        compute='_compute_proof_rule_guide_html',
        sanitize=False,
        help="Read-only informational guidance and statutory rule parameters for HR awareness."
    )
    recalculation_summary_html = fields.Html(
        string="Recalculation Summary",
        sanitize=False,
        help="Full breakdown of the latest TDS recalculation result."
    )

    # Dynamic Component Active Visibility Flags (computed from Configuration Master)
    is_80c_ppf_active = fields.Boolean(compute='_compute_component_active_flags', store=False)
    is_80c_elss_active = fields.Boolean(compute='_compute_component_active_flags', store=False)
    is_80c_epf_active = fields.Boolean(compute='_compute_component_active_flags', store=False)
    is_80c_lic_active = fields.Boolean(compute='_compute_component_active_flags', store=False)
    is_80c_nsc_active = fields.Boolean(compute='_compute_component_active_flags', store=False)
    is_80c_ssy_active = fields.Boolean(compute='_compute_component_active_flags', store=False)
    is_80c_fd_active = fields.Boolean(compute='_compute_component_active_flags', store=False)
    is_80c_tuition_active = fields.Boolean(compute='_compute_component_active_flags', store=False)
    is_80c_housing_principal_active = fields.Boolean(compute='_compute_component_active_flags', store=False)
    is_80c_other_active = fields.Boolean(compute='_compute_component_active_flags', store=False)
    is_80ccd1b_active = fields.Boolean(compute='_compute_component_active_flags', store=False)
    is_80ccd2_active = fields.Boolean(compute='_compute_component_active_flags', store=False)
    is_57iia_active = fields.Boolean(compute='_compute_component_active_flags', store=False)
    is_80cch_active = fields.Boolean(compute='_compute_component_active_flags', store=False)

    @api.depends('regime_code', 'financial_year_id', 'employee_id.hds_in_is_agnipath')
    def _compute_component_active_flags(self):
        from ..services.tds.tds_section_config_service import TdsSectionConfigService
        sec_config_svc = TdsSectionConfigService(self.env)
        for rec in self:
            fy = rec.financial_year_id
            eval_date = (getattr(fy, 'start_date', False) or getattr(fy, 'date_from', False)) if fy else fields.Date.today()
            active_comps = sec_config_svc.get_active_components(regime_code=rec.regime_code, eval_date=eval_date)
            active_codes = set(active_comps.mapped('code')) if active_comps else set()

            has_config = self.env['tds.tax.section.config'].sudo().search_count([]) > 0

            rec.is_80c_ppf_active = ('80c_ppf' in active_codes) if has_config else True
            rec.is_80c_elss_active = ('80c_elss' in active_codes) if has_config else True
            rec.is_80c_epf_active = ('80c_epf' in active_codes) if has_config else True
            rec.is_80c_lic_active = ('80c_lic' in active_codes) if has_config else True
            rec.is_80c_nsc_active = ('80c_nsc' in active_codes) if has_config else True
            rec.is_80c_ssy_active = ('80c_ssy' in active_codes) if has_config else True
            rec.is_80c_fd_active = ('80c_fd' in active_codes) if has_config else True
            rec.is_80c_tuition_active = ('80c_tuition' in active_codes) if has_config else True
            rec.is_80c_housing_principal_active = ('80c_housing_principal' in active_codes) if has_config else True
            rec.is_80c_other_active = ('80c_other' in active_codes) if has_config else True
            rec.is_80ccd1b_active = ('80ccd1b' in active_codes) if has_config else True
            rec.is_80ccd2_active = ('80ccd2' in active_codes) if has_config else True
            rec.is_57iia_active = ('57iia' in active_codes) if has_config else True
            rec.is_80cch_active = (('80cch' in active_codes) if has_config else True) and rec.hds_in_is_agnipath


    decl_80c_total_declared = fields.Monetary(
        string="Section 80C Declared Investment (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=False,
        help="Total Section 80C declared investments before statutory limit cap."
    )
    decl_80c_total_eligible = fields.Monetary(
        string="Section 80C Eligible Deduction (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=False,
        help="Eligible Section 80C deduction capped at statutory limit of ₹1,50,000."
    )
    decl_80c_total_excess = fields.Monetary(
        string="Section 80C Excess Investment (₹)",
        currency_field='currency_id',
        compute='_compute_totals',
        store=False,
        help="Section 80C investment portion exceeding statutory limit of ₹1,50,000."
    )

    @api.depends(
        'decl_80c_ppf', 'decl_80c_epf', 'decl_80c_lic', 'decl_80c_elss', 'decl_80c_nsc',
        'decl_80c_ssy', 'decl_80c_fd', 'decl_80c_tuition', 'decl_80c_housing_principal', 'decl_80c_other',
        'decl_80ccd1b_nps', 'decl_80d_self', 'decl_80d_self_is_senior', 'decl_80d_parents',
        'decl_80d_parents_is_senior', 'decl_80d_preventive', 'decl_80tta_interest',
        'decl_80ttb_interest', 'decl_80e_interest', 'decl_80g_donation', 'decl_80gg_rent',
        'decl_80dd_disability_exists', 'decl_80dd_has_certificate', 'decl_80dd_disability_percentage',
        'decl_80u_disability_percentage', 'decl_80u_has_certificate',
        'decl_80ccd2_employer_nps', 'decl_80cch_agniveer', 'decl_57iia_family_pension', 'decl_hra_annual_rent', 'decl_24b_self_interest',
        'employee_id.hds_in_is_agnipath',
        'declaration_line_ids', 'declaration_line_ids.declared_amount', 'declaration_line_ids.approved_amount',
        'declaration_line_ids.tax_firm_approved_amount', 'declaration_line_ids.is_regime_permitted',
        'declaration_line_ids.rejected_amount', 'declaration_line_ids.eligible_amount', 'declaration_line_ids.excess_amount',
        'regime_code', 'state'
    )
    def _compute_totals(self):
        def _sf(v):
            if not v or not isinstance(v, (int, float)):
                return 0.0
            if math.isinf(v) or math.isnan(v) or v > 1e12:
                return 0.0
            return float(v)

        for rec in self:
            sum_80c_scalars = (
                _sf(rec.decl_80c_ppf) + _sf(rec.decl_80c_epf) + _sf(rec.decl_80c_lic) +
                _sf(rec.decl_80c_elss) + _sf(rec.decl_80c_nsc) + _sf(rec.decl_80c_ssy) +
                _sf(rec.decl_80c_fd) + _sf(rec.decl_80c_tuition) + _sf(rec.decl_80c_housing_principal) +
                _sf(rec.decl_80c_other)
            )
            sum_80d = (rec.decl_80d_self or 0.0) + (rec.decl_80d_parents or 0.0) + (rec.decl_80d_preventive or 0.0)
            sum_other_ded = (
                (rec.decl_80ccd1b_nps or 0.0) + (rec.decl_80tta_interest or 0.0) + (rec.decl_80ttb_interest or 0.0) +
                (rec.decl_80e_interest or 0.0) + (rec.decl_80g_donation or 0.0) + (rec.decl_80gg_rent or 0.0) +
                (rec.decl_80dd_expenditure_amount or 0.0) + (rec.decl_80u_amount or 0.0) + (rec.decl_hra_annual_rent or 0.0) + (rec.decl_24b_self_interest or 0.0)
            )
            
            lines_80c_declared = sum(rec.declaration_line_ids.filtered(lambda l: l.category == '80c' and getattr(l, 'active', True)).mapped('declared_amount'))
            sum_80c_total_declared = max(sum_80c_scalars, lines_80c_declared)

            eligible_80c = min(sum_80c_total_declared, 150000.0) if rec.regime_code == 'old' else 0.0
            excess_80c = max(0.0, sum_80c_total_declared - eligible_80c) if rec.regime_code == 'old' else sum_80c_total_declared

            rec.decl_80c_total_declared = sum_80c_total_declared
            rec.decl_80c_total_eligible = eligible_80c
            rec.decl_80c_total_excess = excess_80c

            non_nps_lines = rec.declaration_line_ids.filtered(lambda l: l.category != '80ccd2' and getattr(l, 'active', True))
            lines_declared = sum(non_nps_lines.mapped('declared_amount'))
            lines_approved = sum(non_nps_lines.mapped('approved_amount'))
            lines_rejected = sum(non_nps_lines.mapped('rejected_amount'))
            lines_eligible = sum(non_nps_lines.mapped('eligible_amount'))
            lines_excess = sum(non_nps_lines.mapped('excess_amount'))
            
            scalars_total = sum_80c_scalars + sum_80d + sum_other_ded
            rec.total_declared_amount = max(scalars_total, lines_declared)
            
            approved_80c = min(sum_80c_scalars, 150000.0) if rec.regime_code == 'old' else 0.0
            approved_80d_self = min((rec.decl_80d_self or 0.0) + min(rec.decl_80d_preventive or 0.0, 5000.0), 50000.0 if rec.decl_80d_self_is_senior else 25000.0)
            approved_80d_parents = min(rec.decl_80d_parents or 0.0, 50000.0 if rec.decl_80d_parents_is_senior else 25000.0)
            approved_80d = (approved_80d_self + approved_80d_parents) if rec.regime_code == 'old' else 0.0
            approved_80ccd1b = min(rec.decl_80ccd1b_nps or 0.0, 50000.0) if rec.regime_code == 'old' else 0.0
            approved_home_loan = min(rec.decl_24b_self_interest or 0.0, 200000.0) if rec.regime_code == 'old' else 0.0

            approved_80g = 0.0
            if rec.regime_code == 'old' and (rec.decl_80g_donation is not False or rec.decl_80g_institution_name):
                from ..services.tds.section_80g_deduction_service import Section80GDeductionService
                g_svc = Section80GDeductionService(rec.env)
                approved_80g = g_svc.validate_and_trace(
                    rec,
                    regime_code=rec.regime_code,
                    employee=rec.employee_id,
                    financial_year=rec.financial_year_id
                ).allowed_deduction

            approved_80e = 0.0
            if rec.regime_code == 'old' and (rec.decl_80e_interest is not False or rec.decl_80e_lender_name):
                from ..services.tds.section_80e_deduction_service import Section80EDeductionService
                e_svc = Section80EDeductionService(rec.env)
                approved_80e = e_svc.validate_and_trace(
                    rec,
                    regime_code=rec.regime_code,
                    employee=rec.employee_id,
                    financial_year=rec.financial_year_id
                ).allowed_deduction

            approved_80dd = 0.0
            if rec.regime_code == 'old' and (rec.decl_80dd_disability_exists or rec.decl_80dd_dependent_name or rec.decl_80dd_has_certificate):
                from ..services.tds.section_80dd_deduction_service import Section80DDDeductionService
                dd_svc = Section80DDDeductionService(rec.env)
                approved_80dd = dd_svc.validate_and_trace(
                    rec,
                    regime_code=rec.regime_code,
                    employee=rec.employee_id,
                    financial_year=rec.financial_year_id
                ).allowed_deduction

            approved_80u = 0.0
            if rec.regime_code == 'old' and (rec.decl_80u_has_certificate or (rec.decl_80u_disability_percentage or 0.0) > 0 or (rec.decl_80u_renewal_disability_percentage or 0.0) > 0):
                from ..services.tds.section_80u_deduction_service import Section80UDeductionService
                u_svc = Section80UDeductionService(rec.env)
                approved_80u = u_svc.validate_and_trace(
                    rec,
                    regime_code=rec.regime_code,
                    employee=rec.employee_id,
                    financial_year=rec.financial_year_id
                ).allowed_deduction

            approved_80gg = 0.0
            if rec.regime_code == 'old' and (rec.decl_80gg_rent or rec.decl_80gg_form_10ba_filed):
                from ..services.tds.section_80gg_deduction_service import Section80GGDeductionService
                gg_svc = Section80GGDeductionService(rec.env)
                approved_80gg = gg_svc.validate_and_trace(
                    rec,
                    regime_code=rec.regime_code,
                    employee=rec.employee_id,
                    financial_year=rec.financial_year_id
                ).allowed_deduction

            approved_80cch = 0.0
            has_80cch_header = (float(getattr(rec, 'decl_80cch_agniveer', 0.0) or 0.0) > 0.0)
            has_80cch_line = any(l.category == '80cch' for l in rec.declaration_line_ids)
            if (has_80cch_header or has_80cch_line) and rec.hds_in_is_agnipath:
                from ..services.tds.section_80cch_deduction_service import Section80CCHDeductionService
                cch_svc = Section80CCHDeductionService(rec.env)
                cch_res = cch_svc.validate_and_trace(
                    rec,
                    regime_code=rec.regime_code,
                    employee=rec.employee_id,
                    financial_year=rec.financial_year_id
                )
                approved_80cch = cch_res.usable_amount

            approved_57iia = 0.0
            has_57iia_header = (float(getattr(rec, 'decl_57iia_family_pension', 0.0) or 0.0) > 0.0)
            has_57iia_line = any(l.category == '57iia' for l in rec.declaration_line_ids)
            if has_57iia_header or has_57iia_line:
                from ..services.tds.section_57iia_deduction_service import Section57IIADeductionService
                p_svc = Section57IIADeductionService(rec.env)
                p_res = p_svc.validate_and_trace(
                    rec,
                    regime_code=rec.regime_code,
                    employee=rec.employee_id,
                    financial_year=rec.financial_year_id
                )
                approved_57iia = p_res.allowed_deduction

            approved_80ccd2 = 0.0
            has_80ccd2_header = (float(getattr(rec, 'decl_80ccd2_employer_nps', 0.0) or 0.0) > 0.0)
            has_80ccd2_line = any(l.category == '80ccd2' for l in rec.declaration_line_ids)
            if has_80ccd2_header or has_80ccd2_line:
                decl_80ccd2_amt = float(getattr(rec, 'decl_80ccd2_employer_nps', 0.0) or 0.0)
                line_80ccd2 = next((l for l in rec.declaration_line_ids if l.category == '80ccd2' and getattr(l, 'active', True)), None)
                if decl_80ccd2_amt > 0.0:
                    source_type_80ccd2 = 'HEADER_DECLARATION'
                elif line_80ccd2:
                    decl_80ccd2_amt = float(line_80ccd2.declared_amount or 0.0)
                    source_type_80ccd2 = 'DECLARATION_LINE'
                else:
                    source_type_80ccd2 = 'HEADER_DECLARATION'

                emp = rec.employee_id
                fy = rec.financial_year_id
                emp_type = getattr(emp, 'hds_in_employer_category', getattr(emp, 'employer_type', 'private')) or 'private' if emp else 'private'

                from ..services.tds.salary_projection_service import SalaryProjectionService
                sal_svc = SalaryProjectionService(rec.env)
                eval_d = fy.start_date if fy and hasattr(fy, 'start_date') and fy.start_date else fields.Date.today()
                sal_res = sal_svc.project_salary(emp, fy, eval_date=eval_d) if emp and fy else None
                annual_b = (sal_res.total_basic or 0.0) if sal_res else 0.0
                annual_d = (sal_res.total_da or 0.0) if sal_res else 0.0
                sal_b = annual_b + annual_d

                from ..services.tds.tds_parameter_service import TdsParameterService
                tds_param_svc = TdsParameterService(rec.env)
                nps_pct = tds_param_svc.get_employer_nps_limit(regime=rec.regime_code, employer_type=emp_type) or 10.0
                param_code = 'HDS_IN_TDS_NPS_LIMIT_NEW' if rec.regime_code == 'new' else ('HDS_IN_TDS_NPS_LIMIT_OLD_GOVT' if 'govt' in str(emp_type).lower() else 'HDS_IN_TDS_NPS_LIMIT_OLD_PRIVATE')
                calc_ceiling = sal_b * (nps_pct / 100.0)

                from ..services.tds.eligibility_rule_engine_service import EligibilityRuleEngineService
                elig_svc = EligibilityRuleEngineService(rec.env)
                elig_res = elig_svc.evaluate_eligibility(
                    '80ccd2',
                    declared_amount=decl_80ccd2_amt,
                    regime_code=rec.regime_code,
                    employer_type=emp_type,
                    salary_base=sal_b,
                    employee=emp,
                    financial_year=fy,
                    declaration_state=rec.state
                )

                contract_obj = sal_svc._get_employee_contract(emp) if (emp and hasattr(sal_svc, '_get_employee_contract')) else False
                c_id = getattr(contract_obj, 'id', 'N/A') if contract_obj else 'N/A'
                from ..services.tds.payroll_period_service import PayrollPeriodService
                _period_svc = PayrollPeriodService(rec.env)
                _emp_periods = _period_svc.calculate_total_periods_in_fy(emp, fy) if (emp and fy) else 12.0
                m_b = float(getattr(contract_obj, 'basic_salary', 0.0) or 0.0) if contract_obj else (annual_b / float(_emp_periods or 12))
                m_d = float(getattr(contract_obj, 'da', 0.0) or getattr(contract_obj, 'da_amount', 0.0) or 0.0) if contract_obj else (annual_d / float(_emp_periods or 12))

                from ..services.tds.tds_declaration_lifecycle_logger import TdsDeclarationLifecycleLogger
                lifecycle_logger = TdsDeclarationLifecycleLogger(rec.env)
                lifecycle_logger.log_80ccd2_statutory_trace(
                    employee_name=emp.name if emp else 'N/A',
                    employee_id=emp.id if emp else 'N/A',
                    financial_year_name=fy.name if fy else 'N/A',
                    declaration_id=rec.id,
                    declaration_state=rec.state,
                    regime_code=rec.regime_code,
                    employer_type=emp_type,
                    parameter_code=param_code,
                    configured_percentage=nps_pct,
                    annual_basic=annual_b,
                    annual_da=annual_d,
                    salary_base=sal_b,
                    calculated_ceiling=calc_ceiling,
                    declared_amount=decl_80ccd2_amt,
                    eligible_amount=elig_res.eligible_deduction,
                    excess_amount=elig_res.excess_amount,
                    verified_amount=float(line_80ccd2.verified_amount or 0.0) if line_80ccd2 else 0.0,
                    approved_amount=float(line_80ccd2.approved_amount or 0.0) if line_80ccd2 else 0.0,
                    usable_amount=elig_res.eligible_deduction,
                    source_type=source_type_80ccd2,
                    contract_id=c_id,
                    monthly_basic=m_b,
                    monthly_da=m_d
                )
                approved_80ccd2 = elig_res.eligible_deduction

            rec.decl_80dd_amount = approved_80dd if rec.state in ('proof_verified', 'approved') else 0.0
            rec.decl_80u_amount = approved_80u

            if rec.state in ('proof_verified', 'approved'):
                if rec.regime_code == 'old':
                    has_80gg_line = any(l.category == '80gg' for l in rec.declaration_line_ids)
                    scalar_80gg = approved_80gg if not has_80gg_line else 0.0
                    scalar_approved = approved_80c + approved_80d + approved_80ccd1b + approved_home_loan + approved_80e + approved_80g + approved_80dd + approved_80u + scalar_80gg
                    if non_nps_lines:
                        line_categories = set(non_nps_lines.mapped('category'))
                        orphan_scalar_approved = 0.0
                        if '80c' not in line_categories:
                            orphan_scalar_approved += approved_80c
                        if '80d_self' not in line_categories and '80d_parents' not in line_categories and '80d_preventive' not in line_categories:
                            orphan_scalar_approved += approved_80d
                        if '80ccd1b' not in line_categories:
                            orphan_scalar_approved += approved_80ccd1b
                        if '24b' not in line_categories:
                            orphan_scalar_approved += approved_home_loan
                        if '80e' not in line_categories:
                            orphan_scalar_approved += approved_80e
                        if '80g' not in line_categories:
                            orphan_scalar_approved += approved_80g
                        if '80dd' not in line_categories:
                            orphan_scalar_approved += approved_80dd
                        if '80u' not in line_categories:
                            orphan_scalar_approved += approved_80u
                        if '80gg' not in line_categories:
                            orphan_scalar_approved += scalar_80gg
                        if '80cch' not in line_categories and approved_80cch:
                            orphan_scalar_approved += approved_80cch
                        if '57iia' not in line_categories and approved_57iia:
                            orphan_scalar_approved += approved_57iia
                        rec.total_approved_amount = lines_approved + orphan_scalar_approved
                    else:
                        rec.total_approved_amount = scalar_approved + approved_80cch + approved_57iia
                    rec.total_rejected_amount = lines_rejected
                else:
                    # New Regime: Regime-permitted lines (e.g. 57iia, 80cch) and New Regime scalars
                    permitted_lines = non_nps_lines.filtered(lambda l: getattr(l, 'is_regime_permitted', True))
                    lines_approved_new = sum(permitted_lines.mapped('approved_amount'))
                    lines_rejected_new = sum(non_nps_lines.mapped('rejected_amount'))

                    orphan_scalar_approved_new = 0.0
                    if non_nps_lines:
                        line_categories = set(non_nps_lines.mapped('category'))
                        if '80cch' not in line_categories and approved_80cch:
                            orphan_scalar_approved_new += approved_80cch
                        if '57iia' not in line_categories and approved_57iia:
                            orphan_scalar_approved_new += approved_57iia
                        rec.total_approved_amount = lines_approved_new + orphan_scalar_approved_new
                    else:
                        rec.total_approved_amount = approved_80cch + approved_57iia
                    rec.total_rejected_amount = lines_rejected_new
            else:
                scalar_approved = 0.0
                rec.total_approved_amount = 0.0
                rec.total_rejected_amount = 0.0

            rec.total_eligible_amount = eligible_80c + lines_eligible
            rec.total_excess_amount = excess_80c + lines_excess

            _logger.info(
                "\n=========================================\n"
                "DEDUCTION ELIGIBILITY TRACE\n"
                "=========================================\n"
                "Employee        : %s\n"
                "Financial Year  : %s\n"
                "Section         : Section 80C\n"
                "Declared Amount : ₹%s\n"
                "Statutory Limit : ₹1,50,000.00\n"
                "Eligible Deduct : ₹%s\n"
                "Excess Amount   : ₹%s (Display Only)\n"
                "Rule Applied    : Income Tax Act Section 80C (Capped at ₹1,50,000 p.a.)\n"
                "=========================================",
                rec.employee_id.name if rec.employee_id else 'N/A',
                rec.financial_year_id.name if rec.financial_year_id else 'N/A',
                sum_80c_total_declared, eligible_80c, excess_80c
            )

    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        related='company_id.currency_id',
        readonly=True
    )

    declaration_line_ids = fields.One2many(
        'tds.employee.declaration.line',
        'declaration_id',
        string="Declaration Items",
        copy=True
    )
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_declaration_ir_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="Supporting Proof Documents",
        help="Uploaded investment receipts, rent receipts, insurance statements, and tax certificates."
    )
    decl_80c_attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_decl_80c_ir_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="Section 80C Investment Proofs",
        help="Investment receipts for PPF, ELSS, LIC, EPF, NSC, SSY, FD, Tuition Fees, Housing Principal."
    )
    decl_80d_attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_decl_80d_ir_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="Section 80D Medical Insurance Proofs",
        help="Health insurance receipts, policy documents, and preventive health checkup bills."
    )
    decl_80ccd1b_attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_decl_80ccd1b_ir_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="Section 80CCD(1B) NPS Tier 1 Proofs",
        help="NPS contribution receipt or transaction statement."
    )
    decl_hra_attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_decl_hra_ir_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="HRA Rent Receipts & Agreement",
        help="Rent receipts, rental agreement, and landlord PAN declaration."
    )
    decl_24b_attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_decl_24b_ir_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="Home Loan Interest Proofs (24b / 80EEA)",
        help="Provisional or final home loan interest certificate issued by bank or financial institution."
    )
    decl_80e_attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_decl_80e_ir_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="Section 80E Education Loan Proofs",
        help="Education loan interest certificate issued by financial institution."
    )
    decl_80g_attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_decl_80g_ir_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="Section 80G Charitable Donation Proofs",
        help="Donation receipts with 80G approval number / registration details."
    )
    decl_80gg_attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_decl_80gg_ir_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="Section 80GG Form 10BA & Rent Proofs",
        help="Form 10BA declaration and rent payment receipts."
    )
    decl_80dd_attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_decl_80dd_ir_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="Section 80DD Disability Medical Certificates",
        help="Disability certificate or Form 10-IA for dependent with disability."
    )
    decl_80u_attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_decl_80u_ir_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="Section 80U Disability Certificates",
        help="Disability certificate or Form 10-IA for employee with disability."
    )
    decl_57iia_attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_decl_57iia_ir_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="Section 57(iia) Family Pension Proofs",
        help="Family pension payment slip or bank passbook copy."
    )
    decl_80cch_attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_decl_80cch_ir_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="Section 80CCH Agniveer Corpus Proofs",
        help="Agniveer Corpus Fund contribution statement under Agnipath scheme."
    )
    prev_employer_attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_decl_prev_emp_ir_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="Previous Employer Form 12B / Form 16",
        help="Form 12B declaration and Form 16 from previous employer."
    )
    active = fields.Boolean(
        string="Active",
        default=True
    )

    @api.constrains(
        'decl_80c_attachment_ids', 'decl_80d_attachment_ids', 'decl_80ccd1b_attachment_ids',
        'decl_hra_attachment_ids', 'decl_lta_attachment_ids', 'decl_24b_attachment_ids',
        'decl_80e_attachment_ids', 'decl_80g_attachment_ids', 'decl_80gg_attachment_ids',
        'decl_80dd_attachment_ids', 'decl_80u_attachment_ids', 'decl_57iia_attachment_ids',
        'decl_80cch_attachment_ids', 'prev_employer_attachment_ids'
    )
    def _check_single_attachment_per_proof(self):
        proof_fields = [
            'decl_80c_attachment_ids', 'decl_80d_attachment_ids', 'decl_80ccd1b_attachment_ids',
            'decl_hra_attachment_ids', 'decl_lta_attachment_ids', 'decl_24b_attachment_ids',
            'decl_80e_attachment_ids', 'decl_80g_attachment_ids', 'decl_80gg_attachment_ids',
            'decl_80dd_attachment_ids', 'decl_80u_attachment_ids', 'decl_57iia_attachment_ids',
            'decl_80cch_attachment_ids', 'prev_employer_attachment_ids'
        ]
        for rec in self:
            for fname in proof_fields:
                if hasattr(rec, fname):
                    atts = getattr(rec, fname)
                    if len(atts) > 1:
                        f_label = rec._fields[fname].string or fname
                        raise ValidationError(_(
                            "Maximum 1 file can be uploaded for '%s'. Currently %d files are attached. "
                            "Please upload only 1 supporting document per category."
                        ) % (f_label, len(atts)))


    regime_choice_id = fields.Many2one(
        'tds.tax.regime',
        string="Selected Tax Regime Choice",
        compute='_compute_regime_choice_id',
        inverse='_inverse_regime_choice_id',
        store=False,
        readonly=True,
        help="Tax Regime selection reflected from Employee Tax Period & Regime settings."
    )

    # -------------------------------------------------------------------------
    # PROXY FIELDS MAPPED TO tds.employee.income.declaration FOR ESS DASHBOARD
    # -------------------------------------------------------------------------
    savings_bank_interest = fields.Monetary(
        string="Savings Account Interest (₹)",
        currency_field='currency_id',
        compute='_compute_income_decl_fields',
        inverse='_inverse_income_decl_fields',
        store=False,
        help="Section 56 - Savings Account Interest\n"
             "• Type: Income from Other Sources.\n"
             "• Applicability: Both Old and New Regimes.\n"
             "• Notes: Report total annual interest earned from all savings bank accounts. Under Old Regime, deduction up to ₹10,000 is available under Section 80TTA (₹50,000 under 80TTB for Senior Citizens)."
    )
    fixed_deposit_interest = fields.Monetary(
        string="Fixed Deposit Interest (₹)",
        currency_field='currency_id',
        compute='_compute_income_decl_fields',
        inverse='_inverse_income_decl_fields',
        store=False,
        help="Section 56 - Fixed & Term Deposit Interest\n"
             "• Type: Income from Other Sources.\n"
             "• Applicability: Both Old and New Regimes.\n"
             "• Notes: Report annual interest accrued on term deposits, fixed deposits, and recurring deposits."
    )
    dividend_income = fields.Monetary(
        string="Dividend Income (₹)",
        currency_field='currency_id',
        compute='_compute_income_decl_fields',
        inverse='_inverse_income_decl_fields',
        store=False,
        help="Section 56 - Dividend Income\n"
             "• Type: Taxable Dividend Income.\n"
             "• Applicability: Both Old and New Regimes.\n"
             "• Notes: Total dividend income received from Indian companies and mutual funds, taxable at applicable slab rates."
    )
    other_sources_income = fields.Monetary(
        string="Other Miscellaneous Income (₹)",
        currency_field='currency_id',
        compute='_compute_income_decl_fields',
        inverse='_inverse_income_decl_fields',
        store=False,
        help="Section 56 - Miscellaneous Income\n"
             "• Type: Other Sources.\n"
             "• Applicability: Both Old and New Regimes.\n"
             "• Notes: Includes gifts, interest on income tax refund, commission, or any other non-payroll taxable income."
    )
    total_other_sources_income = fields.Monetary(
        string="Total Other Sources Income (₹)",
        currency_field='currency_id',
        compute='_compute_total_other_sources_income',
        store=False,
        help="Total Income from Other Sources aggregated for TDS computation."
    )

    annual_let_out_rent = fields.Monetary(
        string="Gross Annual Rent (₹)",
        currency_field='currency_id',
        compute='_compute_income_decl_fields',
        inverse='_inverse_income_decl_fields',
        store=False,
        help="Section 23(1)(b) - Gross Annual Rent Received\n"
             "• Type: Income from House Property (Let-Out Property).\n"
             "• Applicability: Both Old and New Regimes.\n"
             "• Notes: Total rent collected from let-out residential or commercial property during the financial year."
    )
    municipal_taxes_paid = fields.Monetary(
        string="Municipal Taxes Paid (₹)",
        currency_field='currency_id',
        compute='_compute_income_decl_fields',
        inverse='_inverse_income_decl_fields',
        store=False,
        help="Section 23(1) - Municipal Taxes Paid\n"
             "• Type: Property Tax Deduction.\n"
             "• Applicability: Both Old and New Regimes.\n"
             "• Notes: Municipal taxes paid to local authorities during the financial year. Allowed as deduction from gross rent."
    )
    let_out_interest_paid = fields.Monetary(
        string="Housing Loan Interest (₹)",
        currency_field='currency_id',
        compute='_compute_income_decl_fields',
        inverse='_inverse_income_decl_fields',
        store=False,
        help="Section 24(b) - Home Loan Interest (Let-Out Property)\n"
             "• Limit: Full actual interest paid (UNCAPPED for let-out property).\n"
             "• Applicability: Both Old and New Regimes (Loss set-off restricted to let-out income under New Regime)."
    )
    net_house_property_income_loss = fields.Monetary(
        string="Net Property Income / Loss (₹)",
        currency_field='currency_id',
        compute='_compute_house_property_totals',
        store=False,
        help="Net taxable income or loss from Let-Out House Property after 30% statutory standard deduction under Section 24(a)."
    )
    effective_house_property_gti_impact = fields.Monetary(
        string="Effective House Property GTI Impact (₹)",
        currency_field='currency_id',
        compute='_compute_house_property_totals',
        store=False,
        help="Effective House Property impact on Gross Total Income (after regime adjustment and prior-year carry-forward loss set-off u/s 71B)."
    )
    house_property_loss_ids = fields.One2many(
        'tds.house.property.loss.carryforward',
        related='employee_id.house_property_loss_ids',
        string="House Property Loss Carry-Forward (71B)",
        readonly=False
    )
    previous_lta_history_ids = fields.One2many(
        'tds.lta.previous.employer',
        related='employee_id.previous_lta_history_ids',
        string="Previous Employer LTA History",
        readonly=False
    )

    prev_employer_taxable_gross = fields.Monetary(
        string="Previous Employer Taxable Salary (₹)",
        currency_field='currency_id',
        compute='_compute_income_decl_fields',
        inverse='_inverse_income_decl_fields',
        store=False,
        help="Form 12B / Form 16 Part B - Previous Employer Taxable Gross Salary\n"
             "• Applicability: Mid-year joiners.\n"
             "• Notes: Total taxable salary received from previous employer during the current financial year."
    )
    prev_employer_tds = fields.Monetary(
        string="Previous Employer TDS Deducted (₹)",
        currency_field='currency_id',
        compute='_compute_income_decl_fields',
        inverse='_inverse_income_decl_fields',
        store=False,
        help="Previous Employer Income Tax (TDS) Deducted\n"
             "• Notes: Total income tax already deducted at source by previous employer as per Form 12B."
    )
    prev_employer_pt = fields.Monetary(
        string="Previous Employer PT Deducted (₹)",
        currency_field='currency_id',
        compute='_compute_income_decl_fields',
        inverse='_inverse_income_decl_fields',
        store=False,
        help="Previous Employer Professional Tax (PT)\n"
             "• Notes: Professional tax deducted by previous employer."
    )
    prev_employer_pf = fields.Monetary(
        string="Previous Employer EPF (₹)",
        currency_field='currency_id',
        compute='_compute_income_decl_fields',
        inverse='_inverse_income_decl_fields',
        store=False,
        help="Previous Employer Provident Fund (EPF)\n"
             "• Notes: Employee EPF contribution deducted by previous employer."
    )

    # -------------------------------------------------------------------------
    # STORED DEDUCTION FIELDS (PERSISTENT DATABASE COLUMNS)
    # -------------------------------------------------------------------------
    # Section 80C Specified Investments (Gross Limit ₹1,50,000)
    decl_80c_ppf = fields.Monetary(
        string="Public Provident Fund (PPF) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80C - Public Provident Fund (PPF)"
    )
    decl_80c_elss = fields.Monetary(
        string="ELSS Mutual Funds (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80C - Equity Linked Savings Scheme (ELSS)"
    )
    decl_80c_epf = fields.Monetary(
        string="Voluntary EPF (VPF) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80C - Voluntary Employees' Provident Fund (VPF)"
    )
    decl_80c_lic = fields.Monetary(
        string="Life Insurance Premium (LIC) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80C - Life Insurance Premium"
    )
    decl_80c_nsc = fields.Monetary(
        string="National Savings Certificate (NSC) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80C - National Savings Certificate (NSC)"
    )
    decl_80c_ssy = fields.Monetary(
        string="Sukanya Samriddhi Yojana (SSY) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80C - Sukanya Samriddhi Yojana (SSY)"
    )
    decl_80c_fd = fields.Monetary(
        string="Tax Saving Fixed Deposit (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80C - Tax Saving 5-Year Bank Fixed Deposit"
    )
    decl_80c_tuition = fields.Monetary(
        string="Children Tuition Fees (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80C - Children's School / College Tuition Fees"
    )
    decl_80c_housing_principal = fields.Monetary(
        string="Housing Loan Principal Repayment (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80C - Housing Loan Principal Repayment"
    )
    decl_80c_other = fields.Monetary(
        string="Other 80C Specified Investments (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80C - Other Specified Investments"
    )

    decl_80c_total = fields.Monetary(
        string="Total Section 80C Declared (₹)",
        currency_field='currency_id',
        compute='_compute_80c_summary',
        store=True,
        help="Total Section 80C declared amount subject to statutory cap of ₹1,50,000."
    )
    is_80c_exceeded = fields.Boolean(
        string="Section 80C Exceeds Ceiling (₹1.5L)",
        compute='_compute_80c_summary',
        store=True,
        help="True if total declared Section 80C investments exceed the statutory ceiling of ₹1,50,000."
    )
    section_80c_warning_msg = fields.Char(
        string="Section 80C Warning Message",
        compute='_compute_80c_summary',
        store=True,
        help="Informative warning message when Section 80C declared investments exceed ₹1,50,000 statutory limit."
    )

    @api.depends(
        'decl_80c_ppf', 'decl_80c_elss', 'decl_80c_epf', 'decl_80c_lic', 'decl_80c_nsc',
        'decl_80c_ssy', 'decl_80c_fd', 'decl_80c_tuition', 'decl_80c_housing_principal', 'decl_80c_other'
    )
    def _compute_80c_summary(self):
        for rec in self:
            rec.decl_80c_total = (
                (rec.decl_80c_ppf or 0.0) + (rec.decl_80c_elss or 0.0) + (rec.decl_80c_epf or 0.0) +
                (rec.decl_80c_lic or 0.0) + (rec.decl_80c_nsc or 0.0) + (rec.decl_80c_ssy or 0.0) +
                (rec.decl_80c_fd or 0.0) + (rec.decl_80c_tuition or 0.0) + (rec.decl_80c_housing_principal or 0.0) +
                (rec.decl_80c_other or 0.0)
            )
            if rec.decl_80c_total > 150000.0:
                rec.is_80c_exceeded = True
                rec.section_80c_warning_msg = f"Notice: Total Section 80C declared investments (₹{rec.decl_80c_total:,.2f}) exceed the statutory ceiling of ₹1,50,000. All declared values are fully preserved, and the ₹1,50,000 cap will be applied automatically during tax calculation."
            else:
                rec.is_80c_exceeded = False
                rec.section_80c_warning_msg = ""

    # Section 80CCD(1B) Additional NPS Contribution
    decl_80ccd1b_nps = fields.Monetary(
        string="Employee Voluntary NPS (80CCD(1B)) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80CCD(1B) - Employee Voluntary NPS Contribution"
    )

    # Section 80D Medical Insurance
    decl_80d_self = fields.Monetary(
        string="Medical Insurance - Self & Family (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80D - Health Insurance Premium (Self, Spouse & Children)"
    )
    decl_80d_self_is_senior = fields.Boolean(
        string="Self/Spouse is Senior Citizen (Age ≥ 60)",
        default=False,
        store=True,
        help="Mark True if Self or Spouse is aged 60 years or above."
    )
    decl_80d_parents = fields.Monetary(
        string="Medical Insurance - Parents (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80D - Health Insurance Premium (Parents)"
    )
    decl_80d_parents_is_senior = fields.Boolean(
        string="Parents are Senior Citizens (Age ≥ 60)",
        default=False,
        store=True,
        help="Mark True if parents are aged 60 years or above."
    )
    decl_80d_preventive = fields.Monetary(
        string="Preventive Health Checkup (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80D - Preventive Annual Health Checkup"
    )

    # HRA
    decl_hra_annual_rent = fields.Monetary(
        string="Annual House Rent Paid (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 10(13A) - House Rent Allowance (HRA Exemption)"
    )
    decl_hra_landlord_name = fields.Char(
        string="Landlord Name",
        store=True,
        help="Full name of property owner / landlord."
    )
    decl_hra_landlord_pan = fields.Char(
        string="Landlord PAN",
        store=True,
        help="10-character PAN of landlord."
    )
    decl_hra_is_metro = fields.Boolean(
        string="Accommodation in Metro City",
        default=False,
        store=True,
        help="Mark True if rented accommodation is located in Metro city."
    )

    # Section 10(13A) HRA Eligibility Validation Fields
    decl_hra_own_residential_property_at_workplace = fields.Boolean(
        string="Own Residential Property at Place of Work/Residence",
        default=False,
        store=True,
        help="Section 10(13A) - Mark True if employee owns residential property at the place of work/residence (disqualifies HRA exemption)."
    )
    own_residential_property_at_workplace = fields.Boolean(
        string="Own Residential Property at Workplace",
        default=False,
        store=True,
        help="Section 10(13A) - Direct alias for own residential property."
    )
    decl_hra_rent_period_from = fields.Date(
        string="Rent Period From",
        store=True,
        help="Section 10(13A) - Start date of the rent period claimed for HRA exemption."
    )
    rent_period_from = fields.Date(
        string="Rent Period From (Alias)",
        store=True,
        help="Section 10(13A) - Start date of the rent period claimed for HRA exemption."
    )
    decl_hra_rent_period_to = fields.Date(
        string="Rent Period To",
        store=True,
        help="Section 10(13A) - End date of the rent period claimed for HRA exemption."
    )
    rent_period_to = fields.Date(
        string="Rent Period To (Alias)",
        store=True,
        help="Section 10(13A) - End date of the rent period claimed for HRA exemption."
    )

    # Section 10(13A) HRA Eligibility Status & Card Fields
    decl_hra_eligible = fields.Boolean(
        string="HRA Exemption Eligible",
        compute='_compute_hra_status',
        store=True
    )
    decl_hra_ineligibility_reason = fields.Char(
        string="HRA Ineligibility Reason",
        compute='_compute_hra_status',
        store=True
    )
    decl_hra_allowed_exemption = fields.Monetary(
        string="Allowed HRA Exemption (₹)",
        compute='_compute_hra_status',
        store=True,
        currency_field='currency_id'
    )
    decl_hra_actual_received = fields.Monetary(
        string="Projected HRA Received (₹)",
        compute='_compute_hra_status',
        store=True,
        currency_field='currency_id'
    )
    decl_hra_summary_html = fields.Html(
        string="Section 10(13A) HRA Status",
        compute='_compute_hra_summary_html',
        store=False
    )

    @api.depends(
        'decl_hra_annual_rent', 'decl_hra_is_metro', 'decl_hra_own_residential_property_at_workplace',
        'own_residential_property_at_workplace', 'decl_hra_rent_period_from', 'decl_hra_rent_period_to',
        'rent_period_from', 'rent_period_to', 'regime_code', 'employee_id',
        'financial_year_id', 'declaration_line_ids.declared_amount', 'declaration_line_ids.approved_amount'
    )
    def _compute_hra_status(self):
        from ..services.tds.section10_hra_exemption_service import Section10HraExemptionService
        from ..services.tds.salary_projection_service import SalaryProjectionService
        hra_svc = Section10HraExemptionService(self.env)
        sal_proj_svc = SalaryProjectionService(self.env)

        for rec in self:
            if not rec.employee_id or not rec.financial_year_id:
                rec.decl_hra_eligible = False
                rec.decl_hra_ineligibility_reason = False
                rec.decl_hra_allowed_exemption = 0.0
                rec.decl_hra_actual_received = 0.0
                continue

            # Salary projections for HRA & Basic
            sal_res = sal_proj_svc.project_salary(rec.employee_id, rec.financial_year_id)
            annual_basic_salary = (sal_res.total_basic or 0.0) + (sal_res.total_da or 0.0)
            actual_hra_received = sal_res.total_hra or 0.0
            hra_line = rec.declaration_line_ids.filtered(lambda l: l.category == 'hra')
            annual_rent_paid = float(
                hra_line[0].usable_amount if (hra_line and hra_line[0].usable_amount > 0.0)
                else (rec.decl_hra_annual_rent or 0.0)
            )
            is_metro = bool(rec.decl_hra_is_metro)
            own_prop = bool(rec.decl_hra_own_residential_property_at_workplace or rec.own_residential_property_at_workplace)
            r_from = rec.decl_hra_rent_period_from or rec.rent_period_from
            r_to = rec.decl_hra_rent_period_to or rec.rent_period_to

            res = hra_svc.calculate_exemption(
                annual_rent_paid=annual_rent_paid,
                actual_hra_received=actual_hra_received,
                annual_basic_salary=annual_basic_salary,
                is_metro=is_metro,
                employee=rec.employee_id,
                financial_year=rec.financial_year_id,
                declaration=rec,
                regime_code=rec.regime_code or 'old',
                own_residential_property_at_workplace=own_prop,
                rent_period_from=r_from,
                rent_period_to=r_to,
                annual_basic_component=sal_res.total_basic,
                annual_da_component=sal_res.total_da
            )

            rec.decl_hra_eligible = res.is_eligible
            rec.decl_hra_ineligibility_reason = res.rejection_reason if not res.is_eligible else False
            rec.decl_hra_allowed_exemption = res.exempt_amount
            rec.decl_hra_actual_received = actual_hra_received

    @api.depends(
        'decl_hra_annual_rent', 'decl_hra_is_metro', 'decl_hra_own_residential_property_at_workplace',
        'own_residential_property_at_workplace', 'decl_hra_rent_period_from', 'decl_hra_rent_period_to',
        'rent_period_from', 'rent_period_to', 'regime_code', 'employee_id',
        'financial_year_id', 'decl_hra_eligible', 'decl_hra_ineligibility_reason', 'decl_hra_allowed_exemption',
        'decl_hra_actual_received', 'declaration_line_ids.declared_amount', 'declaration_line_ids.approved_amount'
    )
    def _compute_hra_summary_html(self):
        for rec in self:
            if not rec.employee_id or not rec.financial_year_id:
                rec.decl_hra_summary_html = False
                continue

            r_from = rec.decl_hra_rent_period_from or rec.rent_period_from
            r_to = rec.decl_hra_rent_period_to or rec.rent_period_to
            r_from_str = r_from.strftime('%d-%m-%Y') if r_from else (rec.financial_year_id.start_date.strftime('%d-%m-%Y') if rec.financial_year_id and rec.financial_year_id.start_date else 'N/A')
            r_to_str = r_to.strftime('%d-%m-%Y') if r_to else (rec.financial_year_id.end_date.strftime('%d-%m-%Y') if rec.financial_year_id and rec.financial_year_id.end_date else 'N/A')
            own_prop = bool(rec.decl_hra_own_residential_property_at_workplace or rec.own_residential_property_at_workplace)
            own_prop_str = "Yes" if own_prop else "No"
            hra_line = rec.declaration_line_ids.filtered(lambda l: l.category == 'hra')
            annual_rent_paid = float(
                hra_line[0].usable_amount if (hra_line and hra_line[0].usable_amount > 0.0)
                else (rec.decl_hra_annual_rent or 0.0)
            )
            actual_hra_received = float(rec.decl_hra_actual_received or 0.0)

            if not rec.decl_hra_eligible:
                rec.decl_hra_summary_html = f"""
                <div style="padding: 10px; border-radius: 6px; background-color: #fdf2f2; border: 1px solid #f8b4b4; margin-top: 8px;">
                    <div style="font-weight: bold; color: #9b1c1c; margin-bottom: 4px;">Section 10(13A) HRA Status: ❌ NOT ELIGIBLE</div>
                    <div style="color: #771d1d; font-size: 13px;"><strong>Reason:</strong> {rec.decl_hra_ineligibility_reason or 'Eligibility conditions not met.'}</div>
                    <div style="color: #771d1d; font-size: 12px; margin-top: 4px;"><strong>Allowed HRA Exemption:</strong> ₹0.00</div>
                </div>
                """
            else:
                rec.decl_hra_summary_html = f"""
                <div style="padding: 10px; border-radius: 6px; background-color: #f3faf7; border: 1px solid #84e1bc; margin-top: 8px;">
                    <div style="font-weight: bold; color: #03543f; margin-bottom: 4px;">Section 10(13A) HRA Status: ✅ ELIGIBLE</div>
                    <div style="font-size: 13px; color: #046c4e;">
                        <div>• <strong>HRA Received:</strong> ₹{actual_hra_received:,.2f}</div>
                        <div>• <strong>Rent Paid:</strong> ₹{annual_rent_paid:,.2f}</div>
                        <div>• <strong>Rent Period:</strong> {r_from_str} to {r_to_str}</div>
                        <div>• <strong>Own Residential Property:</strong> {own_prop_str}</div>
                        <div style="margin-top: 4px; font-weight: bold; color: #03543f;">• <strong>Allowed HRA Exemption:</strong> ₹{rec.decl_hra_allowed_exemption:,.2f}</div>
                    </div>
                </div>
                """

    @api.onchange('own_residential_property_at_workplace', 'decl_hra_own_residential_property_at_workplace')
    def _onchange_hra_own_property(self):
        if self.own_residential_property_at_workplace != self.decl_hra_own_residential_property_at_workplace:
            val = self.own_residential_property_at_workplace or self.decl_hra_own_residential_property_at_workplace
            self.own_residential_property_at_workplace = val
            self.decl_hra_own_residential_property_at_workplace = val

    @api.onchange('rent_period_from', 'decl_hra_rent_period_from')
    def _onchange_hra_rent_from(self):
        val = self.rent_period_from or self.decl_hra_rent_period_from
        if val:
            self.rent_period_from = val
            self.decl_hra_rent_period_from = val

    @api.onchange('rent_period_to', 'decl_hra_rent_period_to')
    def _onchange_hra_rent_to(self):
        val = self.rent_period_to or self.decl_hra_rent_period_to
        if val:
            self.rent_period_to = val
            self.decl_hra_rent_period_to = val

    @api.constrains('decl_hra_annual_rent', 'decl_hra_landlord_name', 'decl_hra_landlord_pan', 'decl_hra_rent_period_from', 'decl_hra_rent_period_to', 'rent_period_from', 'rent_period_to')
    def _check_hra_landlord_validation(self):
        pan_regex = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$')
        for rec in self:
            rent = rec.decl_hra_annual_rent or 0.0
            r_from = rec.decl_hra_rent_period_from or rec.rent_period_from
            r_to = rec.decl_hra_rent_period_to or rec.rent_period_to
            if r_from and r_to and r_to < r_from:
                raise ValidationError(_("Invalid HRA rent period: Rent To date cannot be before Rent From date."))
            if rent > 0.0:
                if not rec.decl_hra_landlord_name or not rec.decl_hra_landlord_name.strip():
                    raise ValidationError(_("Landlord Name is mandatory when declaring House Rent Allowance (HRA) rent of ₹%s.") % f"{rent:,.2f}")
            if rent > 100000.0:
                pan = (rec.decl_hra_landlord_pan or '').strip().upper()
                if not pan:
                    raise ValidationError(_("CBDT Statutory Requirement: Landlord PAN is mandatory when annual rent exceeds ₹1,00,000 p.a. (Current declaration: ₹%s p.a. / ₹%s monthly). Please enter Landlord PAN before submitting.") % (f"{rent:,.2f}", f"{(rent/12.0):,.2f}"))
                if not pan_regex.match(pan):
                    raise ValidationError(_("Invalid Landlord PAN '%s'. Landlord PAN must be a valid 10-character Indian PAN format (e.g. ABCDE1234F).") % rec.decl_hra_landlord_pan)

    # Section 10(5) Leave Travel Allowance (LTA) Fields
    decl_lta_declared_fare = fields.Monetary(
        string="Declared Travel Fare Amount (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 10(5) - Employee declared travel fare amount for LTA exemption."
    )
    decl_lta_journey_date = fields.Date(
        string="Actual Journey Date",
        store=True,
        help="Section 10(5) - Mandatory date on which the journey was undertaken."
    )
    decl_lta_travel_mode = fields.Selection([
        ('air', 'Air (Economy Class)'),
        ('rail', 'Rail (AC First Class)'),
        ('public_transport', 'Recognised Public Transport'),
        ('other', 'Other Mode')
    ], string="Mode of Travel", default='air', store=True,
       help="Section 10(5) read with Rule 2B - Mode of transport used for travel.")
    decl_lta_family_members_count = fields.Integer(
        string="Accompanying Family Members Count",
        default=1,
        store=True,
        help="Section 10(5) - Number of eligible family members accompanying the employee."
    )
    decl_lta_origin = fields.Char(
        string="Origin City / Place",
        default="Kochi",
        store=True,
        help="Section 10(5) - Place of journey origin within India."
    )
    decl_lta_destination = fields.Char(
        string="Destination City / Place",
        default="Delhi",
        store=True,
        help="Section 10(5) - Place of journey destination within India."
    )
    decl_lta_origin_country = fields.Selection([
        ('IN', 'India (Domestic)'),
        ('OTHER', 'International (Ineligible)')
    ], string="Origin Country", default='IN', store=True,
       help="Section 10(5) - Origin country. Must be India for LTA exemption.")
    decl_lta_destination_country = fields.Selection([
        ('IN', 'India (Domestic)'),
        ('OTHER', 'International (Ineligible)')
    ], string="Destination Country", default='IN', store=True,
       help="Section 10(5) - Destination country. Must be India for LTA exemption.")
    decl_lta_travel_fare = fields.Monetary(
        string="Eligible Pure Travel Fare Amount (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 10(5) - Pure travel fare (excluding lodging, boarding, sightseeing)."
    )
    decl_lta_lodging = fields.Monetary(
        string="Lodging / Hotel Expenses (Ineligible) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Ineligible lodging/hotel expenses incurred during travel."
    )
    decl_lta_boarding = fields.Monetary(
        string="Boarding / Meals Expenses (Ineligible) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Ineligible boarding/meal expenses incurred during travel."
    )
    decl_lta_local_conveyance = fields.Monetary(
        string="Local Conveyance / Sightseeing (Ineligible) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Ineligible local taxi, bus, or sightseeing expenses."
    )
    decl_lta_other_expenses = fields.Monetary(
        string="Other Incidental Expenses (Ineligible) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Ineligible incidental travel expenses."
    )
    decl_lta_has_children = fields.Boolean(
        string="Includes Travel of Children",
        default=False,
        store=True,
        help="Rule 2B - Tick if travel includes children of the employee."
    )
    decl_lta_children_count = fields.Integer(
        string="Number of Children",
        default=0,
        store=True,
        help="Rule 2B - Number of children accompanying the employee."
    )
    decl_lta_children_born_after_oct1998 = fields.Integer(
        string="Children Born on/after 01-Oct-1998",
        default=0,
        store=True,
        help="Rule 2B - Number of children born on or after 01-Oct-1998."
    )
    decl_lta_has_multiple_births = fields.Boolean(
        string="Multiple Births Exception (Twins/Triplets)",
        default=False,
        store=True,
        help="Rule 2B - Tick if second birth resulted in multiple children (Twins/Triplets)."
    )
    decl_lta_shortest_route_reference_fare = fields.Monetary(
        string="Shortest Route Reference Fare Ceiling (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Rule 2B - Statutory reference fare ceiling for shortest route."
    )
    decl_lta_amount_received = fields.Monetary(
        string="Actual LTA Received from Employer (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Actual LTA/LTC amount received or paid by employer for the eligible journey."
    )
    decl_lta_spouse_travelling = fields.Boolean(
        string="Spouse Accompanying Travel",
        default=False,
        store=True,
        help="Tick if spouse accompanied employee during travel."
    )
    decl_lta_dependent_parents_count = fields.Integer(
        string="Dependent Parents Count",
        default=0,
        store=True,
        help="Number of dependent parents accompanying travel."
    )
    decl_lta_dependent_siblings_count = fields.Integer(
        string="Dependent Siblings Count",
        default=0,
        store=True,
        help="Number of dependent brothers/sisters accompanying travel."
    )
    decl_lta_attachment_ids = fields.Many2many(
        'ir.attachment',
        'tds_decl_lta_attachment_rel',
        'declaration_id',
        'attachment_id',
        string="LTA Travel Proof Receipts & Boarding Passes",
        help="Supporting travel tickets, boarding passes, or railway receipts for LTA claim."
    )

    # Section 10(5) LTA System Calculated Fields (Readonly / Non-editable)
    lta_eligibility_status = fields.Selection([
        ('eligible', 'Eligible'),
        ('ineligible', 'Ineligible'),
        ('pending_verification', 'Pending Verification')
    ], string="LTA Eligibility Status", compute='_compute_lta_statutory_fields', store=True,
       help="System-evaluated statutory eligibility status for LTA exemption.")
    lta_block_period = fields.Char(
        string="LTA Block Period",
        compute='_compute_lta_statutory_fields', store=True,
        help="Calculated 4-calendar-year block period (e.g., 2022-2025)."
    )
    lta_claim_sequence = fields.Char(
        string="LTA Claim Sequence in Block",
        compute='_compute_lta_statutory_fields', store=True,
        help="Sequence of current LTA claim within the 4-CY block (e.g. Claim 1 of 2)."
    )
    lta_remaining_claims = fields.Integer(
        string="Remaining Claims in Block",
        compute='_compute_lta_statutory_fields', store=True,
        help="Remaining allowable LTA journey claims in current block."
    )
    lta_carry_forward_used = fields.Boolean(
        string="Carry-Forward Entitlement Utilized",
        compute='_compute_lta_statutory_fields', store=True,
        help="Indicates if carry-forward claim from prior block is utilized."
    )
    lta_statutory_fare_ceiling = fields.Monetary(
        string="Statutory Mode & Route Ceiling (₹)",
        currency_field='currency_id',
        compute='_compute_lta_statutory_fields', store=True,
        help="Applicable Rule 2B statutory fare ceiling based on mode and shortest route."
    )
    lta_eligible_travel_fare = fields.Monetary(
        string="Eligible Pure Travel Fare (₹)",
        currency_field='currency_id',
        compute='_compute_lta_statutory_fields', store=True,
        help="Statutory eligible pure travel fare after applying Rule 2B caps."
    )
    lta_taxable_amount = fields.Monetary(
        string="Taxable LTA Amount (₹)",
        currency_field='currency_id',
        compute='_compute_lta_statutory_fields', store=True,
        help="Taxable LTA portion (Actual LTA Received minus Statutory Exemption)."
    )

    lta_ineligibility_reason = fields.Text(
        string="LTA Ineligibility Reason",
        compute='_compute_lta_statutory_fields', store=True,
        help="Detailed reason(s) if LTA claim is not eligible under Section 10(5) / Rule 2B."
    )
    lta_calculation_phase = fields.Selection([
        ('pre_proof', 'PRE-PROOF / PROJECTED'),
        ('post_proof', 'POST-PROOF / VERIFIED')
    ], string="LTA Calculation Phase", compute='_compute_lta_statutory_fields', store=True,
       help="Calculation phase indicator distinguishing preliminary planning from verified proof calculation.")

    lta_pass_regime = fields.Boolean("Old Tax Regime", compute='_compute_lta_statutory_fields', store=True)
    lta_pass_journey = fields.Boolean("Journey Performed / Date Provided", compute='_compute_lta_statutory_fields', store=True)
    lta_pass_domestic = fields.Boolean("Domestic Travel Only", compute='_compute_lta_statutory_fields', store=True)
    lta_pass_family = fields.Boolean("Eligible Family Members", compute='_compute_lta_statutory_fields', store=True)
    lta_pass_block = fields.Boolean("Block Claim Limit (Max 2)", compute='_compute_lta_statutory_fields', store=True)
    lta_pass_child_limit = fields.Boolean("Child Count Limit (Rule 2B)", compute='_compute_lta_statutory_fields', store=True)
    lta_pass_ceiling = fields.Boolean("Statutory Mode Fare Ceiling", compute='_compute_lta_statutory_fields', store=True)

    decl_lta_summary_html = fields.Html(
        string="Section 10(5) LTA Status",
        compute='_compute_lta_summary_html',
        store=False,
        help="Visual card displaying Section 10(5) LTA eligibility, formula breakdown, block tracking, and compliance checklist."
    )

    @api.depends(
        'decl_lta_declared_fare', 'decl_lta_amount_received', 'decl_lta_approved_amount',
        'decl_lta_journey_date', 'decl_lta_travel_mode', 'decl_lta_origin', 'decl_lta_destination',
        'decl_lta_origin_country', 'decl_lta_destination_country', 'decl_lta_family_members_count',
        'decl_lta_has_children', 'decl_lta_children_count', 'decl_lta_children_born_after_oct1998',
        'decl_lta_has_multiple_births', 'lta_eligibility_status', 'decl_lta_amount',
        'lta_block_period', 'lta_claim_sequence', 'lta_remaining_claims', 'lta_statutory_fare_ceiling',
        'lta_eligible_travel_fare', 'lta_taxable_amount', 'lta_ineligibility_reason',
        'lta_calculation_phase', 'regime_code', 'state', 'employee_id', 'financial_year_id'
    )
    def _compute_lta_summary_html(self):
        for rec in self:
            if not rec.employee_id or not rec.financial_year_id:
                rec.decl_lta_summary_html = False
                continue

            is_eligible = (rec.lta_eligibility_status == 'eligible')
            phase_label = "🔒 POST-PROOF / VERIFIED" if rec.lta_calculation_phase == 'post_proof' else "ℹ️ PRE-PROOF / PROJECTED"
            phase_color = "#03543f" if rec.lta_calculation_phase == 'post_proof' else "#1e40af"
            phase_bg = "#def7ec" if rec.lta_calculation_phase == 'post_proof' else "#dbeafe"

            check_regime = "✅ PASS" if rec.lta_pass_regime else "❌ FAIL (New Regime Prohibited)"
            check_journey = "✅ PASS" if rec.lta_pass_journey else "❌ FAIL (Date Missing)"
            check_domestic = "✅ PASS" if rec.lta_pass_domestic else "❌ FAIL (International Travel)"
            check_child = "✅ PASS" if rec.lta_pass_child_limit else "❌ FAIL (>2 Children Restriction)"

            # Run LTA Exemption Service to get full result DTO
            try:
                from ..services.tds.section10_lta_exemption_service import Section10LtaExemptionService
                svc = Section10LtaExemptionService(self.env)
                res = svc.validate_and_calculate(declaration=rec)
                res_dict = res.to_dict()
            except (AttributeError, ValueError, KeyError, UserError, ValidationError) as err:
                _logger.warning("LTA Exemption calculation fallback for declaration ID %s: %s", rec.id, str(err))
                res_dict = {
                    'current_block': rec.lta_block_period or '2026-2029',
                    'previous_block': '2022-2025',
                    'normal_entitlement': 2,
                    'normal_claims_used': 0,
                    'normal_claims_remaining': rec.lta_remaining_claims,
                    'carry_forward_available': 0,
                    'carry_forward_status': 'not_applicable'
                }
            except Exception as err:
                _logger.error("Unexpected error in LTA Exemption calculation for declaration ID %s: %s", rec.id, str(err), exc_info=True)
                res_dict = {
                    'current_block': rec.lta_block_period or '2026-2029',
                    'previous_block': '2022-2025',
                    'normal_entitlement': 2,
                    'normal_claims_used': 0,
                    'normal_claims_remaining': rec.lta_remaining_claims,
                    'carry_forward_available': 0,
                    'carry_forward_status': 'not_applicable'
                }

            curr_blk = res_dict.get('current_block', '2026-2029')
            prev_blk = res_dict.get('previous_block', '2022-2025')
            norm_ent = res_dict.get('normal_entitlement', 2)
            norm_used = res_dict.get('normal_claims_used', 0)
            norm_rem = res_dict.get('normal_claims_remaining', 2)
            cf_status = str(res_dict.get('carry_forward_status', 'not_applicable')).upper()
            cf_avail = res_dict.get('carry_forward_available', 0)

            if not is_eligible:
                reason_text = rec.lta_ineligibility_reason or ("Not eligible for Section 10(5) exemption under selected tax regime" if rec.regime_code != 'old' else "Journey date has not been provided or statutory conditions not met.")
                rec.decl_lta_summary_html = f"""
                <div style="padding: 14px; border-radius: 8px; background-color: #fdf2f2; border: 1px solid #f8b4b4; margin-top: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-weight: bold; font-size: 14px; color: #9b1c1c;">Section 10(5) LTA Status: ❌ NOT ELIGIBLE</span>
                        <span style="font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 12px; background-color: {phase_bg}; color: {phase_color};">{phase_label}</span>
                    </div>
                    <div style="color: #771d1d; font-size: 13px; margin-bottom: 8px;"><strong>Reason:</strong> {reason_text}</div>
                    <div style="color: #771d1d; font-size: 13px; font-weight: bold;">Allowed LTA Exemption: ₹0.00</div>
                    <div style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed #f8b4b4; font-size: 12px; color: #9b1c1c;">
                        <strong>Entitlement Tracking:</strong> Block: {curr_blk} | Normal Remaining: {norm_rem}/{norm_ent} | CF Status: {cf_status}
                    </div>
                </div>
                """
            else:
                rec.decl_lta_summary_html = f"""
                <div style="padding: 14px; border-radius: 8px; background-color: #f3faf7; border: 1px solid #84e1bc; margin-top: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-weight: bold; font-size: 14px; color: #03543f;">Section 10(5) LTA Status: ✅ ELIGIBLE</span>
                        <span style="font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 12px; background-color: {phase_bg}; color: {phase_color};">{phase_label}</span>
                    </div>
                    <div style="font-size: 13px; color: #046c4e; display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">
                        <div>• <strong>Current Block:</strong> {curr_blk}</div>
                        <div>• <strong>Previous Block:</strong> {prev_blk}</div>
                        <div>• <strong>Normal Entitlement:</strong> {norm_ent} (Used: {norm_used} | Remaining: {norm_rem})</div>
                        <div>• <strong>Carry-Forward Status:</strong> {cf_status} (Available: {cf_avail})</div>
                        <div>• <strong>Declared Fare:</strong> ₹{rec.decl_lta_declared_fare:,.2f}</div>
                        <div>• <strong>Rule 2B Fare Ceiling:</strong> ₹{rec.lta_statutory_fare_ceiling:,.2f} ({str(rec.decl_lta_travel_mode or 'air').upper()})</div>
                        <div>• <strong>Actual LTA Received:</strong> ₹{rec.decl_lta_amount_received:,.2f}</div>
                        <div>• <strong>Eligible Travel Fare:</strong> ₹{rec.lta_eligible_travel_fare:,.2f}</div>
                    </div>
                    <div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid #84e1bc; font-size: 14px; font-weight: bold; color: #03543f;">
                        Allowed Statutory Exemption = MIN(Actual Fare, Rule 2B Ceiling, LTA Received) = ₹{rec.decl_lta_amount:,.2f}
                    </div>
                    <div style="margin-top: 6px; font-size: 12px; color: #046c4e;">
                        <strong>Compliance Checklist:</strong> Old Regime: ✅ PASS | Domestic: ✅ PASS | Journey Date: ✅ PASS | Child Limit: {check_child}
                    </div>
                </div>
                """

    decl_lta_amount = fields.Monetary(
        string="Statutory Approved LTA Exemption (₹)",
        currency_field='currency_id',
        compute='_compute_lta_statutory_fields',
        store=True,
        help="Computed statutory Section 10(5) LTA exemption amount."
    )
    decl_lta_approved_amount = fields.Monetary(
        string="Tax Firm Approved LTA Fare (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Tax firm verified and approved travel fare amount."
    )

    @api.depends(
        'decl_lta_declared_fare', 'decl_lta_amount_received', 'decl_lta_approved_amount',
        'decl_lta_journey_date', 'decl_lta_travel_mode', 'decl_lta_origin', 'decl_lta_destination',
        'decl_lta_origin_country', 'decl_lta_destination_country', 'decl_lta_family_members_count',
        'decl_lta_has_children', 'decl_lta_children_count', 'decl_lta_children_born_after_oct1998',
        'decl_lta_has_multiple_births', 'decl_lta_travel_fare', 'decl_lta_lodging', 'decl_lta_boarding',
        'decl_lta_local_conveyance', 'decl_lta_other_expenses', 'decl_lta_shortest_route_reference_fare',
        'regime_code', 'state'
    )
    def _compute_lta_statutory_fields(self):
        from ..services.tds.section10_lta_exemption_service import Section10LtaExemptionService
        lta_svc = Section10LtaExemptionService(self.env)
        for rec in self:
            res = lta_svc.validate_and_calculate(
                employee=rec.employee_id,
                declared_fare=rec.decl_lta_declared_fare,
                actual_lta_received=rec.decl_lta_amount_received,
                regime_code=rec.regime_code,
                declaration=rec,
                eval_date=rec.decl_lta_journey_date or fields.Date.today()
            )
            rec.lta_eligibility_status = res.eligibility_status
            rec.lta_block_period = str(res.block_period)
            rec.lta_claim_sequence = res.claim_sequence
            rec.lta_remaining_claims = res.remaining_claims
            rec.lta_carry_forward_used = res.carry_forward_used
            rec.lta_statutory_fare_ceiling = res.statutory_fare_ceiling
            rec.lta_eligible_travel_fare = res.eligible_travel_fare
            rec.lta_taxable_amount = res.taxable_amount
            rec.decl_lta_amount = res.exempt_amount

            rec.lta_ineligibility_reason = res.remarks if not res.is_eligible else False
            rec.lta_calculation_phase = 'post_proof' if rec.state in ('proof_verified', 'approved') else 'pre_proof'

            rec.lta_pass_regime = (rec.regime_code == 'old')
            rec.lta_pass_journey = bool(rec.decl_lta_journey_date) or (rec.decl_lta_declared_fare > 0.0 and rec.state in ('draft', 'submitted'))
            rec.lta_pass_domestic = (rec.decl_lta_origin_country == 'IN' and rec.decl_lta_destination_country == 'IN')
            rec.lta_pass_family = True
            rec.lta_pass_block = getattr(res, 'is_eligible', True)
            rec.lta_pass_child_limit = not (rec.decl_lta_has_children and rec.decl_lta_children_born_after_oct1998 > 2 and not rec.decl_lta_has_multiple_births)
            rec.lta_pass_ceiling = (res.eligible_travel_fare <= res.statutory_fare_ceiling) if res.statutory_fare_ceiling > 0 else True

            # Generate Rich UI Summary Card HTML
            phase_label = "🔒 POST-PROOF / VERIFIED" if rec.lta_calculation_phase == 'post_proof' else "ℹ️ PRE-PROOF / PROJECTED"
            phase_color = "#03543f" if rec.lta_calculation_phase == 'post_proof' else "#1e40af"
            phase_bg = "#def7ec" if rec.lta_calculation_phase == 'post_proof' else "#dbeafe"

            check_regime = "✅ PASS" if rec.lta_pass_regime else "❌ FAIL (New Regime Prohibited)"
            check_journey = "✅ PASS" if rec.lta_pass_journey else "❌ FAIL (Date Missing)"
            check_domestic = "✅ PASS" if rec.lta_pass_domestic else "❌ FAIL (International Travel)"
            check_child = "✅ PASS" if rec.lta_pass_child_limit else "❌ FAIL (>2 Children Restriction)"

            if not res.is_eligible:
                rec.decl_lta_summary_html = f"""
                <div style="padding: 14px; border-radius: 8px; background-color: #fdf2f2; border: 1px solid #f8b4b4; margin-top: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-weight: bold; font-size: 14px; color: #9b1c1c;">Section 10(5) LTA Status: ❌ NOT ELIGIBLE</span>
                        <span style="font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 12px; background-color: {phase_bg}; color: {phase_color};">{phase_label}</span>
                    </div>
                    <div style="color: #771d1d; font-size: 13px; margin-bottom: 8px;"><strong>Reason:</strong> {rec.lta_ineligibility_reason or 'Statutory eligibility conditions not met.'}</div>
                    <div style="color: #771d1d; font-size: 13px; font-weight: bold;">Allowed LTA Exemption: ₹0.00</div>
                    <div style="margin-top: 8px; pt-8px; border-top: 1px dashed #f8b4b4; font-size: 12px; color: #9b1c1c;">
                        <strong>Compliance Checklist:</strong> Old Regime: {check_regime} | Domestic: {check_domestic} | Journey Date: {check_journey}
                    </div>
                </div>
                """
            else:
                rec.decl_lta_summary_html = f"""
                <div style="padding: 14px; border-radius: 8px; background-color: #f3faf7; border: 1px solid #84e1bc; margin-top: 10px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-weight: bold; font-size: 14px; color: #03543f;">Section 10(5) LTA Status: ✅ ELIGIBLE</span>
                        <span style="font-size: 11px; font-weight: bold; padding: 3px 8px; border-radius: 12px; background-color: {phase_bg}; color: {phase_color};">{phase_label}</span>
                    </div>
                    <div style="font-size: 13px; color: #046c4e; display: grid; grid-template-columns: 1fr 1fr; gap: 6px;">
                        <div>• <strong>Declared Fare:</strong> ₹{rec.decl_lta_declared_fare:,.2f}</div>
                        <div>• <strong>Actual LTA Received:</strong> ₹{rec.decl_lta_amount_received:,.2f}</div>
                        <div>• <strong>Rule 2B Fare Ceiling:</strong> ₹{res.statutory_fare_ceiling:,.2f} ({str(rec.decl_lta_travel_mode or 'air').upper()})</div>
                        <div>• <strong>Eligible Travel Fare:</strong> ₹{res.eligible_travel_fare:,.2f}</div>
                        <div>• <strong>Block Period:</strong> {res.block_period}</div>
                        <div>• <strong>Claim Sequence:</strong> {res.claim_sequence}</div>
                    </div>
                    <div style="margin-top: 10px; padding-top: 8px; border-top: 1px solid #84e1bc; font-size: 14px; font-weight: bold; color: #03543f;">
                        Allowed Statutory Exemption = MIN(Actual Fare, Rule 2B Ceiling, LTA Received) = ₹{res.exempt_amount:,.2f}
                    </div>
                    <div style="margin-top: 6px; font-size: 12px; color: #046c4e;">
                        <strong>Compliance Checklist:</strong> Old Regime: ✅ PASS | Domestic: ✅ PASS | Block Claims: ✅ PASS | Child Limit: {check_child}
                    </div>
                </div>
                """

    # Home Loan Interest
    decl_24b_self_interest = fields.Monetary(
        string="Self-Occupied Home Loan Interest (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 24(b) - Home Loan Interest"
    )
    decl_24b_loan_purpose = fields.Selection([
        ('purchase', 'Purchase'),
        ('construction', 'Construction'),
        ('repair_renovation', 'Repair-Renovation')
    ], string="Loan Taken For", default='purchase', store=True,
       help="Purpose for which housing loan was taken under Section 24(b): Purchase, Construction, or Repair-Renovation.")
    decl_24b_borrowing_date = fields.Date(
        string="Loan/Capital Borrowing Date",
        store=True,
        help="Date when housing loan/capital was borrowed under Section 24(b). Must be on or after 01-Apr-1999 for the ₹2,00,000 statutory limit."
    )
    decl_24b_completion_date = fields.Date(
        string="Construction/Purchase Completion Date",
        store=True,
        help="Date of completion of construction or purchase of residential property under Section 24(b)."
    )
    decl_80eea_interest = fields.Monetary(
        string="First-Time Home Buyer Interest (80EEA) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80EEA - First-Time Home Buyer Interest."
    )

    decl_80eea_lender_type = fields.Selection([
        ('scheduled_bank', 'Scheduled Bank'),
        ('housing_finance_company', 'Housing Finance Company'),
        ('nbfc', 'NBFC'),
        ('other', 'Other')
    ], string="80EEA Lending Institution Type", default='scheduled_bank', store=True,
       help="Category of lending institution sanctioning housing loan under Section 80EEA.")
    decl_80eea_interest_amount = fields.Monetary(
        string="80EEA Interest Amount",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Annual housing loan interest amount claimed under Section 80EEA."
    )
    decl_80eea_claimed_under_24b = fields.Monetary(
        string="Interest Already Claimed under Section 24(b)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Housing loan interest amount already claimed as deduction under Section 24(b)."
    )
    decl_80eea_loan_sanction_date = fields.Date(
        string="80EEA Loan Sanction Date",
        store=True,
        help="Sanction date of housing loan by bank (Must be between 01-Apr-2019 and 31-Mar-2022 for Section 80EEA)."
    )
    decl_80eea_property_stamp_value = fields.Monetary(
        string="80EEA Property Stamp Duty Value (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Stamp duty value of residential house property (Must not exceed ₹45,00,000 for Section 80EEA)."
    )
    decl_80eea_first_time_home_buyer = fields.Boolean(
        string="First-Time Home Buyer (Section 80EEA)",
        default=True,
        store=True,
        help="Mark True if employee does not own any other residential property on loan sanction date."
    )
    decl_80eea_claimed_under_80ee = fields.Boolean(
        string="Claimed Deduction under Section 80EE",
        default=False,
        store=True,
        help="Mark True if deduction has already been claimed under Section 80EE (Disqualifies Section 80EEA)."
    )
    decl_80eea_lending_institution = fields.Char(
        string="80EEA Lending Bank / Institution",
        store=True,
        help="Name of bank or financial institution (e.g. State Bank of India, HDFC Bank)."
    )
    decl_80eea_loan_account_number = fields.Char(
        string="80EEA Loan Account Number",
        store=True,
        help="Housing loan account number."
    )

    # Section 24(b) Status & Summary HTML Card
    decl_24b_eligible = fields.Boolean(
        string="Section 24(b) Eligible",
        compute='_compute_24b_status',
        store=False
    )
    decl_24b_ineligibility_reason = fields.Char(
        string="24(b) Ineligibility Reason",
        compute='_compute_24b_status',
        store=False
    )
    decl_24b_allowed_deduction = fields.Monetary(
        string="Allowed 24(b) Deduction",
        currency_field='currency_id',
        compute='_compute_24b_status',
        store=False
    )
    decl_24b_applicable_cap = fields.Monetary(
        string="Applicable 24(b) Cap",
        currency_field='currency_id',
        compute='_compute_24b_status',
        store=False
    )
    decl_24b_summary_html = fields.Html(
        string="Section 24(b) Status Card",
        compute='_compute_24b_summary_html',
        store=False
    )

    # Section 80EEA Status & Summary HTML Card
    decl_80eea_eligible = fields.Boolean(
        string="Section 80EEA Eligible",
        compute='_compute_80eea_status',
        store=False
    )
    decl_80eea_ineligibility_reason = fields.Char(
        string="80EEA Ineligibility Reason",
        compute='_compute_80eea_status',
        store=False
    )
    decl_80eea_allowed_deduction = fields.Monetary(
        string="Allowed 80EEA Deduction",
        currency_field='currency_id',
        compute='_compute_80eea_status',
        store=False
    )
    decl_80eea_remaining_interest = fields.Monetary(
        string="Remaining Interest for 80EEA",
        currency_field='currency_id',
        compute='_compute_80eea_status',
        store=False
    )
    decl_80eea_summary_html = fields.Html(
        string="Section 80EEA Status Card",
        compute='_compute_80eea_summary_html',
        store=False
    )

    @api.depends(
        'decl_24b_self_interest', 'decl_24b_loan_purpose', 'decl_24b_borrowing_date',
        'decl_24b_completion_date', 'regime_code', 'employee_id', 'financial_year_id',
        'declaration_line_ids.declared_amount', 'declaration_line_ids.approved_amount'
    )
    def _compute_24b_status(self):
        from ..services.tds.tds_parameter_service import TdsParameterService
        param_svc = TdsParameterService(self.env)

        for rec in self:
            if not rec.employee_id or not rec.financial_year_id:
                rec.decl_24b_eligible = False
                rec.decl_24b_ineligibility_reason = False
                rec.decl_24b_allowed_deduction = 0.0
                rec.decl_24b_applicable_cap = 0.0
                continue

            regime = (rec.regime_code or 'old').lower()
            if regime == 'new':
                rec.decl_24b_eligible = False
                rec.decl_24b_ineligibility_reason = "Section 24(b) deduction on self-occupied house property is not permissible under the New Tax Regime Income-tax Act, 2025 — Section 202(1)."
                rec.decl_24b_allowed_deduction = 0.0
                rec.decl_24b_applicable_cap = 0.0
                continue

            # Resolve declared/approved amount
            is_post_proof = rec.state in ('proof_verified', 'approved')
            line_24b = next((l for l in rec.declaration_line_ids if l.category == '24b' and getattr(l, 'active', True)), None)
            if line_24b:
                line_appr = float(getattr(line_24b, 'tax_firm_approved_amount', 0.0) or getattr(line_24b, 'approved_amount', 0.0) or 0.0)
                sec_24b_amt = line_appr if (is_post_proof and line_appr > 0.0) else line_24b.usable_amount
            elif is_post_proof and (getattr(rec, 'decl_24b_approved_amount', 0.0) or 0.0) > 0:
                sec_24b_amt = float(rec.decl_24b_approved_amount or 0.0)
            else:
                sec_24b_amt = float(rec.decl_24b_self_interest or 0.0)

            if sec_24b_amt <= 0.0:
                rec.decl_24b_eligible = False
                rec.decl_24b_ineligibility_reason = "No self-occupied home loan interest declared."
                rec.decl_24b_allowed_deduction = 0.0
                rec.decl_24b_applicable_cap = 200000.0 if rec.decl_24b_loan_purpose in ('purchase', 'construction', False) else 30000.0
                continue

            # Evaluate purpose, 01-Apr-1999 rule & 5-year completion deadline
            purpose = rec.decl_24b_loan_purpose or 'purchase'
            borrowing_date = rec.decl_24b_borrowing_date
            completion_date = rec.decl_24b_completion_date

            completion_period_years = param_svc.get_24b_completion_period_years()
            borrowing_start_threshold = param_svc.get_24b_borrowing_start_date()
            repair_limit = param_svc.get_24b_repair_renovation_limit()
            purchase_limit = param_svc.get_home_loan_interest_limit() or 200000.0

            deadline = None
            deadline_str = "N/A"
            borrowing_fy_name = "N/A"
            borrowing_date_str = borrowing_date.strftime('%d-%b-%Y') if borrowing_date else "N/A"
            completion_date_str = completion_date.strftime('%d-%b-%Y') if completion_date else "N/A"

            if borrowing_date:
                b_year = borrowing_date.year
                b_month = borrowing_date.month
                fy_end_year = b_year + 1 if b_month >= 4 else b_year
                borrowing_fy_name = f"FY {fy_end_year-1}-{str(fy_end_year)[-2:]}"
                deadline = fields.Date.from_string(f"{fy_end_year + completion_period_years}-03-31")
                deadline_str = deadline.strftime('%d-%b-%Y')

            if purpose == 'repair_renovation':
                selected_cap = repair_limit
                reason = "Repair/Renovation loan subject to statutory ceiling of ₹30,000 under Section 24(b)."
            elif borrowing_date and borrowing_date < borrowing_start_threshold:
                selected_cap = repair_limit
                reason = f"Capital borrowed on {borrowing_date_str} is prior to 01-Apr-1999 statutory threshold. Deduction restricted to ₹30,000 under Section 24(b)."
            elif purpose in ('purchase', 'construction'):
                if completion_date and deadline:
                    if completion_date <= deadline:
                        selected_cap = purchase_limit
                        reason = f"Purchase/Construction completed within statutory {completion_period_years}-year deadline ({deadline_str}) from end of borrowing FY ({borrowing_fy_name}). Full ₹2,00,000 cap applicable."
                    else:
                        selected_cap = repair_limit
                        reason = f"Purchase/Construction completion ({completion_date_str}) exceeded statutory {completion_period_years}-year deadline ({deadline_str}) from end of borrowing FY ({borrowing_fy_name}). Restricted to ₹30,000 cap under Section 24(b)."
                else:
                    selected_cap = purchase_limit
                    reason = "Purchase/Construction loan with valid completion condition. Full ₹2,00,000 cap applicable."
            else:
                selected_cap = purchase_limit
                reason = "Standard purchase/construction limit."

            allowed_ded = min(sec_24b_amt, selected_cap)
            rec.decl_24b_eligible = (allowed_ded > 0.0)
            rec.decl_24b_ineligibility_reason = reason if allowed_ded == 0.0 else False
            rec.decl_24b_allowed_deduction = allowed_ded
            rec.decl_24b_applicable_cap = selected_cap

    @api.depends(
        'decl_24b_eligible', 'decl_24b_ineligibility_reason', 'decl_24b_allowed_deduction',
        'decl_24b_applicable_cap', 'decl_24b_self_interest', 'decl_24b_loan_purpose',
        'decl_24b_borrowing_date', 'decl_24b_completion_date', 'declaration_line_ids.declared_amount',
        'declaration_line_ids.approved_amount'
    )
    def _compute_24b_summary_html(self):
        for rec in self:
            if not rec.employee_id or not rec.financial_year_id:
                rec.decl_24b_summary_html = False
                continue

            purpose_dict = {'purchase': 'Purchase', 'construction': 'Construction', 'repair_renovation': 'Repair / Renovation'}
            purpose_label = purpose_dict.get(rec.decl_24b_loan_purpose, 'Purchase')
            is_post_proof = rec.state in ('proof_verified', 'approved')
            line_24b = next((l for l in rec.declaration_line_ids if l.category == '24b' and getattr(l, 'active', True)), None)
            if line_24b:
                line_appr = float(getattr(line_24b, 'tax_firm_approved_amount', 0.0) or getattr(line_24b, 'approved_amount', 0.0) or 0.0)
                sec_24b_amt = line_appr if (is_post_proof and line_appr > 0.0) else line_24b.usable_amount
            elif is_post_proof and (getattr(rec, 'decl_24b_approved_amount', 0.0) or 0.0) > 0:
                sec_24b_amt = float(rec.decl_24b_approved_amount or 0.0)
            else:
                sec_24b_amt = float(rec.decl_24b_self_interest or 0.0)

            if not rec.decl_24b_eligible:
                rec.decl_24b_summary_html = f"""
                <div style="padding: 10px; border-radius: 6px; background-color: #fdf2f2; border: 1px solid #f8b4b4; margin-top: 8px;">
                    <div style="font-weight: bold; color: #9b1c1c; margin-bottom: 4px;">Section 24(b) Status: ❌ NOT ELIGIBLE</div>
                    <div style="color: #771d1d; font-size: 13px;"><strong>Reason:</strong> {rec.decl_24b_ineligibility_reason or 'Eligibility conditions not met.'}</div>
                    <div style="color: #771d1d; font-size: 12px; margin-top: 4px;"><strong>Allowed 24(b) Deduction:</strong> ₹0.00</div>
                </div>
                """
            else:
                rec.decl_24b_summary_html = f"""
                <div style="padding: 10px; border-radius: 6px; background-color: #f3faf7; border: 1px solid #84e1bc; margin-top: 8px;">
                    <div style="font-weight: bold; color: #03543f; margin-bottom: 4px;">Section 24(b) Status: ✅ ELIGIBLE</div>
                    <div style="font-size: 13px; color: #046c4e;">
                        <div>• <strong>Property Status:</strong> Self-Occupied</div>
                        <div>• <strong>Loan Purpose:</strong> {purpose_label}</div>
                        <div>• <strong>Interest Considered:</strong> ₹{sec_24b_amt:,.2f}</div>
                        <div>• <strong>Applicable Statutory Cap:</strong> ₹{rec.decl_24b_applicable_cap:,.2f}</div>
                        <div style="margin-top: 4px; font-weight: bold; color: #03543f;">• <strong>Allowed 24(b) Deduction:</strong> ₹{rec.decl_24b_allowed_deduction:,.2f}</div>
                    </div>
                </div>
                """

    @api.depends(
        'decl_24b_self_interest', 'decl_24b_allowed_deduction', 'decl_80eea_interest_amount',
        'decl_80eea_lender_type', 'decl_80eea_loan_sanction_date', 'decl_80eea_property_stamp_value',
        'decl_80eea_first_time_home_buyer', 'decl_80eea_claimed_under_80ee', 'regime_code',
        'employee_id', 'financial_year_id', 'declaration_line_ids.declared_amount',
        'declaration_line_ids.approved_amount'
    )
    def _compute_80eea_status(self):
        from ..services.tds.section_80eea_eligibility_service import Section80EEAEligibilityService
        eea_svc = Section80EEAEligibilityService(self.env)

        for rec in self:
            if not rec.employee_id or not rec.financial_year_id:
                rec.decl_80eea_eligible = False
                rec.decl_80eea_ineligibility_reason = False
                rec.decl_80eea_allowed_deduction = 0.0
                rec.decl_80eea_remaining_interest = 0.0
                continue

            regime = (rec.regime_code or 'old').lower()
            if regime == 'new':
                rec.decl_80eea_eligible = False
                rec.decl_80eea_ineligibility_reason = "Section 80EEA deduction is not permissible under the New Tax Regime Income-tax Act, 2025 — Section 202(1)."
                rec.decl_80eea_allowed_deduction = 0.0
                rec.decl_80eea_remaining_interest = 0.0
                continue

            # Resolve declared/approved 24(b) amount
            is_post_proof = rec.state in ('proof_verified', 'approved')
            line_24b = next((l for l in rec.declaration_line_ids if l.category == '24b' and getattr(l, 'active', True)), None)
            total_interest = float(line_24b.declared_amount or 0.0) if line_24b else float(rec.decl_24b_self_interest or 0.0)
            if is_post_proof:
                line_appr = float(getattr(line_24b, 'tax_firm_approved_amount', 0.0) or getattr(line_24b, 'approved_amount', 0.0) or 0.0) if line_24b else float(getattr(rec, 'decl_24b_approved_amount', 0.0) or 0.0)
                if line_appr > 0.0:
                    total_interest = line_appr

            # Section 24(b) used
            sec_24b_used = rec.decl_24b_allowed_deduction or min(total_interest, 200000.0)
            remaining_interest = max(total_interest - sec_24b_used, 0.0)
            rec.decl_80eea_remaining_interest = remaining_interest

            # Check if 80EEA is actually claimed by the employee
            eea_amount_claimed = float(rec.decl_80eea_interest_amount or 0.0)
            line_80eea = next((l for l in rec.declaration_line_ids if l.category == '80eea' and getattr(l, 'active', True)), None)
            if line_80eea:
                eea_amount_claimed = max(eea_amount_claimed, float(line_80eea.declared_amount or 0.0))

            if eea_amount_claimed <= 0.0 and not rec.decl_80eea_loan_sanction_date:
                rec.decl_80eea_eligible = False
                rec.decl_80eea_ineligibility_reason = "No Section 80EEA deduction claimed."
                rec.decl_80eea_allowed_deduction = 0.0
                continue

            if total_interest <= 0.0 and eea_amount_claimed <= 0.0:
                rec.decl_80eea_eligible = False
                rec.decl_80eea_ineligibility_reason = "No home loan interest declared for Section 80EEA."
                rec.decl_80eea_allowed_deduction = 0.0
                continue

            if remaining_interest <= 0.0 and eea_amount_claimed <= 0.0:
                rec.decl_80eea_eligible = False
                rec.decl_80eea_ineligibility_reason = "Entire interest claimed and exhausted under Section 24(b); no residual interest available for Section 80EEA."
                rec.decl_80eea_allowed_deduction = 0.0
                continue

            claimed_amt = remaining_interest if remaining_interest > 0.0 else eea_amount_claimed

            res = eea_svc.validate_eligibility(
                rec,
                eval_date=fields.Date.today(),
                regime_code=regime,
                employee=rec.employee_id,
                financial_year=rec.financial_year_id,
                claimed_interest_amount=claimed_amt
            )

            rec.decl_80eea_eligible = res.is_eligible and (res.allowed_deduction > 0.0)
            rec.decl_80eea_ineligibility_reason = res.remarks if not rec.decl_80eea_eligible else False
            rec.decl_80eea_allowed_deduction = res.allowed_deduction

    @api.depends(
        'decl_80eea_eligible', 'decl_80eea_ineligibility_reason', 'decl_80eea_allowed_deduction',
        'decl_80eea_remaining_interest', 'decl_24b_self_interest', 'decl_24b_allowed_deduction',
        'decl_80eea_interest_amount', 'decl_80eea_loan_sanction_date',
        'declaration_line_ids.declared_amount', 'declaration_line_ids.approved_amount'
    )
    def _compute_80eea_summary_html(self):
        for rec in self:
            if not rec.employee_id or not rec.financial_year_id:
                rec.decl_80eea_summary_html = False
                continue

            eea_amount_claimed = float(rec.decl_80eea_interest_amount or 0.0)
            line_80eea = next((l for l in rec.declaration_line_ids if l.category == '80eea' and getattr(l, 'active', True)), None)
            if line_80eea:
                eea_amount_claimed = max(eea_amount_claimed, float(line_80eea.declared_amount or 0.0))

            if eea_amount_claimed <= 0.0 and not rec.decl_80eea_loan_sanction_date:
                rec.decl_80eea_summary_html = """
                <div style="padding: 10px; border-radius: 6px; background-color: #f8fafc; border: 1px solid #cbd5e1; margin-top: 8px;">
                    <div style="font-weight: bold; color: #475569; margin-bottom: 4px;">Section 80EEA Status: ℹ️ NOT CLAIMED (SKIPPED)</div>
                    <div style="color: #64748b; font-size: 13px;">No Section 80EEA deduction claimed by employee.</div>
                    <div style="color: #64748b; font-size: 12px; margin-top: 4px;"><strong>Allowed 80EEA Deduction:</strong> ₹0.00</div>
                </div>
                """
                continue

            is_post_proof = rec.state in ('proof_verified', 'approved')
            line_24b = next((l for l in rec.declaration_line_ids if l.category == '24b' and getattr(l, 'active', True)), None)
            total_interest = float(line_24b.declared_amount or 0.0) if line_24b else float(rec.decl_24b_self_interest or 0.0)
            if is_post_proof:
                line_appr = float(getattr(line_24b, 'tax_firm_approved_amount', 0.0) or getattr(line_24b, 'approved_amount', 0.0) or 0.0) if line_24b else float(getattr(rec, 'decl_24b_approved_amount', 0.0) or 0.0)
                if line_appr > 0.0:
                    total_interest = line_appr

            sec_24b_used = rec.decl_24b_allowed_deduction or min(total_interest, 200000.0)
            remaining_interest = rec.decl_80eea_remaining_interest or max(total_interest - sec_24b_used, 0.0)

            if not rec.decl_80eea_eligible:
                rec.decl_80eea_summary_html = f"""
                <div style="padding: 10px; border-radius: 6px; background-color: #fdf2f2; border: 1px solid #f8b4b4; margin-top: 8px;">
                    <div style="font-weight: bold; color: #9b1c1c; margin-bottom: 4px;">Section 80EEA Status: ❌ NOT ELIGIBLE</div>
                    <div style="color: #771d1d; font-size: 13px;"><strong>Reason:</strong> {rec.decl_80eea_ineligibility_reason or 'Eligibility conditions not met.'}</div>
                    <div style="color: #771d1d; font-size: 12px; margin-top: 4px;">
                        <span><strong>Total Interest:</strong> ₹{total_interest:,.2f}</span> |
                        <span><strong>24(b) Used:</strong> ₹{sec_24b_used:,.2f}</span> |
                        <span><strong>Remaining for 80EEA:</strong> ₹{remaining_interest:,.2f}</span> |
                        <span><strong>Max Cap:</strong> ₹1,50,000.00</span>
                    </div>
                    <div style="color: #771d1d; font-size: 12px; margin-top: 4px;"><strong>Allowed 80EEA Deduction:</strong> ₹0.00</div>
                </div>
                """
            else:
                rec.decl_80eea_summary_html = f"""
                <div style="padding: 10px; border-radius: 6px; background-color: #f3faf7; border: 1px solid #84e1bc; margin-top: 8px;">
                    <div style="font-weight: bold; color: #03543f; margin-bottom: 4px;">Section 80EEA Status: ✅ ELIGIBLE</div>
                    <div style="font-size: 13px; color: #046c4e;">
                        <div>• <strong>Total Declared Interest:</strong> ₹{total_interest:,.2f}</div>
                        <div>• <strong>Section 24(b) Deduction Used:</strong> ₹{sec_24b_used:,.2f}</div>
                        <div>• <strong>Remaining Interest for 80EEA:</strong> ₹{remaining_interest:,.2f}</div>
                        <div>• <strong>Section 80EEA Statutory Cap:</strong> ₹1,50,000.00</div>
                        <div style="margin-top: 4px; font-weight: bold; color: #03543f;">• <strong>Allowed 80EEA Deduction:</strong> ₹{rec.decl_80eea_allowed_deduction:,.2f}</div>
                    </div>
                </div>
                """

    # Other Chapter VI-A Deductions
    decl_80tta_interest = fields.Monetary(
        string="Savings Interest Deduction (80TTA) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80TTA - Savings Account Interest Deduction"
    )
    decl_80ttb_interest = fields.Monetary(
        string="Senior Citizen Interest (80TTB) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80TTB - Senior Citizen Savings & FD Interest"
    )
    decl_80e_interest = fields.Monetary(
        string="Education Loan Interest (80E) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80E - Education Loan Interest Paid"
    )
    decl_80e_loan_account_number = fields.Char(
        string="80E Loan Account Number",
        store=True,
        help="Education loan account number issued by lending institution."
    )
    decl_80e_loan_sanction_date = fields.Date(
        string="80E Loan Sanction Date",
        store=True,
        help="Date when education loan was sanctioned."
    )
    decl_80e_lender_name = fields.Char(
        string="80E Lending Institution Name",
        store=True,
        help="Full legal name of the lending bank or financial institution."
    )
    decl_80e_lender_type = fields.Selection([
        ('scheduled_bank', 'Scheduled Bank'),
        ('financial_institution', 'Financial Institution'),
        ('approved_charitable', 'Approved Charitable Institution'),
        ('private_individual', 'Private Individual'),
        ('employer', 'Employer'),
        ('friend_relative', 'Friend / Relative'),
        ('cooperative_society', 'Cooperative Society (Non-approved)'),
        ('foreign_individual', 'Foreign Individual'),
        ('money_lender', 'Money Lender'),
        ('unregistered_nbfc', 'Unregistered NBFC'),
        ('other', 'Other (Non-Eligible)'),
    ], string="80E Lending Institution Type", default='scheduled_bank', store=True,
       help="Statutory classification of lending entity under Section 80E.")

    decl_80e_is_higher_education = fields.Boolean(
        string="Taken for Higher Education",
        default=True,
        store=True,
        help="Mark True if loan was obtained for pursuing higher education (full-time or part-time post Higher Secondary)."
    )
    decl_80e_loan_taken_for = fields.Selection([
        ('self', 'Self'),
        ('spouse', 'Spouse'),
        ('child', 'Child'),
        ('legal_guardian', 'Student for whom employee is legal guardian'),
    ], string="Loan Taken For", default='self', store=True,
       help="Relationship of student for whom loan was taken.")

    decl_80e_interest_start_date = fields.Date(
        string="First Interest Repayment / Start Date",
        store=True,
        help="Date when employee first started repaying loan interest. Determines the initial assessment year under Section 80E(3)(b)."
    )
    decl_80e_first_claim_fy_id = fields.Many2one(
        'tds.financial.year',
        string="First Assessment Year of Claim",
        store=True,
        help="Financial Year in which employee first started claiming interest deduction under Section 80E."
    )
    decl_80e_current_claim_year = fields.Integer(
        string="Current Assessment Year Claim Count",
        compute='_compute_80e_deduction_period',
        store=True,
        readonly=True,
        help="Consecutive assessment year count of claim (1 to 8)."
    )
    decl_80e_is_within_8_years = fields.Boolean(
        string="Within Eight Year Deduction Window",
        compute='_compute_80e_deduction_period',
        store=True,
        readonly=True,
        help="True if current claim year count is within the statutory 8 assessment year ceiling."
    )

    @api.depends('decl_80e_interest_start_date', 'decl_80e_first_claim_fy_id', 'financial_year_id', 'decl_80e_interest')
    def _compute_80e_deduction_period(self):
        for rec in self:
            first_fy = False
            first_start = False
            if rec.decl_80e_interest_start_date:
                start_d = rec.decl_80e_interest_start_date
                first_fy = self.env['tds.financial.year'].search([
                    ('start_date', '<=', start_d),
                    ('end_date', '>=', start_d)
                ], limit=1)
                if first_fy:
                    first_start = getattr(first_fy, 'start_date', False) or getattr(first_fy, 'date_from', False)
                else:
                    start_yr = start_d.year if start_d.month >= 4 else start_d.year - 1
                    first_start = fields.Date.from_string(f"{start_yr}-04-01")
            elif rec.decl_80e_first_claim_fy_id:
                first_fy = rec.decl_80e_first_claim_fy_id
                first_start = getattr(first_fy, 'start_date', False) or getattr(first_fy, 'date_from', False)

            if not first_start:
                rec.decl_80e_current_claim_year = 1
                rec.decl_80e_is_within_8_years = True
                continue

            curr_fy = rec.financial_year_id
            curr_start = (getattr(curr_fy, 'start_date', False) or getattr(curr_fy, 'date_from', False)) if curr_fy else False

            if first_start and curr_start:
                try:
                    first_year = first_start.year if hasattr(first_start, 'year') else int(str(first_start)[:4])
                    curr_year = curr_start.year if hasattr(curr_start, 'year') else int(str(curr_start)[:4])
                    count = max(1, (curr_year - first_year) + 1)
                except Exception:
                    count = 1
            else:
                count = 1

            rec.decl_80e_current_claim_year = count
            rec.decl_80e_is_within_8_years = (count <= 8)

            _logger.warning("""[80E_WINDOW_AUDIT]
declaration_id=%s
interest_start_date=%s
first_claim_fy=%s
current_fy=%s
current_claim_year=%s
is_within_8_years=%s""",
                rec.id, rec.decl_80e_interest_start_date, first_fy.name if first_fy else (f"FY {first_start.year}-{str(first_start.year+1)[-2:]}" if first_start else 'N/A'),
                curr_fy.name if curr_fy else 'N/A', count, count <= 8
            )

    # Section 80DD Dependent Disability Deduction Fields
    decl_80dd_amount = fields.Float(
        string="80DD Statutory Approved Deduction (₹)",
        compute='_compute_totals',
        store=True,
        readonly=True,
        help="Statutory approved deduction u/s 80DD (₹75,000 for normal disability, ₹1,25,000 for severe disability)."
    )
    decl_80dd_dependent_name = fields.Char(
        string="Dependent Name",
        store=True,
        help="Full legal name of the dependent person with disability."
    )
    decl_80dd_relationship = fields.Selection([
        ('spouse', 'Spouse'),
        ('child', 'Child'),
        ('parent', 'Parent'),
        ('brother', 'Brother'),
        ('sister', 'Sister'),
        ('other', 'Other (Ineligible)'),
    ], string="Relationship with Employee", default='child', store=True,
       help="Statutory relationship of dependent with employee under Section 80DD.")
    decl_80dd_dependent_pan = fields.Char(
        string="Dependent PAN / Aadhaar",
        store=True,
        help="Permanent Account Number or Aadhaar Number of dependent (Optional)."
    )
    decl_80dd_dependent_dob = fields.Date(
        string="Dependent Date of Birth",
        store=True,
        help="Date of birth of the dependent."
    )
    decl_80dd_disability_exists = fields.Boolean(
        string="Disability Exists",
        default=False,
        store=True,
        help="Mark True if dependent has a certified disability under Section 80DD."
    )
    decl_80dd_has_certificate = fields.Boolean(
        string="Disability Certificate Available",
        default=False,
        store=True,
        help="Tick this if you possess a disability certificate issued by a prescribed medical authority."
    )
    decl_80dd_disability_percentage = fields.Float(
        string="Disability Percentage (%)",
        default=0.0,
        store=True,
        help="Certified percentage of disability (Must be >= 40% for eligibility)."
    )
    decl_80dd_disability_category = fields.Selection([
        ('blindness', 'Blindness'),
        ('low_vision', 'Low Vision'),
        ('leprosy_cured', 'Leprosy Cured'),
        ('hearing_impairment', 'Hearing Impairment'),
        ('locomotor_disability', 'Locomotor Disability'),
        ('mental_illness', 'Mental Illness'),
        ('autism', 'Autism Spectrum Disorder'),
        ('cerebral_palsy', 'Cerebral Palsy'),
        ('multiple_disabilities', 'Multiple Disabilities'),
        ('intellectual_disability', 'Intellectual Disability'),
        ('parkinsons', "Parkinson's Disease"),
        ('learning_disability', 'Specific Learning Disability'),
        ('acid_attack', 'Acid Attack Victim'),
        ('dwarfism', 'Dwarfism'),
        ('muscular_dystrophy', 'Muscular Dystrophy'),
        ('chronic_neurological_conditions', 'Chronic Neurological Conditions'),
        ('multiple_sclerosis', 'Multiple Sclerosis'),
        ('speech_and_language_disability', 'Speech and Language Disability'),
        ('thalassemia', 'Thalassemia'),
        ('hemophilia', 'Hemophilia'),
        ('sickle_cell_disease', 'Sickle Cell Disease'),
        ('other', 'Any Other Notified Disability'),
    ], string="Disability Category", default='autism', store=True,
       help="Medical classification of disability.")
    decl_80dd_is_severe_disability = fields.Boolean(
        string="Severe Disability (>= 80%)",
        compute='_compute_80dd_disability_status',
        store=True,
        readonly=True,
        help="Auto-computed True if certified disability percentage is 80% or higher."
    )
    decl_80dd_cert_type = fields.Selection([
        ('permanent', 'Permanent'),
        ('temporary', 'Temporary'),
    ], string="Disability Certificate Type", default='permanent', store=True,
       help="Permanent certificates do not require an expiry date. Temporary certificates require validity through financial year end.")
    decl_80dd_cert_number = fields.Char(
        string="Certificate Number",
        store=True,
        help="Official registration/reference number of medical certificate."
    )
    decl_80dd_cert_issue_date = fields.Date(
        string="Certificate Issue Date",
        store=True,
        help="Date of issuance of disability certificate."
    )
    decl_80dd_cert_expiry_date = fields.Date(
        string="Certificate Expiry Date",
        store=True,
        help="Expiry date of disability certificate (Mandatory only if Temporary)."
    )
    decl_80dd_issuing_authority = fields.Char(
        string="Issuing Medical Authority",
        store=True,
        help="Name and designation of issuing medical authority / hospital board."
    )
    decl_80dd_is_cert_valid = fields.Boolean(
        string="Certificate Valid",
        compute='_compute_80dd_disability_status',
        store=True,
        readonly=True,
        help="Auto-computed True if certificate is Permanent or Temporary with expiry >= evaluation date."
    )
    decl_80dd_has_maintenance_expenditure = fields.Boolean(
        string="Incurred Maintenance Expenditure",
        default=True,
        store=True,
        help="Employee incurred expenditure for medical treatment / training / rehabilitation of dependent."
    )
    decl_80dd_has_insurance_contribution = fields.Boolean(
        string="Contributed to LIC / Approved Scheme",
        default=False,
        store=True,
        help="Employee paid premium / deposited amount into LIC or approved scheme for maintenance of dependent."
    )
    decl_80dd_expenditure_amount = fields.Float(
        string="Total Amount Paid (Records Only)",
        default=0.0,
        store=True,
        help="Documentation amount paid for maintenance or insurance scheme (Does NOT alter fixed statutory deduction)."
    )

    @api.depends(
        'decl_80dd_has_certificate',
        'decl_80dd_cert_number',
        'decl_80dd_cert_issue_date',
        'decl_80dd_issuing_authority',
        'decl_80dd_disability_percentage',
        'decl_80dd_cert_type',
        'decl_80dd_cert_expiry_date',
        'financial_year_id'
    )
    def _compute_80dd_disability_status(self):
        for rec in self:
            rec.decl_80dd_is_severe_disability = (rec.decl_80dd_disability_percentage >= 80.0)

            if not rec.decl_80dd_has_certificate:
                rec.decl_80dd_is_cert_valid = False
                continue

            if not rec.decl_80dd_cert_number or not rec.decl_80dd_cert_issue_date or not rec.decl_80dd_issuing_authority:
                rec.decl_80dd_is_cert_valid = False
                continue

            if rec.decl_80dd_cert_type == 'permanent':
                rec.decl_80dd_is_cert_valid = True
            elif rec.decl_80dd_cert_type == 'temporary':
                if not rec.decl_80dd_cert_expiry_date:
                    rec.decl_80dd_is_cert_valid = False
                else:
                    eval_dt = fields.Date.today()
                    if rec.financial_year_id:
                        eval_dt = getattr(rec.financial_year_id, 'end_date', False) or getattr(rec.financial_year_id, 'date_to', False) or fields.Date.today()
                    rec.decl_80dd_is_cert_valid = (rec.decl_80dd_cert_expiry_date >= eval_dt)
            else:
                rec.decl_80dd_is_cert_valid = True

    # -------------------------------------------------------------------------
    # SECTION 80U – DEDUCTION FOR PERSON WITH DISABILITY (EMPLOYEE OWN DISABILITY)
    # -------------------------------------------------------------------------
    decl_80u_amount = fields.Float(
        string="Section 80U Approved Deduction (₹)",
        compute='_compute_totals',
        store=True,
        readonly=True,
        help="Statutory approved deduction u/s 80U for employee's own disability (₹75,000 for 40-79%, ₹1,25,000 for 80%+)."
    )
    decl_80u_disability_percentage = fields.Float(
        string="Employee Disability Percentage (%)",
        default=0.0,
        store=True,
        help="Certified percentage of employee's own disability (Must be >= 40% for eligibility)."
    )
    decl_80u_disability_category = fields.Selection([
        ('blindness', 'Blindness'),
        ('low_vision', 'Low Vision'),
        ('leprosy_cured', 'Leprosy Cured'),
        ('hearing_impairment', 'Hearing Impairment'),
        ('locomotor_disability', 'Locomotor Disability'),
        ('mental_illness', 'Mental Illness'),
        ('autism', 'Autism Spectrum Disorder'),
        ('cerebral_palsy', 'Cerebral Palsy'),
        ('multiple_disabilities', 'Multiple Disabilities'),
        ('intellectual_disability', 'Intellectual Disability'),
        ('parkinsons', "Parkinson's Disease"),
        ('learning_disability', 'Specific Learning Disability'),
        ('acid_attack', 'Acid Attack Victim'),
        ('dwarfism', 'Dwarfism'),
        ('muscular_dystrophy', 'Muscular Dystrophy'),
        ('chronic_neurological_conditions', 'Chronic Neurological Conditions'),
        ('multiple_sclerosis', 'Multiple Sclerosis'),
        ('speech_and_language_disability', 'Speech and Language Disability'),
        ('thalassemia', 'Thalassemia'),
        ('hemophilia', 'Hemophilia'),
        ('sickle_cell_disease', 'Sickle Cell Disease'),
    ], string="Employee Disability Category", default='autism', store=True,
       help="Medical classification of employee's disability under Section 80U.")
    decl_80u_has_certificate = fields.Boolean(
        string="Medical Certificate Available",
        default=False,
        store=True,
        help="Tick this if you possess a disability certificate issued by a prescribed medical authority."
    )
    decl_80u_is_severe_disability = fields.Boolean(
        string="Severe Disability (>= 80%)",
        compute='_compute_80u_disability_status',
        store=True,
        readonly=True,
        help="Auto-computed True if certified disability percentage is 80% or higher."
    )
    decl_80u_cert_type = fields.Selection([
        ('permanent', 'Permanent'),
        ('temporary', 'Temporary'),
    ], string="Disability Certificate Type", default='permanent', store=True,
       help="Permanent certificates do not require an expiry date. Temporary certificates require validity through financial year end.")
    decl_80u_cert_number = fields.Char(
        string="Certificate Number",
        store=True,
        help="Official registration/reference number of medical certificate."
    )
    decl_80u_cert_issue_date = fields.Date(
        string="Certificate Issue Date",
        store=True,
        help="Date of issuance of disability certificate."
    )
    decl_80u_cert_expiry_date = fields.Date(
        string="Certificate Expiry Date",
        store=True,
        help="Expiry date of disability certificate (Mandatory only if Temporary)."
    )
    decl_80u_issuing_authority = fields.Char(
        string="Issuing Medical Authority",
        store=True,
        help="Name and designation of issuing medical authority / hospital board."
    )
    decl_80u_reassessment_pending = fields.Boolean(
        string="Reassessment / Renewal Pending",
        default=False,
        store=True,
        help="Tick if temporary certificate expired during FY and reassessment/renewal application is pending with medical authority."
    )
    decl_80u_renewal_cert_number = fields.Char(
        string="Renewed Certificate Number",
        store=True,
        help="Certificate number of renewed disability certificate issued during FY."
    )
    decl_80u_renewal_issue_date = fields.Date(
        string="Renewal / Reassessment Date",
        store=True,
        help="Date on which temporary disability certificate renewal or reassessment was conducted."
    )
    decl_80u_renewal_expiry_date = fields.Date(
        string="New / Renewed Certificate Expiry Date",
        store=True,
        help="Expiry date of the renewed disability certificate."
    )
    decl_80u_renewal_disability_percentage = fields.Float(
        string="Renewed Disability Percentage (%)",
        default=0.0,
        store=True,
        help="Certified disability percentage under renewed certificate."
    )
    decl_80u_is_cert_valid = fields.Boolean(
        string="Certificate Valid",
        compute='_compute_80u_disability_status',
        store=True,
        readonly=True,
        help="Auto-computed True if certificate is Permanent or Temporary with valid coverage/reassessment in FY."
    )

    @api.constrains('decl_80u_renewal_issue_date', 'decl_80u_renewal_expiry_date', 'decl_80u_cert_type')
    def _check_80u_renewal_dates(self):
        for rec in self:
            if rec.decl_80u_cert_type == 'temporary' and rec.decl_80u_renewal_issue_date and rec.decl_80u_renewal_expiry_date:
                if rec.decl_80u_renewal_expiry_date <= rec.decl_80u_renewal_issue_date:
                    raise ValidationError("Section 80U Validation Error: New / Renewed Certificate Expiry Date must be later than the Renewal / Reassessment Date.")

    @api.depends(
        'decl_80u_has_certificate',
        'decl_80u_cert_number',
        'decl_80u_cert_issue_date',
        'decl_80u_issuing_authority',
        'decl_80u_disability_percentage',
        'decl_80u_cert_type',
        'decl_80u_cert_expiry_date',
        'decl_80u_reassessment_pending',
        'decl_80u_renewal_cert_number',
        'decl_80u_renewal_issue_date',
        'decl_80u_renewal_expiry_date',
        'decl_80u_renewal_disability_percentage',
        'financial_year_id'
    )
    def _compute_80u_disability_status(self):
        for rec in self:
            try:
                from ..services.tds.tds_parameter_service import TdsParameterService
                tds_param_svc = TdsParameterService(rec.env)
                severe_threshold = tds_param_svc.get_80u_severe_disability_percent()
            except (ImportError, AttributeError, ValueError, KeyError) as err:
                _logger.warning("Defaulting Section 80U severe disability threshold to 80.0 due to parameter resolution fallback: %s", str(err))
                severe_threshold = 80.0
            except Exception as err:
                _logger.error("Unexpected error resolving Section 80U severe disability parameter threshold: %s", str(err), exc_info=True)
                severe_threshold = 80.0

            eff_pct = rec.decl_80u_renewal_disability_percentage if (rec.decl_80u_renewal_disability_percentage > 0.0 and (rec.decl_80u_renewal_cert_number or rec.decl_80u_renewal_issue_date)) else rec.decl_80u_disability_percentage
            rec.decl_80u_is_severe_disability = (eff_pct >= severe_threshold)

            if not rec.decl_80u_has_certificate:
                rec.decl_80u_is_cert_valid = False
                continue

            if not rec.decl_80u_cert_number or not rec.decl_80u_cert_issue_date or not rec.decl_80u_issuing_authority:
                rec.decl_80u_is_cert_valid = False
                continue

            if rec.decl_80u_cert_type == 'permanent':
                rec.decl_80u_is_cert_valid = True
            elif rec.decl_80u_cert_type == 'temporary':
                fy_start = getattr(rec.financial_year_id, 'start_date', False) or getattr(rec.financial_year_id, 'date_from', False)
                fy_end = getattr(rec.financial_year_id, 'end_date', False) or getattr(rec.financial_year_id, 'date_to', False)
                eval_dt = fields.Date.today()
                if not fy_start or not fy_end:
                    fy_start = fields.Date.from_string(f"{eval_dt.year if eval_dt.month >= 4 else eval_dt.year - 1}-04-01")
                    fy_end = fields.Date.from_string(f"{eval_dt.year + 1 if eval_dt.month >= 4 else eval_dt.year}-03-31")

                if rec.decl_80u_cert_expiry_date and rec.decl_80u_cert_expiry_date >= fy_end:
                    rec.decl_80u_is_cert_valid = True
                elif rec.decl_80u_cert_expiry_date and fy_start <= rec.decl_80u_cert_expiry_date < fy_end:
                    if rec.decl_80u_renewal_cert_number or rec.decl_80u_renewal_issue_date or rec.decl_80u_reassessment_pending:
                        rec.decl_80u_is_cert_valid = True
                    else:
                        rec.decl_80u_is_cert_valid = False
                elif (rec.decl_80u_renewal_cert_number or rec.decl_80u_renewal_issue_date) and rec.decl_80u_renewal_expiry_date and rec.decl_80u_renewal_expiry_date >= fy_start:
                    rec.decl_80u_is_cert_valid = True
                else:
                    rec.decl_80u_is_cert_valid = False
            else:
                rec.decl_80u_is_cert_valid = True
    decl_80g_donation = fields.Monetary(
        string="Charitable Donations (80G) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80G - Donations to Charitable Trusts & Relief Funds"
    )
    decl_80g_institution_name = fields.Char(
        string="80G Donee Institution Name",
        store=True,
        help="Full legal name of the donee trust or relief fund (e.g. PM CARES Fund, National Defence Fund)."
    )
    decl_80g_category = fields.Selection([
        ('100_no_limit', '100% Deduction (Without Qualifying Limit)'),
        ('50_no_limit', '50% Deduction (Without Qualifying Limit)'),
        ('100_with_limit', '100% Deduction (Subject to Qualifying Limit)'),
        ('50_with_limit', '50% Deduction (Subject to Qualifying Limit)'),
    ], string="80G Deduction Category", default='50_with_limit', store=True,
       help="Statutory category under Section 80G governing deduction percentage and qualifying limits.")

    decl_80g_is_approved = fields.Boolean(
        string="Approved under Section 80G",
        default=True,
        store=True,
        help="Mark True if institution possesses valid Section 80G approval from Income Tax Department."
    )
    decl_80g_mode = fields.Selection([
        ('cash', 'Cash'),
        ('cheque', 'Cheque'),
        ('dd', 'Demand Draft'),
        ('neft_rtgs', 'NEFT / RTGS / Banking Channel'),
        ('upi', 'UPI / BHIM'),
        ('other_digital', 'Other Digital Payment'),
    ], string="Donation Payment Mode", default='neft_rtgs', store=True,
       help="Payment mode used for donation. Note: Cash donations exceeding ₹2,000 are statutorily disallowed.")

    decl_80g_donation_date = fields.Date(
        string="Donation Date",
        store=True,
        help="Official date of payment as per donation receipt."
    )
    decl_80g_receipt_number = fields.Char(
        string="Donation Receipt Number",
        store=True,
        help="Donation receipt / acknowledgement number issued by donee institution."
    )
    decl_80g_donee_pan = fields.Char(
        string="Donee Institution PAN",
        store=True,
        help="10-character Permanent Account Number (PAN) of donee institution."
    )
    decl_80g_approval_number = fields.Char(
        string="80G Approval / Registration Number",
        store=True,
        help="Unique registration / approval number issued under Section 80G(5)(vi)."
    )
    decl_80g_remarks = fields.Text(
        string="80G Donation Remarks",
        store=True,
        help="Additional remarks or notes regarding donation."
    )
    # Section 80GG Rent Paid Without HRA Fields
    decl_80gg_rent = fields.Monetary(
        string="Rent Paid without HRA (80GG) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80GG - Rent Paid by Employees NOT Receiving HRA"
    )
    decl_80gg_owns_house_work_place = fields.Boolean(
        string="Own house at place of work/residence?",
        default=False,
        store=True,
        help="Whether employee, spouse, minor child, or HUF owns residential house at the place of duty/residence."
    )
    decl_80gg_owns_house_elsewhere = fields.Boolean(
        string="Own house elsewhere and treated as self-occupied?",
        default=False,
        store=True,
        help="Whether employee owns residential house at another place and claims self-occupied concession."
    )
    decl_80gg_hra_received = fields.Boolean(
        string="HRA received during the relevant period?",
        default=False,
        store=True,
        help="Whether any house rent allowance was received during the relevant financial year."
    )
    decl_80gg_form_10ba_filed = fields.Boolean(
        string="Form 10BA filed?",
        default=False,
        store=True,
        help="Whether statutory Form 10BA declaration has been filed."
    )
    decl_80gg_eligible = fields.Boolean(
        string="80GG Eligible",
        compute='_compute_80gg_status',
        store=True,
        help="Whether Section 80GG eligibility conditions are met."
    )
    decl_80gg_ineligibility_reason = fields.Text(
        string="80GG Ineligibility Reason",
        compute='_compute_80gg_status',
        store=True
    )
    decl_80gg_allowed_amount = fields.Monetary(
        string="80GG Allowed Deduction (₹)",
        compute='_compute_80gg_status',
        store=True,
        currency_field='currency_id'
    )
    decl_80gg_ati = fields.Monetary(
        string="Adjusted Total Income (ATI) (₹)",
        compute='_compute_80gg_status',
        store=True,
        currency_field='currency_id'
    )
    decl_80gg_component_a = fields.Monetary(
        string="Component A (₹5k/month) (₹)",
        compute='_compute_80gg_status',
        store=True,
        currency_field='currency_id'
    )
    decl_80gg_component_b = fields.Monetary(
        string="Component B (25% ATI) (₹)",
        compute='_compute_80gg_status',
        store=True,
        currency_field='currency_id'
    )
    decl_80gg_component_c = fields.Monetary(
        string="Component C (Rent - 10% ATI) (₹)",
        compute='_compute_80gg_status',
        store=True,
        currency_field='currency_id'
    )
    decl_80gg_summary_html = fields.Html(
        string="Section 80GG Summary",
        compute='_compute_80gg_status',
        store=False
    )

    @api.depends(
        'decl_80gg_rent', 'decl_80gg_owns_house_work_place', 'decl_80gg_owns_house_elsewhere',
        'decl_80gg_hra_received', 'decl_80gg_form_10ba_filed', 'regime_code', 'employee_id',
        'financial_year_id', 'declaration_line_ids.declared_amount', 'declaration_line_ids.approved_amount'
    )
    def _compute_80gg_status(self):
        from ..services.tds.section_80gg_deduction_service import Section80GGDeductionService
        gg_svc = Section80GGDeductionService(self.env)
        for rec in self:
            res = gg_svc.validate_and_trace(rec, regime_code=rec.regime_code, employee=rec.employee_id, financial_year=rec.financial_year_id)
            rec.decl_80gg_eligible = res.is_eligible
            rec.decl_80gg_ineligibility_reason = res.rejection_reason if not res.is_eligible else False
            rec.decl_80gg_allowed_amount = res.allowed_deduction
            rec.decl_80gg_ati = res.ati
            rec.decl_80gg_component_a = res.component_a
            rec.decl_80gg_component_b = res.component_b
            rec.decl_80gg_component_c = res.component_c

            if not res.is_eligible:
                rec.decl_80gg_summary_html = f"""
                <div style="padding: 10px; border-radius: 6px; background-color: #fdf2f2; border: 1px solid #f8b4b4; margin-top: 8px;">
                    <div style="font-weight: bold; color: #9b1c1c; margin-bottom: 4px;">Section 80GG Status: ❌ NOT ELIGIBLE</div>
                    <div style="color: #771d1d; font-size: 13px;"><strong>Reason:</strong> {res.rejection_reason}</div>
                    <div style="color: #771d1d; font-size: 12px; margin-top: 4px;"><strong>Allowed Deduction:</strong> ₹0.00</div>
                </div>
                """
            else:
                rec.decl_80gg_summary_html = f"""
                <div style="padding: 10px; border-radius: 6px; background-color: #f3faf7; border: 1px solid #84e1bc; margin-top: 8px;">
                    <div style="font-weight: bold; color: #03543f; margin-bottom: 4px;">Section 80GG Status: ✅ ELIGIBLE</div>
                    <div style="font-size: 13px; color: #046c4e;">
                        <div>• <strong>Annual Rent Paid:</strong> ₹{res.declared_amount:,.2f}</div>
                        <div>• <strong>Adjusted Total Income (ATI):</strong> ₹{res.ati:,.2f}</div>
                        <div>• <strong>₹5,000 / month:</strong> ₹{res.component_a:,.2f}</div>
                        <div>• <strong>25% ATI:</strong> ₹{res.component_b:,.2f}</div>
                        <div>• <strong>Rent − 10% ATI:</strong> ₹{res.component_c:,.2f}</div>
                        <div style="margin-top: 4px; font-weight: bold; color: #03543f;">• <strong>Allowed Deduction:</strong> ₹{res.allowed_deduction:,.2f}</div>
                    </div>
                </div>
                """
    # Other Tax-Eligible Adjustments (80CCD(2), 57(iia), 80CCH)
    decl_80ccd2_employer_nps = fields.Monetary(
        string="Employer NPS Contribution — Section 124 (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Employer NPS Contribution under Section 124 (formerly Section 80CCD(2))"
    )
    decl_57iia_family_pension = fields.Monetary(
        string="Family Pension Received (annual) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Annual gross family pension received by legal heirs (Income from Other Sources). Standard deduction under Family Pension Section 93(1)(d) (1/3 of family pension or ₹25,000, whichever is lower) is netted directly to determine taxable income."
    )
    decl_80cch_agniveer = fields.Monetary(
        string="Agniveer Corpus Fund Contribution (80CCH) (₹)",
        currency_field='currency_id',
        default=0.0,
        store=True,
        help="Section 80CCH - Agniveer Corpus Fund Contribution"
    )

    @api.depends('employee_id.name', 'financial_year_id.name', 'regime_code')
    def _compute_name(self):
        for rec in self:
            emp = rec.employee_id.name if rec.employee_id else 'Employee'
            fy = rec.financial_year_id.name if rec.financial_year_id else 'FY'
            reg = (rec.regime_code or 'regime').upper()
            rec.name = f"Tax Declaration - {emp} [{fy}] ({reg})"

    @api.depends('employee_id', 'financial_year_id', 'employee_id.hds_in_current_tax_regime_id')
    def _compute_tax_regime_id(self):
        """
        Dynamically resolves active tax regime from tds.employee.tax.regime history for employee + FY.
        Defaults to employee's selected regime on profile or statutory default regime (New).
        """
        for rec in self:
            company = rec.company_id or (rec.employee_id and rec.employee_id.company_id) or self.env.company
            policy = getattr(company, 'hds_in_default_tax_regime', 'flexible')

            if policy == 'new':
                reg_new = self.env['tds.tax.regime'].sudo().search([('code', '=', 'new')], limit=1)
                rec.tax_regime_id = reg_new
                continue
            elif policy == 'old':
                reg_old = self.env['tds.tax.regime'].sudo().search([('code', '=', 'old')], limit=1)
                rec.tax_regime_id = reg_old
                continue

            if rec.employee_id and rec.financial_year_id:
                reg_record = self.env['tds.employee.tax.regime'].sudo().search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('financial_year_id', '=', rec.financial_year_id.id),
                ], limit=1)
                if reg_record and reg_record.regime_id:
                    rec.tax_regime_id = reg_record.regime_id
                    continue
                # If no reg_record exists, check employee's selected current regime
                if rec.employee_id.hds_in_current_tax_regime_id:
                    rec.tax_regime_id = rec.employee_id.hds_in_current_tax_regime_id
                    continue

            # Fallback to default regime master (New Tax Regime Income-tax Act, 2025 — Section 202(1))
            default_reg = self.env['tds.tax.regime'].sudo().search([('code', '=', 'new')], limit=1) or self.env['tds.tax.regime'].sudo().search([('is_default', '=', True)], limit=1)
            rec.tax_regime_id = default_reg.id if default_reg else False

    @api.depends('tax_regime_id', 'employee_id.hds_in_current_tax_regime_id')
    def _compute_regime_choice_id(self):
        for rec in self:
            rec.regime_choice_id = rec.tax_regime_id or (rec.employee_id and rec.employee_id.hds_in_current_tax_regime_id)

    def _inverse_regime_choice_id(self):
        for rec in self:
            company = rec.company_id or (rec.employee_id and rec.employee_id.company_id) or self.env.company
            policy = getattr(company, 'hds_in_default_tax_regime', 'flexible')
            if policy in ('new', 'old'):
                raise ValidationError(_(
                    "Company policy mandates the %s Tax Regime for all employees. Individual selection is disabled."
                ) % ('New' if policy == 'new' else 'Old'))

            if rec.employee_id and rec.financial_year_id and rec.regime_choice_id:
                rec.tax_regime_id = rec.regime_choice_id
                reg_record = self.env['tds.employee.tax.regime'].sudo().search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('financial_year_id', '=', rec.financial_year_id.id),
                ], limit=1)
                if reg_record:
                    if reg_record.is_locked:
                        raise ValidationError(_("Tax regime choice is locked by HR for Financial Year '%s'. Contact HR to request an unlock.") % rec.financial_year_id.name)
                    reg_record.sudo().write({'regime_id': rec.regime_choice_id.id})
                else:
                    self.env['tds.employee.tax.regime'].sudo().create({
                        'employee_id': rec.employee_id.id,
                        'financial_year_id': rec.financial_year_id.id,
                        'regime_id': rec.regime_choice_id.id,
                    })
                # Invalidate employee profile computed regime fields so they reflect immediately
                rec.employee_id.invalidate_recordset(['hds_in_current_tax_regime_id', 'hds_in_is_new_tax_regime', 'hds_in_tax_regime'])

    def _get_income_declaration(self):
        self.ensure_one()
        if not self.employee_id or not self.financial_year_id:
            return False
        return self.env['tds.employee.income.declaration'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('financial_year_id', '=', self.financial_year_id.id),
        ], limit=1)

    @api.depends('employee_id', 'financial_year_id')
    def _compute_income_decl_fields(self):
        for rec in self:
            if not rec.employee_id or not rec.financial_year_id:
                rec.savings_bank_interest = 0.0
                rec.fixed_deposit_interest = 0.0
                rec.dividend_income = 0.0
                rec.other_sources_income = 0.0
                rec.annual_let_out_rent = 0.0
                rec.municipal_taxes_paid = 0.0
                rec.let_out_interest_paid = 0.0
                rec.prev_employer_taxable_gross = 0.0
                rec.prev_employer_tds = 0.0
                rec.prev_employer_pt = 0.0
                rec.prev_employer_pf = 0.0
                continue

            decl = rec._get_income_declaration()
            if decl:
                rec.savings_bank_interest = decl.savings_bank_interest
                rec.fixed_deposit_interest = decl.fixed_deposit_interest
                rec.dividend_income = decl.dividend_income
                rec.other_sources_income = decl.other_sources_income
                rec.annual_let_out_rent = decl.annual_let_out_rent
                rec.municipal_taxes_paid = decl.municipal_taxes_paid
                rec.let_out_interest_paid = decl.let_out_interest_paid
                rec.prev_employer_taxable_gross = decl.prev_employer_taxable_gross
                rec.prev_employer_tds = decl.prev_employer_tds
                rec.prev_employer_pt = decl.prev_employer_pt
                rec.prev_employer_pf = decl.prev_employer_pf
            else:
                sb = float(rec.savings_bank_interest or 0.0)
                fd = float(rec.fixed_deposit_interest or 0.0)
                div = float(rec.dividend_income or 0.0)
                oth = float(rec.other_sources_income or 0.0)
                rec.savings_bank_interest = sb
                rec.fixed_deposit_interest = fd
                rec.dividend_income = div
                rec.other_sources_income = oth

                rent = float(rec.annual_let_out_rent or 0.0)
                muni = float(rec.municipal_taxes_paid or 0.0)
                intr = float(rec.let_out_interest_paid or 0.0)
                rec.annual_let_out_rent = rent
                rec.municipal_taxes_paid = muni
                rec.let_out_interest_paid = intr

                rec.prev_employer_taxable_gross = float(rec.prev_employer_taxable_gross or 0.0)
                rec.prev_employer_tds = float(rec.prev_employer_tds or 0.0)
                rec.prev_employer_pt = float(rec.prev_employer_pt or 0.0)
                rec.prev_employer_pf = float(rec.prev_employer_pf or 0.0)

    @api.depends(
        'savings_bank_interest', 'fixed_deposit_interest', 'dividend_income',
        'other_sources_income', 'decl_57iia_family_pension'
    )
    def _compute_total_other_sources_income(self):
        for rec in self:
            rec.total_other_sources_income = (
                float(rec.savings_bank_interest or 0.0) +
                float(rec.fixed_deposit_interest or 0.0) +
                float(rec.dividend_income or 0.0) +
                float(rec.other_sources_income or 0.0) +
                float(rec.decl_57iia_family_pension or 0.0)
            )

    @api.depends(
        'annual_let_out_rent', 'municipal_taxes_paid', 'let_out_interest_paid',
        'regime_code', 'employee_id', 'financial_year_id'
    )
    def _compute_house_property_totals(self):
        for rec in self:
            rent = float(rec.annual_let_out_rent or 0.0)
            muni = float(rec.municipal_taxes_paid or 0.0)
            intr = float(rec.let_out_interest_paid or 0.0)
            nav = max(0.0, rent - muni)
            std_ded = nav * 0.30
            net_hp = nav - std_ded - intr
            rec.net_house_property_income_loss = net_hp

            other_inc_svc = OtherIncomeAggregationService(self.env)
            eval_date = fields.Date.today()
            regime = rec.regime_code or 'new'

            eff_hp = other_inc_svc.calculate_effective_hp_impact(net_hp, regime_code=regime, eval_date=eval_date)
            if eff_hp > 0.0 and rec.employee_id and rec.financial_year_id:
                emp_id = rec.employee_id.id if hasattr(rec.employee_id, 'id') else rec.employee_id
                fy_id = rec.financial_year_id.id if hasattr(rec.financial_year_id, 'id') else rec.financial_year_id
                eff_hp = other_inc_svc.apply_previous_carry_forward_losses(
                    employee_id=emp_id,
                    financial_year_id=fy_id,
                    positive_hp_income=eff_hp,
                    regime_code=regime,
                    eval_date=eval_date
                )
            rec.effective_house_property_gti_impact = eff_hp

    def _inverse_income_decl_fields(self):
        income_fields = [
            'savings_bank_interest', 'fixed_deposit_interest', 'dividend_income',
            'other_sources_income', 'annual_let_out_rent', 'municipal_taxes_paid',
            'let_out_interest_paid', 'prev_employer_taxable_gross', 'prev_employer_tds',
            'prev_employer_pt', 'prev_employer_pf'
        ]
        for rec in self:
            if not rec.employee_id or not rec.financial_year_id:
                continue
            decl = rec._get_income_declaration()
            if not decl:
                decl = self.env['tds.employee.income.declaration'].sudo().create({
                    'employee_id': rec.employee_id.id,
                    'financial_year_id': rec.financial_year_id.id,
                })

            vals = {}
            for f in income_fields:
                raw_val = rec[f]
                decl_val = float(getattr(decl, f, 0.0) or 0.0)
                if raw_val is False or raw_val is None:
                    float_val = 0.0
                else:
                    float_val = float(raw_val or 0.0)

                if abs(float_val - decl_val) > 0.001:
                    vals[f] = float_val

            if vals:
                decl.sudo().with_context(no_tds_audit=True).write(vals)

    def _match_80c_child_line(self, line, python_field_name):
        """
        Strict 1-to-1 binder between an 80C child declaration line and a specific 80C scalar field.
        Guarantees that each 80C investment item stores and displays its own independent value.
        """
        if line.category != '80c' or not line.description:
            return False
        desc = line.description.lower().strip()
        
        GENERIC_LABELS = [
            'section 80c', 'section 80c (ppf, elss, lic, tuition fee, epf)', 
            '80c investments', 'section 80c investment'
        ]
        if desc in GENERIC_LABELS:
            return False

        target_field = None
        if 'ppf' in desc or 'public provident' in desc:
            target_field = 'decl_80c_ppf'
        elif 'elss' in desc or 'mutual fund' in desc:
            target_field = 'decl_80c_elss'
        elif 'vpf' in desc or 'voluntary epf' in desc or 'voluntary pf' in desc or ('epf' in desc and 'ppf' not in desc):
            target_field = 'decl_80c_epf'
        elif 'lic' in desc or 'life insurance' in desc or 'life premium' in desc:
            target_field = 'decl_80c_lic'
        elif 'nsc' in desc or 'national savings' in desc:
            target_field = 'decl_80c_nsc'
        elif 'ssy' in desc or 'sukanya' in desc:
            target_field = 'decl_80c_ssy'
        elif 'fixed deposit' in desc or 'tax saving fd' in desc or ' 5 year' in desc or ' 5-year' in desc or desc == 'fd' or desc.endswith(' fd'):
            target_field = 'decl_80c_fd'
        elif 'tuition' in desc or 'school fee' in desc or 'children tuition' in desc:
            target_field = 'decl_80c_tuition'
        elif 'housing' in desc or 'principal' in desc or 'home loan principal' in desc:
            target_field = 'decl_80c_housing_principal'
        elif 'other 80c' in desc or 'other investment' in desc or 'other specified' in desc:
            target_field = 'decl_80c_other'

        if target_field:
            return target_field == python_field_name
            
        return python_field_name == 'decl_80c_other'

    def _sync_declaration_line(self, category_code, description, amount, ui_field_label, python_field_name, is_senior=False, is_severe=False, method_name='write'):
        """
        Helper to create or update a tds.employee.declaration.line.
        Logs detailed FIELD PERSISTENCE TRACE for exact audit trail.
        """
        self.ensure_one()
        SINGLE_INSTANCE_CATEGORIES = {'57iia', '80ccd2', '80cch', '80ccd1b', 'hra', '24b', '80dd', '80u', '80eea', '80g'}
        if category_code in SINGLE_INSTANCE_CATEGORIES:
            lines = self.declaration_line_ids.filtered(lambda l: l.category == category_code)
        elif category_code == '80c':
            lines = self.declaration_line_ids.filtered(
                lambda l: l.category == '80c' and getattr(l, 'active', True) and self._match_80c_child_line(l, python_field_name)
            )
        else:
            # Match by category only — description is written during sync, not used as a lookup key.
            # Previously matched by label substring which caused duplicate lines when users entered
            # custom descriptions that didn't contain the canonical label (e.g. '80d_self' line named
            # 'My Health Policy' instead of 'Medical Insurance (Self & Family)').
            lines = self.declaration_line_ids.filtered(
                lambda l: l.category == category_code
            )
        existing_val = lines[0].declared_amount if lines else 0.0
        line_id = lines[0].id if lines else 'New'

        if amount > 0.0:
            # When updating an existing line, do NOT overwrite description —
            # the user may have entered a custom name which must be preserved.
            # Description is only set on initial creation.
            update_vals = {
                'declared_amount': amount,
                'is_senior_citizen': is_senior,
                'is_severe_disability': is_severe,
            }
            create_vals = dict(update_vals, description=description)
            if category_code == '80g' and hasattr(self, 'decl_80g_category') and self.decl_80g_category:
                update_vals['decl_80g_category'] = self.decl_80g_category
                create_vals['decl_80g_category'] = self.decl_80g_category

            if lines:
                target_line = lines[0]
                target_line.sudo().write(update_vals)
                if len(lines) > 1:
                    lines[1:].sudo().unlink()
                line_id = target_line.id
                post_val = target_line.declared_amount
            else:
                create_vals.update({
                    'declaration_id': self.id,
                    'category': category_code,
                })
                new_line = self.env['tds.employee.declaration.line'].sudo().create(create_vals)
                line_id = new_line.id
                post_val = new_line.declared_amount
        else:
            if lines:
                lines.sudo().unlink()
            post_val = 0.0

        read_val = float(getattr(self, python_field_name, 0.0) or 0.0) if hasattr(self, python_field_name) else post_val

        _logger.warning(
            "\n====================================================\n"
            "FIELD PERSISTENCE TRACE\n"
            "====================================================\n"
            "Employee : %s\n"
            "FY : %s\n"
            "Declaration ID : %s\n"
            "UI Field : %s\n"
            "Python Field : %s\n"
            "Category : %s\n"
            "Description : %s\n"
            "Incoming Value : %s\n"
            "Existing DB Value : %s\n"
            "Written Value : %s\n"
            "DB After Write : %s\n"
            "DB After Read : %s\n"
            "Line ID : %s\n"
            "Method : %s\n"
            "====================================================",
            self.employee_id.name if self.employee_id else "N/A",
            self.financial_year_id.name if self.financial_year_id else "N/A",
            self.id,
            ui_field_label,
            python_field_name,
            category_code,
            description,
            amount,
            existing_val,
            amount,
            post_val,
            read_val,
            line_id,
            method_name
        )

    @api.model
    def _resolve_declaration_field_for_line(self, category, description):
        """
        Maps a declaration line's category and description to its exact scalar field_name.
        Guarantees 1-to-1 isolation so changes to one line never leak into other fields.
        """
        if not category:
            return None
        if category == '80c':
            d = (description or '').lower().strip()
            if 'ppf' in d or 'public provident' in d: return 'decl_80c_ppf'
            if 'elss' in d or 'mutual fund' in d: return 'decl_80c_elss'
            if 'vpf' in d or 'voluntary epf' in d or 'voluntary pf' in d or ('epf' in d and 'ppf' not in d): return 'decl_80c_epf'
            if 'lic' in d or 'life insurance' in d or 'life premium' in d: return 'decl_80c_lic'
            if 'nsc' in d or 'national savings' in d: return 'decl_80c_nsc'
            if 'ssy' in d or 'sukanya' in d: return 'decl_80c_ssy'
            if 'fixed deposit' in d or 'tax saving fd' in d or ' 5 year' in d or ' 5-year' in d or d == 'fd' or d.endswith(' fd'): return 'decl_80c_fd'
            if 'tuition' in d or 'school fee' in d or 'children tuition' in d: return 'decl_80c_tuition'
            if 'housing' in d or 'principal' in d or 'home loan principal' in d: return 'decl_80c_housing_principal'
            return 'decl_80c_other'

        for item in DECLARATION_BUSINESS_REGISTRY:
            if item['category'] == category:
                return item['field_name']
        return None

    def _sync_all_declaration_lines(self, method_name='write', write_vals=None, pre_deleted_lines=None):
        """
        Metadata-driven intent-aware synchronization of header decl_* fields and child declaration_line_ids.
        - Preserves positive child declaration line items entered directly in the audit grid.
        - Syncs positive child line amounts to scalar header fields.
        - Detects explicit header/line clear operations from write_vals payload and safely unlinks cleared categories.
        - Prevents accidental resurrection of stale declared amounts when a user intentionally clears a section.
        - Safely uses pre_deleted_lines cache to resolve deleted record attributes without MissingError.
        """
        if self.env.context.get('no_line_sync'):
            return

        # Parse explicit user intent from write_vals payload
        header_cleared_fields = set()
        header_updated_fields = {}
        line_cleared_fields = set()
        line_added_fields = {}

        if write_vals and isinstance(write_vals, dict):
            for item in DECLARATION_BUSINESS_REGISTRY:
                fname = item['field_name']
                alt_fname = item.get('alt_field_name')
                if fname in write_vals:
                    val_w = write_vals[fname]
                    if val_w is False or val_w is None or str(val_w).strip() in ('', '0', '0.0', '0.00') or float(val_w or 0.0) == 0.0:
                        header_cleared_fields.add(fname)
                    else:
                        header_updated_fields[fname] = float(val_w or 0.0)
                if alt_fname and alt_fname in write_vals:
                    alt_w = write_vals[alt_fname]
                    if alt_w is False or alt_w is None or str(alt_w).strip() in ('', '0', '0.0', '0.00') or float(alt_w or 0.0) == 0.0:
                        header_cleared_fields.add(fname)
                    else:
                        header_updated_fields[fname] = float(alt_w or 0.0)

            if 'declaration_line_ids' in write_vals:
                line_cmds = write_vals['declaration_line_ids'] or []
                for cmd in line_cmds:
                    if isinstance(cmd, (list, tuple)) and len(cmd) >= 2:
                        c_type = cmd[0]
                        if c_type == 5:
                            for item in DECLARATION_BUSINESS_REGISTRY:
                                line_cleared_fields.add(item['field_name'])
                        elif c_type in (2, 3):
                            cat, desc = False, False
                            if pre_deleted_lines and cmd[1] in pre_deleted_lines:
                                cat, desc = pre_deleted_lines[cmd[1]]
                            else:
                                l_rec = self.env['tds.employee.declaration.line'].browse(cmd[1]).exists()
                                if l_rec:
                                    cat, desc = l_rec.category, l_rec.description
                            if cat:
                                target_f = self._resolve_declaration_field_for_line(cat, desc)
                                if target_f:
                                    line_cleared_fields.add(target_f)
                        elif c_type in (0, 1) and len(cmd) >= 3 and isinstance(cmd[2], dict):
                            c_dict = cmd[2]
                            cmd_cat = c_dict.get('category')
                            cmd_desc = c_dict.get('description')
                            if not cmd_cat and c_type == 1 and cmd[1]:
                                if pre_deleted_lines and cmd[1] in pre_deleted_lines:
                                    cmd_cat, cmd_desc_cached = pre_deleted_lines[cmd[1]]
                                    cmd_desc = cmd_desc or cmd_desc_cached
                                else:
                                    l_rec = self.env['tds.employee.declaration.line'].browse(cmd[1]).exists()
                                    if l_rec:
                                        cmd_cat = l_rec.category
                                        cmd_desc = cmd_desc or l_rec.description
                            target_f = self._resolve_declaration_field_for_line(cmd_cat, cmd_desc)
                            if target_f:
                                if 'declared_amount' in c_dict:
                                    d_amt = float(c_dict.get('declared_amount') or 0.0)
                                    if d_amt == 0.0:
                                        line_cleared_fields.add(target_f)
                                    else:
                                        line_added_fields[target_f] = d_amt

        # Clean up legacy Employer NPS child lines (Employer NPS Section 124 is an employer statutory contribution, not an employee investment line item)
        for rec in self:
            legacy_nps_lines = rec.declaration_line_ids.filtered(lambda l: l.category == '80ccd2')
            if legacy_nps_lines:
                legacy_nps_lines.unlink()

        for rec in self:
            header_updates = {}
            for item in DECLARATION_BUSINESS_REGISTRY:
                active_lines = rec.declaration_line_ids.exists().filtered(lambda l: getattr(l, 'active', True))
                cat = item['category']
                field_name = item['field_name']
                alt_field = item.get('alt_field_name')

                # 1. Read monetary value from primary or alternate header field
                hdr_val = float(getattr(rec, field_name, 0.0) or 0.0)
                if hdr_val == 0.0 and alt_field:
                    hdr_val = float(getattr(rec, alt_field, 0.0) or 0.0)

                # 2. Check existing active child lines for this category & field
                SINGLE_INSTANCE_CATEGORIES = {'57iia', '80cch', '80ccd1b', 'hra', 'lta', '24b', '80dd', '80u', '80eea', '80g', '80e'}
                if cat in SINGLE_INSTANCE_CATEGORIES:
                    matching_lines = active_lines.filtered(lambda l: l.category == cat)
                elif cat == '80c':
                    matching_lines = active_lines.filtered(
                        lambda l: l.category == '80c' and rec._match_80c_child_line(l, field_name)
                    )
                else:
                    # Match by category only — description is not a reliable key because users
                    # may enter custom names. This prevents false misses that cause duplicate lines.
                    matching_lines = active_lines.filtered(lambda l: l.category == cat)
                line_val = sum(float(l.declared_amount or 0.0) for l in matching_lines) if matching_lines else 0.0
                has_approved_proof = any(
                    float(getattr(l, 'tax_firm_approved_amount', 0.0) or getattr(l, 'approved_amount', 0.0) or getattr(l, 'verified_amount', 0.0) or 0.0) > 0.0
                    for l in matching_lines
                )

                is_hdr_cleared = (field_name in header_cleared_fields)
                is_line_cleared = (field_name in line_cleared_fields)
                explicit_line_added = line_added_fields.get(field_name)
                explicit_hdr_updated = header_updated_fields.get(field_name)

                # 3. Intent-aware resolution logic
                action = 'PRESERVE'
                final_val = 0.0

                if is_hdr_cleared or is_line_cleared:
                    final_val = 0.0
                    action = 'DELETE'
                    header_updates[field_name] = 0.0
                    if alt_field and hasattr(rec, alt_field):
                        header_updates[alt_field] = 0.0
                elif explicit_line_added is not None and explicit_line_added > 0.0:
                    final_val = explicit_line_added
                    if abs(hdr_val - final_val) > 0.001:
                        header_updates[field_name] = final_val
                        if alt_field and hasattr(rec, alt_field):
                            header_updates[alt_field] = final_val
                        action = 'SYNC_HEADER'
                    else:
                        action = 'PRESERVE'
                elif explicit_hdr_updated is not None and explicit_hdr_updated > 0.0:
                    final_val = explicit_hdr_updated
                    action = 'SYNC_LINE'
                elif line_val > 0.0 and hdr_val == 0.0:
                    final_val = line_val
                    header_updates[field_name] = line_val
                    if alt_field and hasattr(rec, alt_field):
                        header_updates[alt_field] = line_val
                    action = 'SYNC_HEADER'
                elif line_val > 0.0 and hdr_val > 0.0:
                    final_val = line_val
                    if abs(hdr_val - line_val) > 0.001:
                        header_updates[field_name] = line_val
                        if alt_field and hasattr(rec, alt_field):
                            header_updates[alt_field] = line_val
                        action = 'SYNC_HEADER'
                    else:
                        action = 'PRESERVE'
                elif hdr_val > 0.0 and line_val == 0.0:
                    final_val = hdr_val
                    action = 'SYNC_LINE'
                elif has_approved_proof:
                    final_val = 0.0
                    action = 'PRESERVE'
                else:
                    final_val = 0.0
                    action = 'DELETE' if matching_lines else 'SKIP'

                is_senior = False
                if 'is_senior_field' in item:
                    is_senior = bool(getattr(rec, item['is_senior_field'], False))

                ui_info = DECLARATION_UI_REGISTRY.get(field_name, {})
                desc = ui_info.get('label', field_name)

                if cat == 'hra':
                    if rec.decl_hra_landlord_name or rec.decl_hra_landlord_pan:
                        desc += f" (Landlord: {rec.decl_hra_landlord_name or 'N/A'} (PAN: {rec.decl_hra_landlord_pan or 'N/A'}))"

                _logger.warning(
                    "[TWO-WAY LINE SYNC] Declaration ID: %s | Category: %s | Header Before: ₹%s | Line Amount: ₹%s | Final Target: ₹%s | Action: %s",
                    rec.id, cat, hdr_val, line_val, final_val, action
                )

                rec._sync_declaration_line(
                    category_code=cat,
                    description=desc,
                    amount=final_val,
                    ui_field_label=desc,
                    python_field_name=field_name,
                    is_senior=is_senior,
                    method_name=method_name
                )

            if header_updates:
                rec.with_context(no_line_sync=True).sudo().write(header_updates)

    @api.onchange(
        'decl_80c_ppf', 'decl_80c_elss', 'decl_80c_epf', 'decl_80c_lic', 'decl_80c_nsc',
        'decl_80c_ssy', 'decl_80c_fd', 'decl_80c_tuition', 'decl_80c_housing_principal', 'decl_80c_other',
        'decl_80ccd1b_nps', 'decl_80d_self', 'decl_80d_parents', 'decl_80d_preventive',
        'decl_24b_self_interest', 'decl_80eea_interest_amount', 'decl_80eea_interest',
        'decl_hra_annual_rent', 'decl_lta_declared_fare', 'decl_80tta_interest', 'decl_80ttb_interest',
        'decl_80e_interest', 'decl_80g_donation', 'decl_80gg_rent', 'decl_80dd_expenditure_amount',
        'decl_80u_amount', 'decl_57iia_family_pension', 'decl_80cch_agniveer',
        'decl_80d_self_is_senior', 'decl_80d_parents_is_senior', 'decl_80dd_is_severe_disability',
        'decl_80u_is_severe_disability', 'decl_80g_category', 'decl_hra_landlord_name', 'decl_hra_landlord_pan'
    )
    def _onchange_sync_declaration_lines_ui(self):
        """
        Live Real-Time Synchronization for UI Form View:
        Immediately adds, updates, or cleans up declaration_line_ids in-memory as the user types
        values into any deduction tab (80C, 80D, HRA, NPS, etc.) without requiring a manual save.
        """
        SINGLE_INSTANCE_CATEGORIES = {'57iia', '80cch', '80ccd1b', 'hra', 'lta', '24b', '80dd', '80u', '80eea', '80g', '80e'}
        
        for rec in self:
            existing_lines = list(rec.declaration_line_ids)
            matched_line_set = set()
            new_lines = []

            for item in DECLARATION_BUSINESS_REGISTRY:
                cat = item['category']
                field_name = item['field_name']
                alt_field = item.get('alt_field_name')

                hdr_val = float(getattr(rec, field_name, 0.0) or 0.0)
                if hdr_val == 0.0 and alt_field:
                    hdr_val = float(getattr(rec, alt_field, 0.0) or 0.0)

                ui_info = DECLARATION_UI_REGISTRY.get(field_name, {})
                desc = ui_info.get('label', field_name)
                if cat == 'hra' and (rec.decl_hra_landlord_name or rec.decl_hra_landlord_pan):
                    desc += f" (Landlord: {rec.decl_hra_landlord_name or 'N/A'} (PAN: {rec.decl_hra_landlord_pan or 'N/A'}))"

                is_senior = bool(getattr(rec, item['is_senior_field'], False)) if 'is_senior_field' in item else False
                is_severe = bool(getattr(rec, item['is_severe_field'], False)) if 'is_severe_field' in item else False

                # Find matching line
                matched = None
                for line in rec.declaration_line_ids:
                    if line in matched_line_set:
                        continue
                    if cat in SINGLE_INSTANCE_CATEGORIES and line.category == cat:
                        matched = line
                        break
                    elif cat == '80c' and line.category == '80c' and rec._match_80c_child_line(line, field_name):
                        matched = line
                        break
                    elif line.category == cat:
                        # Match by category only — do not require the canonical label to be present
                        # in the line description. Users may have entered a custom description;
                        # the description is overwritten during sync anyway.
                        matched = line
                        break

                if matched:
                    matched_line_set.add(matched)
                    if hdr_val > 0.0:
                        matched.declared_amount = hdr_val
                        # Do NOT overwrite description — user may have set a custom name.
                        # Only update amount and flags; description is preserved as-is.
                        matched.is_senior_citizen = is_senior
                        matched.is_severe_disability = is_severe
                        if cat == '80g' and hasattr(rec, 'decl_80g_category') and rec.decl_80g_category:
                            matched.decl_80g_category = rec.decl_80g_category
                        new_lines.append(matched)
                    # When header deduction is cleared (hdr_val == 0.0), do not preserve the line in new_lines
                else:
                    if hdr_val > 0.0:
                        line_vals = {
                            'declaration_id': rec._origin.id if rec._origin else False,
                            'category': cat,
                            'description': desc,
                            'declared_amount': hdr_val,
                            'is_senior_citizen': is_senior,
                            'is_severe_disability': is_severe,
                        }
                        if cat == '80g' and hasattr(rec, 'decl_80g_category') and rec.decl_80g_category:
                            line_vals['decl_80g_category'] = rec.decl_80g_category
                        created_line = self.env['tds.employee.declaration.line'].new(line_vals)
                        new_lines.append(created_line)

            # Preserve non-registry custom lines
            for line in rec.declaration_line_ids:
                if line not in matched_line_set and line not in new_lines:
                    new_lines.append(line)

            # Reassign declaration_line_ids
            rec.declaration_line_ids = [(6, 0, [])]
            for nl in new_lines:
                rec.declaration_line_ids += nl


    def action_validate_declaration_rules(self, raise_on_error=True):
        """
        Invokes EmployeeTaxDeclarationValidationService to perform regime-aware line item validations.
        """
        for rec in self:
            from ..services.tds.employee_tax_declaration_validation_service import EmployeeTaxDeclarationValidationService
            val_svc = EmployeeTaxDeclarationValidationService(self.env)
            report = val_svc.validate_declaration(rec)
            if raise_on_error and not report.is_compliant and report.error_messages:
                formatted_errors = "\n".join([f"• {msg}" for msg in report.error_messages])
                raise ValidationError(_(
                    "Tax Declaration Statutory Validation Failed:\n\n"
                    "%s\n\nPlease rectify the ineligible sections or remove the invalid claims before submitting."
                ) % formatted_errors)

    def action_submit_declaration(self):
        """Phase 1 / Phase 2: Employee submits planned investment declaration."""
        for rec in self:
            old_state = rec.state
            rec.action_validate_declaration_rules()
            rec.write({
                'state': 'declared',
                'submission_date': fields.Date.today(),
            })
            _logger.info(
                "[TDS TRACE] Phase: Declaration | Model: tds.employee.declaration | Record ID: %s | Employee: %s | FY: %s | Field: state | Old Value: %s | New Value: declared | Target Model: tds.employee.declaration | DB Write: True | Service: TdsEmployeeDeclaration | Result: Planned Investment Declaration Active",
                rec.id, rec.employee_id.name if rec.employee_id else 'N/A', rec.financial_year_id.name if rec.financial_year_id else 'N/A', old_state
            )
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_submit(self):
        """Alias for action_submit_declaration for UI compatibility."""
        return self.action_submit_declaration()

    def action_submit_proofs(self):
        """Phase 3: Employee submits proof attachments during December/January proof window."""
        for rec in self:
            old_state = rec.state
            fy = rec.financial_year_id
            if fy and not rec.is_proof_window_open and not fy.is_proof_submission_active():
                raise ValidationError(_("The Investment Proof Submission Window for Financial Year '%s' is not currently open. Please contact HR.") % (fy.name if fy else ''))
            rec.write({'state': 'proof_submitted'})
            _logger.info(
                "[TDS TRACE] Phase: Proof Submission | Model: tds.employee.declaration | Record ID: %s | Employee: %s | FY: %s | Field: state | Old Value: %s | New Value: proof_submitted | Target Model: tds.employee.declaration | DB Write: True | Service: TdsEmployeeDeclaration | Result: Proof Documents Submitted for HR Verification",
                rec.id, rec.employee_id.name if rec.employee_id else 'N/A', rec.financial_year_id.name if rec.financial_year_id else 'N/A', old_state
            )
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_start_review(self):
        """Phase 3 / Phase 4: HR starts proof verification."""
        for rec in self:
            old_state = rec.state
            rec.write({'state': 'proof_under_review'})
            _logger.info(
                "[TDS TRACE] Phase: HR Verification | Model: tds.employee.declaration | Record ID: %s | Employee: %s | FY: %s | Field: state | Old Value: %s | New Value: proof_under_review | Target Model: tds.employee.declaration | DB Write: True | Service: TdsEmployeeDeclaration | Result: Proof Verification In Progress by HR",
                rec.id, rec.employee_id.name if rec.employee_id else 'N/A', rec.financial_year_id.name if rec.financial_year_id else 'N/A', old_state
            )
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_review(self):
        """Alias for action_start_review."""
        return self.action_start_review()

    def action_verify_proofs(self):
        """Phase 4: HR completes proof verification, setting approved amounts active for Jan-Mar payroll."""
        for rec in self:
            old_state = rec.state
            for line in rec.declaration_line_ids:
                if line.category == '80g':
                    eff_amt = float(line.tax_firm_approved_amount or line.approved_amount or line.verified_amount or line.declared_amount or 0.0)
                    cat_val = line.decl_80g_category or rec.decl_80g_category
                    if eff_amt > 0.0 and not cat_val:
                        raise ValidationError(_(
                            "Section 80G Deduction Category is mandatory before approving line '%s' with amount ₹%s. "
                            "Please specify a valid 80G category."
                        ) % (line.description or 'Section 80G Donation', f"{eff_amt:,.2f}"))
                    if cat_val and not line.decl_80g_category:
                        line.write({'decl_80g_category': cat_val})

                tf_amt = float(line.tax_firm_approved_amount or 0.0)
                appr_amt = float(line.approved_amount or 0.0)
                if tf_amt > 0.0 and appr_amt == 0.0:
                    line.write({'approved_amount': tf_amt})
                elif appr_amt > 0.0 and tf_amt == 0.0:
                    line.write({'tax_firm_approved_amount': appr_amt})

            rec.write({
                'state': 'proof_verified',
                'approval_date': fields.Date.today(),
                'approved_by_id': self.env.user.id,
            })
            rec.action_validate_declaration_rules()
            rec._compute_totals()
            _logger.info(
                "[TDS TRACE] Phase: HR Verification | Model: tds.employee.declaration | Record ID: %s | Employee: %s | FY: %s | Field: state | Old Value: %s | New Value: proof_verified | Target Model: tds.employee.declaration | DB Write: True | Service: TdsEmployeeDeclaration | Result: Proof Verified; Approved Amounts Active for Jan-Mar TDS",
                rec.id, rec.employee_id.name if rec.employee_id else 'N/A', rec.financial_year_id.name if rec.financial_year_id else 'N/A', old_state
            )
            # Log audit entry
            if 'hds.in.payroll.audit' in self.env:
                self.env['hds.in.payroll.audit'].sudo().create({
                    'employee_id': rec.employee_id.id,
                    'company_id': rec.company_id.id,
                    'user_id': self.env.uid,
                    'statutory_module': 'tds',
                    'rule_code': 'TDS_DECL_APPROVE',
                    'calculation_date': fields.Date.today(),
                    'calculation_type': 'PROOF_VERIFICATION',
                    'messages': f"Tax Declaration Proof Verified: {rec.name}. FY {rec.financial_year_id.name}. Total Declared: ₹{rec.total_declared_amount:,.2f}, Total Approved: ₹{rec.total_approved_amount:,.2f}, Total Rejected: ₹{rec.total_rejected_amount:,.2f}.",
                    'status': 'success',
                })
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_approve(self):
        """Alias for action_verify_proofs for backward compatibility."""
        return self.action_verify_proofs()

    def action_recalculate_tds(self):
        """
        Executes full statutory TDS recalculation using Tax Firm Approved Amounts (or fallback approved/verified/eligible amounts)
        across ALL declared sections for the employee. Applies existing statutory eligibility capping rules, deducts YTD TDS,
        and distributes remaining tax liability across configured FY TDS months.
        """
        from ..services.tds.tds_orchestration_engine import TdsOrchestrationEngine
        orchestration_engine = TdsOrchestrationEngine(self.env)

        for rec in self:
            if rec.state not in ('proof_verified', 'approved'):
                raise ValidationError(_("Full TDS recalculation using Tax Firm Approved amounts can only be executed when declaration is in 'Proof Verified' or 'Approved' status."))

            rec._compute_totals()

            for line in rec.declaration_line_ids:
                if line.category == '80g':
                    eff_amt = float(line.tax_firm_approved_amount or line.approved_amount or line.verified_amount or line.declared_amount or 0.0)
                    cat_val = line.decl_80g_category or rec.decl_80g_category
                    if eff_amt > 0.0 and not cat_val:
                        raise ValidationError(_(
                            "Section 80G Deduction Category is mandatory before recalculating TDS for line '%s' with amount ₹%s. "
                            "Please specify a valid 80G category."
                        ) % (line.description or 'Section 80G Donation', f"{eff_amt:,.2f}"))
                    if cat_val and not line.decl_80g_category:
                        line.sudo().write({'decl_80g_category': cat_val})

            eval_dt = rec.approval_date or fields.Date.today()
            tds_result = orchestration_engine.hds_in_compute_tds(rec.employee_id, eval_date=eval_dt)

            mth_dist = getattr(tds_result, 'monthly_tds_distribution', None)
            annual_tax = float(getattr(tds_result, 'total_annual_tax_liability', 0.0) or 0.0)
            ytd_paid = float(getattr(tds_result, 'total_tds_paid_so_far', getattr(mth_dist, 'total_tds_paid_so_far', getattr(tds_result, 'ytd_tds_deducted', getattr(mth_dist, 'ytd_tds_deducted', 0.0)))) or 0.0)
            rem_tax = float(getattr(tds_result, 'remaining_annual_tax_liability', getattr(mth_dist, 'remaining_annual_tax_liability', 0.0)) or 0.0)
            rem_months = int(getattr(tds_result, 'remaining_payroll_periods', getattr(mth_dist, 'remaining_payroll_periods', 1)) or 1)
            monthly_tds = float(getattr(tds_result, 'current_month_tds', getattr(mth_dist, 'current_month_tds', 0.0)) or 0.0)

            _logger.info(
                "[TAX FIRM RECALCULATION] Executed full TDS recalculation for Employee '%s' (FY %s). "
                "Recalculated Annual Tax Liability: ₹%s, YTD TDS Paid: ₹%s, Remaining Liability: ₹%s, "
                "Remaining Months: %s, New Monthly TDS: ₹%s",
                rec.employee_id.name if rec.employee_id else 'N/A',
                rec.financial_year_id.name if rec.financial_year_id else 'N/A',
                annual_tax,
                ytd_paid,
                rem_tax,
                rem_months,
                monthly_tds
            )

            if 'hds.in.payroll.audit' in self.env:
                self.env['hds.in.payroll.audit'].sudo().create({
                    'employee_id': rec.employee_id.id,
                    'company_id': rec.company_id.id,
                    'user_id': self.env.uid,
                    'statutory_module': 'tds',
                    'rule_code': 'TAX_FIRM_RECALCULATION',
                    'calculation_date': fields.Date.today(),
                    'messages': (
                        f"Tax Firm Approved TDS Recalculation Completed: {rec.name}. FY {rec.financial_year_id.name}. "
                        f"Recalculated Annual Tax: ₹{annual_tax:,.2f}, "
                        f"YTD TDS Paid: ₹{ytd_paid:,.2f}, "
                        f"Remaining Tax: ₹{rem_tax:,.2f}, "
                        f"Distribution Months: {rem_months}, "
                        f"New Monthly TDS: ₹{monthly_tds:,.2f}."
                    ),
                    'status': 'success',
                })

            emp_name = rec.employee_id.name or 'Employee'
            fy_name = rec.financial_year_id.name or 'Current FY'
            regime_name = rec.tax_regime_id.name or (rec.regime_code.upper() if rec.regime_code else 'Standard')

            rec_html = f"""
<div class="p-3" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b;">
    <!-- Success Banner -->
    <div style="background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border: 1px solid #86efac; border-radius: 10px; padding: 16px 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
        <div style="display: flex; align-items: center; gap: 14px;">
            <div style="background: #16a34a; color: #ffffff; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: bold; flex-shrink: 0;">
                &#10003;
            </div>
            <div>
                <h4 style="margin: 0; color: #15803d; font-weight: 700; font-size: 18px; letter-spacing: -0.3px;">
                    Full TDS Recalculation Completed
                </h4>
                <p style="margin: 4px 0 0 0; color: #166534; font-size: 13px;">
                    Tax Firm Approved Amounts successfully applied across all sections for <strong>{emp_name}</strong> ({fy_name} &bull; {regime_name}).
                </p>
            </div>
        </div>
    </div>

    <!-- Statutory Metrics Grid -->
    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-bottom: 20px;">
        <!-- Card 1: Annual Tax -->
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
            <div style="font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px;">
                Recalculated Annual Tax Liability
            </div>
            <div style="font-size: 24px; font-weight: 700; color: #0f172a; margin-top: 6px;">
                &#8377;{annual_tax:,.2f}
            </div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">
                Total computed tax after statutory deductions &amp; cess
            </div>
        </div>

        <!-- Card 2: YTD TDS Paid -->
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
            <div style="font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px;">
                TDS Paid YTD (Year-to-Date)
            </div>
            <div style="font-size: 24px; font-weight: 700; color: #0284c7; margin-top: 6px;">
                &#8377;{ytd_paid:,.2f}
            </div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">
                Tax already withheld in previous payroll cycles
            </div>
        </div>

        <!-- Card 3: Remaining Tax Liability -->
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
            <div style="font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px;">
                Remaining Annual Tax Liability
            </div>
            <div style="font-size: 24px; font-weight: 700; color: #ea580c; margin-top: 6px;">
                &#8377;{rem_tax:,.2f}
            </div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">
                Outstanding balance to be deducted over remaining months
            </div>
        </div>

        <!-- Card 4: Remaining Periods -->
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);">
            <div style="font-size: 11px; color: #64748b; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px;">
                Remaining Payroll Periods
            </div>
            <div style="font-size: 24px; font-weight: 700; color: #475569; margin-top: 6px;">
                {rem_months} Month(s)
            </div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 4px;">
                Remaining distribution cycles in {fy_name}
            </div>
        </div>
    </div>

    <!-- Highlight Callout: New Monthly TDS -->
    <div style="background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); border: 2px solid #3b82f6; border-radius: 10px; padding: 18px 22px; box-shadow: 0 2px 8px rgba(59,130,246,0.15);">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div>
                <div style="font-size: 13px; color: #1e40af; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px;">
                    New Monthly TDS Withholding
                </div>
                <div style="font-size: 12px; color: #3b82f6; margin-top: 2px;">
                    Updated monthly tax deduction to be deducted in upcoming payslips
                </div>
            </div>
            <div style="font-size: 28px; font-weight: 800; color: #1d4ed8; text-align: right;">
                &#8377;{monthly_tds:,.2f}<span style="font-size: 14px; font-weight: 600; color: #3b82f6;"> / month</span>
            </div>
        </div>
    </div>
</div>
"""
            rec.sudo().write({'recalculation_summary_html': rec_html})

            view_id = self.env.ref('hudson_in_payroll.tds_recalculation_result_view_form').id
            return {
                'name': _('Full TDS Recalculation Completed'),
                'type': 'ir.actions.act_window',
                'res_model': 'tds.employee.declaration',
                'res_id': rec.id,
                'view_mode': 'form',
                'views': [(view_id, 'form')],
                'target': 'new',
                'context': {'dialog_size': 'large'},
            }

    def action_reject(self):
        """Transition to Rejected."""
        for rec in self:
            old_state = rec.state
            if not rec.rejection_reason:
                raise ValidationError(_("Please provide a Rejection Reason before rejecting the declaration."))
            rec.write({'state': 'rejected'})
            _logger.info(
                "[TDS TRACE] Phase: HR Verification | Model: tds.employee.declaration | Record ID: %s | Employee: %s | FY: %s | Field: state | Old Value: %s | New Value: rejected | Target Model: tds.employee.declaration | DB Write: True | Service: TdsEmployeeDeclaration | Result: Declaration Rejected",
                rec.id, rec.employee_id.name if rec.employee_id else 'N/A', rec.financial_year_id.name if rec.financial_year_id else 'N/A', old_state
            )

    def action_reset_to_draft(self):
        """Reset back to Draft state."""
        for rec in self:
            old_state = rec.state
            rec.write({'state': 'draft'})
            _logger.info(
                "[TDS TRACE] Phase: Declaration | Model: tds.employee.declaration | Record ID: %s | Employee: %s | FY: %s | Field: state | Old Value: %s | New Value: draft | Target Model: tds.employee.declaration | DB Write: True | Service: TdsEmployeeDeclaration | Result: Reset to Draft",
                rec.id, rec.employee_id.name if rec.employee_id else 'N/A', rec.financial_year_id.name if rec.financial_year_id else 'N/A', old_state
            )

    def unlink(self):
        """Safeguard: Statutory tax declarations cannot be deleted by users."""
        for record in self:
            if not self.env.su:
                raise UserError(_(
                    "Employee Tax Declarations cannot be deleted as they are statutory compliance records. "
                    "If updates are required, please adjust the values or reset the declaration via Employee Profile -> Income Tax."
                ))
        return super().unlink()

    def action_open_employee_income_tax(self):
        """Opens the Employee Profile to make edits or submit declarations via Income Tax tab."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Employee Profile'),
            'res_model': 'hr.employee',
            'res_id': self.employee_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_proof_rule_guide(self):
        """
        Opens the Proof Documentation & Rule Guide in a dedicated dialog/popup modal,
        reducing visual congestion on the main tax declaration form.
        """
        self.ensure_one()
        view_id = self.env.ref('hudson_in_payroll.tds_declaration_rule_guide_view_form').id
        return {
            'name': _('Proof Documentation & Rule Guide'),
            'type': 'ir.actions.act_window',
            'res_model': 'tds.employee.declaration',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(view_id, 'form')],
            'target': 'new',
            'context': {'dialog_size': 'extra-large'},
        }

    def _sync_tax_regime(self):
        """
        Synchronizes tax_regime_id on declaration header to tds.employee.tax.regime master record.
        Ensures AnnualIncomeProjectionService and DeductionCalculationService always read the correct regime.
        """
        for rec in self:
            if rec.employee_id and rec.financial_year_id and rec.tax_regime_id:
                reg_record = self.env['tds.employee.tax.regime'].sudo().search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('financial_year_id', '=', rec.financial_year_id.id),
                ], limit=1)
                if reg_record:
                    if reg_record.regime_id != rec.tax_regime_id:
                        if reg_record.is_locked:
                            raise ValidationError(_("Tax regime choice is locked by HR for Financial Year '%s'.") % rec.financial_year_id.name)
                        reg_record.sudo().write({'regime_id': rec.tax_regime_id.id})
                else:
                    self.env['tds.employee.tax.regime'].sudo().create({
                        'employee_id': rec.employee_id.id,
                        'financial_year_id': rec.financial_year_id.id,
                        'regime_id': rec.tax_regime_id.id,
                    })

    @api.model
    def _set_proof_submission_date(self, vals):
        """Record when the declaration reaches Proof Submitted (whichever way it gets there)."""
        if vals.get('state') == 'proof_submitted' and not vals.get('proof_submission_date'):
            vals = dict(vals, proof_submission_date=fields.Date.context_today(self))
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._set_proof_submission_date(vals) for vals in vals_list]
        records = super().create(vals_list)
        records._sync_tax_regime()
        records._sync_all_declaration_lines(method_name='create')
        if not self.env.context.get('no_tds_audit') and 'hds.in.payroll.audit' in self.env:
            for rec in records:
                if not rec.employee_id:
                    continue
                tracked_fields = [f for f in rec._DECLARATION_AUDIT_FIELDS if hasattr(rec, f)]
                old_diff = {}
                new_diff = {}
                for f in tracked_fields:
                    val = getattr(rec, f, None)
                    if hasattr(val, 'name'):
                        val = val.name
                    if isinstance(val, (int, float)) and abs(float(val)) >= 0.01:
                        old_diff[f] = 0.0
                        new_diff[f] = float(val)
                if new_diff:
                    calc_date = fields.Date.today()
                    self.env['hds.in.payroll.audit'].sudo().create({
                        'employee_id': rec.employee_id.id,
                        'company_id': rec.company_id.id or self.env.company.id,
                        'user_id': self.env.uid,
                        'statutory_module': 'tds',
                        'rule_code': 'TDS_DECLARATION',
                        'calculation_type': 'tax_declaration',
                        'calculation_date': calc_date,
                        'inputs_json': json.dumps(old_diff, default=str),
                        'outputs_json': json.dumps(new_diff, default=str),
                        'status': 'success',
                    })
                    audit_model = self.env['hds.in.payroll.audit']
                    label_map = {
                        'decl_80c_ppf': 'Public Provident Fund (PPF)',
                        'decl_80c_elss': 'ELSS Mutual Funds',
                        'decl_80c_epf': 'Voluntary EPF (VPF)',
                        'decl_80c_lic': 'Life Insurance Premium (LIC)',
                        'decl_80c_nsc': 'National Savings Certificate (NSC)',
                        'decl_80c_ssy': 'Sukanya Samriddhi Yojana (SSY)',
                        'decl_80c_fd': 'Tax Saving Fixed Deposit',
                        'decl_80c_tuition': 'Children Tuition Fees',
                        'decl_80c_housing_principal': 'Housing Loan Principal Repayment',
                        'decl_80c_other': 'Other 80C Specified Investments',
                        'decl_80ccd1b_nps': 'Employee Voluntary NPS (80CCD(1B))',
                        'decl_80d_self': 'Medical Insurance (Self & Family)',
                        'decl_80d_parents': 'Medical Insurance (Parents)',
                        'decl_80d_preventive': 'Preventive Health Checkup',
                        'decl_24b_self_interest': 'Interest on Housing Loan (Self-Occupied)',
                        'decl_80eea_interest_amount': '80EEA Home Loan Additional Interest',
                        'decl_80eea_interest': '80EEA Home Loan Additional Interest',
                        'decl_hra_annual_rent': 'Annual House Rent Paid (HRA)',
                        'decl_lta_declared_fare': 'Leave Travel Allowance (LTA)',
                        'decl_80tta_interest': 'Savings Interest Deduction (80TTA)',
                        'decl_80ttb_interest': 'Senior Citizen Interest (80TTB)',
                        'decl_80e_interest': 'Education Loan Interest (80E)',
                        'decl_80g_donation': 'Charitable Donations (80G)',
                        'decl_80gg_rent': 'Rent Paid without HRA (80GG)',
                        'decl_80dd_expenditure_amount': 'Dependent Disability (80DD)',
                        'decl_80u_amount': 'Employee Disability (80U)',
                        'decl_80ccd2_employer_nps': 'Employer NPS Contribution (80CCD(2))',
                        'decl_57iia_family_pension': 'Family Pension Received (Section 57(iia))',
                        'decl_80cch_agniveer': 'Agniveer Corpus Fund (80CCH)',
                        'total_declared_amount': 'Total Declared Deductions',
                        'total_approved_amount': 'Total Approved Deductions',
                        'state': 'Declaration Status',
                        'tax_regime_id': 'Tax Regime',
                        'savings_bank_interest': 'Savings Account Interest',
                        'fixed_deposit_interest': 'Fixed Deposit Interest',
                        'dividend_income': 'Dividend Income',
                        'other_sources_income': 'Other Miscellaneous Income',
                        'total_other_sources_income': 'Total Other Sources Income',
                        'annual_let_out_rent': 'Gross Annual Rent (Let-Out Property)',
                        'municipal_taxes_paid': 'Municipal Taxes Paid',
                        'let_out_interest_paid': 'Housing Loan Interest (Let-Out Property)',
                        'net_house_property_income_loss': 'Net Property Income / Loss',
                        'prev_employer_taxable_gross': 'Previous Employer Taxable Salary',
                        'prev_employer_tds': 'Previous Employer TDS Deducted',
                        'prev_employer_pt': 'Previous Employer PT Deducted',
                        'prev_employer_pf': 'Previous Employer EPF',
                    }
                    diff_html_parts = []
                    for k in rec._DECLARATION_AUDIT_FIELDS:
                        if k in new_diff:
                            old_f = audit_model._format_audit_value(k, old_diff.get(k))
                            new_f = audit_model._format_audit_value(k, new_diff.get(k))
                            lbl = label_map.get(k, k.replace('_', ' ').title())
                            diff_html_parts.append(
                                f'<div style="line-height: 1.45; margin-bottom: 1px;">'
                                f'<span style="color: #212529;">{old_f}</span>'
                                f'<span style="color: #495057;"> → </span>'
                                f'<b style="color: #008784;">{new_f}</b>'
                                f' <span style="color: #6c757d; font-style: italic;">({lbl})</span>'
                                f'</div>'
                            )
                    if diff_html_parts:
                        today_str = fields.Date.today().strftime('%b %d, %Y').replace(' 0', ' ')
                        chatter_body = (
                            f'<div style="color: #008784; font-weight: bold; margin-bottom: 3px;">'
                            f'→ As of {today_str}</div>'
                            + ''.join(diff_html_parts)
                        )
                        if hasattr(rec, 'message_post'):
                            rec.message_post(body=Markup(chatter_body), subtype_xmlid='mail.mt_note')
                        if rec.employee_id and hasattr(rec.employee_id, 'message_post'):
                            fy_str = rec.financial_year_id.name if rec.financial_year_id else ''
                            emp_body = (
                                f'<div style="font-weight: 600; margin-bottom: 2px;">TDS Declaration Created ({fy_str}):</div>'
                                + chatter_body
                            )
                            rec.employee_id.message_post(body=Markup(emp_body), subtype_xmlid='mail.mt_note')
        for rec in records:
            _logger.warning(
                "[HR & ESS DECLARATION PERSISTENCE AUDIT] Created Declaration ID: %s | Employee: %s (ID: %s) | FY: %s | Total Declared: ₹%s | Line Items: %s",
                rec.id, rec.employee_id.name if rec.employee_id else "None", rec.employee_id.id if rec.employee_id else "None",
                rec.financial_year_id.name if rec.financial_year_id else "None", rec.total_declared_amount, len(rec.declaration_line_ids)
            )
        return records

    def write(self, vals):
        if isinstance(vals, dict):
            vals = self._set_proof_submission_date(vals)
        if self.env.context.get('no_tds_audit'):
            return super().write(vals)

        # 1. Capture old state for tracked fields
        tracked_fields = [f for f in self._DECLARATION_AUDIT_FIELDS if hasattr(self, f)]
        old_state = {}
        for rec in self:
            old_dict = {}
            for f in tracked_fields:
                val = getattr(rec, f, None)
                if hasattr(val, 'name'):
                    val = val.name
                old_dict[f] = val
            old_state[rec.id] = old_dict

        pre_deleted_lines = {}
        if vals and isinstance(vals, dict) and 'declaration_line_ids' in vals:
            for cmd in vals.get('declaration_line_ids') or []:
                if isinstance(cmd, (list, tuple)) and len(cmd) >= 2 and cmd[0] in (1, 2, 3) and cmd[1]:
                    l_rec = self.env['tds.employee.declaration.line'].browse(cmd[1]).exists()
                    if l_rec:
                        pre_deleted_lines[cmd[1]] = (l_rec.category, l_rec.description)

        res = super().write(vals)
        if not self.env.context.get('no_line_sync'):
            self._sync_tax_regime()
            self._sync_all_declaration_lines(method_name='write', write_vals=vals, pre_deleted_lines=pre_deleted_lines)

        # 2. Check for differences and log to Audit Trail + Chatter
        if 'hds.in.payroll.audit' in self.env:
            for rec in self:
                if not rec.employee_id:
                    continue
                rec_old = old_state.get(rec.id, {})
                old_diff = {}
                new_diff = {}
                for f in tracked_fields:
                    old_v = rec_old.get(f)
                    new_v = getattr(rec, f, None)
                    if hasattr(new_v, 'name'):
                        new_v = new_v.name
                    if isinstance(old_v, (int, float)) and isinstance(new_v, (int, float)):
                        if round(float(old_v or 0.0), 2) != round(float(new_v or 0.0), 2):
                            old_diff[f] = float(old_v or 0.0)
                            new_diff[f] = float(new_v or 0.0)
                    elif old_v != new_v:
                        if old_v or new_v:
                            old_diff[f] = old_v
                            new_diff[f] = new_v

                if new_diff:
                    calc_date = fields.Date.today()
                    self.env['hds.in.payroll.audit'].sudo().create({
                        'employee_id': rec.employee_id.id,
                        'company_id': rec.company_id.id or self.env.company.id,
                        'user_id': self.env.uid,
                        'statutory_module': 'tds',
                        'rule_code': 'TDS_DECLARATION',
                        'calculation_type': 'tax_declaration',
                        'calculation_date': calc_date,
                        'inputs_json': json.dumps(old_diff, default=str),
                        'outputs_json': json.dumps(new_diff, default=str),
                        'status': 'success',
                    })
                    audit_model = self.env['hds.in.payroll.audit']
                    label_map = {
                        'decl_80c_ppf': 'Public Provident Fund (PPF)',
                        'decl_80c_elss': 'ELSS Mutual Funds',
                        'decl_80c_epf': 'Voluntary EPF (VPF)',
                        'decl_80c_lic': 'Life Insurance Premium (LIC)',
                        'decl_80c_nsc': 'National Savings Certificate (NSC)',
                        'decl_80c_ssy': 'Sukanya Samriddhi Yojana (SSY)',
                        'decl_80c_fd': 'Tax Saving Fixed Deposit',
                        'decl_80c_tuition': 'Children Tuition Fees',
                        'decl_80c_housing_principal': 'Housing Loan Principal Repayment',
                        'decl_80c_other': 'Other 80C Specified Investments',
                        'decl_80ccd1b_nps': 'Employee Voluntary NPS (80CCD(1B))',
                        'decl_80d_self': 'Medical Insurance (Self & Family)',
                        'decl_80d_parents': 'Medical Insurance (Parents)',
                        'decl_80d_preventive': 'Preventive Health Checkup',
                        'decl_24b_self_interest': 'Interest on Housing Loan (Self-Occupied)',
                        'decl_80eea_interest_amount': '80EEA Home Loan Additional Interest',
                        'decl_80eea_interest': '80EEA Home Loan Additional Interest',
                        'decl_hra_annual_rent': 'Annual House Rent Paid (HRA)',
                        'decl_lta_declared_fare': 'Leave Travel Allowance (LTA)',
                        'decl_80tta_interest': 'Savings Interest Deduction (80TTA)',
                        'decl_80ttb_interest': 'Senior Citizen Interest (80TTB)',
                        'decl_80e_interest': 'Education Loan Interest (80E)',
                        'decl_80g_donation': 'Charitable Donations (80G)',
                        'decl_80gg_rent': 'Rent Paid without HRA (80GG)',
                        'decl_80dd_expenditure_amount': 'Dependent Disability (80DD)',
                        'decl_80u_amount': 'Employee Disability (80U)',
                        'decl_80ccd2_employer_nps': 'Employer NPS Contribution (80CCD(2))',
                        'decl_57iia_family_pension': 'Family Pension Received (Section 57(iia))',
                        'decl_80cch_agniveer': 'Agniveer Corpus Fund (80CCH)',
                        'total_declared_amount': 'Total Declared Deductions',
                        'total_approved_amount': 'Total Approved Deductions',
                        'state': 'Declaration Status',
                        'tax_regime_id': 'Tax Regime',
                        'savings_bank_interest': 'Savings Account Interest',
                        'fixed_deposit_interest': 'Fixed Deposit Interest',
                        'dividend_income': 'Dividend Income',
                        'other_sources_income': 'Other Miscellaneous Income',
                        'total_other_sources_income': 'Total Other Sources Income',
                        'annual_let_out_rent': 'Gross Annual Rent (Let-Out Property)',
                        'municipal_taxes_paid': 'Municipal Taxes Paid',
                        'let_out_interest_paid': 'Housing Loan Interest (Let-Out Property)',
                        'net_house_property_income_loss': 'Net Property Income / Loss',
                        'prev_employer_taxable_gross': 'Previous Employer Taxable Salary',
                        'prev_employer_tds': 'Previous Employer TDS Deducted',
                        'prev_employer_pt': 'Previous Employer PT Deducted',
                        'prev_employer_pf': 'Previous Employer EPF',
                    }
                    diff_html_parts = []
                    for k in rec._DECLARATION_AUDIT_FIELDS:
                        if k in new_diff:
                            old_f = audit_model._format_audit_value(k, old_diff.get(k))
                            new_f = audit_model._format_audit_value(k, new_diff.get(k))
                            lbl = label_map.get(k, k.replace('_', ' ').title())
                            diff_html_parts.append(
                                f'<div style="line-height: 1.45; margin-bottom: 1px;">'
                                f'<span style="color: #212529;">{old_f}</span>'
                                f'<span style="color: #495057;"> → </span>'
                                f'<b style="color: #008784;">{new_f}</b>'
                                f' <span style="color: #6c757d; font-style: italic;">({lbl})</span>'
                                f'</div>'
                            )
                    if diff_html_parts:
                        today_str = fields.Date.today().strftime('%b %d, %Y').replace(' 0', ' ')
                        chatter_body = (
                            f'<div style="color: #008784; font-weight: bold; margin-bottom: 3px;">'
                            f'→ As of {today_str}</div>'
                            + ''.join(diff_html_parts)
                        )
                        if hasattr(rec, 'message_post'):
                            rec.message_post(body=Markup(chatter_body), subtype_xmlid='mail.mt_note')
                        if rec.employee_id and hasattr(rec.employee_id, 'message_post'):
                            fy_str = rec.financial_year_id.name if rec.financial_year_id else ''
                            emp_body = (
                                f'<div style="font-weight: 600; margin-bottom: 2px;">TDS Declaration Update ({fy_str}):</div>'
                                + chatter_body
                            )
                            rec.employee_id.message_post(body=Markup(emp_body), subtype_xmlid='mail.mt_note')
        if not self.env.context.get('no_att_sync'):
            self.with_context(no_att_sync=True)._sync_attachments_to_master()
        _logger.warning(
            "[HR & ESS DECLARATION PERSISTENCE AUDIT] Write Called on Declaration IDs: %s | Payload Vals: %s",
            self.ids, vals
        )
        return res

    def _sync_attachments_to_master(self):
        """
        Synchronizes all attachments uploaded via contextual fields or declaration line items
        into the master attachment_ids pool.
        """
        contextual_fields = [
            'decl_80c_attachment_ids', 'decl_80d_attachment_ids', 'decl_80ccd1b_attachment_ids',
            'decl_hra_attachment_ids', 'decl_lta_attachment_ids', 'decl_24b_attachment_ids',
            'decl_80e_attachment_ids', 'decl_80g_attachment_ids', 'decl_80gg_attachment_ids',
            'decl_80dd_attachment_ids', 'decl_80u_attachment_ids', 'decl_57iia_attachment_ids',
            'decl_80cch_attachment_ids', 'prev_employer_attachment_ids'
        ]
        for rec in self:
            all_attachments = self.env['ir.attachment']
            for fname in contextual_fields:
                if hasattr(rec, fname):
                    all_attachments |= getattr(rec, fname)
            for line in rec.declaration_line_ids:
                all_attachments |= line.attachment_ids
            new_att = all_attachments - rec.attachment_ids
            if new_att:
                rec.with_context(no_tds_audit=True, no_line_sync=True, no_att_sync=True).sudo().write({
                    'attachment_ids': [(4, att.id) for att in new_att]
                })

    def _compute_proof_rule_guide_html(self):
        """
        Dynamically computes a READ-ONLY informational HTML guide displaying statutory rule parameters,
        eligibility conditions, and typical supporting documentation for declared sections.
        Reads parameters dynamically from TdsParameterService (Single Source of Truth).
        Never modifies state, approved amounts, or TDS calculation values.
        """
        from ..services.tds.tds_parameter_service import TdsParameterService
        from ..services.tds.tds_section_config_service import TdsSectionConfigService
        tds_param_svc = TdsParameterService(self.env)
        sec_config_svc = TdsSectionConfigService(self.env)

        for rec in self:
            fy = rec.financial_year_id
            eval_date = (getattr(fy, 'start_date', False) or getattr(fy, 'date_from', False)) if fy else fields.Date.today()
            fy_name = rec.financial_year_id.name if rec.financial_year_id else 'Tax Year: 2026-27'
            ay_name = rec.financial_year_id.assessment_year if rec.financial_year_id and hasattr(rec.financial_year_id, 'assessment_year') and rec.financial_year_id.assessment_year else 'AY 2027-28'
            regime_title = "Old Tax Regime (Section 202(1) Opted Out)" if rec.regime_code == 'old' else "New Tax Regime Income-tax Act, 2025 — Section 202(1)"

            active_sections = sec_config_svc.get_active_sections(regime_code=rec.regime_code, eval_date=eval_date)
            active_sec_codes = [s.code for s in active_sections] if active_sections else [s.code for s in self.env['tds.tax.section.config'].search([])]

            # Resolve statutory parameters dynamically via TdsParameterService
            cap_80c = tds_param_svc.get_parameter('HDS_IN_TDS_80C_MAX_LIMIT', eval_date=eval_date, regime=rec.regime_code)
            cap_80ccd1b = tds_param_svc.get_parameter('HDS_IN_TDS_80CCD1B_MAX_LIMIT', eval_date=eval_date, regime=rec.regime_code)
            cap_80d_self = tds_param_svc.get_parameter('HDS_IN_TDS_80D_SELF_MAX_LIMIT', eval_date=eval_date, regime=rec.regime_code)
            cap_80d_par_sr = tds_param_svc.get_parameter('HDS_IN_TDS_80D_PARENTS_SENIOR_MAX_LIMIT', eval_date=eval_date, regime=rec.regime_code)
            cap_80tta = tds_param_svc.get_parameter('HDS_IN_TDS_80TTA_MAX_LIMIT', eval_date=eval_date, regime=rec.regime_code)
            cap_80ttb = tds_param_svc.get_parameter('HDS_IN_TDS_80TTB_MAX_LIMIT', eval_date=eval_date, regime=rec.regime_code)
            cap_24b = tds_param_svc.get_parameter('HDS_IN_TDS_24B_HOME_LOAN_INTEREST_LIMIT', eval_date=eval_date, regime=rec.regime_code)
            cap_80dd_sev = tds_param_svc.get_80dd_severe_deduction(eval_date=eval_date)
            cap_80u_sev = tds_param_svc.get_80u_severe_deduction(eval_date=eval_date)

            cards = []

            # Notice header
            notice_html = """
            <div style="background-color:#eff6ff; border-left:4px solid #3b82f6; padding:12px 16px; border-radius:6px; margin-bottom:20px;">
                <h4 style="margin:0 0 4px 0; color:#1e40af; font-size:15px; font-weight:600;">
                    <i class="fa fa-info-circle me-1"></i> HR Informational Guide &amp; Proof Documentation Guidance
                </h4>
                <p style="margin:0; font-size:13px; color:#1e3a8a; line-height:1.4;">
                    This guide provides statutory rule parameters and typical proof documentation guidelines for sections declared under this tax declaration. 
                    <strong>Note:</strong> Detailed document audit is performed externally by the designated tax verification team. HR records the verified/approved amount received.
                </p>
            </div>
            """

            # 1. SECTION 80C
            if '80C' in active_sec_codes and rec.regime_code == 'old' and (rec.decl_80c_total > 0 or any(getattr(rec, f, 0) > 0 for f in ['decl_80c_ppf', 'decl_80c_elss', 'decl_80c_epf', 'decl_80c_lic', 'decl_80c_nsc', 'decl_80c_ssy', 'decl_80c_fd', 'decl_80c_tuition', 'decl_80c_housing_principal', 'decl_80c_other'])):
                tot_decl = rec.decl_80c_total or sum(float(getattr(rec, f, 0) or 0) for f in ['decl_80c_ppf', 'decl_80c_elss', 'decl_80c_epf', 'decl_80c_lic', 'decl_80c_nsc', 'decl_80c_ssy', 'decl_80c_fd', 'decl_80c_tuition', 'decl_80c_housing_principal', 'decl_80c_other'])
                tot_elig = min(tot_decl, cap_80c)
                tot_excess = max(0.0, tot_decl - cap_80c)
                cards.append(self._build_card_html(
                    section_code="Section 80C",
                    section_title="Investments in PPF, ELSS, EPF, LIC, Tuition Fees & Principal Repayments",
                    fy_name=fy_name, ay_name=ay_name, regime_title=regime_title,
                    declared_amt=tot_decl, eligible_amt=tot_elig, cap_amt=cap_80c, excess_amt=tot_excess,
                    param_code="HDS_IN_TDS_80C_MAX_LIMIT", param_val=cap_80c, date_from=eval_date,
                    statutory_rule="Deduction allowed for specified life insurance premiums, provident fund contributions, ELSS mutual funds, tuition fees, and housing loan principal repayments. Subject to a combined statutory aggregate ceiling across all 80C components.",
                    conditions=[
                        "Combined aggregate ceiling applies to total of all 10 80C components.",
                        "ELSS investments have a 3-year statutory lock-in period.",
                        "Tuition fees allowed for up to 2 children for full-time education in Indian institutions.",
                        "Housing loan principal allowed only for self-occupied/let-out property construction/acquisition."
                    ],
                    typical_docs=[
                        "PPF Passbook / Deposit Receipt",
                        "ELSS Mutual Fund Account Statement / Certificate",
                        "EPF / VPF Statement / Slip",
                        "LIC Policy Premium Paid Receipt",
                        "National Savings Certificate (NSC) Receipt",
                        "Sukanya Samriddhi Yojana (SSY) Passbook / Deposit Proof",
                        "Tax Saving 5-Year Fixed Deposit Certificate",
                        "School / College Tuition Fee Paid Receipt",
                        "Housing Loan Principal Repayment Certificate from Bank"
                    ]
                ))

            # 2. SECTION 80CCD(1B)
            if rec.regime_code == 'old' and rec.decl_80ccd1b_nps > 0:
                tot_decl = rec.decl_80ccd1b_nps
                tot_elig = min(tot_decl, cap_80ccd1b)
                tot_excess = max(0.0, tot_decl - cap_80ccd1b)
                cards.append(self._build_card_html(
                    section_code="Section 80CCD(1B)",
                    section_title="Employee Voluntary NPS Contribution (National Pension System)",
                    fy_name=fy_name, ay_name=ay_name, regime_title=regime_title,
                    declared_amt=tot_decl, eligible_amt=tot_elig, cap_amt=cap_80ccd1b, excess_amt=tot_excess,
                    param_code="HDS_IN_TDS_80CCD1B_MAX_LIMIT", param_val=cap_80ccd1b, date_from=eval_date,
                    statutory_rule="Additional deduction allowed for individual voluntary contributions to the National Pension System (NPS Tier-I account), over and above the Section 80C limit of ₹1,50,000.",
                    conditions=[
                        "Deduction restricted exclusively to Tier-I NPS accounts.",
                        "Deduction limit capped at statutory maximum of ₹50,000.",
                        "This deduction is in addition to the Section 80C ceiling."
                    ],
                    typical_docs=[
                        "NPS Tier-I Contribution Receipt / Statement",
                        "PRAN (Permanent Retirement Account Number) Card / Statement",
                        "NPS Online Transaction Receipt"
                    ]
                ))

            # 3. SECTION 80D
            if rec.regime_code == 'old' and (rec.decl_80d_self > 0 or rec.decl_80d_parents > 0 or rec.decl_80d_preventive > 0):
                d_self = float(rec.decl_80d_self or 0.0)
                d_par = float(rec.decl_80d_parents or 0.0)
                d_prev = float(rec.decl_80d_preventive or 0.0)
                tot_decl = d_self + d_par + d_prev

                self_is_senior = bool(
                    getattr(rec, 'decl_80d_self_is_senior', False)
                    or (rec.employee_id and (getattr(rec.employee_id, 'is_senior_citizen', False) or getattr(rec.employee_id, 'hds_in_decl_80d_self_is_senior', False)))
                    or any(l.is_senior_citizen for l in rec.declaration_line_ids if l.category == '80d_self')
                )
                parents_is_senior = bool(
                    getattr(rec, 'decl_80d_parents_is_senior', False)
                    or (rec.employee_id and getattr(rec.employee_id, 'hds_in_decl_80d_parents_is_senior', False))
                    or any(l.is_senior_citizen for l in rec.declaration_line_ids if l.category == '80d_parents')
                )

                cap_self = 50000.0 if self_is_senior else (cap_80d_self or 25000.0)
                cap_par = 50000.0 if parents_is_senior else 25000.0

                # Compute profile-accurate statutory cap based on active declared components
                if (d_self > 0 or d_prev > 0) and d_par > 0:
                    profile_cap = cap_self + cap_par
                elif d_par > 0:
                    profile_cap = cap_par
                else:
                    profile_cap = cap_self

                elig_self = min(d_self + min(d_prev, 5000.0), cap_self)
                elig_par = min(d_par, cap_par)
                tot_elig = elig_self + elig_par
                tot_excess = max(0.0, tot_decl - tot_elig)

                param_display_code = ("HDS_IN_TDS_80D_SELF_SENIOR_MAX_LIMIT" if self_is_senior else "HDS_IN_TDS_80D_SELF_MAX_LIMIT") if (d_self > 0 or d_prev > 0 or d_par == 0) else ("HDS_IN_TDS_80D_PARENTS_SENIOR_MAX_LIMIT" if parents_is_senior else "HDS_IN_TDS_80D_PARENTS_MAX_LIMIT")
                param_display_val = cap_self if (d_self > 0 or d_prev > 0 or d_par == 0) else cap_par

                cards.append(self._build_card_html(
                    section_code="Section 80D",
                    section_title="Medical Insurance Premiums & Health Checkups",
                    fy_name=fy_name, ay_name=ay_name, regime_title=regime_title,
                    declared_amt=tot_decl, eligible_amt=tot_elig, cap_amt=profile_cap, excess_amt=tot_excess,
                    param_code=param_display_code, param_val=param_display_val, date_from=eval_date,
                    statutory_rule=f"Deduction allowed for health insurance premiums paid for self/family (Cap: INR {cap_self:,.0f}) and parents (Cap: INR {cap_par:,.0f}). Preventive health checkups allowed up to INR 5,000 sub-limit.",
                    conditions=[
                        f"Self & Family Statutory Limit: INR {cap_self:,.0f} ({'Senior Citizen 60+' if self_is_senior else 'Non-Senior'}).",
                        f"Parents Statutory Limit: INR {cap_par:,.0f} ({'Senior Citizen 60+' if parents_is_senior else 'Non-Senior'}).",
                        "Premiums must be paid by non-cash mode (Netbanking, UPI, Card, Cheque).",
                        "Preventive health checkups allowed up to INR 5,000 (included within overall Self 80D limit)."
                    ],
                    typical_docs=[
                        "Health Insurance Policy Document & Premium Receipt",
                        "80D Tax Exemption Certificate issued by Insurance Company",
                        "Preventive Health Checkup Bill & Payment Receipt"
                    ]
                ))

            # 4. SECTION 80E
            if rec.regime_code == 'old' and rec.decl_80e_interest > 0:
                cards.append(self._build_card_html(
                    section_code="Section 80E",
                    section_title="Interest on Higher Education Loan",
                    fy_name=fy_name, ay_name=ay_name, regime_title=regime_title,
                    declared_amt=rec.decl_80e_interest, eligible_amt=rec.decl_80e_interest, cap_amt=None, excess_amt=0.0,
                    param_code="HDS_IN_TDS_80E_MAX_DEDUCTION_YEARS", param_val=8, date_from=eval_date,
                    statutory_rule="Deduction for interest paid on loan taken for higher education of self, spouse, children, or student for whom the individual is legal guardian. No statutory upper monetary limit on interest amount.",
                    conditions=[
                        "Loan must be sanctioned by an approved financial institution or charitable body.",
                        "Deduction available for maximum of 8 consecutive assessment years starting from first repayment year.",
                        "Applies exclusively to higher education (post-senior secondary)."
                    ],
                    typical_docs=[
                        "Education Loan Interest Certificate from Bank / Financial Institution",
                        "Loan Account Statement showing interest paid during FY",
                        "Course Enrollment Evidence for Higher Education"
                    ]
                ))

            # 5. SECTION 80G
            if rec.regime_code == 'old' and rec.decl_80g_donation > 0:
                cards.append(self._build_card_html(
                    section_code="Section 80G",
                    section_title="Donations to Charitable Funds & Eligible Institutions",
                    fy_name=fy_name, ay_name=ay_name, regime_title=regime_title,
                    declared_amt=rec.decl_80g_donation, eligible_amt=rec.decl_80g_donation, cap_amt=None, excess_amt=0.0,
                    param_code="HDS_IN_TDS_80G_MAX_CASH_DONATION", param_val=2000.0, date_from=eval_date,
                    statutory_rule="Deduction allowed for donations made to specified charitable funds and approved institutions (100% or 50% deduction depending on category and qualifying limit).",
                    conditions=[
                        "Cash donations exceeding ₹2,00,000 are strictly NOT eligible for tax deduction.",
                        "Donation receipt must contain Donee Name, PAN, Registration Number & 80G Certificate details.",
                        "Form 10BE Certificate issued by donee institution required for proof."
                    ],
                    typical_docs=[
                        "Official 80G Donation Receipt with Donee PAN & Registration Number",
                        "Form 10BE Certificate of Donation",
                        "Bank Payment Proof (Cheque counterfoil / Bank statement / Online receipt)"
                    ]
                ))

            # 6. SECTION 80TTA / 80TTB
            if rec.regime_code == 'old' and (rec.decl_80tta_interest > 0 or rec.decl_80ttb_interest > 0):
                amt = rec.decl_80tta_interest or rec.decl_80ttb_interest
                code = "Section 80TTB" if rec.decl_80ttb_interest > 0 else "Section 80TTA"
                title = "Interest on Deposits in Savings Account (Senior Citizens)" if rec.decl_80ttb_interest > 0 else "Interest on Savings Bank Accounts"
                pcode = "HDS_IN_TDS_80TTB_MAX_LIMIT" if rec.decl_80ttb_interest > 0 else "HDS_IN_TDS_80TTA_MAX_LIMIT"
                cap = cap_80ttb if rec.decl_80ttb_interest > 0 else cap_80tta
                elig = min(amt, cap)
                cards.append(self._build_card_html(
                    section_code=code, section_title=title,
                    fy_name=fy_name, ay_name=ay_name, regime_title=regime_title,
                    declared_amt=amt, eligible_amt=elig, cap_amt=cap, excess_amt=max(0.0, amt - cap),
                    param_code=pcode, param_val=cap, date_from=eval_date,
                    statutory_rule="Deduction allowed for interest income earned from savings accounts with banks, co-operative societies, or post office.",
                    conditions=[
                        "Section 80TTA applies to non-senior citizens (capped at ₹10,000).",
                        "Section 80TTB applies to resident senior citizens age 60+ (capped at ₹50,000, covers savings + FD interest).",
                        "FD interest is not eligible under 80TTA."
                    ],
                    typical_docs=[
                        "Bank Savings Account Passbook / Statement",
                        "Bank Interest Certificate for Financial Year"
                    ]
                ))

            # 7. SECTION 24(b) / HRA
            if rec.regime_code == 'old' and (rec.decl_24b_self_interest > 0 or rec.decl_hra_annual_rent > 0):
                if rec.decl_24b_self_interest > 0:
                    amt = rec.decl_24b_self_interest
                    elig = min(amt, cap_24b)
                    cards.append(self._build_card_html(
                        section_code="Section 24(b)", section_title="Interest on Home Loan for Self-Occupied Property",
                        fy_name=fy_name, ay_name=ay_name, regime_title=regime_title,
                        declared_amt=amt, eligible_amt=elig, cap_amt=cap_24b, excess_amt=max(0.0, amt - cap_24b),
                        param_code="HDS_IN_TDS_24B_HOME_LOAN_INTEREST_LIMIT", param_val=cap_24b, date_from=eval_date,
                        statutory_rule="Deduction for interest paid on housing loan borrowed for acquisition or construction of self-occupied residential house property.",
                        conditions=[
                            "Maximum statutory limit of ₹2,00,000 per financial year for self-occupied property.",
                            "Construction must be completed within 5 years from end of FY in which loan was taken."
                        ],
                        typical_docs=[
                            "Provisional / Final Interest Certificate from Lender Bank",
                            "Loan Sanction Letter & Possession Certificate"
                        ]
                    ))
                if rec.decl_hra_annual_rent > 0:
                    cards.append(self._build_card_html(
                        section_code="Section 10(13A)", section_title="House Rent Allowance (HRA) Exemption",
                        fy_name=fy_name, ay_name=ay_name, regime_title=regime_title,
                        declared_amt=rec.decl_hra_annual_rent, eligible_amt=rec.decl_hra_annual_rent, cap_amt=None, excess_amt=0.0,
                        param_code="HDS_IN_TDS_HRA_METRO_PERCENT", param_val=50.0, date_from=eval_date,
                        statutory_rule="Exemption for House Rent Allowance calculated as minimum of: 1) Actual HRA Received, 2) Rent Paid - 10% Basic Salary, 3) 50% Basic (Metro) / 40% Basic (Non-Metro).",
                        conditions=[
                            "Employee must actually reside in rented accommodation and pay rent.",
                            "Landlord PAN mandatory if annual rent exceeds ₹1,00,000."
                        ],
                        typical_docs=[
                            "Valid Rent Agreement / Lease Deed",
                            "Rent Receipts signed by Landlord (with Revenue Stamp if rent > ₹5,000/month)",
                            "Landlord PAN Copy (Mandatory if annual rent > ₹1,00,000)"
                        ]
                    ))

            # 7b. LET-OUT HOUSE PROPERTY (Section 23 & Section 24(b) - Both Regimes)
            if (rec.annual_let_out_rent > 0 or rec.municipal_taxes_paid > 0 or rec.let_out_interest_paid > 0):
                rent = float(rec.annual_let_out_rent or 0.0)
                muni = float(rec.municipal_taxes_paid or 0.0)
                intr = float(rec.let_out_interest_paid or 0.0)
                nav = max(0.0, rent - muni)
                std_ded = nav * 0.30
                net_hp = nav - std_ded - intr

                setoff_limit = cap_24b if rec.regime_code == 'old' else 0.0
                setoff_param_code = "HDS_IN_TDS_HOUSE_PROPERTY_LOSS_LIMIT" if rec.regime_code == 'old' else "HDS_IN_TDS_NEW_REGIME_HP_LOSS_LIMIT"

                if net_hp < 0:
                    allowed_setoff = min(abs(net_hp), setoff_limit) if rec.regime_code == 'old' else 0.0
                    gti_impact_str = f"-INR {allowed_setoff:,.2f} (Loss Set-Off)" if allowed_setoff > 0 else "INR 0.00 (No Set-Off under New Regime)"
                else:
                    gti_impact_str = f"+INR {net_hp:,.2f} (Taxable Rental Income)"

                cards.append(self._build_card_html(
                    section_code="Section 23 & 24(b)",
                    section_title="Income / Loss from Let-Out House Property",
                    fy_name=fy_name, ay_name=ay_name, regime_title=regime_title,
                    declared_amt=rent, eligible_amt=abs(net_hp) if net_hp < 0 else net_hp, cap_amt=setoff_limit if net_hp < 0 else None, excess_amt=max(0.0, abs(net_hp) - setoff_limit) if (net_hp < 0 and rec.regime_code == 'old') else 0.0,
                    param_code=setoff_param_code, param_val=setoff_limit, date_from=eval_date,
                    statutory_rule=f"Gross Annual Rent less Municipal Taxes Paid equals Net Annual Value (NAV). Statutory 30% NAV repair allowance deducted u/s 24(a). Full actual let-out home loan interest deducted u/s 24(b) (uncapped). Net HP Impact on GTI: {gti_impact_str}.",
                    conditions=[
                        "NAV = Gross Rent Received - Municipal Taxes Paid to local body.",
                        "Statutory 30% NAV Standard Repair Allowance deducted automatically u/s 24(a).",
                        "Let-Out Home Loan Interest is UNCAPPED u/s 24(b).",
                        f"Old Regime Loss Set-Off against Salary: Capped at INR {cap_24b:,.0f} u/s 71(3A).",
                        "New Regime Loss Set-Off against Salary: STRICTLY PROHIBITED (INR 0 set-off)."
                    ],
                    typical_docs=[
                        "Valid Lease / Rent Agreement with Tenant",
                        "Rent Paid Receipts / Bank Statements showing rent credits",
                        "Municipal Property Tax Paid Receipt",
                        "Let-Out Property Home Loan Interest Certificate from Lender Bank"
                    ]
                ))

            # 8. SECTION 80DD / 80U
            if rec.regime_code == 'old' and (rec.decl_80dd_amount > 0 or rec.decl_80u_amount > 0):
                if rec.decl_80dd_amount > 0:
                    is_severe = bool(getattr(rec, 'decl_80dd_is_severe_disability', False))
                    cap_80dd = cap_80dd_sev if is_severe else 75000.0
                    pcode_80dd = "HDS_IN_TDS_80DD_SEVERE_LIMIT" if is_severe else "HDS_IN_TDS_80DD_NORMAL_LIMIT"
                    cards.append(self._build_card_html(
                        section_code="Section 80DD", section_title="Maintenance & Medical Treatment of Dependent Person with Disability",
                        fy_name=fy_name, ay_name=ay_name, regime_title=regime_title,
                        declared_amt=rec.decl_80dd_amount, eligible_amt=rec.decl_80dd_amount, cap_amt=cap_80dd, excess_amt=0.0,
                        param_code=pcode_80dd, param_val=cap_80dd, date_from=eval_date,
                        statutory_rule="Flat deduction allowed for maintenance including medical treatment of a dependent with disability (₹75,000 for normal disability 40%-79%, ₹1,25,000 for severe disability 80%+).",
                        conditions=[
                            "Dependent includes spouse, children, parents, brothers, and sisters.",
                            "Normal Disability (40%-79%): Flat INR 75,000 deduction limit.",
                            "Severe Disability (80%+): Flat INR 1,25,000 deduction limit.",
                            "Valid disability certificate Form 10IA issued by medical authority required."
                        ],
                        typical_docs=[
                            "Medical Certificate Form 10IA / Certificate of Disability from Govt Medical Board",
                            "Self-declaration / Proof of Dependent Maintenance Expenditure"
                        ]
                    ))
                if rec.decl_80u_amount > 0:
                    cards.append(self._build_card_html(
                        section_code="Section 80U", section_title="Deduction for Person with Disability (Employee Self)",
                        fy_name=fy_name, ay_name=ay_name, regime_title=regime_title,
                        declared_amt=rec.decl_80u_amount, eligible_amt=rec.decl_80u_amount, cap_amt=cap_80u_sev, excess_amt=0.0,
                        param_code="HDS_IN_TDS_80U_SEVERE_DEDUCTION", param_val=cap_80u_sev, date_from=eval_date,
                        statutory_rule="Flat deduction allowed for resident employee certified with disability (₹75,000 for 40%-79% disability, ₹1,25,000 for 80%+ severe disability).",
                        conditions=[
                            "Available exclusively to resident individuals.",
                            "Valid medical certificate issued by prescribed medical authority required."
                        ],
                        typical_docs=[
                            "Disability Certificate Form 10IA / Medical Authority Certificate"
                        ]
                    ))

            # 9. BOTH REGIMES (Employer NPS 80CCD(2))
            has_80ccd2_line = any(l.category == '80ccd2' and getattr(l, 'active', True) for l in rec.declaration_line_ids)
            decl_80ccd2_val = rec.decl_80ccd2_employer_nps or (sum(float(l.usable_amount if l.usable_amount is not None else (l.declared_amount or 0.0)) for l in rec.declaration_line_ids if l.category == '80ccd2' and getattr(l, 'active', True)))
            if rec.decl_80ccd2_employer_nps > 0 or has_80ccd2_line:
                emp = rec.employee_id
                emp_type = (getattr(emp, 'hds_in_employer_category', getattr(emp, 'employer_type', 'private')) if emp else 'private') or 'private'
                nps_pct = tds_param_svc.get_employer_nps_limit(regime=rec.regime_code, employer_type=emp_type, eval_date=eval_date) or 10.0
                nps_param_code = 'HDS_IN_TDS_NPS_LIMIT_NEW' if rec.regime_code == 'new' else ('HDS_IN_TDS_NPS_LIMIT_OLD_GOVT' if 'govt' in str(emp_type).lower() else 'HDS_IN_TDS_NPS_LIMIT_OLD_PRIVATE')
                
                from ..services.tds.salary_projection_service import SalaryProjectionService
                sal_proj_svc = SalaryProjectionService(self.env)
                sal_res = sal_proj_svc.project_salary(emp, fy, eval_date=eval_date) if emp and fy else None
                sal_b = ((sal_res.total_basic or 0.0) + (sal_res.total_da or 0.0)) if sal_res else 0.0
                nps_cap = sal_b * (nps_pct / 100.0) if sal_b > 0 else None
                nps_elig = min(decl_80ccd2_val, nps_cap) if nps_cap is not None else decl_80ccd2_val
                nps_excess = max(0.0, decl_80ccd2_val - nps_cap) if nps_cap is not None else 0.0

                cards.append(self._build_card_html(
                    section_code="Section 124", section_title="Employer Contribution to National Pension System (NPS) — Section 124",
                    fy_name=fy_name, ay_name=ay_name, regime_title=regime_title,
                    declared_amt=decl_80ccd2_val, eligible_amt=nps_elig, cap_amt=nps_cap, excess_amt=nps_excess,
                    param_code=nps_param_code, param_val=nps_pct, date_from=eval_date,
                    statutory_rule=f"Deduction allowed for employer's contribution to employee's NPS account. Allowed under BOTH Old and New Tax Regimes (up to {nps_pct:.0f}% of Salary Base: Basic + DA).",
                    conditions=[
                        "Employer contribution paid into Tier-I NPS account.",
                        f"Statutory percentage ceiling based on salary (Basic + DA) ({nps_pct:.0f}% limit under {nps_param_code})."
                    ],
                    typical_docs=[
                        "Employer Payroll Contribution Statement",
                        "NPS Tier-I Account Statement"
                    ]
                ))

            # 10. BOTH REGIMES (Section 57(iia) Family Pension Deduction)
            d_57iia = float(getattr(rec, 'decl_57iia_family_pension', 0.0) or 0.0)
            line_57iia = sum(float(l.usable_amount if l.usable_amount is not None else (l.declared_amount or 0.0)) for l in rec.declaration_line_ids if l.category == '57iia' and getattr(l, 'active', True))
            tot_57iia = max(d_57iia, line_57iia)
            if tot_57iia > 0:
                from ..services.tds.section_57iia_deduction_service import Section57IIADeductionService
                sec_code_57 = Section57IIADeductionService.get_statutory_section_code(financial_year=rec.financial_year_id, eval_date=eval_date)
                legal_label_57 = Section57IIADeductionService.get_legal_reference_label(financial_year=rec.financial_year_id, eval_date=eval_date)
                cap_57iia = tds_param_svc.get_family_pension_limit(regime=rec.regime_code, eval_date=eval_date)
                pcode_57iia = 'HDS_IN_TDS_FAMILY_PENSION_LIMIT_NEW' if rec.regime_code == 'new' else 'HDS_IN_TDS_FAMILY_PENSION_LIMIT_OLD'
                elig_57iia = min(tot_57iia / 3.0, cap_57iia)
                cards.append(self._build_card_html(
                    section_code=f"Section {sec_code_57}", section_title=f"Standard Deduction on Family Pension Income (Section {sec_code_57})",
                    fy_name=fy_name, ay_name=ay_name, regime_title=regime_title,
                    declared_amt=tot_57iia, eligible_amt=elig_57iia, cap_amt=cap_57iia, excess_amt=max(0.0, tot_57iia - elig_57iia),
                    param_code=pcode_57iia, param_val=cap_57iia, date_from=eval_date,
                    statutory_rule=f"Statutory standard deduction allowed for family pension received by legal heirs under {legal_label_57}. Calculated as minimum of 1/3rd of family pension income or INR {cap_57iia:,.0f}. Netted directly under Income from Other Sources under BOTH Old and New Tax Regimes.",
                    conditions=[
                        "Deduction calculated as 1/3rd of gross family pension received.",
                        f"Statutory ceiling: INR {cap_57iia:,.0f} per financial year under {regime_title}.",
                        "Netted under Income from Other Sources under BOTH Old Regime and New Tax Regime Income-tax Act, 2025 — Section 202(1)."
                    ],
                    typical_docs=[
                        "Pension Payment Order (PPO) Passbook / Credit Certificate",
                        "Bank Statement showing Monthly Family Pension Credit",
                        "Legal Heir Certificate / Death Certificate of Pensioner"
                    ]
                ))

            # 11. BOTH REGIMES (Section 80CCH Agniveer Corpus Fund)
            if rec.hds_in_is_agnipath:
                d_80cch = float(getattr(rec, 'decl_80cch_agniveer', 0.0) or 0.0)
                line_80cch = sum(float(l.usable_amount if l.usable_amount is not None else (l.declared_amount or 0.0)) for l in rec.declaration_line_ids if l.category == '80cch' and getattr(l, 'active', True))
                tot_80cch = max(d_80cch, line_80cch)
                if tot_80cch > 0:
                    cards.append(self._build_card_html(
                        section_code="Section 80CCH", section_title="Contributions to Agniveer Corpus Fund (Agnipath Scheme)",
                        fy_name=fy_name, ay_name=ay_name, regime_title=regime_title,
                        declared_amt=tot_80cch, eligible_amt=tot_80cch, cap_amt=None, excess_amt=0.0,
                        param_code="HDS_IN_TDS_80CCH_DEDUCTION_LIMIT", param_val=tot_80cch, date_from=eval_date,
                        statutory_rule="100% statutory deduction allowed for contributions made by an individual enrolled in the Agnipath Scheme to the Agniveer Corpus Fund u/s 80CCH(1). Allowed under BOTH Old and New Tax Regimes.",
                        conditions=[
                            "Deduction available for individual contribution to Agniveer Corpus Fund.",
                            "No upper monetary statutory ceiling (100% of contribution allowed).",
                            "Allowed under BOTH Old Tax Regime and New Tax Regime Income-tax Act, 2025 — Section 202(1)."
                        ],
                        typical_docs=[
                            "Agniveer Corpus Fund Contribution Certificate / Statement",
                            "Salary Slip showing Agniveer Corpus Fund Deduction",
                            "Agnipath Enrollment Certificate / Defense Identity Record"
                        ]
                    ))

            if not cards:
                cards.append("""
                <div style="background-color:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:24px; text-align:center; margin-top:10px;">
                    <i class="fa fa-folder-open-o" style="font-size:36px; color:#9ca3af; margin-bottom:12px;"></i>
                    <h3 style="margin:0 0 8px 0; color:#374151; font-size:16px;">No Active Tax Declarations Found</h3>
                    <p style="margin:0; color:#6b7280; font-size:13px;">
                        When investment declarations are entered under Section 80C, 80D, 80CCD, HRA, etc., detailed statutory rule parameters and proof documentation guidelines will dynamically appear here.
                    </p>
                </div>
                """)

            rec.proof_rule_guide_html = f"<div style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'>{notice_html}{''.join(cards)}</div>"

    def _build_card_html(self, section_code, section_title, fy_name, ay_name, regime_title, declared_amt, eligible_amt, cap_amt, excess_amt, param_code, param_val, date_from, statutory_rule, conditions, typical_docs):
        cap_str = f"INR {cap_amt:,.2f}" if cap_amt is not None else "No Monetary Cap (100% Eligible)"
        param_val_str = f"INR {param_val:,.2f}" if isinstance(param_val, (int, float)) and param_val > 100 else (f"{param_val}%" if isinstance(param_val, (int, float)) else str(param_val))

        cond_items = "".join([f"<li style='margin-bottom:4px; font-size:12px; color:#374151;'>{c}</li>" for c in conditions])
        doc_items = "".join([f"<li style='margin-bottom:4px; font-size:12px; color:#1e40af;'>{d}</li>" for d in typical_docs])

        return f"""
        <div style="background-color:#ffffff; border:1px solid #d1d5db; border-radius:8px; padding:18px; margin-bottom:20px; box-shadow:0 1px 3px rgba(0,0,0,0.05);">
            <div style="border-bottom:2px solid #3b82f6; padding-bottom:10px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div>
                    <span style="background-color:#1e40af; color:#ffffff; font-size:12px; font-weight:700; padding:3px 10px; border-radius:4px; text-transform:uppercase;">{section_code}</span>
                    <h3 style="margin:6px 0 0 0; color:#111827; font-size:16px; font-weight:600;">{section_title}</h3>
                </div>
                <div style="font-size:11px; color:#6b7280; text-align:right;">
                    <div><strong>FY:</strong> {fy_name} | <strong>AY:</strong> {ay_name}</div>
                    <div style="color:#2563eb; font-weight:600;">{regime_title}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap:10px; background-color:#f9fafb; padding:12px; border-radius:6px; border:1px solid #e5e7eb; margin-bottom:14px;">
                <div>
                    <div style="font-size:10px; text-transform:uppercase; color:#6b7280; font-weight:600;">Declared Amount</div>
                    <div style="font-size:14px; font-weight:700; color:#1f2937;">INR {declared_amt:,.2f}</div>
                </div>
                <div>
                    <div style="font-size:10px; text-transform:uppercase; color:#6b7280; font-weight:600;">System Eligible</div>
                    <div style="font-size:14px; font-weight:700; color:#16a34a;">INR {eligible_amt:,.2f}</div>
                </div>
                <div>
                    <div style="font-size:10px; text-transform:uppercase; color:#6b7280; font-weight:600;">Statutory Cap</div>
                    <div style="font-size:13px; font-weight:600; color:#4b5563;">{cap_str}</div>
                </div>
                <div>
                    <div style="font-size:10px; text-transform:uppercase; color:#6b7280; font-weight:600;">Excess Declared</div>
                    <div style="font-size:14px; font-weight:700; color:{'#dc2626' if excess_amt > 0 else '#6b7280'};">INR {excess_amt:,.2f}</div>
                </div>
            </div>

            <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px; margin-bottom:14px;">
                <div style="background-color:#ffffff; border:1px solid #e5e7eb; padding:12px; border-radius:6px;">
                    <h5 style="margin:0 0 6px 0; color:#374151; font-size:12px; font-weight:700; text-transform:uppercase; border-bottom:1px solid #f3f4f6; padding-bottom:4px;">
                        <i class="fa fa-gavel me-1" style="color:#4b5563;"></i> Statutory Rule &amp; Conditions
                    </h5>
                    <p style="font-size:12px; color:#4b5563; margin:0 0 8px 0; line-height:1.4;">{statutory_rule}</p>
                    <ul style="margin:0; padding-left:16px;">
                        {cond_items}
                    </ul>
                </div>

                <div style="background-color:#f0f9ff; border:1px solid #bae6fd; padding:12px; border-radius:6px;">
                    <h5 style="margin:0 0 6px 0; color:#0369a1; font-size:12px; font-weight:700; text-transform:uppercase; border-bottom:1px solid #e0f2fe; padding-bottom:4px;">
                        <i class="fa fa-file-text-o me-1" style="color:#0284c7;"></i> Typical Supporting Documentation
                    </h5>
                    <ul style="margin:0; padding-left:16px;">
                        {doc_items}
                    </ul>
                </div>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; background-color:#f3f4f6; padding:8px 12px; border-radius:6px; font-size:11px; color:#4b5563; gap:8px;">
                <div>
                    <i class="fa fa-shield me-1" style="color:#6b7280;"></i>
                    <strong>HR Awareness:</strong> Detailed proof audit handled externally. HR records verified/approved results. System applies statutory limits.
                </div>
                <div>
                    <strong>Parameter:</strong> <code>{param_code}</code> | <strong>Value:</strong> {param_val_str} (w.e.f. {date_from})
                </div>
            </div>
        </div>
        """

