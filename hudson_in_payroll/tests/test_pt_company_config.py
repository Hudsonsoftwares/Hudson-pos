# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestPtCompanyConfig(TransactionCase):

    def setUp(self):
        super(TestPtCompanyConfig, self).setUp()
        self.state = self.env['res.country.state'].search([], limit=1)
        self.company = self.env['res.company'].create({
            'name': 'Test PT Company',
            'hds_in_enable_professional_tax': False,
            'hds_in_professional_tax_registration_no': False,
        })
        self.company.partner_id.write({'state_id': self.state.id})

    def test_01_pt_default_configuration(self):
        """Test default values for Professional Tax company configuration fields."""
        self.assertFalse(self.company.hds_in_enable_professional_tax)
        self.assertFalse(self.company.hds_in_professional_tax_registration_no)

    def test_02_pt_update_configuration(self):
        """Test updating Professional Tax company configuration fields via res.company."""
        self.company.write({
            'hds_in_enable_professional_tax': True,
            'hds_in_professional_tax_registration_no': 'PTRC/MH/2026/998877',
        })
        self.assertTrue(self.company.hds_in_enable_professional_tax)
        self.assertEqual(self.company.hds_in_professional_tax_registration_no, 'PTRC/MH/2026/998877')

    def test_03_pt_res_config_settings_relation(self):
        """Test res.config.settings related fields for Professional Tax."""
        settings = self.env['res.config.settings'].create({
            'company_id': self.company.id,
            'hds_in_enable_professional_tax': True,
            'hds_in_professional_tax_registration_no': 'PTRC/KA/2026/112233',
        })
        self.assertTrue(self.company.hds_in_enable_professional_tax)
        self.assertEqual(self.company.hds_in_professional_tax_registration_no, 'PTRC/KA/2026/112233')
        self.assertTrue(settings.hds_in_enable_professional_tax)
        self.assertEqual(settings.hds_in_professional_tax_registration_no, 'PTRC/KA/2026/112233')

    def test_04_pt_multi_company_isolation(self):
        """Test multi-company isolation for Professional Tax configuration."""
        company_b = self.env['res.company'].create({
            'name': 'Test PT Company B',
            'hds_in_enable_professional_tax': False,
        })
        self.company.write({
            'hds_in_enable_professional_tax': True,
            'hds_in_professional_tax_registration_no': 'PTRC/MH/100',
        })
        self.assertTrue(self.company.hds_in_enable_professional_tax)
        self.assertEqual(self.company.hds_in_professional_tax_registration_no, 'PTRC/MH/100')
        self.assertFalse(company_b.hds_in_enable_professional_tax)
        self.assertFalse(company_b.hds_in_professional_tax_registration_no)
