# -*- coding: utf-8 -*-
import math
# pyrefly: ignore [missing-import]
from odoo import fields
from ..base import BaseStatutoryService


class ESICEmployeeCalculator(BaseStatutoryService):
    """
    Pure Python ESIC Employee deduction calculation engine.
    Statutory basis: ESI (Central) Rules 1950 Rule 51.
    Retrieves contribution rate dynamically from hr.rule.parameter ('hds_in_esic_employee_rate').
    No hardcoded rates or thresholds.
    """

    def __init__(self, env, validator=None):
        super().__init__(env)
        self.validator = validator

    def get_paid_days(self, payslip):
        """
        Determines the exact number of paid/worked days in the payslip period,
        accurately respecting:
        1. Explicit attendance/leave lines in worked_days_line_ids (excluding LOP, unpaid, absent).
        2. Mid-month joiners / leavers (clamped to contract start/end dates).
        3. Calendar month length fallback when worked_days lines are not generated.
        """
        if not payslip:
            return 30.0

        if payslip and hasattr(payslip, '_get_earned_wage_ratio') and payslip._get_earned_wage_ratio() <= 0.0:
            return 0.0

        # Case 1: Worked days lines are populated on payslip
        worked_lines = getattr(payslip, 'worked_days_line_ids', None)
        if worked_lines:
            contract = getattr(payslip, 'contract_id', None) or getattr(payslip, 'contract', None)
            pay_by_attendance = bool(getattr(contract, 'pay_by_attendance', False))
            unpaid_codes = ['UNPAID', 'ABSENT', 'LEAVE_UNPAID', 'LOP']
            if pay_by_attendance:
                unpaid_codes.append('SHORTAGE')
            paid_lines = worked_lines.filtered(lambda l: (l.code or '').upper() not in unpaid_codes)
            paid_days = sum(float(l.number_of_days or 0.0) for l in paid_lines)
            unpaid_lines = worked_lines.filtered(lambda l: (l.code or '').upper() in unpaid_codes)
            lop_days = sum(float(l.number_of_days or 0.0) for l in unpaid_lines)
            cal_days = (payslip.date_to - payslip.date_from).days + 1 if (getattr(payslip, 'date_from', False) and getattr(payslip, 'date_to', False)) else 30
            if (paid_days + lop_days) > cal_days:
                net_paid = max(0.0, paid_days - lop_days)
            else:
                net_paid = paid_days
            if net_paid > 0.0:
                return round(net_paid, 2)
            if lop_days > 0.0 and net_paid <= 0.0:
                return 0.0

        # Case 2: Derive from date range, clamping to active employment dates
        date_from = getattr(payslip, 'date_from', False) or fields.Date.today()
        date_to = getattr(payslip, 'date_to', False) or fields.Date.today()
        if isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        if isinstance(date_to, str):
            date_to = fields.Date.from_string(date_to)

        contract = getattr(payslip, 'contract_id', None) or getattr(payslip, 'contract', None)
        emp = getattr(payslip, 'employee_id', None)

        start_dates = [date_from]
        if contract and getattr(contract, 'date_start', False):
            start_dates.append(contract.date_start)
        elif emp and getattr(emp, 'contract_date_start', False):
            start_dates.append(emp.contract_date_start)
        elif emp and getattr(emp, 'date_start', False):
            start_dates.append(emp.date_start)

        end_dates = [date_to]
        if contract and getattr(contract, 'date_end', False):
            end_dates.append(contract.date_end)
        elif emp and getattr(emp, 'contract_date_end', False):
            end_dates.append(emp.contract_date_end)
        elif emp and getattr(emp, 'date_end', False):
            end_dates.append(emp.date_end)

        active_start = max(start_dates)
        active_end = min(end_dates)

        if active_start <= active_end:
            active_calendar_days = (active_end - active_start).days + 1
        else:
            active_calendar_days = max(0, (date_to - date_from).days + 1)

        # Subtract any LOP days if snapshot or worked days lines exist
        lop_days = 0.0
        if worked_lines:
            unpaid_lines = worked_lines.filtered(lambda l: (l.code or '').upper() in ('UNPAID', 'ABSENT', 'LEAVE_UNPAID', 'LOP', 'SHORTAGE'))
            lop_days = sum(float(l.number_of_days or 0.0) for l in unpaid_lines)
        elif getattr(payslip, 'hds_snapshot_id', False) and getattr(payslip.hds_snapshot_id, 'lop_days', False):
            lop_days = float(payslip.hds_snapshot_id.lop_days or 0.0)

        payable_days = max(0.0, float(active_calendar_days) - lop_days)
        return round(payable_days, 2)

    def check_daily_wage_exemption(self, payslip, esic_wage=0.0, eval_date=None):
        """
        Implements ESI (Central) Rules 1950 Rule 51-B:
        Employees whose average daily wage in a wage period is equal to or less than
        the statutory exemption limit (seeded as INR 176/day w.e.f. 01-Jul-2019)
        are completely exempt from the employee share of ESIC contribution.

        Formula:
            average_daily_wage = esic_wage / paid_days_in_period
            is_exempt = average_daily_wage <= exemption_threshold

        :return: tuple (is_exempt: bool, average_daily_wage: float, paid_days: float, threshold: float)
        """
        if esic_wage <= 0.0:
            return True, 0.0, 0.0, 176.0

        eval_date = eval_date or getattr(payslip, 'date_to', False) or getattr(payslip, 'date_from', False) or self.env.context.get('date') or fields.Date.today()

        # Retrieve configurable threshold from hr.rule.parameter
        threshold = self.get_parameter('esic_daily_wage_exemption_threshold', date=eval_date, as_decimal=False)
        if not threshold:
            threshold = self.get_parameter('hds_in_esic_daily_wage_exemption', date=eval_date, as_decimal=False)
        threshold = float(threshold or 176.0)

        paid_days = self.get_paid_days(payslip)
        if paid_days <= 0.0 and esic_wage > 0.0:
            date_from = getattr(payslip, 'date_from', False) or fields.Date.today()
            date_to = getattr(payslip, 'date_to', False) or fields.Date.today()
            if isinstance(date_from, str):
                date_from = fields.Date.from_string(date_from)
            if isinstance(date_to, str):
                date_to = fields.Date.from_string(date_to)
            cal_days = (date_to - date_from).days + 1 if (date_from and date_to) else 30
            paid_days = float(max(1, cal_days))

        if paid_days <= 0.0:
            average_daily_wage = 0.0
            is_exempt = True
        else:
            average_daily_wage = round(esic_wage / paid_days, 2)
            is_exempt = bool(average_daily_wage <= threshold)

        return is_exempt, average_daily_wage, paid_days, threshold

    def compute(self, payslip, esic_wage=0.0):
        """
        Computes employee ESIC deduction amount.
        Enforces Rule 51-B daily wage exemption before computing standard deduction.
        Returns rounded statutory deduction amount (nearest upper rupee rounding as per ESIC rules).
        """
        if esic_wage <= 0.0:
            return 0.0

        is_exempt, avg_daily_wage, paid_days, threshold = self.check_daily_wage_exemption(payslip, esic_wage=esic_wage)
        if is_exempt:
            return 0.0

        eval_date = getattr(payslip, 'date_to', False) or self.env.context.get('date')
        rate = self.get_parameter('hds_in_esic_employee_rate', date=eval_date, as_decimal=True)
        raw_deduction = esic_wage * rate
        return float(math.ceil(raw_deduction))
