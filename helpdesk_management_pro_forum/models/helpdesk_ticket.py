# -*- coding: utf-8 -*-
from odoo import fields, models, api, _

class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.management.ticket'

    use_website_helpdesk_forum = fields.Boolean(related='team_id.use_website_helpdesk_forum')
    team_forum_id = fields.Many2one(related='team_id.forum_id', string='Team Forum')
    forum_post_id = fields.Many2one('forum.post', string='Forum Post', help='Link this ticket to a community forum post')
    forum_post_ids = fields.One2many('forum.post', 'helpdesk_ticket_id', string='Forum Posts')
    forum_post_count = fields.Integer(compute='_compute_forum_post_count')

    def _get_forum_posts(self):
        self.ensure_one()
        return self.forum_post_ids | self.forum_post_id

    @api.depends('forum_post_ids', 'forum_post_id')
    def _compute_forum_post_count(self):
        for ticket in self:
            ticket.forum_post_count = len(ticket._get_forum_posts())

    def action_share_on_forum(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Share on Forum'),
            'res_model': 'helpdesk.ticket.share.forum',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_ticket_id': self.id},
        }

    def action_view_forum_posts(self):
        self.ensure_one()
        posts = self._get_forum_posts()
        if len(posts) == 1:
            return {
                'type': 'ir.actions.act_url',
                'url': posts.website_url,
                'target': 'new',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': _('Forum Posts'),
            'res_model': 'forum.post',
            'view_mode': 'list,form',
            'domain': [('id', 'in', posts.ids)],
            'context': {'create': False},
        }
