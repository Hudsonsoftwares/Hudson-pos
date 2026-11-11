# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.exceptions import AccessError
# pyrefly: ignore [missing-import]
from odoo.tests import HttpCase, new_test_user, tagged


@tagged('post_install', '-at_install')
class TestHelpdeskForum(HttpCase):
    """ Website forum <-> helpdesk connection: tickets from forum questions, tickets shared on the forum. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.forum = cls.env['forum.forum'].create({'name': 'Support Community'})
        cls.team = cls.env['helpdesk.management.team'].create({
            'name': 'Community Support',
            'use_website_helpdesk_forum': True,
            'forum_id': cls.forum.id,
        })
        cls.agent = new_test_user(cls.env, login='hd_forum_agent', groups='base.group_user,helpdesk_management_pro.group_helpdesk_user')
        cls.employee = new_test_user(cls.env, login='hd_forum_employee', groups='base.group_user')
        cls.customer = new_test_user(cls.env, login='hd_forum_customer', groups='base.group_portal')
        cls.customer.karma = 100
        cls.question = cls.env['forum.post'].with_user(cls.customer).create({
            'forum_id': cls.forum.id, 'name': 'My router keeps rebooting', 'content': '<p>Since yesterday.</p>',
        })

    def _question_url(self):
        return f'/forum/{self.env["ir.http"]._slug(self.forum)}/{self.env["ir.http"]._slug(self.question)}'

    def test_create_ticket_from_forum_question(self):
        """ A helpdesk user creates a ticket from a question of the website forum, then reopens the same one """
        self.authenticate('hd_forum_agent', 'hd_forum_agent')
        page = self.url_open(self._question_url())
        self.assertEqual(page.status_code, 200)
        self.assertIn('Create Helpdesk Ticket', page.text)

        res = self.url_open(f'/helpdesk/forum/post/{self.question.id}/create_ticket',
                            data={'csrf_token': self.csrf_token()}, allow_redirects=False)
        self.assertEqual(res.status_code, 303)
        ticket = self.question.helpdesk_ticket_id
        self.assertTrue(ticket, "The question is linked to the created ticket")
        self.assertTrue(res.headers['Location'].endswith(f'/odoo/helpdesk.management.ticket/{ticket.id}'))
        self.assertEqual(ticket.subject, 'My router keeps rebooting')
        self.assertEqual(ticket.team_id, self.team, "The ticket goes to the team using this forum")
        self.assertEqual(ticket.partner_id, self.customer.partner_id, "The author of the question is the customer")
        self.assertEqual(ticket.forum_post_id, self.question)
        self.assertEqual(ticket.forum_post_count, 1)

        # Same question again: the existing ticket is opened, no duplicate
        self.url_open(f'/helpdesk/forum/post/{self.question.id}/create_ticket',
                      data={'csrf_token': self.csrf_token()}, allow_redirects=False)
        self.assertEqual(self.env['helpdesk.management.ticket'].search_count([('forum_post_id', '=', self.question.id)]), 1)
        page = self.url_open(self._question_url())
        self.assertIn('View Helpdesk Ticket', page.text)
        self.assertNotIn('Create Helpdesk Ticket', page.text)

    def test_create_ticket_reserved_to_helpdesk_users(self):
        self.authenticate('hd_forum_employee', 'hd_forum_employee')
        page = self.url_open(self._question_url())
        self.assertNotIn('Create Helpdesk Ticket', page.text)
        res = self.url_open(f'/helpdesk/forum/post/{self.question.id}/create_ticket',
                            data={'csrf_token': self.csrf_token()}, allow_redirects=False)
        self.assertEqual(res.status_code, 403)
        self.assertFalse(self.question.helpdesk_ticket_id)
        with self.assertRaises(AccessError):
            self.question.with_user(self.employee)._helpdesk_create_ticket()

    def test_backend_create_ticket_from_post(self):
        action = self.question.with_user(self.agent).action_create_helpdesk_ticket()
        self.assertEqual(action['res_model'], 'helpdesk.management.ticket')
        self.assertEqual(action['res_id'], self.question.helpdesk_ticket_id.id)

    def test_share_ticket_on_forum(self):
        """ A ticket is shared on the team forum by an agent without forum karma, and linked to the post """
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': 'Printer offline', 'description': '<p>Restart the spooler.</p>', 'team_id': self.team.id,
            'user_id': self.agent.id,
        })
        self.assertEqual(self.agent.karma, 0)
        action = ticket.with_user(self.agent).action_share_on_forum()
        wizard = self.env[action['res_model']].with_user(self.agent).with_context(action['context']).create({})
        self.assertEqual(wizard.forum_id, self.forum, "The team forum is proposed")
        self.assertEqual(wizard.name, 'Printer offline')
        result = wizard.action_share()

        post = ticket.forum_post_ids
        self.assertEqual(len(post), 1)
        self.assertEqual(post.forum_id, self.forum)
        self.assertEqual(post.name, 'Printer offline')
        self.assertEqual(post.create_uid, self.agent, "The post is authored by the agent")
        self.assertEqual(ticket.forum_post_id, post)
        self.assertEqual(ticket.forum_post_count, 1)
        self.assertEqual(result['url'], post.website_url)
        self.assertEqual(ticket.with_user(self.agent).action_view_forum_posts()['url'], post.website_url)


@tagged('post_install', '-at_install')
class TestHelpdeskTicketPreview(HttpCase):
    """ "Preview" action of the ticket form: opens the customer portal page of the ticket. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.team = cls.env['helpdesk.management.team'].create({'name': 'Preview Team'})
        cls.customer = new_test_user(cls.env, login='hd_preview_customer', groups='base.group_portal')
        cls.agent = new_test_user(cls.env, login='hd_preview_agent', groups='base.group_user,helpdesk_management_pro.group_helpdesk_user')
        cls.ticket = cls.env['helpdesk.management.ticket'].create({
            'subject': 'Preview me', 'description': '<p>Broken <b>screen</b></p>',
            'team_id': cls.team.id, 'partner_id': cls.customer.partner_id.id,
        })

    def test_preview_action_and_page(self):
        action = self.ticket.with_user(self.agent).action_preview_ticket()
        self.assertEqual(action['type'], 'ir.actions.act_url')
        # The helpdesk user previewing the ticket sees the customer page
        self.authenticate('hd_preview_agent', 'hd_preview_agent')
        res = self.url_open(action['url'])
        self.assertEqual(res.status_code, 200)
        self.assertIn('Preview me', res.text)
        self.assertIn('Broken <b>screen</b>', res.text, "The HTML description is rendered")

    def test_preview_page_customer_and_token(self):
        self.authenticate('hd_preview_customer', 'hd_preview_customer')
        res = self.url_open(f'/my/ticket/{self.ticket.id}')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Preview me', res.text)
        self.authenticate(None, None)
        res = self.url_open(f'/my/ticket/{self.ticket.id}?access_token={self.ticket.access_token}')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Preview me', res.text)
