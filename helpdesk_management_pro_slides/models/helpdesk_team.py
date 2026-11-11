# -*- coding: utf-8 -*-
from odoo import api, fields, models

class HelpdeskTeam(models.Model):
    _inherit = 'helpdesk.management.team'

    use_website_helpdesk_elearning = fields.Boolean('eLearning')
    website_slide_channel_ids = fields.Many2many(
        'slide.channel', 'helpdesk_team_slide_channel_rel', 'team_id', 'channel_id',
        string='eLearning Courses', help="Courses shown to customers in the help center of this team.")

    @api.model
    def _get_help_center_feature_fields(self):
        res = super()._get_help_center_feature_fields()
        return res + ['use_website_helpdesk_elearning']

    def _get_help_center_content(self):
        res = super()._get_help_center_content()
        course_teams = self.filtered('use_website_helpdesk_elearning')
        if course_teams:
            res['courses'] = course_teams.website_slide_channel_ids.filtered('website_published')
            res['show_elearning'] = bool(course_teams)
        return res
