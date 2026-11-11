# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo import fields


class TestTdsPhase4AnnualIncomeProjection(TransactionCase):

    def setUp(self):
        super(TestTdsPhase4AnnualIncomeProjection, self).setUp()
        self.fy = self.env['tds.financial.year'].search([('code', '=', '2025-2026')], limit=1)
        if not self.fy:
            self.fy = self.env['tds.financial.year'].create({
                'name': 'Financial Year 2025-2026',
                'code': '2025-2026',
                'start_date': '2025-04-01',
                'end_date': '2026-03-31',
                'active': True,
            })

        self.regime_old = self.env['tds.tax.regime'].search([('code', '=', 'old')], limit=1)
        if not self.regime_old:
            self.regime_old = self.env['tds.tax.regime'].create({
                'name': 'Old Tax Regime',
                'code': 'old',
                'description': 'Traditional Old Tax Regime with Deductions',
                'is_active': True,
            })

        self.regime_new = self.env['tds.tax.regime'].search([('code', '=', 'new')], limit=1)
        if not self.regime_new:
            self.regime_new = self.env['tds.tax.regime'].create({
                'name': 'New Tax Regime (Section 115BAC)',
                'code': 'new',
                'description': 'Concessional New Tax Regime',
                'is_active': True,
            })

        self.employee = self.env['hr.employee'].create({
            'name': 'Phase 4 Projection Test Employee',
            'birthday': '1990-05-15',
        })

    def test_01_salary_projection_service(self):
        """Test SalaryProjectionService annualizing earnings across FY."""
        from hudson_in_payroll.services.tds.salary_projection_service import SalaryProjectionService
        salary_svc = SalaryProjectionService(self.env)

        # Set contract wage ₹60,000
        contract = self.env['hr.contract'].create({
            'name': 'Test Contract Phase 4',
            'employee_id': self.employee.id,
            'wage': 60000.0,
            'state': 'open',
            'date_start': '2025-04-01',
        })
        self.employee.contract_id = contract.id

        # Evaluate on April 15, 2025 (1 month elapsed, 11 months remaining)
        eval_date = fields.Date.from_string('2025-04-15')
        res = salary_svc.project_salary(self.employee, self.fy, eval_date=eval_date)

        self.assertEqual(res.months_elapsed, 1)
        self.assertEqual(res.months_remaining, 11)
        # Total projected basic = 12 * 60,000 = 7,20,000
        self.assertEqual(res.total_projected_current_salary, 720000.0)

    def test_02_previous_employer_and_other_income_aggregation(self):
        """Test PreviousEmployerIncomeService and OtherIncomeAggregationService."""
        from odoo.addons.hudson_in_payroll.services.tds.previous_employer_income_service import PreviousEmployerIncomeService
        from odoo.addons.hudson_in_payroll.services.tds.other_income_aggregation_service import OtherIncomeAggregationService

        # Create Income Declaration
        inc_decl = self.env['tds.employee.income.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'prev_employer_taxable_gross': 250000.0,
            'prev_employer_tds': 15000.0,
            'prev_employer_pt': 2400.0,
            'savings_bank_interest': 12000.0,
            'fixed_deposit_interest': 28000.0,
            'annual_let_out_rent': 120000.0,
            'municipal_taxes_paid': 20000.0,
            'let_out_interest_paid': 50000.0,
            'state': 'submitted',
        })

        # Test Previous Employer Aggregation
        prev_svc = PreviousEmployerIncomeService(self.env)
        prev_res = prev_svc.aggregate_previous_employer_income(self.employee, self.fy)
        self.assertTrue(prev_res.has_declaration)
        self.assertEqual(prev_res.taxable_salary, 250000.0)
        self.assertEqual(prev_res.tds_deducted, 15000.0)
        self.assertEqual(prev_res.pt_deducted, 2400.0)

        # Test Other Income Aggregation
        # Other Sources = 12,000 + 28,000 = 40,000
        # Let-Out Property = NAV (1.2L - 20k = 1L) - 30% NAV (30k) - Loan Int (50k) = 20,000
        # Total Other Income = 40,000 + 20,000 = 60,000
        other_svc = OtherIncomeAggregationService(self.env)
        other_res = other_svc.aggregate_other_income(self.employee, self.fy)
        self.assertTrue(other_res.has_declaration)
        self.assertEqual(other_res.total_other_sources, 40000.0)
        self.assertEqual(other_res.nav, 100000.0)
        self.assertEqual(other_res.property_std_deduction, 30000.0)
        self.assertEqual(other_res.net_house_property_income_loss, 20000.0)
        self.assertEqual(other_res.total_other_income, 60000.0)

    def test_03_annual_income_projection_master_orchestration(self):
        """Test AnnualIncomeProjectionService master orchestration and regime routing."""
        from odoo.addons.hudson_in_payroll.services.tds.annual_income_projection_service import AnnualIncomeProjectionService

        # Select Old Regime for employee
        self.env['tds.employee.tax.regime'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_old.id,
        })

        # Set contract wage ₹50,000 (₹6,00,000 annual)
        contract = self.env['hr.contract'].create({
            'name': 'Contract Orchestration Test',
            'employee_id': self.employee.id,
            'wage': 50000.0,
            'state': 'open',
            'date_start': '2025-04-01',
        })
        self.employee.contract_id = contract.id

        inc_svc = AnnualIncomeProjectionService(self.env)
        eval_date = fields.Date.from_string('2025-04-15')
        res = inc_svc.project_annual_income(self.employee, eval_date=eval_date)

        self.assertEqual(res.regime_code, 'old')
        self.assertEqual(res.projected_annual_salary, 600000.0)
        self.assertEqual(res.gross_total_income, 600000.0)
        self.assertEqual(res.regime_context.standard_deduction_limit, 50000.0)
        self.assertIn('80c', res.regime_context.permitted_categories)

    def test_04_full_tds_orchestration_engine_pipeline(self):
        """Test full end-to-end statutory TDS calculation pipeline via TdsOrchestrationEngine."""
        from odoo.addons.hudson_in_payroll.services.tds.tds_orchestration_engine import TdsOrchestrationEngine

        # Setup Contract: Basic wage ₹1,00,000 / month (₹12,00,000 p.a.)
        contract = self.env['hr.contract'].create({
            'name': 'Full TDS Engine Test Contract',
            'employee_id': self.employee.id,
            'wage': 100000.0,
            'state': 'open',
            'date_start': '2025-04-01',
        })
        self.employee.contract_id = contract.id

        # Select New Tax Regime (Section 115BAC)
        self.env['tds.employee.tax.regime'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_new.id,
        })

        engine = TdsOrchestrationEngine(self.env)
        eval_date = fields.Date.from_string('2025-04-15')
        result = engine.hds_in_compute_tds(self.employee, eval_date=eval_date)

        # 1. Gross Total Income = ₹12,00,000
        self.assertEqual(result.annual_income_projection.gross_total_income, 1200000.0)

        # 2. Approved Deductions (New Regime Std Deduction ₹75,000)
        self.assertEqual(result.deduction_calculation.total_approved_deductions, 75000.0)

        # 3. Net Taxable Income = ₹12,00,000 - ₹75,000 = ₹11,25,000
        self.assertEqual(result.taxable_income.net_taxable_income, 1125000.0)

        # 4. Tax Slabs (New Regime FY 2025-26 Slabs):
        # 0 to 4L: 0% = 0
        # 4L to 8L (4L@5%): 20,000
        # 8L to 11.25L (3.25L@10%): 32,500
        # Base Tax = 20,000 + 32,500 = ₹52,500
        self.assertEqual(result.income_tax_slab.base_tax_liability, 52500.0)

        # 5. Section 87A Rebate: Ineligible because Taxable Income (11.25L) > 7.0L
        self.assertEqual(result.rebate_engine.rebate_applied, 0.0)

        # 6. Surcharge: 0% because Taxable Income < 50L
        self.assertEqual(result.surcharge_engine.surcharge_amount, 0.0)

        # 7. Cess: 4% of ₹52,500 = ₹2,100. Total Annual Tax Liability = ₹54,600
        self.assertEqual(result.health_education_cess.cess_amount, 2100.0)
        self.assertEqual(result.health_education_cess.total_annual_tax_liability, 54600.0)

        # 8. Monthly TDS Withholding (Remaining 12 periods in April): ₹54,600 / 12 = ₹4,550
        self.assertEqual(result.monthly_tds_distribution.remaining_payroll_periods, 12)
        self.assertEqual(result.current_month_tds, 4550.0)

    def test_05_payroll_income_projection_service_standalone(self):
        """Test PayrollIncomeProjectionService standalone projection."""
        from odoo.addons.hudson_in_payroll.services.tds.payroll_income_projection_service import PayrollIncomeProjectionService
        payroll_svc = PayrollIncomeProjectionService(self.env)

        contract = self.env['hr.contract'].create({
            'name': 'Standalone Payroll Projection Contract',
            'employee_id': self.employee.id,
            'wage': 75000.0,
            'state': 'open',
            'date_start': '2025-04-01',
        })
        self.employee.contract_id = contract.id

        eval_date = fields.Date.from_string('2025-04-15')
        proj_res = payroll_svc.project_payroll_income(self.employee, self.fy, eval_date=eval_date)

        self.assertEqual(proj_res.months_remaining, 11)
        self.assertEqual(proj_res.total_projected_payroll, 900000.0)

    def test_06_missing_employee_or_fy_validation(self):
        """Test validation errors for missing employee or financial year."""
        from odoo.addons.hudson_in_payroll.services.tds.annual_income_projection_service import AnnualIncomeProjectionService
        inc_svc = AnnualIncomeProjectionService(self.env)

        with self.assertRaises(ValidationError):
            inc_svc.project_annual_income(False)

    def test_07_regression_annual_projection_remains_constant_across_months(self):
        """
        Regression Test: Verify that when monthly gross salary is ₹150,000,
        the annual salary projection remains exactly ₹18,00,000 for April, May, June, and July,
        even as prior month payslips transition to 'done' state with BASIC and GROSS rule lines.
        """
        from odoo.addons.hudson_in_payroll.services.tds.salary_projection_service import SalaryProjectionService
        salary_svc = SalaryProjectionService(self.env)

        emp = self.env['hr.employee'].create({
            'name': 'Regression Projection Employee',
            'birthday': '1992-08-20',
        })
        contract = self.env['hr.version'].create({
            'name': 'Contract Regression Test',
            'employee_id': emp.id,
            'wage': 150000.0,
            'state': 'open',
            'date_start': '2025-04-01',
        })
        emp.contract_id = contract.id

        # April evaluation (0 paid payslips in DB)
        res_april = salary_svc.project_salary(emp, self.fy, eval_date='2025-04-30')
        self.assertEqual(res_april.total_projected_current_salary, 1800000.0)

        # Create paid April payslip in DB with BASIC and GROSS lines
        rule_basic = self.env.ref('hudson_payroll_base.hr_rule_basic')
        rule_gross = self.env['hr.salary.rule'].search([('code', '=', 'GROSS')], limit=1)

        april_slip = self.env['hr.payslip'].create({
            'name': 'April 2025 Payslip',
            'employee_id': emp.id,
            'contract_id': contract.id,
            'date_from': '2025-04-01',
            'date_to': '2025-04-30',
            'state': 'done',
        })
        self.env['hr.payslip.line'].create({
            'slip_id': april_slip.id,
            'salary_rule_id': rule_basic.id,
            'employee_id': emp.id,
            'contract_id': contract.id,
            'code': 'BASIC',
            'name': 'Basic Salary',
            'amount': 150000.0,
            'quantity': 1.0,
            'rate': 100.0,
        })
        if rule_gross:
            self.env['hr.payslip.line'].create({
                'slip_id': april_slip.id,
                'salary_rule_id': rule_gross.id,
                'employee_id': emp.id,
                'contract_id': contract.id,
                'code': 'GROSS',
                'name': 'Gross Salary',
                'amount': 150000.0,
                'quantity': 1.0,
                'rate': 100.0,
            })

        # May evaluation (1 paid payslip in DB)
        res_may = salary_svc.project_salary(emp, self.fy, eval_date='2025-05-31')
        self.assertEqual(res_may.total_projected_current_salary, 1800000.0)

        # Create paid May payslip in DB
        may_slip = self.env['hr.payslip'].create({
            'name': 'May 2025 Payslip',
            'employee_id': emp.id,
            'contract_id': contract.id,
            'date_from': '2025-05-01',
            'date_to': '2025-05-31',
            'state': 'done',
        })
        self.env['hr.payslip.line'].create({
            'slip_id': may_slip.id,
            'salary_rule_id': rule_basic.id,
            'employee_id': emp.id,
            'contract_id': contract.id,
            'code': 'BASIC',
            'name': 'Basic Salary',
            'amount': 150000.0,
            'quantity': 1.0,
            'rate': 100.0,
        })

        # June evaluation (2 paid payslips in DB)
        res_june = salary_svc.project_salary(emp, self.fy, eval_date='2025-06-30')
        self.assertEqual(res_june.total_projected_current_salary, 1800000.0)

        # July evaluation (2 paid payslips in DB)
        res_july = salary_svc.project_salary(emp, self.fy, eval_date='2025-07-31')
        self.assertEqual(res_july.total_projected_current_salary, 1800000.0)


