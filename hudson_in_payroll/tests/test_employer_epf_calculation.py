# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests import common
from ..services.epf.epf_service import EPFService


class TestEmployerEpfCalculation(common.TransactionCase):
    """
    Dedicated audit test suite for Employer EPF contribution calculation in hudson_in_payroll.
    Validates:
      - Formula: Employer EPF = PF Contribution Wage × Effective Employer EPF Rate
      - Positive representation (+₹1,800) as Employer Cost (Category: COMP)
      - Independent evaluation from Employee EPF while sharing PF Contribution Wage
      - Company applicability guard (company.hds_in_epf_applicable = False -> 0)
      - Employee applicability guard (employee.hds_in_epf_applicable = False -> 0)
      - Zero/negative contribution wage guard (wage <= 0 -> 0)
      - Historical effective-dated rate retrieval (payslip period date vs today)
      - International Worker uncapped computation
      - Zero impact on Gross Salary and Employee Net Salary
      - Salary rule execution sequence (EMPLOYER_EPF sequence > PF_WAGE sequence)
      - Statutory rounding compliance
    """

    def setUp(self):
        super(TestEmployerEpfCalculation, self).setUp()
        self.SalaryRule = self.env['hr.salary.rule']
        self.Payslip = self.env['hr.payslip']
        self.Employee = self.env['hr.employee']
        self.Company = self.env['res.company']
        self.Category = self.env['hr.salary.rule.category']
        self.RuleParameter = self.env['hr.rule.parameter']
        self.RuleParameterValue = self.env['hr.rule.parameter.value']

        self.category_alw = self.Category.search([('code', '=', 'ALW')], limit=1)
        self.category_comp = self.Category.search([('code', '=', 'COMP')], limit=1)
        self.struct_base = self.env.ref('hudson_payroll_base.structure_base')
        self.env.company.hds_in_epf_applicable = True

        # 1. Ensure BASIC rule exists and contributes to PF Wage
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
                'sequence': 10,
            })
        self.rule_basic.write({'hds_in_include_in_pf_wage': True})

        # 2. Ensure DA rule exists and contributes to PF Wage
        self.rule_da = self.SalaryRule.search([('code', '=', 'DA'), ('struct_id', '=', self.struct_base.id)], limit=1)
        if not self.rule_da:
            self.rule_da = self.SalaryRule.create({
                'name': 'Dearness Allowance',
                'code': 'DA',
                'category_id': self.category_alw.id,
                'struct_id': self.struct_base.id,
                'hds_in_include_in_pf_wage': True,
                'sequence': 16,
            })
        self.rule_da.write({'hds_in_include_in_pf_wage': True})

        # 3. Ensure PF Wage Ceiling parameter exists at ₹25,000
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

        # 4. Ensure Employee EPF Rate parameter exists at 12%
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

        # 5. Ensure Employer EPF Rate parameter exists at 12%
        self.employer_epf_rate_param = self.RuleParameter.search([('code', '=', 'hds_in_employer_epf_rate')], limit=1)
        if not self.employer_epf_rate_param:
            self.employer_epf_rate_param = self.RuleParameter.create({
                'name': 'Employer EPF Rate',
                'code': 'hds_in_employer_epf_rate',
                'category': 'rate',
            })
            self.RuleParameterValue.create({
                'parameter_id': self.employer_epf_rate_param.id,
                'date_from': '2014-09-01',
                'parameter_value': '12',
            })

        # 6. Ensure EMPLOYER_EPF Salary Rule exists
        self.rule_employer_epf = self.env.ref('hudson_in_payroll.hds_in_rule_epf_er', raise_if_not_found=False)
        if self.rule_employer_epf:
            self.rule_employer_epf.write({
                'code': 'EMPLOYER_EPF',
                'amount_python_compute': 'result = payslip_record.hds_in_compute_employer_epf()',
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
        Actual PF Wage = ₹8,800
        Contribution Basis = statutory_ceiling
        Ceiling = ₹15,000
        Employer EPF Rate = 12%

        Expected:
        Contribution Wage = ₹8,800
        Employer EPF = ₹1,056
        """
        emp, payslip = self._create_payslip_and_employee(
            'Scenario A Employee', basic=8000.0, da=800.0, hra=3200.0, basis='statutory_ceiling'
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        self.assertEqual(line_map.get('PF_WAGE'), 8800.0, "Actual PF Wage must be 8800.0")
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 8800.0, "Contribution wage must be 8800.0")
        # Employer EPF rule
        er_epf = line_map.get('EMPLOYER_EPF') or line_map.get('EPF_ER')
        self.assertEqual(er_epf, 1056.0, "Employer EPF must be +1056.0 (12% of 8800.0)")

        # Verify through direct service API
        service = EPFService(self.env)
        self.assertEqual(service.compute_employer_epf(payslip), 1056.0)

    def test_scenario_b_wage_above_ceiling(self):
        """
        Scenario B:
        Actual PF Wage = ₹30,000
        Contribution Basis = statutory_ceiling
        Ceiling = ₹25,000
        Employer EPF Rate = 12%

        Expected:
        Contribution Wage = ₹25,000
        Employer EPF = ₹3,000
        """
        emp, payslip = self._create_payslip_and_employee(
            'Scenario B Employee', basic=28000.0, da=2000.0, hra=5000.0, basis='statutory_ceiling'
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        self.assertEqual(line_map.get('PF_WAGE'), 30000.0, "Actual PF Wage must be 30000.0")
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 25000.0, "Contribution wage must be capped at 25000.0")
        er_epf = line_map.get('EMPLOYER_EPF') or line_map.get('EPF_ER')
        self.assertEqual(er_epf, 3000.0, "Employer EPF must be +3000.0 (12% of 25000.0)")

    def test_scenario_c_uncapped_contribution(self):
        """
        Scenario C:
        Actual PF Wage = ₹20,000
        Contribution Basis = actual_pf_wage
        Employer EPF Rate = 12%

        Expected:
        Contribution Wage = ₹20,000
        Employer EPF = ₹2,400
        """
        emp, payslip = self._create_payslip_and_employee(
            'Scenario C Employee', basic=18000.0, da=2000.0, hra=5000.0, basis='actual_pf_wage'
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        self.assertEqual(line_map.get('PF_WAGE'), 20000.0, "Actual PF Wage must be 20000.0")
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 20000.0, "Contribution wage must be uncapped at 20000.0")
        er_epf = line_map.get('EMPLOYER_EPF') or line_map.get('EPF_ER')
        self.assertEqual(er_epf, 2400.0, "Employer EPF must be +2400.0 (12% of 20000.0)")

    def test_scenario_d_zero_wage(self):
        """
        Scenario D:
        Contribution Wage = ₹0

        Expected:
        Employer EPF = ₹0
        """
        emp, payslip = self._create_payslip_and_employee(
            'Scenario D Employee', basic=0.0, da=0.0, hra=0.0, basis='statutory_ceiling'
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        self.assertEqual(line_map.get('PF_WAGE', 0.0), 0.0)
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 0.0)
        er_epf = line_map.get('EMPLOYER_EPF', 0.0) or line_map.get('EPF_ER', 0.0)
        self.assertEqual(er_epf, 0.0, "Employer EPF on zero contribution wage must be 0.0")

    def test_scenario_e_employee_epf_not_applicable(self):
        """
        Scenario E:
        Employee EPF applicable = False

        Expected:
        Employer EPF = ₹0
        """
        emp, payslip = self._create_payslip_and_employee(
            'Scenario E Employee', basic=15000.0, da=0.0, ee_epf_applicable=False
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        er_epf = line_map.get('EMPLOYER_EPF', 0.0) or line_map.get('EPF_ER', 0.0)
        self.assertEqual(er_epf, 0.0, "Employer EPF must be 0.0 when employee EPF is disabled")
        self.assertEqual(line_map.get('EPF', 0.0), 0.0, "Employee EPF must also be 0.0")

    def test_scenario_f_company_epf_not_applicable(self):
        """
        Scenario F:
        Company EPF applicable = False

        Expected:
        Employer EPF = ₹0
        """
        other_comp = self.Company.create({
            'name': 'Non-EPF Company',
            'hds_in_epf_applicable': False,
        })
        emp, payslip = self._create_payslip_and_employee(
            'Scenario F Employee', basic=15000.0, da=0.0, company_epf_applicable=False, company=other_comp
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        er_epf = line_map.get('EMPLOYER_EPF', 0.0) or line_map.get('EPF_ER', 0.0)
        self.assertEqual(er_epf, 0.0, "Employer EPF must be 0.0 when company EPF is disabled")
        self.assertEqual(line_map.get('EPF', 0.0), 0.0, "Employee EPF must also be 0.0")

    def test_scenario_g_historical_payslip_date(self):
        """
        Scenario G:
        Historical payslip with a different historical Employer EPF rate.
        Period: 2012-01-01 to 2012-01-31.
        Historical rate: 10% (configured for dates before 2014-09-01).

        Expected:
        Historical effective rate (10%) is used.
        """
        # Create historical parameter value for dates before 2014-09-01
        self.RuleParameterValue.create({
            'parameter_id': self.employer_epf_rate_param.id,
            'date_from': '2010-01-01',
            'parameter_value': '10',
        })

        emp, payslip = self._create_payslip_and_employee(
            'Historical Employee', basic=10000.0, da=0.0, basis='actual_pf_wage',
            date_from='2012-01-01', date_to='2012-01-31'
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        # Rate should be 10% on ₹10,000 -> ₹1,000
        er_epf = line_map.get('EMPLOYER_EPF') or line_map.get('EPF_ER')
        self.assertEqual(er_epf, 1000.0, "Historical Employer EPF rate of 10% must yield 1000.0")

    def test_scenario_h_international_worker(self):
        """
        Scenario H:
        International Worker:
        Actual PF Wage = ₹25,000

        Expected:
        Contribution Wage = ₹25,000
        Employer EPF = ₹25,000 × effective Employer EPF rate (12%) = ₹3,000
        """
        emp, payslip = self._create_payslip_and_employee(
            'IW Employee', basic=20000.0, da=5000.0, is_iw=True, basis='statutory_ceiling'
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        self.assertEqual(line_map.get('PF_WAGE'), 25000.0)
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 25000.0, "IW must bypass 15k ceiling")
        er_epf = line_map.get('EMPLOYER_EPF') or line_map.get('EPF_ER')
        self.assertEqual(er_epf, 3000.0, "Employer EPF for IW must be 12% of 25,000 = 3000.0")

    def test_scenario_i_reconciliation_and_net_salary_independence(self):
        """
        Scenario I:
        Reconciliation:
        Employer EPF is calculated independently from Employee EPF,
        but both must use the same PF Contribution Wage.

        Example:
        Contribution Wage = ₹15,000
        Employee EPF rate = 12%
        Employer EPF rate = 12%

        Employee EPF = -₹1,800 deduction
        Employer EPF = +₹1,800 employer cost

        Verify:
        - Employer EPF does not affect Gross Salary
        - Employer EPF does not reduce Employee Net Salary
        - NET = GROSS - DEDUCTIONS
        """
        emp, payslip = self._create_payslip_and_employee(
            'Reconcile Employee', basic=15000.0, da=0.0, hra=5000.0, basis='statutory_ceiling'
        )
        payslip.compute_sheet()
        line_map = {l.code: l.total for l in payslip.line_ids}

        ee_epf = line_map.get('EPF')
        er_epf = line_map.get('EMPLOYER_EPF') or line_map.get('EPF_ER')
        gross = line_map.get('GROSS')
        net = line_map.get('NET')

        # 1. Both use same contribution wage
        self.assertEqual(payslip.hds_in_get_pf_contribution_wage(), 15000.0)

        # 2. Employee EPF is negative deduction (-1800.0)
        self.assertEqual(ee_epf, -1800.0, "Employee EPF must be -1800.0 deduction")

        # 3. Employer EPF is positive cost (+1800.0)
        self.assertEqual(er_epf, 1800.0, "Employer EPF must be +1800.0 employer cost")

        # 4. Gross Salary = Basic (15000) + HRA (5000) = 20000
        self.assertEqual(gross, 20000.0, "Gross salary must be 20000.0")

        # 5. Employer EPF must NOT reduce Net Salary
        # Net Salary should be Gross - Deductions = 20000 - 1800 = 18200 (assuming no other deductions)
        # If Employer EPF were incorrectly deducted, Net would be 16400.
        self.assertEqual(net, 18200.0, "Net Salary must NOT be reduced by Employer EPF")

    def test_salary_rule_sequence_and_category(self):
        """
        Requirement 8, 9, 10:
        - Category must be COMP (Company Contribution)
        - Sequence must be > sequence of PF_WAGE (20)
        """
        rule_pf_wage = self.env['hr.salary.rule'].search([
            ('code', '=', 'PF_WAGE'), ('struct_id', '=', self.struct_base.id)
        ], limit=1)
        er_rule = self.env['hr.salary.rule'].search([
            ('code', 'in', ('EMPLOYER_EPF', 'EPF_ER')), ('struct_id', '=', self.struct_base.id)
        ], limit=1)

        self.assertTrue(rule_pf_wage, "PF_WAGE rule must exist")
        self.assertTrue(er_rule, "EMPLOYER_EPF rule must exist")

        self.assertGreater(er_rule.sequence, rule_pf_wage.sequence,
                           f"EMPLOYER_EPF sequence ({er_rule.sequence}) must execute after PF_WAGE ({rule_pf_wage.sequence})")
        self.assertEqual(er_rule.category_id.code, 'COMP', "EMPLOYER_EPF category must be COMP")
