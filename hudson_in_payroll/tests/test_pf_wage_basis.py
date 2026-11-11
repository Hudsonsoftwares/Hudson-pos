# -*- coding: utf-8 -*-
from odoo.tests import common# pyrefly: ignore [missing-import]


class TestPfWageBasis(common.TransactionCase):

    def setUp(self):
        super(TestPfWageBasis, self).setUp()
        self.SalaryRule = self.env['hr.salary.rule']
        self.Payslip = self.env['hr.payslip']
        self.PayslipLine = self.env['hr.payslip.line']
        self.Employee = self.env['hr.employee']
        self.Category = self.env['hr.salary.rule.category']

    def test_01_salary_rule_pf_wage_initial_flags(self):
        """Test initial configuration flags on standard salary rules."""
        basic_rule = self.env.ref('hudson_payroll_base.hr_rule_basic', raise_if_not_found=False)
        if basic_rule:
            self.assertTrue(basic_rule.hds_in_include_in_pf_wage, "Basic Salary rule must be included in PF Wage by default.")

        da_rule = self.env.ref('hudson_in_payroll.hr_rule_da_india', raise_if_not_found=False)
        if da_rule:
            self.assertTrue(da_rule.hds_in_include_in_pf_wage, "Dearness Allowance rule must be included in PF Wage by default.")

        hra_rule = self.env.ref('hudson_in_payroll.hr_rule_hra_india', raise_if_not_found=False)
        if hra_rule:
            self.assertFalse(hra_rule.hds_in_include_in_pf_wage, "House Rent Allowance rule must NOT be included in PF Wage by default.")

    def test_02_configuration_driven_pf_wage_calculation(self):
        """Test that hds_in_get_actual_pf_wage dynamically calculates PF wage based on configuration flags."""
        category_alw = self.Category.search([], limit=1)
        struct_base = self.env.ref('hudson_payroll_base.structure_base')
        
        # Create 3 custom salary rules
        rule_basic = self.SalaryRule.create({
            'name': 'Test Basic',
            'code': 'TEST_BASIC',
            'category_id': category_alw.id,
            'struct_id': struct_base.id,
            'hds_in_include_in_pf_wage': True,
        })
        rule_da = self.SalaryRule.create({
            'name': 'Test DA',
            'code': 'TEST_DA',
            'category_id': category_alw.id,
            'struct_id': struct_base.id,
            'hds_in_include_in_pf_wage': True,
        })
        rule_hra = self.SalaryRule.create({
            'name': 'Test HRA',
            'code': 'TEST_HRA',
            'category_id': category_alw.id,
            'struct_id': struct_base.id,
            'hds_in_include_in_pf_wage': False,
        })

        employee = self.Employee.create({'name': 'PF Basis Test Employee'})
        contract = employee.version_id
        contract.write({
            'wage': 25000.0,
            'basic_salary': 20000.0,
            'struct_id': struct_base.id,
        })
        payslip = self.Payslip.create({
            'name': 'Test Payslip',
            'employee_id': employee.id,
            'contract_id': contract.id,
        })

        # Add lines to payslip
        self.PayslipLine.create({
            'slip_id': payslip.id,
            'employee_id': employee.id,
            'contract_id': contract.id,
            'salary_rule_id': rule_basic.id,
            'name': 'Test Basic',
            'code': 'TEST_BASIC',
            'category_id': category_alw.id,
            'amount': 20000.0,
            'quantity': 1.0,
            'rate': 100.0,
        })
        self.PayslipLine.create({
            'slip_id': payslip.id,
            'employee_id': employee.id,
            'contract_id': contract.id,
            'salary_rule_id': rule_da.id,
            'name': 'Test DA',
            'code': 'TEST_DA',
            'category_id': category_alw.id,
            'amount': 5000.0,
            'quantity': 1.0,
            'rate': 100.0,
        })
        self.PayslipLine.create({
            'slip_id': payslip.id,
            'employee_id': employee.id,
            'contract_id': contract.id,
            'salary_rule_id': rule_hra.id,
            'name': 'Test HRA',
            'code': 'TEST_HRA',
            'category_id': category_alw.id,
            'amount': 10000.0,
            'quantity': 1.0,
            'rate': 100.0,
        })

        # Calculation should sum only rules with hds_in_include_in_pf_wage=True (20,000 + 5,000 = 25,000)
        pf_wage = payslip.hds_in_get_actual_pf_wage()
        self.assertEqual(pf_wage, 25000.0, "PF eligible wage must equal 25000 (BASIC + DA).")

        # Dynamically toggle HRA to be included in PF Wage
        rule_hra.write({'hds_in_include_in_pf_wage': True})
        pf_wage_updated = payslip.hds_in_get_actual_pf_wage()
        self.assertEqual(pf_wage_updated, 35000.0, "PF eligible wage must update to 35000 after enabling HRA in configuration.")

    def test_03_in_flight_localdict_actual_pf_wage(self):
        """Test hds_in_get_actual_pf_wage during in-flight compute_sheet execution via localdict."""
        category_alw = self.Category.search([], limit=1)
        struct_base = self.env.ref('hudson_payroll_base.structure_base')
        rule_basic = self.SalaryRule.create({
            'name': 'InFlight Basic',
            'code': 'INFLIGHT_BASIC',
            'category_id': category_alw.id,
            'struct_id': struct_base.id,
            'hds_in_include_in_pf_wage': True,
        })
        rule_hra = self.SalaryRule.create({
            'name': 'InFlight HRA',
            'code': 'INFLIGHT_HRA',
            'category_id': category_alw.id,
            'struct_id': struct_base.id,
            'hds_in_include_in_pf_wage': False,
        })

        employee = self.Employee.create({'name': 'InFlight Test Employee'})
        payslip = self.Payslip.create({'name': 'InFlight Payslip', 'employee_id': employee.id})

        simulated_localdict = {
            'INFLIGHT_BASIC': 18000.0,
            'INFLIGHT_HRA': 7000.0,
        }
        pf_wage_inflight = payslip.hds_in_get_actual_pf_wage(localdict=simulated_localdict)
        self.assertEqual(pf_wage_inflight, 18000.0, "In-flight PF wage should sum 18000 (only INFLIGHT_BASIC).")

    def test_04_pf_wage_salary_rule_sequence_and_execution_order(self):
        """Test PF_WAGE salary rule sequence (20), execution order relative to BASIC/DA, and validation scenario."""
        pf_wage_rule = self.env.ref('hudson_in_payroll.hds_in_rule_pf_wage', raise_if_not_found=False)
        if not pf_wage_rule:
            pf_wage_rule = self.SalaryRule.search([('code', '=', 'PF_WAGE')], limit=1)

        basic_rule = self.env.ref('hudson_payroll_base.hr_rule_basic', raise_if_not_found=False)
        hra_rule = self.env.ref('hudson_in_payroll.hr_rule_hra_india', raise_if_not_found=False)
        da_rule = self.env.ref('hudson_in_payroll.hr_rule_da_india', raise_if_not_found=False)
        epf_rule = self.env.ref('hudson_in_payroll.hds_in_rule_epf', raise_if_not_found=False)

        # 1. Verify sequences
        self.assertEqual(pf_wage_rule.sequence, 20, "PF_WAGE salary rule sequence must be 20.")
        if basic_rule:
            self.assertLess(basic_rule.sequence, pf_wage_rule.sequence, "BASIC must execute before PF_WAGE.")
        if da_rule:
            self.assertLess(da_rule.sequence, pf_wage_rule.sequence, "DA must execute before PF_WAGE.")
        if epf_rule:
            self.assertGreater(epf_rule.sequence, pf_wage_rule.sequence, "Downstream EPF deduction must execute after PF_WAGE.")

        # 2. Validation scenario: BASIC = 8000, DA = 800, HRA = 3200 (excluded)
        employee = self.Employee.create({
            'name': 'PF Validation Employee',
            'hds_in_epf_applicable': True,
            'hds_in_pf_contribution_basis': 'statutory_ceiling',
        })
        contract = employee.version_id
        struct_base = self.env.ref('hudson_payroll_base.structure_base')
        contract.write({
            'wage': 12000.0,
            'basic_salary': 8000.0,
            'hra': 3200.0,
            'da': 800.0,
            'struct_id': struct_base.id,
        })

        payslip = self.Payslip.create({
            'name': 'PF Sequence Validation Payslip',
            'employee_id': employee.id,
            'contract_id': contract.id,
            'struct_id': struct_base.id,
            'date_from': '2026-09-01',
            'date_to': '2026-09-30',
        })
        payslip.compute_sheet()

        line_map = {line.code: line.total for line in payslip.line_ids}
        self.assertEqual(line_map.get('BASIC'), 8000.0, "BASIC should be 8000.0")
        self.assertEqual(line_map.get('DA'), 800.0, "DA should be 800.0")
        self.assertEqual(line_map.get('HRA'), 3200.0, "HRA should be 3200.0")
        self.assertEqual(line_map.get('PF_WAGE'), 8800.0, "PF_WAGE must equal BASIC (8000) + DA (800) = 8800.0 and exclude HRA.")
        self.assertEqual(line_map.get('EPF'), -1056.0, "EPF deduction must be 12% of 8800 = -1056.0")

    def test_05_actual_pf_wage_uncapped_and_structure_isolation(self):
        """Test that Actual PF Wage is uncapped (distinguished from Contribution Wage) and isolated by structure."""
        struct_base = self.env.ref('hudson_payroll_base.structure_base')
        struct_bonus = self.env.ref('hudson_in_payroll.structure_bonus_payroll', raise_if_not_found=False)

        # 1. Uncapped Actual PF Wage (> 25k)
        employee_high = self.Employee.create({
            'name': 'High Wage Employee',
            'hds_in_epf_applicable': True,
            'hds_in_pf_contribution_basis': 'statutory_ceiling',
        })
        contract_high = employee_high.version_id
        contract_high.write({
            'wage': 35000.0,
            'basic_salary': 28000.0,
            'hra': 5000.0,
            'da': 2000.0,
            'struct_id': struct_base.id,
        })
        payslip_high = self.Payslip.create({
            'name': 'High Wage Payslip',
            'employee_id': employee_high.id,
            'contract_id': contract_high.id,
            'struct_id': struct_base.id,
            'date_from': '2026-09-01',
            'date_to': '2026-09-30',
        })
        payslip_high.compute_sheet()

        line_map_high = {line.code: line.total for line in payslip_high.line_ids}
        # Actual PF Wage must NOT be capped at 25,000 -> 28000 + 2000 = 30000.0
        self.assertEqual(line_map_high.get('PF_WAGE'), 30000.0, "Actual PF Wage must be uncapped (28000 + 2000 = 30000.0).")
        # EPF deduction must be capped at 25,000 ceiling -> 12% of 25000 = -3000.0
        self.assertEqual(line_map_high.get('EPF'), -3000.0, "EPF deduction must be capped at 25000 statutory ceiling.")

        # 2. Structure Isolation: rule in another structure must not be summed into struct_base payslip
        if struct_bonus:
            foreign_rule = self.SalaryRule.create({
                'name': 'Foreign Bonus Allowance',
                'code': 'FOREIGN_ALW',
                'category_id': self.Category.search([], limit=1).id,
                'struct_id': struct_bonus.id,
                'hds_in_include_in_pf_wage': True,
            })
            simulated_localdict = {
                'BASIC': 8000.0,
                'DA': 800.0,
                'FOREIGN_ALW': 5000.0,
            }
            # Payslip belongs to struct_base, so FOREIGN_ALW belonging to struct_bonus must NOT be included
            pf_wage_isolated = payslip_high.hds_in_get_actual_pf_wage(localdict=simulated_localdict)
            self.assertEqual(pf_wage_isolated, 8800.0, "Foreign structure rules must not leak into current structure PF wage.")
