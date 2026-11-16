# -*- encoding: utf-8 -*-
import json
from unittest.mock import patch, MagicMock

# pyrefly: ignore [missing-import]
from werkzeug.wrappers import Response

# pyrefly: ignore [missing-import]
from odoo.tests.common import TransactionCase, tagged
# pyrefly: ignore [missing-import]
from odoo.addons.eh_hr_visitor.controllers.visitor import EhHrVisitorController

@tagged('post_install', '-at_install')
class TestVisitorEndpoints(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        company = cls.env.company
        cls.site = cls.env['eh.hr.kiosk.site'].create({
            'name': 'Visitor http site',
            'code': 'visitor-http',
            'company_id': company.id,
        })
        cls.device = cls.env['eh.hr.kiosk.terminal'].create({
            'name': 'Visitor http device',
            'site_id': cls.site.id,
        })
        cls.host = cls.env['hr.employee'].create({
            'name': 'Host User',
            'company_id': company.id,
            'work_email': 'host@example.com',
        })
        cls.purpose = cls.env.ref('eh_hr_visitor.purpose_meeting')
        cls.purpose.nda_required = False
        cls.purpose_with_nda = cls.env.ref('eh_hr_visitor.purpose_contractor')
        cls.purpose_with_nda.nda_required = True

    def setUp(self):
        super().setUp()
        self.controller = EhHrVisitorController()
        
    def _mock_request(self, token=None, json_data=None):
        mock_req = MagicMock()
        mock_req.env = self.env
        
        headers = {}
        if token:
            headers['X-EH-Kiosk-Token'] = token
            
        mock_req.httprequest.headers.get.side_effect = headers.get
        mock_req.httprequest.remote_addr = '127.0.0.1'
        
        if json_data is not None:
            mock_req.httprequest.data = json.dumps(json_data).encode('utf-8')
            
        def make_response(data, headers=None, status=200):
            return Response(data, status=status, headers=headers)
            
        mock_req.make_response = make_response
        return mock_req

    def test_bootstrap_unauthorized(self):
        with patch('odoo.addons.eh_hr_visitor.controllers.visitor.request', self._mock_request()):
            resp = self.controller.bootstrap()
            self.assertEqual(resp.status_code, 401)

    def test_bootstrap_returns_purposes_not_host_dump(self):
        with patch('odoo.addons.eh_hr_visitor.controllers.visitor.request', self._mock_request(self.device.device_token)):
            resp = self.controller.bootstrap()
            self.assertEqual(resp.status_code, 200)
            body = json.loads(resp.get_data(as_text=True))
            self.assertIn('purposes', body)
            self.assertGreater(len(body['purposes']), 0)
            self.assertEqual(body.get('hosts'), [])
            self.assertTrue(body.get('host_search'))

    def test_host_search_finds_host_by_query(self):
        with patch('odoo.addons.eh_hr_visitor.controllers.visitor.request', self._mock_request(self.device.device_token)):
            resp = self.controller.host_search(q='Host')
            self.assertEqual(resp.status_code, 200)
            body = json.loads(resp.get_data(as_text=True))
            host_names = {h['name'] for h in body['hosts']}
            self.assertIn('Host User', host_names)

    def test_host_search_requires_two_chars(self):
        with patch('odoo.addons.eh_hr_visitor.controllers.visitor.request', self._mock_request(self.device.device_token)):
            resp = self.controller.host_search(q='H')
            self.assertEqual(resp.status_code, 200)
            body = json.loads(resp.get_data(as_text=True))
            self.assertEqual(body['hosts'], [])

    def test_sign_in_creates_record(self):
        data = {
            'name': 'Visitor One',
            'visitor_company': 'Vendor Co',
            'host_id': self.host.id,
            'purpose_id': self.purpose.id,
        }
        with patch('odoo.addons.eh_hr_visitor.controllers.visitor.request', self._mock_request(self.device.device_token, data)):
            resp = self.controller.sign_in()
            self.assertEqual(resp.status_code, 200)
            body = json.loads(resp.get_data(as_text=True))
            self.assertTrue(body['ok'])
            self.assertTrue(body['visit_number'])

            Visitor = self.env['eh.hr.visitor'].sudo()
            v = Visitor.search([('id', '=', body['visitor_id'])])
            self.assertEqual(v.name, 'Visitor One')
            self.assertEqual(v.state, 'signed_in')

    def test_sign_in_nda_required_rejected_without_acceptance(self):
        data = {
            'name': 'Contractor One',
            'host_id': self.host.id,
            'purpose_id': self.purpose_with_nda.id,
            'nda_accepted': False,
        }
        with patch('odoo.addons.eh_hr_visitor.controllers.visitor.request', self._mock_request(self.device.device_token, data)):
            resp = self.controller.sign_in()
            self.assertEqual(resp.status_code, 400)

    def test_sign_in_missing_name_rejected(self):
        data = {
            'host_id': self.host.id,
            'purpose_id': self.purpose.id,
        }
        with patch('odoo.addons.eh_hr_visitor.controllers.visitor.request', self._mock_request(self.device.device_token, data)):
            resp = self.controller.sign_in()
            self.assertEqual(resp.status_code, 400)

    def test_sign_out_by_visit_number_closes_record(self):
        # Sign in
        signin_data = {
            'name': 'Will Leave',
            'host_id': self.host.id,
            'purpose_id': self.purpose.id,
        }
        with patch('odoo.addons.eh_hr_visitor.controllers.visitor.request', self._mock_request(self.device.device_token, signin_data)):
            signin = self.controller.sign_in()
            signin_body = json.loads(signin.get_data(as_text=True))
            visit_number = signin_body['visit_number']

        # Sign out
        signout_data = {'visit_number': visit_number}
        with patch('odoo.addons.eh_hr_visitor.controllers.visitor.request', self._mock_request(self.device.device_token, signout_data)):
            resp = self.controller.sign_out()
            self.assertEqual(resp.status_code, 200)
            body = json.loads(resp.get_data(as_text=True))
            self.assertTrue(body['ok'])

            Visitor = self.env['eh.hr.visitor'].sudo()
            v = Visitor.search([('visit_number', '=', visit_number)], limit=1)
            self.assertEqual(v.state, 'signed_out')

    def test_sign_out_unknown_number_returns_not_found(self):
        signout_data = {'visit_number': 'V999999999'}
        with patch('odoo.addons.eh_hr_visitor.controllers.visitor.request', self._mock_request(self.device.device_token, signout_data)):
            resp = self.controller.sign_out()
            self.assertEqual(resp.status_code, 200)
            body = json.loads(resp.get_data(as_text=True))
            self.assertFalse(body['ok'])
