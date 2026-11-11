# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import fields, _
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


# Enterprise Parameter Mapping Table for regime-dependent & shared TDS parameters
TDS_PARAMETER_MAP = {
    # Standard Deduction
    'STD_DEDUCTION_NEW': 'HDS_IN_TDS_STD_DEDUCTION_NEW',
    'STD_DEDUCTION_OLD': 'HDS_IN_TDS_STD_DEDUCTION_OLD',
    # Section 87A Income Limit
    '87A_LIMIT_NEW': 'HDS_IN_TDS_87A_LIMIT_NEW',
    '87A_LIMIT_OLD': 'HDS_IN_TDS_87A_LIMIT_OLD',
    # Section 87A Max Rebate
    '87A_MAX_REBATE_NEW': 'HDS_IN_TDS_87A_MAX_REBATE_NEW',
    '87A_MAX_REBATE_OLD': 'HDS_IN_TDS_87A_MAX_REBATE_OLD',
    # Shared Cess Rate
    'HEALTH_CESS': 'HDS_IN_TDS_HEALTH_CESS',
    # Employer NPS Limits
    'NPS_LIMIT_NEW': 'HDS_IN_TDS_NPS_LIMIT_NEW',
    'NPS_LIMIT_OLD_PRIVATE': 'HDS_IN_TDS_NPS_LIMIT_OLD_PRIVATE',
    'NPS_LIMIT_OLD_GOVT': 'HDS_IN_TDS_NPS_LIMIT_OLD_GOVT',
    'NPS_EMPLOYER_CONTRIBUTION_PERCENTAGE': 'HDS_IN_TDS_NPS_LIMIT_NEW',
    # Combined Employer Contribution Limit (PF + NPS + Superannuation)
    'EMPLOYER_CONTRIBUTION_LIMIT': 'HDS_IN_TDS_EMPLOYER_CONTRIBUTION_LIMIT',
    # Statutory PF / EPS / EDLI Wage Ceilings
    'PF_WAGE_CEILING': 'hds_in_pf_wage_ceiling',
    'EPS_WAGE_CEILING': 'hds_in_eps_wage_ceiling',
    'EDLI_WAGE_CEILING': 'hds_in_edli_wage_ceiling',
    # Section 57(iia) Family Pension Limits
    'FAMILY_PENSION_LIMIT_NEW': 'HDS_IN_TDS_FAMILY_PENSION_LIMIT_NEW',
    'FAMILY_PENSION_LIMIT_OLD': 'HDS_IN_TDS_FAMILY_PENSION_LIMIT_OLD',
    # Section 80CCH Agniveer Corpus Fund Eligibility Percentages
    '80CCH_ELIGIBILITY_PERCENT_NEW': 'HDS_IN_TDS_80CCH_ELIGIBILITY_PERCENT_NEW',
    '80CCH_ELIGIBILITY_PERCENT_OLD': 'HDS_IN_TDS_80CCH_ELIGIBILITY_PERCENT_OLD',
    # Category A: Scalar Statutory Parameters (Simple Effective-Dated Statutory Constants)
    '80C_MAX_LIMIT': 'HDS_IN_TDS_80C_MAX_LIMIT',
    '80CCD1B_MAX_LIMIT': 'HDS_IN_TDS_80CCD1B_MAX_LIMIT',
    '80D_SELF_MAX_LIMIT': 'HDS_IN_TDS_80D_SELF_MAX_LIMIT',
    '80D_SELF_SENIOR_MAX_LIMIT': 'HDS_IN_TDS_80D_SELF_SENIOR_MAX_LIMIT',
    '80D_PARENTS_MAX_LIMIT': 'HDS_IN_TDS_80D_PARENTS_MAX_LIMIT',
    '80D_PARENTS_SENIOR_MAX_LIMIT': 'HDS_IN_TDS_80D_PARENTS_SENIOR_MAX_LIMIT',
    '80D_PREVENTIVE_CHECKUP_LIMIT': 'HDS_IN_TDS_80D_PREVENTIVE_CHECKUP_LIMIT',
    '80TTA_MAX_LIMIT': 'HDS_IN_TDS_80TTA_MAX_LIMIT',
    '80TTB_MAX_LIMIT': 'HDS_IN_TDS_80TTB_MAX_LIMIT',
    '80DD_NORMAL_LIMIT': 'HDS_IN_TDS_80DD_NORMAL_LIMIT',
    '80DD_SEVERE_LIMIT': 'HDS_IN_TDS_80DD_SEVERE_LIMIT',
    '80U_NORMAL_LIMIT': 'HDS_IN_TDS_80U_NORMAL_LIMIT',
    '80U_SEVERE_LIMIT': 'HDS_IN_TDS_80U_SEVERE_LIMIT',

    # Section 24(b) & Section 10 Exemptions (Category A Monetary Ceilings)
    '24B_HOME_LOAN_INTEREST_LIMIT': 'HDS_IN_TDS_24B_HOME_LOAN_INTEREST_LIMIT',
    '24B_COMPLETION_PERIOD_YEARS': 'HDS_IN_TDS_24B_COMPLETION_PERIOD_YEARS',
    '24B_BORROWING_START_DATE': 'HDS_IN_TDS_24B_BORROWING_START_DATE',
    '24B_REPAIR_RENOVATION_LIMIT': 'HDS_IN_TDS_24B_REPAIR_RENOVATION_LIMIT',
    'HOUSE_PROPERTY_LOSS_LIMIT': 'HDS_IN_TDS_HOUSE_PROPERTY_LOSS_LIMIT',

    # Category B: Eligibility-Based Statutory Features (Monetary ceiling stored as hr.rule.parameter,
    # BUT calculation engines MUST invoke employee eligibility validation services before applying ceiling)
    # E.g. Section 80EEA requires: Loan Sanctioned between 01-Apr-2019 and 31-Mar-2022, Stamp Value <= 45L, First-time Home Buyer.
    '80EEA_MAX_LIMIT': 'HDS_IN_TDS_80EEA_MAX_LIMIT',
    '80EEA_MAX_STAMP_DUTY': 'HDS_IN_TDS_80EEA_MAX_STAMP_DUTY',
    '80G_MAX_CASH_DONATION': 'HDS_IN_TDS_80G_MAX_CASH_DONATION',
    '80E_MAX_DEDUCTION_YEARS': 'HDS_IN_TDS_80E_MAX_DEDUCTION_YEARS',
    '80E_ALLOWED_LENDER_TYPES': 'HDS_IN_TDS_80E_ALLOWED_LENDER_TYPES',

    'HRA_METRO_PERCENT': 'HDS_IN_TDS_HRA_METRO_PERCENT',
    'HRA_NON_METRO_PERCENT': 'HDS_IN_TDS_HRA_NON_METRO_PERCENT',
    'HRA_RENT_EXCESS_BASIC_PERCENT': 'HDS_IN_TDS_HRA_RENT_EXCESS_BASIC_PERCENT',
    'CHILDREN_EDU_ALLOWANCE_MONTHLY': 'HDS_IN_TDS_CHILDREN_EDU_ALLOWANCE_MONTHLY',
    'HOSTEL_ALLOWANCE_MONTHLY': 'HDS_IN_TDS_HOSTEL_ALLOWANCE_MONTHLY',
    'LEAVE_ENCASHMENT_EXEMPTION_CEILING': 'HDS_IN_TDS_LEAVE_ENCASHMENT_EXEMPTION_CEILING',
    'VRS_EXEMPTION_CEILING': 'HDS_IN_TDS_VRS_EXEMPTION_CEILING',

    # Section 10(5) LTA Statutory Parameters
    'LTA_BLOCK_PERIOD': 'HDS_IN_TDS_LTA_BLOCK_PERIOD',
    'LTA_PREV_BLOCK_PERIOD': 'HDS_IN_TDS_LTA_PREV_BLOCK_PERIOD',
    'LTA_MAX_CLAIMS_PER_BLOCK': 'HDS_IN_TDS_LTA_MAX_CLAIMS_PER_BLOCK',
    'LTA_AIR_FARE_CEILING': 'HDS_IN_TDS_LTA_AIR_FARE_CEILING',
    'LTA_RAIL_AC1_FARE_CEILING': 'HDS_IN_TDS_LTA_RAIL_AC1_FARE_CEILING',
    'LTA_PUBLIC_TRANS_FARE_CEILING': 'HDS_IN_TDS_LTA_PUBLIC_TRANS_FARE_CEILING',
}



