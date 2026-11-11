# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase
# pyrefly: ignore [missing-import]
from odoo.fields import Date
from odoo.addons.hudson_in_payroll.services.gratuity.gratuity_validator import GratuityValidator# pyrefly: ignore [missing-import]


class TestGratuityValidator(TransactionCase):

    def setUp(self):
        super(TestGratuityValidator, self).setUp()
        self.validator = GratuityValidator(self.env)
        
        self.company_enabled = self.env['res.company'].create({
            'name': 'Gratuity Enabled Company',
            'hds_in_enable_gratuity': True,
        })
        self.company_disabled = self.env['res.company'].create({
            'name': 'Gratuity Disabled Company',
            'hds_in_enable_gratuity': False,
        })

        self.employee = self.env['hr.employee'].create({
            'name': 'Test Gratuity Employee',
            'company_id': self.company_enabled.id,
            'first_contract_date': Date.from_string('2018-01-01'),
        })

    def test_01_company_disabled_validation(self):
        """Test validation fails when company gratuity is disabled."""
        self.employee.company_id = self.company_disabled.id
        result = self.validator.validate(self.employee, separation_date='2024-01-01')
        self.assertFalse(result.is_eligible)
        self.assertIn("Gratuity is disabled", result.reason)

    def test_02_missing_joining_date_validation(self):
        """Test validation fails when joining date is missing."""
        self.employee.first_contract_date = False
        result = self.validator.validate(self.employee, separation_date='2024-01-01')
        self.assertFalse(result.is_eligible)
        self.assertIn("joining date is missing", result.reason)
        # Restore joining date for subsequent tests
        self.employee.first_contract_date = Date.from_string('2018-01-01')

    def test_03_missing_separation_date_validation(self):
        """Test validation fails when separation date is missing."""
        self.employee.first_contract_date = Date.from_string('2018-01-01')
        result = self.validator.validate(self.employee, separation_date=None)
        self.assertFalse(result.is_eligible)
        self.assertIn("Separation date cannot be determined", result.reason)

    def test_04_service_below_minimum_validation(self):
        """Test validation fails when completed service (3 years) is below minimum (5 years)."""
        self.employee.first_contract_date = Date.from_string('2021-01-01')
        result = self.validator.validate(self.employee, separation_date='2024-01-01')
        self.assertFalse(result.is_eligible)
        self.assertEqual(result.completed_years, 3)
        self.assertEqual(result.min_required_years, 5.0)
        self.assertIn("below the statutory minimum", result.reason)

    def test_05_service_meets_minimum_validation(self):
        """Test validation succeeds when completed service (6 years) meets minimum (5 years)."""
        self.employee.first_contract_date = Date.from_string('2018-01-01')
        result = self.validator.validate(self.employee, separation_date='2024-01-01')
        self.assertTrue(result.is_eligible)
        self.assertEqual(result.completed_years, 6)
        self.assertEqual(result.min_required_years, 5.0)
        self.assertIn("Eligible for gratuity", result.reason)

    def test_06_gratuity_rounding_rule_validation(self):
        """Test statutory continuous service gate: 4 years 7 months is below mandatory 5 full years (Ineligible)."""
        self.employee.first_contract_date = Date.from_string('2019-01-01')
        result = self.validator.validate(self.employee, separation_date='2023-08-15')
        self.assertFalse(result.is_eligible)
        self.assertEqual(result.completed_years, 4)
        self.assertEqual(result.total_years, 4)
        self.assertEqual(result.remaining_months, 7)
        self.assertIn("below the statutory minimum", result.reason)

    def test_06b_gratuity_rounding_rule_after_mandatory_five_years(self):
        """Test statutory rounding: 5 years 7 months rounds UP to 6 completed years for payout (Eligible)."""
        self.employee.first_contract_date = Date.from_string('2018-01-01')
        result = self.validator.validate(self.employee, separation_date='2023-08-15')
        self.assertTrue(result.is_eligible)
        self.assertEqual(result.total_years, 5)
        self.assertEqual(result.remaining_months, 7)
        self.assertEqual(result.completed_years, 6)
        self.assertIn("Eligible for gratuity", result.reason)

    def test_06c_gratuity_death_disablement_fraction_rounding(self):
        """Test statutory exception: 2 years 7 months with death/disablement flag rounds UP to 3 payout years."""
        self.employee.first_contract_date = Date.from_string('2021-01-01')
        result = self.validator.validate(
            self.employee,
            separation_date='2023-08-15',
            is_death_or_disablement=True
        )
        self.assertTrue(result.is_eligible)
        self.assertTrue(result.is_death_or_disablement)
        self.assertEqual(result.total_years, 2)
        self.assertEqual(result.remaining_months, 7)
        self.assertEqual(result.completed_years, 3)
        self.assertIn("Death/Disablement exemption", result.reason)

    def test_07_death_disablement_exception_validation(self):
        """Test statutory exception: 2 years service with death/disablement flag is Eligible."""
        self.employee.first_contract_date = Date.from_string('2022-01-01')
        result = self.validator.validate(
            self.employee,
            separation_date='2024-01-01',
            is_death_or_disablement=True
        )
        self.assertTrue(result.is_eligible)
        self.assertTrue(result.is_death_or_disablement)
        self.assertIn("Death/Disablement exemption", result.reason)

    def test_08_rule_parameter_resolution(self):
        """Test Rule Parameter resolution for minimum service years."""
        result = self.validator.validate(self.employee, separation_date='2024-01-01')
        self.assertEqual(result.min_required_years, 5.0)
        self.assertIsInstance(result.to_dict(), dict)
