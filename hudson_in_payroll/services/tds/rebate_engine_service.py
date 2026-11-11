# -*- coding: utf-8 -*-
import logging
from ..base import BaseStatutoryService
from .tds_parameter_service import TdsParameterService

_logger = logging.getLogger(__name__)


class RebateEngineResult:
    """
    Data Transfer Object (DTO) holding Section 87A rebate calculation details.
    """
    def __init__(self, net_taxable_income, base_tax_liability, rebate_eligible_limit,
                 max_rebate_allowed, rebate_applied, tax_after_rebate):
        self.net_taxable_income = net_taxable_income
        self.base_tax_liability = base_tax_liability
        self.rebate_eligible_limit = rebate_eligible_limit
        self.max_rebate_allowed = max_rebate_allowed
        self.rebate_applied = rebate_applied
        self.tax_after_rebate = tax_after_rebate


class RebateEngineService(BaseStatutoryService):
    """
    Phase 4 Pipeline Service: Section 87A Tax Rebate Engine Service.
    Applies Section 87A rebate based on effective-dated statutory parameters for the Financial Year & Tax Regime:
    - Old Regime: Income <= ₹5,00,000 -> Max Rebate ₹12,500 (Tax liability becomes ₹0).
    - New Regime: Income <= ₹7,00,000 -> Max Rebate ₹25,000 (Tax liability becomes ₹0).
      Includes marginal rebate relief for income slightly exceeding the ₹7,00,000 threshold under Section 115BAC.
    """

    def apply_rebate(self, net_taxable_income, base_tax_liability, regime_code, eval_date=None):
        """
        Calculates Section 87A rebate and revised tax liability after rebate.

        :param net_taxable_income: float (Net Taxable Income)
        :param base_tax_liability: float (Base tax before rebate)
        :param regime_code: str ('old' or 'new')
        :param eval_date: Date (optional)
        :return: RebateEngineResult
        """
        tds_param_svc = TdsParameterService(self.env)
        regime_code = (regime_code or 'new').lower()

        # Resolve 87A eligibility limit and max rebate ceiling via TdsParameterService
        rebate_limit = tds_param_svc.get_parameter('87A_LIMIT', eval_date=eval_date, regime=regime_code) or (700000.0 if regime_code == 'new' else 500000.0)
        max_rebate = tds_param_svc.get_parameter('87A_MAX_REBATE', eval_date=eval_date, regime=regime_code) or (25000.0 if regime_code == 'new' else 12500.0)

        rebate_applied = 0.0

        if net_taxable_income <= rebate_limit:
            # Full Section 87A Rebate up to base tax liability
            rebate_applied = min(base_tax_liability, max_rebate)
        elif regime_code == 'new':
            # Section 115BAC Marginal Rebate Relief:
            # If Net Income slightly exceeds 7.0L, rebate is provided so tax does not exceed (Net Income - 7.0L)
            income_excess = net_taxable_income - rebate_limit
            if base_tax_liability > income_excess:
                marginal_tax = income_excess
                rebate_applied = max(0.0, base_tax_liability - marginal_tax)

        tax_after_rebate = max(0.0, base_tax_liability - rebate_applied)

        is_eligible = "YES" if (net_taxable_income <= rebate_limit or rebate_applied > 0) else "NO"
        reason = f"Taxable Income within eligible limit of ₹{rebate_limit:,.2f}" if is_eligible == "YES" else f"Taxable Income exceeds eligibility limit of ₹{rebate_limit:,.2f}."

        summary_log = f"""
========================================================
REBATE ENGINE SERVICE (SECTION 87A)
========================================================
Tax Before Rebate       : ₹{base_tax_liability:,.2f}
87A Eligible            : {is_eligible}
Reason                  : {reason}
Maximum Rebate          : ₹{max_rebate:,.2f}
Rebate Applied          : ₹{rebate_applied:,.2f}
Tax After Rebate        : ₹{tax_after_rebate:,.2f}
========================================================
"""
        _logger.warning(summary_log)

        return RebateEngineResult(
            net_taxable_income=net_taxable_income,
            base_tax_liability=base_tax_liability,
            rebate_eligible_limit=rebate_limit,
            max_rebate_allowed=max_rebate,
            rebate_applied=rebate_applied,
            tax_after_rebate=tax_after_rebate
        )
