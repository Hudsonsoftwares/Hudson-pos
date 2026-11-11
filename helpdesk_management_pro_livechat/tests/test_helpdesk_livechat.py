# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests import HttpCase, tagged
# pyrefly: ignore [missing-import]
from odoo.addons.mail.tests.common import mail_new_test_user


@tagged('post_install', '-at_install')
class TestHelpdeskLivechat(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.team = cls.env['helpdesk.management.team'].create({'name': 'Chat Support', 'use_livechat': True})
        cls.chatbot = cls.env.ref('helpdesk_management_pro_livechat.chatbot_script_helpdesk_bot')
        cls.step_create_ticket = cls.env.ref('helpdesk_management_pro_livechat.chatbot_script_helpdesk_step_create_ticket')
        cls.step_create_ticket.helpdesk_team_id = cls.team
        cls.livechat_channel = cls.env['im_livechat.channel'].create({
            'name': 'Support Chat',
            'rule_ids': [(0, 0, {'chatbot_script_id': cls.chatbot.id})],
        })

    def _post_and_trigger(self, channel, body, contact_info=False):
        self.make_jsonrpc_request('/mail/message/post', {
            'thread_model': 'discuss.channel',
            'thread_id': channel.id,
            'post_data': {'body': body, 'message_type': 'comment', 'subtype_xmlid': 'mail.mt_comment'},
        })
        if contact_info:
            self.make_jsonrpc_request('/chatbot/step/validate_contact_info', {'channel_id': channel.id})
        self.make_jsonrpc_request('/chatbot/step/trigger', {'channel_id': channel.id})

    def test_chatbot_creates_ticket_for_visitor(self):
        """ A website visitor chatting with the Helpdesk Bot gets a ticket with their data and the conversation """
        data = self.make_jsonrpc_request('/im_livechat/get_session', {
            'channel_id': self.livechat_channel.id, 'chatbot_script_id': self.chatbot.id,
        })
        channel = self.env['discuss.channel'].sudo().browse(data['channel_id'])
        self._post_and_trigger(channel, 'My printer does not print anymore')
        self._post_and_trigger(channel, 'chat.visitor@example.com', contact_info=True)
        self._post_and_trigger(channel, '+32 470 12 34 56', contact_info=True)
        self.assertEqual(channel.chatbot_current_step_id, self.step_create_ticket)

        ticket = self.env['helpdesk.management.ticket'].search([('origin_channel_id', '=', channel.id)])
        self.assertEqual(len(ticket), 1)
        self.assertEqual(ticket.subject, 'My printer does not print anymore')
        self.assertEqual(ticket.team_id, self.team)
        self.assertEqual(ticket.chatbot_script_id, self.chatbot)
        self.assertEqual(ticket.partner_id.email, 'chat.visitor@example.com')
        self.assertEqual(ticket.partner_email, 'chat.visitor@example.com')
        self.assertIn('My printer does not print anymore', ticket.description)
        self.assertIn('chat.visitor@example.com', ticket.description)
        self.assertIn('+32 470 12 34 56', ticket.description)
        # The visitor gets the ticket reference in the chat
        self.assertIn(ticket.name, channel.message_ids[:1].body)
        self.assertEqual(self.chatbot.helpdesk_ticket_count, 1)
        self.assertEqual(self.chatbot.action_view_helpdesk_tickets()['domain'], [('chatbot_script_id', '=', self.chatbot.id)])

    def test_operator_ticket_command(self):
        """ "/ticket <subject>" typed by an operator creates a ticket for the chat's customer """
        operator = mail_new_test_user(
            self.env, login='chat_agent', groups='im_livechat.im_livechat_group_user,helpdesk_management_pro.group_helpdesk_user')
        customer = mail_new_test_user(self.env, login='chat_customer', groups='base.group_portal')
        operator_channel = self.env['im_livechat.channel'].create({'name': 'Agents Chat', 'user_ids': [(6, 0, operator.ids)]})
        self.env['mail.presence']._update_presence(operator)
        # The customer starts a chat with the operator on the website
        self.authenticate('chat_customer', 'chat_customer')
        data = self.make_jsonrpc_request('/im_livechat/get_session', {'channel_id': operator_channel.id})
        channel = self.env['discuss.channel'].browse(data['channel_id'])
        channel.message_post(author_id=customer.partner_id.id, body='My invoice is wrong', message_type='comment')

        channel.with_user(operator).execute_command_ticket(body='/ticket Wrong invoice')
        ticket = channel.sudo().helpdesk_ticket_ids
        self.assertEqual(ticket.subject, 'Wrong invoice')
        self.assertEqual(ticket.team_id, self.team)
        self.assertEqual(ticket.user_id, operator)
        self.assertEqual(ticket.partner_id, customer.partner_id)
        self.assertIn('My invoice is wrong', ticket.description)
