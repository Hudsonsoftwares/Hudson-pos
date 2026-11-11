# -*- coding: utf-8 -*-
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestUAEGPSSASalaryRule(common.TransactionCase):

    def setUp(self):
        super(TestUAEGPSSASalaryRule, self).setUp()
        self.category_alw = self.env.ref('hr_payroll_community.ALW', raise_if_not_found=False) or self.env['hr.salary.rule.category'].search([('code', '=', 'ALW')], limit=1)

    def test_01_default_gpssa_base_flag(self):
        """A new salary rule must default hds_ae_include_in_gpssa_base to False."""
        rule = self.env['hr.salary.rule'].create({
            'name': 'Test General Allowance',
            'code': 'TEST_GEN_ALW',
            'category_id': self.category_alw.id,
            'sequence': 50,
            'amount_select': 'fix',
            'amount_fix': 500.0,
        })
        self.assertFalse(rule.hds_ae_include_in_gpssa_base)

    def test_02_enable_gpssa_base_flag(self):
        """Setting hds_ae_include_in_gpssa_base to True persists correctly."""
        rule = self.env['hr.salary.rule'].create({
            'name': 'Test Housing Allowance',
            'code': 'TEST_HOU_ALW',
            'category_id': self.category_alw.id,
            'sequence': 20,
            'amount_select': 'fix',
            'amount_fix': 3000.0,
            'hds_ae_include_in_gpssa_base': True,
        })
        self.assertTrue(rule.hds_ae_include_in_gpssa_base)

        # Toggle back to False
        rule.write({'hds_ae_include_in_gpssa_base': False})
        self.assertFalse(rule.hds_ae_include_in_gpssa_base)

    def test_03_search_by_gpssa_base_flag(self):
        """ORM search correctly filters rules by hds_ae_include_in_gpssa_base."""
        rule1 = self.env['hr.salary.rule'].create({
            'name': 'Rule GPSSA Eligible',
            'code': 'RULE_GPSSA_YES',
            'category_id': self.category_alw.id,
            'sequence': 10,
            'amount_select': 'fix',
            'amount_fix': 1000.0,
            'hds_ae_include_in_gpssa_base': True,
        })
        rule2 = self.env['hr.salary.rule'].create({
            'name': 'Rule GPSSA Ineligible',
            'code': 'RULE_GPSSA_NO',
            'category_id': self.category_alw.id,
            'sequence': 11,
            'amount_select': 'fix',
            'amount_fix': 200.0,
            'hds_ae_include_in_gpssa_base': False,
        })
        matched_rules = self.env['hr.salary.rule'].search([('hds_ae_include_in_gpssa_base', '=', True)])
        self.assertIn(rule1, matched_rules)
        self.assertNotIn(rule2, matched_rules)
