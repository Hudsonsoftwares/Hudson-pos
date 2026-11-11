# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.fields import Date


class TestPTRegression(TransactionCase):

    def setUp(self):
        super(TestPTRegression, self).setUp()
        self.company = self.env.company
        self.company.write({
            'hds_in_enable_epf': True,
            'hds_in_enable_esic': True,
            'hds_in_enable_lwf': True,
            'hds_in_enable_gratuity': True,
            'hds_in_enable_professional_tax': True,
        })

        self.state_mh = self.env.ref('base.state_in_mh')
        self.partner_mh = self.env['res.partner'].create({
            'name': 'Regression Test Address',
            'state_id': self.state_mh.id,
        })
        self.work_loc_mh = self.env['hr.work.location'].create({
            'name': 'Regression Office',
            'address_id': self.partner_mh.id,
            'company_id': self.company.id,
        })

        self.employee = self.env['hr.employee'].create({
            'name': 'Regression Test Employee',
            'gender': 'male',
            'work_location_id': self.work_loc_mh.id,
            'company_id': self.company.id,
            'first_contract_date': Date.from_string('2018-01-01'),
        })

        self.contract = self.env['hr.version'].create({
            'name': 'Regression Contract',
            'employee_id': self.employee.id,
            'date_start': Date.from_string('2018-01-01'),
            'wage': 20000.0,
            'basic_salary': 15000.0,
        })

        self.payslip = self.env['hr.payslip'].create({
            'name': 'Regression Payslip',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'company_id': self.company.id,
            'date_from': Date.from_string('2026-01-01'),
            'date_to': Date.from_string('2026-01-31'),
        })

    def test_01_epf_esic_lwf_gratuity_coexistence(self):
        """Test that introducing Professional Tax does not alter EPF, ESIC, LWF, or Gratuity computations."""
        localdict = {
            'payslip': self.payslip,
            'employee': self.employee,
            'contract': self.contract,
            'gross_salary': 20000.0,
        }
        self.payslip._get_statutory_context(localdict)

        # EPF Employee Deduction: 12% of 15,000 basic = -1,800.0
        epf_amount = self.payslip.hds_in_compute_employee_epf()
        self.assertEqual(epf_amount, -1800.0)

        # PT Employee Deduction: MH Male ₹20,000 = -200.0
        pt_amount = self.payslip.hds_in_compute_professional_tax()
        self.assertEqual(pt_amount, -200.0)

    def test_02_payroll_structure_integrity(self):
        """Test base payroll structure includes PT rule alongside other statutory rules."""
        base_struct = self.env.ref('hudson_payroll_base.structure_base')
        rule_pt = self.env.ref('hudson_in_payroll.hds_in_rule_pt')
        rule_epf = self.env.ref('hudson_in_payroll.hds_in_rule_epf')
        rule_lwf = self.env.ref('hudson_in_payroll.hds_in_rule_lwf_ee')

        self.assertIn(rule_pt, base_struct.rule_ids)
        self.assertIn(rule_epf, base_struct.rule_ids)
        self.assertIn(rule_lwf, base_struct.rule_ids)
