# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestUAEGPSSACompanyConfig(common.TransactionCase):

    def setUp(self):
        super(TestUAEGPSSACompanyConfig, self).setUp()
        self.country_ae = self.env.ref('base.ae', raise_if_not_found=False) or self.env['res.country'].search([('code', '=', 'AE')], limit=1)
        if not self.country_ae:
            self.country_ae = self.env['res.country'].create({
                'name': 'United Arab Emirates',
                'code': 'AE',
            })

    def test_01_default_company_gpssa_values(self):
        """GPSSA enablement should default to False with no employer number."""
        company = self.env['res.company'].create({
            'name': 'Test UAE Company Alpha',
            'country_id': self.country_ae.id,
        })
        self.assertFalse(company.hds_ae_enable_gpssa)
        self.assertFalse(company.hds_ae_gpssa_employer_number)

    def test_02_enable_gpssa_without_employer_number_fails(self):
        """Enabling GPSSA without employer number must raise ValidationError."""
        company = self.env['res.company'].create({
            'name': 'Test UAE Company Beta',
            'country_id': self.country_ae.id,
        })
        with self.assertRaises(ValidationError):
            company.write({
                'hds_ae_enable_gpssa': True,
                'hds_ae_gpssa_employer_number': False,
            })

    def test_03_enable_gpssa_with_empty_or_whitespace_string_fails(self):
        """Enabling GPSSA with empty/whitespace string must raise ValidationError."""
        company = self.env['res.company'].create({
            'name': 'Test UAE Company Gamma',
            'country_id': self.country_ae.id,
        })
        with self.assertRaises(ValidationError):
            company.write({
                'hds_ae_enable_gpssa': True,
                'hds_ae_gpssa_employer_number': '   ',
            })

    def test_04_create_company_with_gpssa_enabled_and_valid_number(self):
        """Creating company with GPSSA enabled and valid number succeeds and strips whitespace."""
        company = self.env['res.company'].create({
            'name': 'Test UAE Company Delta',
            'country_id': self.country_ae.id,
            'hds_ae_enable_gpssa': True,
            'hds_ae_gpssa_employer_number': '  GPSSA-987654  ',
        })
        self.assertTrue(company.hds_ae_enable_gpssa)
        self.assertEqual(company.hds_ae_gpssa_employer_number, 'GPSSA-987654')

    def test_05_disable_gpssa_allows_empty_employer_number(self):
        """Disabling GPSSA allows clearing or having no employer number."""
        company = self.env['res.company'].create({
            'name': 'Test UAE Company Epsilon',
            'country_id': self.country_ae.id,
            'hds_ae_enable_gpssa': True,
            'hds_ae_gpssa_employer_number': 'GPSSA-112233',
        })
        company.write({
            'hds_ae_enable_gpssa': False,
            'hds_ae_gpssa_employer_number': False,
        })
        self.assertFalse(company.hds_ae_enable_gpssa)
        self.assertFalse(company.hds_ae_gpssa_employer_number)

    def test_06_res_config_settings_synchronization(self):
        """res.config.settings related fields correctly read and update company fields."""
        company = self.env['res.company'].create({
            'name': 'Test UAE Company Zeta',
            'country_id': self.country_ae.id,
        })
        settings = self.env['res.config.settings'].create({
            'company_id': company.id,
            'hds_ae_enable_gpssa': True,
            'hds_ae_gpssa_employer_number': 'GPSSA-556677',
        })
        self.assertTrue(settings.hds_ae_enable_gpssa)
        self.assertEqual(settings.hds_ae_gpssa_employer_number, 'GPSSA-556677')
        self.assertTrue(company.hds_ae_enable_gpssa)
        self.assertEqual(company.hds_ae_gpssa_employer_number, 'GPSSA-556677')
