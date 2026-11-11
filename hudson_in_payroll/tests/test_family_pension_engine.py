# -*- coding: utf-8 -*-
from datetime import date
from odoo.tests.common import TransactionCase
from odoo.addons.hudson_in_payroll.services.tds.section_57iia_deduction_service import Section57IIADeductionService
from odoo.addons.hudson_in_payroll.services.tds.other_income_aggregation_service import OtherIncomeAggregationService
from odoo.addons.hudson_in_payroll.services.tds.deduction_calculation_service import DeductionCalculationService
from odoo.addons.hudson_in_payroll.services.tds.chapter6a_deduction_service import Chapter6aDeductionService
from odoo.addons.hudson_in_payroll.services.tds.tds_parameter_service import TdsParameterService


class TestFamilyPensionEngine(TransactionCase):
    """
    Exhaustive Statutory Unit Test Suite for Family Pension Treatment:
    - Section 57(iia) of Income-tax Act 1961 (FY <= 2025-26)
    - Section 93(1)(d) of Income-tax Act 2025 (FY >= 2026-27)
    - Treated under 'Income from Other Sources' (NOT a salary / Chapter VI-A deduction).
    - Standard deduction = min(1/3rd of pension, cap).
    - Cap = ₹25,000 (New Regime) / ₹15,000 (Old Regime).
    """

    def setUp(self):
        super().setUp()
        self.param_svc = TdsParameterService(self.env)
        self.fp_svc = Section57IIADeductionService(self.env)
        self.other_inc_svc = OtherIncomeAggregationService(self.env)
        self.deduction_svc = DeductionCalculationService(self.env)
        self.c6a_svc = Chapter6aDeductionService(self.env)
        self.company = self.env.company

        # Setup Financial Years
        self.fy2526 = self.env['tds.financial.year'].search([('name', '=', '2025-2026')], limit=1)
        if not self.fy2526:
            self.fy2526 = self.env['tds.financial.year'].create({
                'name': '2025-2026',
                'code': 'FY2025-26',
                'assessment_year': '2026-2027',
                'start_date': '2025-04-01',
                'end_date': '2026-03-31',
                'active': True,
            })

        self.fy2627 = self.env['tds.financial.year'].search([('name', '=', '2026-2027')], limit=1)
        if not self.fy2627:
            self.fy2627 = self.env['tds.financial.year'].create({
                'name': '2026-2027',
                'code': 'FY2026-27',
                'assessment_year': '2027-2028',
                'start_date': '2026-04-01',
                'end_date': '2027-03-31',
                'active': True,
            })

        # Setup Regimes
        self.regime_old = self.env['tds.tax.regime'].search([('code', '=', 'old')], limit=1)
        if not self.regime_old:
            self.regime_old = self.env['tds.tax.regime'].create({'name': 'Old Tax Regime', 'code': 'old'})

        self.regime_new = self.env['tds.tax.regime'].search([('code', '=', 'new')], limit=1)
        if not self.regime_new:
            self.regime_new = self.env['tds.tax.regime'].create({'name': 'New Tax Regime', 'code': 'new'})

        # Test Employee
        self.employee = self.env['hr.employee'].create({
            'name': 'Family Pension Test Employee',
            'company_id': self.company.id,
            'hds_in_residential_status': 'ror',
        })

    def _create_declaration(self, pension_amt=120000.0, regime='new', fy=None, state='draft', approved_amt=0.0):
        target_fy = fy or self.fy2526
        target_regime = self.regime_new if regime == 'new' else self.regime_old

        emp_regime = self.env['tds.employee.tax.regime'].search([
            ('employee_id', '=', self.employee.id),
            ('financial_year_id', '=', target_fy.id)
        ], limit=1)
        if emp_regime:
            emp_regime.write({'regime_id': target_regime.id})
        else:
            self.env['tds.employee.tax.regime'].create({
                'employee_id': self.employee.id,
                'financial_year_id': target_fy.id,
                'regime_id': target_regime.id
            })

        line_vals = []
        if approved_amt > 0.0 or state in ('proof_verified', 'approved'):
            line_vals.append((0, 0, {
                'category': '57iia',
                'description': 'Family Pension Proof',
                'declared_amount': pension_amt,
                'approved_amount': approved_amt,
                'tax_firm_approved_amount': approved_amt,
            }))

        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': target_fy.id,
            'tax_regime_id': target_regime.id,
            'state': state,
            'decl_57iia_family_pension': pension_amt,
            'declaration_line_ids': line_vals,
        })

        return decl

    def test_01_new_regime_capped(self):
        """
        Scenario 1: New Regime, ₹1,20,000 gross.
        1/3rd = ₹40,000. Cap = ₹25,000.
        Deduction = ₹25,000. Net other sources = ₹95,000.
        """
        decl = self._create_declaration(pension_amt=120000.0, regime='new', fy=self.fy2526)
        eval_date = date(2025, 7, 15)

        # 1. Section 57(iia) Service
        fp_res = self.fp_svc.validate_and_trace(decl, eval_date=eval_date, regime_code='new',
                                                employee=self.employee, financial_year=self.fy2526)
        self.assertEqual(fp_res.allowed_deduction, 25000.0)

        # 2. Other Income Aggregation
        oth_res = self.other_inc_svc.aggregate_other_income(self.employee, self.fy2526, eval_date=eval_date)
        self.assertEqual(oth_res.family_pension_gross, 120000.0)
        self.assertEqual(oth_res.family_pension_deduction, 25000.0)
        self.assertEqual(oth_res.family_pension_net, 95000.0)
        self.assertEqual(oth_res.total_other_sources, 95000.0)
        self.assertEqual(oth_res.total_other_income, 95000.0)

    def test_02_new_regime_below_cap(self):
        """
        Scenario 2: New Regime, ₹60,000 gross.
        1/3rd = ₹20,000. Cap = ₹25,000.
        Deduction = ₹20,000. Net other sources = ₹40,000.
        """
        decl = self._create_declaration(pension_amt=60000.0, regime='new', fy=self.fy2526)
        eval_date = date(2025, 7, 15)

        fp_res = self.fp_svc.validate_and_trace(decl, eval_date=eval_date, regime_code='new',
                                                employee=self.employee, financial_year=self.fy2526)
        self.assertEqual(fp_res.allowed_deduction, 20000.0)

        oth_res = self.other_inc_svc.aggregate_other_income(self.employee, self.fy2526, eval_date=eval_date)
        self.assertEqual(oth_res.family_pension_gross, 60000.0)
        self.assertEqual(oth_res.family_pension_deduction, 20000.0)
        self.assertEqual(oth_res.family_pension_net, 40000.0)
        self.assertEqual(oth_res.total_other_sources, 40000.0)

    def test_03_old_regime_capped(self):
        """
        Scenario 3: Old Regime, ₹1,20,000 gross.
        1/3rd = ₹40,000. Cap = ₹15,000.
        Deduction = ₹15,000. Net other sources = ₹1,05,000.
        """
        decl = self._create_declaration(pension_amt=120000.0, regime='old', fy=self.fy2526)
        eval_date = date(2025, 7, 15)

        fp_res = self.fp_svc.validate_and_trace(decl, eval_date=eval_date, regime_code='old',
                                                employee=self.employee, financial_year=self.fy2526)
        self.assertEqual(fp_res.allowed_deduction, 15000.0)

        oth_res = self.other_inc_svc.aggregate_other_income(self.employee, self.fy2526, eval_date=eval_date)
        self.assertEqual(oth_res.family_pension_gross, 120000.0)
        self.assertEqual(oth_res.family_pension_deduction, 15000.0)
        self.assertEqual(oth_res.family_pension_net, 105000.0)
        self.assertEqual(oth_res.total_other_sources, 105000.0)

    def test_04_old_regime_below_cap(self):
        """
        Scenario 4: Old Regime, ₹30,000 gross.
        1/3rd = ₹10,000. Cap = ₹15,000.
        Deduction = ₹10,000. Net other sources = ₹20,000.
        """
        decl = self._create_declaration(pension_amt=30000.0, regime='old', fy=self.fy2526)
        eval_date = date(2025, 7, 15)

        fp_res = self.fp_svc.validate_and_trace(decl, eval_date=eval_date, regime_code='old',
                                                employee=self.employee, financial_year=self.fy2526)
        self.assertEqual(fp_res.allowed_deduction, 10000.0)

        oth_res = self.other_inc_svc.aggregate_other_income(self.employee, self.fy2526, eval_date=eval_date)
        self.assertEqual(oth_res.family_pension_gross, 30000.0)
        self.assertEqual(oth_res.family_pension_deduction, 10000.0)
        self.assertEqual(oth_res.family_pension_net, 20000.0)
        self.assertEqual(oth_res.total_other_sources, 20000.0)

    def test_05_no_double_counting_in_deductions(self):
        """
        Scenario 5: Verify Family Pension deduction is NOT double-counted in
        Chapter VI-A (Old Regime) or allowable deductions (New Regime).
        """
        # Test in New Regime
        decl_new = self._create_declaration(pension_amt=120000.0, regime='new', fy=self.fy2526)
        eval_date = date(2025, 7, 15)

        # Regimes context DTO
        regime_ctx_new = type('RegimeCalculationContext', (), {
            'regime_code': 'new',
            'regime_name': 'New Tax Regime',
            'regime_id': self.regime_new.id,
            'gross_total_income': 1000000.0
        })()
        ded_calc_new = self.deduction_svc.calculate_deductions(
            employee=self.employee, financial_year=self.fy2526,
            regime_context=regime_ctx_new, eval_date=eval_date
        )
        # family_pension_57iia is preserved as attribute for trace, but NOT added into total_allowable_deductions
        self.assertEqual(ded_calc_new.total_chapter_6a, 0.0)
        # Total allowable deductions in new regime should only include standard deduction (₹75,000) and employer NPS
        self.assertNotIn(ded_calc_new.family_pension_57iia, [ded_calc_new.total_allowable_deductions])
        self.assertEqual(ded_calc_new.total_allowable_deductions, ded_calc_new.standard_deduction)

        # Test in Old Regime
        decl_old = self._create_declaration(pension_amt=120000.0, regime='old', fy=self.fy2526)
        c6a_res = self.c6a_svc.calculate_chapter_6a_deductions(self.employee, self.fy2526, 'old', eval_date=eval_date, declaration_id=decl_old)
        self.assertEqual(getattr(c6a_res, 'section_57iia', 0.0), 0.0)
        # 57(iia) is completely excluded from other_80_deductions and total_chapter_6a
        self.assertEqual(c6a_res.other_80_deductions, 0.0)
        self.assertEqual(c6a_res.total_chapter_6a, 0.0)

    def test_06_proof_phase_verification(self):
        """
        Scenario 6: In proof verification phase, 1/3rd must be computed from
        approved pension amount, not declared pension amount.
        Declared: ₹1,20,000. Approved: ₹60,000.
        1/3rd of ₹60,000 = ₹20,000. Cap = ₹25,000 (New Regime).
        Eligible deduction = ₹20,000. Net pension in other sources = ₹40,000.
        """
        decl = self._create_declaration(pension_amt=120000.0, regime='new', fy=self.fy2526,
                                        state='proof_verified', approved_amt=60000.0)
        eval_date = date(2026, 1, 15)

        fp_res = self.fp_svc.validate_and_trace(decl, eval_date=eval_date, regime_code='new',
                                                employee=self.employee, financial_year=self.fy2526)
        self.assertEqual(fp_res.allowed_deduction, 20000.0)

        oth_res = self.other_inc_svc.aggregate_other_income(self.employee, self.fy2526, eval_date=eval_date)
        self.assertEqual(oth_res.family_pension_gross, 60000.0)
        self.assertEqual(oth_res.family_pension_deduction, 20000.0)
        self.assertEqual(oth_res.family_pension_net, 40000.0)

    def test_07_edge_cases_zero_and_lines(self):
        """
        Scenario 7: Edge cases:
        - Pension = 0 -> deduction = 0, net = 0.
        - Line-only declaration without header -> correctly detected.
        """
        # Zero pension
        decl_zero = self._create_declaration(pension_amt=0.0, regime='new', fy=self.fy2526)
        oth_zero = self.other_inc_svc.aggregate_other_income(self.employee, self.fy2526, eval_date=date(2025, 7, 1))
        self.assertEqual(oth_zero.family_pension_gross, 0.0)
        self.assertEqual(oth_zero.family_pension_deduction, 0.0)
        self.assertEqual(oth_zero.family_pension_net, 0.0)

        # Line-only declaration
        decl_line = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy2526.id,
            'tax_regime_id': self.regime_new.id,
            'state': 'draft',
            'decl_57iia_family_pension': 0.0,
        })
        self.env['tds.employee.declaration.line'].create({
            'declaration_id': decl_line.id,
            'category': '57iia',
            'description': 'Pension line only',
            'declared_amount': 90000.0,
        })
        oth_line = self.other_inc_svc.aggregate_other_income(self.employee, self.fy2526, eval_date=date(2025, 7, 1))
        self.assertEqual(oth_line.family_pension_gross, 90000.0)
        # 1/3rd of 90,000 = 30,000 -> capped at 25,000
        self.assertEqual(oth_line.family_pension_deduction, 25000.0)
        self.assertEqual(oth_line.family_pension_net, 65000.0)

    def test_08_dynamic_legal_reference_label(self):
        """
        Scenario 8: Dynamic legal reference label:
        - FY 2025-26: "Section 57(iia), Income-tax Act 1961"
        - FY 2026-27: "Section 93(1)(d), Income-tax Act 2025"
        """
        label_2526 = Section57IIADeductionService.get_legal_reference_label(self.fy2526)
        self.assertIn("Section 57(iia)", label_2526)
        self.assertIn("1961", label_2526)

        code_2526 = Section57IIADeductionService.get_statutory_section_code(self.fy2526)
        self.assertEqual(code_2526, "57(iia)")

        label_2627 = Section57IIADeductionService.get_legal_reference_label(self.fy2627)
        self.assertIn("Section 93(1)(d)", label_2627)
        self.assertIn("2025", label_2627)

        code_2627 = Section57IIADeductionService.get_statutory_section_code(self.fy2627)
        self.assertEqual(code_2627, "93(1)(d)")

    def test_09_declaration_form_total_other_sources_includes_family_pension(self):
        """
        Verify that Tab 4 'Income from Other Sources' on tds.employee.declaration
        correctly sums savings interest, FD interest, dividend, misc, AND family pension.
        """
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy2526.id,
            'tax_regime_id': self.regime_new.id,
            'state': 'draft',
            'savings_bank_interest': 10000.0,
            'fixed_deposit_interest': 0.0,
            'dividend_income': 0.0,
            'other_sources_income': 10000.0,
            'decl_57iia_family_pension': 12000.0,
        })
        self.assertEqual(decl.total_other_sources_income, 32000.0)

        # Dynamic update when family pension amount changes
        decl.write({'decl_57iia_family_pension': 18000.0})
        self.assertEqual(decl.total_other_sources_income, 38000.0)