class TdsParameterService(BaseStatutoryService):
    """
    Centralized Service Resolver for Indian TDS Engine Statutory Parameters & Masters.
    Provides regime-aware, effective-dated parameter lookups from hr.rule.parameter
    and structured query resolution for tds.financial.year, tds.tax.slab, and tds.surcharge masters.

    ARCHITECTURAL CLASSIFICATION FRAMEWORK:
    --------------------------------------
    1. Category A – Scalar Statutory Parameters:
       Simple statutory constants (e.g. Standard Deduction, Cess, Sec 80C limit, Sec 87A limit, Sec 24(b) limit)
       resolved directly via get_parameter().

    2. Category B – Eligibility-Based Statutory Features:
       Features where deduction eligibility depends on employee-specific facts (e.g. Sec 80EEA loan sanction date
       between 01/04/2019 and 31/03/2022, property value <= 45L, first-time home buyer).
       For Category B features, get_parameter() resolves the statutory ceiling, BUT downstream calculation engines
       MUST validate employee eligibility facts via declaration services BEFORE applying the deduction ceiling.

    All downstream TDS calculation services MUST resolve parameters through this service.
    """


    def get_parameter(self, code_or_key, eval_date=None, regime='new', employer_type='private', as_decimal=False, default_val=0.0, **kwargs):
        """
        Resolves a scalar statutory parameter by code, regime, and evaluation date.

        :param code_or_key: str (mapped short key like 'STD_DEDUCTION' or full parameter code)
        :param eval_date: datetime.date or str (defaults to today)
        :param regime: str ('new' or 'old')
        :param employer_type: str ('private', 'govt_central', 'govt_state')
        :param as_decimal: bool (if True and parameter is a rate, divides by 100.0)
        :return: float
        """
        if not eval_date:
            eval_date = fields.Date.today()
        elif isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)

        regime_code = (regime or 'new').lower()

        # Dynamic regime-aware parameter key mapping
        resolved_code = code_or_key
        if code_or_key in ('STD_DEDUCTION', 'HDS_IN_TDS_STD_DEDUCTION'):
            resolved_code = 'HDS_IN_TDS_STD_DEDUCTION_NEW' if regime_code == 'new' else 'HDS_IN_TDS_STD_DEDUCTION_OLD'
        elif code_or_key in ('87A_LIMIT', 'HDS_IN_TDS_87A_LIMIT'):
            resolved_code = 'HDS_IN_TDS_87A_LIMIT_NEW' if regime_code == 'new' else 'HDS_IN_TDS_87A_LIMIT_OLD'
        elif code_or_key in ('87A_MAX_REBATE', 'HDS_IN_TDS_87A_MAX_REBATE'):
            resolved_code = 'HDS_IN_TDS_87A_MAX_REBATE_NEW' if regime_code == 'new' else 'HDS_IN_TDS_87A_MAX_REBATE_OLD'
        elif code_or_key in ('NPS_LIMIT', 'HDS_IN_TDS_NPS_LIMIT', 'NPS_EMPLOYER_CONTRIBUTION_PERCENTAGE', 'HDS_IN_TDS_NPS_EMPLOYER_CONTRIBUTION_PERCENTAGE'):
            if regime_code == 'new':
                if self.env['hr.rule.parameter'].search_count([('code', '=', 'NPS_EMPLOYER_CONTRIBUTION_PERCENTAGE')]):
                    resolved_code = 'NPS_EMPLOYER_CONTRIBUTION_PERCENTAGE'
                else:
                    resolved_code = 'HDS_IN_TDS_NPS_LIMIT_NEW'
            elif 'govt' in (employer_type or '').lower():
                resolved_code = 'HDS_IN_TDS_NPS_LIMIT_OLD_GOVT'
            else:
                resolved_code = 'HDS_IN_TDS_NPS_LIMIT_OLD_PRIVATE'
        elif code_or_key in ('FAMILY_PENSION_LIMIT', 'HDS_IN_TDS_FAMILY_PENSION_LIMIT'):
            resolved_code = 'HDS_IN_TDS_FAMILY_PENSION_LIMIT_NEW' if regime_code == 'new' else 'HDS_IN_TDS_FAMILY_PENSION_LIMIT_OLD'
        elif code_or_key in ('80CCH_ELIGIBILITY_PERCENT', 'HDS_IN_TDS_80CCH_ELIGIBILITY_PERCENT'):
            resolved_code = 'HDS_IN_TDS_80CCH_ELIGIBILITY_PERCENT_NEW' if regime_code == 'new' else 'HDS_IN_TDS_80CCH_ELIGIBILITY_PERCENT_OLD'
        elif code_or_key in TDS_PARAMETER_MAP:
            resolved_code = TDS_PARAMETER_MAP[code_or_key]

        try:
            return self.env['hr.rule.parameter'].get_parameter(resolved_code, date=eval_date, as_decimal=as_decimal)
        except (KeyError, ValueError, TypeError, ValidationError) as e:
            _logger.debug("Rule parameter '%s' not found or invalid on date %s (using default): %s", resolved_code, eval_date, e)
            val = default_val or kwargs.get('default', 0.0)
            if as_decimal and val > 1.0:
                val = val / 100.0
            return val

    def get_80cch_eligibility_percent(self, regime='old', eval_date=None, as_decimal=False):
        """
        Resolves Section 80CCH Agniveer Corpus Fund employee contribution statutory eligibility percentage based on tax regime.
        - Old Regime: HDS_IN_TDS_80CCH_ELIGIBILITY_PERCENT_OLD (100%)
        - New Regime: HDS_IN_TDS_80CCH_ELIGIBILITY_PERCENT_NEW (100%)
        """
        return self.get_parameter('80CCH_ELIGIBILITY_PERCENT', eval_date=eval_date, regime=regime, as_decimal=as_decimal)

    def get_family_pension_limit(self, regime='new', eval_date=None):
        """Resolves Family Pension Section 93(1)(d) / Section 57(iia) deduction statutory ceiling (1/3 of family pension or ₹25,000, whichever is lower)."""
        is_ita_2025 = False
        if eval_date:
            # pyrefly: ignore [missing-import]
            from odoo import fields
            ref_year = eval_date.year if hasattr(eval_date, 'year') else int(str(eval_date)[:4])
            is_ita_2025 = (eval_date >= fields.Date.from_string('2026-04-01')) if hasattr(eval_date, 'year') else (ref_year >= 2026)
        def_val = 25000.0 if (is_ita_2025 or (regime or 'new').lower() == 'new') else 15000.0
        return self.get_parameter('FAMILY_PENSION_LIMIT', eval_date=eval_date, regime=regime, default_val=def_val)

    def get_employer_nps_limit(self, regime='new', employer_type='private', eval_date=None, as_decimal=False):
        """
        Resolves Employer NPS statutory percentage limit based on regime and employer category.
        - New Regime: 14% for all employers (via NPS_EMPLOYER_CONTRIBUTION_PERCENTAGE / HDS_IN_TDS_NPS_LIMIT_NEW).
        - Old Regime: 10% for Private/Other employers, 14% for Central/State Government.
        """
        reg_code = (regime or 'new').lower()
        default_pct = 14.0 if reg_code == 'new' else (14.0 if 'govt' in (employer_type or '').lower() else 10.0)
        return self.get_parameter('NPS_EMPLOYER_CONTRIBUTION_PERCENTAGE', eval_date=eval_date, regime=regime, employer_type=employer_type, as_decimal=as_decimal, default_val=default_pct)

    def get_combined_employer_contribution_limit(self, eval_date=None):
        """
        Resolves the statutory combined employer contribution ceiling under Section 17(2)(vii)
        for Employer PF + Employer NPS + Approved Superannuation (₹7,50,000 per annum).
        """
        return self.get_parameter('EMPLOYER_CONTRIBUTION_LIMIT', eval_date=eval_date, as_decimal=False)

    def get_80c_limit(self, eval_date=None):
        """Resolves Section 80C maximum allowable deduction ceiling (₹1,50,000)."""
        return self.get_parameter('80C_MAX_LIMIT', eval_date=eval_date)

    def get_80ccd1b_limit(self, eval_date=None):
        """Resolves Section 80CCD(1B) additional NPS deduction ceiling (₹50,000)."""
        return self.get_parameter('80CCD1B_MAX_LIMIT', eval_date=eval_date)

    def get_hra_percentage(self, is_metro=True, eval_date=None, as_decimal=False):
        """Resolves HRA exemption percentage (50% for Metro cities, 40% for Non-Metro)."""
        key = 'HRA_METRO_PERCENT' if is_metro else 'HRA_NON_METRO_PERCENT'
        return self.get_parameter(key, eval_date=eval_date, as_decimal=as_decimal)

    def get_80d_limit(self, is_senior=False, is_parents=False, eval_date=None):
        """Resolves Section 80D Health Insurance deduction ceiling based on beneficiary and senior citizen status."""
        if is_parents:
            key = '80D_PARENTS_SENIOR_MAX_LIMIT' if is_senior else '80D_PARENTS_MAX_LIMIT'
        else:
            key = '80D_SELF_SENIOR_MAX_LIMIT' if is_senior else '80D_SELF_MAX_LIMIT'
        return self.get_parameter(key, eval_date=eval_date)

    def get_home_loan_interest_limit(self, eval_date=None):
        """Resolves Section 24(b) Self-Occupied Home Loan Interest deduction ceiling (₹2,00,000)."""
        return self.get_parameter('24B_HOME_LOAN_INTEREST_LIMIT', eval_date=eval_date)

    def get_house_property_loss_limit(self, eval_date=None):
        """Resolves Section 71(3A) House Property Loss set-off limit for Old Tax Regime (₹2,00,000)."""
        return self.get_parameter('HOUSE_PROPERTY_LOSS_LIMIT', eval_date=eval_date, default_val=200000.0)

    def get_leave_encashment_ceiling(self, eval_date=None):
        """Resolves Section 10(10AA) Leave Encashment exemption ceiling for non-government employees (₹25,00,000)."""
        return self.get_parameter('LEAVE_ENCASHMENT_EXEMPTION_CEILING', eval_date=eval_date)

    def get_80dd_limit(self, is_severe=False, eval_date=None):
        """
        Resolves Section 80DD Dependent Disability deduction statutory ceiling.
        - Severe Disability (≥80%): HDS_IN_TDS_80DD_SEVERE_LIMIT (₹1,25,000)
        - Normal Disability (≥40% & <80%): HDS_IN_TDS_80DD_NORMAL_LIMIT (₹75,000)
        """
        key = '80DD_SEVERE_LIMIT' if is_severe else '80DD_NORMAL_LIMIT'
        return self.get_parameter(key, eval_date=eval_date)

    def get_lta_block_period(self, eval_date=None):
        """Dynamically computes active Section 10(5) LTA 4-calendar-year block period from journey date (e.g. '2022-2025' or '2026-2029')."""
        if not eval_date:
            return 'PENDING_JOURNEY_DATE'
        if isinstance(eval_date, str):
            try:
                eval_date = fields.Date.from_string(eval_date)
            except Exception:
                return 'PENDING_JOURNEY_DATE'
        year = eval_date.year if hasattr(eval_date, 'year') else int(str(eval_date)[:4])
        base_year = 1986 + ((year - 1986) // 4) * 4
        return f"{base_year}-{base_year + 3}"

    def get_lta_prev_block_period(self, eval_date=None):
        """Dynamically computes previous Section 10(5) LTA 4-calendar-year block period from journey date (e.g. '2018-2021' or '2022-2025')."""
        if not eval_date:
            return 'PENDING_JOURNEY_DATE'
        if isinstance(eval_date, str):
            try:
                eval_date = fields.Date.from_string(eval_date)
            except Exception:
                return 'PENDING_JOURNEY_DATE'
        year = eval_date.year if hasattr(eval_date, 'year') else int(str(eval_date)[:4])
        base_year = 1986 + ((year - 1986) // 4) * 4
        return f"{base_year - 4}-{base_year - 1}"

    def get_lta_max_claims_per_block(self, eval_date=None):
        """Resolves Section 10(5) LTA maximum claims per block (default: 2)."""
        val = self.get_parameter('LTA_MAX_CLAIMS_PER_BLOCK', eval_date=eval_date, default_val=2)
        try:
            return int(val)
        except (ValueError, TypeError):
            return 2

    def get_lta_air_ceiling(self, eval_date=None):
        """Resolves Rule 2B economy air fare national carrier statutory ceiling (default: ₹50,000)."""
        return float(self.get_parameter('LTA_AIR_FARE_CEILING', eval_date=eval_date, default_val=50000.0))

    def get_lta_rail_ac1_ceiling(self, eval_date=None):
        """Resolves Rule 2B AC 1st class rail fare statutory ceiling (default: ₹15,000)."""
        return float(self.get_parameter('LTA_RAIL_AC1_FARE_CEILING', eval_date=eval_date, default_val=15000.0))

    def get_lta_public_trans_ceiling(self, eval_date=None):
        """Resolves Rule 2B recognised public transport travel fare statutory ceiling (default: ₹10,000)."""
        return float(self.get_parameter('LTA_PUBLIC_TRANS_FARE_CEILING', eval_date=eval_date, default_val=10000.0))



    def get_financial_year(self, eval_date=None, company=None):
        """
        Resolves active tds.financial.year master record covering eval_date.
        Raises ValidationError if no active Financial Year is configured for eval_date.
        Silent fallback to previous Financial Year is strictly prohibited to prevent stale TDS deductions.
        """
        if not eval_date:
            eval_date = fields.Date.today()
        elif isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)

        company = company or self.env.company
        if company and company.hds_in_default_tax_year:
            default_fy = company.hds_in_default_tax_year
            if default_fy.active and not default_fy.is_closed:
                if default_fy.start_date <= eval_date <= default_fy.end_date:
                    return default_fy

        domain = [
            ('active', '=', True),
            ('start_date', '<=', eval_date),
            ('end_date', '>=', eval_date),
            ('is_closed', '=', False),
        ]
        fy = self.env['tds.financial.year'].search(domain, limit=1)
        if not fy and company and company.hds_in_default_tax_year and company.hds_in_default_tax_year.active:
            fy = company.hds_in_default_tax_year

        if not fy:
            raise ValidationError(
                _(f"No active Financial Year configuration exists covering evaluation date {eval_date}. "
                  f"Please generate and configure the required Financial Year using the Financial Year Roll-Over Wizard "
                  f"before processing payroll or managing tax declarations.")
            )
        return fy



    def get_tax_slabs(self, financial_year=None, regime='new', eval_date=None):
        """
        Retrieves ordered income tax slab records for the target financial year and tax regime.

        :param financial_year: tds.financial.year recordset or ID (optional)
        :param regime: str ('new' or 'old')
        :param eval_date: datetime.date or str
        :return: recordset of tds.tax.slab
        """
        if not financial_year:
            financial_year = self.get_financial_year(eval_date=eval_date)

        regime_code = (regime or 'new').lower()
        domain = [
            ('financial_year_id', '=', financial_year.id if hasattr(financial_year, 'id') else financial_year),
            ('regime_code', '=', regime_code),
            ('active', '=', True),
        ]
        slabs = self.env['tds.tax.slab'].search(domain, order='income_from asc, sequence asc')
        if not slabs:
            _logger.warning(
                "TdsParameterService: No active tax slabs found for FY '%s', Regime '%s'.",
                getattr(financial_year, 'name', financial_year), regime_code
            )
        return slabs

    def get_surcharge_slabs(self, financial_year=None, regime='new', eval_date=None):
        """
        Retrieves ordered surcharge slab records for the target financial year and tax regime.

        :param financial_year: tds.financial.year recordset or ID (optional)
        :param regime: str ('new' or 'old')
        :param eval_date: datetime.date or str
        :return: recordset of tds.surcharge
        """
        if not financial_year:
            financial_year = self.get_financial_year(eval_date=eval_date)

        regime_code = (regime or 'new').lower()
        domain = [
            ('financial_year_id', '=', financial_year.id if hasattr(financial_year, 'id') else financial_year),
            ('regime_code', '=', regime_code),
            ('active', '=', True),
        ]
        surcharges = self.env['tds.surcharge'].search(domain, order='income_from asc, sequence asc')
        return surcharges

    def get_80e_max_years(self, eval_date=None):
        """
        Retrieves statutory maximum deduction period in years under Section 80E (Default: 8 years).
        """
        try:
            val = self.get_parameter('HDS_IN_TDS_80E_MAX_DEDUCTION_YEARS', eval_date=eval_date)
            return int(val) if val else 8
        except (ValueError, TypeError):
            return 8

    get_80e_max_deduction_years = get_80e_max_years

    def get_80e_allowed_lenders(self, eval_date=None):
        """
        Retrieves list of permitted lender categories under Section 80E.
        """
        try:
            val = self.get_parameter('HDS_IN_TDS_80E_ALLOWED_LENDER_TYPES', eval_date=eval_date)
            if isinstance(val, str) and val.strip():
                return [x.strip().upper() for x in val.split(',')]
        except (ValueError, TypeError, AttributeError):
            pass
        return ['SCHEDULED_BANK', 'FINANCIAL_INSTITUTION', 'APPROVED_CHARITABLE_INSTITUTION']

    def get_80dd_normal_deduction(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_80DD_NORMAL_DEDUCTION', eval_date=eval_date)
            return float(val) if val else 75000.0
        except (ValueError, TypeError):
            return 75000.0

    def get_80dd_severe_deduction(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_80DD_SEVERE_DEDUCTION', eval_date=eval_date)
            return float(val) if val else 125000.0
        except (ValueError, TypeError):
            return 125000.0

    def get_80dd_normal_disability_percent(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_80DD_NORMAL_DISABILITY_PERCENT', eval_date=eval_date)
            return float(val) if val else 40.0
        except (ValueError, TypeError):
            return 40.0

    def get_80dd_severe_disability_percent(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_80DD_SEVERE_DISABILITY_PERCENT', eval_date=eval_date)
            return float(val) if val else 80.0
        except (ValueError, TypeError):
            return 80.0

    def get_80dd_allow_only_resident(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_80DD_ALLOW_ONLY_RESIDENT', eval_date=eval_date)
            return str(val).lower() in ('true', '1', 'yes') if val is not None else True
        except (ValueError, TypeError):
            return True

    def get_80dd_certificate_required(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_80DD_CERTIFICATE_REQUIRED', eval_date=eval_date)
            return str(val).lower() in ('true', '1', 'yes') if val is not None else True
        except (ValueError, TypeError):
            return True

    def get_80dd_check_certificate_expiry(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_80DD_CHECK_CERTIFICATE_EXPIRY', eval_date=eval_date)
            return str(val).lower() in ('true', '1', 'yes') if val is not None else True
        except (ValueError, TypeError):
            return True

    def get_80u_normal_deduction(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_80U_NORMAL_DEDUCTION', eval_date=eval_date)
            return float(val) if val else 75000.0
        except (ValueError, TypeError):
            return 75000.0

    def get_80u_severe_deduction(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_80U_SEVERE_DEDUCTION', eval_date=eval_date)
            return float(val) if val else 125000.0
        except (ValueError, TypeError):
            return 125000.0

    def get_80u_normal_disability_percent(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_80U_NORMAL_DISABILITY_PERCENT', eval_date=eval_date)
            return float(val) if val else 40.0
        except (ValueError, TypeError):
            return 40.0

    def get_80u_severe_disability_percent(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_80U_SEVERE_DISABILITY_PERCENT', eval_date=eval_date)
            return float(val) if val else 80.0
        except (ValueError, TypeError):
            return 80.0

    def get_80u_allow_only_resident(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_80U_ALLOW_ONLY_RESIDENT', eval_date=eval_date)
            if val is not None:
                sval = str(val).strip().lower()
                if sval in ('false', '0', '0.0', 'no'):
                    return True  # Statutory mandatory rule u/s 80U
                return sval in ('true', '1', 'yes')
            return True
        except (ValueError, TypeError):
            return True

    def get_80u_certificate_required(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_80U_CERTIFICATE_REQUIRED', eval_date=eval_date)
            return str(val).lower() in ('true', '1', 'yes') if val is not None else True
        except (ValueError, TypeError):
            return True

    def get_80u_check_certificate_expiry(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_80U_CHECK_CERTIFICATE_EXPIRY', eval_date=eval_date)
            return str(val).lower() in ('true', '1', 'yes') if val is not None else True
        except (ValueError, TypeError):
            return True

    def get_24b_completion_period_years(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_24B_COMPLETION_PERIOD_YEARS', eval_date=eval_date)
            return int(val) if val else 5
        except (ValueError, TypeError):
            return 5

    def get_24b_borrowing_start_date(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_24B_BORROWING_START_DATE', eval_date=eval_date)
            return fields.Date.from_string(str(val)) if val else fields.Date.from_string('1999-04-01')
        except (ValueError, TypeError):
            return fields.Date.from_string('1999-04-01')

    def get_24b_repair_renovation_limit(self, eval_date=None):
        try:
            val = self.get_parameter('HDS_IN_TDS_24B_REPAIR_RENOVATION_LIMIT', eval_date=eval_date)
            return float(val) if val else 30000.0
        except (ValueError, TypeError):
            return 30000.0
