# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestGratuityCompanyConfig(TransactionCase):

    def setUp(self):
        super(TestGratuityCompanyConfig, self).setUp()
        self.company = self.env['res.company'].create({
            'name': 'Test Gratuity Company',
            'hds_in_enable_gratuity': False,
            'hds_in_gratuity_registration_no': False,
        })

    def test_01_gratuity_default_configuration(self):
        """Test default values for Gratuity company configuration fields."""
        self.assertFalse(self.company.hds_in_enable_gratuity)
        self.assertFalse(self.company.hds_in_gratuity_registration_no)

    def test_02_gratuity_update_configuration(self):
        """Test updating Gratuity company configuration fields via res.company."""
        self.company.write({
            'hds_in_enable_gratuity': True,
            'hds_in_gratuity_registration_no': 'GR/MH/2026/998877',
        })
        self.assertTrue(self.company.hds_in_enable_gratuity)
        self.assertEqual(self.company.hds_in_gratuity_registration_no, 'GR/MH/2026/998877')

    def test_03_gratuity_res_config_settings_relation(self):
        """Test res.config.settings related fields for Gratuity."""
        settings = self.env['res.config.settings'].create({
            'company_id': self.company.id,
            'hds_in_enable_gratuity': True,
            'hds_in_gratuity_registration_no': 'GR/KA/2026/112233',
        })
        self.assertTrue(self.company.hds_in_enable_gratuity)
        self.assertEqual(self.company.hds_in_gratuity_registration_no, 'GR/KA/2026/112233')
        self.assertTrue(settings.hds_in_enable_gratuity)
        self.assertEqual(settings.hds_in_gratuity_registration_no, 'GR/KA/2026/112233')
