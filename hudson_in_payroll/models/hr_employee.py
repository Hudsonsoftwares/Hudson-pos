# -*- coding: utf-8 -*-
import json
import re
# pyrefly: ignore [missing-import]
from markupsafe import Markup
# pyrefly: ignore [missing-import]
from odoo import api, fields, models, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError, UserError


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    _INCOME_TAX_AUDIT_FIELDS = [
        'hds_in_current_tax_regime_id',
        'hds_in_tax_regime',
        'hds_in_tds_applicable',
        'hds_in_is_agnipath',
        'hds_in_residential_status',
        'hds_in_pan',
        'hds_in_aadhaar',
        'hds_in_decl_80ccd2_employer_nps',
        'hds_in_decl_57iia_family_pension',
        'hds_in_prev_taxable_gross',
        'hds_in_prev_tds_deducted',
        'hds_in_prev_pt_deducted',
        'hds_in_prev_employer_pf',
        'hds_in_prev_employer_nps',
        # Income from Other Sources & Let-Out Property
        'hds_in_savings_bank_interest',
        'hds_in_fixed_deposit_interest',
        'hds_in_dividend_income',
        'hds_in_other_sources_income',
        'hds_in_total_other_sources_income',
        'hds_in_annual_let_out_rent',
        'hds_in_municipal_taxes_paid',
        'hds_in_let_out_interest_paid',
        'hds_in_net_house_property_income_loss',
    ]

    registration_number = fields.Char(
        string="Employee Code",
        copy=False,
        help="Configurable internal Employee Code or Registration Number (e.g. EMP001)."
    )
    employee_code = fields.Char(
        string="Employee Code",
        related='registration_number',
        readonly=False,
        store=True,
        help="Configurable Employee Code (alias for registration_number)."
    )

    @api.constrains('registration_number')
    def _check_unique_registration_number(self):
        for emp in self:
            if emp.registration_number:
                domain = [
                    ('registration_number', '=', emp.registration_number),
                    ('id', '!=', emp.id),
                ]
                if emp.company_id:
                    domain.append(('company_id', '=', emp.company_id.id))
                if self.search_count(domain):
                    raise ValidationError(_("The Employee Code '%s' is already assigned to another employee.") % emp.registration_number)

    previous_lta_history_ids = fields.One2many(
        'tds.lta.previous.employer',
        'employee_id',
        string="Previous Employer LTA History",
        help="Historical LTA usage records under previous employers to verify carry-forward entitlement."
    )
    house_property_loss_ids = fields.One2many(
        'tds.house.property.loss.carryforward',
        'employee_id',
        string="House Property Loss Carry-Forward (71B)",
        help="Unabsorbed House Property losses carried forward under Section 71B for inter-year set-off."
    )

    def _default_hds_in_epf_applicable(self):
        company = self.env.company
        return bool(company and getattr(company, 'hds_in_epf_applicable', False))

    # EPF / UAN Information
    hds_in_enable_epf = fields.Boolean(
        string="Company Enables EPF",
        related='company_id.hds_in_epf_applicable',
        readonly=True,
    )
    hds_in_epf_applicable = fields.Boolean(
        string="EPF Applicable",
        default=_default_hds_in_epf_applicable,
        help="Enable EPF statutory deductions for this employee."
    )
    hds_in_uan = fields.Char(
        string="UAN (Universal Account Number)",
        help="12-digit EPFO Universal Account Number."
    )
    hds_in_pf_member_id = fields.Char(
        string="PF Member ID / Member Code",
        help="Establishment Member ID (e.g. MH/BAN/0012345/000/0000123)."
    )
    hds_in_pf_joining_date = fields.Date(
        string="Date of Joining PF",
        help="Date employee first enrolled in Provident Fund."
    )
    hds_in_existing_epf_member = fields.Boolean(
        string="Existing EPF Member",
        default=True,
        help="Check if employee had a prior EPF account before joining this company."
    )
    hds_in_is_international_worker = fields.Boolean(
        string="International Worker",
        default=False,
        help="Check if employee is classified as an International Worker under EPFO rules."
    )

    # EPS (Pension) Information
    hds_in_eps_applicable = fields.Boolean(
        string="EPS Applicable",
        default=True,
        help="Enable EPS statutory pension allocation (8.33%)."
    )

    @api.onchange('hds_in_epf_applicable')
    def _onchange_hds_in_epf_applicable(self):
        for emp in self:
            if not emp.hds_in_epf_applicable:
                emp.hds_in_eps_applicable = False
    hds_in_existing_eps_member = fields.Boolean(
        string="Existing EPS Member",
        default=True,
        help="Check if employee was enrolled in EPS scheme prior to 01-Sep-2014 or current joining."
    )
    hds_in_higher_pension = fields.Boolean(
        string="Opted for Higher Pension Scheme",
        default=False,
        help="Check if employee opted for higher pension scheme under SC judgment guidelines."
    )
    hds_in_pf_contribution_basis = fields.Selection([
        ('statutory_ceiling', 'Statutory Wage Ceiling'),
        ('actual_pf_wage', 'Actual PF Wage (Uncapped)'),
    ], string="Employee PF Contribution Basis", default='statutory_ceiling', required=True)
    hds_in_pf_employer_basis = fields.Selection([
        ('statutory_ceiling', 'Statutory Wage Ceiling'),
        ('actual_pf_wage', 'Actual PF Wage (Uncapped)'),
    ], string="Employer PF Contribution Basis", default='statutory_ceiling', required=True)

    hds_in_pf_wage_info_note = fields.Char(
        string="PF Wage Info Note",
        compute='_compute_hds_in_pf_wage_info',
        help="Informative note regarding PF wage and statutory ceiling calculation."
    )
    hds_in_pf_wage_is_below_ceiling = fields.Boolean(
        string="PF Wage Below Ceiling",
        compute='_compute_hds_in_pf_wage_info'
    )

    @api.depends('hds_in_epf_applicable', 'hds_in_pf_contribution_basis', 'wage', 'basic_salary')
    def _compute_hds_in_pf_wage_info(self):
        for emp in self:
            emp.hds_in_pf_wage_info_note = False
            emp.hds_in_pf_wage_is_below_ceiling = False
            if not emp.hds_in_epf_applicable:
                continue

            contract = False
            if emp.id and isinstance(emp.id, int):
                contract = self.env['hr.version'].search([
                    ('employee_id', '=', emp.id)
                ], order='date_version desc, id desc', limit=1)

            pf_wage = 0.0
            if contract:
                pf_rules = self.env['hr.salary.rule'].search([
                    ('hds_in_include_in_pf_wage', '=', True),
                    ('active', '=', True),
                    ('code', '!=', 'PF_WAGE')
                ])
                code_field_map = {
                    'BASIC': 'basic_salary',
                    'DA': 'da',
                    'HRA': 'hra',
                    'FIXED': 'fixed_allowance',
                    'STANDARD': 'standard_allowance',
                    'PERF': 'performance_bonus',
                    'RET': 'retention_bonus',
                    'LTA': 'lta_allowance',
                    'TRAVEL': 'travel_allowance',
                    'MEAL': 'meal_allowance',
                    'MEDICAL': 'medical_allowance',
                    'OTHER': 'other_allowance',
                }
                for rule in pf_rules:
                    fld = code_field_map.get(rule.code, rule.code.lower())
                    if hasattr(contract, fld):
                        pf_wage += float(getattr(contract, fld, 0.0) or 0.0)

                if pf_wage <= 0.0:
                    pf_wage = float(getattr(contract, 'basic_salary', 0.0) or getattr(contract, 'wage', 0.0) or 0.0)
            elif hasattr(emp, 'basic_salary') and emp.basic_salary:
                pf_wage = float(emp.basic_salary) + float(getattr(emp, 'da', 0.0) or 0.0)
            elif hasattr(emp, 'wage') and emp.wage:
                pf_wage = float(emp.wage)

            pf_ceiling = self.env['hr.rule.parameter'].get_pf_parameter('PF_WAGE_CEILING') or 25000.0
            if 0.0 < pf_wage < pf_ceiling:
                emp.hds_in_pf_wage_is_below_ceiling = True
                pf_deduction = round(pf_wage * 0.12)
                emp.hds_in_pf_wage_info_note = (
                    f"Current PF wage (₹{pf_wage:,.0f}) is below the ₹{pf_ceiling:,.0f} ceiling. "
                    f"Therefore, PF (12%) will only be deducted on the actual wage of ₹{pf_wage:,.0f} (₹{pf_deduction:,.0f}/month)."
                )

    # VPF (Voluntary Provident Fund)
    hds_in_vpf_type = fields.Selection([
        ('none', 'None'),
        ('percent', 'Percentage of Basic Pay'),
        ('fixed', 'Fixed Monthly Amount'),
    ], string="VPF Contribution Type", default='none', required=True)

    hds_in_vpf_percent = fields.Float(
        string="VPF Percentage (%)",
        help="Additional VPF percentage contributed by employee."
    )
    hds_in_vpf_amount = fields.Float(
        string="VPF Fixed Amount (₹)",
        help="Additional VPF fixed amount contributed by employee."
    )

    def _default_hds_in_esic_applicable(self):
        return False

    # ESIC Information
    hds_in_enable_esic = fields.Boolean(
        string="Company Enables ESIC",
        related='company_id.hds_in_esic_applicable',
        readonly=True,
    )
    hds_in_esic_applicable = fields.Boolean(
        string="ESIC Applicable",
        default=False,
        help="Enable Employees' State Insurance (ESIC) statutory compliance for this employee."
    )
    hds_in_esic_ip_number = fields.Char(
        string="ESIC IP Number",
        help="10-digit ESIC Insured Person (IP) Number."
    )
    hds_in_esic_joining_date = fields.Date(
        string="Date of Joining ESIC",
        help="Date of enrollment into ESIC."
    )
    hds_in_esic_exit_date = fields.Date(
        string="Date of Exit ESIC",
        help="Date of exit from ESIC scheme."
    )
    hds_in_esic_ip_status = fields.Selection([
        ('active', 'Active'),
        ('exempt', 'Exempt'),
        ('resigned', 'Resigned'),
        ('disabled', 'Disabled'),
    ], string="Insured Person Status", default='exempt', help="Current ESIC Insured Person (IP) compliance status.")

    hds_in_is_pwd = fields.Boolean(
        string="Person with Disability (PWD)",
        default=False,
        help="Indicates that the employee is eligible for the statutory ESIC PWD wage ceiling limit."
    )

    hds_in_esic_contribution_basis = fields.Char(
        string="Contribution Basis",
        readonly=True,
        default="Gross Wages (Statutory)",
        help="ESIC contribution basis is calculated on gross wages per statutory rules."
    )
    hds_in_esic_contribution_period = fields.Char(
        string="Contribution Period",
        compute='_compute_esic_contribution_period',
        store=False,
        readonly=True,
        help="Half-yearly ESIC statutory contribution period derived automatically from joining date or current date."
    )
    hds_in_esic_dispensary = fields.Char(
        string="ESIC Dispensary",
        help="Nominated ESIC Dispensary / Medical Benefit Hospital."
    )
    hds_in_esic_exit_reason = fields.Selection([
        ('wage_exceeded', 'Salary Exceeded Limit'),
        ('resigned', 'Resigned'),
        ('death', 'Death'),
        ('retired', 'Retired'),
        ('other', 'Other'),
    ], string="Reason for Exit ESIC", help="Reason for exit from ESIC coverage.")

    def _default_hds_in_lwf_applicable(self):
        company = self.env.company
        return bool(company and getattr(company, 'hds_in_enable_lwf', False))

    def _default_hds_in_pt_applicable(self):
        company = self.env.company
        return bool(company and getattr(company, 'hds_in_enable_professional_tax', False))

    # Labour Welfare Fund (LWF) Information
    hds_in_enable_lwf = fields.Boolean(
        string="Company Enables LWF",
        related='company_id.hds_in_enable_lwf',
        readonly=True,
    )
    hds_in_lwf_applicable = fields.Boolean(
        string="LWF Applicable",
        default=_default_hds_in_lwf_applicable,
        help="Enable Labour Welfare Fund (LWF) statutory deductions for this employee."
    )
    hds_in_lwf_number = fields.Char(
        string="LWF Employee / Registration Number",
        help="Labour Welfare Fund Registration or Employee Number."
    )

    # Professional Tax (PT) Information
    hds_in_enable_professional_tax = fields.Boolean(
        string="Company Enables Professional Tax",
        related='company_id.hds_in_enable_professional_tax',
        readonly=True,
    )
    hds_in_pt_applicable = fields.Boolean(
        string="Professional Tax (PT) Applicable",
        default=_default_hds_in_pt_applicable,
        help="Enable Professional Tax (PT) statutory deduction for this employee based on state slab rules."
    )

    @api.onchange('company_id')
    def _onchange_company_id_statutory_applicability(self):
        for emp in self:
            comp = emp.company_id or self.env.company
            if comp:
                if not getattr(comp, 'hds_in_epf_applicable', False):
                    emp.hds_in_epf_applicable = False
                if not getattr(comp, 'hds_in_esic_applicable', False):
                    emp.hds_in_esic_applicable = False
                if not getattr(comp, 'hds_in_enable_lwf', False):
                    emp.hds_in_lwf_applicable = False
                if not getattr(comp, 'hds_in_enable_professional_tax', False):
                    emp.hds_in_pt_applicable = False
                if not getattr(comp, 'hds_in_tds_applicable', False):
                    emp.hds_in_tds_applicable = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            cid = vals.get('company_id')
            company = self.env['res.company'].browse(cid) if cid else self.env.company
            if company:
                if not getattr(company, 'hds_in_epf_applicable', False) and 'hds_in_epf_applicable' not in vals:
                    vals['hds_in_epf_applicable'] = False
                if not getattr(company, 'hds_in_esic_applicable', False) and 'hds_in_esic_applicable' not in vals:
                    vals['hds_in_esic_applicable'] = False
                if not getattr(company, 'hds_in_enable_lwf', False) and 'hds_in_lwf_applicable' not in vals:
                    vals['hds_in_lwf_applicable'] = False
                if not getattr(company, 'hds_in_enable_professional_tax', False) and 'hds_in_pt_applicable' not in vals:
                    vals['hds_in_pt_applicable'] = False
                if not getattr(company, 'hds_in_tds_applicable', False) and 'hds_in_tds_applicable' not in vals:
                    vals['hds_in_tds_applicable'] = False
        return super().create(vals_list)

    @api.constrains('hds_in_epf_applicable', 'hds_in_uan')
    def _check_hds_in_uan_format(self):
        for emp in self:
            if emp.hds_in_epf_applicable and emp.hds_in_uan:
                uan_clean = emp.hds_in_uan.strip()
                if not uan_clean.isdigit():
                    raise ValidationError(_("EPF UAN must contain digits only. Invalid value: '%s'") % emp.hds_in_uan)
                if len(uan_clean) != 12:
                    raise ValidationError(_("EPF UAN must be exactly 12 digits. Provided length: %d digits.") % len(uan_clean))
                duplicate = self.search([
                    ('id', '!=', emp.id),
                    ('hds_in_uan', '=', uan_clean)
                ], limit=1)
                if duplicate:
                    raise ValidationError(_("EPF UAN '%s' is already registered for employee '%s'. Duplicate UANs are prohibited.") % (uan_clean, duplicate.name))

    hds_in_employer_cost_monthly = fields.Monetary(
        string="Employer Cost (Monthly)",
        compute='_compute_hds_in_employer_cost',
        currency_field='currency_id',
        store=True,
        readonly=True,
        help="Monthly Employer Cost to Company (CTC) synced directly from active contract."
    )
    hds_in_employer_cost_annual = fields.Monetary(
        string="Employer Cost (Annual)",
        compute='_compute_hds_in_employer_cost',
        currency_field='currency_id',
        store=True,
        readonly=True,
        help="Annual Employer Cost to Company (CTC) synced directly from active contract."
    )

    hds_in_statutory_audit_count = fields.Integer(
        string="Audit Trail Count",
        compute='_compute_hds_in_statutory_audit_count'
    )



    @api.depends(
        'hds_in_esic_applicable', 'hds_in_is_pwd', 'wage', 'basic_salary',
        'da', 'hra', 'fixed_allowance', 'standard_allowance',
        'contract_date_start', 'date_start', 'date_version', 'hds_in_esic_joining_date'
    )
    def _compute_esic_contribution_period(self):
        today = fields.Date.today()
        from ..services.esic.contribution_period_service import ESICContributionPeriodService
        period_service = ESICContributionPeriodService(self.env)
        for emp in self:
            ref_date = today
            join_date = (
                getattr(emp, 'contract_date_start', None) or
                getattr(emp, 'date_start', None) or
                getattr(emp, 'hds_in_esic_joining_date', None) or
                getattr(emp, 'date_version', None)
            )
            if not join_date and hasattr(emp, 'version_id') and emp.version_id:
                join_date = emp.version_id.date_start or emp.version_id.date_version
            if not join_date:
                emp_id = emp._origin.id if (getattr(emp, '_origin', None) and emp._origin.id and isinstance(emp._origin.id, int)) else (emp.id if isinstance(emp.id, int) else False)
                if emp_id:
                    version = self.env['hr.version'].search([
                        ('employee_id', '=', emp_id)
                    ], order='date_version desc, id desc', limit=1)
                    if version:
                        join_date = getattr(version, 'date_start', None) or getattr(version, 'date_version', None)

            if join_date and join_date > today:
                ref_date = join_date

            comp = emp.company_id or self.env.company
            period_start, period_end = period_service.get_contribution_period_bounds(ref_date, company=comp)
            period_str = f"{period_start.strftime('%B %Y')} – {period_end.strftime('%B %Y')}"
            valid_until = period_end.strftime('%d-%b-%Y')

            gross = emp._get_gross_wage()
            ceiling = 25000.0 if emp.hds_in_is_pwd else 21000.0

            is_covered = period_service.is_covered_for_contribution_period(emp, eval_date=ref_date, current_wage=gross)
            if is_covered:
                if not emp.hds_in_esic_applicable:
                    origin_emp = getattr(emp, '_origin', emp)
                    is_existing = bool(getattr(origin_emp, 'id', False) and isinstance(origin_emp.id, int))
                    if is_existing:
                        emp.hds_in_esic_contribution_period = f"{period_str} — Mandated under Reg. 31 till {valid_until} (Currently Disabled)"
                    else:
                        emp.hds_in_esic_contribution_period = f"{period_str} (Valid until {valid_until})"
                else:
                    emp.hds_in_esic_contribution_period = f"{period_str} (Valid until {valid_until})"
            else:
                if gross > ceiling:
                    emp.hds_in_esic_contribution_period = f"{period_str} — Exempt (Wage ₹{gross:,.0f} > ₹{ceiling:,.0f})"
                elif gross > 0:
                    emp.hds_in_esic_contribution_period = f"{period_str} (Valid until {valid_until})"
                else:
                    emp.hds_in_esic_contribution_period = f"{period_str} — Not Applicable (Exempt)"

    def _get_gross_wage(self):
        """Helper to reliably retrieve gross wage from record, _origin, or contract version."""
        self.ensure_one()
        wage = float(getattr(self, 'wage', 0.0) or 0.0)
        breakdown = float(
            (getattr(self, 'basic_salary', 0.0) or 0.0) + (getattr(self, 'hra', 0.0) or 0.0) +
            (getattr(self, 'da', 0.0) or 0.0) + (getattr(self, 'standard_allowance', 0.0) or 0.0) +
            (getattr(self, 'performance_bonus', 0.0) or 0.0) + (getattr(self, 'retention_bonus', 0.0) or 0.0) +
            (getattr(self, 'lta_allowance', 0.0) or 0.0) + (getattr(self, 'fixed_allowance', 0.0) or 0.0)
        )
        if breakdown > wage:
            wage = breakdown
        if wage <= 0.0:
            origin = getattr(self, '_origin', None)
            if origin:
                orig_wage = float(getattr(origin, 'wage', 0.0) or 0.0)
                orig_bd = float(
                    (getattr(origin, 'basic_salary', 0.0) or 0.0) + (getattr(origin, 'hra', 0.0) or 0.0) +
                    (getattr(origin, 'da', 0.0) or 0.0) + (getattr(origin, 'standard_allowance', 0.0) or 0.0) +
                    (getattr(origin, 'performance_bonus', 0.0) or 0.0) + (getattr(origin, 'retention_bonus', 0.0) or 0.0) +
                    (getattr(origin, 'lta_allowance', 0.0) or 0.0) + (getattr(origin, 'fixed_allowance', 0.0) or 0.0)
                )
                wage = max(orig_wage, orig_bd)
        if wage <= 0.0:
            version = getattr(self, 'version_id', None) or (getattr(self, '_origin', None) and getattr(self._origin, 'version_id', None))
            if version:
                wage = float(getattr(version, 'wage', 0.0) or getattr(version, 'basic_salary', 0.0) or 0.0)
        return float(wage or 0.0)

    def _evaluate_default_esic_applicable(self, gross_wage=None, eval_date=None):
        """
        Evaluates ESIC applicability based on statutory contribution period bounds and period-start wage.
        Enforces Regulation 31 continuity: Gross wage on first day of Contribution Period defines coverage.
        """
        self.ensure_one()
        company = self.company_id or self.env.company
        if not company or not company.hds_in_esic_applicable:
            return False

        from ..services.esic.contribution_period_service import ESICContributionPeriodService
        period_service = ESICContributionPeriodService(self.env)
        wage = gross_wage if gross_wage is not None else self._get_gross_wage()
        return period_service.is_covered_for_contribution_period(self, eval_date=eval_date, current_wage=wage)

    @api.onchange('hds_in_esic_applicable')
    def _onchange_esic_applicable(self):
        """Syncs IP status and exit reason when user manually checks/unchecks ESIC Applicable."""
        for emp in self:
            gross = emp._get_gross_wage()
            ceiling = 25000.0 if emp.hds_in_is_pwd else 21000.0
            if emp.hds_in_esic_applicable:
                if gross <= 0.0:
                    emp.hds_in_esic_applicable = False
                    emp.hds_in_esic_ip_status = 'exempt'
                    emp.hds_in_esic_exit_reason = False
                    return {
                        'warning': {
                            'title': _("ESIC Not Applicable"),
                            'message': _(
                                "ESIC cannot be enabled when employee wage/salary is ₹0.\n\n"
                                "Please define the employee's salary breakdown (Basic, HRA, etc.) first. "
                                "If the gross wage is within statutory limits (₹21,000 / ₹25,000 for PWD), "
                                "ESIC will automatically be enabled."
                            )
                        }
                    }
                is_eligible = emp._evaluate_default_esic_applicable(gross_wage=gross)
                if not is_eligible and gross > ceiling:
                    emp.hds_in_esic_applicable = False
                    emp.hds_in_esic_ip_status = 'exempt'
                    emp.hds_in_esic_exit_reason = 'wage_exceeded'
                    return {
                        'warning': {
                            'title': _("ESIC Not Applicable"),
                            'message': _(
                                "Employee gross wage (₹%s) exceeds the statutory ESIC ceiling of ₹%s per month.\n\n"
                                "Under Indian ESI Regulations, employees earning above ₹21,000 (or ₹25,000 for PWD) "
                                "are exempt and cannot be enrolled in ESIC."
                            ) % (f"{gross:,.2f}", f"{ceiling:,.2f}")
                        }
                    }
                emp.hds_in_esic_ip_status = 'active'
                emp.hds_in_esic_exit_reason = False
            else:
                emp.hds_in_esic_ip_status = 'exempt'
                is_mandated = emp._evaluate_default_esic_applicable(gross_wage=gross)
                if is_mandated:
                    emp.hds_in_esic_exit_reason = 'other'
                    return {
                        'warning': {
                            'title': _("ESIC Statutory Continuity Notice"),
                            'message': _(
                                "Under ESIC Regulation 31, this employee is legally covered until the end of the "
                                "current contribution period because their wage at the start of the period was within the ceiling.\n\n"
                                "If you uncheck ESIC Applicable, statutory ESIC deductions will be bypassed for upcoming payslips."
                            )
                        }
                    }
                elif gross > ceiling:
                    emp.hds_in_esic_exit_reason = 'wage_exceeded'
            emp._sync_and_compute_employer_cost()

    @api.onchange(
        'wage', 'basic_salary', 'da', 'hra', 'fixed_allowance', 'standard_allowance',
        'performance_bonus', 'retention_bonus', 'lta_allowance',
        'contract_date_start', 'date_start', 'date_version', 'hds_in_esic_joining_date',
        'hds_in_is_pwd', 'company_id'
    )
    def _onchange_esic_default_triggers(self):
        """Triggered on employee form when salary, joining date, PWD status or company changes."""
        today = fields.Date.today()
        for emp in self:
            gross = emp._get_gross_wage()
            ceiling = 25000.0 if emp.hds_in_is_pwd else 21000.0
            if gross <= 0.0:
                emp.hds_in_esic_applicable = False
                emp.hds_in_esic_ip_status = 'exempt'
                continue

            join_date = (
                getattr(emp, 'contract_date_start', None) or
                getattr(emp, 'date_start', None) or
                getattr(emp, 'hds_in_esic_joining_date', None) or
                getattr(emp, 'date_version', None)
            )
            ref_date = join_date if (join_date and join_date > today) else today

            is_applicable = emp._evaluate_default_esic_applicable(gross_wage=gross, eval_date=ref_date)
            emp.hds_in_esic_applicable = is_applicable
            if not is_applicable:
                emp.hds_in_esic_ip_status = 'exempt'
                if gross > ceiling:
                    emp.hds_in_esic_exit_reason = 'wage_exceeded'
            else:
                emp.hds_in_esic_ip_status = 'active'
                emp.hds_in_esic_exit_reason = False

    @api.onchange(
        'wage', 'basic_salary', 'da', 'hra', 'fixed_allowance', 'standard_allowance',
        'performance_bonus', 'retention_bonus', 'lta_allowance', 'company_id'
    )
    def _onchange_wage_check_tds_threshold(self):
        """
        Dynamically checks whether the entered salary/wage on the employee profile
        projects an annual taxable salary exceeding the statutory zero-tax threshold
        (Standard Deduction + Section 87A Rebate).
        If threshold is exceeded and TDS is not yet enabled, automatically selects 'Enable TDS'
        and displays an informative advisory warning popup to the payroll administrator.
        """
        for emp in self:
            company = emp.company_id or self.env.company
            if not getattr(company, 'hds_in_tds_applicable', False):
                continue

            # If TDS is already enabled on employee, do not show repeated alert
            if emp.hds_in_tds_applicable:
                continue

            gross = emp._get_gross_wage()
            if gross <= 0.0:
                continue

            annual_gross = gross * 12.0
            eval_date = fields.Date.today()
            if hasattr(emp, 'contract_date_start') and emp.contract_date_start:
                eval_date = emp.contract_date_start
            elif hasattr(emp, 'date_start') and emp.date_start:
                eval_date = emp.date_start

            regime = getattr(emp, 'hds_in_tax_regime', False) or (
                emp.hds_in_current_tax_regime_id.code
                if hasattr(emp, 'hds_in_current_tax_regime_id') and emp.hds_in_current_tax_regime_id
                else False
            )
            if not regime:
                regime = getattr(company, 'hds_in_default_tax_regime', 'new') or 'new'
            regime_code = (regime or 'new').lower()

            # pyrefly: ignore [missing-import]
            from odoo.addons.hudson_in_payroll.services.tds.tds_parameter_service import TdsParameterService
            tds_param_svc = TdsParameterService(self.env)
            std_deduction = tds_param_svc.get_parameter('STD_DEDUCTION', eval_date=eval_date, regime=regime_code) or (
                75000.0 if regime_code == 'new' else 50000.0
            )
            rebate_limit = tds_param_svc.get_parameter('87A_LIMIT', eval_date=eval_date, regime=regime_code) or (
                1200000.0 if regime_code == 'new' else 500000.0
            )

            tax_free_threshold = rebate_limit + std_deduction

            if annual_gross > tax_free_threshold:
                emp.hds_in_tds_applicable = True

                regime_label = _("New Tax Regime (Section 115BAC)") if regime_code == 'new' else _("Old Tax Regime")
                return {
                    'warning': {
                        'title': _("Statutory TDS Notice: Tax Liability Detected"),
                        'message': _(
                            "The entered monthly salary of ₹%(monthly_wage)s (Annual Gross: ₹%(annual_gross)s) "
                            "exceeds the dynamic tax-free threshold of ₹%(threshold)s "
                            "(Standard Deduction: ₹%(std_ded)s + Section 87A Rebate: ₹%(rebate)s under %(regime)s).\n\n"
                            "The 'Enable TDS' option has been automatically selected for this employee to ensure statutory compliance."
                        ) % {
                            'monthly_wage': f"{gross:,.2f}",
                            'annual_gross': f"{annual_gross:,.2f}",
                            'threshold': f"{tax_free_threshold:,.2f}",
                            'std_ded': f"{std_deduction:,.2f}",
                            'rebate': f"{rebate_limit:,.2f}",
                            'regime': regime_label,
                        }
                    }
                }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            wage = vals.get('wage') if 'wage' in vals else vals.get('basic_salary')
            if wage is None or float(wage or 0.0) <= 0.0:
                bd = sum(float(vals.get(k, 0.0) or 0.0) for k in (
                    'basic_salary', 'da', 'hra', 'fixed_allowance', 'standard_allowance',
                    'performance_bonus', 'retention_bonus', 'lta_allowance'
                ))
                if bd > 0:
                    wage = bd
            if wage is not None:
                gross = float(wage or 0.0)
                is_pwd = vals.get('hds_in_is_pwd', False)
                ceiling = 25000.0 if is_pwd else 21000.0
                if gross > ceiling:
                    vals['hds_in_esic_applicable'] = False
                    vals['hds_in_esic_ip_status'] = 'exempt'
                    vals['hds_in_esic_exit_reason'] = 'wage_exceeded'
                elif 0.0 < gross <= ceiling and not vals.get('hds_in_esic_applicable'):
                    vals['hds_in_esic_applicable'] = True
                    vals['hds_in_esic_ip_status'] = 'active'
                    vals['hds_in_esic_exit_reason'] = False
            elif not vals.get('hds_in_esic_applicable'):
                if 'hds_in_esic_ip_status' not in vals:
                    vals['hds_in_esic_ip_status'] = 'exempt'
        return super().create(vals_list)

    def write(self, vals):
        if 'hds_in_residential_status' in vals and 'is_non_resident' not in vals:
            vals['is_non_resident'] = (vals.get('hds_in_residential_status') == 'nre')
        elif 'is_non_resident' in vals and 'hds_in_residential_status' not in vals:
            vals['hds_in_residential_status'] = 'nre' if vals.get('is_non_resident') else 'ror'

        if 'hds_in_esic_applicable' in vals and not vals['hds_in_esic_applicable']:
            if 'hds_in_esic_ip_status' not in vals:
                vals['hds_in_esic_ip_status'] = 'exempt'
        if 'hds_in_esic_applicable' in vals and vals['hds_in_esic_applicable']:
            for emp in self:
                gross = float(vals.get('wage') or getattr(emp, 'wage', 0.0) or vals.get('basic_salary') or getattr(emp, 'basic_salary', 0.0) or 0.0)
                ceiling = 25000.0 if (vals.get('hds_in_is_pwd') if 'hds_in_is_pwd' in vals else emp.hds_in_is_pwd) else 21000.0
                if gross > ceiling and not emp._evaluate_default_esic_applicable(gross_wage=gross):
                    vals['hds_in_esic_applicable'] = False
                    vals['hds_in_esic_ip_status'] = 'exempt'
                    vals['hds_in_esic_exit_reason'] = 'wage_exceeded'
                    break

        # Capture old values for Income Tax (TDS) Profile fields
        tracked_income_tax = [f for f in self._INCOME_TAX_AUDIT_FIELDS if f in vals]
        old_income_tax_state = {}
        if tracked_income_tax and not self.env.context.get('no_tds_audit'):
            for emp in self:
                emp_state = {}
                for f in tracked_income_tax:
                    val = getattr(emp, f, None)
                    if f in ('hds_in_current_tax_regime_id', 'hds_in_tax_regime'):
                        reg = emp.hds_in_current_tax_regime_id
                        emp_state[f] = reg.name if reg else ('New Tax Regime' if emp.hds_in_is_new_tax_regime else 'Old Tax Regime')
                    else:
                        emp_state[f] = val
                old_income_tax_state[emp.id] = emp_state

        res = super().write(vals)

        # Audit Trail & Chatter Logging for Income Tax (TDS) Profile Changes
        if tracked_income_tax and not self.env.context.get('no_tds_audit') and 'hds.in.payroll.audit' in self.env:
            audit_model = self.env['hds.in.payroll.audit']
            for emp in self:
                old_dict = old_income_tax_state.get(emp.id, {})
                old_diff = {}
                new_diff = {}
                for f in tracked_income_tax:
                    old_v = old_dict.get(f)
                    if f in ('hds_in_current_tax_regime_id', 'hds_in_tax_regime'):
                        reg = emp.hds_in_current_tax_regime_id
                        new_v = reg.name if reg else ('New Tax Regime' if emp.hds_in_is_new_tax_regime else 'Old Tax Regime')
                    else:
                        new_v = getattr(emp, f, None)

                    if isinstance(old_v, (int, float)) and isinstance(new_v, (int, float)):
                        if round(float(old_v or 0.0), 2) != round(float(new_v or 0.0), 2):
                            old_diff[f] = float(old_v or 0.0)
                            new_diff[f] = float(new_v or 0.0)
                    elif old_v != new_v:
                        if old_v or new_v:
                            old_diff[f] = old_v
                            new_diff[f] = new_v

                if new_diff:
                    # Avoid duplicate regime logging if both fields were in vals
                    if 'hds_in_current_tax_regime_id' in new_diff and 'hds_in_tax_regime' in new_diff:
                        del new_diff['hds_in_tax_regime']
                        if 'hds_in_tax_regime' in old_diff:
                            del old_diff['hds_in_tax_regime']

                    calc_date = fields.Date.today()
                    audit_model.sudo().create({
                        'employee_id': emp.id,
                        'company_id': emp.company_id.id or self.env.company.id,
                        'user_id': self.env.uid,
                        'statutory_module': 'tds',
                        'rule_code': 'TDS_PROFILE_CHANGE',
                        'calculation_type': 'profile_update',
                        'calculation_date': calc_date,
                        'inputs_json': json.dumps(old_diff, default=str),
                        'outputs_json': json.dumps(new_diff, default=str),
                        'status': 'success',
                    })

                    diff_html_parts = []
                    label_map = {
                        'hds_in_current_tax_regime_id': 'Tax Regime',
                        'hds_in_tax_regime': 'Tax Regime',
                        'hds_in_tds_applicable': 'TDS Applicable',
                        'hds_in_is_agnipath': 'Employee under Agnipath Scheme',
                        'hds_in_residential_status': 'Residential Status',
                        'hds_in_pan': 'PAN',
                        'hds_in_aadhaar': 'Aadhaar Number',
                        'hds_in_decl_80ccd2_employer_nps': 'Employer NPS Contribution (80CCD(2))',
                        'hds_in_decl_57iia_family_pension': 'Family Pension Received (Section 57(iia))',
                        'hds_in_prev_taxable_gross': 'Previous Employer Taxable Salary',
                        'hds_in_prev_tds_deducted': 'Previous Employer TDS Deducted',
                        'hds_in_prev_pt_deducted': 'Previous Employer PT Deducted',
                        'hds_in_prev_employer_pf': 'Previous Employer EPF',
                        'hds_in_prev_employer_nps': 'Previous Employer NPS',
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
                    for k in self._INCOME_TAX_AUDIT_FIELDS:
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
                    if diff_html_parts and hasattr(emp, 'message_post'):
                        today_str = fields.Date.today().strftime('%b %d, %Y').replace(' 0', ' ')
                        chatter_body = (
                            f'<div style="color: #008784; font-weight: bold; margin-bottom: 3px;">'
                            f'→ As of {today_str}</div>'
                            + ''.join(diff_html_parts)
                        )
                        emp.message_post(body=Markup(chatter_body), subtype_xmlid='mail.mt_note')

        if any(k in vals for k in ('wage', 'basic_salary', 'hds_in_is_pwd', 'company_id')):
            for emp in self:
                gross = float(getattr(emp, 'wage', 0.0) or getattr(emp, 'basic_salary', 0.0) or 0.0)
                if gross > 0.0:
                    is_covered = emp._evaluate_default_esic_applicable(gross_wage=gross)
                    ceiling = 25000.0 if emp.hds_in_is_pwd else 21000.0
                    update_vals = {'hds_in_esic_applicable': is_covered}
                    if not is_covered:
                        update_vals['hds_in_esic_ip_status'] = 'exempt'
                        if gross > ceiling:
                            update_vals['hds_in_esic_exit_reason'] = 'wage_exceeded'
                    else:
                        if emp.hds_in_esic_ip_status == 'exempt':
                            update_vals['hds_in_esic_ip_status'] = 'active'
                            update_vals['hds_in_esic_exit_reason'] = False
        if any(k in vals for k in (
            'wage', 'basic_salary', 'da', 'hra', 'fixed_allowance', 'standard_allowance',
            'performance_bonus', 'retention_bonus', 'lta_allowance',
            'hds_in_pf_contribution_basis', 'hds_in_pf_employer_basis',
            'hds_in_epf_applicable', 'hds_in_eps_applicable', 'hds_in_esic_applicable', 'hds_in_lwf_applicable',
            'hds_in_pt_applicable',
            'private_state_id', 'work_location_id', 'address_id', 'company_id',
            'hds_in_is_pwd', 'hds_in_is_international_worker'
        )):
            for emp in self:
                emp._sync_and_compute_employer_cost()
        return res

    @api.onchange(
        'wage', 'basic_salary', 'da', 'hra', 'fixed_allowance', 'standard_allowance',
        'performance_bonus', 'retention_bonus', 'lta_allowance',
        'hds_in_pf_contribution_basis', 'hds_in_pf_employer_basis',
        'hds_in_epf_applicable', 'hds_in_eps_applicable', 'hds_in_esic_applicable', 'hds_in_lwf_applicable',
        'hds_in_pt_applicable',
        'private_state_id', 'work_location_id', 'address_id', 'company_id',
        'hds_in_is_pwd', 'hds_in_is_international_worker'
    )
    def _onchange_ctc_and_statutory_inputs(self):
        """Immediately recomputes Monthly Employer Cost and Annual CTC dynamically on employee form."""
        self._sync_and_compute_employer_cost()

    @api.depends(
        'wage', 'basic_salary', 'da', 'hra', 'fixed_allowance', 'standard_allowance',
        'performance_bonus', 'retention_bonus', 'lta_allowance',
        'hds_in_pf_contribution_basis', 'hds_in_pf_employer_basis',
        'hds_in_epf_applicable', 'hds_in_eps_applicable', 'hds_in_esic_applicable', 'hds_in_lwf_applicable',
        'private_state_id', 'work_location_id', 'address_id', 'company_id',
        'hds_in_is_pwd', 'hds_in_is_international_worker',
        'version_id.hds_in_employer_cost_monthly', 'version_id.hds_in_employer_cost_annual',
        'version_id.wage', 'version_id.basic_salary', 'version_id.da'
    )
    def _compute_hds_in_employer_cost(self):
        for emp in self:
            emp._sync_and_compute_employer_cost()

    def _sync_and_compute_employer_cost(self):
        if self.env.context.get('in_employer_cost_sync'):
            return
        for emp in self.with_context(in_employer_cost_sync=True):
            active_contract = False
            if hasattr(emp, 'version_id') and emp.version_id:
                active_contract = emp.version_id
            elif hasattr(emp, 'version_ids') and emp.version_ids:
                active_contract = emp.version_ids[0]
            else:
                emp_id = emp._origin.id if (hasattr(emp, '_origin') and emp._origin.id and isinstance(emp._origin.id, int)) else (emp.id if isinstance(emp.id, int) else False)
                if emp_id:
                    contracts = self.env['hr.version'].search([('employee_id', '=', emp_id)])
                    active_contract = contracts.sorted(lambda c: c.date_start or fields.Date.today(), reverse=True)[0] if contracts else False

            if active_contract:
                if emp.wage and active_contract.wage != emp.wage:
                    active_contract.wage = emp.wage
                if emp.basic_salary and active_contract.basic_salary != emp.basic_salary:
                    active_contract.basic_salary = emp.basic_salary
                if emp.da and active_contract.da != emp.da:
                    active_contract.da = emp.da
                if hasattr(emp, 'hra') and emp.hra and hasattr(active_contract, 'hra') and active_contract.hra != emp.hra:
                    active_contract.hra = emp.hra
                if hasattr(emp, 'fixed_allowance') and hasattr(active_contract, 'fixed_allowance') and active_contract.fixed_allowance != emp.fixed_allowance:
                    active_contract.fixed_allowance = emp.fixed_allowance
                if hasattr(active_contract, '_compute_breakdown_totals'):
                    active_contract._compute_breakdown_totals()
                if hasattr(active_contract, '_compute_breakdown_percentages'):
                    active_contract._compute_breakdown_percentages()
                active_contract._compute_employer_cost(employee=emp)
                emp.hds_in_employer_cost_monthly = active_contract.hds_in_employer_cost_monthly
                emp.hds_in_employer_cost_annual = active_contract.hds_in_employer_cost_annual
                if hasattr(emp, 'breakdown_total'):
                    emp.breakdown_total = active_contract.breakdown_total
                if hasattr(emp, 'breakdown_diff'):
                    emp.breakdown_diff = active_contract.breakdown_diff
                if hasattr(emp, 'breakdown_is_equal'):
                    emp.breakdown_is_equal = active_contract.breakdown_is_equal
            else:
                gross_wage = float(emp.wage or 0.0)
                breakdown = float(
                    (getattr(emp, 'basic_salary', 0.0) or 0.0) + (getattr(emp, 'hra', 0.0) or 0.0) +
                    (getattr(emp, 'da', 0.0) or 0.0) + (getattr(emp, 'standard_allowance', 0.0) or 0.0) +
                    (getattr(emp, 'performance_bonus', 0.0) or 0.0) + (getattr(emp, 'retention_bonus', 0.0) or 0.0) +
                    (getattr(emp, 'lta_allowance', 0.0) or 0.0) + (getattr(emp, 'fixed_allowance', 0.0) or 0.0)
                )
                if gross_wage <= 0.0 and breakdown > 0.0:
                    gross_wage = breakdown
                elif breakdown > gross_wage > 0.0:
                    gross_wage = breakdown

                basic = float(emp.basic_salary or 0.0)
                if basic <= 0.0 and gross_wage > 0.0:
                    basic = round(gross_wage * 0.50, 2)
                actual_pf_wage = basic + float(emp.da or 0.0)

                employer_contrib = 0.0
                if emp.hds_in_epf_applicable and actual_pf_wage > 0.0:
                    pf_ceiling = self.env['hr.rule.parameter'].get_pf_parameter('PF_WAGE_CEILING') or 25000.0
                    edli_ceiling = self.env['hr.rule.parameter'].get_pf_parameter('EDLI_WAGE_CEILING') or 25000.0
                    if emp.hds_in_pf_employer_basis in ('actual_pf_wage', 'actual_basic'):
                        pf_basis_wage = actual_pf_wage
                    else:
                        pf_basis_wage = min(actual_pf_wage, pf_ceiling)
                    er_pf = round(pf_basis_wage * 0.12, 2)
                    edli = round(min(actual_pf_wage, edli_ceiling) * 0.005, 2)
                    admin = round(pf_basis_wage * 0.005, 2)
                    employer_contrib += (er_pf + edli + admin)

                esic_ceiling = 25000.0 if emp.hds_in_is_pwd else 21000.0
                if emp.hds_in_esic_applicable and 0.0 < gross_wage <= esic_ceiling:
                    employer_contrib += round(gross_wage * 0.0325, 2)

                if emp.hds_in_lwf_applicable and gross_wage > 0.0:
                    company = emp.company_id or self.env.company
                    from ..services.payroll.work_location_service import PayrollWorkLocationService
                    from ..services.lwf.lwf_rate_service import LWFRateService
                    work_state = PayrollWorkLocationService(self.env).get_work_state(emp)
                    rate_cfg = LWFRateService(self.env).get_rate_config(work_state, eval_date=fields.Date.today(), company=company)
                    if rate_cfg:
                        er_contrib = float(rate_cfg.empl_contribution or 0.0)
                        freq = rate_cfg.deduction_frequency or 'monthly'
                        if freq == 'half_yearly':
                            employer_contrib += round((er_contrib * 2.0) / 12.0, 2)
                        elif freq == 'annual':
                            employer_contrib += round(er_contrib / 12.0, 2)
                        else:
                            employer_contrib += er_contrib

                monthly_ctc = round(gross_wage + employer_contrib, 2)
                emp.hds_in_employer_cost_monthly = monthly_ctc
                emp.hds_in_employer_cost_annual = round(monthly_ctc * 12.0, 2)

    @api.onchange(
        'benefit_medical_insurance_per_person',
        'benefit_insured_spouse',
        'benefit_insured_first_child',
        'benefit_insured_second_child'
    )
    def _onchange_medical_insurance_benefits(self):
        rate = float(self.benefit_medical_insurance_per_person or 0.0)
        if rate <= 0.0:
            self.benefit_insured_spouse = False
            self.benefit_insured_first_child = False
            self.benefit_insured_second_child = False
            self.benefit_medical_insurance_amount = 0.0
        else:
            count = 1
            if self.benefit_insured_spouse:
                count += 1
            if self.benefit_insured_first_child:
                count += 1
            if self.benefit_insured_second_child:
                count += 1
            self.benefit_medical_insurance_amount = round(count * rate, 2)

        monthly = round(
            float(getattr(self, 'benefit_phone', 0.0) or 0.0) +
            float(getattr(self, 'benefit_internet', 0.0) or 0.0) +
            float(getattr(self, 'benefit_meal_vouchers', 0.0) or 0.0) +
            float(getattr(self, 'benefit_transport', 0.0) or 0.0) +
            float(self.benefit_medical_insurance_amount or 0.0),
            2
        )
        self.benefit_employer_cost_monthly = monthly
        self.benefit_employer_cost_yearly = round(monthly * 12.0, 2)

    @api.onchange('benefit_phone', 'benefit_internet', 'benefit_meal_vouchers', 'benefit_transport')
    def _onchange_benefit_employer_costs(self):
        monthly = round(
            float(getattr(self, 'benefit_phone', 0.0) or 0.0) +
            float(getattr(self, 'benefit_internet', 0.0) or 0.0) +
            float(getattr(self, 'benefit_meal_vouchers', 0.0) or 0.0) +
            float(getattr(self, 'benefit_transport', 0.0) or 0.0) +
            float(getattr(self, 'benefit_medical_insurance_amount', 0.0) or 0.0),
            2
        )
        self.benefit_employer_cost_monthly = monthly
        self.benefit_employer_cost_yearly = round(monthly * 12.0, 2)

    def _compute_hds_in_statutory_audit_count(self):
        for emp in self:
            emp.hds_in_statutory_audit_count = self.env['hds.in.payroll.audit'].search_count([
                ('employee_id', '=', emp.id)
            ])

    def action_view_statutory_audits(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Audit Trail'),
            'res_model': 'hds.in.payroll.audit',
            'view_mode': 'list',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

    def action_open_tax_declaration_dashboard(self):
        """
        Smart Button Action on Employee Profile ('Tax Declarations').
        Opens the Employee Self-Service Tax Declaration Dashboard for active Financial Year.
        Auto-resolves/creates tds.employee.declaration record for (employee_id, financial_year_id).
        """
        self.ensure_one()
        if not self.hds_in_tds_applicable:
            raise UserError(_("Income Tax (TDS) is not enabled for employee '%s'. Please enable TDS under Payroll & Statutory configuration first.") % (self.name or ''))
        today = fields.Date.today()
        fy = self.company_id.hds_in_default_tax_year or self.env['tds.financial.year'].search([
            ('start_date', '<=', today),
            ('end_date', '>=', today),
            ('active', '=', True),
            ('is_closed', '=', False)
        ], limit=1)

        if not fy:
            raise ValidationError(_("No active Financial Year configuration exists. Please contact HR to set up the Financial Year."))

        # Ensure employee tax regime record exists and is synced with employee's selection
        if self.hds_in_current_tax_regime_id:
            reg_rec = self.env['tds.employee.tax.regime'].sudo().search([
                ('employee_id', '=', self.id),
                ('financial_year_id', '=', fy.id),
            ], limit=1)
            if not reg_rec:
                self.env['tds.employee.tax.regime'].sudo().create({
                    'employee_id': self.id,
                    'financial_year_id': fy.id,
                    'regime_id': self.hds_in_current_tax_regime_id.id,
                })
            elif reg_rec.regime_id != self.hds_in_current_tax_regime_id:
                reg_rec.sudo().write({'regime_id': self.hds_in_current_tax_regime_id.id})

        decl = self.env['tds.employee.declaration'].sudo().search([
            ('employee_id', '=', self.id),
            ('financial_year_id', '=', fy.id)
        ], limit=1)

        if not decl:
            regime = self.hds_in_current_tax_regime_id or self.env['tds.tax.regime'].search([('code', '=', 'new')], limit=1)
            decl = self.env['tds.employee.declaration'].sudo().create({
                'employee_id': self.id,
                'financial_year_id': fy.id,
                'tax_regime_id': regime.id if regime else False,
                'state': 'draft',
            })
        elif self.hds_in_current_tax_regime_id and decl.tax_regime_id != self.hds_in_current_tax_regime_id:
            decl.sudo().write({'tax_regime_id': self.hds_in_current_tax_regime_id.id})

        # Also ensure regime choice and income declaration records exist
        inc_decl = self.env['tds.employee.income.declaration'].sudo().search([
            ('employee_id', '=', self.id),
            ('financial_year_id', '=', fy.id)
        ], limit=1)
        if not inc_decl:
            self.env['tds.employee.income.declaration'].sudo().create({
                'employee_id': self.id,
                'financial_year_id': fy.id,
            })

        view_id = self.env.ref('hudson_in_payroll.tds_employee_declaration_view_dashboard_form', raise_if_not_found=False)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Employee Tax Declaration Dashboard'),
            'res_model': 'tds.employee.declaration',
            'res_id': decl.id,
            'view_mode': 'form',
            'views': [(view_id.id if view_id else False, 'form')],
            'target': 'current',
            'context': {'create': False, 'delete': False, 'edit': True},
        }

    # =========================================================================
    # INCOME TAX (TDS) PROFILE FIELDS
    # =========================================================================
    hds_in_pan = fields.Char(
        string="PAN Number",
        help="10-character Permanent Account Number (e.g. ABCDE1234F)."
    )
    hds_in_aadhaar = fields.Char(
        string="Aadhaar Number",
        help="12-digit Aadhaar Card Number."
    )
    def _default_hds_in_tds_applicable(self):
        company = self.env.company
        return bool(company and getattr(company, 'hds_in_tds_applicable', False))

    hds_in_enable_tds = fields.Boolean(
        string="Company Enables TDS",
        related='company_id.hds_in_tds_applicable',
        readonly=True,
    )
    hds_in_tds_applicable = fields.Boolean(
        string="Enable TDS",
        default=_default_hds_in_tds_applicable,
        help="Enable Indian Income Tax (TDS) withholding computation for this employee."
    )
    hds_in_tds_month_division = fields.Integer(
        string="TDS Month Division",
        compute='_compute_hds_in_tds_month_division',
        store=False,
        readonly=True,
        help="Remaining months in the Financial Year from employee's joining date to Financial Year end."
    )
    hds_in_is_agnipath = fields.Boolean(
        string="Employee under Agnipath Scheme",
        default=False,
        help="Check if the employee is enrolled under the Agnipath Scheme (eligible for Section 80CCH Agniveer Corpus Fund deduction)."
    )

    def _get_employee_joining_date(self):
        """Helper to reliably retrieve employee joining date from contract or explicit joining date fields."""
        self.ensure_one()
        join_date = (
            getattr(self, 'contract_date_start', None) or
            (self.version_id.contract_date_start if hasattr(self, 'version_id') and self.version_id else None) or
            getattr(self, 'hds_in_doj', None) or
            getattr(self, 'hds_in_esic_joining_date', None) or
            getattr(self, 'hds_in_pf_joining_date', None)
        )
        if not join_date:
            emp_id = self._origin.id if (getattr(self, '_origin', None) and self._origin.id and isinstance(self._origin.id, int)) else (self.id if isinstance(self.id, int) else False)
            if emp_id:
                version = self.env['hr.version'].search([
                    ('employee_id', '=', emp_id),
                    ('contract_date_start', '!=', False)
                ], order='contract_date_start asc, id asc', limit=1)
                if version:
                    join_date = version.contract_date_start
        return join_date or False

    @api.depends(
        'company_id',
        'hds_in_tds_applicable',
        'contract_date_start',
        'version_id.contract_date_start',
        'hds_in_esic_joining_date',
        'hds_in_pf_joining_date'
    )
    def _compute_hds_in_tds_month_division(self):
        for emp in self:
            if not emp.hds_in_tds_applicable:
                emp.hds_in_tds_month_division = 0
                continue

            join_date = emp._get_employee_joining_date()
            if not join_date:
                emp.hds_in_tds_month_division = 0
                continue

            company = emp.company_id or self.env.company
            fy = getattr(company, 'hds_in_default_tax_year', None)
            if not fy or not fy.active:
                fy = self.env['tds.financial.year'].search([('active', '=', True)], order='start_date desc', limit=1)

            if not fy or not fy.end_date or not fy.start_date:
                emp.hds_in_tds_month_division = 12
                continue

            # If joined on or before FY start date, standard full year (12)
            if join_date <= fy.start_date:
                emp.hds_in_tds_month_division = 12
            elif join_date > fy.end_date:
                emp.hds_in_tds_month_division = 1
            else:
                # Mid-year joiner: count of months from join_date month to fy.end_date month (inclusive)
                rem_months = (fy.end_date.year - join_date.year) * 12 + (fy.end_date.month - join_date.month) + 1
                emp.hds_in_tds_month_division = max(1, min(12, rem_months))

    @api.onchange('contract_date_start', 'hds_in_tds_applicable', 'hds_in_esic_joining_date', 'hds_in_pf_joining_date')
    def _onchange_contract_date_start_tds(self):
        self._compute_hds_in_tds_month_division()
    hds_in_residential_status = fields.Selection([
        ('ror', 'Resident & Ordinarily Resident (ROR)'),
        ('rnor', 'Resident but Not Ordinarily Resident (RNOR)'),
        ('nre', 'Non-Resident Indian (NRI)'),
    ], string="Residential Status", default='ror', required=True, help="Income Tax Act residential compliance status.")

    resident_status = fields.Selection([
        ('resident', 'Resident'),
        ('non_resident', 'Non-Resident'),
    ], string="Income Tax Resident Status", compute='_compute_resident_status', store=True,
       help="Income Tax residential status computed automatically from Residential Status (ROR/RNOR -> Resident, NRE -> Non-Resident).")

    @api.depends('hds_in_residential_status')
    def _compute_resident_status(self):
        for emp in self:
            if emp.hds_in_residential_status in ('ror', 'rnor'):
                emp.resident_status = 'resident'
            elif emp.hds_in_residential_status == 'nre':
                emp.resident_status = 'non_resident'
            else:
                emp.resident_status = 'resident'

    @api.onchange('hds_in_residential_status')
    def _onchange_hds_in_residential_status(self):
        """Automatically toggle is_non_resident checkbox based on residential status dropdown selection."""
        for emp in self:
            if hasattr(emp, 'is_non_resident'):
                emp.is_non_resident = (emp.hds_in_residential_status == 'nre')

    @api.onchange('is_non_resident')
    def _onchange_is_non_resident(self):
        """Automatically sync residential status dropdown when is_non_resident checkbox is toggled."""
        for emp in self:
            if hasattr(emp, 'is_non_resident'):
                if emp.is_non_resident and emp.hds_in_residential_status != 'nre':
                    emp.hds_in_residential_status = 'nre'
                elif not emp.is_non_resident and emp.hds_in_residential_status == 'nre':
                    emp.hds_in_residential_status = 'ror'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'hds_in_residential_status' in vals and 'is_non_resident' not in vals:
                vals['is_non_resident'] = (vals.get('hds_in_residential_status') == 'nre')
            elif 'is_non_resident' in vals and 'hds_in_residential_status' not in vals:
                vals['hds_in_residential_status'] = 'nre' if vals.get('is_non_resident') else 'ror'
        return super().create(vals_list)

    # Previous Employer Income & TDS (For Mid-Year Joiners)
    hds_in_prev_taxable_gross = fields.Monetary(
        string="Previous Employer Taxable Salary (₹)",
        currency_field='currency_id',
        compute='_compute_current_income_decl',
        inverse='_inverse_current_income_decl',
        store=False,
        help="Gross taxable salary earned from previous employer during current financial year."
    )
    hds_in_prev_tds_deducted = fields.Monetary(
        string="Previous Employer TDS Deducted (₹)",
        currency_field='currency_id',
        compute='_compute_current_income_decl',
        inverse='_inverse_current_income_decl',
        store=False,
        help="Total TDS tax deducted by previous employer during current financial year."
    )
    hds_in_prev_pt_deducted = fields.Monetary(
        string="Previous Employer PT Deducted (₹)",
        currency_field='currency_id',
        compute='_compute_current_income_decl',
        inverse='_inverse_current_income_decl',
        store=False,
        help="Professional Tax deducted by previous employer during current financial year."
    )
    hds_in_prev_employer_pf = fields.Monetary(
        string="Previous Employer EPF (₹)",
        currency_field='currency_id',
        compute='_compute_current_income_decl',
        inverse='_inverse_current_income_decl',
        store=False,
        help="Employer EPF contribution at previous employer during current financial year."
    )
    hds_in_prev_employer_nps = fields.Monetary(
        string="Previous Employer NPS (₹)",
        currency_field='currency_id',
        default=0.0,
        help="Employer NPS contribution at previous employer during current financial year."
    )

    # Tax Regime History One2many
    hds_in_tax_regime_history_ids = fields.One2many(
        'tds.employee.tax.regime',
        'employee_id',
        string="Tax Regime History",
        help="Financial Year specific Tax Regime selections for this employee."
    )

    @api.constrains('hds_in_pan')
    def _check_hds_in_pan_format(self):
        pan_regex = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$')
        for emp in self:
            if emp.hds_in_pan:
                pan_clean = emp.hds_in_pan.strip().upper()
                if not pan_regex.match(pan_clean):
                    raise ValidationError(_(
                        "Invalid PAN Number format: '%s'. "
                        "PAN must be exactly 10 characters formatted as 5 uppercase letters, 4 digits, and 1 uppercase letter (e.g. ABCDE1234F)."
                    ) % emp.hds_in_pan)
                duplicate = self.search([
                    ('id', '!=', emp.id),
                    ('hds_in_pan', '=', pan_clean)
                ], limit=1)
                if duplicate:
                    raise ValidationError(_(
                        "PAN Number '%s' is already registered for employee '%s'. Duplicate PAN numbers are prohibited."
                    ) % (pan_clean, duplicate.name))

    @api.constrains('hds_in_aadhaar')
    def _check_hds_in_aadhaar_format(self):
        for emp in self:
            if emp.hds_in_aadhaar:
                aadhaar_clean = emp.hds_in_aadhaar.strip()
                if not aadhaar_clean.isdigit() or len(aadhaar_clean) != 12:
                    raise ValidationError(_(
                        "Invalid Aadhaar Number: '%s'. Aadhaar must contain exactly 12 digits."
                    ) % emp.hds_in_aadhaar)

    hds_in_tax_regime_count = fields.Integer(
        string="Tax Regime Selections Count",
        compute='_compute_hds_in_tax_regime_count'
    )

    def _compute_hds_in_tax_regime_count(self):
        for emp in self:
            if not emp.hds_in_tds_applicable:
                emp.hds_in_tax_regime_count = 0
            else:
                emp.hds_in_tax_regime_count = self.env['tds.employee.tax.regime'].search_count([
                    ('employee_id', '=', emp.id)
                ])

    def action_view_tax_regimes(self):
        """
        Smart Button Action on Employee Profile ('Tax Regimes').
        Auto-resolves current active Financial Year and opens/creates the tds.employee.tax.regime
        record for (employee_id, financial_year_id), defaulting to system default regime if new.
        """
        self.ensure_one()
        if not self.hds_in_tds_applicable:
            raise UserError(_("Income Tax (TDS) is not enabled for employee '%s'. Please enable TDS under Payroll & Statutory configuration first.") % (self.name or ''))
        today = fields.Date.today()
        fy = self.company_id.hds_in_default_tax_year or self.env['tds.financial.year'].search([
            ('start_date', '<=', today),
            ('end_date', '>=', today),
            ('active', '=', True),
            ('is_closed', '=', False)
        ], limit=1)

        if not fy:
            raise ValidationError(_("No active Financial Year configuration exists. Please configure the default Tax Year in settings."))

        reg_records = self.env['tds.employee.tax.regime'].sudo().search([
            ('employee_id', '=', self.id),
        ])

        active_reg_record = reg_records.filtered(lambda r: r.financial_year_id == fy)

        if not active_reg_record:
            default_regime = self.env['tds.tax.regime'].search([('is_default', '=', True)], limit=1) or self.env['tds.tax.regime'].search([], limit=1)
            active_reg_record = self.env['tds.employee.tax.regime'].sudo().create({
                'employee_id': self.id,
                'financial_year_id': fy.id,
                'regime_id': default_regime.id if default_regime else False,
            })
            reg_records = self.env['tds.employee.tax.regime'].sudo().search([
                ('employee_id', '=', self.id),
            ])

        if len(reg_records) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Financial Year Tax Selection'),
                'res_model': 'tds.employee.tax.regime',
                'res_id': active_reg_record.id,
                'view_mode': 'form',
                'target': 'current',
                'context': {
                    'default_employee_id': self.id,
                    'default_financial_year_id': fy.id,
                }
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Financial Year Tax Selections'),
                'res_model': 'tds.employee.tax.regime',
                'view_mode': 'list,form',
                'domain': [('employee_id', '=', self.id)],
                'target': 'current',
                'context': {
                    'default_employee_id': self.id,
                    'default_financial_year_id': fy.id,
                }
            }

    hds_in_current_fy_id = fields.Many2one(
        'tds.financial.year',
        string="Tax Year",
        compute='_compute_current_fy_regime',
        store=False,
        help="Automatically resolved active Tax Year for current date."
    )
    hds_in_current_tax_regime_id = fields.Many2one(
        'tds.tax.regime',
        string="Selected Tax Regime",
        compute='_compute_current_fy_regime',
        inverse='_inverse_current_tax_regime',
        store=False,
        help="Employee selected Tax Regime for the current Financial Year."
    )
    hds_in_is_new_tax_regime = fields.Boolean(
        string="Is New Tax Regime",
        compute='_compute_current_fy_regime',
        store=False,
        help="Boolean indicator true if employee has selected New Tax Regime for current FY."
    )
    hds_in_tax_regime = fields.Selection(
        selection=[
            ('new', 'New Tax Regime Income-tax Act, 2025 — Section 202(1)'),
            ('old', 'Old Tax Regime'),
        ],
        string="Tax Regime",
        compute='_compute_current_fy_regime',
        inverse='_inverse_hds_in_tax_regime',
        search='_search_hds_in_tax_regime',
        help="Employee selected Tax Regime ('new' or 'old') for the current Financial Year."
    )

    hds_in_company_tax_regime = fields.Selection(
        related='company_id.hds_in_default_tax_regime',
        string="Company Tax Regime Policy",
        readonly=True,
    )
    hds_in_can_choose_regime = fields.Boolean(
        string="Can Choose Regime",
        compute='_compute_hds_in_can_choose_regime',
    )

    @api.depends('company_id.hds_in_default_tax_regime')
    def _compute_hds_in_can_choose_regime(self):
        for emp in self:
            comp = emp.company_id or self.env.company
            emp.hds_in_can_choose_regime = (comp.hds_in_default_tax_regime == 'flexible')

    @api.depends_context('company')
    def _compute_current_fy_regime(self):
        today = fields.Date.today()
        default_fy_fallback = self.env['tds.financial.year'].sudo().search([
            ('start_date', '<=', today),
            ('end_date', '>=', today),
            ('active', '=', True),
            ('is_closed', '=', False)
        ], limit=1)

        valid_emp_ids = [e.id for e in self if e.id]
        fy_map = {}
        reg_map = {}

        if valid_emp_ids:
            for emp in self:
                company = emp.company_id or self.env.company
                fy_map[emp.id] = company.hds_in_default_tax_year or default_fy_fallback

            all_fys = list(set(f.id for f in fy_map.values() if f))
            if all_fys:
                all_regs = self.env['tds.employee.tax.regime'].sudo().search([
                    ('employee_id', 'in', valid_emp_ids),
                    ('financial_year_id', 'in', all_fys)
                ])
                for r in all_regs:
                    reg_map[(r.employee_id.id, r.financial_year_id.id)] = r

        reg_new = self.env['tds.tax.regime'].sudo().search([('code', '=', 'new')], limit=1)
        reg_old = self.env['tds.tax.regime'].sudo().search([('code', '=', 'old')], limit=1)

        for emp in self:
            fy = fy_map.get(emp.id) if emp.id else False
            emp.hds_in_current_fy_id = fy
            company = emp.company_id or self.env.company
            policy = company.hds_in_default_tax_regime or 'new'

            if policy == 'new':
                emp.hds_in_current_tax_regime_id = reg_new
                emp.hds_in_is_new_tax_regime = True
                emp.hds_in_tax_regime = 'new'
            elif policy == 'old':
                emp.hds_in_current_tax_regime_id = reg_old
                emp.hds_in_is_new_tax_regime = False
                emp.hds_in_tax_regime = 'old'
            else:
                # Flexible policy: Respect employee-level selection
                if fy and emp.id:
                    rec = reg_map.get((emp.id, fy.id))
                    reg_id = rec.regime_id if (rec and rec.regime_id) else reg_new
                    emp.hds_in_current_tax_regime_id = reg_id
                    code = reg_id.code if reg_id else 'new'
                    emp.hds_in_is_new_tax_regime = (code == 'new')
                    emp.hds_in_tax_regime = code
                else:
                    emp.hds_in_current_tax_regime_id = reg_new
                    emp.hds_in_is_new_tax_regime = True
                    emp.hds_in_tax_regime = 'new'

    def _inverse_hds_in_tax_regime(self):
        for emp in self:
            if not emp.id or not emp.hds_in_tds_applicable:
                continue
            company = emp.company_id or self.env.company
            policy = company.hds_in_default_tax_regime or 'new'
            if policy in ('new', 'old'):
                raise ValidationError(_(
                    "Company policy mandates the %s Tax Regime for all employees. Individual regime selection cannot be altered."
                ) % ('New' if policy == 'new' else 'Old'))
            if emp.hds_in_tax_regime:
                regime = self.env['tds.tax.regime'].sudo().search([('code', '=', emp.hds_in_tax_regime)], limit=1)
                if regime:
                    emp.hds_in_current_tax_regime_id = regime
                    emp._inverse_current_tax_regime()

    def _search_hds_in_tax_regime(self, operator, value):
        """Search on the computed regime so filters/counts match what each employee shows.

        The regime depends on the company policy ('new' / 'old' / 'flexible') and, for flexible
        companies, the employee's regime record for the current FY (default 'new'). Searching only
        regime records missed employees who are on the default regime, so the matching employees
        are taken from _compute_current_fy_regime itself.
        """
        if operator not in ('=', '!=', 'in', 'not in'):
            return []
        # Odoo may pass a single value or any collection (list, tuple, set, OrderedSet)
        if isinstance(value, str) or not hasattr(value, '__iter__'):
            targets = {value}
        else:
            targets = set(value)
        employees = self.sudo().with_context(active_test=False).search([])
        matched_ids = employees.filtered(lambda emp: emp.hds_in_tax_regime in targets).ids
        if operator in ('=', 'in'):
            return [('id', 'in', matched_ids)]
        return [('id', 'not in', matched_ids)]

    def _inverse_current_tax_regime(self):
        today = fields.Date.today()
        default_fy_fallback = self.env['tds.financial.year'].sudo().search([
            ('start_date', '<=', today),
            ('end_date', '>=', today),
            ('active', '=', True),
            ('is_closed', '=', False)
        ], limit=1)

        for emp in self:
            if not emp.id or not emp.hds_in_tds_applicable:
                continue
            company = emp.company_id or self.env.company
            policy = company.hds_in_default_tax_regime or 'new'
            if policy in ('new', 'old'):
                raise ValidationError(_(
                    "Company policy mandates the %s Tax Regime for all employees. Individual regime selection cannot be altered."
                ) % ('New' if policy == 'new' else 'Old'))

            fy = company.hds_in_default_tax_year or default_fy_fallback
            if not fy:
                raise ValidationError(_("No active Financial Year configuration exists. Please configure Default Tax Year under Payroll Settings or generate the active Financial Year using the Roll-Over Wizard."))

            if emp.hds_in_current_tax_regime_id and emp.id:
                rec = self.env['tds.employee.tax.regime'].sudo().search([
                    ('employee_id', '=', emp.id),
                    ('financial_year_id', '=', fy.id)
                ], limit=1)
                if rec:
                    rec.sudo().write({'regime_id': emp.hds_in_current_tax_regime_id.id})
                else:
                    self.env['tds.employee.tax.regime'].sudo().create({
                        'employee_id': emp.id,
                        'financial_year_id': fy.id,
                        'regime_id': emp.hds_in_current_tax_regime_id.id,
                    })

                # Also sync tax declaration header if it exists
                decl = self.env['tds.employee.declaration'].sudo().search([
                    ('employee_id', '=', emp.id),
                    ('financial_year_id', '=', fy.id)
                ], limit=1)
                if decl:
                    decl.with_context(no_tds_audit=True).sudo().write({'tax_regime_id': emp.hds_in_current_tax_regime_id.id})
                    decl.invalidate_recordset(['regime_choice_id', 'regime_code', 'tax_regime_id'])

    # -------------------------------------------------------------------------
    # ACTIVE TAX DECLARATION LIVE SUMMARY & KPI FIELDS
    # -------------------------------------------------------------------------
    hds_in_current_declaration_id = fields.Many2one(
        'tds.employee.declaration',
        string="Active Tax Declaration",
        compute='_compute_current_tax_declaration_summary',
        store=False,
        help="Active TDS Employee Declaration for the current active Financial Year."
    )
    hds_in_decl_status = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('declared', 'Declared'),
            ('submitted', 'Submitted'),
            ('proof_submitted', 'Proof Submitted'),
            ('proof_under_review', 'Proof Under Review'),
            ('proof_verified', 'Proof Verified'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string="Declaration Status",
        compute='_compute_current_tax_declaration_summary',
        store=False,
    )
    hds_in_decl_total_declared = fields.Monetary(
        string="Total Declared Deductions",
        currency_field='currency_id',
        compute='_compute_current_tax_declaration_summary',
        store=False,
    )
    hds_in_decl_total_approved = fields.Monetary(
        string="Total Approved Deductions",
        currency_field='currency_id',
        compute='_compute_current_tax_declaration_summary',
        store=False,
    )
    hds_in_decl_net_estimated_tax = fields.Monetary(
        string="Net Estimated Annual TDS",
        currency_field='currency_id',
        compute='_compute_current_tax_declaration_summary',
        store=False,
    )
    hds_in_decl_summary_html = fields.Html(
        string="Live Tax Summary Card",
        compute='_compute_current_tax_declaration_summary',
        store=False,
    )

    def _compute_current_tax_declaration_summary(self):
        for emp in self:
            fy = emp.hds_in_current_fy_id
            decl = False
            if fy and emp.id and emp.hds_in_tds_applicable:
                decl = self.env['tds.employee.declaration'].sudo().search([
                    ('employee_id', '=', emp.id),
                    ('financial_year_id', '=', fy.id)
                ], limit=1)

            emp.hds_in_current_declaration_id = decl
            if decl:
                decl._compute_totals()
                emp.hds_in_decl_status = decl.state
                emp.hds_in_decl_total_declared = decl.total_declared_amount
                emp.hds_in_decl_total_approved = decl.total_approved_amount
            else:
                emp.hds_in_decl_status = 'draft'
                emp.hds_in_decl_total_declared = 0.0
                emp.hds_in_decl_total_approved = 0.0

            # Compute Net Estimated Annual TDS
            est_tax = 0.0
            if emp.id and emp.hds_in_tds_applicable:
                try:
                    from ..services.tds.tds_orchestration_engine import TdsOrchestrationEngine
                    engine = TdsOrchestrationEngine(self.env)
                    tds_res = engine.hds_in_compute_tds(emp, eval_date=fields.Date.today())
                    est_tax = float(getattr(tds_res, 'total_annual_tax_liability', 0.0) or 0.0)
                except Exception:
                    est_tax = 0.0
            emp.hds_in_decl_net_estimated_tax = est_tax

            # Generate modern, responsive HTML Live Tax Card
            fy_name = fy.name if fy else "N/A"
            regime_name = emp.hds_in_current_tax_regime_id.name if emp.hds_in_current_tax_regime_id else ("New Tax Regime" if emp.hds_in_is_new_tax_regime else "Old Tax Regime")
            status_val = dict(self._fields['hds_in_decl_status'].selection).get(emp.hds_in_decl_status, 'Draft')

            badge_bg = '#64748b'  # slate
            if emp.hds_in_decl_status == 'approved':
                badge_bg = '#10b981'  # emerald
            elif emp.hds_in_decl_status in ['declared', 'submitted']:
                badge_bg = '#3b82f6'  # blue
            elif emp.hds_in_decl_status in ['proof_submitted', 'proof_under_review', 'proof_verified']:
                badge_bg = '#f59e0b'  # amber
            elif emp.hds_in_decl_status == 'rejected':
                badge_bg = '#ef4444'  # red

            curr = emp.currency_id.symbol or '₹'
            emp.hds_in_decl_summary_html = f"""
            <div style="background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); border: 1px solid #cbd5e1; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
                <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 14px; margin-bottom: 16px;">
                    <div>
                        <span style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 700; color: #64748b;">Statutory Tax Overview</span>
                        <h4 style="margin: 2px 0 0 0; color: #0f172a; font-weight: 700;">{fy_name}</h4>
                    </div>
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <span style="background: #e0e7ff; color: #3730a3; font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 20px;">
                            {regime_name}
                        </span>
                        <span style="background: {badge_bg}; color: #ffffff; font-size: 12px; font-weight: 600; padding: 4px 10px; border-radius: 20px;">
                            Status: {status_val}
                        </span>
                    </div>
                </div>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px;">
                    <div style="background: #ffffff; padding: 14px; border-radius: 8px; border: 1px solid #e2e8f0;">
                        <div style="font-size: 12px; color: #64748b; font-weight: 600;">Total Declared Deductions</div>
                        <div style="font-size: 20px; font-weight: 700; color: #1e293b; margin-top: 4px;">{curr} {emp.hds_in_decl_total_declared:,.2f}</div>
                    </div>
                    <div style="background: #ffffff; padding: 14px; border-radius: 8px; border: 1px solid #e2e8f0;">
                        <div style="font-size: 12px; color: #64748b; font-weight: 600;">Employer NPS (Sec 124)</div>
                        <div style="font-size: 20px; font-weight: 700; color: #0284c7; margin-top: 4px;">{curr} {emp.hds_in_decl_80ccd2_employer_nps:,.2f}</div>
                    </div>
                    <div style="background: #ffffff; padding: 14px; border-radius: 8px; border: 1px solid #e2e8f0;">
                        <div style="font-size: 12px; color: #64748b; font-weight: 600;">Total Approved Deductions</div>
                        <div style="font-size: 20px; font-weight: 700; color: #059669; margin-top: 4px;">{curr} {emp.hds_in_decl_total_approved:,.2f}</div>
                    </div>
                    <div style="background: #ffffff; padding: 14px; border-radius: 8px; border: 1px solid #e2e8f0;">
                        <div style="font-size: 12px; color: #64748b; font-weight: 600;">Net Estimated Annual TDS</div>
                        <div style="font-size: 20px; font-weight: 700; color: #dc2626; margin-top: 4px;">{curr} {emp.hds_in_decl_net_estimated_tax:,.2f}</div>
                    </div>
                </div>
            </div>
            """

    # Section 3: Income Declaration Helper Fields (Mapped to tds.employee.income.declaration)
    hds_in_savings_bank_interest = fields.Monetary(
        string="Savings Account Interest (₹)",
        currency_field='currency_id',
        compute='_compute_current_income_decl',
        inverse='_inverse_current_income_decl',
        store=False,
        help="Annual interest earned on savings bank accounts."
    )
    hds_in_fixed_deposit_interest = fields.Monetary(
        string="Fixed Deposit Interest (₹)",
        currency_field='currency_id',
        compute='_compute_current_income_decl',
        inverse='_inverse_current_income_decl',
        store=False,
        help="Annual interest earned on term deposits."
    )
    hds_in_dividend_income = fields.Monetary(
        string="Dividend Income (₹)",
        currency_field='currency_id',
        compute='_compute_current_income_decl',
        inverse='_inverse_current_income_decl',
        store=False,
        help="Annual taxable dividend income."
    )
    hds_in_other_sources_income = fields.Monetary(
        string="Other Miscellaneous Income (₹)",
        currency_field='currency_id',
        compute='_compute_current_income_decl',
        inverse='_inverse_current_income_decl',
        store=False,
        help="Other taxable income."
    )
    hds_in_total_other_sources_income = fields.Monetary(
        string="Total Other Sources Income (₹)",
        currency_field='currency_id',
        compute='_compute_current_income_decl',
        store=False
    )
    hds_in_annual_let_out_rent = fields.Monetary(
        string="Gross Annual Rent (₹)",
        currency_field='currency_id',
        compute='_compute_current_income_decl',
        inverse='_inverse_current_income_decl',
        store=False
    )
    hds_in_municipal_taxes_paid = fields.Monetary(
        string="Municipal Taxes Paid (₹)",
        currency_field='currency_id',
        compute='_compute_current_income_decl',
        inverse='_inverse_current_income_decl',
        store=False
    )
    hds_in_let_out_interest_paid = fields.Monetary(
        string="Housing Loan Interest (₹)",
        currency_field='currency_id',
        compute='_compute_current_income_decl',
        inverse='_inverse_current_income_decl',
        store=False
    )
    hds_in_net_house_property_income_loss = fields.Monetary(
        string="Net Property Income / Loss (₹)",
        currency_field='currency_id',
        compute='_compute_current_income_decl',
        store=False
    )

    def _compute_current_income_decl(self):
        today = fields.Date.today()
        default_fy_fallback = self.env['tds.financial.year'].sudo().search([
            ('start_date', '<=', today),
            ('end_date', '>=', today),
            ('active', '=', True),
            ('is_closed', '=', False)
        ], limit=1)

        valid_emp_ids = [e.id for e in self if e.id and e.hds_in_tds_applicable]
        fy_map = {}
        decl_map = {}

        if valid_emp_ids:
            for emp in self:
                company = emp.company_id or self.env.company
                fy_map[emp.id] = emp.hds_in_current_fy_id or company.hds_in_default_tax_year or default_fy_fallback

            all_fys = list(set(f.id for f in fy_map.values() if f))
            if all_fys:
                all_decls = self.env['tds.employee.income.declaration'].sudo().search([
                    ('employee_id', 'in', valid_emp_ids),
                    ('financial_year_id', 'in', all_fys)
                ])
                for d in all_decls:
                    decl_map[(d.employee_id.id, d.financial_year_id.id)] = d

        for emp in self:
            fy = fy_map.get(emp.id) if emp.id else False
            if fy and emp.id:
                decl = decl_map.get((emp.id, fy.id))
                if decl:
                    emp.hds_in_savings_bank_interest = decl.savings_bank_interest
                    emp.hds_in_fixed_deposit_interest = decl.fixed_deposit_interest
                    emp.hds_in_dividend_income = decl.dividend_income
                    emp.hds_in_other_sources_income = decl.other_sources_income
                    emp.hds_in_total_other_sources_income = decl.total_other_sources_income
                    emp.hds_in_annual_let_out_rent = decl.annual_let_out_rent
                    emp.hds_in_municipal_taxes_paid = decl.municipal_taxes_paid
                    emp.hds_in_let_out_interest_paid = decl.let_out_interest_paid
                    emp.hds_in_net_house_property_income_loss = decl.net_house_property_income_loss
                    emp.hds_in_prev_taxable_gross = decl.prev_employer_taxable_gross
                    emp.hds_in_prev_tds_deducted = decl.prev_employer_tds
                    emp.hds_in_prev_pt_deducted = decl.prev_employer_pt
                    emp.hds_in_prev_employer_pf = decl.prev_employer_pf
                else:
                    emp.hds_in_savings_bank_interest = 0.0
                    emp.hds_in_fixed_deposit_interest = 0.0
                    emp.hds_in_dividend_income = 0.0
                    emp.hds_in_other_sources_income = 0.0
                    emp.hds_in_total_other_sources_income = 0.0
                    emp.hds_in_annual_let_out_rent = 0.0
                    emp.hds_in_municipal_taxes_paid = 0.0
                    emp.hds_in_let_out_interest_paid = 0.0
                    emp.hds_in_net_house_property_income_loss = 0.0
                    emp.hds_in_prev_taxable_gross = 0.0
                    emp.hds_in_prev_tds_deducted = 0.0
                    emp.hds_in_prev_pt_deducted = 0.0
                    emp.hds_in_prev_employer_pf = 0.0
            else:
                emp.hds_in_savings_bank_interest = 0.0
                emp.hds_in_fixed_deposit_interest = 0.0
                emp.hds_in_dividend_income = 0.0
                emp.hds_in_other_sources_income = 0.0
                emp.hds_in_total_other_sources_income = 0.0
                emp.hds_in_annual_let_out_rent = 0.0
                emp.hds_in_municipal_taxes_paid = 0.0
                emp.hds_in_let_out_interest_paid = 0.0
                emp.hds_in_net_house_property_income_loss = 0.0
                emp.hds_in_prev_taxable_gross = 0.0
                emp.hds_in_prev_tds_deducted = 0.0
                emp.hds_in_prev_pt_deducted = 0.0
                emp.hds_in_prev_employer_pf = 0.0

    def _inverse_current_income_decl(self):
        today = fields.Date.today()
        default_fy_fallback = self.env['tds.financial.year'].sudo().search([
            ('start_date', '<=', today),
            ('end_date', '>=', today),
            ('active', '=', True),
            ('is_closed', '=', False)
        ], limit=1)

        income_fields_map = {
            'hds_in_savings_bank_interest': 'savings_bank_interest',
            'hds_in_fixed_deposit_interest': 'fixed_deposit_interest',
            'hds_in_dividend_income': 'dividend_income',
            'hds_in_other_sources_income': 'other_sources_income',
            'hds_in_annual_let_out_rent': 'annual_let_out_rent',
            'hds_in_municipal_taxes_paid': 'municipal_taxes_paid',
            'hds_in_let_out_interest_paid': 'let_out_interest_paid',
            'hds_in_prev_taxable_gross': 'prev_employer_taxable_gross',
            'hds_in_prev_tds_deducted': 'prev_employer_tds',
            'hds_in_prev_pt_deducted': 'prev_employer_pt',
            'hds_in_prev_employer_pf': 'prev_employer_pf',
        }

        for emp in self:
            if not emp.id or not emp.hds_in_tds_applicable:
                continue
            company = emp.company_id or self.env.company
            fy = emp.hds_in_current_fy_id or company.hds_in_default_tax_year or default_fy_fallback
            if not fy:
                continue

            decl = self.env['tds.employee.income.declaration'].sudo().search([
                ('employee_id', '=', emp.id),
                ('financial_year_id', '=', fy.id)
            ], limit=1)
            if not decl:
                decl = self.env['tds.employee.income.declaration'].sudo().create({
                    'employee_id': emp.id,
                    'financial_year_id': fy.id,
                })

            vals = {}
            for emp_f, decl_f in income_fields_map.items():
                val = getattr(emp, emp_f, None)
                decl_val = float(getattr(decl, decl_f, 0.0) or 0.0)
                float_val = float(val or 0.0) if (val is not False and val is not None) else 0.0
                if abs(float_val - decl_val) > 0.001:
                    vals[decl_f] = float_val
            if vals:
                decl.sudo().with_context(no_tds_audit=True).write(vals)

    # -------------------------------------------------------------------------
    # SECTION 4: DEDUCTION DECLARATION HELPER FIELDS (Old Regime Only)
    # -------------------------------------------------------------------------
    # Group A: Investments (Chapter VI-A / Section 80C)
    hds_in_decl_80c_ppf = fields.Monetary(string="PPF Contribution (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_80c_elss = fields.Monetary(string="ELSS Mutual Funds (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_80c_epf = fields.Monetary(string="Voluntary EPF (VPF) (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_80c_lic = fields.Monetary(string="Life Insurance Premium (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_80c_nsc = fields.Monetary(string="National Savings Certificate (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_80c_ssy = fields.Monetary(string="Sukanya Samriddhi Yojana (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_80c_fd = fields.Monetary(string="Tax Saving FD (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_80c_tuition = fields.Monetary(string="Children Tuition Fees (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_80c_housing_principal = fields.Monetary(string="Housing Loan Principal (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_80c_other = fields.Monetary(string="Other 80C Investments (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_80c_total = fields.Monetary(string="Total Declared Section 80C (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', store=False)

    # Group B: National Pension Scheme (Section 80CCD(1B))
    hds_in_decl_80ccd1b_nps = fields.Monetary(string="Employee NPS Contribution 80CCD(1B) (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)

    # Group C: Medical Insurance (Section 80D)
    hds_in_decl_80d_self = fields.Monetary(string="Medical Insurance (Self/Family) (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_80d_parents = fields.Monetary(string="Medical Insurance (Parents) (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_80d_parents_is_senior = fields.Boolean(string="Parents are Senior Citizens (Age ≥ 60 years)", compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False, help="Check if parents are Senior Citizens (Age 60+), unlocking higher ₹50,000 Section 80D ceiling.")
    hds_in_decl_80d_preventive = fields.Monetary(string="Preventive Health Check-up (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)


    # Group D: House Rent Allowance (HRA)
    hds_in_decl_hra_annual_rent = fields.Monetary(string="Annual Rent Paid (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_hra_landlord_name = fields.Char(string="Landlord Name", compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_hra_landlord_pan = fields.Char(string="Landlord PAN", compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_hra_is_metro = fields.Boolean(string="Accommodation in Metro City", compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_hra_own_residential_property_at_workplace = fields.Boolean(string="Own Property at Workplace", compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_hra_rent_period_from = fields.Date(string="Rent Period From", compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_hra_rent_period_to = fields.Date(string="Rent Period To", compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)

    # Group E: Home Loan Interest (Section 24(b))
    hds_in_decl_24b_self_interest = fields.Monetary(string="Self-Occupied Home Loan Interest (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)

    # Group F: Savings Interest (Section 80TTA / 80TTB)
    hds_in_decl_80tta_interest = fields.Monetary(string="Savings Interest 80TTA (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_80ttb_interest = fields.Monetary(string="Senior Citizen Interest 80TTB (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)

    # Group G: Disability Deductions (Section 80DD)
    hds_in_decl_80dd_amount = fields.Monetary(string="Dependent Disability 80DD (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)
    hds_in_decl_80dd_is_severe = fields.Boolean(string="Severe Disability (Disability ≥ 80%)", compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False, help="Check if dependent disability is 80% or higher, unlocking ₹1,25,000 Section 80DD ceiling.")


    # Group H: Other Eligible Deductions
    hds_in_decl_other_amount = fields.Monetary(string="Other Eligible Deductions (₹)", currency_field='currency_id', compute='_compute_current_deduction_decl', inverse='_inverse_current_deduction_decl', store=False)

    # -------------------------------------------------------------------------
    # CATEGORY C: NEW REGIME & BOTH REGIMES SUPPORTED DEDUCTIONS
    # -------------------------------------------------------------------------
    hds_in_decl_80ccd2_employer_nps = fields.Monetary(
        string="Employer NPS Contribution — Section 124 (₹)",
        currency_field='currency_id',
        compute='_compute_current_deduction_decl',
        inverse='_inverse_current_deduction_decl',
        store=False,
        help="Employer contribution under Section 124 (formerly Section 80CCD(2)) (up to 14%/10% of Basic + DA, permitted under BOTH Old and New Regimes)."
    )
    hds_in_decl_57iia_family_pension = fields.Monetary(
        string="Family Pension Received (annual) — Section 93(1)(d) (₹)",
        currency_field='currency_id',
        compute='_compute_current_deduction_decl',
        inverse='_inverse_current_deduction_decl',
        store=False,
        help="Family Pension received under Section 93(1)(d) / Section 57(iia) (Income from Other Sources). Standard deduction: min(1/3rd of family pension, ₹25,000)."
    )
    hds_in_decl_80cch_agniveer = fields.Monetary(
        string="Agniveer Corpus Fund 80CCH (₹)",
        currency_field='currency_id',
        compute='_compute_current_deduction_decl',
        inverse='_inverse_current_deduction_decl',
        store=False,
        help="Agniveer Corpus Fund deduction under Section 80CCH (permitted under BOTH Old and New Regimes)."
    )

    # Section 6: Supporting Proof Documents
    hds_in_tax_attachment_ids = fields.Many2many(
        'ir.attachment',
        'hr_employee_tax_ir_attachment_rel',
        'employee_id',
        'attachment_id',
        string="Tax Supporting Proof Documents",
        help="Upload LIC receipts, PPF statements, rent receipts, medical insurance receipts, and home loan certificates."
    )

    def _compute_current_deduction_decl(self):
        today = fields.Date.today()
        default_fy_fallback = self.env['tds.financial.year'].sudo().search([
            ('start_date', '<=', today),
            ('end_date', '>=', today),
            ('active', '=', True),
            ('is_closed', '=', False)
        ], limit=1)

        valid_emp_ids = [e.id for e in self if e.id and e.hds_in_tds_applicable]
        fy_map = {}
        decl_map = {}

        if valid_emp_ids:
            for emp in self:
                company = emp.company_id or self.env.company
                fy_map[emp.id] = emp.hds_in_current_fy_id or company.hds_in_default_tax_year or default_fy_fallback

            all_fys = list(set(f.id for f in fy_map.values() if f))
            if all_fys:
                all_decls = self.env['tds.employee.declaration'].sudo().search([
                    ('employee_id', 'in', valid_emp_ids),
                    ('financial_year_id', 'in', all_fys)
                ])
                for d in all_decls:
                    decl_map[(d.employee_id.id, d.financial_year_id.id)] = d

        for emp in self:
            # Default zero values
            emp.hds_in_decl_80c_ppf = 0.0
            emp.hds_in_decl_80c_elss = 0.0
            emp.hds_in_decl_80c_epf = 0.0
            emp.hds_in_decl_80c_lic = 0.0
            emp.hds_in_decl_80c_nsc = 0.0
            emp.hds_in_decl_80c_ssy = 0.0
            emp.hds_in_decl_80c_fd = 0.0
            emp.hds_in_decl_80c_tuition = 0.0
            emp.hds_in_decl_80c_housing_principal = 0.0
            emp.hds_in_decl_80c_other = 0.0
            emp.hds_in_decl_80c_total = 0.0
            emp.hds_in_decl_80ccd1b_nps = 0.0
            emp.hds_in_decl_80d_self = 0.0
            emp.hds_in_decl_80d_parents = 0.0
            emp.hds_in_decl_80d_parents_is_senior = False
            emp.hds_in_decl_80d_preventive = 0.0

            emp.hds_in_decl_hra_annual_rent = 0.0
            emp.hds_in_decl_hra_landlord_name = False
            emp.hds_in_decl_hra_landlord_pan = False
            emp.hds_in_decl_hra_is_metro = False
            emp.hds_in_decl_hra_own_residential_property_at_workplace = False
            emp.hds_in_decl_hra_rent_period_from = False
            emp.hds_in_decl_hra_rent_period_to = False
            emp.hds_in_decl_24b_self_interest = 0.0
            emp.hds_in_decl_80tta_interest = 0.0
            emp.hds_in_decl_80ttb_interest = 0.0
            emp.hds_in_decl_80dd_amount = 0.0
            emp.hds_in_decl_80dd_is_severe = False
            emp.hds_in_decl_other_amount = 0.0

            emp.hds_in_decl_80ccd2_employer_nps = 0.0
            emp.hds_in_decl_57iia_family_pension = 0.0
            emp.hds_in_decl_80cch_agniveer = 0.0

            fy = fy_map.get(emp.id) if emp.id else False
            if fy and emp.id:
                decl = decl_map.get((emp.id, fy.id))
                if decl:
                    for line in decl.declaration_line_ids:
                        cat = line.category
                        amt = line.declared_amount
                        desc = (line.description or '').lower()
                        if cat == '80c':
                            if desc in ['section 80c', 'section 80c (ppf, elss, lic, tuition fee, epf)', '80c investments', 'section 80c investment']:
                                continue
                            if 'ppf' in desc or 'public provident' in desc: emp.hds_in_decl_80c_ppf += amt
                            elif 'elss' in desc or 'mutual fund' in desc: emp.hds_in_decl_80c_elss += amt
                            elif 'vpf' in desc or 'voluntary epf' in desc or 'voluntary pf' in desc or ('epf' in desc and 'ppf' not in desc): emp.hds_in_decl_80c_epf += amt
                            elif 'lic' in desc or 'life insurance' in desc or 'life premium' in desc: emp.hds_in_decl_80c_lic += amt
                            elif 'nsc' in desc or 'national savings' in desc: emp.hds_in_decl_80c_nsc += amt
                            elif 'sukanya' in desc or 'ssy' in desc: emp.hds_in_decl_80c_ssy += amt
                            elif 'fixed deposit' in desc or 'tax saving fd' in desc or ' 5 year' in desc or ' 5-year' in desc or desc == 'fd' or desc.endswith(' fd'): emp.hds_in_decl_80c_fd += amt
                            elif 'tuition' in desc or 'school fee' in desc or 'children tuition' in desc: emp.hds_in_decl_80c_tuition += amt
                            elif 'housing' in desc or 'principal' in desc or 'home loan principal' in desc: emp.hds_in_decl_80c_housing_principal += amt
                            elif 'other 80c' in desc or 'other investment' in desc or 'other specified' in desc: emp.hds_in_decl_80c_other += amt
                            else: emp.hds_in_decl_80c_other += amt
                        elif cat == '80ccd1b': emp.hds_in_decl_80ccd1b_nps += amt
                        elif cat == '80d_self': emp.hds_in_decl_80d_self += amt
                        elif cat == '80d_parents':
                            emp.hds_in_decl_80d_parents += amt
                            if line.is_senior_citizen:
                                emp.hds_in_decl_80d_parents_is_senior = True
                        elif cat == '80d_preventive': emp.hds_in_decl_80d_preventive += amt
                        elif cat == 'hra':
                            emp.hds_in_decl_hra_annual_rent += amt
                            landlord_name = getattr(line.declaration_id, 'decl_hra_landlord_name', False) or getattr(line, 'landlord_name', False)
                            landlord_pan = getattr(line.declaration_id, 'decl_hra_landlord_pan', False) or getattr(line, 'landlord_pan', False)
                            is_metro = getattr(line.declaration_id, 'decl_hra_is_metro', False) or getattr(line, 'is_metro', False)
                            own_prop = getattr(line.declaration_id, 'decl_hra_own_residential_property_at_workplace', False) or getattr(line, 'own_residential_property_at_workplace', False)
                            r_from = getattr(line.declaration_id, 'decl_hra_rent_period_from', False) or getattr(line, 'rent_period_from', False)
                            r_to = getattr(line.declaration_id, 'decl_hra_rent_period_to', False) or getattr(line, 'rent_period_to', False)
                            if landlord_name: emp.hds_in_decl_hra_landlord_name = landlord_name
                            if landlord_pan: emp.hds_in_decl_hra_landlord_pan = landlord_pan
                            emp.hds_in_decl_hra_is_metro = is_metro
                            emp.hds_in_decl_hra_own_residential_property_at_workplace = own_prop
                            emp.hds_in_decl_hra_rent_period_from = r_from
                            emp.hds_in_decl_hra_rent_period_to = r_to
                        elif cat == '24b': emp.hds_in_decl_24b_self_interest += amt
                        elif cat == '80tta': emp.hds_in_decl_80tta_interest += amt
                        elif cat == '80ttb': emp.hds_in_decl_80ttb_interest += amt
                        elif cat == '80dd':
                            emp.hds_in_decl_80dd_amount += amt
                            if line.is_severe_disability:
                                emp.hds_in_decl_80dd_is_severe = True
                        elif cat == 'other': emp.hds_in_decl_other_amount += amt
                        elif cat == '80ccd2': pass
                        elif cat == '57iia': emp.hds_in_decl_57iia_family_pension += amt
                        elif cat == '80cch': emp.hds_in_decl_80cch_agniveer += amt

                    # Employer NPS Contribution is read directly from declaration header
                    emp.hds_in_decl_80ccd2_employer_nps = float(decl.decl_80ccd2_employer_nps or 0.0) if decl else 0.0
                    if not emp.hds_in_decl_57iia_family_pension and decl.decl_57iia_family_pension:
                        emp.hds_in_decl_57iia_family_pension = decl.decl_57iia_family_pension
                    if not emp.hds_in_decl_80cch_agniveer and decl.decl_80cch_agniveer:
                        emp.hds_in_decl_80cch_agniveer = decl.decl_80cch_agniveer

                    if not (decl.regime_code == 'new' or emp.hds_in_is_new_tax_regime):
                        if not emp.hds_in_decl_hra_annual_rent and decl.decl_hra_annual_rent:
                            emp.hds_in_decl_hra_annual_rent = decl.decl_hra_annual_rent
                        if decl.decl_hra_landlord_name and not emp.hds_in_decl_hra_landlord_name: emp.hds_in_decl_hra_landlord_name = decl.decl_hra_landlord_name
                        if decl.decl_hra_landlord_pan and not emp.hds_in_decl_hra_landlord_pan: emp.hds_in_decl_hra_landlord_pan = decl.decl_hra_landlord_pan
                        if decl.decl_hra_is_metro: emp.hds_in_decl_hra_is_metro = bool(decl.decl_hra_is_metro)
                        if decl.decl_hra_own_residential_property_at_workplace: emp.hds_in_decl_hra_own_residential_property_at_workplace = bool(decl.decl_hra_own_residential_property_at_workplace)
                        if decl.decl_hra_rent_period_from: emp.hds_in_decl_hra_rent_period_from = decl.decl_hra_rent_period_from
                        if decl.decl_hra_rent_period_to: emp.hds_in_decl_hra_rent_period_to = decl.decl_hra_rent_period_to

                        if not emp.hds_in_decl_24b_self_interest and decl.decl_24b_self_interest:
                            emp.hds_in_decl_24b_self_interest = decl.decl_24b_self_interest
                        if not emp.hds_in_decl_80tta_interest and decl.decl_80tta_interest:
                            emp.hds_in_decl_80tta_interest = decl.decl_80tta_interest
                        if not emp.hds_in_decl_80ttb_interest and decl.decl_80ttb_interest:
                            emp.hds_in_decl_80ttb_interest = decl.decl_80ttb_interest
                        if not emp.hds_in_decl_80dd_amount and (decl.decl_80dd_amount or decl.decl_80dd_expenditure_amount):
                            emp.hds_in_decl_80dd_amount = decl.decl_80dd_amount or decl.decl_80dd_expenditure_amount
                        if decl.decl_80dd_is_severe_disability:
                            emp.hds_in_decl_80dd_is_severe = True
                        if decl.decl_80d_parents_is_senior:
                            emp.hds_in_decl_80d_parents_is_senior = True

            emp.hds_in_decl_80c_total = (
                emp.hds_in_decl_80c_ppf + emp.hds_in_decl_80c_elss + emp.hds_in_decl_80c_epf +
                emp.hds_in_decl_80c_lic + emp.hds_in_decl_80c_nsc + emp.hds_in_decl_80c_ssy +
                emp.hds_in_decl_80c_fd + emp.hds_in_decl_80c_tuition +
                emp.hds_in_decl_80c_housing_principal + emp.hds_in_decl_80c_other
            )

    def _inverse_current_deduction_decl(self):
        today = fields.Date.today()
        default_fy_fallback = self.env['tds.financial.year'].sudo().search([
            ('start_date', '<=', today),
            ('end_date', '>=', today),
            ('active', '=', True),
            ('is_closed', '=', False)
        ], limit=1)

        for emp in self:
            if not emp.id or not emp.hds_in_tds_applicable:
                continue
            company = emp.company_id or self.env.company
            fy = emp.hds_in_current_fy_id or company.hds_in_default_tax_year or default_fy_fallback
            if not fy:
                continue

            decl = self.env['tds.employee.declaration'].sudo().search([
                ('employee_id', '=', emp.id),
                ('financial_year_id', '=', fy.id)
            ], limit=1)
            if not decl:
                decl = self.env['tds.employee.declaration'].sudo().create({
                    'employee_id': emp.id,
                    'financial_year_id': fy.id,
                })

            is_new = (decl.regime_code == 'new' or emp.hds_in_is_new_tax_regime)

            # Category C items (Allowed under BOTH Regimes)
            decl_vals = {
                'decl_80ccd2_employer_nps': float(emp.hds_in_decl_80ccd2_employer_nps or 0.0),
                'decl_57iia_family_pension': float(emp.hds_in_decl_57iia_family_pension or 0.0),
                'decl_80cch_agniveer': float(emp.hds_in_decl_80cch_agniveer or 0.0),
            }

            if not is_new:
                decl_vals.update({
                    'decl_80c_ppf': float(emp.hds_in_decl_80c_ppf or 0.0),
                    'decl_80c_elss': float(emp.hds_in_decl_80c_elss or 0.0),
                    'decl_80c_epf': float(emp.hds_in_decl_80c_epf or 0.0),
                    'decl_80c_lic': float(emp.hds_in_decl_80c_lic or 0.0),
                    'decl_80c_nsc': float(emp.hds_in_decl_80c_nsc or 0.0),
                    'decl_80c_ssy': float(emp.hds_in_decl_80c_ssy or 0.0),
                    'decl_80c_fd': float(emp.hds_in_decl_80c_fd or 0.0),
                    'decl_80c_tuition': float(emp.hds_in_decl_80c_tuition or 0.0),
                    'decl_80c_housing_principal': float(emp.hds_in_decl_80c_housing_principal or 0.0),
                    'decl_80c_other': float(emp.hds_in_decl_80c_other or 0.0),
                    'decl_80ccd1b_nps': float(emp.hds_in_decl_80ccd1b_nps or 0.0),
                    'decl_80d_self': float(emp.hds_in_decl_80d_self or 0.0),
                    'decl_80d_parents': float(emp.hds_in_decl_80d_parents or 0.0),
                    'decl_80d_parents_is_senior': bool(emp.hds_in_decl_80d_parents_is_senior),
                    'decl_80d_preventive': float(emp.hds_in_decl_80d_preventive or 0.0),
                    'decl_hra_annual_rent': float(emp.hds_in_decl_hra_annual_rent or 0.0),
                    'decl_hra_landlord_name': emp.hds_in_decl_hra_landlord_name or False,
                    'decl_hra_landlord_pan': emp.hds_in_decl_hra_landlord_pan or False,
                    'decl_hra_is_metro': bool(emp.hds_in_decl_hra_is_metro),
                    'decl_hra_own_residential_property_at_workplace': bool(emp.hds_in_decl_hra_own_residential_property_at_workplace),
                    'decl_hra_rent_period_from': emp.hds_in_decl_hra_rent_period_from or False,
                    'decl_hra_rent_period_to': emp.hds_in_decl_hra_rent_period_to or False,
                    'decl_24b_self_interest': float(emp.hds_in_decl_24b_self_interest or 0.0),
                    'decl_80tta_interest': float(emp.hds_in_decl_80tta_interest or 0.0),
                    'decl_80ttb_interest': float(emp.hds_in_decl_80ttb_interest or 0.0),
                    'decl_80dd_amount': float(emp.hds_in_decl_80dd_amount or 0.0),
                    'decl_80dd_expenditure_amount': float(emp.hds_in_decl_80dd_amount or 0.0),
                    'decl_80dd_is_severe_disability': bool(emp.hds_in_decl_80dd_is_severe),
                })
            else:
                decl_vals.update({
                    'decl_80c_ppf': 0.0, 'decl_80c_elss': 0.0, 'decl_80c_epf': 0.0, 'decl_80c_lic': 0.0,
                    'decl_80c_nsc': 0.0, 'decl_80c_ssy': 0.0, 'decl_80c_fd': 0.0, 'decl_80c_tuition': 0.0,
                    'decl_80c_housing_principal': 0.0, 'decl_80c_other': 0.0, 'decl_80ccd1b_nps': 0.0,
                    'decl_80d_self': 0.0, 'decl_80d_parents': 0.0, 'decl_80d_parents_is_senior': False,
                    'decl_80d_preventive': 0.0, 'decl_hra_annual_rent': 0.0, 'decl_hra_landlord_name': False,
                    'decl_hra_landlord_pan': False, 'decl_hra_is_metro': False,
                    'decl_hra_own_residential_property_at_workplace': False,
                    'decl_hra_rent_period_from': False, 'decl_hra_rent_period_to': False,
                    'decl_24b_self_interest': 0.0, 'decl_80tta_interest': 0.0, 'decl_80ttb_interest': 0.0,
                    'decl_80dd_amount': 0.0, 'decl_80dd_expenditure_amount': 0.0, 'decl_80dd_is_severe_disability': False,
                })

            decl.sudo().with_context(no_tds_audit=True).write(decl_vals)

            # Unlink any legacy child lines for employer NPS (Employer NPS Section 124 is an employer contribution, not an employee investment line item)
            legacy_nps_lines = decl.declaration_line_ids.filtered(lambda l: l.category == '80ccd2')
            if legacy_nps_lines:
                legacy_nps_lines.unlink()

            # Handle 'other' statutory deduction line
            other_amt = float(emp.hds_in_decl_other_amount or 0.0) if not is_new else 0.0
            other_line = decl.declaration_line_ids.filtered(lambda l: l.category == 'other' and getattr(l, 'active', True))
            if other_amt > 0:
                if other_line:
                    other_line[:1].sudo().write({'declared_amount': other_amt})
                else:
                    self.env['tds.employee.declaration.line'].sudo().create({
                        'declaration_id': decl.id,
                        'category': 'other',
                        'description': 'Other Statutory Deduction',
                        'declared_amount': other_amt,
                    })
            elif other_line:
                other_line.unlink()

            decl.action_validate_declaration_rules()





    def action_view_home_loans(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Housing Loan & Section 80EEA Eligibility'),
            'res_model': 'tds.employee.home.loan',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
