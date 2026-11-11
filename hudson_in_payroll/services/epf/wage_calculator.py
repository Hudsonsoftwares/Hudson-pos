# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import fields
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class EPFWageCalculator(BaseStatutoryService):
    """Calculates Actual PF Wage and Statutory Contribution Wage Basis."""

    def __init__(self, env, localdict=None):
        super().__init__(env)
        self.localdict = localdict

    def get_actual_pf_wage(self, payslip, localdict=None):
        """Delegates actual PF wage calculation to payslip domain API."""
        _logger.info("===================================================")
        _logger.info("6. Wage Calculator: get_actual_pf_wage()")
        _logger.info("===================================================")
        _logger.info("[EPFWageCalculator] Called get_actual_pf_wage(payslip=%s)", payslip)
        ld = localdict if localdict is not None else self.localdict
        result = payslip.hds_in_get_actual_pf_wage(localdict=ld)
        _logger.info("[EPFWageCalculator] Returned get_actual_pf_wage -> %s", result)
        return result

    def get_pf_contribution_wage(self, payslip, localdict=None):
        """
        Determines the wage basis for PF contribution.
        Capped at Statutory PF Wage Ceiling (default ₹25,000) unless:
        - Employee is an International Worker (IW)
        - Contribution basis is set to 'actual_pf_wage' (or legacy 'actual_basic')

        Returns:
            float: 0.0 if actual PF wage is <= 0, otherwise the statutory contribution wage.
        """
        _logger.info("===================================================")
        _logger.info("6. Wage Calculator: get_pf_contribution_wage()")
        _logger.info("===================================================")
        _logger.info("[EPFWageCalculator] Called get_pf_contribution_wage(payslip=%s)", payslip)
        ld = localdict if localdict is not None else self.localdict
        actual_pf_wage = self.get_actual_pf_wage(payslip, localdict=ld)

        # Non-positive wage handling: Actual PF Wage <= 0 -> 0.0 contribution basis
        if actual_pf_wage <= 0.0:
            _logger.info("[EPFWageCalculator] Non-positive Actual PF Wage (%s) -> Contribution Wage: 0.0", actual_pf_wage)
            return 0.0

        employee = payslip.employee_id
        if getattr(employee, 'hds_in_is_international_worker', False):
            _logger.info("[EPFWageCalculator] International Worker -> Wage: %s", actual_pf_wage)
            return actual_pf_wage

        basis = getattr(employee, 'hds_in_pf_contribution_basis', 'statutory_ceiling')
        if basis in ('actual_pf_wage', 'actual_basic'):
            _logger.info("[EPFWageCalculator] Basis '%s' (Uncapped) -> Wage: %s", basis, actual_pf_wage)
            return actual_pf_wage

        eval_date = payslip.date_to or fields.Date.today()
        pf_ceiling = self.get_pf_parameter('PF_WAGE_CEILING', date=eval_date)
        res = min(actual_pf_wage, pf_ceiling)
        _logger.info("[EPFWageCalculator] Capped Wage Basis (Ceiling: %s) -> %s", pf_ceiling, res)
        return res

    def get_employer_pf_contribution_wage(self, payslip, localdict=None):
        """
        Determines the wage basis for Employer PF contribution.
        Uses hds_in_pf_employer_basis (falls back to employee basis if not set).
        """
        ld = localdict if localdict is not None else self.localdict
        actual_pf_wage = self.get_actual_pf_wage(payslip, localdict=ld)
        if actual_pf_wage <= 0.0:
            return 0.0

        employee = payslip.employee_id
        if getattr(employee, 'hds_in_is_international_worker', False):
            return actual_pf_wage

        basis = getattr(employee, 'hds_in_pf_employer_basis', False) or getattr(employee, 'hds_in_pf_contribution_basis', 'statutory_ceiling')
        if basis in ('actual_pf_wage', 'actual_basic'):
            return actual_pf_wage

        eval_date = payslip.date_to or fields.Date.today()
        pf_ceiling = self.get_pf_parameter('PF_WAGE_CEILING', date=eval_date)
        return min(actual_pf_wage, pf_ceiling)


