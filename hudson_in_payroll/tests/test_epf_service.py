# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase
# pyrefly: ignore [missing-import]
from odoo.exceptions import UserError
from ..services.epf.epf_service import EPFService


class TestEPFService(TransactionCase):

    def setUp(self):
        super().setUp()
        self.employee = self.env['hr.employee'].create({
            'name': 'Test EPF Employee',
            'hds_in_epf_applicable': True,
            'hds_in_eps_applicable': True,
            'hds_in_pf_contribution_basis': 'statutory_ceiling',
            'hds_in_uan': '100123456789',
        })
        self.payslip = self.env['hr.payslip'].create({
            'employee_id': self.employee.id,
            'date_from': '2026-04-01',
            'date_to': '2026-04-30',
        })

    def test_01_wage_below_ceiling(self):
        """Wage = ₹10,000 (< ₹25,000 ceiling). EPF = 1200, EPS = 833, ER EPF = 367."""
        service = EPFService(self.env)
        pf_wage = 10000.0
        localdict = {'rules': {'BASIC': {'total': pf_wage}}}
        
        basis_wage = service.wage_calc.get_pf_contribution_wage(self.payslip, localdict=localdict)
        self.assertEqual(basis_wage, 10000.0)

    def test_02_wage_above_ceiling(self):
        """Wage = ₹30,000 (> ₹25,000 ceiling). Capped at 25000."""
        service = EPFService(self.env)
        localdict = {'rules': {'BASIC': {'total': 30000.0}}}
        
        basis_wage = service.wage_calc.get_pf_contribution_wage(self.payslip, localdict=localdict)
        self.assertEqual(basis_wage, 25000.0)

    def test_03_international_worker(self):
        """IW = True disables ceiling cap."""
        self.employee.hds_in_is_international_worker = True
        service = EPFService(self.env)
        localdict = {'rules': {'BASIC': {'total': 50000.0}}}
        
        basis_wage = service.wage_calc.get_pf_contribution_wage(self.payslip, localdict=localdict)
        self.assertEqual(basis_wage, 50000.0)

    def test_04_vpf_validation(self):
        """Negative VPF raises UserError."""
        self.employee.hds_in_vpf_type = 'percent'
        self.employee.hds_in_vpf_percent = -5.0
        service = EPFService(self.env)
        
        with self.assertRaises(UserError):
            service.compute_employee_epf(self.payslip)

    def test_05_employee_epf_calculation_prompt_spec(self):
        """
        Prompt Test Case:
        Basic = 15000, DA = 0, EPF Applicable = True, Basis = Statutory Wage Ceiling (15000), Rate = 12%.
        Contribution Wage = 15000
        EPFService / EPFEmployeeCalculator output = 1800.0 (Positive)
        HrPayslip API output = -1800.0 (Negative deduction)
        """
        localdict = {'rules': {'BASIC': {'total': 15000.0}}}
        service = EPFService(self.env, localdict=localdict)
        
        # 1. Contribution Wage
        contribution_wage = service.wage_calc.get_pf_contribution_wage(self.payslip)
        self.assertEqual(contribution_wage, 15000.0)

        # 2. Calculator & Facade return positive float 1800.0
        epf_amount = service.compute_employee_epf(self.payslip)
        self.assertEqual(epf_amount, 1800.0)

        # 3. HrPayslip API converts to negative deduction -1800.0
        payslip_deduction = self.payslip.hds_in_compute_employee_epf(localdict=localdict)
        self.assertEqual(payslip_deduction, -1800.0)

    def test_06_employer_epf_total_vs_share(self):
        """
        Verifies Total Employer PF (12% = ₹3,600) vs Employer EPF Share (₹1,517).
        PF Wage = ₹30,000 (actual_pf_wage basis, EPS capped at ₹25k ceiling)
        """
        self.employee.hds_in_pf_contribution_basis = 'actual_pf_wage'
        self.employee.hds_in_pf_employer_basis = 'actual_pf_wage'
        localdict = {'rules': {'BASIC': {'total': 30000.0}}}
        service = EPFService(self.env, localdict=localdict)

        # Total 12% Employer PF Contribution
        total_pf = service.compute_employer_total_pf(self.payslip)
        self.assertEqual(total_pf, 3600.0)

        # Employer EPF (12% of Contribution Wage)
        employer_epf = service.compute_employer_epf(self.payslip)
        self.assertEqual(employer_epf, 3600.0)

        # Employer EPS (8.33% capped at 25k -> 25000 * 0.0833 = 2083.0)
        eps = service.compute_employer_eps(self.payslip)
        self.assertEqual(eps, 2083.0)

        # Employer EPF Share (3600 - 2083 = 1517)
        epf_share = service.compute_employer_epf_share(self.payslip)
        self.assertEqual(epf_share, 1517.0)

    def test_07_compute_pf_wage_delegation(self):
        """Verifies compute_pf_wage delegates directly to get_actual_pf_wage."""
        localdict = {'rules': {'BASIC': {'total': 18000.0}}}
        service = EPFService(self.env, localdict=localdict)

        pf_wage = service.compute_pf_wage(self.payslip)
        self.assertEqual(pf_wage, 18000.0)

        payslip_pf_wage = self.payslip.hds_in_compute_pf_wage(localdict=localdict)
        self.assertEqual(payslip_pf_wage, 18000.0)
