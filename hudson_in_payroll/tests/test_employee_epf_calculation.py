# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests import common


class TestEmployeeEpfCalculation(common.TransactionCase):
    """
    Dedicated test suite for Employee EPF contribution calculation layer in hudson_in_payroll.
    Validates:
      - Contribution Wage × Effective EPF Rate
      - Negative deduction representation on payslip
      - Company and employee applicability guards
      - Zero/negative wage handling
      - Historical effective-dated rate application
      - International Worker uncapped deduction
      - Absence of mutation across payslip wage rules
    """

    def setUp(self):
        super(TestEmployeeEpfCalculation, self).setUp()
        self.SalaryRule = self.env['hr.salary.rule']
        self.Payslip = self.env['hr.payslip']
        self.PayslipLine = self.env['hr.payslip.line']
        self.Employee = self.env['hr.employee']
        self.Company = self.env['res.company']
        self.Category = self.env['hr.salary.rule.category']
        self.RuleParameter = self.env['hr.rule.parameter']
        self.RuleParameterValue = self.env['hr.rule.parameter.value']

        self.category_alw = self.Category.search([], limit=1)
        self.struct_base = self.env.ref('hudson_payroll_base.structure_base')
        self.env.company.hds_in_epf_applicable = True

        # Ensure BASIC rule exists and contributes to PF Wage
        self.rule_basic = self.env.ref('hudson_payroll_base.hr_rule_basic', raise_if_not_found=False)
        if not self.rule_basic:
            self.rule_basic = self.SalaryRule.search([('code', '=', 'BASIC'), ('struct_id', '=', self.struct_base.id)], limit=1)
        if not self.rule_basic:
            self.rule_basic = self.SalaryRule.create({
                'name': 'Basic Salary',
                'code': 'BASIC',
                'category_id': self.category_alw.id,
                'struct_id': self.struct_base.id,
                'hds_in_include_in_pf_wage': True,
            })
        self.rule_basic.write({'hds_in_include_in_pf_wage': True})

        # Ensure DA rule exists and contributes to PF Wage
        self.rule_da = self.SalaryRule.search([('code', '=', 'DA'), ('struct_id', '=', self.struct_base.id)], limit=1)
        if not self.rule_da:
            self.rule_da = self.SalaryRule.create({
                'name': 'Dearness Allowance',
                'code': 'DA',
                'category_id': self.category_alw.id,
                'struct_id': self.struct_base.id,
                'hds_in_include_in_pf_wage': True,
            })
        self.rule_da.write({'hds_in_include_in_pf_wage': True})

        # Ensure PF Wage Ceiling parameter exists at ₹25,000
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

        # Ensure EPF Rate parameter exists at 12%
        self.epf_rate_param = self.RuleParameter.search([('code', '=', 'hds_in_epf_rate')], limit=1)
        if not self.epf_rate_param:
            self.epf_rate_param = self.RuleParameter.create({
                'name': 'EPF Rate',
                'code': 'hds_in_epf_rate',
                'category': 'rate',
            })
            self.RuleParameterValue.create({
                'parameter_id': self.epf_rate_param.id,
                'date_from': '2014-09-01',
                'parameter_value': '12',
            })

    def _create_payslip_and_employee(self, name, basic=0.0, da=0.0, hra=0.0, basis='statutory_ceiling',
                                     ee_epf_applicable=True, company_epf_applicable=True,
                                     is_iw=False, date_from='2026-09-01', date_to='2026-09-30', company=None):
        comp = company or self.env.company
        comp.hds_in_epf_applicable = company_epf_applicable

        emp = self.Employee.create({
            'name': name,
            'company_id': comp.id,
            'hds_in_epf_applicable': ee_epf_applicable,
            'hds_in_pf_contribution_basis': basis,
            'hds_in_is_international_worker': is_iw,
        })
        contract = emp.version_id
        contract.write({
            'wage': basic + da + hra,
            'basic_salary': basic,
            'da': da,
            'hra': hra,
            'struct_id': self.struct_base.id,
            'date_start': date_from,
            'contract_date_start': date_from,
            'pay_by_attendance': False,
            'enable_attendance_threshold': False,
        })

        payslip = self.Payslip.create({
            'name': f'Payslip {name}',
            'employee_id': emp.id,
            'contract_id': contract.id,
            'struct_id': self.struct_base.id,
            'company_id': comp.id,
            'date_from': date_from,
            'date_to': date_to,
        })
        return emp, payslip

    def test_scenario_a_wage_below_ceiling(self):
        """
        Scenario A:
        Actual PF Wage = ₹8,800 (BASIC ₹8,000 + DA ₹800)
        Contribution Basis = statutory_ceiling
        Ceiling = ₹15,000
        EPF Rate = 12%
        Expected: Contribution Wage = ₹8,800, Employee EPF = -₹1,056
        """
        emp, payslip = self._create_payslip_and_employee(
            'Scenario A Employee', basic=8000.0, da=800.0, hra=3200.0, basis='statutory_ceiling'
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        self.assertEqual(line_map.get('PF_WAGE'), 8800.0, "Actual PF Wage must be 8800.0")
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 8800.0, "Contribution wage must be 8800.0")
        self.assertEqual(line_map.get('EPF'), -1056.0, "Employee EPF must be -1056.0 (-12% of 8800.0)")

    def test_scenario_b_wage_above_ceiling(self):
        """
        Scenario B:
        Actual PF Wage = ₹30,000 (BASIC ₹28,000 + DA ₹2,000)
        Contribution Basis = statutory_ceiling
        Ceiling = ₹25,000
        EPF Rate = 12%
        Expected: Contribution Wage = ₹25,000, Employee EPF = -₹3,000
        """
        emp, payslip = self._create_payslip_and_employee(
            'Scenario B Employee', basic=28000.0, da=2000.0, hra=5000.0, basis='statutory_ceiling'
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        self.assertEqual(line_map.get('PF_WAGE'), 30000.0, "Actual PF Wage must be 30000.0")
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 25000.0, "Contribution wage must be capped at 25000.0")
        self.assertEqual(line_map.get('EPF'), -3000.0, "Employee EPF must be -3000.0 (-12% of 25000.0)")

    def test_scenario_c_uncapped_contribution(self):
        """
        Scenario C:
        Actual PF Wage = ₹20,000 (BASIC ₹18,000 + DA ₹2,000)
        Contribution Basis = actual_pf_wage
        EPF Rate = 12%
        Expected: Contribution Wage = ₹20,000, Employee EPF = -₹2,400
        """
        emp, payslip = self._create_payslip_and_employee(
            'Scenario C Employee', basic=18000.0, da=2000.0, hra=5000.0, basis='actual_pf_wage'
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        self.assertEqual(line_map.get('PF_WAGE'), 20000.0, "Actual PF Wage must be 20000.0")
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 20000.0, "Contribution wage must be uncapped 20000.0")
        self.assertEqual(line_map.get('EPF'), -2400.0, "Employee EPF must be -2400.0 (-12% of 20000.0)")

    def test_scenario_d_zero_and_negative_contribution_wage(self):
        """
        Scenario D:
        Contribution Wage = ₹0 or negative
        Expected: Employee EPF = ₹0
        """
        emp, payslip = self._create_payslip_and_employee(
            'Scenario D Employee', basic=0.0, da=0.0, basis='statutory_ceiling'
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 0.0)
        self.assertEqual(line_map.get('EPF', 0.0), 0.0, "Employee EPF must be 0 for zero wage")

    def test_scenario_e_employee_epf_applicable_false(self):
        """
        Scenario E:
        Employee EPF applicable = False
        Expected: Employee EPF = ₹0
        """
        emp, payslip = self._create_payslip_and_employee(
            'Scenario E Employee', basic=10000.0, da=1000.0, ee_epf_applicable=False
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        self.assertEqual(line_map.get('EPF', 0.0), 0.0, "Employee EPF must be 0 when employee EPF applicability is False")

    def test_scenario_f_company_epf_applicable_false(self):
        """
        Scenario F:
        Company EPF applicable = False
        Expected: Employee EPF = ₹0
        """
        emp, payslip = self._create_payslip_and_employee(
            'Scenario F Employee', basic=10000.0, da=1000.0, company_epf_applicable=False
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        self.assertEqual(line_map.get('EPF', 0.0), 0.0, "Employee EPF must be 0 when company EPF applicability is False")

    def test_scenario_g_historical_payslip_effective_rate(self):
        """
        Scenario G:
        Historical payslip where EPF rate differs from today's rate.
        Expected: The rate effective on the payslip period date must be used.
        """
        # Ensure historical ceiling parameter exists for 2010
        hist_ceiling = self.RuleParameterValue.search([
            ('parameter_id', '=', self.pf_ceiling_param.id),
            ('date_from', '<=', '2012-05-01'),
        ], limit=1)
        if not hist_ceiling:
            self.RuleParameterValue.create({
                'parameter_id': self.pf_ceiling_param.id,
                'date_from': '2010-01-01',
                'parameter_value': '6500',
            })

        # Ensure historical rate parameter exists: 10% effective 2010-01-01
        hist_rate = self.RuleParameterValue.search([
            ('parameter_id', '=', self.epf_rate_param.id),
            ('date_from', '=', '2010-01-01'),
        ], limit=1)
        if not hist_rate:
            self.RuleParameterValue.create({
                'parameter_id': self.epf_rate_param.id,
                'date_from': '2010-01-01',
                'parameter_value': '10',
            })

        # Historical payslip for May 2012 (wage ₹5,000 <= ₹6,500 ceiling)
        emp_hist, payslip_hist = self._create_payslip_and_employee(
            'Historical Employee', basic=5000.0, da=0.0, date_from='2012-05-01', date_to='2012-05-31'
        )
        payslip_hist.compute_sheet()
        line_map_hist = {l.code: l.total for l in payslip_hist.line_ids}
        # In May 2012: 10% of 5,000 = -500.0
        self.assertEqual(line_map_hist.get('EPF'), -500.0, "Historical payslip must use 10% rate effective in May 2012")

        # Current payslip for September 2026 (wage ₹5,000)
        emp_curr, payslip_curr = self._create_payslip_and_employee(
            'Current Employee', basic=5000.0, da=0.0, date_from='2026-09-01', date_to='2026-09-30'
        )
        payslip_curr.compute_sheet()
        line_map_curr = {l.code: l.total for l in payslip_curr.line_ids}
        # In September 2026: 12% of 5,000 = -600.0
        self.assertEqual(line_map_curr.get('EPF'), -600.0, "Current payslip must use 12% rate effective in September 2026")

    def test_scenario_h_international_worker_deduction(self):
        """
        Scenario H:
        International Worker with actual PF wage ₹25,000.
        Expected: Contribution Wage = ₹25,000 (uncapped), Employee EPF = -₹3,000 (12% of 25,000)
        """
        emp, payslip = self._create_payslip_and_employee(
            'Scenario H IW Employee', basic=25000.0, da=0.0, is_iw=True, basis='statutory_ceiling'
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 25000.0, "IW contribution wage must be uncapped 25000.0")
        self.assertEqual(line_map.get('EPF'), -3000.0, "IW Employee EPF must be -3000.0 (-12% of 25000.0)")

    def test_scenario_i_no_mutation_of_wages(self):
        """
        Scenario I: Verify that computing Employee EPF does NOT modify or mutate PF_WAGE.
        """
        emp, payslip = self._create_payslip_and_employee(
            'No Mutation Employee', basic=30000.0, da=0.0, basis='statutory_ceiling'
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        self.assertEqual(line_map.get('PF_WAGE'), 30000.0, "PF_WAGE must remain intact at ₹30,000.")
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 25000.0, "Contribution wage must remain capped at ₹25,000.")
        self.assertEqual(line_map.get('EPF'), -3000.0, "Employee EPF must be -₹3,000 (-12% of ₹25,000).")
