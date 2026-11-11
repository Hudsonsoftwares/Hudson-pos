# -*- coding: utf-8 -*-
import datetime
import logging
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class ESICContributionPeriodService(BaseStatutoryService):
    """
    Pure Python service for ESIC statutory Contribution Period determination.
    Enforces Regulation 31 continuity: If an employee's wage on the first day
    of an active Contribution Period is <= ceiling, ESIC deductions continue
    through the end of that 6-month period regardless of mid-period increments.
    """

    def get_contribution_period_bounds(self, ref_date, company=None):
        """
        Returns statutory (period_start_date, period_end_date) for a given reference date.
        Respects company ESIC contribution period configuration:
        - 'apr_sep_oct_mar' (Standard / Set A): April 1 to September 30 & October 1 to March 31
        - 'jul_dec_jan_jun' (Set B): July 1 to December 31 & January 1 to June 30
        - 'may_oct_nov_apr' (Set C): May 1 to October 31 & November 1 to April 30
        - 'custom': Configured start and end months
        """
        import calendar
        if not ref_date:
            ref_date = datetime.date.today()
        elif isinstance(ref_date, str):
            ref_date = datetime.datetime.strptime(ref_date, '%Y-%m-%d').date()

        comp = company or self.env.company

        # 1. Resolve from master model esic.contribution.period
        schedule = False
        if hasattr(self.env, '__getitem__') and 'esic.contribution.period' in self.env:
            domain = [
                ('active', '=', True),
                '|', ('date_from', '=', False), ('date_from', '<=', ref_date),
                '|', ('date_to', '=', False), ('date_to', '>=', ref_date),
                '|', ('company_id', '=', False), ('company_id', '=', comp.id),
            ]
            schedule = self.env['esic.contribution.period'].search(domain, order='company_id desc, id desc', limit=1)

        if schedule:
            p1_start_m = int(getattr(schedule, 'period1_start_month', 4) or 4)
            p1_end_m = int(getattr(schedule, 'period1_end_month', 9) or 9)
            p2_start_m = int(getattr(schedule, 'period2_start_month', 10) or 10)
            p2_end_m = int(getattr(schedule, 'period2_end_month', 3) or 3)
        else:
            # Fallback to company field or standard April-September & October-March
            cycle = getattr(comp, 'hds_in_esic_contribution_period_type', 'apr_sep_oct_mar') or 'apr_sep_oct_mar'
            if cycle == 'jul_dec_jan_jun':
                p1_start_m, p1_end_m = 7, 12
                p2_start_m, p2_end_m = 1, 6
            elif cycle == 'may_oct_nov_apr':
                p1_start_m, p1_end_m = 5, 10
                p2_start_m, p2_end_m = 11, 4
            elif cycle == 'custom':
                p1_start_m = int(getattr(comp, 'hds_in_esic_custom_period1_start_month', 4) or 4)
                p1_end_m = int(getattr(comp, 'hds_in_esic_custom_period1_end_month', 9) or 9)
                p2_start_m = int(getattr(comp, 'hds_in_esic_custom_period2_start_month', 10) or 10)
                p2_end_m = int(getattr(comp, 'hds_in_esic_custom_period2_end_month', 3) or 3)
            else:
                p1_start_m, p1_end_m = 4, 9
                p2_start_m, p2_end_m = 10, 3

        year = ref_date.year
        month = ref_date.month

        def _in_range(m, s, e):
            if s <= e:
                return s <= m <= e
            else:
                return m >= s or m <= e

        if _in_range(month, p1_start_m, p1_end_m):
            s_month, e_month = p1_start_m, p1_end_m
        else:
            s_month, e_month = p2_start_m, p2_end_m

        if s_month <= e_month:
            start_date = datetime.date(year, s_month, 1)
            last_day = calendar.monthrange(year, e_month)[1]
            end_date = datetime.date(year, e_month, last_day)
        else:
            if month >= s_month:
                start_date = datetime.date(year, s_month, 1)
                last_day = calendar.monthrange(year + 1, e_month)[1]
                end_date = datetime.date(year + 1, e_month, last_day)
            else:
                start_date = datetime.date(year - 1, s_month, 1)
                last_day = calendar.monthrange(year, e_month)[1]
                end_date = datetime.date(year, e_month, last_day)

        return start_date, end_date

    def get_effective_wage_on_date(self, employee, eval_date):
        """
        Determines effective gross wage on a given historical or future date by inspecting
        past payslips, active contract wage, and adjusting for salary revisions.
        """
        if not employee:
            return 0.0

        emp_id = False
        if getattr(employee, '_origin', None) and employee._origin.id:
            emp_id = employee._origin.id
        elif employee.id and isinstance(employee.id, int):
            emp_id = employee.id
        elif hasattr(employee.id, 'origin') and employee.id.origin:
            emp_id = employee.id.origin

        if not emp_id:
            return 0.0

        if isinstance(eval_date, str):
            eval_date = datetime.datetime.strptime(eval_date, '%Y-%m-%d').date()

        # 1. Inspect confirmed payslip on eval_date if available
        slips = self.env['hr.payslip'].search([
            ('employee_id', '=', emp_id),
            ('date_from', '<=', eval_date),
            ('date_to', '>=', eval_date),
            ('state', 'not in', ('cancel',)),
        ], limit=1)
        if slips:
            g_line = slips.line_ids.filtered(lambda l: l.category_id.code == 'GROSS')
            if g_line and g_line.total > 0:
                return g_line.total
            w_line = slips.line_ids.filtered(lambda l: l.code == 'ESIC_WAGE')
            if w_line and w_line.total > 0:
                return w_line.total

        # 2. Check approved salary revisions
        if emp_id:
            # A. Revision effective on or before eval_date (gives new_wage as of eval_date)
            eff_revisions = self.env['hds.in.salary.revision'].search([
                ('employee_id', '=', emp_id),
                ('effective_date', '<=', eval_date),
                ('state', '=', 'approved')
            ], order='effective_date desc, id desc', limit=1)
            if eff_revisions and eff_revisions.new_wage > 0:
                return eff_revisions.new_wage

            # B. Revision effective after eval_date (gives old_wage before the hike)
            future_revisions = self.env['hds.in.salary.revision'].search([
                ('employee_id', '=', emp_id),
                ('effective_date', '>', eval_date),
                ('state', '=', 'approved')
            ], order='effective_date asc, id asc', limit=1)
            if future_revisions and future_revisions.old_wage > 0:
                return future_revisions.old_wage

        # 3. Check contract versions
        contracts = self.env['hr.version'].search([
            ('employee_id', '=', emp_id),
        ])
        if not contracts:
            return 0.0

        # Sort contracts by date (date_start or date_version)
        valid_contracts = [c for c in contracts if (
            ((c.date_start and c.date_start <= eval_date) or (c.date_version and c.date_version <= eval_date))
            and (c.wage or 0.0) > 0
        )]
        if not valid_contracts:
            valid_contracts = [c for c in contracts if (c.wage or 0.0) > 0]
        if not valid_contracts:
            valid_contracts = contracts
        sorted_contracts = sorted(valid_contracts, key=lambda c: (c.date_start or c.date_version or datetime.date.min, c.id), reverse=True)
        return sorted_contracts[0].wage or 0.0

    def is_covered_for_contribution_period(self, employee, eval_date=None, current_wage=None):
        """
        Single Source of Truth for ESIC Contribution Period coverage under Regulation 31 of
        ESI (General) Regulations, 1950.
        
        Statutory Law:
        If an employee's gross wage at the beginning of a Contribution Period (April 1 or October 1,
        or on date of joining if joined mid-period) is <= wage ceiling (Rs. 21,000, or Rs. 25,000 for PWD),
        the employee continues to be covered and deductions MUST continue until the END of that
        contribution period (September 30 or March 31), even if salary is revised / increased above
        the wage ceiling in the middle of the contribution period.
        
        Coverage terminates ONLY at the start of the subsequent contribution period if wages
        continue to exceed the ceiling.
        """
        if not employee:
            return False

        if eval_date is None:
            eval_date = datetime.date.today()
        elif isinstance(eval_date, str):
            eval_date = datetime.datetime.strptime(eval_date, '%Y-%m-%d').date()

        # 1. Determine Contribution Period Bounds
        company = getattr(employee, 'company_id', None) or self.env.company
        period_start, period_end = self.get_contribution_period_bounds(eval_date, company=company)

        # 2. Determine Applicable Statutory Wage Ceiling
        if getattr(employee, 'hds_in_is_pwd', False):
            ceiling = self.get_parameter('hds_in_esic_pwd_wage_ceiling', date=eval_date, as_decimal=False)
        else:
            ceiling = self.get_parameter('hds_in_esic_wage_ceiling', date=eval_date, as_decimal=False)

        emp_id = False
        if getattr(employee, '_origin', None) and employee._origin.id:
            emp_id = employee._origin.id
        elif employee.id and isinstance(employee.id, int):
            emp_id = employee.id
        elif hasattr(employee.id, 'origin') and employee.id.origin:
            emp_id = employee.id.origin

        # 3. Check Evidence A: Existing Payslips in this Contribution Period
        # If the employee already had ANY payslip within this contribution period with ESIC deduction
        # or wage <= ceiling, Regulation 31 mandates coverage for ALL remaining months in this period!
        if emp_id:
            slips = self.env['hr.payslip'].search([
                ('employee_id', '=', emp_id),
                ('date_from', '>=', period_start),
                ('date_to', '<=', period_end),
                ('state', 'not in', ('cancel',)),
            ], order='date_from asc')
            for slip in slips:
                # Did this payslip have ESIC deducted?
                has_esic = any(l.code in ('ESIC_EE', 'ESIC_WAGE') and l.total != 0 for l in slip.line_ids)
                if has_esic:
                    _logger.info("[ESIC] Employee %s has prior payslip %s in period (%s to %s) with ESIC -> Covered till %s",
                                 employee.name, slip.name, period_start, period_end, period_end)
                    return True
                # Or was the wage in that payslip <= ceiling?
                gross_line = slip.line_ids.filtered(lambda l: l.category_id.code == 'GROSS')
                slip_gross = gross_line.total if gross_line else (slip.net_wage or 0.0)
                if 0 < slip_gross <= ceiling:
                    _logger.info("[ESIC] Employee %s had payslip %s with wage %s <= ceiling in period -> Covered till %s",
                                 employee.name, slip.name, slip_gross, period_end)
                    return True

        # 4. Check Evidence B: Salary Revisions within this Contribution Period
        # If employee received a salary hike during this period, check old_wage before the hike!
        if emp_id:
            revisions = self.env['hds.in.salary.revision'].search([
                ('employee_id', '=', emp_id),
                ('effective_date', '>', period_start),
                ('effective_date', '<=', period_end),
                ('state', '=', 'approved')
            ], order='effective_date asc')
            if revisions:
                first_rev = revisions[0]
                if 0 < first_rev.old_wage <= ceiling:
                    _logger.info("[ESIC] Employee %s had salary hike in period from old_wage %s <= ceiling -> Covered till %s",
                                 employee.name, first_rev.old_wage, period_end)
                    return True

        # 5. Check Evidence C: Wage on the First Day of the Contribution Period
        period_start_wage = self.get_effective_wage_on_date(employee, period_start)
        if 0 < period_start_wage <= ceiling:
            _logger.info("[ESIC] Employee %s wage on period_start %s was %s <= ceiling %s -> Covered.",
                         employee.name, period_start, period_start_wage, ceiling)
            return True

        # 6. Check Evidence D: Mid-Period Joiner (joining wage <= ceiling)
        contracts = self.env['hr.version'].search([('employee_id', '=', emp_id)]) if emp_id else False
        if contracts:
            join_contracts = [c for c in contracts if c.date_start and period_start <= c.date_start <= period_end]
            if join_contracts:
                earliest_contract = sorted(join_contracts, key=lambda c: c.date_start)[0]
                if 0 < earliest_contract.wage <= ceiling:
                    _logger.info("[ESIC] Employee %s joined on %s with wage %s <= ceiling -> Covered till %s",
                                 employee.name, earliest_contract.date_start, earliest_contract.wage, period_end)
                    return True

        # 7. Check Evidence E: Current Active ESIC Enrollment & Mid-Period Wage Increase
        # If employee was already active in ESIC (hds_in_esic_applicable = True and IP status != 'exempt' / 'resigned'),
        # and evaluating a date within the active period, a salary increase cannot drop them mid-period!
        today = datetime.date.today()
        today_start, today_end = self.get_contribution_period_bounds(today, company=company)
        if period_start == today_start and period_end == today_end:
            origin_emp = getattr(employee, '_origin', employee)
            was_applicable = getattr(employee, 'hds_in_esic_applicable', False) or getattr(origin_emp, 'hds_in_esic_applicable', False)
            status = getattr(employee, 'hds_in_esic_ip_status', None) or getattr(origin_emp, 'hds_in_esic_ip_status', None)
            exit_reason = getattr(employee, 'hds_in_esic_exit_reason', None) or getattr(origin_emp, 'hds_in_esic_exit_reason', None)

            if was_applicable and status not in ('exempt', 'resigned') and exit_reason != 'resigned':
                _logger.info("[ESIC] Employee %s was active in current running period -> Regulation 31 continuity till %s",
                             employee.name, period_end)
                return True

        # 8. Fallback check against wage
        wage_to_check = period_start_wage if period_start_wage > 0 else (current_wage or 0.0)
        result = (0 < wage_to_check <= ceiling)
        _logger.info(
            "[ESIC] period_start=%s period_start_wage=%s ceiling=%s result=%s",
            period_start,
            period_start_wage,
            ceiling,
            result
        )
        return result
