# -*- coding: utf-8 -*-


class EligibilityValidationResult:
    """Data container for statutory LWF eligibility validation results."""
    def __init__(self, is_eligible, reason="", rate_config=None, headcount=0, min_threshold=0, is_scheduled_month=False):
        self.is_eligible = is_eligible
        self.reason = reason
        self.rate_config = rate_config
        self.headcount = headcount
        self.min_threshold = min_threshold
        self.is_scheduled_month = is_scheduled_month


class LWFEligibilityValidator:
    """
    Validator for statutory Labour Welfare Fund (LWF) employee eligibility.
    Single Responsibility: Evaluate state rate existence, headcount threshold,
    and deduction schedule month eligibility.
    """

    def __init__(self, env):
        self.env = env

    def validate(self, employee, state, rate_config, eval_date, establishment_headcount=0, contract=None, net_salary=None, is_employer=False):
        """
        Validates statutory employee eligibility for LWF deduction/contribution.

        :param employee: hr.employee recordset
        :param state: res.country.state recordset
        :param rate_config: lwf.state.rate recordset or False
        :param eval_date: datetime.date object
        :param establishment_headcount: int (active headcount in company/establishment)
        :param contract: optional hr.contract / hr.version recordset
        :param net_salary: float (employee net salary for minimum threshold evaluation)
        :param is_employer: bool (True when evaluating employer statutory contribution)
        :return: EligibilityValidationResult
        """
        if not employee:
            return EligibilityValidationResult(
                is_eligible=False,
                reason="No employee record found in payslip context."
            )

        # 1. Employee-level LWF Applicability check (HR Manager setting / Exempt / Contractor)
        if hasattr(employee, 'hds_in_lwf_applicable') and not employee.hds_in_lwf_applicable:
            return EligibilityValidationResult(
                is_eligible=False,
                reason=f"LWF is not applicable for employee '{employee.name}' (LWF Applicable unchecked / exempt)."
            )

        # 2. Contractor / Exempt Employee Type check
        emp_type_name = ''
        if getattr(employee, 'employee_type_id', False):
            emp_type_name = (employee.employee_type_id.name or '').lower()
        elif getattr(employee, 'employee_type', False):
            emp_type_name = str(employee.employee_type).lower()

        if any(term in emp_type_name for term in ('contract', 'freelance')):
            return EligibilityValidationResult(
                is_eligible=False,
                reason=f"Employee '{employee.name}' is a contractor/exempt and LWF is not applicable."
            )

        # 3. Contract-level LWF applicability check (if contract passed or linked)
        contract_rec = contract or (getattr(employee, 'contract_id', False) if hasattr(employee, 'contract_id') else False)
        if contract_rec and hasattr(contract_rec, 'hds_in_lwf_applicable') and not contract_rec.hds_in_lwf_applicable:
            return EligibilityValidationResult(
                is_eligible=False,
                reason=f"LWF is not applicable under contract for employee '{employee.name}'."
            )

        if not state:
            return EligibilityValidationResult(
                is_eligible=False,
                reason=f"Statutory work state could not be resolved for employee '{employee.name}'." if employee else "No state provided."
            )

        if not rate_config:
            return EligibilityValidationResult(
                is_eligible=False,
                reason=f"No active LWF rate configuration for state '{state.name}' on date {eval_date}."
            )

        # Minimum employee count threshold check
        min_threshold = getattr(rate_config, 'min_employee_count', 0) or 0
        if min_threshold > 0 and establishment_headcount < min_threshold:
            return EligibilityValidationResult(
                is_eligible=False,
                reason=f"LWF statutory threshold not met: Headcount ({establishment_headcount}) < Required Threshold ({min_threshold}).",
                rate_config=rate_config,
                headcount=establishment_headcount,
                min_threshold=min_threshold
            )

        # Deduction schedule month check
        is_scheduled = rate_config.is_deduction_month(eval_date)
        if not is_scheduled:
            return EligibilityValidationResult(
                is_eligible=False,
                reason=f"LWF deduction not scheduled for month {eval_date.month} (Frequency: {rate_config.deduction_frequency}).",
                rate_config=rate_config,
                headcount=establishment_headcount,
                min_threshold=min_threshold,
                is_scheduled_month=False
            )

        # Minimum Net / Earned Salary check (applicable only for employee deduction)
        # If employee's earned/net salary is less than the state employee contribution amount (e.g. 0 on LOP or < state amount),
        # employee contribution is not deducted (returns 0.0).
        if not is_employer and rate_config and net_salary is not None:
            emp_contrib = getattr(rate_config, 'emp_contribution', 0.0) or 0.0
            if emp_contrib > 0.0 and net_salary < emp_contrib:
                return EligibilityValidationResult(
                    is_eligible=False,
                    reason=f"Employee Net/Earned Salary ({net_salary:,.2f}) is less than the state LWF contribution amount ({emp_contrib:,.2f}) for '{state.name}'.",
                    rate_config=rate_config,
                    headcount=establishment_headcount,
                    min_threshold=min_threshold,
                    is_scheduled_month=True
                )

        return EligibilityValidationResult(
            is_eligible=True,
            reason="Employee is eligible for LWF contribution.",
            rate_config=rate_config,
            headcount=establishment_headcount,
            min_threshold=min_threshold,
            is_scheduled_month=True
        )
