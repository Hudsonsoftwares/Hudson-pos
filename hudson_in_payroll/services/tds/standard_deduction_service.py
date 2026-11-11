# -*- coding: utf-8 -*-
import logging
from ..base import BaseStatutoryService
from .tds_parameter_service import TdsParameterService

_logger = logging.getLogger(__name__)


class StandardDeductionService(BaseStatutoryService):
    """
    Phase 5 Service: Standard Deduction Service.
    Resolves regime-aware statutory Standard Deduction ceiling under Section 16(ia).
    - Old Regime: ₹50,000 limit (HDS_IN_TDS_STD_DEDUCTION_OLD).
    - New Regime: ₹75,000 limit (HDS_IN_TDS_STD_DEDUCTION_NEW under Finance Act 2025 / FY 2025-26).
    """

    def calculate_standard_deduction(self, regime_code, gross_payroll_income, eval_date=None):
        """
        Calculates Standard Deduction capped at gross payroll income.

        :param regime_code: str ('old' or 'new')
        :param gross_payroll_income: float (Gross payroll earnings from current/previous employer)
        :param eval_date: Date (optional)
        :return: float (Approved Standard Deduction)
        """
        tds_param_svc = TdsParameterService(self.env)
        regime_code = (regime_code or 'new').lower()

        std_limit = tds_param_svc.get_parameter(
            'STD_DEDUCTION',
            eval_date=eval_date,
            regime=regime_code
        ) or (75000.0 if regime_code == 'new' else 50000.0)

        # Standard deduction cannot exceed gross payroll income
        return min(max(0.0, gross_payroll_income), std_limit)
