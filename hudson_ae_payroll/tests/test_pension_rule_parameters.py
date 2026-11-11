# -*- coding: utf-8 -*-
from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestUAEPensionRuleParameters(common.TransactionCase):

    def setUp(self):
        super(TestUAEPensionRuleParameters, self).setUp()
        self.param_model = self.env['hr.rule.parameter']

    def test_01_gpssa_parameters_loaded_in_rule_parameters(self):
        """GPSSA parameters exist with historical versions in hr.rule.parameter."""
        gpssa_ee = self.env.ref('hudson_ae_payroll.hds_ae_gpssa_ee_rate')
        self.assertEqual(gpssa_ee.category, 'uae_gpssa')
        self.assertEqual(gpssa_ee.code, 'hds_ae_gpssa_ee_rate')
        # At least 2 effective-dated versions: 1999 (5.0%) and 2023 (11.0%)
        self.assertTrue(len(gpssa_ee.parameter_version_ids) >= 2)

        gpssa_max = self.env.ref('hudson_ae_payroll.hds_ae_gpssa_max_wage')
        self.assertEqual(gpssa_max.category, 'uae_gpssa')
        self.assertTrue(len(gpssa_max.parameter_version_ids) >= 2)

        gpssa_threshold = self.env.ref('hudson_ae_payroll.hds_ae_gpssa_subsidy_wage_threshold')
        self.assertEqual(gpssa_threshold.category, 'uae_gpssa')
        self.assertEqual(float(gpssa_threshold.current_value), 20000.0)

    def test_02_adpf_parameters_loaded_in_rule_parameters(self):
        """ADPF parameters exist with uae_adpf category in hr.rule.parameter."""
        adpf_ee = self.env.ref('hudson_ae_payroll.hds_ae_adpf_ee_rate')
        self.assertEqual(adpf_ee.category, 'uae_adpf')
        self.assertTrue(len(adpf_ee.parameter_version_ids) >= 2)

        adpf_er = self.env.ref('hudson_ae_payroll.hds_ae_adpf_er_rate')
        self.assertEqual(float(adpf_er.current_value), 15.0)

        adpf_max = self.env.ref('hudson_ae_payroll.hds_ae_adpf_max_wage')
        self.assertEqual(float(adpf_max.current_value), 60000.0)

    def test_03_gcc_parameters_loaded_with_caps_and_shortfall(self):
        """GCC National scheme parameters exist with rates, employer cap, and shortfall absorption."""
        gosi_ee = self.env.ref('hudson_ae_payroll.hds_gcc_sa_ee_rate')
        self.assertEqual(gosi_ee.category, 'gcc_pension')
        self.assertEqual(float(gosi_ee.current_value), 9.0)

        gosi_cap = self.env.ref('hudson_ae_payroll.hds_gcc_sa_er_cap')
        self.assertEqual(float(gosi_cap.current_value), 12.5)

        gosi_shortfall = self.env.ref('hudson_ae_payroll.hds_gcc_sa_absorb_shortfall')
        self.assertEqual(gosi_shortfall.current_value, 'True')

    def test_04_date_driven_gpssa_cutover_resolution(self):
        """
        Pure date-driven resolution for GPSSA:
        Payslip date 2022-06-01 -> Law 7/1999 (5% EE, 12.5% ER, 2.5% subsidy, 50,000 AED cap)
        Payslip date 2024-01-15 -> Decree-Law 57/2023 (11% EE, 12.5% ER, 2.5% subsidy, 70,000 AED cap)
        Zero hardcoded cutover dates in Python.
        """
        # Pre-cutover payslip date
        rates_pre = self.param_model.resolve_uae_pension_rates(
            authority_code='GPSSA',
            date='2022-06-01'
        )
        self.assertEqual(rates_pre['employee_rate'], 5.0)
        self.assertEqual(rates_pre['employer_rate'], 12.5)
        self.assertEqual(rates_pre['subsidy_rate'], 2.5)
        self.assertEqual(rates_pre['total_rate'], 20.0)
        self.assertEqual(rates_pre['max_wage_limit'], 50000.0)
        self.assertEqual(rates_pre['min_wage_limit'], 1000.0)

        # Post-cutover payslip date
        rates_post = self.param_model.resolve_uae_pension_rates(
            authority_code='GPSSA',
            date='2024-01-15'
        )
        self.assertEqual(rates_post['employee_rate'], 11.0)
        self.assertEqual(rates_post['employer_rate'], 12.5)
        self.assertEqual(rates_post['subsidy_rate'], 2.5)
        self.assertEqual(rates_post['subsidy_wage_threshold'], 20000.0)
        self.assertEqual(rates_post['total_rate'], 26.0)
        self.assertEqual(rates_post['max_wage_limit'], 70000.0)
        self.assertEqual(rates_post['min_wage_limit'], 3000.0)

        # Post-cutover with decimal conversion
        rates_post_dec = self.param_model.resolve_uae_pension_rates(
            authority_code='GPSSA',
            date='2024-01-15',
            as_decimal=True
        )
        self.assertAlmostEqual(rates_post_dec['employee_rate'], 0.11)
        self.assertAlmostEqual(rates_post_dec['employer_rate'], 0.125)
        self.assertAlmostEqual(rates_post_dec['subsidy_rate'], 0.025)
        self.assertAlmostEqual(rates_post_dec['total_rate'], 0.26)

    def test_05_date_driven_adpf_cutover_resolution(self):
        """
        Pure date-driven resolution for ADPF independent of GPSSA:
        Payslip date 2022-06-01 -> 9% EE, 15% ER, 60k max wage
        Payslip date 2024-01-15 -> 11% EE, 15% ER, 60k max wage
        """
        rates_pre = self.param_model.resolve_uae_pension_rates(
            authority_code='ADPF',
            date='2022-06-01'
        )
        self.assertEqual(rates_pre['employee_rate'], 9.0)
        self.assertEqual(rates_pre['employer_rate'], 15.0)
        self.assertEqual(rates_pre['max_wage_limit'], 60000.0)

        rates_post = self.param_model.resolve_uae_pension_rates(
            authority_code='ADPF',
            date='2024-01-15'
        )
        self.assertEqual(rates_post['employee_rate'], 11.0)
        self.assertEqual(rates_post['employer_rate'], 15.0)
        self.assertEqual(rates_post['max_wage_limit'], 60000.0)

    def test_06_configurable_gcc_pension_rates(self):
        """
        Resolves configurable parameters for GCC Social Security Extension Scheme:
        Employee Rate, Employer Rate, Employer Contribution Cap, Shortfall Absorption Flag, Wage Ceiling.
        """
        # KSA GOSI
        rates_sa = self.param_model.resolve_gcc_pension_rates('SA', date='2024-01-15')
        self.assertEqual(rates_sa['country_code'], 'SA')
        self.assertEqual(rates_sa['employee_rate'], 9.0)
        self.assertEqual(rates_sa['employer_rate'], 9.0)
        self.assertEqual(rates_sa['employer_cap'], 12.5)
        self.assertTrue(rates_sa['absorb_shortfall'])
        self.assertEqual(rates_sa['max_wage_limit'], 45000.0)
        self.assertEqual(rates_sa['total_rate'], 18.0)

        # Decimal format
        rates_sa_dec = self.param_model.resolve_gcc_pension_rates('SA', date='2024-01-15', as_decimal=True)
        self.assertAlmostEqual(rates_sa_dec['employee_rate'], 0.09)
        self.assertAlmostEqual(rates_sa_dec['employer_rate'], 0.09)
        self.assertAlmostEqual(rates_sa_dec['employer_cap'], 0.125)
        self.assertTrue(rates_sa_dec['absorb_shortfall'])

        # Kuwait PIFSS
        rates_kw = self.param_model.resolve_gcc_pension_rates('KW', date='2024-01-15')
        self.assertEqual(rates_kw['employee_rate'], 8.0)
        self.assertEqual(rates_kw['employer_rate'], 11.5)
        self.assertEqual(rates_kw['employer_cap'], 12.5)
        self.assertTrue(rates_kw['absorb_shortfall'])
        self.assertEqual(rates_kw['max_wage_limit'], 3000.0)

    def test_07_concurrent_legacy_and_new_law_cohorts_resolution(self):
        """
        Verify that Legacy and New Law cohorts can coexist simultaneously on the exact same date.
        On 2026-09-01:
        - Employee A under Legacy Scheme gets Law 7/1999 rates (5% EE, 50k max wage)
        - Employee B under New Law Scheme gets Decree-Law 57/2023 rates (11% EE, 70k max wage)
        """
        eval_date = '2026-09-01'
        legacy_scheme = self.env.ref('hudson_ae_payroll.pension_scheme_legacy')
        new_law_scheme = self.env.ref('hudson_ae_payroll.pension_scheme_new_law')

        # 1. GPSSA Legacy Scheme (passed as record)
        rates_gpssa_legacy = self.param_model.resolve_uae_pension_rates(
            authority_code='GPSSA',
            scheme_code=legacy_scheme,
            date=eval_date
        )
        self.assertEqual(rates_gpssa_legacy['scheme'], 'legacy')
        self.assertEqual(rates_gpssa_legacy['employee_rate'], 5.0)
        self.assertEqual(rates_gpssa_legacy['employer_rate'], 12.5)
        self.assertEqual(rates_gpssa_legacy['subsidy_rate'], 2.5)
        self.assertEqual(rates_gpssa_legacy['subsidy_wage_threshold'], 20000.0)
        self.assertEqual(rates_gpssa_legacy['max_wage_limit'], 50000.0)
        self.assertEqual(rates_gpssa_legacy['min_wage_limit'], 1000.0)

        # 2. GPSSA New Law Scheme (passed as string code)
        rates_gpssa_new = self.param_model.resolve_uae_pension_rates(
            authority_code='GPSSA',
            scheme_code='new_law',
            date=eval_date
        )
        self.assertEqual(rates_gpssa_new['scheme'], 'new_law')
        self.assertEqual(rates_gpssa_new['employee_rate'], 11.0)
        self.assertEqual(rates_gpssa_new['employer_rate'], 12.5)
        self.assertEqual(rates_gpssa_new['subsidy_rate'], 2.5)
        self.assertEqual(rates_gpssa_new['subsidy_wage_threshold'], 20000.0)
        self.assertEqual(rates_gpssa_new['max_wage_limit'], 70000.0)
        self.assertEqual(rates_gpssa_new['min_wage_limit'], 3000.0)

        # 3. ADPF Legacy Scheme on 2026-09-01
        rates_adpf_legacy = self.param_model.resolve_uae_pension_rates(
            authority_code='ADPF',
            scheme_code='legacy',
            date=eval_date
        )
        self.assertEqual(rates_adpf_legacy['scheme'], 'legacy')
        self.assertEqual(rates_adpf_legacy['employee_rate'], 9.0)
        self.assertEqual(rates_adpf_legacy['employer_rate'], 15.0)
        self.assertEqual(rates_adpf_legacy['max_wage_limit'], 60000.0)

        # 4. ADPF New Law Scheme on 2026-09-01
        rates_adpf_new = self.param_model.resolve_uae_pension_rates(
            authority_code='ADPF',
            scheme_code='new_law',
            date=eval_date
        )
        self.assertEqual(rates_adpf_new['scheme'], 'new_law')
        self.assertEqual(rates_adpf_new['employee_rate'], 11.0)
        self.assertEqual(rates_adpf_new['employer_rate'], 15.0)
        self.assertEqual(rates_adpf_new['max_wage_limit'], 60000.0)

    def test_08_pension_scheme_master_and_company_configuration(self):
        """
        Verify Pension Scheme master configuration and multi-cohort coexistence at employee level.
        """
        legacy = self.env.ref('hudson_ae_payroll.pension_scheme_legacy')
        new_law = self.env.ref('hudson_ae_payroll.pension_scheme_new_law')
        self.assertTrue(legacy.active)
        self.assertTrue(new_law.active)

        # Company allows both schemes without forcing a single one
        company = self.env.company
        company.uae_pension_scheme_ids = [(6, 0, [legacy.id, new_law.id])]
        self.assertIn(legacy, company.uae_pension_scheme_ids)
        self.assertIn(new_law, company.uae_pension_scheme_ids)

        uae_country = self.env.ref('base.ae')
        emp_a = self.env['hr.employee'].create({
            'name': 'Employee A (Legacy Cohort)',
            'country_id': uae_country.id,
            'uae_pension_scheme_id': legacy.id,
        })
        emp_b = self.env['hr.employee'].create({
            'name': 'Employee B (New Law Cohort)',
            'country_id': uae_country.id,
            'uae_pension_scheme_id': new_law.id,
        })

        self.assertEqual(emp_a.uae_pension_scheme_id.code, 'legacy')
        self.assertEqual(emp_b.uae_pension_scheme_id.code, 'new_law')
