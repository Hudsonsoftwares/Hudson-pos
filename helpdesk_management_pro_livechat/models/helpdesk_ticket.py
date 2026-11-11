# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import _, fields, models


class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.management.ticket'

    origin_channel_id = fields.Many2one(
        'discuss.channel', string='Live Chat Conversation', copy=False, index='btree_not_null',
        ondelete='set null', help="Live chat conversation this ticket was created from.")
    chatbot_script_id = fields.Many2one(
        'chatbot.script', string='Chatbot', copy=False, index='btree_not_null',
        ondelete='set null', readonly=True, help="Chatbot that created this ticket.")

    def action_open_livechat(self):
        self.ensure_one()
        return {
            'name': _('Live Chat'),
            'type': 'ir.actions.act_window',
            'res_model': 'discuss.channel',
            'res_id': self.origin_channel_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
