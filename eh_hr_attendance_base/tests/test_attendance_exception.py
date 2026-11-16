# -*- encoding: utf-8 -*-
from odoo.exceptions import UserError

from .common import EhHrTestCommon


class TestAttendanceException(EhHrTestCommon):

    def test_raise_exception_creates_row_and_audit(self):
        record = self.Exception_.raise_exception(
            employee=self.employee_alice,
            exception_type='late',
            severity='warning',
            description='Five minutes late',
        )
        self.assertTrue(record.id)
        self.assertEqual(record.employee_id, self.employee_alice)
        self.assertEqual(record.exception_type, 'late')
        self.assertEqual(record.severity, 'warning')
        self.assertFalse(record.resolved)

        events = self.Event.search([
            ('event_type', '=', 'exception_raised'),
            ('employee_id', '=', self.employee_alice.id),
        ])
        self.assertTrue(events)
        self.assertEqual(events[0].ref_model, 'eh.hr.attendance.exception')
        self.assertEqual(events[0].ref_id, record.id)

    def test_raise_exception_requires_employee(self):
        with self.assertRaises(UserError):
            self.Exception_.raise_exception(
                employee=None,
                exception_type='late',
            )

    def test_resolve_sets_user_and_date(self):
        record = self.Exception_.raise_exception(
            employee=self.employee_alice,
            exception_type='manual',
        )
        record.action_resolve()
        self.assertTrue(record.resolved)
        self.assertEqual(record.resolved_by, self.env.user)
        self.assertTrue(record.resolved_on)

    def test_reopen_clears_resolution(self):
        record = self.Exception_.raise_exception(
            employee=self.employee_alice,
            exception_type='manual',
        )
        record.action_resolve()
        record.action_reopen()
        self.assertFalse(record.resolved)
        self.assertFalse(record.resolved_by)
        self.assertFalse(record.resolved_on)
