# -*- coding: utf-8 -*-
import logging
from ..base import BaseStatutoryService
from .tds_parameter_service import TdsParameterService

_logger = logging.getLogger(__name__)


class RegimeCalculationContext:
    """
    Data Transfer Object (DTO) holding the regime-specific execution context pipeline
    prepared for downstream Phase 5 (Taxable Income Service) and Phase 6 (Tax Calculation Service).
    """
    def __init__(self, regime_code, gross_total_income, standard_deduction_limit,
                 permitted_categories, prohibited_categories, pipeline_slots,
                 gross_salary_income=None):
        self.regime_code = regime_code
        self.gross_total_income = gross_total_income
        self.gross_salary_income = gross_salary_income if gross_salary_income is not None else gross_total_income
        self.standard_deduction_limit = standard_deduction_limit
        self.permitted_categories = permitted_categories
        self.prohibited_categories = prohibited_categories
        self.pipeline_slots = pipeline_slots


class RegimeRoutingService(BaseStatutoryService):
    """
    Phase 4 Service: Regime Routing Service.
    Routes processing according to the employee's selected Tax Regime ('old' vs 'new')
    and prepares the exact statutory calculation context pipeline for downstream phases.
    """

    # Category sets permitted under each regime
    NEW_REGIME_PERMITTED_CATEGORIES = {
        '80ccd2',  # Employer NPS Contribution (Section 80CCD(2))
        '57iia',   # Family Pension Standard Deduction (Section 57(iia))
        '80cch',   # Agniveer Corpus Fund (Section 80CCH)
    }

    OLD_REGIME_PERMITTED_CATEGORIES = {
        '80c', 'nps_employee', '80ccd1b', '80d_self', '80d_parents', '80d_preventive',
        '80tta', '80ttb', '80dd', '24b', '80eea', 'hra', 'children_edu', 'hostel', 'lta',
        '80ccd2', '57iia', '80cch', 'other'
    }

    def prepare_regime_context(self, employee, financial_year, regime_code, gross_total_income, eval_date=None, gross_salary_income=None):
        """
        Prepares the statutory execution context pipeline for the selected Tax Regime.

        :param employee: hr.employee record
        :param financial_year: tds.financial.year record
        :param regime_code: str ('old' or 'new')
        :param gross_total_income: float (Gross Total Income projected in Phase 4)
        :param eval_date: Date (optional)
        :param gross_salary_income: float (Gross Salary Income projected in Phase 4)
        :return: RegimeCalculationContext
        """
        tds_param_svc = TdsParameterService(self.env)
        regime_code = (regime_code or 'new').lower()

        # Resolve regime-specific Standard Deduction via TdsParameterService
        # Old Regime: ₹50,000 (HDS_IN_TDS_STD_DEDUCTION_OLD)
        # New Regime: ₹75,000 (HDS_IN_TDS_STD_DEDUCTION_NEW under Finance Act 2025 / FY 2025-26)
        std_deduction_limit = tds_param_svc.get_parameter(
            'STD_DEDUCTION',
            eval_date=eval_date,
            regime=regime_code
        ) or (75000.0 if regime_code == 'new' else 50000.0)

        if regime_code == 'new':
            permitted_categories = self.NEW_REGIME_PERMITTED_CATEGORIES
            prohibited_categories = self.OLD_REGIME_PERMITTED_CATEGORIES - self.NEW_REGIME_PERMITTED_CATEGORIES
            pipeline_slots = {
                'standard_deduction': std_deduction_limit,
                'employer_nps_80ccd2': 0.0,
                'family_pension_57iia': 0.0,
                'agniveer_80cch': 0.0,
                'chapter_6a_deductions': 0.0,
                'hra_exemption': 0.0,
                'home_loan_interest_24b': 0.0,
            }
        else:
            permitted_categories = self.OLD_REGIME_PERMITTED_CATEGORIES
            prohibited_categories = set()
            pipeline_slots = {
                'standard_deduction': std_deduction_limit,
                'chapter_6a_80c': 0.0,
                'chapter_6a_80ccd1b': 0.0,
                'chapter_6a_80d': 0.0,
                'chapter_6a_80tta_80ttb': 0.0,
                'chapter_6a_80dd': 0.0,
                'employer_nps_80ccd2': 0.0,
                'hra_exemption': 0.0,
                'home_loan_interest_24b': 0.0,
                'section_80eea': 0.0,
            }

        return RegimeCalculationContext(
            regime_code=regime_code,
            gross_total_income=gross_total_income,
            standard_deduction_limit=std_deduction_limit,
            permitted_categories=permitted_categories,
            prohibited_categories=prohibited_categories,
            pipeline_slots=pipeline_slots,
            gross_salary_income=gross_salary_income
        )
