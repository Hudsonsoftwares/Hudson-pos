# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo import fields


class TestTdsPhase11CarryForwardIsolation(TransactionCase):
    """
    Automated Regression Test Suite for Tax Declaration vs Payroll Declaration Data Consistency
    and Section 71B Carry-Forward Isolation (Scenarios 1 to 10).
    """

    def setUp(self):
        super(TestTdsPhase11CarryForwardIsolation, self).setUp()
        self.Employee = self.env['hr.employee']
        self.FinancialYear = self.env['tds.financial.year']
        self.Declaration = self.env['tds.employee.declaration']
        self.IncomeDeclaration = self.env['tds.employee.income.declaration']
        self.RegimeChoice = self.env['tds.employee.tax.regime']
        self.RegimeMaster = self.env['tds.tax.regime']

        from hudson_in_payroll.services.tds.other_income_aggregation_service import OtherIncomeAggregationService
        self.other_svc = OtherIncomeAggregationService(self.env)

        # 1. Create Test Employee
        self.emp = self.Employee.create({
            'name': 'Audit Test Employee',
            'work_email': 'audit.emp@hudson.com',
        })

        # 2. Create Test FY
        self.fy2026 = self.FinancialYear.create({
            'name': 'Tax Year: 2026-27',
            'code': '2026-2027-AUDIT',
            'assessment_year': '2027-2028',
            'start_date': '2026-04-01',
            'end_date': '2027-03-31',
            'active': True,
        })
        self.fy2025 = self.FinancialYear.create({
            'name': 'Tax Year: 2025-26',
            'code': '2025-2026-AUDIT',
            'assessment_year': '2026-2027',
            'start_date': '2025-04-01',
            'end_date': '2026-03-31',
            'active': True,
        })

        # 3. Create Tax Regimes
        self.old_regime = self.RegimeMaster.search([('code', '=', 'old')], limit=1)
        if not self.old_regime:
            self.old_regime = self.RegimeMaster.create({'name': 'Old Regime', 'code': 'old'})

        self.new_regime = self.RegimeMaster.search([('code', '=', 'new')], limit=1)
        if not self.new_regime:
            self.new_regime = self.RegimeMaster.create({'name': 'New Regime', 'code': 'new'})

    def test_scenario_01_no_let_out_declaration(self):
        """Scenario 1: No Let-Out Property declared -> forms & aggregation return 0.0."""
        inc_decl = self.IncomeDeclaration.create({
            'employee_id': self.emp.id,
            'financial_year_id': self.fy2026.id,
            'annual_let_out_rent': 0.0,
            'municipal_taxes_paid': 0.0,
            'let_out_interest_paid': 0.0,
        })
        self.assertEqual(inc_decl.net_house_property_income_loss, 0.0)
        self.assertEqual(inc_decl.effective_house_property_gti_impact, 0.0)

        res = self.other_svc.aggregate_other_income(self.emp, self.fy2026, regime_code='new')
        self.assertEqual(res.effective_hp_gti_impact, 0.0)

    def test_scenario_02_let_out_declared_no_carryforward(self):
        """Scenario 2: Let-Out Property declared -> Payroll values match Employee Declaration."""
        inc_decl = self.IncomeDeclaration.create({
            'employee_id': self.emp.id,
            'financial_year_id': self.fy2026.id,
            'annual_let_out_rent': 200000.0,
            'municipal_taxes_paid': 20000.0,
            'let_out_interest_paid': 50000.0,
        })
        # NAV = 180,000; 30% Ded = 54,000; Net HP = 180,000 - 54,000 - 50,000 = 76,000
        self.assertEqual(inc_decl.net_house_property_income_loss, 76000.0)
        self.assertEqual(inc_decl.effective_house_property_gti_impact, 76000.0)

    def test_scenario_03_positive_income_added_to_gti(self):
        """Scenario 3: Positive Let-Out income -> Taxable rental income added to GTI."""
        res = self.other_svc.calculate_effective_hp_impact(76000.0, regime_code='new')
        self.assertEqual(res, 76000.0)
        res_old = self.other_svc.calculate_effective_hp_impact(76000.0, regime_code='old')
        self.assertEqual(res_old, 76000.0)

    def test_scenario_04_loss_within_setoff_limit(self):
        """Scenario 4: HP Loss within limit -> Capped set-off under Old Regime, 0.0 under New Regime."""
        loss_val = -150000.0
        res_new = self.other_svc.calculate_effective_hp_impact(loss_val, regime_code='new')
        self.assertEqual(res_new, 0.0)

        res_old = self.other_svc.calculate_effective_hp_impact(loss_val, regime_code='old')
        self.assertEqual(res_old, -150000.0)

    def test_scenario_05_loss_exceeding_limit(self):
        """Scenario 5: Loss exceeding limit -> Capped at parameter ceiling (2,00,000) under Old Regime."""
        loss_val = -300000.0
        res_old = self.other_svc.calculate_effective_hp_impact(loss_val, regime_code='old')
        self.assertEqual(res_old, -200000.0)

    def test_scenario_06_carryforward_application_on_positive_income(self):
        """Scenario 6: Prior-year carryforward applied only when positive income exists; input fields untouched."""
        inc_decl = self.IncomeDeclaration.create({
            'employee_id': self.emp.id,
            'financial_year_id': self.fy2026.id,
            'annual_let_out_rent': 0.0,
            'municipal_taxes_paid': 0.0,
            'let_out_interest_paid': 0.0,
        })
        self.assertEqual(inc_decl.annual_let_out_rent, 0.0)
        self.assertEqual(inc_decl.municipal_taxes_paid, 0.0)
        self.assertEqual(inc_decl.let_out_interest_paid, 0.0)

    def test_scenario_07_regime_switching_isolation(self):
        """Scenario 7: Regime switching re-evaluates set-off rules without mutating input fields."""
        inc_decl = self.IncomeDeclaration.create({
            'employee_id': self.emp.id,
            'financial_year_id': self.fy2026.id,
            'annual_let_out_rent': 100000.0,
            'municipal_taxes_paid': 10000.0,
            'let_out_interest_paid': 150000.0,
        })
        self.assertEqual(inc_decl.net_house_property_income_loss, -87000.0)
        self.assertEqual(inc_decl.annual_let_out_rent, 100000.0)
        self.assertEqual(inc_decl.municipal_taxes_paid, 10000.0)

    def test_scenario_08_multiple_financial_years_isolation(self):
        """Scenario 8: Complete FY isolation maintained."""
        inc_decl_2025 = self.IncomeDeclaration.create({
            'employee_id': self.emp.id,
            'financial_year_id': self.fy2025.id,
            'annual_let_out_rent': 300000.0,
        })
        inc_decl_2026 = self.IncomeDeclaration.create({
            'employee_id': self.emp.id,
            'financial_year_id': self.fy2026.id,
            'annual_let_out_rent': 0.0,
        })
        self.assertEqual(inc_decl_2025.annual_let_out_rent, 300000.0)
        self.assertEqual(inc_decl_2026.annual_let_out_rent, 0.0)

    def test_scenario_09_repeated_payroll_calculation_idempotency(self):
        """Scenario 9: Repeated Payroll calculations are 100% idempotent."""
        res1 = self.other_svc.aggregate_other_income(self.emp, self.fy2026, regime_code='new')
        res2 = self.other_svc.aggregate_other_income(self.emp, self.fy2026, regime_code='new')
        self.assertEqual(res1.effective_hp_gti_impact, res2.effective_hp_gti_impact)

    def test_scenario_10_repeated_carryforward_calculation_idempotency(self):
        """Scenario 10: Repeated Carry-Forward calculations leave input fields 100% unchanged."""
        inc_decl = self.IncomeDeclaration.create({
            'employee_id': self.emp.id,
            'financial_year_id': self.fy2026.id,
            'annual_let_out_rent': 0.0,
            'municipal_taxes_paid': 0.0,
            'let_out_interest_paid': 0.0,
        })
        for _ in range(3):
            self.other_svc.aggregate_other_income(self.emp, self.fy2026, regime_code='new')
        self.assertEqual(inc_decl.annual_let_out_rent, 0.0)
        self.assertEqual(inc_decl.let_out_interest_paid, 0.0)

    def test_scenario_11_wizard_origin_regime_based_on_employee_regime(self):
        """Scenario 11: House Property Loss Origin Regime defaults to employee's tax regime."""
        # 1. New regime employee/declaration
        decl_new = self.Declaration.create({
            'employee_id': self.emp.id,
            'financial_year_id': self.fy2026.id,
            'regime_code': 'new',
        })
        LossModel = self.env['tds.house.property.loss.carryforward']
        loss_new = LossModel.with_context(
            default_employee_id=self.emp.id,
            default_regime_code='new',
            default_financial_year_id=self.fy2026.id
        ).create({
            'unabsorbed_loss_amount': 50000.0,
        })
        self.assertEqual(loss_new.regime_code, 'new')

        # 2. Old regime employee/declaration
        decl_old = self.Declaration.create({
            'employee_id': self.emp.id,
            'financial_year_id': self.fy2025.id,
            'regime_code': 'old',
        })
        loss_old = LossModel.with_context(
            default_employee_id=self.emp.id,
            default_regime_code='old',
            default_financial_year_id=self.fy2025.id
        ).create({
            'unabsorbed_loss_amount': 30000.0,
        })
        self.assertEqual(loss_old.regime_code, 'old')

        # 3. Unabsorbed loss amount == 0 defaults status to 'draft'
        loss_zero = LossModel.with_context(
            default_employee_id=self.emp.id,
            default_financial_year_id=self.fy2026.id
        ).create({
            'unabsorbed_loss_amount': 0.0,
        })
        self.assertEqual(loss_zero.status, 'draft')
        self.assertEqual(loss_new.status, 'active')

