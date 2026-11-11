# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestPtStateSlab(TransactionCase):

    def setUp(self):
        super(TestPtStateSlab, self).setUp()
        self.state_ka = self.env.ref('base.state_in_ka')
        self.company_a = self.env.company
        self.company_b = self.env['res.company'].create({'name': 'Company B'})

    def test_01_create_pt_state_slab(self):
        """Test creating a PT state slab record and verifying name computation."""
        slab = self.env['pt.state.slab'].create({
            'state_id': self.state_ka.id,
            'periodicity': 'monthly',
            'salary_from': 25000.0,
            'salary_to': False,  # Open-ended slab
            'pt_amount': 200.0,
            'special_rules': 'Rs.300 in Feb',
            'company_id': self.company_a.id,
        })
        self.assertTrue(slab.name)
        self.assertIn('Karnataka', slab.name)
        self.assertIn('Above', slab.name)
        self.assertIn('200', slab.name)
        self.assertEqual(slab.pt_amount, 200.0)
        self.assertFalse(slab.salary_to)

    def test_02_negative_salary_and_pt_amount_validation(self):
        """Test validation error when salary limits or PT amount is negative."""
        with self.assertRaises(ValidationError):
            self.env['pt.state.slab'].create({
                'state_id': self.state_ka.id,
                'periodicity': 'monthly',
                'salary_from': -100.0,
                'salary_to': 10000.0,
                'pt_amount': 150.0,
            })

        with self.assertRaises(ValidationError):
            self.env['pt.state.slab'].create({
                'state_id': self.state_ka.id,
                'periodicity': 'monthly',
                'salary_from': 0.0,
                'salary_to': 10000.0,
                'pt_amount': -150.0,
            })

    def test_03_invalid_salary_range_validation(self):
        """Test validation error when salary_to is less than salary_from (when salary_to is set)."""
        with self.assertRaises(ValidationError):
            self.env['pt.state.slab'].create({
                'state_id': self.state_ka.id,
                'periodicity': 'monthly',
                'salary_from': 15000.0,
                'salary_to': 10000.0,
                'pt_amount': 200.0,
            })

    def test_04_invalid_date_range_validation(self):
        """Test validation error when date_to is earlier than date_from."""
        with self.assertRaises(ValidationError):
            self.env['pt.state.slab'].create({
                'state_id': self.state_ka.id,
                'periodicity': 'monthly',
                'salary_from': 0.0,
                'salary_to': 10000.0,
                'pt_amount': 100.0,
                'date_from': '2026-06-01',
                'date_to': '2026-01-01',
            })

    def test_05_overlapping_slabs_validation(self):
        """Test validation error when creating an overlapping active slab for same periodicity."""
        self.env['pt.state.slab'].create({
            'state_id': self.state_ka.id,
            'periodicity': 'monthly',
            'salary_from': 10000.0,
            'salary_to': 20000.0,
            'pt_amount': 150.0,
            'company_id': self.company_a.id,
        })

        with self.assertRaises(ValidationError):
            self.env['pt.state.slab'].create({
                'state_id': self.state_ka.id,
                'periodicity': 'monthly',
                'salary_from': 15000.0,  # Overlaps 10000-20000
                'salary_to': 30000.0,
                'pt_amount': 200.0,
                'company_id': self.company_a.id,
            })

    def test_06_multi_company_isolation(self):
        """Test multi-company isolation allows identical slabs for different companies."""
        slab_a = self.env['pt.state.slab'].create({
            'state_id': self.state_ka.id,
            'periodicity': 'monthly',
            'salary_from': 10000.0,
            'salary_to': 20000.0,
            'pt_amount': 150.0,
            'company_id': self.company_a.id,
        })
        slab_b = self.env['pt.state.slab'].create({
            'state_id': self.state_ka.id,
            'periodicity': 'monthly',
            'salary_from': 10000.0,
            'salary_to': 20000.0,
            'pt_amount': 150.0,
            'company_id': self.company_b.id,
        })
        self.assertTrue(slab_a.id)
        self.assertTrue(slab_b.id)
        self.assertNotEqual(slab_a.company_id, slab_b.company_id)

    def test_07_gender_differentiated_slabs(self):
        """Test that distinct gender criteria (Male vs Female) allow overlapping salary ranges."""
        state_mh = self.env.ref('base.state_in_mh')
        male_slab = self.env['pt.state.slab'].create({
            'state_id': state_mh.id,
            'periodicity': 'monthly',
            'gender': 'male',
            'salary_from': 0.0,
            'salary_to': 7500.0,
            'pt_amount': 0.0,
        })
        female_slab = self.env['pt.state.slab'].create({
            'state_id': state_mh.id,
            'periodicity': 'monthly',
            'gender': 'female',
            'salary_from': 0.0,
            'salary_to': 25000.0,  # Overlaps salary range with male slab, but gender is female
            'pt_amount': 0.0,
        })
        self.assertTrue(male_slab.id)
        self.assertTrue(female_slab.id)

    def test_08_special_monthly_override(self):
        """Test creating and validating special monthly override fields."""
        slab = self.env['pt.state.slab'].create({
            'state_id': self.state_ka.id,
            'periodicity': 'monthly',
            'salary_from': 25000.0,
            'pt_amount': 200.0,
            'override_month': '2',
            'override_amount': 300.0,
        })
        self.assertEqual(slab.override_month, '2')
        self.assertEqual(slab.override_amount, 300.0)

        with self.assertRaises(ValidationError):
            self.env['pt.state.slab'].create({
                'state_id': self.state_ka.id,
                'periodicity': 'monthly',
                'salary_from': 30000.0,
                'pt_amount': 200.0,
                'override_month': '2',
                'override_amount': -50.0,
            })


