# -*- encoding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from psycopg2 import IntegrityError
from odoo.tools import mute_logger

from .common import EhHrTestCommon


class TestKioskSite(EhHrTestCommon):

    def test_code_format_validation(self):
        with self.assertRaises(ValidationError):
            self.Site.create({
                'name': 'Bad code',
                'code': 'has spaces and *bad chars',
                'company_id': self.company.id,
            })

    def test_code_unique_per_company(self):
        # Same code in same company is rejected by the SQL UNIQUE.
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self.Site.create({
                    'name': 'Duplicate',
                    'code': self.site.code,
                    'company_id': self.company.id,
                })

    def test_geofence_validation_rejects_bad_coords(self):
        with self.assertRaises(ValidationError):
            self.Site.create({
                'name': 'Bad geo',
                'code': 'bad-geo',
                'company_id': self.company.id,
                'geofence_enabled': True,
                'geofence_lat': 999.0,
                'geofence_lng': 0.0,
                'geofence_radius_m': 50,
            })

    def test_issue_pairing_pin_is_one_shot(self):
        action = self.site.action_issue_pairing_pin()
        self.assertIn('pin', action['params']['message'].lower())


class TestKioskDevice(EhHrTestCommon):

    def test_device_token_auto_issued(self):
        device = self.Device.create({
            'name': 'Auto token kiosk',
            'site_id': self.site.id,
        })
        self.assertTrue(device.device_token)
        self.assertGreater(len(device.device_token), 30)

    def test_rotate_token_changes_value(self):
        original = self.device.device_token
        self.device.action_rotate_token()
        self.assertNotEqual(self.device.device_token, original)

    def test_revoke_deactivates(self):
        self.assertTrue(self.device.active)
        self.device.action_revoke()
        self.assertFalse(self.device.active)

    def test_touch_records_heartbeat(self):
        before = self.device.last_seen
        self.device._touch(ip_address='10.0.0.1', user_agent='Mozilla/5.0')
        self.assertNotEqual(self.device.last_seen, before)
        self.assertEqual(self.device.last_ip, '10.0.0.1')


class TestKioskEvent(EhHrTestCommon):

    def test_log_creates_audit_row(self):
        event = self.Event.log(
            'attempt_match',
            device_id=self.device.id,
            employee_id=self.employee_alice.id,
            confidence=0.92,
            company_id=self.company.id,
        )
        self.assertTrue(event.id)
        self.assertEqual(event.event_type, 'attempt_match')
        self.assertEqual(event.employee_id, self.employee_alice)
        self.assertEqual(event.confidence, 0.92)
        self.assertEqual(event.site_id, self.site)

    def test_log_with_minimal_args(self):
        event = self.Event.log('error', notes='Boom', company_id=self.company.id)
        self.assertEqual(event.event_type, 'error')
        self.assertFalse(event.device_id)

    def test_audit_retention_sweep_deletes_old_events(self):
        event = self.Event.log('error', company_id=self.company.id)
        cutoff = fields.Datetime.now() - timedelta(days=365 * 10)
        self.env.cr.execute(
            "UPDATE eh_hr_kiosk_event SET timestamp = %s WHERE id = %s",
            (cutoff, event.id),
        )
        self.Event.invalidate_model()
        self.Event._cron_retention_sweep()
        self.assertFalse(self.Event.browse(event.id).exists())
