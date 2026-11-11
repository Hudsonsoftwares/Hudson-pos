# -*- coding: utf-8 -*-
import re

# pyrefly: ignore [missing-import]
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestHelpdeskWebsite(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env['website'].search([], order='sequence, id', limit=1)
        cls.forum = cls.env['forum.forum'].create({'name': 'Helpdesk Forum'})
        cls.post = cls.env['forum.post'].create({
            'forum_id': cls.forum.id, 'name': 'How to reset my router', 'content': '<p>Unplug it.</p>',
        })
        cls.course = cls.env['slide.channel'].create({'name': 'Router Academy', 'is_published': True})
        cls.slide = cls.env['slide.slide'].create({
            'channel_id': cls.course.id, 'name': 'Router setup lesson', 'is_published': True,
        })
        cls.team = cls.env['helpdesk.management.team'].create({
            'name': 'Website Support',
            'use_website_helpdesk_form': True,
            'use_website_helpdesk_forum': True,
            'forum_id': cls.forum.id,
            'use_website_helpdesk_elearning': True,
            'website_slide_channel_ids': [(6, 0, cls.course.ids)],
        })
        cls.hidden_team = cls.env['helpdesk.management.team'].create({'name': 'Internal Only'})

    def test_help_center_teams_and_content(self):
        teams = self.env['helpdesk.management.team']._get_help_center_teams(self.website)
        self.assertIn(self.team, teams)
        self.assertNotIn(self.hidden_team, teams, "Teams without any help center feature are not exposed.")
        content = self.team._get_help_center_content()
        self.assertEqual(content['forums'], self.forum)
        self.assertEqual(content['courses'], self.course)
        self.assertTrue(self.team.website_url.startswith('/helpdesk/'))

    def test_help_center_pages_and_search(self):
        res = self.url_open('/helpdesk')
        self.assertEqual(res.status_code, 200)
        self.assertIn(self.forum.website_url, res.text)
        self.assertIn(self.course.website_url, res.text)

        res = self.url_open(self.team.website_url + '?search=router')
        self.assertEqual(res.status_code, 200)
        self.assertIn('How to reset my router', res.text)
        self.assertIn('Router setup lesson', res.text)

        res = self.url_open('/helpdesk/%s' % self.env['ir.http']._slug(self.hidden_team))
        self.assertEqual(res.status_code, 404)

        menu_urls = self.env['website.menu'].search([('website_id', '=', self.website.id)]).mapped('url')
        self.assertIn('/helpdesk', menu_urls, "The website menu links to the help center.")

    def test_website_ticket_submission(self):
        res = self.url_open('/helpdesk/submit?team_id=%s' % self.team.id)
        self.assertEqual(res.status_code, 200)
        csrf_token = re.search(r'name="csrf_token" value="([^"]+)"', res.text).group(1)
        res = self.url_open('/helpdesk/submit/process', data={
            'csrf_token': csrf_token,
            'team_id': self.team.id,
            'name': 'Web Customer',
            'email': 'web.customer@example.com',
            'subject': 'Router broken',
            'description': 'It does not boot',
        })
        self.assertEqual(res.status_code, 200)
        ticket = self.env['helpdesk.management.ticket'].search([('subject', '=', 'Router broken')])
        self.assertEqual(ticket.team_id, self.team, "Website tickets are routed to the team of the form.")
        self.assertEqual(ticket.partner_id.email, 'web.customer@example.com', "The customer is linked to the ticket.")

    def test_website_form_builder_create_ticket_action(self):
        model = self.env['ir.model']._get('helpdesk.management.ticket')
        self.assertTrue(model.website_form_access)
        self.assertEqual(model.website_form_key, 'create_ticket')
        self.assertEqual(model.website_form_label, 'Create a Ticket')
        self.assertEqual(model.website_form_default_field_id.name, 'description')
        self.assertIn('create_ticket', self.env['ir.model'].sudo().search(
            [('website_form_access', '=', True)]).mapped('website_form_key'))

        res = self.url_open('/website/form/helpdesk.management.ticket', data={
            'team_id': self.team.id,
            'partner_name': 'Form Builder Customer',
            'partner_email': 'builder.customer@example.com',
            'partner_phone': '+1 555 0100',
            'subject': 'Printer jammed',
            'description': 'Paper stuck in tray 2',
            'Order Reference': 'SO-042',
        })
        self.assertEqual(res.status_code, 200)
        ticket_id = res.json().get('id')
        self.assertTrue(ticket_id, res.text)
        ticket = self.env['helpdesk.management.ticket'].browse(ticket_id)
        self.assertEqual(ticket.subject, 'Printer jammed')
        self.assertEqual(ticket.team_id, self.team)
        self.assertEqual(ticket.partner_id.email, 'builder.customer@example.com')
        self.assertEqual(ticket.partner_name, 'Form Builder Customer')
        self.assertIn('Paper stuck in tray 2', ticket.description)
        self.assertIn('SO-042', ticket.description, "Custom form fields are kept on the ticket description.")

        # A team that does not accept website tickets cannot be forced from the form
        res = self.url_open('/website/form/helpdesk.management.ticket', data={
            'team_id': self.hidden_team.id,
            'partner_email': 'builder.customer@example.com',
            'subject': 'Tampered team',
        })
        ticket = self.env['helpdesk.management.ticket'].browse(res.json().get('id'))
        self.assertNotEqual(ticket.team_id, self.hidden_team)
        self.assertTrue(ticket.team_id.use_website_helpdesk_form)
