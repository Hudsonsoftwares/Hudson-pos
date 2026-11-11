# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests import common


class TestEpfMasterToggle(common.TransactionCase):
    """
    Test suite verifying that 'EPF Applicable' acts as the single master toggle
    across both Company and Employee levels, guaranteeing:
    1. Zero downstream calculations across all 6 statutory EPF lines when disabled.
    2. Zero reflection on payslips (no lines generated).
    3. Proper synchronization and onchange behaviors on Company and Employee.
    """

    def setUp(self):
        super().setUp()
        self.Company = self.env['res.company']
        self.Employee = self.env['hr.employee']
        self.Payslip = self.env['hr.payslip']
        self.Structure = self.env.ref('hudson_payroll_base.structure_base')
        self.SalaryRule = self.env['hr.salary.rule']
        self.Category = self.env['hr.salary.rule.category']
        self.RuleParameter = self.env['hr.rule.parameter']
        self.RuleParameterValue = self.env['hr.rule.parameter.value']

        category_alw = self.Category.search([], limit=1)

        # Ensure BASIC rule exists and contributes to PF Wage
        self.rule_basic = self.SalaryRule.search([('code', '=', 'BASIC'), ('struct_id', '=', self.Structure.id)], limit=1)
        if not self.rule_basic:
            self.rule_basic = self.SalaryRule.create({
                'name': 'Basic Salary',
                'code': 'BASIC',
                'category_id': category_alw.id,
                'struct_id': self.Structure.id,
                'hds_in_include_in_pf_wage': True,
            })
        self.rule_basic.write({'hds_in_include_in_pf_wage': True})

        # Ensure DA rule exists and contributes to PF Wage
        self.rule_da = self.SalaryRule.search([('code', '=', 'DA'), ('struct_id', '=', self.Structure.id)], limit=1)
        if not self.rule_da:
            self.rule_da = self.SalaryRule.create({
                'name': 'Dearness Allowance',
                'code': 'DA',
                'category_id': category_alw.id,
                'struct_id': self.Structure.id,
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

        # Company with EPF enabled
        self.company_epf = self.env.company
        self.company_epf.write({
            'hds_in_epf_applicable': True,
            'hds_in_epf_employer_id': 'GJ/BAN/0000006/000/0000001',
        })

        # Company with EPF disabled
        self.company_no_epf = self.Company.create({
            'name': 'Exempt Private Limited',
            'hds_in_epf_applicable': False,
        })

    def _create_employee_and_payslip(self, name, company, epf_applicable=True, basic=30000.0, da=5000.0):
        emp = self.Employee.create({
            'name': name,
            'company_id': company.id,
            'hds_in_epf_applicable': epf_applicable,
            'hds_in_eps_applicable': True,
            'hds_in_pf_contribution_basis': 'statutory_ceiling',
            'hds_in_pf_employer_basis': 'statutory_ceiling',
        })
        contract = emp.version_id
        if contract:
            contract.write({
                'wage': basic + da,
                'basic_salary': basic,
                'da': da,
                'struct_id': self.Structure.id,
                'date_start': '2026-04-01',
            })
        payslip = self.Payslip.create({
            'name': f'Payslip {name}',
            'employee_id': emp.id,
            'company_id': company.id,
            'contract_id': contract.id if contract else False,
            'struct_id': self.Structure.id,
            'date_from': '2026-04-01',
            'date_to': '2026-04-30',
        })
        return emp, contract, payslip

    def test_01_company_master_toggle_disabled_evaluates_all_to_zero(self):
        """When Company EPF Applicable is False, all 6 statutory components evaluate to 0.0."""
        emp, contract, payslip = self._create_employee_and_payslip(
            'Emp_Company_Disabled', self.company_no_epf, epf_applicable=True
        )

        ee_epf = payslip.hds_in_compute_employee_epf(localdict={})
        er_epf = payslip.hds_in_compute_employer_epf(localdict={})
        eps = payslip.env['epf.service'].pension_calc.compute(payslip) if 'epf.service' in self.env else 0.0
        # pyrefly: ignore [missing-import]
        from odoo.addons.hudson_in_payroll.services.epf.epf_service import EPFService
        epf_service = EPFService(self.env)
        eps = epf_service.pension_calc.compute(payslip)
        epf_share = payslip.hds_in_compute_employer_epf_share(localdict={})
        edli = epf_service.employer_calc.compute_edli(payslip)
        epf_admin = epf_service.employer_calc.compute_epf_admin(payslip)
        edli_admin = epf_service.employer_calc.compute_edli_admin(payslip)

        self.assertEqual(ee_epf, 0.0, "Employee EPF must evaluate to 0.0 when company EPF is disabled")
        self.assertEqual(er_epf, 0.0, "Employer Total EPF must evaluate to 0.0 when company EPF is disabled")
        self.assertEqual(eps, 0.0, "Employer EPS must evaluate to 0.0 when company EPF is disabled")
        self.assertEqual(epf_share, 0.0, "Employer EPF Share must evaluate to 0.0 when company EPF is disabled")
        self.assertEqual(edli, 0.0, "EDLI must evaluate to 0.0 when company EPF is disabled")
        self.assertEqual(epf_admin, 0.0, "EPF Admin Charges must evaluate to 0.0 when company EPF is disabled")
        self.assertEqual(edli_admin, 0.0, "EDLI Admin Charges must evaluate to 0.0 when company EPF is disabled")

        # Payslip evaluation: rule condition prevents lines from reflecting
        payslip.compute_sheet()
        rule_codes = {l.code for l in payslip.line_ids}
        pf_codes = {'EPF', 'EMPLOYER_EPF', 'EPS', 'EPF_SHARE', 'EDLI', 'EPF_ADMIN', 'EDLI_ADMIN'}
        self.assertFalse(rule_codes.intersection(pf_codes), "No PF rules should appear on payslip when company EPF is disabled")

    def test_02_employee_master_toggle_disabled_evaluates_all_to_zero(self):
        """When Employee EPF Applicable is False, all 6 statutory components evaluate to 0.0."""
        emp, contract, payslip = self._create_employee_and_payslip(
            'Emp_Employee_Disabled', self.company_epf, epf_applicable=False
        )

        # pyrefly: ignore [missing-import]
        from odoo.addons.hudson_in_payroll.services.epf.epf_service import EPFService
        epf_service = EPFService(self.env)

        ee_epf = payslip.hds_in_compute_employee_epf(localdict={})
        er_epf = payslip.hds_in_compute_employer_epf(localdict={})
        eps = epf_service.pension_calc.compute(payslip)
        epf_share = payslip.hds_in_compute_employer_epf_share(localdict={})
        edli = epf_service.employer_calc.compute_edli(payslip)
        epf_admin = epf_service.employer_calc.compute_epf_admin(payslip)
        edli_admin = epf_service.employer_calc.compute_edli_admin(payslip)

        self.assertEqual(ee_epf, 0.0, "Employee EPF must evaluate to 0.0 when employee EPF is disabled")
        self.assertEqual(er_epf, 0.0, "Employer Total EPF must evaluate to 0.0 when employee EPF is disabled")
        self.assertEqual(eps, 0.0, "Employer EPS must evaluate to 0.0 when employee EPF is disabled")
        self.assertEqual(epf_share, 0.0, "Employer EPF Share must evaluate to 0.0 when employee EPF is disabled")
        self.assertEqual(edli, 0.0, "EDLI must evaluate to 0.0 when employee EPF is disabled")
        self.assertEqual(epf_admin, 0.0, "EPF Admin Charges must evaluate to 0.0 when employee EPF is disabled")
        self.assertEqual(edli_admin, 0.0, "EDLI Admin Charges must evaluate to 0.0 when employee EPF is disabled")

        # Payslip evaluation: rule condition prevents lines from reflecting
        payslip.compute_sheet()
        rule_codes = {l.code for l in payslip.line_ids}
        pf_codes = {'EPF', 'EMPLOYER_EPF', 'EPS', 'EPF_SHARE', 'EDLI', 'EPF_ADMIN', 'EDLI_ADMIN'}
        self.assertFalse(rule_codes.intersection(pf_codes), "No PF rules should appear on payslip when employee EPF is disabled")

    def test_03_both_toggles_enabled_computes_standard_statutory(self):
        """When both toggles are True, statutory PF computes and reflects properly."""
        emp, contract, payslip = self._create_employee_and_payslip(
            'Emp_Both_Enabled', self.company_epf, epf_applicable=True, basic=15000.0, da=0.0
        )

        # pyrefly: ignore [missing-import]
        from odoo.addons.hudson_in_payroll.services.epf.epf_service import EPFService
        localdict = {'rules': {'BASIC': {'total': 15000.0}}}
        epf_service = EPFService(self.env, localdict=localdict)

        ee_epf = abs(payslip.hds_in_compute_employee_epf(localdict=localdict))
        er_epf = payslip.hds_in_compute_employer_epf(localdict=localdict)
        eps = epf_service.pension_calc.compute(payslip)
        epf_share = payslip.hds_in_compute_employer_epf_share(localdict=localdict)
        edli = epf_service.employer_calc.compute_edli(payslip)
        epf_admin = epf_service.employer_calc.compute_epf_admin(payslip)

        # ₹15,000 * 12% = ₹1,800
        self.assertEqual(ee_epf, 1800.0, "Employee EPF should be 12% of ₹15,000 = ₹1,800")
        self.assertEqual(er_epf, 1800.0, "Employer Total EPF should be 12% of ₹15,000 = ₹1,800")
        # ₹15,000 * 8.33% = ₹1,250
        self.assertEqual(eps, 1250.0, "Employer EPS should be ₹1,250")
        # ₹1,800 - ₹1,250 = ₹550
        self.assertEqual(epf_share, 550.0, "Employer EPF Share should be ₹550")
        # ₹15,000 * 0.5% = ₹75
        self.assertEqual(edli, 75.0, "EDLI should be 0.5% = ₹75")
        self.assertEqual(epf_admin, 75.0, "EPF Admin Charges should be 0.5% = ₹75")

    def test_04_company_sync_and_employee_onchange(self):
        """Verify onchange and model sync hooks."""
        comp = self.Company.create({'name': 'Sync Test Comp 2', 'hds_in_epf_applicable': True})
        self.assertTrue(comp.hds_in_eps_applicable)
        self.assertTrue(comp.hds_in_edli_applicable)

        comp.write({'hds_in_epf_applicable': False})
        self.assertFalse(comp.hds_in_eps_applicable)
        self.assertFalse(comp.hds_in_edli_applicable)

        emp = self.Employee.create({
            'name': 'Onchange Test Emp',
            'hds_in_epf_applicable': True,
            'hds_in_eps_applicable': True,
        })
        emp.hds_in_epf_applicable = False
        emp._onchange_hds_in_epf_applicable()
        self.assertFalse(emp.hds_in_eps_applicable)
