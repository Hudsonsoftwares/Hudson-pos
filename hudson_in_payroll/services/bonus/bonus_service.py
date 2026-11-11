# -*- coding: utf-8 -*-
import logging
from odoo import fields
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class BonusService(BaseStatutoryService):
    """
    Statutory / Payroll Service for Employee Bonuses (Performance Bonus & Retention Bonus).
    Encapsulates all business eligibility rules:
      - Active employment status
      - Separation / Notice period exclusion (configurable at company level)
      - Minimum service period threshold (configurable at company level)
    Ensures XML salary rules contain ZERO business logic and remain clean thin invocations.
    """

    def __init__(self, env, localdict=None):
        super().__init__(env)
        self.localdict = localdict or {}

    def _extract_context_data(self, payslip=None):
        """Extract payslip, employee, contract, evaluation date, and company safely."""
        slip = payslip or self.localdict.get('payslip_record') or self.localdict.get('payslip')
        employee = False
        contract = False
        eval_date = fields.Date.today()
        company = self.env.company

        if slip:
            employee = getattr(slip, 'employee_id', False)
            contract = getattr(slip, 'contract_id', False)
            eval_date = getattr(slip, 'date_to', fields.Date.today()) or fields.Date.today()
            company = getattr(slip, 'company_id', False) or getattr(employee, 'company_id', False) or self.env.company
        else:
            employee = self.localdict.get('employee')
            contract = self.localdict.get('contract')
            company = getattr(employee, 'company_id', False) or self.env.company

        return slip, employee, contract, eval_date, company

    def is_in_notice_period(self, employee, slip=None):
        """Check if employee is currently serving notice period or has pending/approved resignation."""
        if not employee:
            return False

        # 1. Scheduled departure date
        if employee.departure_date:
            date_from = getattr(slip, 'date_from', False) or fields.Date.today()
            if employee.departure_date >= date_from:
                return True

        # 2. Resignation flag on employee record if exists
        if getattr(employee, 'resigned', False):
            return True

        # 3. hr.resignation model records in confirmed/approved state
        if 'hr.resignation' in self.env:
            res = self.env['hr.resignation'].search([
                ('employee_id', '=', employee.id),
                ('state', 'in', ('confirm', 'approved'))
            ], limit=1)
            if res:
                return True

        return False

    def is_employee_active(self, employee, date_to):
        """Check if employee is active and not terminated before payslip period."""
        if not employee or not employee.active:
            return False
        if employee.departure_date and employee.departure_date <= date_to:
            return False
        return True

    def compute_performance_bonus(self, payslip=None):
        """
        Public calculation entry point for Performance Bonus (PERF_BONUS).
        Returns payable amount in INR.
        """
        slip, employee, contract, eval_date, company = self._extract_context_data(payslip)
        if not contract:
            return 0.0

        bonus_amt = getattr(contract, 'performance_bonus', 0.0) or 0.0
        if bonus_amt <= 0:
            return 0.0

        # Active status check
        date_to = getattr(slip, 'date_to', eval_date) or eval_date
        if not self.is_employee_active(employee, date_to):
            return 0.0

        # Notice period exclusion check (Rule-level setting if is_bonus enabled, else company setting)
        exclude_notice = self._is_notice_period_excluded('PERF_BONUS', company)
        if exclude_notice and self.is_in_notice_period(employee, slip):
            _logger.info("[BonusService] Performance bonus 0.0 for employee %s: In Notice Period", employee.name)
            return 0.0

        return bonus_amt

    def _is_notice_period_excluded(self, rule_code, company):
        """Resolves whether notice period exclusion applies, checking rule-level setting first then company-level."""
        rule = self.env['hr.salary.rule'].search([('code', '=', rule_code)], limit=1)
        if rule and getattr(rule, 'hds_in_is_bonus', False):
            return rule.hds_in_exclude_notice_period
        return getattr(company, 'hds_in_retention_exclude_notice_period', True)

    def compute_retention_bonus(self, payslip=None):
        """
        Public calculation entry point for Retention Bonus (RETENTION_BONUS).
        Validates minimum service period, employment status, and notice period exclusion.
        Returns payable amount in INR.
        """
        slip, employee, contract, eval_date, company = self._extract_context_data(payslip)
        if not contract:
            return 0.0

        bonus_amt = getattr(contract, 'retention_bonus', 0.0) or 0.0
        if bonus_amt <= 0:
            return 0.0

        # Active status check
        date_to = getattr(slip, 'date_to', eval_date) or eval_date
        if not self.is_employee_active(employee, date_to):
            return 0.0

        # Notice period exclusion check (Rule-level setting if is_bonus enabled, else company setting)
        exclude_notice = self._is_notice_period_excluded('RETENTION_BONUS', company)
        if exclude_notice and self.is_in_notice_period(employee, slip):
            _logger.info("[BonusService] Retention bonus 0.0 for employee %s: In Notice Period", employee.name)
            return 0.0

        # Minimum service period check
        min_months = company.hds_in_retention_min_service_months or 12
        join_date = False
        if getattr(contract, 'contract_date_start', False):
            join_date = contract.contract_date_start
        elif getattr(employee, 'contract_date_start', False):
            join_date = employee.contract_date_start
        elif getattr(contract, 'date_start', False):
            join_date = contract.date_start
        elif getattr(contract, 'date_version', False):
            join_date = contract.date_version
        elif getattr(employee, 'first_contract_date', False):
            join_date = employee.first_contract_date

        if not join_date:
            return 0.0

        service_days = (date_to - join_date).days
        required_days = int(min_months * 30.4375)
        if service_days < required_days:
            _logger.info(
                "[BonusService] Retention bonus 0.0 for employee %s: Service days %s < required %s",
                employee.name, service_days, required_days
            )
            return 0.0

        return bonus_amt
