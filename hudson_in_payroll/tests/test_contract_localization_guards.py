# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.fields import Date


class TestContractLocalizationGuards(TransactionCase):

    def setUp(self):
        super().setUp()
        self.SalaryRule = self.env['hr.salary.rule']
        self.Contract = self.env['hr.version']
        self.Employee = self.env['hr.employee']
        self.Company = self.env['res.company']

        self.country_in = self.env.ref('base.in')
        self.country_ae = self.env.ref('base.ae')

        # 1. India Company Setup
        self.company_in = self.Company.create({
            'name': 'India Tech Solutions Pvt Ltd',
            'country_id': self.country_in.id,
            'hds_in_epf_applicable': True,
            'hds_in_esic_applicable': True,
        })

        # 2. UAE Company Setup
        self.company_ae = self.Company.create({
            'name': 'Gulf Innovations LLC',
            'country_id': self.country_ae.id,
        })

        self.structure_base = self.env.ref('hudson_payroll_base.structure_base')

        # India Employee & Contract
        self.emp_in = self.Employee.create({
            'name': 'Ramesh Kumar',
            'company_id': self.company_in.id,
        })
        self.contract_in = self.Contract.create({
            'name': 'Contract - Ramesh Kumar (IN)',
            'employee_id': self.emp_in.id,
            'company_id': self.company_in.id,
            'wage': 15000.0,
            'basic_salary': 7500.0,
            'hra': 3000.0,
            'da': 1500.0,
            'travel_allowance': 1000.0,
            'fixed_allowance': 2000.0,
            'struct_id': self.structure_base.id,
        })

        # UAE Employee & Contract
        self.emp_ae = self.Employee.create({
            'name': 'Tariq Al-Mansoor',
            'company_id': self.company_ae.id,
        })
        self.contract_ae = self.Contract.create({
            'name': 'Contract - Tariq Al-Mansoor (AE)',
            'employee_id': self.emp_ae.id,
            'company_id': self.company_ae.id,
            'wage': 15000.0,
            'basic_salary': 9000.0,
            'hra': 4500.0,
            'travel_allowance': 1500.0,
            'struct_id': self.structure_base.id,
        })

    def test_01_centralized_localization_detection(self):
        """Verify centralized _is_india_localization cleanly resolves India vs UAE contracts."""
        self.assertTrue(self.company_in.hds_in_is_india_company)
        self.assertFalse(self.company_ae.hds_in_is_india_company)

        self.assertTrue(self.contract_in._is_india_localization())
        self.assertFalse(self.contract_ae._is_india_localization())

    def test_02_india_contract_computes_employer_ctc_and_syncs_esic(self):
        """Verify India contracts execute Indian employer cost (CTC) and ESIC synchronization."""
        self.contract_in._compute_employer_cost()

        # Monthly CTC must be greater than wage (15,000 + employer PF/EDLI/Admin)
        self.assertGreater(self.contract_in.hds_in_employer_cost_monthly, 15000.0)
        self.assertEqual(
            self.contract_in.hds_in_employer_cost_annual,
            self.contract_in.hds_in_employer_cost_monthly * 12.0
        )
        self.assertEqual(
            self.emp_in.hds_in_employer_cost_annual,
            self.contract_in.hds_in_employer_cost_annual
        )

        # ESIC should be evaluated and set for Indian employee earning <= 21,000
        self.assertTrue(self.emp_in.hds_in_esic_applicable)

    def test_03_uae_contract_does_not_execute_indian_statutory_computations(self):
        """Verify UAE contracts never execute Indian statutory CTC and ESIC computations."""
        # 1. Employer cost on UAE contract must evaluate to 0.0
        self.assertEqual(self.contract_ae.hds_in_employer_cost_monthly, 0.0)
        self.assertEqual(self.contract_ae.hds_in_employer_cost_annual, 0.0)
        self.assertEqual(self.emp_ae.hds_in_employer_cost_monthly, 0.0)
        self.assertEqual(self.emp_ae.hds_in_employer_cost_annual, 0.0)

        # 2. ESIC applicability on UAE employee must NOT be enabled
        self.assertFalse(self.emp_ae.hds_in_esic_applicable)

        # 3. Direct statutory rule estimation helper must return 0.0
        rule_epf_er = self.env.ref('hudson_in_payroll.hds_in_rule_epf_er', raise_if_not_found=False)
        if rule_epf_er:
            estimated_pf = self.contract_ae._estimate_statutory_rule_amount(self.contract_ae, rule_epf_er)
            self.assertEqual(estimated_pf, 0.0)

        # 4. Wage update onchange must NOT trigger ESIC on UAE employee
        self.contract_ae.wage = 18000.0
        self.contract_ae._onchange_wage_sync_esic()
        self.assertFalse(self.emp_ae.hds_in_esic_applicable)

        # 5. Contract write must keep employer cost at 0.0 and avoid ESIC
        self.contract_ae.write({'wage': 20000.0, 'basic_salary': 12000.0})
        self.assertEqual(self.contract_ae.hds_in_employer_cost_monthly, 0.0)
        self.assertEqual(self.contract_ae.hds_in_employer_cost_annual, 0.0)
        self.assertFalse(self.emp_ae.hds_in_esic_applicable)

    def test_04_uae_contract_template_does_not_execute_indian_ctc(self):
        """Verify UAE contract template creation and onchange loading does not compute Indian CTC."""
        tmpl_ae = self.Contract.create({
            'name': 'UAE Senior Engineer Template',
            'company_id': self.company_ae.id,
            'wage': 30000.0,
            'struct_id': self.structure_base.id,
        })
        self.assertFalse(tmpl_ae._is_india_localization())
        self.assertEqual(tmpl_ae.hds_in_employer_cost_monthly, 0.0)
        self.assertEqual(tmpl_ae.hds_in_employer_cost_annual, 0.0)

        # New contract loading this UAE template
        new_contract = self.Contract.create({
            'name': 'Contract - New UAE Hire',
            'employee_id': self.emp_ae.id,
            'company_id': self.company_ae.id,
            'contract_template_id': tmpl_ae.id,
        })
        new_contract._onchange_contract_template_id()
        self.assertEqual(new_contract.hds_in_employer_cost_monthly, 0.0)
        self.assertEqual(new_contract.hds_in_employer_cost_annual, 0.0)

    def test_05_generic_salary_breakdown_works_for_both_india_and_uae(self):
        """Verify generic salary calculations and validations (breakdown totals & diffs) work identically for both."""
        # Check India contract generic breakdown
        self.assertEqual(self.contract_in.breakdown_total, 15000.0)
        self.assertEqual(self.contract_in.breakdown_diff, 0.0)
        self.assertTrue(self.contract_in.breakdown_is_equal)
        self.assertEqual(self.contract_in.basic_salary_percent, 50.0)
        self.assertEqual(self.contract_in.hra_percent, 20.0)

        # Check UAE contract generic breakdown
        self.assertEqual(self.contract_ae.breakdown_total, 15000.0)
        self.assertEqual(self.contract_ae.breakdown_diff, 0.0)
        self.assertTrue(self.contract_ae.breakdown_is_equal)
        self.assertEqual(self.contract_ae.basic_salary_percent, 60.0)
        self.assertEqual(self.contract_ae.hra_percent, 30.0)
        self.assertEqual(self.contract_ae.travel_allowance_percent, 10.0)
