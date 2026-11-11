# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import fields
from odoo.tests.common import TransactionCase


class TestExpiryNotifications(TransactionCase):
    """Test suite for automated Contract & Work Permit Expiry Notifications."""

    def setUp(self):
        super().setUp()
        self.today = fields.Date.today()
        self.company = self.env.company

        # Ensure settings are enabled on company
        self.company.write({
            'contract_expiration_notice_period': 30,
            'work_permit_expiration_notice_period': 30,
            'enable_contract_expiry_notification': True,
            'enable_work_permit_expiry_notification': True,
        })

        # Create HR Officer User
        self.hr_user = self.env['res.users'].create({
            'name': 'HR Officer Test',
            'login': 'hr_officer_test@example.com',
            'email': 'hr_officer_test@example.com',
        })
        self.company.write({
            'expiry_notification_user_ids': [(4, self.hr_user.id)],
        })

        # Create Test Employee with expiring contract and work permit
        self.c_start = self.today - timedelta(days=180)
        self.c_end = self.today + timedelta(days=15)
        self.p_end = self.today + timedelta(days=20)

        emp_vals = {
            'name': 'Test Expiry Employee',
            'work_email': 'test.expiry.emp@example.com',
            'company_id': self.company.id,
            'hr_responsible_id': self.hr_user.id,
            'contract_date_start': self.c_start,
            'contract_date_end': self.c_end,
            'work_permit_expiration_date': self.p_end,
        }
        self.employee = self.env['hr.employee'].create(emp_vals)

        # If version_id exists in Odoo 19, ensure version has contract dates set
        if hasattr(self.employee, 'version_id') and self.employee.version_id:
            v_vals = {}
            if 'contract_date_start' in self.employee.version_id._fields:
                v_vals['contract_date_start'] = self.c_start
            if 'contract_date_end' in self.employee.version_id._fields:
                v_vals['contract_date_end'] = self.c_end
            if v_vals:
                self.employee.version_id.write(v_vals)

    def test_01_expiry_notifications_contract_and_permit(self):
        """Test that running notification check generates activities, messages, and email records."""
        # Execute notification check
        res = self.env['hr.employee'].notify_expiring_contract_work_permit()

        self.assertGreaterEqual(res.get('contract_notified_count', 0), 1, "Should notify for expiring contract")
        self.assertGreaterEqual(res.get('permit_notified_count', 0), 1, "Should notify for expiring work permit")

        # Verify employee tracking dates were recorded
        self.assertEqual(self.employee.last_contract_expiry_notified_date, self.c_end)
        self.assertEqual(self.employee.last_work_permit_expiry_notified_date, self.p_end)

        # Verify HR In-App Activity was created
        act_summaries = self.employee.activity_ids.mapped('summary')
        self.assertTrue(any('Contract Expiring Soon' in s for s in act_summaries), "Contract expiry activity not found")
        self.assertTrue(any('Work Permit Expiring Soon' in s for s in act_summaries), "Work permit expiry activity not found")

        # Verify HR In-App Discuss Message was posted in chatter
        chatter_bodies = self.employee.message_ids.mapped('body')
        self.assertTrue(any('Upcoming Contract Expiry Notice' in b for b in chatter_bodies), "Contract chatter message not found")
        self.assertTrue(any('Upcoming Work Permit Expiry Notice' in b for b in chatter_bodies), "Work permit chatter message not found")

    def test_02_anti_spam_deduplication(self):
        """Test that running the job repeatedly does NOT send duplicate notifications for the same expiry date."""
        # Initial run
        self.env['hr.employee'].notify_expiring_contract_work_permit()
        act_count_before = len(self.employee.activity_ids)
        msg_count_before = len(self.employee.message_ids)

        # Second run immediately after
        res2 = self.env['hr.employee'].notify_expiring_contract_work_permit()

        # Counts for this employee should be 0 because last_notified_date matches c_end and p_end
        self.assertEqual(len(self.employee.activity_ids), act_count_before, "Should not duplicate activities")
        self.assertEqual(len(self.employee.message_ids), msg_count_before, "Should not duplicate messages")

    def test_03_disabled_toggle_skips_notification(self):
        """Test that disabling notifications in settings prevents alerts from sending."""
        # Create second employee
        emp2 = self.env['hr.employee'].create({
            'name': 'Test Disabled Employee',
            'work_email': 'disabled.emp@example.com',
            'company_id': self.company.id,
            'work_permit_expiration_date': self.today + timedelta(days=10),
        })

        # Disable both toggles
        self.company.write({
            'enable_contract_expiry_notification': False,
            'enable_work_permit_expiry_notification': False,
        })

        res = self.env['hr.employee'].notify_expiring_contract_work_permit()
        self.assertEqual(res.get('contract_notified_count', 0), 0)
        self.assertEqual(res.get('permit_notified_count', 0), 0)
        self.assertFalse(emp2.last_work_permit_expiry_notified_date)

    def test_04_manual_trigger_from_settings(self):
        """Test on-demand button trigger from Settings UI."""
        settings_wizard = self.env['res.config.settings'].create({
            'company_id': self.company.id,
        })
        action = settings_wizard.action_check_and_notify_expirations()
        self.assertEqual(action.get('type'), 'ir.actions.client')
        self.assertEqual(action.get('tag'), 'display_notification')
        self.assertIn('Expiry Check Completed', action.get('params', {}).get('message', ''))
