# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo import fields


class TestTdsWageThresholdOnchange(TransactionCase):

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        super().setUp()
        self.env.company.write({'hds_in_tds_applicable': True})
        self.employee = self.env['hr.employee'].create({
            'name': 'Threshold Test Employee',
            'hds_in_tds_applicable': False,
        })

    def test_01_wage_below_threshold_does_not_trigger_tds(self):
        """Monthly wage of 1,00,000 (Annual 12L) is <= 12.75L threshold: no warning, TDS remains False."""
        contract = self.env['hr.version'].new({
            'name': 'Contract Below Threshold',
            'employee_id': self.employee.id,
            'wage': 100000.0,
            'hds_in_tds_applicable': False,
            'is_india_localization': True,
        })
        warn = contract._onchange_wage_check_tds_threshold()
        self.assertFalse(warn, "No warning should be triggered when wage is below the zero-tax threshold.")
        self.assertFalse(contract.hds_in_tds_applicable, "TDS should remain disabled.")

    def test_02_wage_above_threshold_triggers_tds_and_warning(self):
        """Monthly wage of 1,10,000 (Annual 13.2L) exceeds 12.75L threshold: warning returned, TDS enabled."""
        contract = self.env['hr.version'].new({
            'name': 'Contract Above Threshold',
            'employee_id': self.employee.id,
            'wage': 110000.0,
            'hds_in_tds_applicable': False,
            'is_india_localization': True,
        })
        warn = contract._onchange_wage_check_tds_threshold()
        self.assertTrue(warn, "Warning modal must be returned when wage exceeds threshold.")
        self.assertIn('warning', warn)
        self.assertTrue(contract.hds_in_tds_applicable, "TDS must be automatically selected.")
        self.assertIn("Statutory TDS Notice", warn['warning']['title'])

    def test_03_wage_above_threshold_when_already_enabled_no_warning(self):
        """When TDS is already enabled on contract, no redundant warning popup is shown."""
        contract = self.env['hr.version'].new({
            'name': 'Contract Already Enabled',
            'employee_id': self.employee.id,
            'wage': 110000.0,
            'hds_in_tds_applicable': True,
            'is_india_localization': True,
        })
        warn = contract._onchange_wage_check_tds_threshold()
        self.assertFalse(warn, "Should not produce repeated warnings when TDS is already checked.")

    def test_04_statutory_refresh_service_on_salary_revision(self):
        """Salary revision crossing threshold automatically enables TDS on employee."""
        emp = self.env['hr.employee'].create({
            'name': 'Revision Test Employee',
            'hds_in_tds_applicable': False,
        })
        from odoo.addons.hudson_in_payroll.services.revision.statutory_refresh_service import StatutoryRefreshService
        svc = StatutoryRefreshService(self.env)
        self.assertFalse(emp.hds_in_tds_applicable)
        svc.refresh_statutory_components(emp, new_wage=120000.0)
        self.assertTrue(emp.hds_in_tds_applicable, "TDS must be enabled after salary revision exceeds threshold.")

    def test_05_employee_form_wage_triggers_popup(self):
        """Entering monthly wage 120,000 on hr.employee form triggers TDS warning and enables TDS."""
        emp = self.env['hr.employee'].new({
            'name': 'Form Employee Wage Test',
            'wage': 120000.0,
            'hds_in_tds_applicable': False,
        })
        warn = emp._onchange_wage_check_tds_threshold()
        self.assertTrue(warn, "Warning modal must be returned on hr.employee when wage exceeds threshold.")
        self.assertIn('warning', warn)
        self.assertTrue(emp.hds_in_tds_applicable, "TDS must be checked on hr.employee.")

    def test_06_employee_form_basic_salary_triggers_popup(self):
        """Entering basic_salary 120,000 on hr.employee form triggers TDS warning and enables TDS."""
        emp = self.env['hr.employee'].new({
            'name': 'Form Employee Basic Salary Test',
            'basic_salary': 120000.0,
            'hds_in_tds_applicable': False,
        })
        warn = emp._onchange_wage_check_tds_threshold()
        self.assertTrue(warn, "Warning modal must be returned on hr.employee when basic_salary exceeds threshold.")
        self.assertIn('warning', warn)
        self.assertTrue(emp.hds_in_tds_applicable, "TDS must be checked on hr.employee.")
