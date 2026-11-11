# -*- coding: utf-8 -*-
import logging
from odoo import fields
from ..payroll.work_location_service import PayrollWorkLocationService
from .professional_tax_slab_service import ProfessionalTaxSlabService

_logger = logging.getLogger(__name__)


class PTValidationResult:
    """
    Structured Result Container representing an employee Professional Tax eligibility validation evaluation.
    Decoupled from tax calculations and payslip mutations.
    """

    def __init__(self, is_valid, validation_status, failure_reason="", resolved_state=None, matched_slab=None):
        self.is_valid = is_valid
        self.validation_status = validation_status
        self.failure_reason = failure_reason
        self.resolved_state = resolved_state
        self.matched_slab = matched_slab

    @property
    def is_eligible(self):
        return self.is_valid

    def to_dict(self):
        """Returns a structured dictionary representation of the validation result."""
        return {
            'is_valid': self.is_valid,
            'validation_status': self.validation_status,
            'failure_reason': self.failure_reason,
            'resolved_state_id': self.resolved_state.id if self.resolved_state else False,
            'resolved_state_name': self.resolved_state.name if self.resolved_state else False,
            'matched_slab': self.matched_slab.to_dict() if self.matched_slab else False,
        }

    def __repr__(self):
        return (
            f"<PTValidationResult status={self.validation_status} valid={self.is_valid} "
            f"state={self.resolved_state.name if self.resolved_state else None} "
            f"reason='{self.failure_reason}'>"
        )


class PTValidator:
    """
    Domain Validator for Professional Tax (PT) Statutory Employee Eligibility.
    Single Responsibility: Validate company configuration, employee work state resolution,
    and Professional Tax State Slab existence and active effective period.

    Validation Chain:
    1. Company Configuration: Ensure hds_in_enable_professional_tax is True for company.
    2. Work State Resolution: Confirm employee work location resolves to a state via PayrollWorkLocationService.
    3. PT Slab Resolution: Query ProfessionalTaxSlabService for an active matching PT state slab.
    4. Active & Effective Date Verification: Confirm slab is active and effective on evaluation date.
    """

    def __init__(self, env):
        self.env = env
        self.location_service = PayrollWorkLocationService(env)
        self.slab_service = ProfessionalTaxSlabService(env)

    def validate(self, employee=None, salary=0.0, eval_date=None, company=None, state=None, gender=None, periodicity=None, strategy=None, period_schedule=None):
        """
        Validates employee eligibility for Professional Tax deduction.

        :param employee: hr.employee recordset (optional if state & company provided)
        :param salary: float (monthly or aggregated gross salary)
        :param eval_date: datetime.date or str (defaults to today)
        :param company: res.company recordset (optional)
        :param state: res.country.state recordset (optional explicit state override)
        :param gender: str (optional gender criteria)
        :param periodicity: str (optional periodicity override)
        :param strategy: AbstractPTPeriodicityStrategy instance (optional)
        :return: PTValidationResult instance
        """
        # 1. Resolve Company & Validate Company Configuration
        target_company = company
        if not target_company and employee:
            target_company = employee.company_id
        if not target_company:
            target_company = self.env.company

        if not getattr(target_company, 'hds_in_enable_professional_tax', True):
            reason = f"Professional Tax (PT) is disabled for company '{target_company.name}'."
            _logger.info("PTValidator: %s", reason)
            return PTValidationResult(
                is_valid=False,
                validation_status='DISABLED_COMPANY',
                failure_reason=reason
            )

        # 1b. Validate Employee PT Applicability
        if employee and hasattr(employee, 'hds_in_pt_applicable') and not employee.hds_in_pt_applicable:
            reason = f"Professional Tax (PT) is disabled for employee '{employee.name}'."
            _logger.info("PTValidator: %s", reason)
            return PTValidationResult(
                is_valid=False,
                validation_status='DISABLED_EMPLOYEE',
                failure_reason=reason
            )

        # 2. Resolve Statutory Work State
        target_state = state
        if not target_state and employee:
            target_state = self.location_service.get_work_state(employee)

        if not target_state:
            emp_name = getattr(employee, 'name', 'Unknown')
            reason = f"Statutory work state could not be resolved for employee '{emp_name}'."
            _logger.info("PTValidator: %s", reason)
            return PTValidationResult(
                is_valid=False,
                validation_status='MISSING_WORK_STATE',
                failure_reason=reason
            )

        # 3. Resolve Evaluation Date
        if not eval_date:
            eval_date = fields.Date.today()
        elif isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)

        # 4. Resolve Matching PT Slab
        slab_result = self.slab_service.get_applicable_slab(
            employee=employee,
            salary=salary,
            eval_date=eval_date,
            company=target_company,
            state=target_state,
            gender=gender,
            periodicity=periodicity
        )

        if not slab_result or not slab_result.slab_record:
            reason = f"No matching active Professional Tax slab found for state '{target_state.name}', company '{target_company.name}', salary ₹{salary:,.2f} on date {eval_date}."
            _logger.warning("PTValidator: %s", reason)
            return PTValidationResult(
                is_valid=False,
                validation_status='NO_MATCHING_SLAB',
                failure_reason=reason,
                resolved_state=target_state
            )

        slab_rec = slab_result.slab_record

        # 6. Verify Active Status
        if not slab_rec.active:
            reason = f"Matched Professional Tax slab '{slab_rec.name}' is archived/inactive."
            _logger.info("PTValidator: %s", reason)
            return PTValidationResult(
                is_valid=False,
                validation_status='INACTIVE_SLAB',
                failure_reason=reason,
                resolved_state=target_state,
                matched_slab=slab_result
            )

        # 7. Verify Effective Date Bounds
        if slab_rec.date_from and eval_date < slab_rec.date_from:
            reason = f"Evaluation date ({eval_date}) is earlier than effective start date ({slab_rec.date_from}) for slab '{slab_rec.name}'."
            _logger.info("PTValidator: %s", reason)
            return PTValidationResult(
                is_valid=False,
                validation_status='EXPIRED_SLAB',
                failure_reason=reason,
                resolved_state=target_state,
                matched_slab=slab_result
            )

        if slab_rec.date_to and eval_date > slab_rec.date_to:
            reason = f"Evaluation date ({eval_date}) is later than effective end date ({slab_rec.date_to}) for slab '{slab_rec.name}'."
            _logger.info("PTValidator: %s", reason)
            return PTValidationResult(
                is_valid=False,
                validation_status='EXPIRED_SLAB',
                failure_reason=reason,
                resolved_state=target_state,
                matched_slab=slab_result
            )

        # 8. Validation Success
        return PTValidationResult(
            is_valid=True,
            validation_status='VALID',
            failure_reason="Employee is eligible for Professional Tax deduction.",
            resolved_state=target_state,
            matched_slab=slab_result
        )

