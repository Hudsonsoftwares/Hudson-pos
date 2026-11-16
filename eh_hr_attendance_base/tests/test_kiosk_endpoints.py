# -*- encoding: utf-8 -*-
import json

from odoo.tests import HttpCase, tagged

from odoo.addons.eh_hr_attendance_base.controllers.kiosk import issue_pairing_pin


@tagged('post_install', '-at_install')
class TestKioskHttpEndpoints(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.site = cls.env['eh.hr.kiosk.site'].create({
            'name': 'HTTP Test Site',
            'code': 'http-test',
            'company_id': cls.env.company.id,
        })

    def test_pair_with_valid_pin_returns_token(self):
        pin = issue_pairing_pin(self.site.code)
        body = json.dumps({
            'site_code': self.site.code,
            'pin': pin,
            'device_name': 'Test device',
        })
        response = self.url_open(
            '/eh_hr/kiosk/pair',
            data=body,
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('device_token', payload)
        self.assertEqual(payload['site_code'], self.site.code)

        Device = self.env['eh.hr.kiosk.terminal'].sudo()
        device = Device.search([('device_token', '=', payload['device_token'])], limit=1)
        self.assertTrue(device)
        self.assertEqual(device.site_id, self.site)

    def test_pair_with_wrong_site_code_rejects(self):
        pin = issue_pairing_pin(self.site.code)
        response = self.url_open(
            '/eh_hr/kiosk/pair',
            data=json.dumps({'site_code': 'no-such-site', 'pin': pin}),
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 403)

    def test_pair_missing_pin_returns_400(self):
        response = self.url_open(
            '/eh_hr/kiosk/pair',
            data=json.dumps({'site_code': self.site.code}),
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 400)

    def test_heartbeat_without_token_returns_401(self):
        response = self.url_open(
            '/eh_hr/kiosk/heartbeat',
            data='{}',
            headers={'Content-Type': 'application/json'},
        )
        self.assertEqual(response.status_code, 401)

    def test_whoami_with_valid_token(self):
        device = self.env['eh.hr.kiosk.terminal'].sudo().create({
            'name': 'Whoami test',
            'site_id': self.site.id,
        })
        response = self.url_open(
            '/eh_hr/kiosk/whoami',
            headers={'X-EH-Kiosk-Token': device.device_token},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['site_code'], self.site.code)
        self.assertEqual(payload['device_id'], device.id)
