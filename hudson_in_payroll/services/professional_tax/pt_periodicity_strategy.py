# -*- coding: utf-8 -*-
import logging
from abc import ABC, abstractmethod
from datetime import date
# pyrefly: ignore [missing-import]
from odoo import fields
from ..payroll.payroll_wage_aggregation_service import PayrollWageAggregationService

_logger = logging.getLogger(__name__)


PT_COUNTED_PAYSLIP_STATES = ('verify', 'done', 'paid')


class AbstractPTPeriodicityStrategy(ABC):
    """
    Abstract Base Class for Professional Tax Periodicity Strategies.
    Encapsulates window resolution, prior deduction tracking, and dynamic payroll distribution math.
    """

    @abstractmethod
    def get_periodicity_code(self) -> str:
        """Returns the periodicity code matching pt.state.slab (e.g., 'monthly', 'half_yearly')."""
        pass

    @abstractmethod
    def resolve_aggregation_window(self, eval_date: date) -> tuple:
        """Resolves period (start_date, end_date) for a given evaluation date."""
        pass

    @abstractmethod
    def calculate_wage_basis(
        self,
        env,
        employee,
        eval_date: date,
        current_slip=None,
        current_slip_gross=0.0,
        company=None,
        period_schedule=None,
        is_simulation=False
    ) -> float:
        """Aggregates salary basis across period window."""
        pass

    def should_deduct(self, eval_date=None, slab=None, schedule=None, employee=None) -> bool:
        """
        Determines whether PT should be deducted on eval_date.
        Supports both pt.period.schedule and legacy/mock slab records.
        """
        if isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)
        if not eval_date:
            eval_date = fields.Date.today()

        m = eval_date.month

        if schedule:
            from .pt_period_config_service import PTPeriodScheduleService
            return PTPeriodScheduleService(False).should_deduct(schedule, eval_date=eval_date, employee=employee)

        if slab:
            sched_type = getattr(slab, 'deduction_schedule_type', None) or 'every_payroll'
            if sched_type == 'every_payroll':
                return True
            if sched_type == 'end_of_period':
                win_start, win_end = self.resolve_aggregation_window(eval_date)
                return m == win_end.month
            if sched_type == 'beginning_of_period':
                win_start, win_end = self.resolve_aggregation_window(eval_date)
                return m == win_start.month
            if sched_type == 'specific_month':
                ded_m = getattr(slab, 'deduction_month', None)
                if ded_m:
                    return m == int(str(ded_m).strip())
                return False

        return True

    def get_period_already_deducted(self, env, employee, start_date: date, eval_date: date, current_slip=None) -> float:
        """
        Queries all payslips for the employee within the period window [start_date, eval_date]
        and sums up already deducted PT amount lines.
        Only counts payslips in verify/done/paid states (never draft or cancelled).
        """
        if not employee or not start_date or not eval_date:
            return 0.0

        if isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)
        if not eval_date:
            eval_date = fields.Date.today()

        m_first_date = date(eval_date.year, eval_date.month, 1)

        domain = [
            ('employee_id', '=', employee.id),
            ('state', 'in', PT_COUNTED_PAYSLIP_STATES),
            ('date_from', '>=', start_date),
            ('date_from', '<=', eval_date),
        ]
        curr_id = getattr(current_slip, 'id', False)
        if current_slip and isinstance(curr_id, int):
            domain.append(('id', '!=', curr_id))

        slips = env['hr.payslip'].search(domain)
        if not slips:
            return 0.0

        total_pt = 0.0
        for slip in slips:
            for line in slip.line_ids:
                if line.code in ('PT', 'HDS_IN_PT') or getattr(line.category_id, 'code', '') == 'PT':
                    total_pt += abs(line.total or 0.0)

        return float(total_pt)

    def get_carried_forward_liability(
        self,
        env,
        employee,
        eval_date: date,
        period_schedule=None,
        company=None,
        current_slip=None,
        return_interim=False
    ):
        """
        Determines uncollected Professional Tax liability from prior statutory periods.
        If salary was zero in the statutory deduction month (e.g. full LOP at cycle end),
        the uncollected liability carries forward to be recovered in upcoming eligible months.

        :param return_interim: If True, returns tuple (uncollected_prior, deducted_interim_in_current_period)
        :return: float uncollected_prior or tuple if return_interim=True
        """
        from datetime import timedelta
        from .pt_period_config_service import PTPeriodScheduleService
        from .professional_tax_slab_service import ProfessionalTaxSlabService
        from .pt_calculator import PTCalculator
        from ..payroll.payroll_wage_aggregation_service import PayrollWageAggregationService
        # pyrefly: ignore [missing-import]
        from odoo.tools import float_round

        if not employee or self.get_periodicity_code() == 'monthly':
            return (0.0, 0.0) if return_interim else 0.0

        if isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)
        if not eval_date:
            eval_date = fields.Date.today()

        sched_service = PTPeriodScheduleService(env)
        start_d, _ = sched_service.resolve_period_window(
            schedule=period_schedule, eval_date=eval_date, periodicity=self.get_periodicity_code()
        )

        prior_eval_date = start_d - timedelta(days=1)
        prior_sched = sched_service.resolve_schedule(
            period_schedule.state_id if period_schedule else False,
            company=company or (employee.company_id if employee else False),
            eval_date=prior_eval_date
        )
        prior_start_d, prior_end_d = sched_service.resolve_period_window(
            schedule=prior_sched, eval_date=prior_eval_date, periodicity=self.get_periodicity_code()
        )

        # STRICT BOUNDARY GUARD: Prior period must strictly end before the current period starts.
        # This prevents circular lookup of current-cycle earnings if schedule resolution fails.
        if not prior_start_d or not prior_end_d or prior_end_d >= start_d:
            return (0.0, 0.0) if return_interim else 0.0

        # Aggregate prior period earned wages
        agg_service = PayrollWageAggregationService(env)
        prior_earned_wage = agg_service.get_aggregated_wage(
            employee=employee,
            start_date=prior_start_d,
            end_date=prior_end_d,
            category_code="GROSS",
            company=company
        )
        if prior_earned_wage <= 0.0:
            return (0.0, 0.0) if return_interim else 0.0

        # Check min_service_days for prior period
        if prior_sched and getattr(prior_sched, 'min_service_days', 0) > 0:
            meets_min, _, _ = sched_service.check_min_service_days(prior_sched, employee, eval_date=prior_end_d)
            if not meets_min:
                return (0.0, 0.0) if return_interim else 0.0

        # Resolve prior period statutory slab and liability
        state = prior_sched.state_id if (prior_sched and prior_sched.state_id) else (period_schedule.state_id if period_schedule else False)
        if not state:
            from ..payroll.work_location_service import PayrollWorkLocationService
            state = PayrollWorkLocationService(env).get_work_state(employee)

        slab_service = ProfessionalTaxSlabService(env)
        slab_result = slab_service.get_applicable_slab(
            employee=employee,
            salary=prior_earned_wage,
            eval_date=prior_end_d,
            company=company or (employee.company_id if employee else False),
            state=state,
            periodicity=self.get_periodicity_code()
        )
        if not slab_result or not slab_result.slab_record:
            return (0.0, 0.0) if return_interim else 0.0

        calc_result = PTCalculator(env).calculate(slab=slab_result, eval_date=prior_end_d)
        prior_liability = float(calc_result.pt_amount or 0.0)
        if prior_liability <= 0.0:
            return (0.0, 0.0) if return_interim else 0.0

        # Prior period deducted in [prior_start_d, prior_end_d]
        deducted_in_prior = self.get_period_already_deducted(
            env, employee=employee, start_date=prior_start_d, eval_date=prior_end_d
        )

        # Carried-forward deductions already recovered in current period before eval_date
        interim_start = prior_end_d + timedelta(days=1)
        deducted_interim = 0.0
        if interim_start <= eval_date:
            deducted_interim = self.get_period_already_deducted(
                env, employee=employee, start_date=interim_start, eval_date=eval_date, current_slip=current_slip
            )

        uncollected_prior = max(0.0, prior_liability - (deducted_in_prior + deducted_interim))
        uncollected_prior = float_round(uncollected_prior, precision_digits=2)
        deducted_interim = float_round(deducted_interim, precision_digits=2)

        if return_interim:
            return (uncollected_prior, deducted_interim)
        return uncollected_prior

    def calculate_payroll_deduction(
        self,
        env,
        employee,
        period_liability: float,
        eval_date: date,
        current_slip=None,
        period_schedule=None,
        is_simulation=False,
        current_slip_gross=0.0
    ) -> float:
        """
        Generic, configuration-driven algorithm calculating exact PT deduction for current payroll.
        Formula:
        1. Resolve carried_forward liability from prior uncollected cycles (e.g. zero wage at cycle end)
        2. Resolve already_deducted in current period (distinguishing interim carry-forward recoveries)
        3. if End of Period -> deduct full remaining_period_liability + carried_forward in deduction month
        4. if Not End of Period -> if carried_forward > 0, deduct carried_forward in upcoming eligible month; else 0
        5. if Every Payroll -> deduct remaining_liability / remaining_eligible_payrolls
        """
        from .pt_period_config_service import PTPeriodScheduleService
        # pyrefly: ignore [missing-import]
        from odoo.tools import float_round

        if is_simulation:
            # In simulation mode (e.g. Salary Revision preview), return standard statutory slab liability
            # without deducting prior actual payslips from the database
            return float_round(period_liability or 0.0, precision_digits=2)

        sched_service = PTPeriodScheduleService(env)

        # Resolve period window
        start_d, end_d = sched_service.resolve_period_window(
            schedule=period_schedule, eval_date=eval_date, periodicity=self.get_periodicity_code()
        )

        # Calculate already deducted PT in this period
        already_deducted = self.get_period_already_deducted(
            env, employee=employee, start_date=start_d, eval_date=eval_date, current_slip=current_slip
        )

        # Carried forward liability from prior uncollected cycles (and interim recovery tracking)
        company = getattr(current_slip, 'company_id', False) or (employee.company_id if employee else False)
        carried_forward, deducted_interim = self.get_carried_forward_liability(
            env, employee=employee, eval_date=eval_date, period_schedule=period_schedule,
            company=company, current_slip=current_slip, return_interim=True
        )

        # Amount deducted in current period that was specifically for current period liability
        already_deducted_current_period = max(0.0, already_deducted - deducted_interim)

        # Resolve strategy and distribution method
        strategy = (period_schedule.deduction_strategy if period_schedule else 'every_payroll') or 'every_payroll'
        dist_method = (period_schedule.distribution_method if period_schedule else False) or ('full_amount' if strategy in ('end_of_period', 'specific_month', 'beginning_of_period') else 'equal_distribution')

        # For quarterly, half-yearly, and annual, force full_amount deduction (no equal fractional monthly distribution)
        if self.get_periodicity_code() in ('quarterly', 'half_yearly', 'annual'):
            dist_method = 'full_amount'
            if strategy == 'every_payroll':
                strategy = 'end_of_period'

        should_deduct = sched_service.should_deduct(period_schedule, eval_date=eval_date, employee=employee)

        # Strategy 1: End of Period / Specific Month / Beginning of Period / Full Amount
        if strategy in ('end_of_period', 'specific_month', 'beginning_of_period') or dist_method == 'full_amount':
            if should_deduct:
                remaining_period = max(float(period_liability or 0.0) - already_deducted_current_period, 0.0)
                total_due = remaining_period + carried_forward
                return float_round(total_due, precision_digits=2)
            else:
                # In non-deduction months, if employee has carried-forward liability and positive salary
                if carried_forward > 0.0:
                    return float_round(carried_forward, precision_digits=2)
                return 0.0

        # Strategy 2: Every Payroll / Equal Distribution
        remaining_liability = max(float(period_liability or 0.0) - already_deducted_current_period, 0.0) + carried_forward
        if remaining_liability <= 0.0:
            return 0.0

        rem_payrolls = sched_service.calculate_remaining_payrolls(
            employee=employee, period_start_date=start_d, period_end_date=end_d, eval_date=eval_date
        )

        if rem_payrolls <= 1:
            # Final eligible payroll of period absorbs exact residual amount for perfect reconciliation
            return float_round(remaining_liability, precision_digits=2)

        raw_deduction = remaining_liability / rem_payrolls
        return float_round(raw_deduction, precision_digits=2)


