# -*- coding: utf-8 -*-
from datetime import date
from dateutil.relativedelta import relativedelta
# pyrefly: ignore [missing-import]
from odoo import fields
from odoo.tools.translate import _# pyrefly: ignore [missing-import]
import logging

_logger = logging.getLogger(__name__)


class GratuityCalculationData:
    """
    Data Transfer Object (DTO) containing all collected and prepared data
    required for Gratuity Calculation. Pure data container passed to GratuityCalculator.
    """

    def __init__(
        self,
        employee_id=None,
        company_id=None,
        joining_date=None,
        separation_date=None,
        total_years=0,
        remaining_months=0,
        remaining_days=0,
        completed_years=0,
        last_drawn_basic=0.0,
        last_drawn_da=0.0,
        wage_base=0.0,
        days_multiplier=15.0,
        month_divisor=26.0,
        min_service_years=5.0,
        statutory_ceiling=2000000.0,
        is_death_or_disablement=False
    ):
        self.employee_id = employee_id
        self.company_id = company_id
        self.joining_date = joining_date
        self.separation_date = separation_date
        self.total_years = total_years
        self.remaining_months = remaining_months
        self.remaining_days = remaining_days
        self.completed_years = completed_years
        self.last_drawn_basic = last_drawn_basic
        self.last_drawn_da = last_drawn_da
        self.wage_base = wage_base
        self.days_multiplier = days_multiplier
        self.month_divisor = month_divisor
        self.min_service_years = min_service_years
        self.statutory_ceiling = statutory_ceiling
        self.is_death_or_disablement = is_death_or_disablement

    def to_dict(self):
        """Serialize data object into dictionary for audit logging and diagnostics."""
        return {
            'employee_id': self.employee_id,
            'company_id': self.company_id,
            'joining_date': str(self.joining_date) if self.joining_date else None,
            'separation_date': str(self.separation_date) if self.separation_date else None,
            'total_years': self.total_years,
            'remaining_months': self.remaining_months,
            'remaining_days': self.remaining_days,
            'completed_years': self.completed_years,
            'last_drawn_basic': float(self.last_drawn_basic),
            'last_drawn_da': float(self.last_drawn_da),
            'wage_base': float(self.wage_base),
            'days_multiplier': float(self.days_multiplier),
            'month_divisor': float(self.month_divisor),
            'min_service_years': float(self.min_service_years),
            'statutory_ceiling': float(self.statutory_ceiling),
            'is_death_or_disablement': self.is_death_or_disablement,
        }

    def __repr__(self):
        return (
            f"<GratuityCalculationData emp_id={self.employee_id} "
            f"completed_years={self.completed_years} wage_base={self.wage_base} "
            f"days_mult={self.days_multiplier} div={self.month_divisor} ceiling={self.statutory_ceiling}>"
        )


