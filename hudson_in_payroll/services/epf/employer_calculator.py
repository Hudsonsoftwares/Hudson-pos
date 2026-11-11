# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import fields
from ..base import BaseStatutoryService


class EPFEmployerCalculator(BaseStatutoryService):
    """Calculates Employer EPF Total, Employer EPF Share, EPS, EDLI, and Admin Charges."""

    def __init__(self, env, wage_calc, pension_calc):
        super().__init__(env)
        self.wage_calc = wage_calc
        self.pension_calc = pension_calc

    def _is_epf_applicable(self, payslip):
        """Validates that EPF master toggle is enabled at both employee and company levels."""
        employee = getattr(payslip, 'employee_id', False)
        if not employee or not getattr(employee, 'hds_in_epf_applicable', False):
            return False
        company = getattr(payslip, 'company_id', False) or (employee and getattr(employee, 'company_id', False)) or self.env.company
        if company and hasattr(company, 'hds_in_epf_applicable') and not company.hds_in_epf_applicable:
            return False
        return True

    def compute_employer_epf(self, payslip):
        """
        Calculates Employer EPF Contribution.
        Formula: Round(PF Contribution Wage * Effective Employer EPF Rate)
        Returns POSITIVE float amount representing Employer Cost.
        """
        if not self._is_epf_applicable(payslip):
            return 0.0

        # Guard 3: Historical date handling (payslip period date, not today's date)
        eval_date = getattr(payslip, 'date_to', False) or getattr(payslip, 'date_from', False) or self.env.context.get('date') or fields.Date.today()

        # Guard 4: PF Contribution Wage (Employer Basis)
        contribution_wage = getattr(self.wage_calc, 'get_employer_pf_contribution_wage', self.wage_calc.get_pf_contribution_wage)(payslip)

        # Guard 5: Non-positive wage guard
        if contribution_wage <= 0.0:
            return 0.0

        # Retrieve effective Employer EPF rate via mapped parameter (no hardcoding)
        employer_epf_rate = self.get_pf_parameter('EMPLOYER_EPF_RATE', date=eval_date, as_decimal=True)

        return self.round_statutory(contribution_wage * employer_epf_rate)

    def compute_employer_total_pf(self, payslip):
        """
        Calculates the Total Employer Statutory PF Contribution (12% of PF Contribution Wage).
        Delegates to compute_employer_epf(payslip).
        """
        return self.compute_employer_epf(payslip)

    def compute_employer_epf_share(self, payslip):
        """
        Calculates the Net Employer EPF Contribution Share after deducting EPS share.
        Formula: Max(0.0, Total Employer PF Contribution - Employer EPS Contribution)
        Example: ₹2,040 (Total 12%) - ₹1,250 (EPS 8.33%) = ₹790.00
        """
        if not self._is_epf_applicable(payslip):
            return 0.0

        total_statutory = self.compute_employer_epf(payslip)
        eps_amount = self.pension_calc.compute(payslip)

        return max(0.0, total_statutory - eps_amount)

    def compute_edli(self, payslip):
        if not self._is_epf_applicable(payslip):
            return 0.0

        eval_date = getattr(payslip, 'date_to', False) or fields.Date.today()
        actual_pf_wage = self.wage_calc.get_actual_pf_wage(payslip)
        if actual_pf_wage <= 0.0:
            return 0.0

        edli_ceiling = self.get_pf_parameter('hds_in_edli_wage_ceiling', date=eval_date)
        edli_wage = min(actual_pf_wage, edli_ceiling) if edli_ceiling else actual_pf_wage

        edli_rate = self.get_pf_parameter('hds_in_edli_rate', date=eval_date, as_decimal=True)
        return self.round_statutory(edli_wage * edli_rate)

    def compute_epf_admin(self, payslip):
        if not self._is_epf_applicable(payslip):
            return 0.0

        eval_date = getattr(payslip, 'date_to', False) or fields.Date.today()
        pf_wage = getattr(self.wage_calc, 'get_employer_pf_contribution_wage', self.wage_calc.get_pf_contribution_wage)(payslip)
        if pf_wage <= 0.0:
            return 0.0
        admin_rate = self.get_pf_parameter('hds_in_epf_admin_charge_rate', date=eval_date, as_decimal=True)
        return self.round_statutory(pf_wage * admin_rate)

    def compute_edli_admin(self, payslip):
        if not self._is_epf_applicable(payslip):
            return 0.0

        eval_date = getattr(payslip, 'date_to', False) or fields.Date.today()
        actual_pf_wage = self.wage_calc.get_actual_pf_wage(payslip)
        if actual_pf_wage <= 0.0:
            return 0.0

        edli_ceiling = self.get_pf_parameter('hds_in_edli_wage_ceiling', date=eval_date)
        edli_wage = min(actual_pf_wage, edli_ceiling) if edli_ceiling else actual_pf_wage

        admin_rate = self.get_pf_parameter('hds_in_edli_admin_charge_rate', date=eval_date, as_decimal=True)
        return self.round_statutory(edli_wage * admin_rate)
