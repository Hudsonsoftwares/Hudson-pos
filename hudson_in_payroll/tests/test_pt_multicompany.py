# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.fields import Date
from odoo.addons.hudson_in_payroll.services.professional_tax.professional_tax_service import ProfessionalTaxService


class TestPTMultiCompany(TransactionCase):

    def setUp(self):
        super(TestPTMultiCompany, self).setUp()
        self.service = ProfessionalTaxService(self.env)

        # Create two distinct companies
        self.company_a = self.env['res.company'].create({
            'name': 'MultiCompany Alpha Corp',
            'hds_in_enable_professional_tax': True,
            'hds_in_professional_tax_registration_no': 'MH/PT/ALPHA/111',
        })
        self.company_b = self.env['res.company'].create({
            'name': 'MultiCompany Beta Corp',
            'hds_in_enable_professional_tax': False,
            'hds_in_professional_tax_registration_no': 'MH/PT/BETA/222',
        })

        self.state_mh = self.env.ref('base.state_in_mh')
        self.state_ka = self.env.ref('base.state_in_ka')

        # Company A Employee in MH
        self.partner_a = self.env['res.partner'].create({'name': 'Alpha MH Location', 'state_id': self.state_mh.id})
        self.work_loc_a = self.env['hr.work.location'].create({
            'name': 'Alpha Mumbai',
            'address_id': self.partner_a.id,
            'company_id': self.company_a.id,
        })
        self.emp_a = self.env['hr.employee'].create({
            'name': 'Alpha Employee',
            'gender': 'male',
            'work_location_id': self.work_loc_a.id,
            'company_id': self.company_a.id,
        })
        self.contract_a = self.env['hr.version'].create({
            'name': 'Alpha Contract',
            'employee_id': self.emp_a.id,
            'date_start': Date.from_string('2025-01-01'),
            'wage': 20000.0,
        })

        # Company B Employee in MH
        self.partner_b = self.env['res.partner'].create({'name': 'Beta MH Location', 'state_id': self.state_mh.id})
        self.work_loc_b = self.env['hr.work.location'].create({
            'name': 'Beta Mumbai',
            'address_id': self.partner_b.id,
            'company_id': self.company_b.id,
        })
        self.emp_b = self.env['hr.employee'].create({
            'name': 'Beta Employee',
            'gender': 'male',
            'work_location_id': self.work_loc_b.id,
            'company_id': self.company_b.id,
        })
        self.contract_b = self.env['hr.version'].create({
            'name': 'Beta Contract',
            'employee_id': self.emp_b.id,
            'date_start': Date.from_string('2025-01-01'),
            'wage': 20000.0,
        })

    def test_01_multicompany_company_config_isolation(self):
        """Test multi-company isolation: Company A (PT enabled) vs Company B (PT disabled)."""
        res_a = self.service.compute_pt(employee=self.emp_a, salary=20000.0, company=self.company_a)
        self.assertTrue(res_a.is_valid)
        self.assertEqual(res_a.amount, 200.0)

        res_b = self.service.compute_pt(employee=self.emp_b, salary=20000.0, company=self.company_b)
        self.assertFalse(res_b.is_valid)
        self.assertEqual(res_b.amount, 0.0)
        self.assertEqual(res_b.validation_status, 'DISABLED_COMPANY')

    def test_02_multicompany_state_slab_override(self):
        """Test company-specific slab override taking precedence over global state slab."""
        # Enable PT on Company B for custom slab test
        self.company_b.write({'hds_in_enable_professional_tax': True})

        # Company B custom slab in Karnataka (₹150 instead of global ₹200)
        slab_custom_b = self.env['pt.state.slab'].create({
            'state_id': self.state_ka.id,
            'periodicity': 'monthly',
            'salary_from': 25000.0,
            'pt_amount': 150.0,
            'company_id': self.company_b.id,
        })

        res_a = self.service.compute_pt(salary=30000.0, state=self.state_ka, company=self.company_a)
        self.assertEqual(res_a.amount, 200.0)

        res_b = self.service.compute_pt(salary=30000.0, state=self.state_ka, company=self.company_b)
        self.assertEqual(res_b.amount, 150.0)
        self.assertEqual(res_b.company.id, self.company_b.id)

    def test_03_multicompany_payslip_computation(self):
        """Test simultaneous payslip sheet calculations across multi-company setup."""
        payslip_a = self.env['hr.payslip'].create({
            'name': 'Alpha Payslip',
            'employee_id': self.emp_a.id,
            'contract_id': self.contract_a.id,
            'company_id': self.company_a.id,
            'date_from': Date.from_string('2026-01-01'),
            'date_to': Date.from_string('2026-01-31'),
        })

        payslip_b = self.env['hr.payslip'].create({
            'name': 'Beta Payslip',
            'employee_id': self.emp_b.id,
            'contract_id': self.contract_b.id,
            'company_id': self.company_b.id,
            'date_from': Date.from_string('2026-01-01'),
            'date_to': Date.from_string('2026-01-31'),
        })

        lines_a = self.env['hr.payslip']._get_payslip_lines([self.contract_a.id], payslip_a.id)
        pt_lines_a = [l for l in lines_a if l['code'] == 'PT']
        self.assertEqual(len(pt_lines_a), 1)
        self.assertEqual(pt_lines_a[0]['amount'], -200.0)

        lines_b = self.env['hr.payslip']._get_payslip_lines([self.contract_b.id], payslip_b.id)
        pt_lines_b = [l for l in lines_b if l['code'] == 'PT']
        self.assertEqual(len(pt_lines_b), 0)
