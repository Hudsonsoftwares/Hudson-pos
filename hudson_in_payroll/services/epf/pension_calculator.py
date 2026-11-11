# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import fields
from ..base import BaseStatutoryService


class EPFPensionCalculator(BaseStatutoryService):
    """Calculates Employer Pension Scheme (EPS) Contribution."""

    def __init__(self, env, wage_calc):
        super().__init__(env)
        self.wage_calc = wage_calc

    def compute(self, payslip):
        employee = getattr(payslip, 'employee_id', False)
        if not employee or not getattr(employee, 'hds_in_epf_applicable', False) or not getattr(employee, 'hds_in_eps_applicable', False):
            return 0.0

        company = getattr(payslip, 'company_id', False) or (employee and getattr(employee, 'company_id', False)) or self.env.company
        if company and hasattr(company, 'hds_in_epf_applicable') and not company.hds_in_epf_applicable:
            return 0.0

        eval_date = getattr(payslip, 'date_to', False) or fields.Date.today()

        # Age > 58 Check: Pension contribution ceases at age 58
        if employee.birthday:
            age = self.calculate_age(employee.birthday, eval_date)
            if age >= 58:
                return 0.0

        pf_wage = self.wage_calc.get_pf_contribution_wage(payslip)
        eps_rate = self.get_pf_parameter('hds_in_eps_rate', date=eval_date, as_decimal=True)

        if employee.hds_in_higher_pension or employee.hds_in_is_international_worker:
            eps_wage = self.wage_calc.get_actual_pf_wage(payslip)
        else:
            eps_ceiling = self.get_pf_parameter('hds_in_eps_wage_ceiling', date=eval_date)
            eps_wage = min(self.wage_calc.get_actual_pf_wage(payslip), eps_ceiling)

        if eps_wage <= 0.0:
            return 0.0

        return self.round_statutory(eps_wage * eps_rate)
