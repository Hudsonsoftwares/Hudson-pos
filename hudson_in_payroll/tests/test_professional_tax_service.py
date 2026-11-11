# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.addons.hudson_in_payroll.services.professional_tax.professional_tax_service import ProfessionalTaxService


class TestProfessionalTaxService(TransactionCase):

    def setUp(self):
        super(TestProfessionalTaxService, self).setUp()
        self.service = ProfessionalTaxService(self.env)
        self.company_enabled = self.env.company
        self.company_enabled.write({
            'hds_in_enable_professional_tax': True,
            'hds_in_professional_tax_registration_no': 'MH/PT/REG/999',
        })

        self.company_disabled = self.env['res.company'].create({
            'name': 'Company Disabled PT (Test)',
            'hds_in_enable_professional_tax': False,
        })

        self.company_b = self.env['res.company'].create({
            'name': 'Company B Custom Slabs',
            'hds_in_enable_professional_tax': True,
        })

        # States
        self.state_mh = self.env.ref('base.state_in_mh')
        self.state_dl = self.env.ref('base.state_in_dl')

        # Employee with MH Work Location
        self.partner_mh = self.env['res.partner'].create({
            'name': 'Mumbai HQ Address',
            'state_id': self.state_mh.id,
        })
        self.work_loc_mh = self.env['hr.work.location'].create({
            'name': 'Mumbai HQ',
            'address_id': self.partner_mh.id,
            'company_id': self.company_enabled.id,
        })
        self.emp_mh = self.env['hr.employee'].create({
            'name': 'Aditya Verma',
            'gender': 'male',
            'work_location_id': self.work_loc_mh.id,
            'company_id': self.company_enabled.id,
        })

    def test_01_successful_pt_computation(self):
        """Test end-to-end successful Professional Tax calculation through orchestrator."""
        res = self.service.compute_pt(
            employee=self.emp_mh,
            salary=15000.0,
            eval_date='2026-06-01',
            company=self.company_enabled
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.validation_status, 'VALID')
        self.assertEqual(res.amount, 200.0)
        self.assertEqual(res.state.id, self.state_mh.id)
        self.assertFalse(res.override_applied)

        # Verify float helper method
        amount = self.service.compute_pt_amount(
            employee=self.emp_mh,
            salary=15000.0,
            eval_date='2026-06-01',
            company=self.company_enabled
        )
        self.assertEqual(amount, 200.0)

    def test_02_company_disabled(self):
        """Test orchestrator output when Professional Tax is disabled for company."""
        res = self.service.compute_pt(
            employee=self.emp_mh,
            salary=15000.0,
            company=self.company_disabled
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.validation_status, 'DISABLED_COMPANY')
        self.assertEqual(res.amount, 0.0)
        self.assertIn('disabled', res.failure_reason)

    def test_03_no_applicable_slab(self):
        """Test orchestrator output for state with no configured PT slabs (e.g. Delhi)."""
        res = self.service.compute_pt(
            salary=50000.0,
            state=self.state_dl,
            company=self.company_enabled
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.validation_status, 'NO_MATCHING_SLAB')
        self.assertEqual(res.amount, 0.0)

    def test_04_salary_outside_configured_slabs(self):
        """Test salary in zero-tax slab (MH Male ₹5,000 gross → PT ₹0)."""
        res = self.service.compute_pt(
            employee=self.emp_mh,
            salary=5000.0,
            eval_date='2026-06-01',
            company=self.company_enabled
        )
        self.assertTrue(res.is_valid)
        self.assertEqual(res.amount, 0.0)
        self.assertEqual(res.salary_from, 0.0)
        self.assertEqual(res.salary_to, 7500.0)

    def test_05_override_month_handling(self):
        """Test special February override month calculation through orchestrator."""
        res_feb = self.service.compute_pt(
            employee=self.emp_mh,
            salary=15000.0,
            eval_date='2026-02-15',
            company=self.company_enabled
        )
        self.assertTrue(res_feb.is_valid)
        self.assertEqual(res_feb.amount, 300.0)
        self.assertTrue(res_feb.override_applied)
        self.assertEqual(res_feb.override_month, '2')
        self.assertEqual(res_feb.override_amount, 300.0)

    def test_06_multi_company_scenarios(self):
        """Test multi-company isolation in orchestrator."""
        # Create company-specific slab for Company B
        self.env['pt.state.slab'].create({
            'state_id': self.state_mh.id,
            'periodicity': 'monthly',
            'salary_from': 10001.0,
            'pt_amount': 150.0,
            'company_id': self.company_b.id,
        })

        res_a = self.service.compute_pt(salary=15000.0, state=self.state_mh, company=self.company_enabled, gender='male')
        self.assertEqual(res_a.amount, 200.0)

        res_b = self.service.compute_pt(salary=15000.0, state=self.state_mh, company=self.company_b, gender='male')
        self.assertEqual(res_b.amount, 150.0)

    def test_07_payslip_localdict_context(self):
        """Test execution simulating salary rule execution environment with localdict."""
        class MockCategories:
            GROSS_PT = 18000.0

        localdict = {
            'employee': self.emp_mh,
            'categories': MockCategories(),
            'company': self.company_enabled,
            'eval_date': '2026-06-01',
        }

        res = self.service.compute_pt(localdict=localdict)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.amount, 200.0)

        amount = self.service.compute_pt_amount(localdict=localdict)
        self.assertEqual(amount, 200.0)
