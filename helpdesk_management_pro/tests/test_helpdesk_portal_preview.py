# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestHelpdeskPortalPreview(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.team = cls.env['helpdesk.management.team'].create({'name': 'Preview Team'})
        cls.portal_user = cls.env['res.users'].create({
            'name': 'Preview Customer', 'login': 'preview_customer', 'password': 'preview_customer',
            'group_ids': [(6, 0, [cls.env.ref('base.group_portal').id])],
        })
        cls.ticket = cls.env['helpdesk.management.ticket'].create({
            'subject': 'Preview me', 'team_id': cls.team.id, 'partner_id': cls.portal_user.partner_id.id,
            'description': '<p>Broken printer</p>',
        })

    def test_preview_action(self):
        action = self.ticket.action_preview_ticket()
        self.assertEqual(action['type'], 'ir.actions.act_url')

    def test_preview_page_as_internal_user(self):
        self.authenticate('admin', 'admin')
        url = self.ticket.action_preview_ticket()['url']
        res = self.url_open(url)
        self.assertEqual(res.status_code, 200, res.text[-3000:])
        self.assertIn('Preview me', res.text)

    def test_preview_page_as_customer(self):
        self.authenticate('preview_customer', 'preview_customer')
        res = self.url_open(self.ticket.access_url)
        self.assertEqual(res.status_code, 200, res.text[-3000:])
        self.assertIn('Preview me', res.text)
