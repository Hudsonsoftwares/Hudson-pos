# -*- encoding: utf-8 -*-
from datetime import timedelta

# pyrefly: ignore [missing-import]
from odoo import fields
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError

from odoo.addons.eh_hr_attendance_base.tests.common import EhHrTestCommon


class TestVisitor(EhHrTestCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.purpose_meeting = cls.env.ref('eh_hr_visitor.purpose_meeting')
        cls.purpose_contractor = cls.env.ref('eh_hr_visitor.purpose_contractor')

    def _create_visitor(self, **overrides):
        vals = {
            'name': 'Charlie External',
            'visitor_company': 'Acme Co',
            'host_employee_id': self.employee_alice.id,
            'purpose_id': self.purpose_meeting.id,
            'company_id': self.company.id,
        }
        vals.update(overrides)
        return self.env['eh.hr.visitor'].create(vals)

    def test_create_assigns_visit_number(self):
        v = self._create_visitor()
        self.assertTrue(v.visit_number)

    def test_sign_in_sets_state_and_arrived(self):
        v = self._create_visitor()
        self.assertEqual(v.state, 'pending')
        v.action_sign_in()
        self.assertEqual(v.state, 'signed_in')
        self.assertTrue(v.arrived_on)

    def test_nda_required_blocks_sign_in_without_acceptance(self):
        # nda_required must be set on the visitor record itself
        # (the purpose drives it via the controller, but ORM tests set it directly)
        v = self._create_visitor(purpose_id=self.purpose_contractor.id, nda_required=True)
        with self.assertRaises(ValidationError):
            v.action_sign_in()

    def test_nda_required_passes_with_acceptance(self):
        import base64
        # digital_signature is stored as base64 bytes
        valid_sig = base64.b64encode(b'dummy_signature')
        v = self._create_visitor(
            purpose_id=self.purpose_contractor.id,
            nda_required=True,
            nda_accepted=True,
            digital_signature=valid_sig,
        )
        v.action_sign_in()
        self.assertEqual(v.state, 'signed_in')

    def test_sign_out_sets_signed_out_on(self):
        v = self._create_visitor()
        v.action_sign_in()
        v.action_sign_out()
        self.assertEqual(v.state, 'signed_out')
        self.assertTrue(v.signed_out_on)
        self.assertGreater(v.duration_minutes, -1)

    def test_purpose_code_unique_per_company(self):
        # The seed purposes are company_id=False (shared). UNIQUE in
        # SQL treats NULL company differently from a concrete company,
        # so the test creates the first row itself to assert the
        # constraint actually fires on a true duplicate.
        from psycopg2 import IntegrityError
        from odoo.tools import mute_logger
        Purpose = self.env['eh.hr.visitor.purpose']
        Purpose.create({
            'name': 'Custom one',
            'code': 'custom-test-purpose',
            'company_id': self.company.id,
        })
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                Purpose.create({
                    'name': 'Custom dup',
                    'code': 'custom-test-purpose',
                    'company_id': self.company.id,
                })

    def test_auto_sign_out_cron_closes_overstays(self):
        v = self._create_visitor()
        v.action_sign_in()
        # Force the company hour to 0 so the cron always fires.
        self.company.write({
            'eh_hr_visitor_auto_checkout_enabled': True,
            'eh_hr_visitor_auto_checkout_hour': 0,
        })
        self.env['eh.hr.visitor']._cron_auto_sign_out()
        v.invalidate_recordset(['state', 'auto_signed_out'])
        self.assertEqual(v.state, 'signed_out')
        self.assertTrue(v.auto_signed_out)

    def test_retention_sweep_deletes_old_signed_out_rows(self):
        v = self._create_visitor()
        v.action_sign_in()
        v.action_sign_out()
        # Flush pending ORM writes before the raw SQL update, otherwise
        # the next implicit flush overwrites our aged signed_out_on.
        self.env.flush_all()
        cutoff = fields.Datetime.now() - timedelta(days=400)
        self.env.cr.execute(
            "UPDATE eh_hr_visitor SET signed_out_on = %s WHERE id = %s",
            (cutoff, v.id),
        )
        self.env['eh.hr.visitor'].invalidate_model()
        self.env['eh.hr.visitor']._cron_retention_sweep()
        self.assertFalse(self.env['eh.hr.visitor'].browse(v.id).exists())
