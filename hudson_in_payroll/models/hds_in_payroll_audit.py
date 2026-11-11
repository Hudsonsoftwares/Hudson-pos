# -*- coding: utf-8 -*-
import json
# pyrefly: ignore [missing-import]
from odoo import api, fields, models
# pyrefly: ignore [missing-import]
from odoo.tools import html_escape


class HdsInPayrollAudit(models.Model):
    """
    Statutory Payroll Calculation Audit Storage Model.
    Stores immutable calculation snapshots for Indian Statutory Compliance.
    """
    _name = 'hds.in.payroll.audit'
    _description = 'Audit Trail'
    _order = 'create_date desc, id desc'
    _rec_name = 'display_name'

    company_id = fields.Many2one(
        'res.company',
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        readonly=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string="Employee",
        required=True,
        index=True,
        readonly=True
    )
    payslip_id = fields.Many2one(
        'hr.payslip',
        string="Payslip",
        ondelete='cascade',
        index=True,
        readonly=True
    )
    user_id = fields.Many2one(
        'res.users',
        string="Author",
        default=lambda self: self.env.user,
        index=True,
        readonly=True
    )
    statutory_module = fields.Selection([
        ('epf', 'Employee Provident Fund (EPF)'),
        ('esic', 'Employees State Insurance (ESIC)'),
        ('pt', 'Professional Tax (PT)'),
        ('lwf', 'Labour Welfare Fund (LWF)'),
        ('bonus', 'Statutory Bonus'),
        ('gratuity', 'Gratuity'),
        ('leave_encashment', 'Leave Encashment'),
        ('tds', 'Income Tax (TDS)'),
        ('revision', 'Salary Revision'),
    ], string="Statutory Module", required=True, index=True, readonly=True)

    calculation_type = fields.Char(
        string="Calculation Type",
        default="statutory_compute",
        readonly=True
    )
    rule_code = fields.Char(
        string="Rule Code",
        required=True,
        index=True,
        readonly=True
    )
    calculation_date = fields.Date(
        string="Calculation Date",
        required=True,
        index=True,
        default=fields.Date.today,
        readonly=True
    )

    inputs_json = fields.Text(
        string="Inputs (JSON)",
        help="Formatted JSON payload containing all input variables.",
        readonly=True
    )
    outputs_json = fields.Text(
        string="Outputs (JSON)",
        help="Formatted JSON payload containing all output calculation results.",
        readonly=True
    )
    parameters_json = fields.Text(
        string="Applied Parameters (JSON)",
        help="Formatted JSON payload containing all date-effective rule parameters used.",
        readonly=True
    )

    messages = fields.Text(string="Audit Messages", readonly=True)
    warnings = fields.Text(string="Warnings", readonly=True)
    exception_trace = fields.Text(string="Exception Stack Trace", readonly=True)
    execution_time_ms = fields.Float(string="Execution Time (ms)", digits=(16, 3), readonly=True)
    version = fields.Char(string="Engine Version", default="19.0.1.0.0", readonly=True)

    status = fields.Selection([
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ], string="Status", required=True, default='success', index=True, readonly=True)

    display_name = fields.Char(string="Title", compute='_compute_display_name', store=True)
    description_html = fields.Html(
        string="Description",
        compute='_compute_description_html',
        sanitize=False,
    )

    @api.depends('statutory_module', 'rule_code', 'employee_id', 'calculation_date')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = (
                f"[{rec.statutory_module.upper() if rec.statutory_module else ''}] "
                f"{rec.rule_code or ''} - {rec.employee_id.name or ''} "
                f"({rec.calculation_date or ''})"
            )

    @api.depends('outputs_json', 'inputs_json', 'calculation_date', 'statutory_module', 'rule_code', 'status', 'messages', 'warnings')
    def _compute_description_html(self):
        """
        Build Odoo-style Audit Trail description HTML showing field-level
        old → new diffs matching Odoo Online Audit Trail.
        Format:
            → As of DD Mon YYYY
            OLD → NEW (Field Label)
        """
        IGNORED_KEYS = {
            'employee_id', 'employee_name', 'eval_date', 'date_to', 'date_from',
            'company_id', 'payslip_id', 'is_senior', 'pan', 'regime_id', 'id',
            'version', 'REVISION_TYPE', 'REVISION_BASIS', 'revision_record_id',
            'contract_template_id', 'struct_id', 'structure_type_id',
            'date_version', 'contract_date_start', 'contract_date_end',
            'actual_pf_wage', 'pf_contribution_wage', 'gross_wage',
        }

        LABEL_MAP = {
            'wage': 'Wage',
            'wage_type': 'Wage Type',
            'salary_calculation_type': 'Salary Calculation Type',
            'basic_salary': 'Basic Salary',
            'basic_salary_percentage': 'Basic Salary Percentage',
            'basic_salary_percent': 'Basic Salary Percentage',
            'hra': 'House Rent Allowance',
            'hra_percentage': 'House Rent Allowance Percentage',
            'hra_percent': 'House Rent Allowance Percentage',
            'da': 'Dearness Allowance',
            'da_percent': 'Dearness Allowance Percentage',
            'da_percentage': 'Dearness Allowance Percentage',
            'fixed_allowance': 'Fixed Allowance',
            'fixed_allowance_percentage': 'Fixed Allowance Percentage',
            'fixed_allowance_percent': 'Fixed Allowance Percentage',
            'standard_allowance': 'Standard Allowance',
            'standard_allowance_percentage': 'Standard Allowance Percentage',
            'standard_allowance_percent': 'Standard Allowance Percentage',
            'performance_bonus': 'Performance Bonus',
            'performance_bonus_percentage': 'Performance Bonus Percentage',
            'performance_bonus_percent': 'Performance Bonus Percentage',
            'retention_bonus': 'Retention Bonus',
            'retention_bonus_percentage': 'Retention Bonus Percentage',
            'retention_bonus_percent': 'Retention Bonus Percentage',
            'lta_allowance': 'Leave Travel Allowance',
            'lta_percent': 'Leave Travel Allowance Percentage',
            'lta_percentage': 'Leave Travel Allowance Percentage',
            'travel_allowance': 'Travel Allowance',
            'meal_allowance': 'Meal Allowance',
            'medical_allowance': 'Medical Allowance',
            'other_allowance': 'Other Allowance',
            'pay_by_attendance': 'Pay by Attendance',
            'enable_attendance_threshold': 'Enable Attendance Threshold',
            'min_attendance_threshold_days': 'Minimum Attendance Days',
            'hds_in_employer_cost_monthly': 'Employer Cost (Monthly)',
            'hds_in_employer_cost_annual': 'Employer Cost to Company (CTC)',
            'l10n_in_esic_employee_amount': 'L10N In Esic Employee Amount',
            'l10n_in_esic_employer_amount': 'L10N In Esic Employer Amount',
            'l10n_in_pf_employee_amount': 'L10N In Pf Employee Amount',
            'employer': 'Employer',
            'employee_epf': 'L10N In Pf Employee Amount',
            'employee_pf': 'L10N In Pf Employee Amount',
            'employer_epf': 'Employer',
            'employer_pf': 'Employer',
            'employer_eps': 'Employer EPS',
            'employer_edli': 'Employer EDLI',
            'epf_admin_charges': 'EPF Admin Charges',
            'edli_admin_charges': 'EDLI Admin Charges',
            'employee_esic': 'L10N In Esic Employee Amount',
            'employer_esic': 'L10N In Esic Employer Amount',
            'esic_employer_contribution': 'L10N In Esic Employer Amount',
            'esic_employee_deduction': 'L10N In Esic Employee Amount',
            'esic_daily_wage_exempt': 'Esic Daily Wage Exempt',
            'pt_deduction': 'Professional Tax Deduction',
            'lwf_ee': 'L10N In Lwf Employee Amount',
            'lwf_er': 'L10N In Lwf Employer Amount',
            'benefit_phone': 'Phone Subscription',
            'benefit_internet': 'Internet Subscription',
            'benefit_meal_vouchers': 'Meal Vouchers',
            'benefit_transport': 'Company Transport',
            'benefit_medical_insurance_per_person': 'Medical Insurance Rate (per person)',
            'benefit_insured_spouse': 'Insured Spouse',
            'benefit_insured_first_child': 'Insured First-Child',
            'benefit_insured_second_child': 'Insured Second-Child',
            'benefit_medical_insurance_amount': 'Medical Insurance Amount',
            'new_wage': 'Wage',
            'old_wage': 'Wage',
            # TDS Declarations (Section 80C, 80D, 80CCD, 24(b), HRA, LTA, etc.)
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
            'total_eligible_amount': 'Total Eligible Deductions',
            'total_approved_amount': 'Total Approved Deductions',
            'decl_80c_total_declared': 'Section 80C Total Declared',
            'decl_80c_total_eligible': 'Section 80C Total Eligible',
            'state': 'Declaration Status',
            'tax_regime_id': 'Tax Regime',
            # Employee Income Tax (TDS) Profile Fields
            'hds_in_current_tax_regime_id': 'Tax Regime',
            'hds_in_tax_regime': 'Tax Regime',
            'hds_in_tds_applicable': 'TDS Applicable',
            'hds_in_is_agnipath': 'Employee under Agnipath Scheme',
            'hds_in_residential_status': 'Residential Status',
            'hds_in_pan': 'PAN',
            'hds_in_aadhaar': 'Aadhaar Number',
            'hds_in_decl_80ccd2_employer_nps': 'Employer NPS Contribution (80CCD(2))',
            'hds_in_prev_taxable_gross': 'Previous Employer Taxable Salary',
            'hds_in_prev_tds_deducted': 'Previous Employer TDS Deducted',
            'hds_in_prev_pt_deducted': 'Previous Employer PT Deducted',
            'hds_in_prev_employer_pf': 'Previous Employer EPF',
            'hds_in_prev_employer_nps': 'Previous Employer NPS',
            # Income from Other Sources & House Property (Both Declaration & Employee)
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
            'hds_in_decl_57iia_family_pension': 'Family Pension Received (Section 57(iia))',
            'hds_in_savings_bank_interest': 'Savings Account Interest',
            'hds_in_fixed_deposit_interest': 'Fixed Deposit Interest',
            'hds_in_dividend_income': 'Dividend Income',
            'hds_in_other_sources_income': 'Other Miscellaneous Income',
            'hds_in_total_other_sources_income': 'Total Other Sources Income',
            'hds_in_annual_let_out_rent': 'Gross Annual Rent (Let-Out Property)',
            'hds_in_municipal_taxes_paid': 'Municipal Taxes Paid',
            'hds_in_let_out_interest_paid': 'Housing Loan Interest (Let-Out Property)',
            'hds_in_net_house_property_income_loss': 'Net Property Income / Loss',
        }

        # Preferred display order matching Odoo screenshot & chatter
        KEY_ORDER = [
            # Salary Revision
            'wage',
            'basic_salary',
            'basic_salary_percentage', 'basic_salary_percent',
            'hra',
            'hra_percentage', 'hra_percent',
            'da', 'da_percent', 'da_percentage',
            'fixed_allowance',
            'fixed_allowance_percentage', 'fixed_allowance_percent',
            'standard_allowance', 'standard_allowance_percent', 'standard_allowance_percentage',
            'performance_bonus', 'performance_bonus_percent', 'performance_bonus_percentage',
            'retention_bonus', 'retention_bonus_percent', 'retention_bonus_percentage',
            'lta_allowance', 'lta_percent', 'lta_percentage',
            'wage_type',
            'salary_calculation_type',
            'l10n_in_esic_employee_amount', 'employee_esic', 'esic_employee_deduction',
            'l10n_in_esic_employer_amount', 'employer_esic', 'esic_employer_contribution',
            'l10n_in_pf_employee_amount', 'employee_epf', 'employee_pf',
            'employer_epf', 'employer_pf', 'employer',
            # Income Tax Profile
            'hds_in_current_tax_regime_id', 'hds_in_tax_regime', 'tax_regime_id',
            'hds_in_residential_status', 'hds_in_tds_applicable', 'hds_in_pan', 'hds_in_aadhaar',
            'hds_in_is_agnipath',
            'hds_in_prev_taxable_gross', 'hds_in_prev_tds_deducted', 'hds_in_prev_pt_deducted',
            'hds_in_prev_employer_pf', 'hds_in_prev_employer_nps',
            # Tax Declarations & Deductions
            'total_declared_amount', 'total_approved_amount', 'total_eligible_amount',
            'decl_80c_ppf', 'decl_80c_elss', 'decl_80c_epf', 'decl_80c_lic', 'decl_80c_nsc',
            'decl_80c_ssy', 'decl_80c_fd', 'decl_80c_tuition', 'decl_80c_housing_principal', 'decl_80c_other',
            'decl_80ccd1b_nps',
            'decl_80d_self', 'decl_80d_parents', 'decl_80d_preventive',
            'decl_24b_self_interest', 'decl_80eea_interest_amount',
            'decl_hra_annual_rent', 'decl_lta_declared_fare',
            'decl_80tta_interest', 'decl_80ttb_interest', 'decl_80e_interest',
            'decl_80g_donation', 'decl_80gg_rent', 'decl_80dd_expenditure_amount', 'decl_80u_amount',
            'decl_80ccd2_employer_nps', 'decl_57iia_family_pension', 'decl_80cch_agniveer',
            # Income from Other Sources & House Property
            'savings_bank_interest', 'hds_in_savings_bank_interest',
            'fixed_deposit_interest', 'hds_in_fixed_deposit_interest',
            'dividend_income', 'hds_in_dividend_income',
            'other_sources_income', 'hds_in_other_sources_income',
            'total_other_sources_income', 'hds_in_total_other_sources_income',
            'annual_let_out_rent', 'hds_in_annual_let_out_rent',
            'municipal_taxes_paid', 'hds_in_municipal_taxes_paid',
            'let_out_interest_paid', 'hds_in_let_out_interest_paid',
            'net_house_property_income_loss', 'hds_in_net_house_property_income_loss',
            'prev_employer_taxable_gross', 'prev_employer_tds', 'prev_employer_pt', 'prev_employer_pf',
            'state',
        ]

        for rec in self:
            lines = []

            # 1. Clean Header: "→ As of Mon D, YYYY" in teal bold matching chatter
            if rec.calculation_date:
                date_str = rec.calculation_date.strftime('%b %d, %Y').replace(' 0', ' ')
            else:
                date_str = ''
            header = f'<div style="color: #008784; font-weight: bold; margin-bottom: 3px;">→ As of {html_escape(date_str)}</div>'
            lines.append(header)

            # 2. Parse outputs and inputs
            try:
                outputs = json.loads(rec.outputs_json or '{}')
            except (json.JSONDecodeError, TypeError):
                outputs = {}

            try:
                inputs = json.loads(rec.inputs_json or '{}')
            except (json.JSONDecodeError, TypeError):
                inputs = {}

            diff_lines = []

            # Collect all distinct candidate keys
            all_keys = []
            for k in KEY_ORDER:
                if (k in outputs or k in inputs) and k not in IGNORED_KEYS:
                    all_keys.append(k)
            for k in list(outputs.keys()) + list(inputs.keys()):
                if k not in all_keys and k not in IGNORED_KEYS:
                    all_keys.append(k)

            for key in all_keys:
                new_val = outputs.get(key)
                old_val = inputs.get(key)

                if new_val is None and old_val is None:
                    continue

                # If new_val is given but old_val is missing, default old_val to 0.0 for numeric
                if old_val is None:
                    if isinstance(new_val, (int, float)):
                        old_val = 0.0
                    else:
                        old_val = '—'

                # If old_val is given but new_val is missing, default new_val to 0.0
                if new_val is None:
                    if isinstance(old_val, (int, float)):
                        new_val = 0.0
                    else:
                        new_val = '—'

                # If old and new are identical (no effective change), skip unless it's the only key
                is_same = False
                if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                    is_same = (round(float(old_val), 2) == round(float(new_val), 2))
                elif old_val == new_val:
                    is_same = True

                if is_same and len(all_keys) > 1:
                    continue

                # Format values
                old_fmt = rec._format_audit_value(key, old_val)
                new_fmt = rec._format_audit_value(key, new_val)
                field_label = LABEL_MAP.get(key, key.replace('_', ' ').title())

                diff_lines.append(
                    f'<div style="line-height: 1.45; margin-bottom: 1px;">'
                    f'<span style="color: #212529;">{html_escape(old_fmt)}</span>'
                    f'<span style="color: #495057;"> → </span>'
                    f'<b style="color: #008784;">{html_escape(new_fmt)}</b>'
                    f' <span style="color: #6c757d; font-style: italic;">({html_escape(field_label)})</span>'
                    f'</div>'
                )

            # 3. If no JSON outputs or inputs were processed, check messages (e.g. TDS_SNAPSHOT)
            if not diff_lines and rec.messages:
                # Parse key amounts from message string
                # e.g. "Eligible Deduction Used: ₹75,000.00 | Taxable Income Used: ₹1,725,000.00 | Annual Tax Used: ₹150,800.00"
                for part in rec.messages.split('|'):
                    if ':' in part:
                        k_str, v_str = part.split(':', 1)
                        k_str = k_str.strip()
                        v_str = v_str.strip()
                        k_low = k_str.lower()
                        if any(term in k_low for term in ['deduction', 'taxable income', 'annual tax', 'tax used', 'approved amount', 'declared amount']):
                            v_float = 0.0
                            if not v_str.startswith('₹'):
                                try:
                                    v_float = float(v_str.replace(',', ''))
                                    v_str = f"₹ {v_float:,.2f}"
                                except (ValueError, TypeError):
                                    pass
                            else:
                                try:
                                    v_float = float(v_str.replace('₹', '').replace(',', '').strip())
                                except (ValueError, TypeError):
                                    v_float = 0.0
                            # Per user request (A2): Hide zero-amount lines so they don't look like fake changes
                            if abs(v_float) < 0.01:
                                continue
                            diff_lines.append(
                                f'<div style="line-height: 1.45; margin-bottom: 1px;">'
                                f'<span style="color: #212529;">₹ 0.00</span>'
                                f'<span style="color: #495057;"> → </span>'
                                f'<b style="color: #008784;">{html_escape(v_str)}</b>'
                                f' <span style="color: #6c757d; font-style: italic;">({html_escape(k_str)})</span>'
                                f'</div>'
                            )

            if diff_lines:
                lines.append(''.join(diff_lines))

            # Warnings / Errors (if any)
            if rec.status == 'error' and rec.messages:
                for m in rec.messages.splitlines():
                    if m.strip() and not diff_lines:
                        lines.append(f'<span style="color:#d32f2f">✕ {html_escape(m.strip())}</span>')

            rec.description_html = ''.join(lines) if lines else ''

    def _format_audit_value(self, key, val):
        """Format a raw audit field value for Odoo Online-style display."""
        k_lower = key.lower()

        if val is None or val is False:
            if any(term in k_lower for term in [
                'wage', 'salary', 'allowance', 'cost', 'bonus', 'hra', 'da',
                'amount', 'deduction', 'contribution', 'benefit', 'decl_', 'prev_',
                'interest', 'income', 'rent', 'loss', 'taxes', 'nav'
            ]):
                return '₹ 0.00'
            elif any(term in k_lower for term in ['percent', 'percentage', 'pct']):
                return '0.00'
            elif any(term in k_lower for term in ['applicable', 'agnipath']):
                return 'No'
            return '—'

        if val is True:
            return 'Yes'

        # 1. Selection and string mappings (e.g. wage_type, salary_calculation_type, regime, resident status)
        if isinstance(val, str):
            val_stripped = val.strip()
            if val_stripped == 'fixed_wage':
                return 'Fixed Wage'
            elif val_stripped == 'hourly_wage':
                return 'Hourly Wage'
            elif val_stripped == 'fixed':
                return 'Fixed Salary (Pro-rated by Attendance)'
            elif val_stripped == 'monthly':
                return 'Monthly'
            elif val_stripped == 'ror':
                return 'Resident & Ordinarily Resident'
            elif val_stripped == 'rnor':
                return 'Resident but Not Ordinarily Resident'
            elif val_stripped == 'nre':
                return 'Non-Resident'
            elif val_stripped == 'new':
                return 'New Tax Regime'
            elif val_stripped == 'old':
                return 'Old Tax Regime'
            elif val_stripped in ('draft', 'declared', 'submitted', 'proof_submitted', 'proof_under_review', 'proof_verified', 'approved', 'rejected'):
                return val_stripped.replace('_', ' ').title()
            elif val_stripped.startswith('₹'):
                return val_stripped
            # Check if string is a numeric value
            try:
                num = float(val_stripped.replace(',', ''))
                if any(term in k_lower for term in ['percent', 'percentage', 'pct']):
                    if num > 1.0:
                        num = num / 100.0
                    return f"{num:.2f}"
                return f"₹ {num:,.2f}"
            except (ValueError, TypeError):
                return val_stripped.replace('_', ' ').title()

        # 2. Percentage fields (e.g. basic_salary_percentage -> 0.50)
        if any(term in k_lower for term in ['percent', 'percentage', 'pct']):
            try:
                num = float(val)
                if num > 1.0:
                    num = num / 100.0
                return f"{num:.2f}"
            except (ValueError, TypeError):
                return str(val)

        # 3. Monetary fields
        if any(term in k_lower for term in [
            'wage', 'salary', 'allowance', 'cost', 'bonus', 'hra', 'da',
            'amount', 'deduction', 'contribution', 'benefit', 'employer',
            'employee_epf', 'employer_epf', 'employee_esic', 'employer_esic',
            'pt', 'lwf', 'charges', 'decl_', 'prev_',
            'interest', 'income', 'rent', 'loss', 'taxes', 'nav'
        ]) or isinstance(val, (float, int)):
            try:
                num = float(val)
                return f"₹ {num:,.2f}"
            except (ValueError, TypeError):
                return str(val)

        if isinstance(val, int):
            return str(val)

        return str(val)

    def action_open_employee(self):
        """
        Open the linked employee profile in the Employee module.
        Called directly when a row in the Audit Trail list is clicked.
        """
        self.ensure_one()
        if not self.employee_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': self.employee_id.name or 'Employee',
            'res_model': 'hr.employee',
            'res_id': self.employee_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }

    def get_formview_action(self, access_uid=None):
        """Fallback for any client calling get_formview_action."""
        return self.action_open_employee()