class MonthlyPTStrategy(AbstractPTPeriodicityStrategy):
    """Monthly Professional Tax Strategy."""

    def get_periodicity_code(self) -> str:
        return 'monthly'

    def resolve_aggregation_window(self, eval_date: date) -> tuple:
        if isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)
        if not eval_date:
            eval_date = fields.Date.today()
        year = eval_date.year
        month = eval_date.month
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        return (date(year, month, 1), date(year, month, last_day))

    def calculate_wage_basis(
        self,
        env,
        employee,
        eval_date: date,
        current_slip=None,
        current_slip_gross=0.0,
        company=None,
        period_schedule=None,
        is_simulation=False
    ) -> float:
        return float(current_slip_gross or 0.0)


class HalfYearlyPTStrategy(AbstractPTPeriodicityStrategy):
    """Half-Yearly Professional Tax Strategy."""

    def get_periodicity_code(self) -> str:
        return 'half_yearly'

    def resolve_aggregation_window(self, eval_date: date) -> tuple:
        if isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)
        if not eval_date:
            eval_date = fields.Date.today()

        month = eval_date.month
        year = eval_date.year

        if 4 <= month <= 9:
            start_d = date(year, 4, 1)
            end_d = date(year, 9, 30)
        elif month >= 10:
            start_d = date(year, 10, 1)
            end_d = date(year + 1, 3, 31)
        else:
            start_d = date(year - 1, 10, 1)
            end_d = date(year, 3, 31)

        return (start_d, end_d)

    def calculate_wage_basis(
        self,
        env,
        employee,
        eval_date: date,
        current_slip=None,
        current_slip_gross=0.0,
        company=None,
        period_schedule=None,
        is_simulation=False
    ) -> float:
        if is_simulation:
            return float(current_slip_gross or 0.0) * 6.0
        if period_schedule:
            from .pt_period_config_service import PTPeriodScheduleService
            sched_service = PTPeriodScheduleService(env)
            start_d, end_d = sched_service.resolve_period_window(period_schedule, eval_date=eval_date)
        else:
            start_d, end_d = self.resolve_aggregation_window(eval_date)

        agg_service = PayrollWageAggregationService(env)
        return agg_service.get_aggregated_wage(
            employee=employee,
            start_date=start_d,
            end_date=end_d,
            category_code="GROSS",
            company=company,
            current_slip=current_slip,
            current_slip_gross=current_slip_gross
        )


