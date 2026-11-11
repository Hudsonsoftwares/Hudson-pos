# -*- coding: utf-8 -*-
from odoo import fields# pyrefly: ignore [missing-import]
import logging
from ..base import BaseStatutoryService
from ..audit.audit_service import StatutoryAuditSession
from .gratuity_validator import GratuityValidator
from .gratuity_data_service import GratuityDataService
from .gratuity_calculator import GratuityCalculator

_logger = logging.getLogger(__name__)


class GratuityService(BaseStatutoryService):
    """
    Orchestration Facade for Gratuity statutory calculation.
    Coordinates SOA components:
    1. GratuityValidator
    2. GratuityDataService
    3. GratuityCalculator
    4. StatutoryAuditSession
    """

    def __init__(self, env, localdict=None):
        super().__init__(env)
        self.localdict = localdict or {}
        self.validator = GratuityValidator(env)
        self.data_service = GratuityDataService(env)
        self.calculator = GratuityCalculator()

    def _extract_payslip_and_employee(self, payslip=None, separation_date=None):
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
            if separation_date:
                eval_date = fields.Date.from_string(separation_date)
            elif self.localdict.get('separation_date'):
                eval_date = fields.Date.from_string(self.localdict.get('separation_date'))
        elif separation_date:
            eval_date = fields.Date.from_string(separation_date)

        return slip, employee, eval_date, company

    def compute_gratuity(self, payslip=None, separation_date=None, is_death_or_disablement=False, return_gross=False):
        """
        Computes statutory gratuity amount via SOA components.

        :param payslip: optional hr.payslip recordset
        :param separation_date: optional separation date
        :param is_death_or_disablement: optional statutory exception flag
        :param return_gross: if True, returns uncapped raw formula gratuity; otherwise capped at statutory ceiling
        :return: float (payable gratuity amount in INR)
        """
        slip, employee, eval_date, company = self._extract_payslip_and_employee(payslip, separation_date=separation_date)
        resolved_sep_date = separation_date or (getattr(slip, 'date_to', None) if slip else None)
        if not slip and separation_date:
            eval_date = fields.Date.from_string(separation_date)
        contract = getattr(slip, 'contract_id', None) or self.localdict.get('contract') or getattr(employee, 'version_id', None)

        with StatutoryAuditSession(self.env, slip, statutory_module="gratuity", rule_code="GRATUITY", calculation_type="gratuity_settlement") as audit:
            audit.attach_input("employee_id", employee.id if employee else False)
            audit.attach_input("employee_name", employee.name if employee else False)
            audit.attach_input("eval_date", str(eval_date))

            # 1. Statutory Validation
            val_result = self.validator.validate(
                employee=employee,
                contract=contract,
                separation_date=resolved_sep_date,
                is_death_or_disablement=is_death_or_disablement,
                calc_date=eval_date
            )
            audit.attach_parameter("is_eligible", val_result.is_eligible)
            audit.attach_parameter("validation_reason", val_result.reason)
            audit.attach_parameter("completed_years", val_result.completed_years)

            if not val_result.is_eligible:
                audit.log_message(val_result.reason)
                return 0.0

            # 2. Gather & Prepare Calculation Data DTO
            calc_data = self.data_service.prepare_calculation_data(
                employee=employee,
                contract=contract,
                separation_date=resolved_sep_date or val_result.separation_date,
                payslip=slip,
                is_death_or_disablement=is_death_or_disablement or val_result.is_death_or_disablement,
                calc_date=eval_date
            )
            audit.attach_parameter("wage_base", calc_data.wage_base)
            audit.attach_parameter("days_multiplier", calc_data.days_multiplier)
            audit.attach_parameter("month_divisor", calc_data.month_divisor)
            audit.attach_parameter("statutory_ceiling", calc_data.statutory_ceiling)

            # 3. Perform Pure Calculation
            calc_result = self.calculator.calculate(calc_data)
            audit.attach_output("raw_gratuity_amount", calc_result.raw_gratuity_amount)
            audit.attach_output("capped_gratuity_amount", calc_result.capped_gratuity_amount)
            audit.attach_output("final_gratuity_amount", calc_result.final_gratuity_amount)
            audit.attach_output("is_ceiling_applied", calc_result.is_ceiling_applied)

            if return_gross:
                return calc_result.raw_gratuity_amount
            return calc_result.final_gratuity_amount

    def compute_gratuity_details(self, payslip=None, separation_date=None, is_death_or_disablement=False):
        """
        Computes statutory gratuity details returning a GratuityCalculationResult DTO
        containing raw_gratuity_amount (gross payable), capped_gratuity_amount (exemption),
        is_ceiling_applied, and audit breakdown.
        """
        slip, employee, eval_date, company = self._extract_payslip_and_employee(payslip, separation_date=separation_date)
        resolved_sep_date = separation_date or (getattr(slip, 'date_to', None) if slip else None)
        if not slip and separation_date:
            eval_date = fields.Date.from_string(separation_date)
        contract = getattr(slip, 'contract_id', None) or self.localdict.get('contract') or getattr(employee, 'version_id', None)

        val_result = self.validator.validate(
            employee=employee,
            contract=contract,
            separation_date=resolved_sep_date,
            is_death_or_disablement=is_death_or_disablement,
            calc_date=eval_date
        )
        if not val_result.is_eligible:
            return self.calculator.calculate(None)

        calc_data = self.data_service.prepare_calculation_data(
            employee=employee,
            contract=contract,
            separation_date=resolved_sep_date or val_result.separation_date,
            payslip=slip,
            is_death_or_disablement=is_death_or_disablement or val_result.is_death_or_disablement,
            calc_date=eval_date
        )
        return self.calculator.calculate(calc_data)
