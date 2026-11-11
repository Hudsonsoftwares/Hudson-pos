# -*- coding: utf-8 -*-
# pyrefly: ignore[missing-import]
from odoo import _, fields, models
# pyrefly: ignore[missing-import]
from odoo.exceptions import AccessError, UserError


class ForumPost(models.Model):
    _inherit = 'forum.post'

    helpdesk_ticket_id = fields.Many2one(
        'helpdesk.management.ticket', string='Helpdesk Ticket', index='btree_not_null', copy=False,
        ondelete='set null', help="Ticket created from this post, or ticket this post was shared from.")

    def _helpdesk_get_team(self):
        """ Team receiving the tickets created from this forum: the team using it as community forum. """
        self.ensure_one()
        Team = self.env['helpdesk.management.team']
        return Team.search([('use_website_helpdesk_forum', '=', True), ('forum_id', '=', self.forum_id.id)], limit=1) \
            or Team.search([], limit=1)

    def _helpdesk_create_ticket(self):
        """ Create a helpdesk ticket from this question (or return the one already linked). Requires a helpdesk user. """
        self.ensure_one()
        if not self.env.user.has_group('helpdesk_management_pro.group_helpdesk_user'):
            raise AccessError(_("Only helpdesk users can create a ticket from a forum post."))
        question = self.parent_id or self
        if question.helpdesk_ticket_id:
            return question.helpdesk_ticket_id
        team = question._helpdesk_get_team()
        if not team:
            raise UserError(_("Create a helpdesk team before creating tickets from the forum."))
        author = question.create_uid.partner_id
        ticket = self.env['helpdesk.management.ticket'].create({
            'subject': question.name,
            'description': question.content,
            'team_id': team.id,
            'partner_id': author.id if author and not question.create_uid._is_public() else False,
            'forum_post_id': question.id,
        })
        # sudo: linking the post must not depend on the agent's forum karma
        question.sudo().helpdesk_ticket_id = ticket
        ticket.message_post(body=_("Ticket created from the forum post %s", question._get_html_link()))
        return ticket

    def action_create_helpdesk_ticket(self):
        """ Backend button: create (or open) the helpdesk ticket of this forum post. """
        ticket = self._helpdesk_create_ticket()
        return {
            'type': 'ir.actions.act_window',
            'name': ticket.display_name,
            'res_model': 'helpdesk.management.ticket',
            'res_id': ticket.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
        }
