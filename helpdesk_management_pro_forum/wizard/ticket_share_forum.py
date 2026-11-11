# -*- coding: utf-8 -*-
# pyrefly: ignore[missing-import]
from odoo import _, api, fields, models


class TicketShareForum(models.TransientModel):
    _name = 'helpdesk.ticket.share.forum'
    _description = 'Share a Helpdesk Ticket on a Forum'

    ticket_id = fields.Many2one('helpdesk.management.ticket', required=True, readonly=True, ondelete='cascade')
    forum_id = fields.Many2one('forum.forum', string='Forum', required=True)
    name = fields.Char(string='Title', required=True)
    content = fields.Html(string='Question',
                          help="Review it before sharing: the forum is public, remove any confidential information.")
    tag_ids = fields.Many2many('forum.tag', string='Tags', domain="[('forum_id', '=', forum_id)]")

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        ticket = self.env['helpdesk.management.ticket'].browse(defaults.get('ticket_id')).exists()
        if ticket:
            # The team forum first, otherwise the forum of any helpdesk team
            forum = ticket.team_id.forum_id or self.env['helpdesk.management.team'].search(
                [('use_website_helpdesk_forum', '=', True), ('forum_id', '!=', False)], limit=1).forum_id
            defaults.setdefault('forum_id', forum.id)
            defaults.setdefault('name', ticket.subject)
            defaults.setdefault('content', ticket.description)
        return defaults

    @api.onchange('forum_id')
    def _onchange_forum_id(self):
        self.tag_ids = self.tag_ids.filtered(lambda tag: tag.forum_id == self.forum_id)

    def action_share(self):
        self.ensure_one()
        ticket = self.ticket_id
        ticket.check_access('write')
        # sudo: the agent shares on behalf of the helpdesk whatever their forum karma; the post stays authored
        # by the agent (sudo keeps the current user)
        post = self.env['forum.post'].sudo().create({
            'forum_id': self.forum_id.id,
            'name': self.name,
            'content': self.content or '',
            'tag_ids': [(6, 0, self.tag_ids.ids)],
            'helpdesk_ticket_id': ticket.id,
        })
        if not ticket.forum_post_id:
            ticket.forum_post_id = post
        ticket.message_post(body=_("Ticket shared on the forum: %s", post._get_html_link()))
        return {
            'type': 'ir.actions.act_url',
            'url': post.website_url,
            'target': 'new',
        }
