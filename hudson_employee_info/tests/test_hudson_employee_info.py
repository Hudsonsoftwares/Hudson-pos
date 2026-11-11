# -*- coding: utf-8 -*-
import base64
from datetime import timedelta
# pyrefly: ignore [missing-import]
from odoo import fields
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError
# pyrefly: ignore [missing-import]
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestHudsonEmployeeInfo(common.TransactionCase):

    def setUp(self):
        super(TestHudsonEmployeeInfo, self).setUp()
        self.lang_en = self.env['res.lang'].search([('code', '=', 'en_US')], limit=1)
        if not self.lang_en:
            self.lang_en = self.env['res.lang'].search([], limit=1)

    def test_01_personal_info_fields(self):
        """Test storing personal info and payslip language."""
        employee = self.env['hr.employee'].create({
            'name': 'Hudson Test Employee',
            'is_disabled': False,
            'payslip_lang_id': self.lang_en.id if self.lang_en else False,
            'is_non_resident': True,
            'work_permit_expiry_date': fields.Date.today() + timedelta(days=365),
            'spouse_legal_name': 'Jane Doe',
            'spouse_birthdate': fields.Date.today() - timedelta(days=365 * 25),
        })
        self.assertFalse(employee.is_disabled)
        self.assertTrue(employee.is_non_resident)
        self.assertEqual(employee.spouse_legal_name, 'Jane Doe')

    def test_02_document_upload(self):
        """Test document attachment storage for SIM Card and Internet bill."""
        sim_data = base64.b64encode(b"SIM Card Copy Content")
        invoice_data = base64.b64encode(b"Internet Invoice Content")
        employee = self.env['hr.employee'].create({
            'name': 'Hudson Doc Employee',
            'sim_card_copy': sim_data,
            'sim_card_copy_filename': 'sim.pdf',
            'internet_subscription_invoice': invoice_data,
            'internet_subscription_invoice_filename': 'bill.pdf',
        })
        self.assertEqual(employee.sim_card_copy_filename, 'sim.pdf')
        self.assertEqual(employee.internet_subscription_invoice_filename, 'bill.pdf')

    def test_03_future_spouse_birthdate_validation(self):
        """Test validation error for future spouse birthdate."""
        with self.assertRaises(ValidationError):
            self.env['hr.employee'].create({
                'name': 'Validation Emp',
                'spouse_birthdate': fields.Date.today() + timedelta(days=5),
            })
