# -*- coding: utf-8 -*-
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from odoo import fields# pyrefly: ignore [missing-import]
from odoo.tools.translate import _# pyrefly: ignore [missing-import]
import logging

_logger = logging.getLogger(__name__)


class GratuityValidationResult:
    """
    Structured data container representing Gratuity Statutory Eligibility Validation Result.
    Provides complete transparency for audit logging, reporting, and debugging.
    """

    def __init__(
        self,
        is_eligible=False,
        reason="",
        joining_date=None,
        separation_date=None,
        total_years=0,
        remaining_months=0,
        remaining_days=0,
        completed_years=0,
        min_required_years=5.0,
        is_death_or_disablement=False
    ):
        self.is_eligible = is_eligible
        self.reason = reason
        self.joining_date = joining_date
        self.separation_date = separation_date
        self.total_years = total_years
        self.remaining_months = remaining_months
        self.remaining_days = remaining_days
        self.completed_years = completed_years
        self.min_required_years = min_required_years
        self.is_death_or_disablement = is_death_or_disablement

    def to_dict(self):
        """Serialize validation result into dictionary for audit trail / JSON logging."""
        return {
            'is_eligible': self.is_eligible,
            'reason': self.reason,
            'joining_date': str(self.joining_date) if self.joining_date else None,
            'separation_date': str(self.separation_date) if self.separation_date else None,
            'total_years': self.total_years,
            'remaining_months': self.remaining_months,
            'remaining_days': self.remaining_days,
            'completed_years': self.completed_years,
            'min_required_years': self.min_required_years,
            'is_death_or_disablement': self.is_death_or_disablement,
        }

    def __repr__(self):
        return f"<GratuityValidationResult eligible={self.is_eligible} completed_years={self.completed_years} min_req={self.min_required_years} reason='{self.reason}'>"