class QuarterlyPTStrategy(AbstractPTPeriodicityStrategy):
    """Quarterly Professional Tax Strategy."""

    def get_periodicity_code(self) -> str:
        return 'quarterly'

    def resolve_aggregation_window(self, eval_date: date) -> tuple:
        if isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)
        if not eval_date:
            eval_date = fields.Date.today()

        month = eval_date.month
        year = eval_date.year

        if 4 <= month <= 6:
            return (date(year, 4, 1), date(year, 6, 30))
        elif 7 <= month <= 9:
            return (date(year, 7, 1), date(year, 9, 30))
        elif 10 <= month <= 12:
            return (date(year, 10, 1), date(year, 12, 31))
        else:
            return (date(year, 1, 1), date(year, 3, 31))

    def calculate_wage_basis(
        self,
        env,
        employee,
        eval_date: date,
        current_slip=None,
        current_slip_gross=0.0,
        company=None,
        period_schedule=None,
        is_simulation=False
    ) -> float:
        if is_simulation:
            return float(current_slip_gross or 0.0) * 3.0
        if period_schedule:
            from .pt_period_config_service import PTPeriodScheduleService
            sched_service = PTPeriodScheduleService(env)
            start_d, end_d = sched_service.resolve_period_window(period_schedule, eval_date=eval_date)
        else:
            start_d, end_d = self.resolve_aggregation_window(eval_date)

        agg_service = PayrollWageAggregationService(env)
        return agg_service.get_aggregated_wage(
            employee=employee,
            start_date=start_d,
            end_date=end_d,
            category_code="GROSS",
            company=company,
            current_slip=current_slip,
            current_slip_gross=current_slip_gross
        )


