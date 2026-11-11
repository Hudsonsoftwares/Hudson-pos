# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.addons.hudson_in_payroll.services.professional_tax.pt_calculator import PTCalculator
from odoo.addons.hudson_in_payroll.services.professional_tax.professional_tax_slab_service import ProfessionalTaxSlabService


class TestPTCalculator(TransactionCase):

    def setUp(self):
        super(TestPTCalculator, self).setUp()
        self.calculator = PTCalculator()
        self.slab_service = ProfessionalTaxSlabService(self.env)
        self.state_mh = self.env.ref('base.state_in_mh')
        self.state_wb = self.env.ref('base.state_in_wb')

    def test_01_normal_slab_calculation(self):
        """Test standard calculation for non-override month (January - MH Male ₹15,000 gross)."""
        slab_result = self.slab_service.get_applicable_slab(
            salary=15000.0,
            state=self.state_mh,
            gender='male',
            eval_date='2026-01-15'
        )
        self.assertIsNotNone(slab_result)
        calc_result = self.calculator.calculate(slab=slab_result, eval_date='2026-01-15')

        self.assertEqual(calc_result.pt_amount, 200.0)
        self.assertEqual(calc_result.normal_amount, 200.0)
        self.assertFalse(calc_result.override_applied)
        self.assertEqual(calc_result.calculation_status, 'SUCCESS')
        self.assertEqual(calc_result.to_dict()['pt_amount'], 200.0)

    def test_02_override_month_calculation(self):
        """Test calculation for special override month (February - MH Male ₹15,000 gross → ₹300)."""
        slab_result = self.slab_service.get_applicable_slab(
            salary=15000.0,
            state=self.state_mh,
            gender='male',
            eval_date='2026-02-15'
        )
        self.assertIsNotNone(slab_result)
        calc_result = self.calculator.calculate(slab=slab_result, eval_date='2026-02-15')

        self.assertEqual(calc_result.pt_amount, 300.0)
        self.assertEqual(calc_result.normal_amount, 200.0)
        self.assertTrue(calc_result.override_applied)
        self.assertEqual(calc_result.override_month, '2')
        self.assertEqual(calc_result.override_amount, 300.0)
        self.assertEqual(calc_result.calculation_status, 'OVERRIDE_APPLIED')

    def test_03_no_override_configured(self):
        """Test calculation for slab with no monthly override configured (West Bengal)."""
        slab_result = self.slab_service.get_applicable_slab(
            salary=45000.0,
            state=self.state_wb,
            eval_date='2026-02-15'
        )
        self.assertIsNotNone(slab_result)
        calc_result = self.calculator.calculate(slab=slab_result, eval_date='2026-02-15')

        self.assertEqual(calc_result.pt_amount, 200.0)
        self.assertEqual(calc_result.normal_amount, 200.0)
        self.assertFalse(calc_result.override_applied)
        self.assertEqual(calc_result.calculation_status, 'SUCCESS')

    def test_04_no_slab_supplied(self):
        """Test calculation when None is passed as slab."""
        calc_result = self.calculator.calculate(slab=None, eval_date='2026-02-15')

        self.assertEqual(calc_result.pt_amount, 0.0)
        self.assertEqual(calc_result.normal_amount, 0.0)
        self.assertFalse(calc_result.override_applied)
        self.assertEqual(calc_result.calculation_status, 'NO_SLAB')

    def test_05_different_payroll_months(self):
        """Test calculation across all 12 months verifying override triggers ONLY in February."""
        slab_result = self.slab_service.get_applicable_slab(
            salary=15000.0,
            state=self.state_mh,
            gender='male',
            eval_date='2026-01-01'
        )
        self.assertIsNotNone(slab_result)

        for month in range(1, 13):
            eval_date_str = f"2026-{month:02d}-15"
            calc_res = self.calculator.calculate(slab=slab_result, eval_date=eval_date_str)
            if month == 2:
                self.assertEqual(calc_res.pt_amount, 300.0, f"Month {month} failed override check")
                self.assertTrue(calc_res.override_applied)
            else:
                self.assertEqual(calc_res.pt_amount, 200.0, f"Month {month} failed standard check")
                self.assertFalse(calc_res.override_applied)
