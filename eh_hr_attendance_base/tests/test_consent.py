# -*- encoding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError

from .common import EhHrTestCommon


class TestConsentLifecycle(EhHrTestCommon):

    def test_create_starts_pending(self):
        consent = self.Consent.create({
            'employee_id': self.employee_alice.id,
            'consent_type': 'face',
        })
        self.assertEqual(consent.state, 'pending')
        self.assertFalse(consent.granted_on)
        self.assertFalse(consent.withdrawn_on)

    def test_grant_sets_dates_and_state(self):
        consent = self.Consent.create({
            'employee_id': self.employee_alice.id,
            'consent_type': 'face',
        })
        consent.action_grant()
        self.assertEqual(consent.state, 'granted')
        self.assertTrue(consent.granted_on)
        self.assertTrue(consent.expires_on)
        self.assertGreater(consent.expires_on, consent.granted_on)

    def test_withdraw_after_grant(self):
        consent = self._grant_face_consent(self.employee_alice)
        consent.action_withdraw()
        self.assertEqual(consent.state, 'withdrawn')
        self.assertTrue(consent.withdrawn_on)
        self.assertGreaterEqual(consent.withdrawn_on, consent.granted_on)

    def test_withdraw_rejected_before_granted_date(self):
        consent = self._grant_face_consent(self.employee_alice)
        with self.assertRaises(ValidationError):
            consent.write({'withdrawn_on': consent.granted_on - timedelta(days=1)})

    def test_employee_face_consent_state_compute(self):
        self.assertEqual(self.employee_alice.eh_face_consent_state, 'not_set')
        self._grant_face_consent(self.employee_alice)
        self.employee_alice.invalidate_recordset(['eh_face_consent_state', 'eh_consent_ids'])
        self.assertEqual(self.employee_alice.eh_face_consent_state, 'granted')

    def test_retention_sweep_expires_past_due_grants(self):
        consent = self._grant_face_consent(self.employee_alice)
        consent.write({'expires_on': fields.Datetime.now() - timedelta(days=1)})
        self.Consent._cron_retention_sweep()
        consent.invalidate_recordset()
        self.assertEqual(consent.state, 'expired')

    def test_retention_sweep_deletes_old_withdrawn_rows(self):
        consent = self._grant_face_consent(self.employee_alice)
        consent.action_withdraw()
        # Flush pending ORM writes before the raw SQL update, otherwise
        # the next implicit flush overwrites our aged write_date.
        self.env.flush_all()
        # Retention horizon defaults to 24 months. Force-age the row.
        cutoff = fields.Datetime.now() - timedelta(days=365 * 3)
        self.env.cr.execute(
            "UPDATE eh_hr_consent SET write_date = %s WHERE id = %s",
            (cutoff, consent.id),
        )
        self.Consent.invalidate_model()
        self.Consent._cron_retention_sweep()
        self.assertFalse(self.Consent.browse(consent.id).exists())

    def test_face_consent_state_search(self):
        # Alice gets face consent, Bob does not.
        self._grant_face_consent(self.employee_alice)
        granted = self.Employee.search([
            ('id', 'in', [self.employee_alice.id, self.employee_bob.id]),
            ('eh_face_consent_state', '=', 'granted'),
        ])
        self.assertEqual(granted, self.employee_alice)
        not_set = self.Employee.search([
            ('id', 'in', [self.employee_alice.id, self.employee_bob.id]),
            ('eh_face_consent_state', '=', 'not_set'),
        ])
        self.assertEqual(not_set, self.employee_bob)
