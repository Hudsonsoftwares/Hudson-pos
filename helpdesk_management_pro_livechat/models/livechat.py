# -*- coding: utf-8 -*-
from markupsafe import Markup

# pyrefly: ignore [missing-import]
from odoo import _, api, fields, models
# pyrefly: ignore [missing-import]
from odoo.tools import html2plaintext


class ChatbotScriptStep(models.Model):
    _inherit = 'chatbot.script.step'

    step_type = fields.Selection(
        selection_add=[('create_ticket', 'Create Ticket')],
        ondelete={'create_ticket': 'cascade'},
    )
    helpdesk_team_id = fields.Many2one(
        'helpdesk.management.team', string='Helpdesk Team', ondelete='set null', index='btree_not_null',
        help="Team of the tickets created by this step. Defaults to the first team using Live Chat.")

    def _process_step(self, discuss_channel):
        self.ensure_one()
        if self.step_type != 'create_ticket':
            return super()._process_step(discuss_channel)
        ticket = self._process_step_create_ticket(discuss_channel)
        # The step message is posted with the ticket reference, so the customer can follow it up
        body = Markup('%s') % (self.message or '')
        if ticket:
            reference = _("Your ticket reference is %(ref)s.", ref=ticket.name)
            body = Markup('%s<br/>%s') % (body, reference) if self.message else Markup('%s') % reference
        return {'message': discuss_channel._chatbot_post_message(self.chatbot_script_id, body)}

    def _get_helpdesk_team(self):
        Team = self.env['helpdesk.management.team'].sudo()
        return self.helpdesk_team_id.sudo() or Team.search([('use_livechat', '=', True)], limit=1) or Team.search([], limit=1)

    def _chatbot_prepare_ticket_values(self, discuss_channel, customer_values):
        team = self._get_helpdesk_team()
        subject = _("%s's New Ticket", self.chatbot_script_id.title)
        if msg := self._find_first_user_free_input(discuss_channel.sudo()):
            subject = (html2plaintext(msg.body) or subject).strip().splitlines()[0][:100]
        partner = customer_values['partner']
        vals = {
            'subject': subject,
            'description': customer_values['description'] + discuss_channel._get_channel_history(),
            'team_id': team.id,
            'origin_channel_id': discuss_channel.id,
            'chatbot_script_id': self.chatbot_script_id.id,
        }
        if team.company_id:
            vals['company_id'] = team.company_id.id
        if partner:
            vals['partner_id'] = partner.id
        else:
            vals.update({
                'partner_email': customer_values['email'] or False,
                'partner_phone': customer_values['phone'] or False,
            })
        return vals

    def _process_step_create_ticket(self, discuss_channel):
        """ When reaching a 'create_ticket' step, create a helpdesk ticket holding the visitor's
        contact details (email / phone questions) and the whole conversation as description.

        A visitor who left an email address gets a contact (like the website ticket form), so they
        receive the ticket notifications; logged-in customers are linked directly. """
        # Visitors (public users / guests) cannot create tickets or contacts: the bot creates them
        customer_values = self._chatbot_prepare_customer_values(
            discuss_channel, create_partner=False, update_partner=True)
        if not customer_values['partner'] and customer_values['email']:
            Partner = self.env['res.partner'].sudo()
            customer_values['partner'] = Partner.search(
                [('email', '=ilike', customer_values['email'])], limit=1) or Partner.create({
                    'name': customer_values['email'],
                    'email': customer_values['email'],
                    'phone': customer_values['phone'] or False,
                })
        Ticket = self.env['helpdesk.management.ticket'].sudo()
        ticket = Ticket.create(self._chatbot_prepare_ticket_values(discuss_channel, customer_values))
        ticket.message_post(
            body=_("Ticket created by the chatbot %(bot)s from a live chat conversation.",
                   bot=self.chatbot_script_id.title),
            message_type='comment', subtype_xmlid='mail.mt_note')
        return ticket


class ChatbotScript(models.Model):
    _inherit = 'chatbot.script'

    helpdesk_ticket_count = fields.Integer(string='Generated Ticket Count', compute='_compute_helpdesk_ticket_count')

    def _compute_helpdesk_ticket_count(self):
        data = dict(self.env['helpdesk.management.ticket'].with_context(active_test=False).sudo()._read_group(
            [('chatbot_script_id', 'in', self.ids)], ['chatbot_script_id'], ['__count']))
        for script in self:
            script.helpdesk_ticket_count = data.get(script, 0)

    def action_view_helpdesk_tickets(self):
        self.ensure_one()
        return {
            'name': _('Tickets'),
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.management.ticket',
            'view_mode': 'list,kanban,form',
            'domain': [('chatbot_script_id', '=', self.id)],
            'context': {'create': False},
        }


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    helpdesk_ticket_ids = fields.One2many(
        'helpdesk.management.ticket', 'origin_channel_id', string='Helpdesk Tickets',
        groups='helpdesk_management_pro.group_helpdesk_user')

    def execute_command_ticket(self, **kwargs):
        """ Operator command "/ticket <subject>": create a ticket from the conversation. """
        key = (kwargs.get('body') or '').strip()
        command = '/ticket'
        if key == command:
            msg = _("Create a new helpdesk ticket with: %(pre_start)s%(cmd)s %(i_start)sticket subject%(i_end)s%(pre_end)s",
                    cmd=command, pre_start=Markup('<pre>'), pre_end=Markup('</pre>'),
                    i_start=Markup('<i>'), i_end=Markup('</i>'))
            self.env.user._bus_send_transient_message(self, msg)
            return
        subject = key[len(command):].strip() if key.startswith(command) else key
        ticket = self._convert_visitor_to_helpdesk_ticket(subject)
        msg = Markup('<div class="o_mail_notification" data-oe-type="create-ticket">%s</div>') % _(
            "created a new ticket: %s", ticket._get_html_link())
        self.message_post(body=msg, message_type='notification')

    def _convert_visitor_to_helpdesk_ticket(self, subject):
        self.ensure_one()
        customer = self.livechat_customer_partner_ids[:1]
        team = self.env['helpdesk.management.team'].search([('use_livechat', '=', True)], limit=1)
        vals = {
            'subject': subject or _("Live Chat Ticket"),
            'description': self._get_channel_history(),
            'partner_id': customer.id or False,
            'origin_channel_id': self.id,
            'user_id': self.env.user.id,
        }
        if team:
            vals['team_id'] = team.id
        # Agents need ticket create rights: the access rules of the helpdesk apply
        return self.env['helpdesk.management.ticket'].create(vals)
