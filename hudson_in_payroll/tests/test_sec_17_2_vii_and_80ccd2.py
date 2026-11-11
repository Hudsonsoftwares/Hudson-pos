# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase
# pyrefly: ignore [missing-import]
from odoo import fields
from ..services.tds.tds_parameter_service import TdsParameterService
from ..services.tds.annual_income_projection_service import AnnualIncomeProjectionService
from ..services.tds.deduction_calculation_service import DeductionCalculationService
from ..services.tds.regime_routing_service import RegimeRoutingService


class TestSec172viiAnd80ccd2(TransactionCase):
    """
    Automated Test Suite for Section 17(2)(vii) Employer Contribution Perquisite
    and Section 80CCD(2) Employer NPS Percentage Cap.
    """

    def setUp(self):
        super().setUp()
        self.param_svc = TdsParameterService(self.env)
        self.annual_svc = AnnualIncomeProjectionService(self.env)
        self.deduct_svc = DeductionCalculationService(self.env)
        self.routing_svc = RegimeRoutingService(self.env)

        # 1. Ensure FY 2025-26 exists
        self.fy = self.env['tds.financial.year'].search([('code', '=', '2025-2026')], limit=1)
        if not self.fy:
            self.fy = self.env['tds.financial.year'].create({
                'name': 'FY 2025-26',
                'code': '2025-2026',
                'assessment_year': '2026-2027',
                'start_date': '2025-04-01',
                'end_date': '2026-03-31',
            })

        self.regime_new = self.env['tds.tax.regime'].search([('code', '=', 'new')], limit=1)
        self.regime_old = self.env['tds.tax.regime'].search([('code', '=', 'old')], limit=1)

        # 2. Base employee with unique PAN
        import random
        r_num = random.randint(1000, 9999)
        self.employee = self.env['hr.employee'].create({
            'name': f'Senior Tech Exec {r_num}',
            'hds_in_pan': f'ZZZTE{r_num}Z',
            'hds_in_epf_applicable': True,
        })

        # Set tax regime to New Regime
        self.env['tds.employee.tax.regime'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'regime_id': self.regime_new.id,
        })

        # Ensure Rules exist
        cat_basic = self.env['hr.salary.rule.category'].search([('code', '=', 'BASIC')], limit=1)
        cat_alw = self.env['hr.salary.rule.category'].search([('code', '=', 'ALW')], limit=1)
        cat_comp = self.env['hr.salary.rule.category'].search([('code', '=', 'COMP')], limit=1)

        self.rule_basic = self.env['hr.salary.rule'].search([('code', '=', 'BASIC')], limit=1)
        if not self.rule_basic:
            self.rule_basic = self.env['hr.salary.rule'].create({
                'name': 'Basic Salary',
                'code': 'BASIC',
                'category_id': cat_basic.id if cat_basic else False,
                'sequence': 1,
            })

        self.rule_da = self.env['hr.salary.rule'].search([('code', '=', 'DA')], limit=1)
        if not self.rule_da:
            self.rule_da = self.env['hr.salary.rule'].create({
                'name': 'Dearness Allowance',
                'code': 'DA',
                'category_id': cat_alw.id if cat_alw else False,
                'sequence': 2,
            })

        self.rule_epf = self.env['hr.salary.rule'].search([('code', 'in', ('EMPLOYER_EPF', 'EPF_ER'))], limit=1)
        if not self.rule_epf:
            self.rule_epf = self.env['hr.salary.rule'].create({
                'name': 'Employer EPF',
                'code': 'EMPLOYER_EPF',
                'category_id': cat_comp.id if cat_comp else False,
                'sequence': 100,
            })

    def _create_contract(self, employee, vals):
        contract_model = 'hr.version' if 'hr.version' in self.env else 'hr.contract'
        Model = self.env[contract_model]

        existing = False
        if hasattr(employee, 'version_id') and employee.version_id:
            existing = employee.version_id
        elif hasattr(employee, 'contract_id') and employee.contract_id:
            existing = employee.contract_id
        else:
            existing = Model.search([('employee_id', '=', employee.id)], limit=1)

        c_vals = {
            'wage': vals.get('wage', 50000.0),
        }
        if 'name' in vals and 'name' in Model._fields:
            c_vals['name'] = vals['name']
        if 'state' in Model._fields:
            c_vals['state'] = 'open'
        elif 'status' in Model._fields:
            c_vals['status'] = 'open'
        if 'basic_salary' in vals and 'basic_salary' in Model._fields:
            c_vals['basic_salary'] = vals['basic_salary']
        if 'da' in vals and 'da' in Model._fields:
            c_vals['da'] = vals['da']
        if 'date_start' in vals and 'date_start' in Model._fields:
            c_vals['date_start'] = vals['date_start']

        if existing:
            existing.write(c_vals)
            return existing
        else:
            c_vals['employee_id'] = employee.id
            if 'date_version' in Model._fields:
                c_vals['date_version'] = vals.get('date_start', '2025-04-01')
            contract = Model.create(c_vals)
            return contract

    def test_01_nps_employer_contribution_percentage_parameter(self):
        """Test parameter resolution for NPS_EMPLOYER_CONTRIBUTION_PERCENTAGE."""
        eval_date = fields.Date.from_string('2025-05-01')

        # New Regime should resolve to 14%
        new_limit = self.param_svc.get_parameter('NPS_EMPLOYER_CONTRIBUTION_PERCENTAGE', eval_date=eval_date, regime='new')
        self.assertEqual(new_limit, 14.0)

        # Decimal format should be 0.14
        new_dec = self.param_svc.get_employer_nps_limit(regime='new', eval_date=eval_date, as_decimal=True)
        self.assertAlmostEqual(new_dec, 0.14, places=2)

        # Old Regime Private should resolve to 10%
        old_private = self.param_svc.get_employer_nps_limit(regime='old', employer_type='private', eval_date=eval_date)
        self.assertEqual(old_private, 10.0)

        # Old Regime Govt should resolve to 14%
        old_govt = self.param_svc.get_employer_nps_limit(regime='old', employer_type='govt_central', eval_date=eval_date)
        self.assertEqual(old_govt, 14.0)

        # Aggregate ceiling should resolve to 7,50,000
        agg_ceiling = self.param_svc.get_combined_employer_contribution_limit(eval_date=eval_date)
        self.assertEqual(agg_ceiling, 750000.0)

    def test_02_section_80ccd2_percentage_cap_calculation(self):
        """
        Test Section 80CCD(2) employer NPS deduction cap:
        Basic = ₹50,000/mo, DA = ₹10,000/mo → Annual Basic + DA = ₹7,20,000.
        At 14%: ₹7,20,000 × 14% = ₹1,00,800.
        Declared NPS: ₹1,20,000.
        Eligible deduction must be capped at ₹1,00,800 (excess ₹19,200 disallowed).
        """
        contract = self._create_contract(self.employee, {
            'name': 'Senior Exec Contract',
            'wage': 100000.0,
            'basic_salary': 50000.0,
            'da': 10000.0,
            'date_start': '2025-04-01',
        })

        # Create declaration with ₹1,20,000 employer NPS
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'tax_regime_id': self.regime_new.id,
            'decl_80ccd2_employer_nps': 120000.0,
            'declaration_line_ids': [
                (0, 0, {
                    'category': '80ccd2',
                    'description': 'Employer NPS Contribution',
                    'declared_amount': 120000.0,
                })
            ]
        })

        eval_date = fields.Date.from_string('2025-05-01')
        reg_ctx = self.routing_svc.prepare_regime_context(
            employee=self.employee,
            financial_year=self.fy,
            regime_code='new',
            gross_total_income=1200000.0,
            eval_date=eval_date,
            gross_salary_income=1200000.0
        )
        deduct_res = self.deduct_svc.calculate_deductions(
            employee=self.employee,
            financial_year=self.fy,
            regime_context=reg_ctx,
            eval_date=eval_date,
            gross_salary_income=1200000.0
        )

        # Eligible deduction should be strictly ₹1,00,800
        self.assertEqual(deduct_res.employer_nps_80ccd2, 100800.0)

    def test_03_section_17_2_vii_under_ceiling_no_perquisite(self):
        """
        Normal employee scenario:
        Employer EPF = ₹1,800/month (Annual = ₹21,600).
        Declared NPS = ₹0.
        Combined = ₹21,600 < ₹7,50,000 ceiling → Perquisite = ₹0.00.
        """
        contract = self._create_contract(self.employee, {
            'name': 'Standard Contract',
            'wage': 50000.0,
            'basic_salary': 25000.0,
            'date_start': '2025-04-01',
        })

        eval_date = fields.Date.from_string('2025-05-01')
        proj_res = self.annual_svc.project_annual_income(self.employee, eval_date=eval_date)

        self.assertEqual(proj_res.sec_17_2_vii_perquisite, 0.0)

    def test_04_section_17_2_vii_above_ceiling_taxable_perquisite(self):
        """
        High contribution scenario:
        Company contributes ₹6,00,000 to EPF and ₹5,00,000 to NPS (Total ₹11,00,000).
        Excess ₹3,50,000 (₹11,00,000 - ₹7,50,000) must be taxed as perquisite under Section 17(2)(vii).
        """
        contract = self._create_contract(self.employee, {
            'name': 'High Earner Contract',
            'wage': 500000.0,
            'basic_salary': 250000.0,
            'date_start': '2025-04-01',
        })

        # Create paid payslip with ₹50,000/month Employer EPF line (50,000 * 12 = 6,00,000)
        payslip = self.env['hr.payslip'].create({
            'name': 'April 2025 Payslip',
            'employee_id': self.employee.id,
            'contract_id': contract.id,
            'date_from': '2025-04-01',
            'date_to': '2025-04-30',
            'state': 'done',
            'line_ids': [
                (0, 0, {
                    'name': 'Employer EPF',
                    'code': 'EMPLOYER_EPF',
                    'salary_rule_id': self.rule_epf.id,
                    'employee_id': self.employee.id,
                    'contract_id': contract.id,
                    'amount': 50000.0,
                    'quantity': 1.0,
                    'rate': 100.0,
                    'total': 50000.0,
                })
            ]
        })
        payslip.write({'hds_in_employer_epf': 50000.0})

        # Declaration with ₹5,00,000 Employer NPS
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'tax_regime_id': self.regime_new.id,
            'decl_80ccd2_employer_nps': 500000.0,
        })

        eval_date = fields.Date.from_string('2025-04-30')
        proj_res = self.annual_svc.project_annual_income(self.employee, eval_date=eval_date)

        # EPF annual: ₹50,000 paid + ₹50,000 * 11 remaining = ₹6,00,000
        # NPS actual: ₹5,00,000
        # Combined: ₹11,00,000
        # Ceiling: ₹7,50,000
        # Perquisite: ₹3,50,000
        self.assertEqual(proj_res.sec_17_2_vii_perquisite, 350000.0)

    def test_05_decoupled_interaction_both_calculations(self):
        """
        Verify both calculations simultaneously on the user's specific scenario:
        - Basic = ₹50,000/mo, DA = ₹10,000/mo → Annual Basic + DA = ₹7,20,000
        - Declared Employer NPS = ₹1,20,000
        - Actual Employer EPF = ₹6,80,000 (via payslip EPF of ₹56,666.67/mo × 12)

        Calculation 1 (80CCD(2)):
        Cap = ₹7,20,000 × 14% = ₹1,00,800.
        Eligible deduction = ₹1,00,800.

        Calculation 2 (17(2)(vii)):
        Total employer contributions = ₹6,80,000 + ₹1,20,000 = ₹8,00,000.
        Ceiling = ₹7,50,000.
        Perquisite = ₹50,000 added to GTI.
        """
        contract = self._create_contract(self.employee, {
            'name': 'Dual Calc Contract',
            'wage': 80000.0,
            'basic_salary': 50000.0,
            'da': 10000.0,
            'date_start': '2025-04-01',
        })

        # Payslip with employer EPF yielding ₹6,80,000 annually
        # 1 paid month = ₹56,666.67, 11 remaining = ₹6,23,333.33 => total = ₹6,80,000.00
        payslip = self.env['hr.payslip'].create({
            'name': 'April 2025 Dual Calc',
            'employee_id': self.employee.id,
            'contract_id': contract.id,
            'date_from': '2025-04-01',
            'date_to': '2025-04-30',
            'state': 'done',
            'line_ids': [
                (0, 0, {
                    'name': 'Basic Salary',
                    'code': 'BASIC',
                    'salary_rule_id': self.rule_basic.id,
                    'employee_id': self.employee.id,
                    'contract_id': contract.id,
                    'amount': 50000.0,
                    'quantity': 1.0,
                    'rate': 100.0,
                    'total': 50000.0,
                }),
                (0, 0, {
                    'name': 'Dearness Allowance',
                    'code': 'DA',
                    'salary_rule_id': self.rule_da.id,
                    'employee_id': self.employee.id,
                    'contract_id': contract.id,
                    'amount': 10000.0,
                    'quantity': 1.0,
                    'rate': 100.0,
                    'total': 10000.0,
                }),
                (0, 0, {
                    'name': 'Employer EPF',
                    'code': 'EMPLOYER_EPF',
                    'salary_rule_id': self.rule_epf.id,
                    'employee_id': self.employee.id,
                    'contract_id': contract.id,
                    'amount': 56666.67,
                    'quantity': 1.0,
                    'rate': 100.0,
                    'total': 56666.67,
                })
            ]
        })
        payslip.write({'hds_in_employer_epf': 56666.67})

        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'tax_regime_id': self.regime_new.id,
            'decl_80ccd2_employer_nps': 120000.0,
        })

        eval_date = fields.Date.from_string('2025-04-30')

        # 1. Test Income Projection & Section 17(2)(vii) Perquisite
        proj_res = self.annual_svc.project_annual_income(self.employee, eval_date=eval_date)
        # Combined = ~6,80,000 + 1,20,000 = 8,00,000. Excess = 50,000
        self.assertAlmostEqual(proj_res.sec_17_2_vii_perquisite, 50000.0, places=0)

        # 2. Test Deduction Calculation & Section 80CCD(2) Cap
        reg_ctx = self.routing_svc.prepare_regime_context(
            employee=self.employee,
            financial_year=self.fy,
            regime_code='new',
            gross_total_income=proj_res.gross_total_income,
            eval_date=eval_date,
            gross_salary_income=proj_res.projected_annual_salary
        )
        deduct_res = self.deduct_svc.calculate_deductions(
            employee=self.employee,
            financial_year=self.fy,
            regime_context=reg_ctx,
            eval_date=eval_date,
            gross_salary_income=proj_res.projected_annual_salary
        )
        # 80CCD(2) must be capped at ₹1,00,800
        self.assertEqual(deduct_res.employer_nps_80ccd2, 100800.0)

    def test_06_month_1_draft_epf_projection_and_user_scenario(self):
        """
        Verify the exact user scenario in Month 1 (April) with a draft payslip:
        - Monthly Gross = ₹3,00,000 (Basic ₹2,00,000, DA ₹50,000, Special ₹50,000)
        - Employer EPF = ₹30,000/mo (12% of Basic + DA)
        - Declared Employer NPS = ₹5,00,000
        - 0 paid payslips (paid_months_count == 0)

        Statutory Expectation:
        - 12 months EPF projection: ₹30,000 × 12 = ₹3,60,000
        - Combined Contribution: ₹3,60,000 + ₹5,00,000 = ₹8,60,000
        - Sec 17(2)(vii) Perquisite: ₹8,60,000 - ₹7,50,000 = ₹1,10,000
        - Annual Salary: ₹36,00,000 -> Gross Total Income (GTI): ₹37,10,000
        - Basic + DA Annual: ₹30,00,000 -> 80CCD(2) Cap (14%): ₹4,20,000
        - Standard Deduction: ₹75,000
        - Net Taxable Income: ₹37,10,000 - ₹4,95,000 = ₹32,15,000
        """
        contract = self._create_contract(self.employee, {
            'name': 'Senior Director Contract',
            'wage': 300000.0,
            'basic_salary': 200000.0,
            'da': 50000.0,
            'date_start': '2025-04-01',
        })

        # Draft payslip for April (not marked done)
        draft_slip = self.env['hr.payslip'].create({
            'name': 'April 2025 Draft Payslip',
            'employee_id': self.employee.id,
            'contract_id': contract.id,
            'date_from': '2025-04-01',
            'date_to': '2025-04-30',
            'state': 'draft',
            'line_ids': [
                (0, 0, {
                    'name': 'Basic Salary',
                    'code': 'BASIC',
                    'salary_rule_id': self.rule_basic.id,
                    'employee_id': self.employee.id,
                    'contract_id': contract.id,
                    'amount': 200000.0,
                    'quantity': 1.0,
                    'rate': 100.0,
                    'total': 200000.0,
                }),
                (0, 0, {
                    'name': 'Dearness Allowance',
                    'code': 'DA',
                    'salary_rule_id': self.rule_da.id,
                    'employee_id': self.employee.id,
                    'contract_id': contract.id,
                    'amount': 50000.0,
                    'quantity': 1.0,
                    'rate': 100.0,
                    'total': 50000.0,
                }),
                (0, 0, {
                    'name': 'Employer EPF',
                    'code': 'EMPLOYER_EPF',
                    'salary_rule_id': self.rule_epf.id,
                    'employee_id': self.employee.id,
                    'contract_id': contract.id,
                    'amount': 30000.0,
                    'quantity': 1.0,
                    'rate': 100.0,
                    'total': 30000.0,
                })
            ]
        })
        draft_slip.write({'hds_in_employer_epf': 30000.0})

        # Declaration with ₹5,00,000 Employer NPS
        decl = self.env['tds.employee.declaration'].create({
            'employee_id': self.employee.id,
            'financial_year_id': self.fy.id,
            'tax_regime_id': self.regime_new.id,
            'decl_80ccd2_employer_nps': 500000.0,
            'declaration_line_ids': [
                (0, 0, {
                    'category': '80ccd2',
                    'description': 'Employer NPS Contribution',
                    'declared_amount': 500000.0,
                })
            ]
        })

        eval_date = fields.Date.from_string('2025-04-15')

        # 1. Test Annual Income Projection
        proj_res = self.annual_svc.project_annual_income(
            self.employee,
            payslip=draft_slip,
            eval_date=eval_date
        )

        # EPF must project 12 full months (30,000 * 12 = 3,60,000)
        # Combined = 3,60,000 + 5,00,000 = 8,60,000 -> Perquisite = 1,10,000
        self.assertEqual(proj_res.current_employer_salary, 3600000.0)
        self.assertEqual(proj_res.sec_17_2_vii_perquisite, 110000.0)
        self.assertEqual(proj_res.projected_annual_salary, 3710000.0)
        self.assertEqual(proj_res.gross_total_income, 3710000.0)

        # 2. Test Deductions Calculation & Section 80CCD(2)
        reg_ctx = self.routing_svc.prepare_regime_context(
            employee=self.employee,
            financial_year=self.fy,
            regime_code='new',
            gross_total_income=proj_res.gross_total_income,
            eval_date=eval_date,
            gross_salary_income=proj_res.projected_annual_salary
        )
        deduct_res = self.deduct_svc.calculate_deductions(
            employee=self.employee,
            financial_year=self.fy,
            regime_context=reg_ctx,
            eval_date=eval_date,
            gross_salary_income=proj_res.projected_annual_salary
        )

        # 80CCD(2) statutory cap: 14% of (2,00,000 + 50,000) * 12 = ₹4,20,000
        self.assertEqual(deduct_res.employer_nps_80ccd2, 420000.0)
        self.assertEqual(deduct_res.standard_deduction, 75000.0)
        self.assertEqual(deduct_res.total_allowable_deductions, 495000.0)

        # Net Taxable Income
        net_taxable = proj_res.gross_total_income - deduct_res.total_allowable_deductions
        self.assertEqual(net_taxable, 3215000.0)