class GratuityDataService:
    """
    Enterprise Data Service for Hudson Indian Payroll Gratuity Module.
    Single Responsibility: Gather, extract, and prepare all input data required for gratuity calculation.
    Does NOT perform statutory validation or gratuity calculation.
    """

    PARAM_DAYS_MULTIPLIER = 'hds_in_gratuity_days_multiplier'
    PARAM_MONTH_DIVISOR = 'hds_in_gratuity_month_divisor'
    PARAM_MIN_SERVICE_YEARS = 'hds_in_gratuity_min_service_years'
    PARAM_STATUTORY_CEILING = 'hds_in_gratuity_statutory_ceiling'

    def __init__(self, env):
        self.env = env

    def prepare_calculation_data(
        self,
        employee,
        contract=None,
        separation_date=None,
        payslip=None,
        is_death_or_disablement=False,
        calc_date=None
    ):
        """
        Gathers all required input data for gratuity calculation and returns a structured DTO.

        :param employee: hr.employee recordset (required)
        :param contract: hr.version recordset (optional)
        :param separation_date: str or date (optional)
        :param payslip: hr.payslip recordset (optional)
        :param is_death_or_disablement: bool (optional)
        :param calc_date: str or date (optional)
        :return: GratuityCalculationData
        """
        if not employee:
            raise ValueError(_("Employee is required to prepare gratuity calculation data."))

        # 1. Resolve Contract if not provided
        resolved_contract = contract or self._resolve_active_contract(employee)

        # 2. Resolve Joining & Separation Dates
        joining_date = self._resolve_joining_date(employee, resolved_contract)
        resolved_sep_date = self._resolve_separation_date(employee, resolved_contract, separation_date, payslip)

        # 3. Resolve Rule Parameters first to know statutory minimum service years
        ref_date = calc_date or resolved_sep_date or fields.Date.today()
        params = self._resolve_rule_parameters(ref_date)
        min_service_years = params.get('min_service_years', 5.0)

        # 4. Calculate Service Duration (Section 4(1) continuous service guard on Section 4(2) rounding)
        duration_info = self._calculate_service_duration(
            joining_date,
            resolved_sep_date,
            min_service_years=min_service_years,
            is_death_or_disablement=is_death_or_disablement
        )

        # 5. Retrieve Last Drawn Salary Components (Basic + DA)
        salary_info = self._retrieve_last_drawn_salary(employee, resolved_contract, payslip)

        # 6. Construct Data Transfer Object
        return GratuityCalculationData(
            employee_id=employee.id,
            company_id=employee.company_id.id if employee.company_id else self.env.company.id,
            joining_date=joining_date,
            separation_date=resolved_sep_date,
            total_years=duration_info['total_years'],
            remaining_months=duration_info['remaining_months'],
            remaining_days=duration_info['remaining_days'],
            completed_years=duration_info['completed_years'],
            last_drawn_basic=salary_info['basic'],
            last_drawn_da=salary_info['da'],
            wage_base=salary_info['wage_base'],
            days_multiplier=params['days_multiplier'],
            month_divisor=params['month_divisor'],
            min_service_years=min_service_years,
            statutory_ceiling=params['statutory_ceiling'],
            is_death_or_disablement=is_death_or_disablement
        )

    def _resolve_active_contract(self, employee):
        """Finds the most relevant contract for the employee."""
        if getattr(employee, 'version_id', False):
            return employee.version_id
        contracts = self.env['hr.version'].search([
            ('employee_id', '=', employee.id)
        ], order='id desc', limit=1)
        return contracts or None

    def _resolve_joining_date(self, employee, contract=None):
        """Resolves the employee's original joining date."""
        if getattr(employee, 'joining_date', None):
            return fields.Date.from_string(employee.joining_date)
        if getattr(employee, 'first_contract_date', None):
            return fields.Date.from_string(employee.first_contract_date)
        if contract:
            if getattr(contract, 'contract_date_start', None):
                return fields.Date.from_string(contract.contract_date_start)
            if getattr(contract, 'date_start', None):
                return fields.Date.from_string(contract.date_start)
        if getattr(employee, 'create_date', None):
            return fields.Date.from_string(employee.create_date)
        return None

    def _resolve_separation_date(self, employee, contract=None, explicit_date=None, payslip=None):
        """Resolves the separation date with priority order: explicit -> employee -> contract -> payslip."""
        if explicit_date:
            return fields.Date.from_string(explicit_date)
        if getattr(employee, 'departure_date', None):
            return fields.Date.from_string(employee.departure_date)
        if contract and getattr(contract, 'date_end', None):
            return fields.Date.from_string(contract.date_end)
        if payslip and getattr(payslip, 'date_to', None):
            return fields.Date.from_string(payslip.date_to)
        return fields.Date.today()

    def _calculate_service_duration(self, joining_date, separation_date, min_service_years=5.0, is_death_or_disablement=False):
        """
        Calculates service duration and completed service years under Payment of Gratuity Act 1972.
        - Section 4(1): Requires 5 full continuous years of service (waived for death/disablement).
        - Section 4(2): > 6 months in a fraction year counts as 1 full completed year ONLY AFTER
          the employee has completed mandatory 5 years of service or under death/disablement waiver.
        """
        if not joining_date or not separation_date or separation_date < joining_date:
            return {'total_years': 0, 'remaining_months': 0, 'remaining_days': 0, 'completed_years': 0}

        # Inclusive end date: separation date is worked and paid under statutory rules
        end_date = separation_date + relativedelta(days=1)
        rdelta = relativedelta(end_date, joining_date)
        total_years = max(0, rdelta.years)
        remaining_months = max(0, rdelta.months)
        remaining_days = max(0, rdelta.days)

        is_eligible_for_rounding = (total_years >= min_service_years) or is_death_or_disablement
        if is_eligible_for_rounding and (remaining_months > 6 or (remaining_months == 6 and remaining_days > 0)):
            completed_years = total_years + 1
        else:
            completed_years = total_years

        return {
            'total_years': total_years,
            'remaining_months': remaining_months,
            'remaining_days': remaining_days,
            'completed_years': completed_years,
        }

    def _retrieve_last_drawn_salary(self, employee, contract=None, payslip=None):
        """
        Retrieves last drawn Basic Salary and Dearness Allowance (DA).
        Prioritizes unprorated contract wage rate under Payment of Gratuity Act 1972 Section 4(2).
        Falls back to payslip lines only if contract values are missing or zero.
        """
        basic = 0.0
        da = 0.0

        # Method A: Extract unprorated rate of wages from Contract Breakdown (Primary Statutory Source)
        if contract:
            basic = float(getattr(contract, 'basic_salary', 0.0) or getattr(contract, 'wage', 0.0) or 0.0)
            da = float(getattr(contract, 'da', 0.0) or getattr(contract, 'da_amount', 0.0) or 0.0)

        # Method B: Fallback to Payslip Lines ONLY if contract wage base is missing or zero
        if (basic + da) <= 0.0 and payslip and getattr(payslip, 'line_ids', None):
            line_basic = payslip.line_ids.filtered(lambda l: l.code == 'BASIC')
            if line_basic:
                basic = float(line_basic[0].total)
            line_da = payslip.line_ids.filtered(lambda l: l.code == 'DA')
            if line_da:
                da = float(line_da[0].total)

        wage_base = basic + da
        return {
            'basic': basic,
            'da': da,
            'wage_base': wage_base,
        }

    def _resolve_rule_parameters(self, calc_date):
        """Resolves all 4 gratuity statutory rule parameters using Rule Parameter lookup engine."""
        rule_param_obj = self.env['hr.rule.parameter']

        def _get_param(code, default_val):
            try:
                val = rule_param_obj._get_parameter_value(code, calc_date)
                return float(val)
            except Exception as e:
                _logger.warning("Could not resolve rule parameter '%s' for date %s: %s. Using default %s.",
                                code, calc_date, str(e), default_val)
                return float(default_val)

        return {
            'days_multiplier': _get_param(self.PARAM_DAYS_MULTIPLIER, 15.0),
            'month_divisor': _get_param(self.PARAM_MONTH_DIVISOR, 26.0),
            'min_service_years': _get_param(self.PARAM_MIN_SERVICE_YEARS, 5.0),
            'statutory_ceiling': _get_param(self.PARAM_STATUTORY_CEILING, 2000000.0),
        }
