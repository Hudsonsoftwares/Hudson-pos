# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class TdsEmployeeHomeLoan(models.Model):
    """
    TDS Employee Home Loan & Section 80EEA Eligibility Declaration Model.
    Captures employee-specific housing loan facts, sanction dates, property stamp values,
    and first-time home buyer status required for Section 24(b) and Section 80EEA statutory validation.

    Enforces the separation of Employee Facts from Statutory Monetary Ceilings.
    """
    _name = 'tds.employee.home.loan'
    _description = 'Employee Home Loan & Section 80EEA Declaration'
    _order = 'financial_year_id desc, employee_id, id'

    name = fields.Char(
        string="Loan Reference Title",
        compute='_compute_name',
        store=True,
        help="Automated title display."
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        required=True,
        ondelete='cascade',
        help="Employee making the housing loan declaration."
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        related='employee_id.company_id',
        store=True,
        readonly=True
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
        help="Tax year for which this housing loan interest deduction is declared."
    )

    loan_sanction_date = fields.Date(
        string="Loan Sanction Date",
        required=True,
        help="Official sanction date of the housing loan by the lending financial institution (crucial for Section 80EEA)."
    )
    loan_amount = fields.Float(
        string="Sanctioned Loan Amount (₹)",
        required=True,
        default=0.0,
        help="Total housing loan amount sanctioned in Rupees."
    )
    property_stamp_value = fields.Float(
        string="Property Stamp Duty Value (₹)",
        required=True,
        default=0.0,
        help="Stamp duty value of the residential house property in Rupees (crucial for Section 80EEA ≤ ₹45 Lakhs limit)."
    )
    is_first_time_home_buyer = fields.Boolean(
        string="First-Time Home Buyer",
        default=True,
        help="Check if the employee does not own any other residential house property on the date of loan sanction."
    )
    lending_institution = fields.Char(
        string="Lending Bank / Financial Institution",
        help="Name of bank, HFC, or financial institution (e.g. State Bank of India, HDFC Bank)."
    )
    loan_account_number = fields.Char(
        string="Loan Account Number",
        help="Unique loan account number."
    )
    loan_purpose = fields.Selection([
        ('purchase', 'Purchase'),
        ('construction', 'Construction'),
        ('repair_renovation', 'Repair-Renovation')
    ], string="Loan Taken For", default='purchase',
       help="Purpose for which housing loan was taken under Section 24(b): Purchase, Construction, or Repair-Renovation.")
    borrowing_date = fields.Date(
        string="Loan/Capital Borrowing Date",
        help="Date when housing loan/capital was borrowed under Section 24(b)."
    )
    completion_date = fields.Date(
        string="Construction/Purchase Completion Date",
        help="Date of completion of construction or purchase of property under Section 24(b)."
    )
    lender_type = fields.Selection([
        ('scheduled_bank', 'Scheduled Bank'),
        ('housing_finance_company', 'Housing Finance Company'),
        ('nbfc', 'NBFC'),
        ('other', 'Other')
    ], string="80EEA Lending Institution Type", default='scheduled_bank',
       help="Type of lending financial institution sanctioning housing loan under Section 80EEA.")
    eea_interest_amount = fields.Float(
        string="80EEA Interest Amount",
        default=0.0,
        help="Housing loan interest amount claimed under Section 80EEA."
    )
    interest_claimed_24b = fields.Float(
        string="Interest Already Claimed under Section 24(b)",
        default=0.0,
        help="Interest amount already claimed as deduction under Section 24(b)."
    )
    claimed_interest_amount = fields.Float(
        string="Declared Annual Interest (₹)",
        required=True,
        default=0.0,
        help="Total annual interest payable on housing loan declared by the employee."
    )
    approved_deduction_amount = fields.Float(
        string="Approved Section 80EEA Deduction (₹)",
        compute='_compute_eligibility',
        store=True,
        help="Calculated Section 80EEA deduction amount after statutory eligibility validation."
    )
    is_80eea_eligible = fields.Boolean(
        string="Section 80EEA Eligible",
        compute='_compute_eligibility',
        store=True,
        help="True if employee satisfies all statutory conditions under Section 80EEA."
    )
    eligibility_remarks = fields.Text(
        string="Eligibility Audit Remarks",
        compute='_compute_eligibility',
        store=True,
        help="Detailed statutory audit remarks detailing eligibility or reasons for disqualification."
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string="Declaration State",
        default='draft',
        required=True
    )
    active = fields.Boolean(
        string="Active",
        default=True
    )

    @api.depends('employee_id.name', 'financial_year_id.name', 'loan_account_number')
    def _compute_name(self):
        for rec in self:
            emp_str = rec.employee_id.name if rec.employee_id else 'Employee'
            fy_str = rec.financial_year_id.name if rec.financial_year_id else 'FY'
            acct_str = f" ({rec.loan_account_number})" if rec.loan_account_number else ""
            rec.name = f"Home Loan - {emp_str} [{fy_str}]{acct_str}"

    @api.depends(
        'loan_sanction_date',
        'property_stamp_value',
        'is_first_time_home_buyer',
        'claimed_interest_amount',
        'state'
    )
    def _compute_eligibility(self):
        """
        Invokes Section80EEAEligibilityService to evaluate employee eligibility
        and compute allowed deduction amount safely.
        """
        for rec in self:
            if not rec.loan_sanction_date:
                rec.is_80eea_eligible = False
                rec.approved_deduction_amount = 0.0
                rec.eligibility_remarks = "Loan Sanction Date is missing."
                continue

            try:
                service = self.env['services.tds.section_80eea_eligibility_service'] if 'services.tds.section_80eea_eligibility_service' in self.env else None
            except Exception:
                service = None

            # Instantiate service directly from addon path
            from ..services.tds.section_80eea_eligibility_service import Section80EEAEligibilityService
            svc = Section80EEAEligibilityService(self.env)
            res = svc.validate_eligibility(rec, eval_date=rec.loan_sanction_date)

            rec.is_80eea_eligible = res.is_eligible
            rec.approved_deduction_amount = res.allowed_deduction
            rec.eligibility_remarks = res.remarks
