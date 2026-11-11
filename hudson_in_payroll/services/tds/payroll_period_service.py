# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import fields
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class PayrollPeriodService(BaseStatutoryService):
    """
    Phase 10 Service: Payroll Period Service.
    Dynamically determines the remaining payroll periods in the Financial Year (including current evaluation month).
    Supports:
    - Standard Financial Year (12 monthly periods April through March)
    - Dynamic countdown of remaining periods under Section 192 (12 - eval_fy_idx + 1)
    - Mid-year joiners (taking employee joining date / contract date_start into account)
    - Early resignations / departures before FY end (taking departure_date / contract date_end into account)
    """

    def _resolve_employee_joining_date(self, employee):
        """
        Resolves employee's joining date or first employment start date.
        Supports employee helper methods, Odoo 19 hr.version, version_id, contract_date_start, date_start, and all employee joining fields.
        """
        if not employee:
            return None

        # Check if employee has dedicated joining date helper method
        if hasattr(employee, '_get_employee_joining_date'):
            try:
                emp_join = employee._get_employee_joining_date()
                if emp_join:
                    return fields.Date.from_string(emp_join) if isinstance(emp_join, str) else emp_join
            except Exception:
                pass

        for fname in ('contract_date_start', 'joining_date', 'date_of_joining', 'hds_in_doj',
                      'first_contract_date', 'hds_in_esic_joining_date', 'hds_in_pf_joining_date'):
            val = getattr(employee, fname, None)
            if val:
                return fields.Date.from_string(val) if isinstance(val, str) else val

        # Check employee contract (hr.version in Odoo 19 or legacy hr.contract)
        contract = getattr(employee, 'version_id', False) or getattr(employee, 'contract_id', False)
        if not contract and hasattr(employee, 'contract_ids') and employee.contract_ids:
            open_contracts = employee.contract_ids.filtered(lambda c: getattr(c, 'state', False) == 'open')
            contract = open_contracts[0] if open_contracts else employee.contract_ids[0]
        if not contract:
            ContractModel = self.env.get('hr.version') or self.env.get('hr.contract')
            if ContractModel is not None:
                contracts = ContractModel.search([('employee_id', '=', employee.id)])
                if contracts:
                    open_contracts = contracts.filtered(lambda c: getattr(c, 'state', False) == 'open')
                    contract = open_contracts[0] if open_contracts else contracts[0]

        if contract:
            for dfname in ('contract_date_start', 'date_start', 'date_version'):
                val = getattr(contract, dfname, None)
                if val:
                    return fields.Date.from_string(val) if isinstance(val, str) else val

        if getattr(employee, 'date_start', None):
            return fields.Date.from_string(employee.date_start) if isinstance(employee.date_start, str) else employee.date_start

        # Fallback: check earliest payslip date for this employee
        first_slip = self.env['hr.payslip'].search([
            ('employee_id', '=', employee.id),
        ], order='date_from asc', limit=1)
        if first_slip and first_slip.date_from:
            return fields.Date.from_string(first_slip.date_from)

        return None

    def _resolve_employee_departure_date(self, employee):
        """
        Resolves employee's departure date, resignation date, or contract end date.
        """
        if not employee:
            return None
        for fname in ('departure_date', 'end_date', 'resignation_date'):
            val = getattr(employee, fname, None)
            if val:
                return fields.Date.from_string(val) if isinstance(val, str) else val

        if 'final.settlement' in self.env:
            settlement = self.env['final.settlement'].search([
                ('employee_id', '=', employee.id),
                ('state', '!=', 'cancel'),
            ], order='id desc', limit=1)
            if settlement and settlement.last_working_day:
                return fields.Date.from_string(settlement.last_working_day) if isinstance(settlement.last_working_day, str) else settlement.last_working_day

        if 'hr.resignation' in self.env:
            resignation = self.env['hr.resignation'].search([
                ('employee_id', '=', employee.id),
                ('state', 'in', ['approved', 'done']),
            ], order='id desc', limit=1)
            if resignation and getattr(resignation, 'approved_revealing_date', False):
                return fields.Date.from_string(resignation.approved_revealing_date) if isinstance(resignation.approved_revealing_date, str) else resignation.approved_revealing_date

        contract = getattr(employee, 'version_id', False) or getattr(employee, 'contract_id', False)
        if not contract and hasattr(employee, 'contract_ids') and employee.contract_ids:
            open_contracts = employee.contract_ids.filtered(lambda c: getattr(c, 'state', False) == 'open')
            contract = open_contracts[0] if open_contracts else employee.contract_ids[0]
        if not contract:
            ContractModel = self.env.get('hr.version') or self.env.get('hr.contract')
            if ContractModel is not None:
                contracts = ContractModel.search([('employee_id', '=', employee.id)])
                if contracts:
                    open_contracts = contracts.filtered(lambda c: getattr(c, 'state', False) == 'open')
                    contract = open_contracts[0] if open_contracts else contracts[0]

        if contract:
            for dfname in ('contract_date_end', 'date_end'):
                val = getattr(contract, dfname, None)
                if val:
                    return fields.Date.from_string(val) if isinstance(val, str) else val

        return None

    def calculate_remaining_periods(self, employee, financial_year, eval_date=None, payslip=None):
        """
        Calculates remaining payroll periods in Financial Year (inclusive of current month).
        Always respects employee joining date rather than assuming 12 months.
        For final settlement payslips, returns 1 period to withhold remaining annual liability in full.

        :param employee: hr.employee record
        :param financial_year: tds.financial.year record
        :param eval_date: Date (optional payslip eval_date / date_to)
        :param payslip: hr.payslip record (optional)
        :return: int (Remaining payroll periods, min 1)
        """
        # Final settlement payslip check: 100% of remaining tax liability must be deducted on the final payslip
        if payslip:
            struct = getattr(payslip, 'struct_id', False)
            struct_code = (getattr(struct, 'code', '') or '').upper() if struct else ''
            struct_name = (getattr(struct, 'name', '') or '').upper() if struct else ''
            if (struct and (struct_code in ('FINAL_SETTLEMENT_STRUCT', 'FINAL_SETT', 'FINAL_SETTLEMENT') or 'SETTLEMENT' in struct_code or 'SETTLEMENT' in struct_name or 'FINAL' in struct_name)) or self.env.context.get('is_final_settlement'):
                return 1
            if 'final.settlement' in self.env:
                if self.env['final.settlement'].search_count([('payslip_id', '=', payslip.id), ('state', '!=', 'cancel')]):
                    return 1
        elif employee and 'final.settlement' in self.env and eval_date:
            if self.env['final.settlement'].search_count([
                ('employee_id', '=', employee.id), ('state', '!=', 'cancel'), ('last_working_day', '<=', eval_date)
            ]):
                return 1

        eval_date = eval_date or fields.Date.today()
        if isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)

        fy_start = financial_year.start_date if financial_year else None
        fy_end = financial_year.end_date if financial_year else None

        if not fy_start or not fy_end:
            joining_date = self._resolve_employee_joining_date(employee)
            if joining_date and eval_date:
                ed = fields.Date.from_string(eval_date) if isinstance(eval_date, str) else eval_date
                rem = (12 - ed.month + 1) if ed else 12
                return max(1, rem)
            return 12

        if eval_date > fy_end:
            return 1

        fy_start_year = fy_start.year
        fy_start_month = fy_start.month

        # Calculate 1-based FY month index for eval_date (1 for April, ..., 12 for March)
        if eval_date < fy_start:
            eval_fy_idx = 1
        else:
            eval_year = eval_date.year
            eval_month = eval_date.month
            elapsed_months = (eval_year - fy_start_year) * 12 + (eval_month - fy_start_month) + 1
            eval_fy_idx = min(12, max(1, elapsed_months))

        # Check joining date
        joining_date = self._resolve_employee_joining_date(employee)
        if joining_date and joining_date > fy_start:
            join_year = joining_date.year
            join_month = joining_date.month
            join_elapsed = (join_year - fy_start_year) * 12 + (join_month - fy_start_month) + 1
            join_fy_idx = min(12, max(1, join_elapsed))
        else:
            join_fy_idx = 1

        # If joining date was not resolved on employee/contract, but employee declared previous employer income:
        if join_fy_idx == 1 and employee and financial_year:
            from .previous_employer_income_service import PreviousEmployerIncomeService
            prev_svc = PreviousEmployerIncomeService(self.env)
            prev_res = prev_svc.aggregate_previous_employer_income(employee, financial_year)
            if prev_res.has_declaration and (prev_res.taxable_salary > 0 or prev_res.tds_deducted > 0):
                earliest_slip = self.env['hr.payslip'].search([
                    ('employee_id', '=', employee.id),
                    ('date_from', '>=', fy_start),
                    ('date_to', '<=', fy_end)
                ], order='date_from asc', limit=1)
                if earliest_slip and earliest_slip.date_from:
                    s_date = fields.Date.from_string(earliest_slip.date_from)
                    join_elapsed = (s_date.year - fy_start_year) * 12 + (s_date.month - fy_start_month) + 1
                    join_fy_idx = min(12, max(1, join_elapsed))
                elif eval_date:
                    ed = fields.Date.from_string(eval_date) if isinstance(eval_date, str) else eval_date
                    join_elapsed = (ed.year - fy_start_year) * 12 + (ed.month - fy_start_month) + 1
                    join_fy_idx = min(12, max(1, join_elapsed))

        # Effective start index for remaining periods:
        # If eval_date is earlier than joining date, countdown starts from joining month.
        # Otherwise, starts from current evaluation month (inclusive).
        start_fy_idx = max(eval_fy_idx, join_fy_idx)

        # Check departure / contract end date
        departure_date = self._resolve_employee_departure_date(employee)
        if departure_date and departure_date < fy_end:
            dep_year = departure_date.year
            dep_month = departure_date.month
            dep_elapsed = (dep_year - fy_start_year) * 12 + (dep_month - fy_start_month) + 1
            dep_fy_idx = min(12, max(1, dep_elapsed))
            end_fy_idx = min(12, max(start_fy_idx, dep_fy_idx))
        else:
            end_fy_idx = 12

        remaining_periods = max(1, end_fy_idx - start_fy_idx + 1)

        _logger.info(
            "[PAYROLL PERIOD SERVICE] Employee '%s' | FY '%s' | Eval FY Index: %s | "
            "Join FY Index: %s | End FY Index: %s | Remaining Periods: %s",
            employee.name if employee else 'N/A',
            financial_year.name if financial_year else 'N/A',
            eval_fy_idx, join_fy_idx, end_fy_idx, remaining_periods
        )
        return remaining_periods

    def calculate_total_periods_in_fy(self, employee, financial_year, eval_date=None):
        """
        Calculates total employment months for the employee in this Financial Year.
        - Existing employee (joined on/before FY start): 12 months (or up to departure date).
        - Mid-year joiner (joined after FY start): count of months from joining month to FY end (or departure date).
        """
        if not financial_year or not financial_year.start_date or not financial_year.end_date:
            joining_date = self._resolve_employee_joining_date(employee)
            if joining_date:
                ed = fields.Date.from_string(eval_date) if eval_date and isinstance(eval_date, str) else (eval_date or fields.Date.today())
                if ed and joining_date > ed:
                    rem = 12 - joining_date.month + 1 if joining_date.month <= 3 else 12 - (joining_date.month - 3) + 1
                    return max(1, min(12, rem))
            return 12

        fy_start = financial_year.start_date
        fy_end = financial_year.end_date
        fy_start_year = fy_start.year
        fy_start_month = fy_start.month

        joining_date = self._resolve_employee_joining_date(employee)
        if joining_date and joining_date > fy_start:
            join_year = joining_date.year
            join_month = joining_date.month
            join_elapsed = (join_year - fy_start_year) * 12 + (join_month - fy_start_month) + 1
            join_fy_idx = min(12, max(1, join_elapsed))
        else:
            join_fy_idx = 1

        # If joining date was not resolved on employee/contract, check if previous employer income is declared
        if join_fy_idx == 1 and employee and financial_year:
            from .previous_employer_income_service import PreviousEmployerIncomeService
            prev_svc = PreviousEmployerIncomeService(self.env)
            prev_res = prev_svc.aggregate_previous_employer_income(employee, financial_year)
            if prev_res.has_declaration and (prev_res.taxable_salary > 0 or prev_res.tds_deducted > 0):
                earliest_slip = self.env['hr.payslip'].search([
                    ('employee_id', '=', employee.id),
                    ('date_from', '>=', fy_start),
                    ('date_to', '<=', fy_end)
                ], order='date_from asc', limit=1)
                if earliest_slip and earliest_slip.date_from:
                    s_date = fields.Date.from_string(earliest_slip.date_from)
                    join_elapsed = (s_date.year - fy_start_year) * 12 + (s_date.month - fy_start_month) + 1
                    join_fy_idx = min(12, max(1, join_elapsed))
                elif eval_date:
                    ed = fields.Date.from_string(eval_date) if isinstance(eval_date, str) else eval_date
                    join_elapsed = (ed.year - fy_start_year) * 12 + (ed.month - fy_start_month) + 1
                    join_fy_idx = min(12, max(1, join_elapsed))

        departure_date = self._resolve_employee_departure_date(employee)
        if departure_date and departure_date < fy_end:
            dep_year = departure_date.year
            dep_month = departure_date.month
            dep_elapsed = (dep_year - fy_start_year) * 12 + (dep_month - fy_start_month) + 1
            dep_fy_idx = min(12, max(1, dep_elapsed))
            end_fy_idx = min(12, max(join_fy_idx, dep_fy_idx))
        else:
            end_fy_idx = 12

        total_periods = max(1, end_fy_idx - join_fy_idx + 1)
        return total_periods