class GratuityValidator:
    """
    Enterprise Gratuity Eligibility Validator for Hudson Indian Payroll.
    Single Responsibility: Validate whether an employee satisfies the statutory eligibility
    requirements under the Payment of Gratuity Act 1972 before calculation occurs.
    """

    PARAM_MIN_SERVICE_YEARS = 'hds_in_gratuity_min_service_years'

    def __init__(self, env):
        self.env = env

    def validate(
        self,
        employee,
        contract=None,
        separation_date=None,
        is_death_or_disablement=False,
        calc_date=None
    ):
        """
        Main entry point to perform statutory gratuity eligibility validation.

        :param employee: hr.employee recordset (required)
        :param contract: hr.version recordset (optional, for joining date fallback)
        :param separation_date: str or date (optional, employee separation date)
        :param is_death_or_disablement: bool (optional, statutory exception flag)
        :param calc_date: str or date (optional, reference date for rule parameters)
        :return: GratuityValidationResult
        """
        if not employee:
            return GratuityValidationResult(
                is_eligible=False,
                reason=_("No employee provided for gratuity eligibility validation.")
            )

        company = employee.company_id or self.env.company

        # Validation 1: Company Configuration Enablement Check
        if not company or not getattr(company, 'hds_in_enable_gratuity', False):
            return GratuityValidationResult(
                is_eligible=False,
                reason=_("Gratuity is disabled for company '%s'.") % (company.name if company else 'Unknown')
            )

        # Validation 2: Resolve Joining Date
        joining_date = self._resolve_joining_date(employee, contract)
        if not joining_date:
            return GratuityValidationResult(
                is_eligible=False,
                reason=_("Employee joining date is missing or invalid.")
            )

        # Validation 3: Determine Separation Date
        separation_date = self._resolve_separation_date(employee, contract, separation_date)
        if not separation_date:
            return GratuityValidationResult(
                is_eligible=False,
                joining_date=joining_date,
                reason=_("Separation date cannot be determined for gratuity eligibility validation.")
            )

        if separation_date < joining_date:
            return GratuityValidationResult(
                is_eligible=False,
                joining_date=joining_date,
                separation_date=separation_date,
                reason=_("Separation date (%s) cannot be earlier than joining date (%s).") % (separation_date, joining_date)
            )

        # Validation 4: Resolve Statutory Minimum Service Years via Rule Parameter Engine
        ref_date = calc_date or separation_date or fields.Date.today()
        min_required_years = self._resolve_min_service_years_parameter(ref_date)

        # Validation 5: Calculate Service Duration (Payment of Gratuity Act Rules)
        # Note: Under Section 4(1), continuous service of not less than 5 full continuous years
        # is mandatory for eligibility. Section 4(2) fraction rounding (> 6 months = 1 year)
        # applies ONLY to compute the payout multiplier AFTER completing the mandatory 5 years,
        # or under the statutory waiver for death/disablement.
        is_death_or_disablement_applicable = bool(
            is_death_or_disablement or self._check_death_disablement_exception(employee, contract)
        )

        duration_info = self._calculate_service_duration(
            joining_date,
            separation_date,
            min_service_years=min_required_years,
            is_death_or_disablement=is_death_or_disablement_applicable
        )
        total_years = duration_info['total_years']
        remaining_months = duration_info['remaining_months']
        remaining_days = duration_info['remaining_days']
        completed_years = duration_info['completed_years']

        # Validation 6 & 7: Check Statutory Eligibility & Future-Ready Exceptions
        if is_death_or_disablement_applicable:
            return GratuityValidationResult(
                is_eligible=True,
                reason=_("Eligible for gratuity under Death/Disablement exemption (minimum service requirement waived per Section 4(1) proviso)."),
                joining_date=joining_date,
                separation_date=separation_date,
                total_years=total_years,
                remaining_months=remaining_months,
                remaining_days=remaining_days,
                completed_years=completed_years,
                min_required_years=min_required_years,
                is_death_or_disablement=True
            )

        if self._check_continuous_service_exception(employee, contract, duration_info):
            return GratuityValidationResult(
                is_eligible=True,
                reason=_("Eligible for gratuity under continuous service exception rules."),
                joining_date=joining_date,
                separation_date=separation_date,
                total_years=total_years,
                remaining_months=remaining_months,
                remaining_days=remaining_days,
                completed_years=completed_years,
                min_required_years=min_required_years
            )

        # Statutory Eligibility Gate (Section 4(1)):
        # An employee must render continuous service for not less than 5 full years.
        # Section 4(2) fraction rounding rule cannot be used to bridge service below 5 years.
        if total_years >= min_required_years:
            if completed_years > total_years:
                reason = _("Eligible for gratuity. Completed %s full years of continuous service (statutory minimum: %s years; payout calculated on %s years per Section 4(2)).") % (total_years, min_required_years, completed_years)
            else:
                reason = _("Eligible for gratuity. Completed %s years of service (minimum required: %s years).") % (completed_years, min_required_years)
            return GratuityValidationResult(
                is_eligible=True,
                reason=reason,
                joining_date=joining_date,
                separation_date=separation_date,
                total_years=total_years,
                remaining_months=remaining_months,
                remaining_days=remaining_days,
                completed_years=completed_years,
                min_required_years=min_required_years
            )

        return GratuityValidationResult(
            is_eligible=False,
            reason=_("Ineligible for gratuity. Completed %s years and %s months of continuous service, which is below the statutory minimum required %s full years under Section 4(1).") % (total_years, remaining_months, int(min_required_years) if isinstance(min_required_years, (int, float)) and min_required_years.is_integer() else min_required_years),
            joining_date=joining_date,
            separation_date=separation_date,
            total_years=total_years,
            remaining_months=remaining_months,
            remaining_days=remaining_days,
            completed_years=completed_years,
            min_required_years=min_required_years
        )

    def _resolve_joining_date(self, employee, contract=None):
        """Resolves employee joining date from employee record or contract."""
        if getattr(employee, 'joining_date', None):
            return fields.Date.from_string(employee.joining_date)
        if getattr(employee, 'first_contract_date', None):
            return fields.Date.from_string(employee.first_contract_date)
        if contract:
            if getattr(contract, 'contract_date_start', None):
                return fields.Date.from_string(contract.contract_date_start)
            if getattr(contract, 'date_start', None):
                return fields.Date.from_string(contract.date_start)
        return None

    def _resolve_separation_date(self, employee, contract=None, explicit_date=None):
        """Resolves employee separation/departure date."""
        if explicit_date:
            return fields.Date.from_string(explicit_date)
        if getattr(employee, 'departure_date', None):
            return fields.Date.from_string(employee.departure_date)
        if contract and getattr(contract, 'date_end', None):
            return fields.Date.from_string(contract.date_end)
        return None

    def _calculate_service_duration(self, joining_date, separation_date, min_service_years=5.0, is_death_or_disablement=False):
        """
        Calculates service duration and completed years under Payment of Gratuity Act 1972.
        - Section 4(1): Mandatory threshold of 5 full continuous years (waived for death/disablement).
        - Section 4(2): Payout rounding rule - any period exceeding 6 months in a fraction year
          counts as 1 full completed year ONLY AFTER the employee has satisfied Section 4(1) eligibility
          (or under the death/disablement statutory waiver).
        """
        if not joining_date or not separation_date or separation_date < joining_date:
            return {
                'total_years': 0,
                'remaining_months': 0,
                'remaining_days': 0,
                'completed_years': 0,
            }

        # Inclusive end date: separation date is worked and paid under statutory rules
        end_date = separation_date + relativedelta(days=1)
        rdelta = relativedelta(end_date, joining_date)
        total_years = max(0, rdelta.years)
        remaining_months = max(0, rdelta.months)
        remaining_days = max(0, rdelta.days)

        # Statutory Rounding Rule (Section 4(2)):
        # Fraction rounding (> 6 months = 1 year) applies ONLY if the employee has completed
        # the statutory minimum service years (Section 4(1)) or has a statutory waiver (death/disablement).
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

    def _resolve_min_service_years_parameter(self, calc_date):
        """Resolves statutory minimum service years via Rule Parameter engine."""
        try:
            val = self.env['hr.rule.parameter']._get_parameter_value(
                self.PARAM_MIN_SERVICE_YEARS,
                calc_date
            )
            return float(val)
        except (KeyError, ValueError, AttributeError) as e:
            _logger.warning("Parameter resolution fallback for %s on %s: %s. Defaulting to 5.0 years.",
                            self.PARAM_MIN_SERVICE_YEARS, calc_date, str(e))
            return 5.0
        except Exception as e:
            _logger.error("Unexpected error resolving %s for date %s: %s. Falling back to 5.0 years.",
                          self.PARAM_MIN_SERVICE_YEARS, calc_date, str(e), exc_info=True)
            return 5.0

    # -------------------------------------------------------------------------
    # EXTENSION POINTS FOR FUTURE STATUTORY AMENDMENTS & SPECIAL RULES
    # -------------------------------------------------------------------------
    def _check_death_disablement_exception(self, employee, contract=None):
        """Extension point: Payment of Gratuity Act Section 4(1) proviso for death or disablement."""
        departure_reason = getattr(employee, 'departure_reason_id', None)
        if departure_reason and getattr(departure_reason, 'name', '') in ('Death', 'Permanent Disablement'):
            return True
        return False

    def _check_continuous_service_exception(self, employee, contract=None, duration_info=None):
        """Extension point: Payment of Gratuity Act Section 2A continuous service rules."""
        return False
