# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase# pyrefly: ignore [missing-import]
from odoo import fields# pyrefly: ignore [missing-import]


class TestTdsPhase6TaxComputation(TransactionCase):

    def setUp(self):
        super(TestTdsPhase6TaxComputation, self).setUp()
        self.fy = self.env['tds.financial.year'].search([('code', '=', '2025-2026')], limit=1)
        if not self.fy:
            self.fy = self.env['tds.financial.year'].create({
                'name': 'Financial Year 2025-2026',
                'code': '2025-2026',
                'start_date': '2025-04-01',
                'assessment_year': '2026-2027',
                'active': True,
            })

    def test_01_taxable_income_service(self):
        """Test TaxableIncomeService calculating Net Taxable Income = max(0, GTI - Deductions)."""
        from odoo.addons.hudson_in_payroll.services.tds.taxable_income_service import TaxableIncomeService# pyrefly: ignore [missing-import]
        svc = TaxableIncomeService(self.env)

        res = svc.calculate_taxable_income(gross_total_income=1000000.0, total_approved_deductions=250000.0)
        self.assertEqual(res.net_taxable_income, 750000.0)

        # High deduction zero floor test
        res_zero = svc.calculate_taxable_income(gross_total_income=300000.0, total_approved_deductions=400000.0)
        self.assertEqual(res_zero.net_taxable_income, 0.0)

    def test_02_income_tax_slab_service_new_regime(self):
        """Test IncomeTaxSlabService progressive slab rates under New Regime FY 2025-26."""
        from odoo.addons.hudson_in_payroll.services.tds.income_tax_slab_service import IncomeTaxSlabService# pyrefly: ignore [missing-import]
        svc = IncomeTaxSlabService(self.env)

        # Taxable Income = ₹12,00,000 under New Regime
        # Slabs: 0-4L@0% (0), 4L-8L@5% (20,000), 8L-12L@10% (40,000) -> Base Tax = ₹60,000
        res = svc.calculate_base_tax(net_taxable_income=1200000.0, financial_year=self.fy, regime_code='new')
        self.assertEqual(res.base_tax_liability, 60000.0)

    def test_03_rebate_engine_service_section_87a_and_marginal_relief(self):
        """Test Section 87A rebate and Section 115BAC marginal relief."""
        from odoo.addons.hudson_in_payroll.services.tds.rebate_engine_service import RebateEngineService# pyrefly: ignore [missing-import]
        svc = RebateEngineService(self.env)

        # 1. New Regime Taxable Income ₹6,50,000 (<= 7.0L threshold) -> Full 87A rebate
        res_full = svc.apply_rebate(net_taxable_income=650000.0, base_tax_liability=12500.0, regime_code='new')
        self.assertEqual(res_full.rebate_applied, 12500.0)
        self.assertEqual(res_full.tax_after_rebate, 0.0)

        # 2. New Regime Taxable Income ₹7,10,000 (Slightly > 7.0L) -> Marginal relief applied so tax <= 10,000
        res_marginal = svc.apply_rebate(net_taxable_income=710000.0, base_tax_liability=15500.0, regime_code='new')
        self.assertGreater(res_marginal.rebate_applied, 0.0)
        self.assertEqual(res_marginal.tax_after_rebate, 10000.0)

    def test_04_surcharge_and_cess_services(self):
        """Test SurchargeEngineService and HealthEducationCessService."""
        from odoo.addons.hudson_in_payroll.services.tds.surcharge_engine_service import SurchargeEngineService# pyrefly: ignore [missing-import]
        from odoo.addons.hudson_in_payroll.services.tds.health_education_cess_service import HealthEducationCessService# pyrefly: ignore [missing-import]

        sur_svc = SurchargeEngineService(self.env)
        cess_svc = HealthEducationCessService(self.env)

        # 1. Low income (No surcharge)
        sur_res = sur_svc.calculate_surcharge(net_taxable_income=1000000.0, tax_after_rebate=50000.0, financial_year=self.fy, regime_code='new')
        self.assertEqual(sur_res.surcharge_amount, 0.0)
        self.assertEqual(sur_res.surcharge_before_relief, 0.0)
        self.assertEqual(sur_res.marginal_relief, 0.0)
        self.assertFalse(sur_res.is_applicable)

        # 2. Cess (4% of ₹50,000 = ₹2,000)
        cess_res = cess_svc.calculate_cess(tax_plus_surcharge=50000.0)
        self.assertEqual(cess_res.cess_amount, 2000.0)
        self.assertEqual(cess_res.total_annual_tax_liability, 52000.0)

    def test_05_section_288b_cess_and_tax_rounding(self):
        """Test Section 288B statutory rounding to nearest ₹10 on Health & Education Cess and Total Annual Tax."""
        # pyrefly: ignore [missing-import]
        from odoo.addons.hudson_in_payroll.services.tds.health_education_cess_service import HealthEducationCessService
        cess_svc = HealthEducationCessService(self.env)

        # 1. Real-world case from unrounded payroll trace:
        # Tax + Surcharge = ₹1,538,090.40, Cess (4%) = ₹61,523.62, Unrounded = ₹1,599,614.02
        # Section 288B: 0.02 paise ignored -> ₹1,599,614 -> last digit 4 (< 5) -> rounds down to ₹1,599,610.00
        res1 = cess_svc.calculate_cess(tax_plus_surcharge=1538090.40)
        self.assertEqual(res1.cess_amount, 61523.62)
        self.assertEqual(res1.unrounded_annual_tax, 1599614.02)
        self.assertEqual(res1.total_annual_tax_liability, 1599610.0)
        self.assertEqual(res1.rounding_factor_288b, -4.02)
        self.assertEqual(res1.cess_rate, 4.0)

        # 2. Rounding up case (remainder >= 5):
        # Tax + Surcharge = ₹10,005.00, Cess (4%) = ₹400.20, Unrounded = ₹10,405.20
        # Section 288B: 0.20 paise ignored -> ₹10,405 -> last digit 5 (>= 5) -> rounds up to ₹10,410.00
        res2 = cess_svc.calculate_cess(tax_plus_surcharge=10005.0)
        self.assertEqual(res2.cess_amount, 400.20)
        self.assertEqual(res2.unrounded_annual_tax, 10405.20)
        self.assertEqual(res2.total_annual_tax_liability, 10410.0)
        self.assertEqual(res2.rounding_factor_288b, 4.80)

        # 3. Direct Section 288B static method tests:
        # 35,804.99: paise ignored -> 35,804 -> last digit 4 -> 35,800.0
        self.assertEqual(HealthEducationCessService.round_tax_to_nearest_10(35804.99), 35800.0)
        # 35,805.01: paise ignored -> 35,805 -> last digit 5 -> 35,810.0
        self.assertEqual(HealthEducationCessService.round_tax_to_nearest_10(35805.01), 35810.0)
        # 0 or None:
        self.assertEqual(HealthEducationCessService.round_tax_to_nearest_10(0.0), 0.0)
        self.assertEqual(HealthEducationCessService.round_tax_to_nearest_10(None), 0.0)

