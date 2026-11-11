# -*- coding: utf-8 -*-
from odoo import fields
from ..base import BaseStatutoryService


class EPFEmployeeCalculator(BaseStatutoryService):
    """
    Calculates Employee EPF Contribution (Standard EPF + VPF).
    Returns POSITIVE float amount. Negative conversion belongs strictly to HrPayslip layer.
    """

    def __init__(self, env, wage_calc):
        super().__init__(env)
        self.wage_calc = wage_calc

    def compute(self, payslip):
        employee = payslip.employee_id

        # Step 1: Check employee eligibility guard
        if not employee or not employee.hds_in_epf_applicable:
            return 0.0

        # Step 2: Check company applicability guard
        company = getattr(payslip, 'company_id', False) or (employee and getattr(employee, 'company_id', False)) or self.env.company
        if company and hasattr(company, 'hds_in_epf_applicable') and not company.hds_in_epf_applicable:
            return 0.0

        eval_date = payslip.date_to or payslip.date_from or fields.Date.today()

        # Step 3: Get PF contribution wage
        contribution_wage = self.wage_calc.get_pf_contribution_wage(payslip)

        # Step 4: Non-positive wage guard: Contribution Wage <= 0 -> Employee EPF = 0
        if contribution_wage <= 0.0:
            return 0.0

        # Step 5: Fetch effective-dated EPF rate from Rule Parameters (NOT hardcoded)
        epf_rate = self.get_pf_parameter(
            'EPF_RATE',
            date=eval_date,
            as_decimal=True
        )

        # Step 6: Calculate standard EPF (Statutory nearest rupee rounding)
        base_epf = self.round_statutory(
            contribution_wage * epf_rate
        )

        # Step 5: Calculate VPF (if applicable)
        vpf_amount = 0.0
        vpf_type = getattr(employee, 'hds_in_vpf_type', 'none') or 'none'

        if vpf_type == 'percent' and getattr(employee, 'hds_in_vpf_percent', 0.0) > 0:
            actual_pf_wage = self.wage_calc.get_actual_pf_wage(payslip)
            vpf_amount = self.round_statutory(
                actual_pf_wage * (employee.hds_in_vpf_percent / 100.0)
            )

        elif vpf_type == 'fixed' and getattr(employee, 'hds_in_vpf_amount', 0.0) > 0:
            vpf_amount = float(employee.hds_in_vpf_amount)

        # Step 6: Return positive amount
        return base_epf + vpf_amount
