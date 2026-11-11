# -*- coding: utf-8 -*-
from datetime import date
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase
from ..services.lwf.company_configuration_validator import CompanyConfigurationValidator
from ..services.lwf.lwf_eligibility_validator import LWFEligibilityValidator
from ..services.lwf.lwf_calculator import LWFCalculator


class TestLWFValidatorsCalculators(TransactionCase):

    def setUp(self):
        super().setUp()
        self.comp_validator = CompanyConfigurationValidator(self.env)
        self.elig_validator = LWFEligibilityValidator(self.env)
        self.calculator = LWFCalculator(self.env)

        self.country_in = self.env.ref('base.in', raise_if_not_found=False) or self.env['res.country'].search([('code', '=', 'IN')], limit=1)

        self.state_mh = self.env['res.country.state'].create({
            'name': 'Maharashtra SOA Test State',
            'code': 'MH_SOA',
            'country_id': self.country_in.id,
        })

        self.rate_mh = self.env['lwf.state.rate'].create({
            'state_id': self.state_mh.id,
            'emp_contribution': 25.0,
            'empl_contribution': 75.0,
            'deduction_frequency': 'half_yearly',
            'deduction_month_1': '6',
            'deduction_month_2': '12',
            'min_employee_count': 10,
            'date_from': '2026-01-01',
            'active': True,
        })

        self.emp = self.env['hr.employee'].create({
            'name': 'SOA Test Employee',
            'hds_in_lwf_applicable': True,
        })

    def test_01_company_configuration_validator_enabled(self):
        """Validates company enablement check."""
        self.env.company.hds_in_enable_lwf = True
        self.env.company.hds_in_lwf_registration_no = "LWF/MH/2026/001"

        res = self.comp_validator.validate(self.env.company)
        self.assertTrue(res.is_valid)
        self.assertTrue(res.is_enabled)
        self.assertEqual(res.registration_no, "LWF/MH/2026/001")

    def test_02_company_configuration_validator_disabled(self):
        """Validates disabled company configuration."""
        self.env.company.hds_in_enable_lwf = False

        res = self.comp_validator.validate(self.env.company)
        self.assertFalse(res.is_valid)
        self.assertFalse(res.is_enabled)
        self.env.company.hds_in_enable_lwf = True

    def test_03_lwf_eligibility_validator_threshold_met(self):
        """Validates eligibility when headcount threshold (15 >= 10) and deduction month (June) match."""
        res = self.elig_validator.validate(
            employee=self.emp,
            state=self.state_mh,
            rate_config=self.rate_mh,
            eval_date=date(2026, 6, 30),
            establishment_headcount=15
        )
        self.assertTrue(res.is_eligible)
        self.assertTrue(res.is_scheduled_month)

    def test_04_lwf_eligibility_validator_threshold_failed(self):
        """Validates ineligibility when headcount threshold (5 < 10) is not met."""
        res = self.elig_validator.validate(
            employee=self.emp,
            state=self.state_mh,
            rate_config=self.rate_mh,
            eval_date=date(2026, 6, 30),
            establishment_headcount=5
        )
        self.assertFalse(res.is_eligible)
        self.assertEqual(res.headcount, 5)

    def test_05_lwf_eligibility_validator_off_cycle_month(self):
        """Validates ineligibility for off-cycle month (April)."""
        res = self.elig_validator.validate(
            employee=self.emp,
            state=self.state_mh,
            rate_config=self.rate_mh,
            eval_date=date(2026, 4, 30),
            establishment_headcount=15
        )
        self.assertFalse(res.is_eligible)
        self.assertFalse(res.is_scheduled_month)

    def test_06_lwf_calculator_contributions(self):
        """Validates calculation math and monetary rounding."""
        ee = self.calculator.calculate_employee_contribution(self.rate_mh)
        er = self.calculator.calculate_employer_contribution(self.rate_mh)

        self.assertEqual(ee, 25.0)
        self.assertEqual(er, 75.0)

    def test_07_lwf_eligibility_employee_unchecked(self):
        """Validates ineligibility when HR unchecks LWF Applicable for employee."""
        self.emp.hds_in_lwf_applicable = False
        res = self.elig_validator.validate(
            employee=self.emp,
            state=self.state_mh,
            rate_config=self.rate_mh,
            eval_date=date(2026, 6, 30),
            establishment_headcount=15
        )
        self.assertFalse(res.is_eligible)
        self.assertIn("exempt", res.reason.lower())

    def test_08_lwf_eligibility_contractor(self):
        """Validates ineligibility when employee is a contractor/freelancer."""
        self.emp.hds_in_lwf_applicable = True
        contract_type = self.env.ref('hudson_payroll_base.employee_type_contract', raise_if_not_found=False)
        if not contract_type:
            contract_type = self.env['hr.employee.type'].create({'name': 'Contractor', 'code': 'CON'})
        self.emp.employee_type_id = contract_type.id
        res = self.elig_validator.validate(
            employee=self.emp,
            state=self.state_mh,
            rate_config=self.rate_mh,
            eval_date=date(2026, 6, 30),
            establishment_headcount=15
        )
        self.assertFalse(res.is_eligible)
        self.assertIn("contractor", res.reason.lower())

    def test_09_company_enable_lwf_below_threshold_blocked(self):
        """Enabling LWF at company level when headcount < state threshold raises ValidationError."""
        partner_mh = self.env['res.partner'].create({
            'name': 'Test MH Company Partner',
            'state_id': self.state_mh.id,
            'country_id': self.country_in.id,
        })
        test_comp = self.env['res.company'].create({
            'name': 'Test Small MH Company',
            'partner_id': partner_mh.id,
            'hds_in_enable_lwf': False,
        })
        # Create only 2 employees (< 10 threshold)
        self.env['hr.employee'].create({
            'name': 'Emp 1',
            'company_id': test_comp.id,
            'address_id': partner_mh.id,
        })
        self.env['hr.employee'].create({
            'name': 'Emp 2',
            'company_id': test_comp.id,
            'address_id': partner_mh.id,
        })

        with self.assertRaises(ValidationError):
            test_comp.with_context(validate_statutory_threshold=True).hds_in_enable_lwf = True

    def test_10_company_enable_lwf_above_threshold_allowed(self):
        """Enabling LWF at company level when headcount >= state threshold succeeds."""
        partner_mh = self.env['res.partner'].create({
            'name': 'Test Large MH Company Partner',
            'state_id': self.state_mh.id,
            'country_id': self.country_in.id,
        })
        test_comp = self.env['res.company'].create({
            'name': 'Test Large MH Company',
            'partner_id': partner_mh.id,
            'hds_in_enable_lwf': False,
        })
        # Create 10 employees (>= 10 threshold)
        for i in range(10):
            self.env['hr.employee'].create({
                'name': f'Emp {i}',
                'company_id': test_comp.id,
                'address_id': partner_mh.id,
            })

        test_comp.with_context(validate_statutory_threshold=True).hds_in_enable_lwf = True
        self.assertTrue(test_comp.hds_in_enable_lwf)

    def test_11_lwf_eligibility_net_salary_below_contribution(self):
        """Validates ineligibility when employee earned net salary is less than LWF contribution (or 0 on LOP)."""
        self.emp.hds_in_lwf_applicable = True
        reg_type = self.env.ref('hudson_payroll_base.employee_type_employee', raise_if_not_found=False)
        if reg_type:
            self.emp.employee_type_id = reg_type.id
        # Contribution is 25.0, net salary is 10.0
        res = self.elig_validator.validate(
            employee=self.emp,
            state=self.state_mh,
            rate_config=self.rate_mh,
            eval_date=date(2026, 6, 30),
            establishment_headcount=15,
            net_salary=10.0
        )
        self.assertFalse(res.is_eligible)
        self.assertIn("less than the state lwf contribution", res.reason.lower())

        # Net salary is 0.0 (unpaid shortage / LOP)
        res_zero = self.elig_validator.validate(
            employee=self.emp,
            state=self.state_mh,
            rate_config=self.rate_mh,
            eval_date=date(2026, 6, 30),
            establishment_headcount=15,
            net_salary=0.0
        )
        self.assertFalse(res_zero.is_eligible)

    def test_12_lwf_eligibility_net_salary_sufficient(self):
        """Validates eligibility when employee earned net salary exceeds LWF contribution."""
        self.emp.hds_in_lwf_applicable = True
        reg_type = self.env.ref('hudson_payroll_base.employee_type_employee', raise_if_not_found=False)
        if reg_type:
            self.emp.employee_type_id = reg_type.id
        res = self.elig_validator.validate(
            employee=self.emp,
            state=self.state_mh,
            rate_config=self.rate_mh,
            eval_date=date(2026, 6, 30),
            establishment_headcount=15,
            net_salary=15000.0
        )
        self.assertTrue(res.is_eligible)