class AnnualPTStrategy(AbstractPTPeriodicityStrategy):
    """Annual Professional Tax Strategy."""

    def get_periodicity_code(self) -> str:
        return 'annual'

    def resolve_aggregation_window(self, eval_date: date) -> tuple:
        if isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)
        if not eval_date:
            eval_date = fields.Date.today()

        year = eval_date.year
        if eval_date.month >= 4:
            return (date(year, 4, 1), date(year + 1, 3, 31))
        else:
            return (date(year - 1, 4, 1), date(year, 3, 31))

    def calculate_wage_basis(
        self,
        env,
        employee,
        eval_date: date,
        current_slip=None,
        current_slip_gross=0.0,
        company=None,
        period_schedule=None,
        is_simulation=False
    ) -> float:
        if is_simulation:
            return float(current_slip_gross or 0.0) * 12.0
        if period_schedule:
            from .pt_period_config_service import PTPeriodScheduleService
            sched_service = PTPeriodScheduleService(env)
            start_d, end_d = sched_service.resolve_period_window(period_schedule, eval_date=eval_date)
        else:
            start_d, end_d = self.resolve_aggregation_window(eval_date)

        agg_service = PayrollWageAggregationService(env)
        return agg_service.get_aggregated_wage(
            employee=employee,
            start_date=start_d,
            end_date=end_d,
            category_code="GROSS",
            company=company,
            current_slip=current_slip,
            current_slip_gross=current_slip_gross
        )


class PTPeriodicityStrategyRegistry:
    """
    Factory & Registry for Professional Tax Periodicity Strategies.
    Decouples ProfessionalTaxService from periodicity-specific code branches.
    """

    _strategies = {
        'monthly': MonthlyPTStrategy(),
        'half_yearly': HalfYearlyPTStrategy(),
        'quarterly': QuarterlyPTStrategy(),
        'annual': AnnualPTStrategy(),
    }

    @classmethod
    def get_strategy(cls, periodicity_code) -> AbstractPTPeriodicityStrategy:
        code = str(periodicity_code).strip().lower() if periodicity_code else 'monthly'
        return cls._strategies.get(code, cls._strategies['monthly'])
