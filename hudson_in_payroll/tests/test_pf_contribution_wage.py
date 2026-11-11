# -*- coding: utf-8 -*-
from odoo.tests import common# pyrefly: ignore [missing-import]
from odoo import fields# pyrefly: ignore [missing-import]


class TestPfContributionWage(common.TransactionCase):

    def setUp(self):
        super(TestPfContributionWage, self).setUp()
        self.SalaryRule = self.env['hr.salary.rule']
        self.Payslip = self.env['hr.payslip']
        self.PayslipLine = self.env['hr.payslip.line']
        self.Employee = self.env['hr.employee']
        self.Category = self.env['hr.salary.rule.category']
        self.RuleParameter = self.env['hr.rule.parameter']
        self.RuleParameterValue = self.env['hr.rule.parameter.value']

        self.category_alw = self.Category.search([], limit=1)
        self.struct_base = self.env.ref('hudson_payroll_base.structure_base')

        # Use existing BASIC salary rule or create if missing
        self.rule_basic = self.env.ref('hudson_payroll_base.hr_rule_basic', raise_if_not_found=False)
        if not self.rule_basic:
            self.rule_basic = self.SalaryRule.search([('code', '=', 'BASIC'), ('struct_id', '=', self.struct_base.id)], limit=1)
        if not self.rule_basic:
            self.rule_basic = self.SalaryRule.create({
                'name': 'Test Basic',
                'code': 'BASIC',
                'category_id': self.category_alw.id,
                'struct_id': self.struct_base.id,
                'hds_in_include_in_pf_wage': True,
            })
        self.rule_basic.write({'hds_in_include_in_pf_wage': True})

        # Ensure PF Wage Ceiling parameter exists
        self.pf_ceiling_param = self.RuleParameter.search([('code', '=', 'hds_in_pf_wage_ceiling')], limit=1)
        if not self.pf_ceiling_param:
            self.pf_ceiling_param = self.RuleParameter.create({
                'name': 'PF Wage Ceiling',
                'code': 'hds_in_pf_wage_ceiling',
                'category': 'ceiling',
            })
            self.RuleParameterValue.create({
                'parameter_id': self.pf_ceiling_param.id,
                'date_from': '2014-09-01',
                'parameter_value': '25000',
            })

    def _create_payslip_with_lines(self, employee, basic_amount, date_to='2026-04-30'):
        payslip = self.Payslip.create({
            'name': 'Test Payslip',
            'employee_id': employee.id,
            'contract_id': employee.version_id.id,
            'struct_id': self.struct_base.id,
            'date_from': '2026-04-01',
            'date_to': date_to,
        })
        if basic_amount != 0:
            self.PayslipLine.create({
                'slip_id': payslip.id,
                'employee_id': employee.id,
                'contract_id': employee.version_id.id,
                'salary_rule_id': self.rule_basic.id,
                'name': 'Test Basic',
                'code': 'BASIC',
                'category_id': self.category_alw.id,
                'amount': float(basic_amount),
                'quantity': 1.0,
                'rate': 100.0,
            })
        return payslip

    def test_scenario_a_wage_below_ceiling(self):
        """Scenario A: Wage below ceiling (Actual PF Wage = ₹8,800, Ceiling = ₹15,000, statutory_ceiling) -> ₹8,800"""
        employee = self.Employee.create({
            'name': 'Employee Scenario A',
            'hds_in_pf_contribution_basis': 'statutory_ceiling',
        })
        payslip = self._create_payslip_with_lines(employee, 8800.0)
        self.assertEqual(payslip.hds_in_get_actual_pf_wage(), 8800.0)
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 8800.0)

    def test_scenario_b_wage_above_ceiling(self):
        """Scenario B: Wage above ceiling (Actual PF Wage = ₹30,000, Ceiling = ₹25,000, statutory_ceiling) -> ₹25,000"""
        employee = self.Employee.create({
            'name': 'Employee Scenario B',
            'hds_in_pf_contribution_basis': 'statutory_ceiling',
        })
        payslip = self._create_payslip_with_lines(employee, 30000.0)
        self.assertEqual(payslip.hds_in_get_actual_pf_wage(), 30000.0)
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 25000.0)

    def test_scenario_c_uncapped_contribution(self):
        """Scenario C: Uncapped contribution (Actual PF Wage = ₹20,000, Basis = actual_pf_wage) -> ₹20,000"""
        employee = self.Employee.create({
            'name': 'Employee Scenario C',
            'hds_in_pf_contribution_basis': 'actual_pf_wage',
        })
        payslip = self._create_payslip_with_lines(employee, 20000.0)
        self.assertEqual(payslip.hds_in_get_actual_pf_wage(), 20000.0)
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 20000.0)

    def test_scenario_d_wage_at_ceiling(self):
        """Scenario D: Wage exactly at ceiling (Actual PF Wage = ₹25,000, Ceiling = ₹25,000, statutory_ceiling) -> ₹25,000"""
        employee = self.Employee.create({
            'name': 'Employee Scenario D',
            'hds_in_pf_contribution_basis': 'statutory_ceiling',
        })
        payslip = self._create_payslip_with_lines(employee, 25000.0)
        self.assertEqual(payslip.hds_in_get_actual_pf_wage(), 25000.0)
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 25000.0)

    def test_scenario_e_zero_and_negative_wage(self):
        """Scenario E: Zero and negative wage handling -> PF Contribution Wage must be 0.0"""
        employee = self.Employee.create({
            'name': 'Employee Scenario E',
            'hds_in_pf_contribution_basis': 'statutory_ceiling',
        })
        # 1. Zero wage
        payslip_zero = self._create_payslip_with_lines(employee, 0.0)
        self.assertEqual(payslip_zero.hds_in_get_actual_pf_wage(), 0.0)
        self.assertEqual(payslip_zero.hds_in_get_pf_contribution_wage(), 0.0)

        # 2. Negative wage
        payslip_neg = self._create_payslip_with_lines(employee, -500.0)
        self.assertEqual(payslip_neg.hds_in_get_actual_pf_wage(), -500.0)
        self.assertEqual(payslip_neg.hds_in_get_pf_contribution_wage(), 0.0, "Negative wage must yield 0.0 contribution wage")

    def test_scenario_f_international_worker_override(self):
        """Scenario F: International Worker (Section 83 EPF Scheme) -> Contribution Wage is uncapped even with statutory_ceiling"""
        employee_iw = self.Employee.create({
            'name': 'International Worker',
            'hds_in_is_international_worker': True,
            'hds_in_pf_contribution_basis': 'statutory_ceiling',
        })
        payslip_iw = self._create_payslip_with_lines(employee_iw, 25000.0)
        self.assertEqual(payslip_iw.hds_in_get_actual_pf_wage(), 25000.0)
        self.assertEqual(payslip_iw.hds_in_get_pf_contribution_wage(), 25000.0, "International Worker contribution wage must remain uncapped")

    def test_scenario_g_separation_actual_pf_wage_and_contribution_wage(self):
        """Scenario G: Verify PF Contribution Wage never overwrites or mutates the Actual PF_WAGE rule result."""
        employee = self.Employee.create({
            'name': 'Separation Verification Employee',
            'hds_in_epf_applicable': True,
            'hds_in_pf_contribution_basis': 'statutory_ceiling',
        })
        contract = employee.version_id
        contract.write({
            'wage': 25000.0,
            'basic_salary': 18000.0,
            'da': 2000.0,
            'hra': 5000.0,
            'struct_id': self.struct_base.id,
        })
        payslip = self.Payslip.create({
            'name': 'Separation Payslip',
            'employee_id': employee.id,
            'contract_id': contract.id,
            'struct_id': self.struct_base.id,
            'date_from': '2026-09-01',
            'date_to': '2026-09-30',
        })
        payslip.compute_sheet()

        line_map = {line.code: line.total for line in payslip.line_ids}
        # Actual PF Wage salary rule must remain ₹30,000 (uncapped)
        self.assertEqual(line_map.get('PF_WAGE'), 30000.0, "PF_WAGE salary rule must represent Actual PF Wage (uncapped).")
        # Contribution calculations internally use PF Contribution Wage (₹25,000)
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 25000.0, "PF Contribution Wage must be capped at ₹25,000.")
        self.assertEqual(line_map.get('EPF'), -3000.0, "EPF deduction must be 12% of contribution wage ₹25,000 = -₹3,000.")

    def test_scenario_h_backward_compatibility_legacy_basis(self):
        """Scenario H: Legacy contribution basis values ('statutory_restricted' and 'actual_basic') function identically."""
        # 1. Legacy statutory_restricted
        emp_leg_capped = self.Employee.create({
            'name': 'Legacy Capped Employee',
            'hds_in_pf_contribution_basis': 'statutory_restricted',
        })
        payslip_leg_capped = self._create_payslip_with_lines(emp_leg_capped, 30000.0)
        self.assertEqual(payslip_leg_capped.hds_in_get_pf_contribution_wage(), 25000.0)

        # 2. Legacy actual_basic
        emp_leg_uncapped = self.Employee.create({
            'name': 'Legacy Uncapped Employee',
            'hds_in_pf_contribution_basis': 'actual_basic',
        })
        payslip_leg_uncapped = self._create_payslip_with_lines(emp_leg_uncapped, 22000.0)
        self.assertEqual(payslip_leg_uncapped.hds_in_get_pf_contribution_wage(), 22000.0)

    def test_scenario_i_effective_dated_parameter_ceiling(self):
        """Scenario I: Verify statutory ceiling is obtained via the effective-dated parameter system."""
        employee = self.Employee.create({
            'name': 'Parameter Test Employee',
            'hds_in_pf_contribution_basis': 'statutory_ceiling',
        })
        payslip = self._create_payslip_with_lines(employee, 30000.0, date_to='2026-05-31')
        ceiling_from_param = self.env['hr.rule.parameter'].get_pf_parameter('PF_WAGE_CEILING', date=payslip.date_to)
        self.assertEqual(ceiling_from_param, 25000.0, "Parameter system must supply the ₹25,000 ceiling")
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), ceiling_from_param)

    def test_scenario_j_inflight_localdict_execution(self):
        """Scenario J: In-flight localdict execution during compute_sheet."""
        employee = self.Employee.create({
            'name': 'Employee Localdict Test',
            'hds_in_pf_contribution_basis': 'statutory_ceiling',
        })
        payslip = self.Payslip.create({
            'name': 'Inflight Payslip',
            'employee_id': employee.id,
            'date_to': '2026-04-30',
        })

        class RuleValue:
            def __init__(self, total):
                self.total = total

        localdict = {
            'BASIC': 30000.0,
            'rules': {
                'BASIC': RuleValue(30000.0),
            }
        }
        res_capped = payslip.hds_in_get_pf_contribution_wage(localdict=localdict)
        self.assertEqual(res_capped, 25000.0)

        # Toggle to uncapped actual_pf_wage
        employee.hds_in_pf_contribution_basis = 'actual_pf_wage'
        res_uncapped = payslip.hds_in_get_pf_contribution_wage(localdict=localdict)
        self.assertEqual(res_uncapped, 30000.0)

    def test_scenario_k_backward_compatible_aliases(self):
        """Scenario K: Backward compatible alias methods get_pf_contribution_wage and get_pf_eligible_wage."""
        employee = self.Employee.create({
            'name': 'Alias Employee',
            'hds_in_pf_contribution_basis': 'statutory_ceiling',
        })
        payslip = self._create_payslip_with_lines(employee, 30000.0)
        self.assertEqual(payslip.get_pf_eligible_wage(), 30000.0)
        self.assertEqual(payslip.get_pf_contribution_wage(), 25000.0)
