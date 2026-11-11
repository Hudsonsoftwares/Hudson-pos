# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.fields import Date
from odoo.addons.hudson_in_payroll.services.professional_tax.professional_tax_service import ProfessionalTaxService


class TestPTHalfYearly(TransactionCase):

    def setUp(self):
        super(TestPTHalfYearly, self).setUp()
        self.service = ProfessionalTaxService(self.env)
        self.company = self.env.company
        self.company.write({
            'hds_in_enable_professional_tax': True,
            'hds_in_professional_tax_registration_no': 'KL/PT/REG/100',
        })

        # States
        self.state_kl = self.env.ref('base.state_in_kl')
        self.state_tn = self.env.ref('base.state_in_tn')
        self.state_mh = self.env.ref('base.state_in_mh')

        # Work Locations
        self.partner_kl = self.env['res.partner'].create({
            'name': 'Kochi Location Address',
            'state_id': self.state_kl.id,
        })
        self.work_loc_kl = self.env['hr.work.location'].create({
            'name': 'Kochi Tech Park',
            'address_id': self.partner_kl.id,
            'company_id': self.company.id,
        })

        self.partner_tn = self.env['res.partner'].create({
            'name': 'Chennai Location Address',
            'state_id': self.state_tn.id,
        })
        self.work_loc_tn = self.env['hr.work.location'].create({
            'name': 'Chennai Office',
            'address_id': self.partner_tn.id,
            'company_id': self.company.id,
        })

        # Employees
        self.emp_kl = self.env['hr.employee'].create({
            'name': 'Anand Nair (Kerala)',
            'sex': 'male',
            'work_location_id': self.work_loc_kl.id,
            'company_id': self.company.id,
        })

        self.emp_tn = self.env['hr.employee'].create({
            'name': 'Karthik Raja (Tamil Nadu)',
            'sex': 'male',
            'work_location_id': self.work_loc_tn.id,
            'company_id': self.company.id,
        })

    def test_01_kerala_non_deduction_month(self):
        """Test Kerala PT returns 0.0 for non-deduction month (e.g. June)."""
        res = self.service.compute_pt(
            employee=self.emp_kl,
            salary=25000.0,
            eval_date='2026-06-01',
            company=self.company
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.validation_status, 'NON_DEDUCTION_MONTH')
        self.assertEqual(res.amount, 0.0)

    def test_02_kerala_deduction_month_august(self):
        """Test Kerala PT calculates full half-yearly deduction in August (H1)."""
        res = self.service.compute_pt(
            employee=self.emp_kl,
            salary=150000.0,  # Half-yearly gross > 125,000
            eval_date='2026-08-31',
            company=self.company
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.validation_status, 'VALID')
        self.assertEqual(res.amount, 1250.0)

    def test_03_tamil_nadu_deduction_month_september(self):
        """Test Tamil Nadu PT calculates half-yearly deduction in September."""
        res = self.service.compute_pt(
            employee=self.emp_tn,
            salary=80000.0,  # Half-yearly gross > 75,000 -> PT ₹1,250
            eval_date='2026-09-30',
            company=self.company
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.validation_status, 'VALID')
        self.assertEqual(res.amount, 1250.0)

    def test_04_maharashtra_monthly_backward_compatibility(self):
        """Test Maharashtra monthly PT calculation remains 100% backward compatible (June ₹200)."""
        partner_mh = self.env['res.partner'].create({'name': 'MH Address', 'state_id': self.state_mh.id})
        work_loc_mh = self.env['hr.work.location'].create({'name': 'MH Office', 'address_id': partner_mh.id, 'company_id': self.company.id})
        emp_mh = self.env['hr.employee'].create({'name': 'MH Test Emp', 'sex': 'male', 'work_location_id': work_loc_mh.id, 'company_id': self.company.id})

        res = self.service.compute_pt(
            employee=emp_mh,
            salary=15000.0,
            eval_date='2026-06-01',
            company=self.company
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.validation_status, 'VALID')
        self.assertEqual(res.amount, 200.0)
