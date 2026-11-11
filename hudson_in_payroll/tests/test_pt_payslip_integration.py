# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.fields import Date


class TestPTPayslipIntegration(TransactionCase):

    def setUp(self):
        super(TestPTPayslipIntegration, self).setUp()
        self.company = self.env.company
        self.company.write({
            'hds_in_enable_professional_tax': True,
            'hds_in_professional_tax_registration_no': 'MH/PT/INT/2026',
        })

        self.state_mh = self.env.ref('base.state_in_mh')
        self.partner_mh = self.env['res.partner'].create({
            'name': 'Mumbai Integration Partner Address',
            'state_id': self.state_mh.id,
        })
        self.work_loc_mh = self.env['hr.work.location'].create({
            'name': 'Mumbai Office Location',
            'address_id': self.partner_mh.id,
            'company_id': self.company.id,
        })

        self.employee = self.env['hr.employee'].create({
            'name': 'PT Integration Test Employee',
            'sex': 'male',
            'work_location_id': self.work_loc_mh.id,
            'company_id': self.company.id,
        })

        if self.employee.version_id:
            self.contract = self.employee.version_id
            self.contract.write({
                'date_start': Date.from_string('2025-01-01'),
                'wage': 15000.0,
            })
        else:
            self.contract = self.env['hr.version'].create({
                'name': 'PT Integration Contract',
                'employee_id': self.employee.id,
                'date_start': Date.from_string('2025-01-01'),
                'wage': 15000.0,
            })

        self.payslip_jan = self.env['hr.payslip'].create({
            'name': 'PT Jan Payslip',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'company_id': self.company.id,
            'date_from': Date.from_string('2026-01-01'),
            'date_to': Date.from_string('2026-01-31'),
        })

        self.payslip_feb = self.env['hr.payslip'].create({
            'name': 'PT Feb Payslip',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'company_id': self.company.id,
            'date_from': Date.from_string('2026-02-01'),
            'date_to': Date.from_string('2026-02-28'),
        })

    def test_01_single_record_enforcement(self):
        """Test hds_in_compute_professional_tax raises Exception when called on multi-recordset."""
        payslips = self.payslip_jan | self.payslip_feb
        with self.assertRaises(Exception):
            payslips.hds_in_compute_professional_tax()

    def test_02_successful_payslip_delegation_january(self):
        """Test delegation returns -200.0 (negated for deduction rule) for standard month (January)."""
        localdict = {
            'payslip': self.payslip_jan,
            'employee': self.employee,
            'contract': self.contract,
            'gross_salary': 15000.0,
        }
        self.payslip_jan._get_statutory_context(localdict)
        amount = self.payslip_jan.hds_in_compute_professional_tax()
        self.assertEqual(amount, -200.0)

    def test_03_override_month_payslip_delegation_february(self):
        """Test delegation returns -300.0 for special override month (February)."""
        localdict = {
            'payslip': self.payslip_feb,
            'employee': self.employee,
            'contract': self.contract,
            'gross_salary': 15000.0,
        }
        self.payslip_feb._get_statutory_context(localdict)
        amount = self.payslip_feb.hds_in_compute_professional_tax()
        self.assertEqual(amount, -300.0)

    def test_04_disabled_company_payslip_delegation(self):
        """Test delegation returns 0.0 when Professional Tax is disabled for company."""
        company_disabled = self.env['res.company'].create({
            'name': 'Disabled PT Company Test',
            'hds_in_enable_professional_tax': False,
            'hds_in_enable_lwf': False,
            'state_id': self.state_mh.id,
        })
        if company_disabled.partner_id:
            company_disabled.partner_id.state_id = self.state_mh.id
        slip_disabled = self.env['hr.payslip'].create({
            'name': 'Disabled PT Payslip',
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'company_id': company_disabled.id,
            'date_from': Date.from_string('2026-01-01'),
            'date_to': Date.from_string('2026-01-31'),
        })
        localdict = {
            'payslip': slip_disabled,
            'employee': self.employee,
            'contract': self.contract,
            'company': company_disabled,
            'gross_salary': 15000.0,
        }
        slip_disabled._get_statutory_context(localdict)
        amount = slip_disabled.hds_in_compute_professional_tax()
        self.assertEqual(amount, 0.0)

    def test_05_disabled_employee_payslip_delegation(self):
        """Test delegation returns 0.0 when Professional Tax is disabled for employee via PT Applicable checkbox."""
        emp_pt_disabled = self.env['hr.employee'].create({
            'name': 'PT Disabled Employee',
            'sex': 'male',
            'work_location_id': self.work_loc_mh.id,
            'company_id': self.company.id,
            'hds_in_pt_applicable': False,
        })
        if emp_pt_disabled.version_id:
            contract_disabled = emp_pt_disabled.version_id
            contract_disabled.write({
                'date_start': Date.from_string('2025-01-01'),
                'wage': 15000.0,
            })
        else:
            contract_disabled = self.env['hr.version'].create({
                'name': 'PT Disabled Contract',
                'employee_id': emp_pt_disabled.id,
                'date_start': Date.from_string('2025-01-01'),
                'wage': 15000.0,
            })
        slip = self.env['hr.payslip'].create({
            'name': 'PT Disabled Payslip',
            'employee_id': emp_pt_disabled.id,
            'contract_id': contract_disabled.id,
            'company_id': self.company.id,
            'date_from': Date.from_string('2026-01-01'),
            'date_to': Date.from_string('2026-01-31'),
        })
        localdict = {
            'payslip': slip,
            'employee': emp_pt_disabled,
            'contract': contract_disabled,
            'company': self.company,
            'gross_salary': 15000.0,
        }
        slip._get_statutory_context(localdict)
        amount = slip.hds_in_compute_professional_tax()
        self.assertEqual(amount, 0.0)
