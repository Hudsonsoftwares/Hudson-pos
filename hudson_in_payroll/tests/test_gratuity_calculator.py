# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.addons.hudson_in_payroll.services.gratuity.gratuity_data_service import GratuityCalculationData
from odoo.addons.hudson_in_payroll.services.gratuity.gratuity_calculator import GratuityCalculator


class TestGratuityCalculator(TransactionCase):

    def setUp(self):
        super(TestGratuityCalculator, self).setUp()
        self.calculator = GratuityCalculator()

    def test_01_standard_gratuity_calculation(self):
        """
        Test standard gratuity formula calculation.
        Basic + DA = 50,000, Completed Years = 10.
        Formula: (50000 / 26) * 15 * 10 = 288461.53846 -> 288461.54
        """
        data = GratuityCalculationData(
            wage_base=50000.0,
            completed_years=10,
            days_multiplier=15.0,
            month_divisor=26.0,
            statutory_ceiling=2000000.0
        )
        res = self.calculator.calculate(data)
        self.assertAlmostEqual(res.raw_gratuity_amount, 288461.54, places=2)
        self.assertAlmostEqual(res.final_gratuity_amount, 288461.54, places=2)
        self.assertFalse(res.is_ceiling_applied)

    def test_02_statutory_ceiling_applied(self):
        """
        Test gratuity capping when raw amount exceeds statutory ceiling (2,000,000).
        Basic + DA = 500,000, Completed Years = 30.
        Raw = (500000 / 26) * 15 * 30 = 8653846.15 > 2000000 -> Capped at 2000000.
        """
        data = GratuityCalculationData(
            wage_base=500000.0,
            completed_years=30,
            days_multiplier=15.0,
            month_divisor=26.0,
            statutory_ceiling=2000000.0
        )
        res = self.calculator.calculate(data)
        self.assertTrue(res.is_ceiling_applied)
        self.assertEqual(res.capped_gratuity_amount, 2000000.0)
        self.assertEqual(res.final_gratuity_amount, 2000000.0)
        self.assertGreater(res.raw_gratuity_amount, 2000000.0)

    def test_03_zero_wage_or_service_edge_case(self):
        """Test zero wage base or zero completed years returns 0.0."""
        data_zero_wage = GratuityCalculationData(wage_base=0.0, completed_years=10)
        res1 = self.calculator.calculate(data_zero_wage)
        self.assertEqual(res1.final_gratuity_amount, 0.0)

        data_zero_years = GratuityCalculationData(wage_base=50000.0, completed_years=0)
        res2 = self.calculator.calculate(data_zero_years)
        self.assertEqual(res2.final_gratuity_amount, 0.0)

    def test_04_custom_parameters_calculation(self):
        """Test calculation with custom parameter values."""
        data = GratuityCalculationData(
            wage_base=30000.0,
            completed_years=5,
            days_multiplier=20.0,
            month_divisor=30.0,
            statutory_ceiling=1000000.0
        )
        # Raw = (30000 / 30) * 20 * 5 = 1000 * 20 * 5 = 100000.0
        res = self.calculator.calculate(data)
        self.assertEqual(res.final_gratuity_amount, 100000.0)
        self.assertFalse(res.is_ceiling_applied)
        self.assertEqual(res.days_multiplier_used, 20.0)
        self.assertEqual(res.month_divisor_used, 30.0)
        
        dict_output = res.to_dict()
        self.assertIsInstance(dict_output, dict)
        self.assertEqual(dict_output['final_gratuity_amount'], 100000.0)
