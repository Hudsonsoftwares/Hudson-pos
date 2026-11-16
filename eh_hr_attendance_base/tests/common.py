# -*- encoding: utf-8 -*-
"""Shared fixtures for the EH attendance suite test sweep.

Every test class in eh_hr_* uses this base (or extends it). Centralising
fixtures here prevents drift between modules and keeps each test focused
on the behaviour it asserts.
"""
import json
import random

from odoo.tests import TransactionCase


class EhHrTestCommon(TransactionCase):
    """Common setup: company, two employees, kiosk site, kiosk device.

    Subclasses can call `_grant_face_consent(employee)` and
    `_seed_face_template(employee, ...)` to extend the fixture without
    duplicating boilerplate.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.Company = cls.env['res.company']
        cls.Employee = cls.env['hr.employee']
        cls.Consent = cls.env['eh.hr.consent']
        cls.Site = cls.env['eh.hr.kiosk.site']
        cls.Device = cls.env['eh.hr.kiosk.terminal']
        cls.Event = cls.env['eh.hr.kiosk.event']
        cls.Exception_ = cls.env['eh.hr.attendance.exception']

        cls.company = cls.env.company

        cls.employee_alice = cls.Employee.create({
            'name': 'Alice Test',
            'company_id': cls.company.id,
        })
        cls.employee_bob = cls.Employee.create({
            'name': 'Bob Test',
            'company_id': cls.company.id,
        })

        cls.site = cls.Site.create({
            'name': 'Test HQ',
            'code': 'test-hq',
            'company_id': cls.company.id,
        })
        cls.device = cls.Device.create({
            'name': 'Test kiosk',
            'site_id': cls.site.id,
        })

    def _grant_face_consent(self, employee, company=None, validity_months=None):
        """Helper. Creates and grants a face consent for `employee`."""
        company = company or self.company
        consent = self.Consent.create({
            'employee_id': employee.id,
            'consent_type': 'face',
            'consent_text': 'I consent to face capture for attendance verification.',
            'company_id': company.id,
        })
        consent.action_grant()
        return consent

    def _make_embedding(self, seed=0):
        """Deterministic 128-dim embedding for tests."""
        rng = random.Random(seed)
        vec = [rng.uniform(-1.0, 1.0) for _ in range(128)]
        norm = sum(v * v for v in vec) ** 0.5
        return [v / norm for v in vec]

    def _seed_face_template(self, employee, consent=None, embedding=None, seed=0):
        """Create one eh.hr.face.template row for `employee`. Used by
        face_kiosk and downstream tests. Lives here so the helper is
        usable from any test in the suite.
        """
        Template = self.env.get('eh.hr.face.template')
        if Template is None:
            self.skipTest('eh.hr.face.template not installed (eh_hr_face_kiosk required)')
        consent = consent or self._grant_face_consent(employee)
        embedding = embedding if embedding is not None else self._make_embedding(seed)
        return Template.create({
            'employee_id': employee.id,
            'consent_id': consent.id,
            'embedding': json.dumps(embedding),
            'embedding_dim': len(embedding),
            'company_id': employee.company_id.id,
        })
