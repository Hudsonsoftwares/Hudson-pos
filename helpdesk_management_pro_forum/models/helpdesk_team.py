# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.fields import Domain

class HelpdeskTeam(models.Model):
    _inherit = 'helpdesk.management.team'

    use_website_helpdesk_forum = fields.Boolean('Community Forum')
    forum_id = fields.Many2one('forum.forum', string='Forums')

    @api.model
    def _get_help_center_feature_fields(self):
        res = super()._get_help_center_feature_fields()
        return res + ['use_website_helpdesk_forum']

    def _get_help_center_content(self):
        res = super()._get_help_center_content()
        forum_teams = self.filtered('use_website_helpdesk_forum')
        if forum_teams:
            res['forums'] = forum_teams.forum_id
            res['show_forum'] = bool(forum_teams.forum_id)
        return res

