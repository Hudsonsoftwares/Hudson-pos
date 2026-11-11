# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
try:
    from odoo.addons.hudson_in_payroll.services.tds.surcharge_engine_service import SurchargeEngineService
    from odoo.addons.hudson_in_payroll.services.tds.income_tax_slab_service import IncomeTaxSlabService
    from odoo.addons.hudson_in_payroll.services.tds.health_education_cess_service import HealthEducationCessService
except ImportError:
    from hudson_in_payroll.services.tds.surcharge_engine_service import SurchargeEngineService
    from hudson_in_payroll.services.tds.income_tax_slab_service import IncomeTaxSlabService
    from hudson_in_payroll.services.tds.health_education_cess_service import HealthEducationCessService


class TestTdsSurchargeMarginalRelief(TransactionCase):
    """
    Automated Test Suite for TDS Surcharge and Statutory Marginal Relief.
    Verifies statutory thresholds (50L, 1Cr, 2Cr, 5Cr), marginal relief caps,
    and payslip breakdown alignment for Old and New Tax Regimes.
    """

    def setUp(self):
        super(TestTdsSurchargeMarginalRelief, self).setUp()
        self.fy = self.env['tds.financial.year'].search([('code', '=', '2025-2026')], limit=1)
        if not self.fy:
            self.fy = self.env['tds.financial.year'].create({
                'name': 'Financial Year 2025-2026',
                'code': '2025-2026',
                'start_date': '2025-04-01',
                'end_date': '2026-03-31',
                'is_active': True,
            })
        self.surcharge_svc = SurchargeEngineService(self.env)
        self.slab_svc = IncomeTaxSlabService(self.env)
        self.cess_svc = HealthEducationCessService(self.env)

    def test_01_below_threshold(self):
        """Case 1: Below ₹50,00,000 threshold -> No surcharge and no marginal relief."""
        income = 4500000.0  # ₹45 Lakh
        tax_res = self.slab_svc.calculate_base_tax(income, self.fy, regime_code='old')
        tax_before_surcharge = tax_res.base_tax_liability

        res = self.surcharge_svc.calculate_surcharge(
            net_taxable_income=income,
            tax_after_rebate=tax_before_surcharge,
            financial_year=self.fy,
            regime_code='old'
        )

        self.assertFalse(res.is_applicable)
        self.assertEqual(res.surcharge_rate_pct, 0.0)
        self.assertEqual(res.surcharge_before_relief, 0.0)
        self.assertEqual(res.marginal_relief, 0.0)
        self.assertEqual(res.surcharge_amount, 0.0)
        self.assertEqual(res.surcharge, 0.0)
        self.assertEqual(res.tax_plus_surcharge, tax_before_surcharge)

    def test_02_just_above_50_lakh_with_marginal_relief(self):
        """
        Case 2: Income = ₹50,10,000 (just above ₹50 Lakh).
        Must apply 10% surcharge, calculate marginal relief, and ensure:
        Tax + Final Surcharge <= Tax at 50L + Excess Income (₹10,000).
        """
        income = 5010000.0
        tax_res = self.slab_svc.calculate_base_tax(income, self.fy, regime_code='old')
        tax_at_50l_res = self.slab_svc.calculate_base_tax(5000000.0, self.fy, regime_code='old')

        tax_before_surcharge = tax_res.base_tax_liability
        tax_at_50l = tax_at_50l_res.base_tax_liability
        excess_income = income - 5000000.0

        res = self.surcharge_svc.calculate_surcharge(
            net_taxable_income=income,
            tax_after_rebate=tax_before_surcharge,
            financial_year=self.fy,
            regime_code='old'
        )

        # 1. Surcharge eligible
        self.assertTrue(res.is_applicable)
        # 2. 10% rate
        self.assertEqual(res.surcharge_rate_pct, 10.0)
        # 3. Normal surcharge before relief
        expected_surcharge_pre = round(tax_before_surcharge * 0.10, 2)
        self.assertEqual(res.surcharge_before_relief, expected_surcharge_pre)
        # 4. Marginal relief must be positive
        self.assertGreater(res.marginal_relief, 0.0)
        # 5. Final surcharge must be reduced
        self.assertLess(res.surcharge_amount, res.surcharge_before_relief)
        self.assertEqual(res.surcharge_amount, round(res.surcharge_before_relief - res.marginal_relief, 2))
        # 6. Core statutory invariant: Tax + Final Surcharge <= Tax at 50L + Excess Income
        max_allowed = tax_at_50l + excess_income
        self.assertAlmostEqual(res.tax_plus_surcharge, max_allowed, places=2)

        # 7. Cess applied strictly after marginal relief
        cess_res = self.cess_svc.calculate_cess(tax_plus_surcharge=res.tax_plus_surcharge)
        expected_cess = round(res.tax_plus_surcharge * 0.04, 2)
        self.assertEqual(cess_res.cess_amount, expected_cess)
        self.assertEqual(cess_res.total_annual_tax_liability, res.tax_plus_surcharge + expected_cess)

    def test_03_boundary_50_lakh(self):
        """
        Case 3: Boundary testing around ₹50,00,000 threshold.
        - ₹49,99,999 -> No Surcharge
        - ₹50,00,000 -> No Surcharge
        - ₹50,00,001 -> Surcharge Eligible (10%) with Marginal Relief
        """
        tax_49_99 = self.slab_svc.calculate_base_tax(4999999.0, self.fy, regime_code='old').base_tax_liability
        res_49_99 = self.surcharge_svc.calculate_surcharge(4999999.0, tax_49_99, self.fy, 'old')
        self.assertFalse(res_49_99.is_applicable)
        self.assertEqual(res_49_99.surcharge_amount, 0.0)
        self.assertEqual(res_49_99.marginal_relief, 0.0)

        tax_50_00 = self.slab_svc.calculate_base_tax(5000000.0, self.fy, regime_code='old').base_tax_liability
        res_50_00 = self.surcharge_svc.calculate_surcharge(5000000.0, tax_50_00, self.fy, 'old')
        self.assertFalse(res_50_00.is_applicable)
        self.assertEqual(res_50_00.surcharge_amount, 0.0)
        self.assertEqual(res_50_00.marginal_relief, 0.0)

        tax_50_01 = self.slab_svc.calculate_base_tax(5000001.0, self.fy, regime_code='old').base_tax_liability
        res_50_01 = self.surcharge_svc.calculate_surcharge(5000001.0, tax_50_01, self.fy, 'old')
        self.assertTrue(res_50_01.is_applicable)
        self.assertEqual(res_50_01.surcharge_rate_pct, 10.0)
        self.assertGreater(res_50_01.marginal_relief, 0.0)
        self.assertGreater(res_50_01.surcharge_amount, 0.0)
        # Invariant check
        self.assertAlmostEqual(res_50_01.tax_plus_surcharge, tax_50_00 + 1.0, places=2)

    def test_04_higher_threshold_1_crore(self):
        """
        Case 4: ₹1 Crore threshold.
        - ₹1,00,00,000 -> 10% Surcharge
        - ₹1,01,00,000 -> 15% Surcharge with marginal relief relative to 1 Crore (10%)
        """
        tax_1cr = self.slab_svc.calculate_base_tax(10000000.0, self.fy, regime_code='old').base_tax_liability
        res_1cr = self.surcharge_svc.calculate_surcharge(10000000.0, tax_1cr, self.fy, 'old')
        self.assertEqual(res_1cr.surcharge_rate_pct, 10.0)

        income_101 = 10100000.0
        tax_101 = self.slab_svc.calculate_base_tax(income_101, self.fy, regime_code='old').base_tax_liability
        res_101 = self.surcharge_svc.calculate_surcharge(income_101, tax_101, self.fy, 'old')

        self.assertEqual(res_101.surcharge_rate_pct, 15.0)
        self.assertGreater(res_101.marginal_relief, 0.0)
        # Invariant: Tax + Final Surcharge <= (Tax at 1Cr + 10% Surcharge at 1Cr) + Excess Income
        surcharge_at_1cr = round(tax_1cr * 0.10, 2)
        max_allowed = tax_1cr + surcharge_at_1cr + (income_101 - 10000000.0)
        self.assertAlmostEqual(res_101.tax_plus_surcharge, max_allowed, places=2)

    def test_05_thresholds_2_crore_and_5_crore_regimes(self):
        """
        Case 5: ₹2 Crore and ₹5 Crore thresholds under Old and New Regimes.
        - ₹2,01,00,000 -> 25% Surcharge with marginal relief relative to 2 Crore (15%).
        - ₹5,01,00,000:
          - Old Regime: 37% rate, marginal relief relative to 5 Crore (25%).
          - New Regime: capped at 25% rate.
        """
        # 2 Crore Boundary (Old Regime)
        tax_2cr = self.slab_svc.calculate_base_tax(20000000.0, self.fy, regime_code='old').base_tax_liability
        surcharge_at_2cr = round(tax_2cr * 0.15, 2)
        income_201 = 20100000.0
        tax_201 = self.slab_svc.calculate_base_tax(income_201, self.fy, regime_code='old').base_tax_liability
        res_201 = self.surcharge_svc.calculate_surcharge(income_201, tax_201, self.fy, 'old')

        self.assertEqual(res_201.surcharge_rate_pct, 25.0)
        self.assertGreater(res_201.marginal_relief, 0.0)
        max_allowed_2cr = tax_2cr + surcharge_at_2cr + (income_201 - 20000000.0)
        self.assertAlmostEqual(res_201.tax_plus_surcharge, max_allowed_2cr, places=2)

        # 5 Crore Boundary: Old Regime (37%)
        tax_5cr_old = self.slab_svc.calculate_base_tax(50000000.0, self.fy, regime_code='old').base_tax_liability
        surcharge_at_5cr_old = round(tax_5cr_old * 0.25, 2)
        income_501 = 50100000.0
        tax_501_old = self.slab_svc.calculate_base_tax(income_501, self.fy, regime_code='old').base_tax_liability
        res_501_old = self.surcharge_svc.calculate_surcharge(income_501, tax_501_old, self.fy, 'old')

        self.assertEqual(res_501_old.surcharge_rate_pct, 37.0)
        self.assertGreater(res_501_old.marginal_relief, 0.0)
        max_allowed_5cr = tax_5cr_old + surcharge_at_5cr_old + (income_501 - 50000000.0)
        self.assertAlmostEqual(res_501_old.tax_plus_surcharge, max_allowed_5cr, places=2)

        # 5 Crore Boundary: New Regime (25% capped)
        tax_501_new = self.slab_svc.calculate_base_tax(income_501, self.fy, regime_code='new').base_tax_liability
        res_501_new = self.surcharge_svc.calculate_surcharge(income_501, tax_501_new, self.fy, 'new')
        self.assertEqual(res_501_new.surcharge_rate_pct, 25.0)

    def test_06_payslip_breakdown_dto(self):
        """Case 6: Verification of DTO dictionary and payslip tax summary structure."""
        income = 5010000.0
        tax_res = self.slab_svc.calculate_base_tax(income, self.fy, regime_code='old')
        sur_res = self.surcharge_svc.calculate_surcharge(income, tax_res.base_tax_liability, self.fy, 'old')
        cess_res = self.cess_svc.calculate_cess(sur_res.tax_plus_surcharge)

        d = sur_res.to_dict()
        self.assertIn('surcharge_before_relief', d)
        self.assertIn('marginal_relief', d)
        self.assertIn('surcharge_amount', d)
        self.assertIn('tax_plus_surcharge', d)

        # Check arithmetic consistency
        self.assertEqual(d['surcharge_amount'], round(d['surcharge_before_relief'] - d['marginal_relief'], 2))
        self.assertEqual(d['tax_plus_surcharge'], round(d['tax_after_rebate'] + d['surcharge_amount'], 2))
        self.assertEqual(cess_res.total_annual_tax_liability, round(d['tax_plus_surcharge'] + cess_res.cess_amount, 2))
