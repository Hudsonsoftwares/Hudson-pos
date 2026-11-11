# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from ..services.epf.epf_service import EPFService, ContractPayslipAdapter


class TestEdliCeilingEnforcement(TransactionCase):
    """
    Audit test suite verifying strict statutory enforcement of EDLI wage ceiling
    under Paragraph 28(1) of the EDLI Scheme, 1976.
    Validates:
      - EDLI wage is always min(actual_pf_wage, edli_ceiling)
      - Wages below ceiling remain uninflated
      - International Workers cannot bypass the EDLI ceiling
      - Actual-wage PF contribution basis cannot bypass the EDLI ceiling
      - Dynamically responds to configured date-effective rule parameter (both 15k and 25k)
      - EPF uncapped rules for International Workers remain unaffected
      - Non-applicable / exempt employees yield 0 contribution
      - EDLI admin charge also strictly enforces the statutory ceiling
    """

    @classmethod
    def _gc_filestore(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        try:
            super(TestEdliCeilingEnforcement, cls).tearDownClass()
        except BaseException:
            pass

    def setUp(self):
        super().setUp()
        self.Employee = self.env['hr.employee']
        self.RuleParameter = self.env['hr.rule.parameter']
        self.RuleParameterValue = self.env['hr.rule.parameter.value']
        self.struct_base = self.env.ref('hudson_payroll_base.structure_base')
        self.env.company.hds_in_epf_applicable = True

        # Ensure EDLI Wage Ceiling parameter exists
        self.edli_ceiling_param = self.RuleParameter.search([('code', '=', 'hds_in_edli_wage_ceiling')], limit=1)
        if not self.edli_ceiling_param:
            self.edli_ceiling_param = self.RuleParameter.create({
                'name': 'EDLI Wage Ceiling',
                'code': 'hds_in_edli_wage_ceiling',
                'category': 'ceiling',
            })
        self.edli_ceiling_val = self.RuleParameterValue.search([('parameter_id', '=', self.edli_ceiling_param.id)], limit=1)
        if not self.edli_ceiling_val:
            self.edli_ceiling_val = self.RuleParameterValue.create({
                'parameter_id': self.edli_ceiling_param.id,
                'date_from': '2014-09-01',
                'parameter_value': '25000',
            })

        # Ensure EDLI Rate parameter exists (0.5%)
        self.edli_rate_param = self.RuleParameter.search([('code', '=', 'hds_in_edli_rate')], limit=1)
        if not self.edli_rate_param:
            self.edli_rate_param = self.RuleParameter.create({
                'name': 'EDLI Rate',
                'code': 'hds_in_edli_rate',
                'category': 'rate',
            })
        self.edli_rate_val = self.RuleParameterValue.search([('parameter_id', '=', self.edli_rate_param.id)], limit=1)
        if not self.edli_rate_val:
            self.edli_rate_val = self.RuleParameterValue.create({
                'parameter_id': self.edli_rate_param.id,
                'date_from': '2014-09-01',
                'parameter_value': '0.5',
            })

        # Ensure Employer EPF Rate exists (12%)
        self.er_epf_rate_param = self.RuleParameter.search([('code', '=', 'hds_in_employer_epf_rate')], limit=1)
        if not self.er_epf_rate_param:
            self.er_epf_rate_param = self.RuleParameter.create({
                'name': 'Employer EPF Rate',
                'code': 'hds_in_employer_epf_rate',
                'category': 'rate',
            })
            self.RuleParameterValue.create({
                'parameter_id': self.er_epf_rate_param.id,
                'date_from': '2014-09-01',
                'parameter_value': '12',
            })

        # Initialize EPF domain service
        self.epf_svc = EPFService(self.env)

    def _create_employee_and_adapter(self, name, wage=0.0, basis='actual_pf_wage', is_iw=False, epf_applicable=True):
        emp = self.Employee.create({
            'name': name,
            'company_id': self.env.company.id,
            'hds_in_epf_applicable': epf_applicable,
            'hds_in_pf_contribution_basis': basis,
            'hds_in_is_international_worker': is_iw,
        })
        contract = emp.version_id
        c_vals = {
            'wage': wage,
            'basic_salary': wage,
            'struct_id': self.struct_base.id,
        }
        if 'contract_date_start' in contract._fields:
            c_vals['contract_date_start'] = '2026-01-01'
        if 'date_start' in contract._fields:
            c_vals['date_start'] = '2026-01-01'
        contract.write(c_vals)

        adapter = ContractPayslipAdapter(contract, employee=emp)
        return emp, adapter

    def test_01_scenario_a_wage_above_25k_ceiling(self):
        """
        Scenario A: Normal employee earning ₹60,000 / month.
        Ceiling: ₹25,000.
        EDLI Wage must be capped at ₹25,000.
        Contribution (0.5%): 25,000 * 0.005 = ₹125.0.
        """
        self.edli_ceiling_val.parameter_value = '25000'
        emp, adapter = self._create_employee_and_adapter('Emp_ScenarioA', wage=60000.0, basis='actual_pf_wage')
        edli_contrib = self.epf_svc.compute_employer_edli(adapter)
        self.assertEqual(edli_contrib, 125.0, "EDLI contribution for ₹60k wage with ₹25k ceiling must be ₹125.0")

    def test_02_scenario_b_wage_below_25k_ceiling(self):
        """
        Scenario B: Normal employee earning ₹20,000 / month.
        Ceiling: ₹25,000.
        EDLI Wage must remain ₹20,000 (not inflated).
        Contribution (0.5%): 20,000 * 0.005 = ₹100.0.
        """
        self.edli_ceiling_val.parameter_value = '25000'
        emp, adapter = self._create_employee_and_adapter('Emp_ScenarioB', wage=20000.0, basis='actual_pf_wage')
        edli_contrib = self.epf_svc.compute_employer_edli(adapter)
        self.assertEqual(edli_contrib, 100.0, "EDLI contribution for ₹20k wage with ₹25k ceiling must be ₹100.0")

    def test_03_scenario_c_wage_low_8k_below_ceiling(self):
        """
        Scenario C: Normal employee earning ₹8,000 / month.
        Ceiling: ₹25,000.
        EDLI Wage must remain ₹8,000.
        Contribution (0.5%): 8,000 * 0.005 = ₹40.0.
        """
        self.edli_ceiling_val.parameter_value = '25000'
        emp, adapter = self._create_employee_and_adapter('Emp_ScenarioC', wage=8000.0, basis='actual_pf_wage')
        edli_contrib = self.epf_svc.compute_employer_edli(adapter)
        self.assertEqual(edli_contrib, 40.0, "EDLI contribution for ₹8k wage must be ₹40.0")

    def test_04_scenario_d_international_worker_above_ceiling(self):
        """
        Scenario D: International Worker earning ₹60,000 / month.
        Ceiling: ₹25,000.
        International worker flag must NOT bypass EDLI ceiling.
        EDLI Wage = ₹25,000 -> EDLI Contribution = ₹125.0.
        """
        self.edli_ceiling_val.parameter_value = '25000'
        emp, adapter = self._create_employee_and_adapter('Emp_ScenarioD', wage=60000.0, basis='actual_pf_wage', is_iw=True)
        edli_contrib = self.epf_svc.compute_employer_edli(adapter)
        self.assertEqual(edli_contrib, 125.0, "International Worker must NOT bypass EDLI ceiling (must be ₹125.0)")

    def test_05_scenario_e_international_worker_below_ceiling(self):
        """
        Scenario E: International Worker earning ₹20,000 / month.
        Ceiling: ₹25,000.
        EDLI Wage must remain ₹20,000 (not inflated).
        Contribution = 20,000 * 0.005 = ₹100.0.
        """
        self.edli_ceiling_val.parameter_value = '25000'
        emp, adapter = self._create_employee_and_adapter('Emp_ScenarioE', wage=20000.0, basis='actual_pf_wage', is_iw=True)
        edli_contrib = self.epf_svc.compute_employer_edli(adapter)
        self.assertEqual(edli_contrib, 100.0, "IW below ceiling must use actual wage ₹20k -> ₹100.0")

    def test_06_scenario_f_15k_ceiling_matrix(self):
        """
        Scenario F: Verify behavior across wage spectrum with a ₹15,000 ceiling.
        | Wage    | Expected EDLI Wage | Expected Contrib (0.5%) |
        | ₹8,000  | ₹8,000             | ₹40.0                   |
        | ₹15,000 | ₹15,000            | ₹75.0                   |
        | ₹20,000 | ₹15,000            | ₹75.0                   |
        | ₹30,000 | ₹15,000            | ₹75.0                   |
        | ₹60,000 | ₹15,000            | ₹75.0                   |
        """
        self.edli_ceiling_val.parameter_value = '15000'
        test_matrix = [
            (8000.0, 40.0),
            (15000.0, 75.0),
            (20000.0, 75.0),
            (30000.0, 75.0),
            (60000.0, 75.0),
        ]
        for wage, expected_contrib in test_matrix:
            emp, adapter = self._create_employee_and_adapter(f'Emp_15k_{int(wage)}', wage=wage, basis='actual_pf_wage')
            edli_contrib = self.epf_svc.compute_employer_edli(adapter)
            self.assertEqual(edli_contrib, expected_contrib, f"At ₹15k ceiling, wage ₹{wage} must yield ₹{expected_contrib}")

    def test_07_scenario_g_25k_ceiling_matrix(self):
        """
        Scenario G: Verify behavior across wage spectrum with a ₹25,000 ceiling.
        | Wage    | Expected EDLI Wage | Expected Contrib (0.5%) |
        | ₹8,000  | ₹8,000             | ₹40.0                   |
        | ₹15,000 | ₹15,000            | ₹75.0                   |
        | ₹20,000 | ₹20,000            | ₹100.0                  |
        | ₹25,000 | ₹25,000            | ₹125.0                  |
        | ₹30,000 | ₹25,000            | ₹125.0                  |
        | ₹60,000 | ₹25,000            | ₹125.0                  |
        """
        self.edli_ceiling_val.parameter_value = '25000'
        test_matrix = [
            (8000.0, 40.0),
            (15000.0, 75.0),
            (20000.0, 100.0),
            (25000.0, 125.0),
            (30000.0, 125.0),
            (60000.0, 125.0),
        ]
        for wage, expected_contrib in test_matrix:
            emp, adapter = self._create_employee_and_adapter(f'Emp_25k_{int(wage)}', wage=wage, basis='actual_pf_wage')
            edli_contrib = self.epf_svc.compute_employer_edli(adapter)
            self.assertEqual(edli_contrib, expected_contrib, f"At ₹25k ceiling, wage ₹{wage} must yield ₹{expected_contrib}")

    def test_08_actual_wage_basis_capped(self):
        """
        Verify that basis='actual_pf_wage' strictly respects the statutory EDLI ceiling.
        """
        self.edli_ceiling_val.parameter_value = '25000'
        emp, adapter = self._create_employee_and_adapter('Emp_ActualPfWage', wage=80000.0, basis='actual_pf_wage')
        edli_contrib = self.epf_svc.compute_employer_edli(adapter)
        self.assertEqual(edli_contrib, 125.0, "actual_pf_wage basis must strictly cap EDLI to ₹25k -> ₹125.0")

    def test_09_other_contributions_unaffected(self):
        """
        Verify that EPF for International Workers remains uncapped while EDLI is capped.
        IW on ₹60,000 wage:
        - Employer EPF total: 60,000 * 12% = ₹7,200 (uncapped)
        - Employer EDLI: min(60,000, 25,000) * 0.5% = ₹125.0 (capped)
        """
        self.edli_ceiling_val.parameter_value = '25000'
        emp, adapter = self._create_employee_and_adapter('Emp_IW_Isolation', wage=60000.0, basis='actual_pf_wage', is_iw=True)
        er_epf = self.epf_svc.compute_employer_total_pf(adapter)
        edli_contrib = self.epf_svc.compute_employer_edli(adapter)

        self.assertEqual(er_epf, 7200.0, "IW Employer EPF must remain uncapped (₹7,200.0)")
        self.assertEqual(edli_contrib, 125.0, "IW Employer EDLI must be capped (₹125.0)")

    def test_10_exemptions_and_admin_charges(self):
        """
        Verify exemptions and EDLI admin charges:
        1. hds_in_epf_applicable=False -> EDLI = ₹0.0
        2. Wage = 0 -> EDLI = ₹0.0
        3. EDLI admin charge uses the same capped EDLI wage.
        """
        self.edli_ceiling_val.parameter_value = '25000'
        emp_exempt, adapter_exempt = self._create_employee_and_adapter('Emp_Exempt', wage=60000.0, epf_applicable=False)
        self.assertEqual(self.epf_svc.compute_employer_edli(adapter_exempt), 0.0, "Exempt employee must yield ₹0.0 EDLI")

        emp_zero, adapter_zero = self._create_employee_and_adapter('Emp_Zero', wage=0.0)
        self.assertEqual(self.epf_svc.compute_employer_edli(adapter_zero), 0.0, "Zero wage must yield ₹0.0 EDLI")

        # Test EDLI Admin Charge capping
        edli_admin_param = self.RuleParameter.search([('code', '=', 'hds_in_edli_admin_charge_rate')], limit=1)
        if not edli_admin_param:
            edli_admin_param = self.RuleParameter.create({
                'name': 'EDLI Admin Rate',
                'code': 'hds_in_edli_admin_charge_rate',
                'category': 'admin',
            })
        admin_val = self.RuleParameterValue.search([('parameter_id', '=', edli_admin_param.id)], limit=1)
        if not admin_val:
            admin_val = self.RuleParameterValue.create({
                'parameter_id': edli_admin_param.id,
                'date_from': '2014-09-01',
                'parameter_value': '0.01',
            })
        else:
            admin_val.parameter_value = '0.01'

        emp_admin, adapter_admin = self._create_employee_and_adapter('Emp_Admin', wage=60000.0, basis='actual_pf_wage', is_iw=True)
        # Wage capped at 25,000 * 0.0001 = 2.5 -> rounded statutory = 3.0
        admin_contrib = self.epf_svc.compute_edli_admin(adapter_admin)
        self.assertEqual(admin_contrib, 3.0, "EDLI admin must also cap wage at ₹25k (25k * 0.0001 = 2.5 -> rounds to 3.0)")

    def test_11_payslip_localdict_capping(self):
        """
        Verify that payslip with localdict evaluation also strictly caps EDLI at ceiling.
        """
        self.edli_ceiling_val.parameter_value = '25000'
        emp = self.Employee.create({
            'name': 'Emp_Payslip_Localdict',
            'company_id': self.env.company.id,
            'hds_in_epf_applicable': True,
            'hds_in_pf_contribution_basis': 'actual_pf_wage',
            'hds_in_is_international_worker': True,
        })
        payslip = self.env['hr.payslip'].create({
            'name': 'Slip Test Localdict',
            'employee_id': emp.id,
            'struct_id': self.struct_base.id,
            'company_id': self.env.company.id,
            'date_from': '2026-04-01',
            'date_to': '2026-04-30',
        })
        svc_ld = EPFService(self.env, localdict={'PF_WAGE': 75000.0})
        edli_res = svc_ld.compute_employer_edli(payslip)
        self.assertEqual(edli_res, 125.0, "Payslip in-flight localdict must strictly cap ₹75k to ₹25k -> ₹125.0")
