# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.fields import Date


class TestPTSalaryRule(TransactionCase):

    def setUp(self):
        super(TestPTSalaryRule, self).setUp()
        self.company = self.env.company
        self.company.write({
            'hds_in_enable_professional_tax': True,
            'hds_in_professional_tax_registration_no': 'MH/PT/RULE/2026',
        })

        self.state_mh = self.env.ref('base.state_in_mh')
        self.partner_mh = self.env['res.partner'].create({
            'name': 'Mumbai Rule Test Partner',
            'state_id': self.state_mh.id,
        })
        self.work_loc_mh = self.env['hr.work.location'].create({
            'name': 'Mumbai Rule Office',
            'address_id': self.partner_mh.id,
            'company_id': self.company.id,
        })

        self.employee = self.env['hr.employee'].create({
            'name': 'PT Rule Test Employee',
            'gender': 'male',
            'work_location_id': self.work_loc_mh.id,
            'company_id': self.company.id,
        })

        self.contract = self.env['hr.version'].create({
            'name': 'PT Rule Contract',
            'employee_id': self.employee.id,
            'date_start': Date.from_string('2025-01-01'),
            'wage': 18000.0,
            'basic_salary': 18000.0,
        })

    def test_01_salary_rule_definition(self):
        """Test PT salary rule definition attributes in database."""
        rule = self.env.ref('hudson_in_payroll.hds_in_rule_pt')
        self.assertTrue(rule.id)
        self.assertEqual(rule.code, 'PT')
        self.assertEqual(rule.name, 'Professional Tax')
        self.assertEqual(rule.sequence, 165)
        self.assertEqual(rule.category_id, self.env.ref('hudson_payroll_base.rule_category_ded'))
        self.assertIn('hds_in_compute_professional_tax', rule.amount_python_compute)
        self.assertTrue(rule.appears_on_payslip)
        self.assertTrue(rule.active)

    def test_02_salary_rule_execution_in_payslip(self):
        """Test execution of PT salary rule during payslip computation (_get_payslip_lines)."""
        payslip_jan = self.env['hr.payslip'].create({
            'name': 'Jan Rule Payslip',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'company_id': self.company.id,
            'date_from': Date.from_string('2026-01-01'),
            'date_to': Date.from_string('2026-01-31'),
        })

        lines_jan = self.env['hr.payslip']._get_payslip_lines([self.contract.id], payslip_jan.id)
        pt_lines_jan = [l for l in lines_jan if l['code'] == 'PT']
        self.assertEqual(len(pt_lines_jan), 1)
        self.assertEqual(pt_lines_jan[0]['amount'], -200.0)

        # Test February override month
        payslip_feb = self.env['hr.payslip'].create({
            'name': 'Feb Rule Payslip',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'company_id': self.company.id,
            'date_from': Date.from_string('2026-02-01'),
            'date_to': Date.from_string('2026-02-28'),
        })

        lines_feb = self.env['hr.payslip']._get_payslip_lines([self.contract.id], payslip_feb.id)
        pt_lines_feb = [l for l in lines_feb if l['code'] == 'PT']
        self.assertEqual(len(pt_lines_feb), 1)
        self.assertEqual(pt_lines_feb[0]['amount'], -300.0)

    def test_03_salary_structure_membership(self):
        """Test PT salary rule membership in base salary structure."""
        base_struct = self.env.ref('hudson_payroll_base.structure_base')
        rule = self.env.ref('hudson_in_payroll.hds_in_rule_pt')
        self.assertIn(rule, base_struct.rule_ids)
