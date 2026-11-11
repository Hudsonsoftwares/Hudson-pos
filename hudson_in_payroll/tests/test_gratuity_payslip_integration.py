# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.fields import Date
from odoo.exceptions import UserError


class TestGratuityPayslipIntegration(TransactionCase):

    def setUp(self):
        super(TestGratuityPayslipIntegration, self).setUp()
        self.company = self.env['res.company'].create({
            'name': 'Gratuity Integration Company',
            'hds_in_enable_gratuity': True,
        })

        self.employee = self.env['hr.employee'].create({
            'name': 'Gratuity Integration Employee',
            'company_id': self.company.id,
            'first_contract_date': Date.from_string('2018-01-01'),
        })

        if self.employee.version_id:
            self.contract = self.employee.version_id
            self.contract.write({
                'name': 'Gratuity Integration Contract',
                'date_start': Date.from_string('2018-01-01'),
                'wage': 50000.0,
                'basic_salary': 40000.0,
                'da': 10000.0,
            })
        else:
            self.contract = self.env['hr.version'].create({
                'name': 'Gratuity Integration Contract',
                'employee_id': self.employee.id,
                'date_start': Date.from_string('2018-01-01'),
                'wage': 50000.0,
                'basic_salary': 40000.0,
                'da': 10000.0,
            })

        self.payslip = self.env['hr.payslip'].create({
            'name': 'Gratuity Payslip Test',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'company_id': self.company.id,
            'date_from': Date.from_string('2024-03-01'),
            'date_to': Date.from_string('2024-03-31'),
        })

    def test_01_single_record_enforcement(self):
        """Test hds_in_compute_gratuity raises exception if called on multi-recordset."""
        payslips = self.payslip | self.payslip.copy()
        with self.assertRaises(Exception):
            payslips.hds_in_compute_gratuity()

    def test_02_gratuity_delegation_to_service(self):
        """Test hds_in_compute_gratuity delegates calculation to GratuityService."""
        # Initialize statutory evaluation context
        localdict = {'payslip': self.payslip, 'employee': self.employee, 'contract': self.contract}
        self.payslip._get_statutory_context(localdict)
        
        # Completed service: 6 years 3 months -> 6 completed years
        # Formula: (50,000 / 26) * 15 * 6 = 173,076.92
        amount = self.payslip.hds_in_compute_gratuity()
        self.assertAlmostEqual(amount, 173076.92, places=2)

    def test_03_disabled_company_delegation(self):
        """Test delegation returns 0.0 when gratuity is disabled on company."""
        self.company.hds_in_enable_gratuity = False
        localdict = {'payslip': self.payslip, 'employee': self.employee, 'contract': self.contract}
        self.payslip._get_statutory_context(localdict)
        
        amount = self.payslip.hds_in_compute_gratuity()
        self.assertEqual(amount, 0.0)
