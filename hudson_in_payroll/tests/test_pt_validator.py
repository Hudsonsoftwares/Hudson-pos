# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.addons.hudson_in_payroll.services.professional_tax.pt_validator import PTValidator


class TestPTValidator(TransactionCase):

    def setUp(self):
        super(TestPTValidator, self).setUp()
        self.validator = PTValidator(self.env)
        self.company_enabled = self.env.company
        self.company_enabled.write({
            'hds_in_enable_professional_tax': True,
            'hds_in_professional_tax_registration_no': 'MH/PT/12345/2026',
        })

        self.company_disabled = self.env['res.company'].create({
            'name': 'Disabled PT Company',
            'hds_in_enable_professional_tax': False,
        })

        # Reference States
        self.state_mh = self.env.ref('base.state_in_mh')
        self.state_dl = self.env.ref('base.state_in_dl')  # Delhi (No PT)

        # Create Work Location Partners
        self.partner_mh = self.env['res.partner'].create({
            'name': 'Mumbai Office Partner',
            'state_id': self.state_mh.id,
        })
        self.work_loc_mh = self.env['hr.work.location'].create({
            'name': 'Mumbai Branch',
            'address_id': self.partner_mh.id,
            'company_id': self.company_enabled.id,
        })

        # Employee with MH Work Location
        self.emp_mh = self.env['hr.employee'].create({
            'name': 'Vikramaditya Rao',
            'gender': 'male',
            'work_location_id': self.work_loc_mh.id,
            'company_id': self.company_enabled.id,
        })

        # Employee without Work Location or Partner State
        self.emp_no_state = self.env['hr.employee'].create({
            'name': 'Employee No State',
            'company_id': self.company_enabled.id,
        })

    def test_01_company_disabled(self):
        """Test validation failure when Professional Tax is disabled for company."""
        res = self.validator.validate(
            employee=self.emp_mh,
            salary=20000.0,
            company=self.company_disabled
        )
        self.assertFalse(res.is_valid)
        self.assertFalse(res.is_eligible)
        self.assertEqual(res.validation_status, 'DISABLED_COMPANY')
        self.assertIn('disabled', res.failure_reason)

    def test_02_missing_work_state(self):
        """Test validation failure when employee work location state cannot be resolved."""
        res = self.validator.validate(
            employee=self.emp_no_state,
            salary=20000.0,
            company=self.company_enabled
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.validation_status, 'MISSING_WORK_STATE')
        self.assertIn('could not be resolved', res.failure_reason)

    def test_03_no_matching_pt_slab(self):
        """Test validation failure when no PT slab exists for state (e.g. Delhi)."""
        res = self.validator.validate(
            salary=50000.0,
            state=self.state_dl,
            company=self.company_enabled
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.validation_status, 'NO_MATCHING_SLAB')
        self.assertIn('No matching active Professional Tax slab', res.failure_reason)

    def test_04_inactive_slab(self):
        """Test validation failure when matched slab is archived/inactive."""
        # Create a single state with only an inactive slab
        state_test = self.env['res.country.state'].create({
            'name': 'Test Statutory State',
            'code': 'TS_STAT',
            'country_id': self.env.ref('base.in').id,
        })
        inactive_slab = self.env['pt.state.slab'].create({
            'state_id': state_test.id,
            'periodicity': 'monthly',
            'salary_from': 0.0,
            'salary_to': False,
            'pt_amount': 200.0,
            'active': False,
        })

        res = self.validator.validate(
            salary=25000.0,
            state=state_test,
            company=self.company_enabled
        )
        self.assertFalse(res.is_valid)
        self.assertEqual(res.validation_status, 'NO_MATCHING_SLAB')

    def test_05_successful_validation(self):
        """Test successful validation for eligible employee with active slab."""
        res = self.validator.validate(
            employee=self.emp_mh,
            salary=15000.0,
            eval_date='2026-06-01',
            company=self.company_enabled
        )
        self.assertTrue(res.is_valid)
        self.assertTrue(res.is_eligible)
        self.assertEqual(res.validation_status, 'VALID')
        self.assertEqual(res.resolved_state.id, self.state_mh.id)
        self.assertIsNotNone(res.matched_slab)
        self.assertEqual(res.matched_slab.pt_amount, 200.0)
        self.assertEqual(res.to_dict()['validation_status'], 'VALID')
