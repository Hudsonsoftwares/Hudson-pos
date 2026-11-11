# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import fields
from ..base import BaseStatutoryService
from ..audit.audit_service import StatutoryAuditSession
from ..payroll.work_location_service import PayrollWorkLocationService
from .lwf_rate_service import LWFRateService
from .company_configuration_validator import CompanyConfigurationValidator
from .lwf_eligibility_validator import LWFEligibilityValidator
from .lwf_calculator import LWFCalculator

_logger = logging.getLogger(__name__)


class LWFService(BaseStatutoryService):
    """
    Thin Orchestration Facade for Labour Welfare Fund (LWF) statutory calculations.
    Coordinates sub-components in strict SOA order:
    1. CompanyConfigurationValidator
    2. PayrollWorkLocationService
    3. LWFRateService
    4. LWFEligibilityValidator
    5. LWFCalculator
    6. StatutoryAuditSession
    """

    def __init__(self, env, localdict=None):
        super().__init__(env)
        self.localdict = localdict or {}
        self.company_validator = CompanyConfigurationValidator(env)
        self.location_service = PayrollWorkLocationService(env)
        self.rate_service = LWFRateService(env)
        self.eligibility_validator = LWFEligibilityValidator(env)
        self.calculator = LWFCalculator(env)

    def _extract_payslip_and_employee(self, payslip=None):
        slip = payslip or self.localdict.get('payslip_record') or self.localdict.get('payslip')
        employee = False
        eval_date = fields.Date.today()
        company = self.env.company

        if slip:
            employee = getattr(slip, 'employee_id', False)
            eval_date = getattr(slip, 'date_to', fields.Date.today()) or fields.Date.today()
            company = getattr(slip, 'company_id', False) or self.env.company
        elif self.localdict.get('employee'):
            employee = self.localdict.get('employee')
            company = getattr(employee, 'company_id', False) or self.env.company

        return slip, employee, eval_date, company

    def _get_establishment_employee_count(self, employee, company, state=None):
        """
        Returns active headcount strictly for the employee's state/establishment,
        preventing nationwide headcount from triggering state-level thresholds.
        Work Address (address_id.state_id) has 1st priority, followed by Work Location (work_location_id.address_id.state_id).
        """
        if not company:
            return 0
        base_domain = [('company_id', '=', company.id), ('active', '=', True)]
        if state:
            state_domain = base_domain + [
                '|',
                ('address_id.state_id', '=', state.id),
                '&', ('address_id.state_id', '=', False), ('work_location_id.address_id.state_id', '=', state.id)
            ]
            comp_state = company.partner_id.state_id if company.partner_id else False
            if comp_state and comp_state.id == state.id:
                state_domain = base_domain + [
                    '|',
                    ('address_id.state_id', '=', state.id),
                    '|',
                    '&', ('address_id.state_id', '=', False), ('work_location_id.address_id.state_id', '=', state.id),
                    '&', ('address_id.state_id', '=', False), ('work_location_id.address_id.state_id', '=', False),
                ]
            return self.env['hr.employee'].search_count(state_domain)

        if employee and employee.work_location_id:
            return self.env['hr.employee'].search_count(
                base_domain + [('work_location_id', '=', employee.work_location_id.id)]
            )
        return self.env['hr.employee'].search_count(base_domain)

    def _get_eval_net_salary(self, slip):
        """
        Determines the employee's Net Salary for statutory threshold evaluations.
        During rule evaluation, sums basic, allowances, and deductions computed so far.
        Falls back to payslip's net_wage, gross_wage, or contract wage.
        """
        if self.localdict:
            cats = self.localdict.get('categories')
            if cats:
                basic = float(getattr(cats, 'BASIC', 0.0) or 0.0)
                alw = float(getattr(cats, 'ALW', 0.0) or 0.0)
                gross = float(getattr(cats, 'GROSS', basic + alw) or 0.0)
                ded = float(getattr(cats, 'DED', 0.0) or 0.0)
                return max(0.0, gross + ded)
        if slip:
            if hasattr(slip, 'net_wage') and slip.net_wage:
                return float(slip.net_wage)
            if hasattr(slip, 'gross_wage') and slip.gross_wage:
                return float(slip.gross_wage)
            if hasattr(slip, 'contract_id') and slip.contract_id and getattr(slip.contract_id, 'wage', False):
                return float(slip.contract_id.wage or 0.0)
            if hasattr(slip, 'employee_id') and slip.employee_id and getattr(slip.employee_id, 'wage', False):
                return float(slip.employee_id.wage or 0.0)
        return None

    def compute_lwf_employee(self, payslip=None):
        """
        Computes Employee LWF statutory deduction amount via SOA components.

        :param payslip: optional hr.payslip recordset
        :return: float (employee contribution amount in INR)
        """
        slip, employee, eval_date, company = self._extract_payslip_and_employee(payslip)
        # If employee has 0 attendance (100% LOP / shortage), do not deduct employee LWF
        if slip and hasattr(slip, '_get_earned_wage_ratio') and slip._get_earned_wage_ratio(localdict=self.localdict) <= 0.0:
            return 0.0
        with StatutoryAuditSession(self.env, slip, statutory_module="lwf", rule_code="LWF_EE", calculation_type="employee_contribution") as audit:
            audit.attach_input("employee_id", employee.id if employee else False)
            audit.attach_input("employee_name", employee.name if employee else False)
            audit.attach_input("eval_date", str(eval_date))

            # 1. Company Configuration Validation
            comp_result = self.company_validator.validate(company)
            audit.attach_parameter("company_enabled", comp_result.is_enabled)
            audit.attach_parameter("company_registration_no", comp_result.registration_no)
            if not comp_result.is_valid:
                audit.log_message(comp_result.reason)
                return 0.0

            # 2. Location Service Resolution
            state = self.location_service.get_work_state(employee)
            audit.attach_parameter("resolved_state", state.name if state else False)

            # 3. Rate Service Query
            rate_config = self.rate_service.get_rate_config(state, eval_date=eval_date, company=company)
            audit.attach_parameter("rate_config_id", rate_config.id if rate_config else False)

            # 4. Eligibility Validation
            headcount = self._get_establishment_employee_count(employee, company, state=state)
            contract = getattr(slip, 'contract_id', False) if slip else False
            net_salary = self._get_eval_net_salary(slip)
            audit.attach_parameter("employee_lwf_applicable", getattr(employee, 'hds_in_lwf_applicable', True))
            audit.attach_parameter("evaluated_net_salary", net_salary)
            elig_result = self.eligibility_validator.validate(
                employee=employee,
                state=state,
                rate_config=rate_config,
                eval_date=eval_date,
                establishment_headcount=headcount,
                contract=contract,
                net_salary=net_salary,
                is_employer=False,
            )
            audit.attach_parameter("min_employee_count_threshold", elig_result.min_threshold)
            audit.attach_parameter("establishment_employee_headcount", elig_result.headcount)
            audit.attach_parameter("is_deduction_month", elig_result.is_scheduled_month)

            if not elig_result.is_eligible:
                audit.log_message(elig_result.reason)
                return 0.0

            # 5. Calculation
            amount = self.calculator.calculate_employee_contribution(rate_config)
            audit.attach_output("emp_contribution", amount)
            return amount

    def compute_lwf_employer(self, payslip=None):
        """
        Computes Employer LWF statutory contribution amount via SOA components.
        Employer contribution remains payable even when employee attendance is 0 (100% LOP).

        :param payslip: optional hr.payslip recordset
        :return: float (employer contribution amount in INR)
        """
        slip, employee, eval_date, company = self._extract_payslip_and_employee(payslip)
        with StatutoryAuditSession(self.env, slip, statutory_module="lwf", rule_code="LWF_ER", calculation_type="employer_contribution") as audit:
            audit.attach_input("employee_id", employee.id if employee else False)
            audit.attach_input("employee_name", employee.name if employee else False)
            audit.attach_input("eval_date", str(eval_date))

            # 1. Company Configuration Validation
            comp_result = self.company_validator.validate(company)
            audit.attach_parameter("company_enabled", comp_result.is_enabled)
            audit.attach_parameter("company_registration_no", comp_result.registration_no)
            if not comp_result.is_valid:
                audit.log_message(comp_result.reason)
                return 0.0

            # 2. Location Service Resolution
            state = self.location_service.get_work_state(employee)
            audit.attach_parameter("resolved_state", state.name if state else False)

            # 3. Rate Service Query
            rate_config = self.rate_service.get_rate_config(state, eval_date=eval_date, company=company)
            audit.attach_parameter("rate_config_id", rate_config.id if rate_config else False)

            # 4. Eligibility Validation
            headcount = self._get_establishment_employee_count(employee, company, state=state)
            contract = getattr(slip, 'contract_id', False) if slip else False
            audit.attach_parameter("employee_lwf_applicable", getattr(employee, 'hds_in_lwf_applicable', True))
            elig_result = self.eligibility_validator.validate(
                employee=employee,
                state=state,
                rate_config=rate_config,
                eval_date=eval_date,
                establishment_headcount=headcount,
                contract=contract,
                is_employer=True,
            )
            audit.attach_parameter("min_employee_count_threshold", elig_result.min_threshold)
            audit.attach_parameter("establishment_employee_headcount", elig_result.headcount)
            audit.attach_parameter("is_deduction_month", elig_result.is_scheduled_month)

            if not elig_result.is_eligible:
                audit.log_message(elig_result.reason)
                return 0.0

            # 5. Calculation
            amount = self.calculator.calculate_employer_contribution(rate_config)
            audit.attach_output("empl_contribution", amount)
            return amount
