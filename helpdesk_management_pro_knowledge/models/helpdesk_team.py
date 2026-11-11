# -*- coding: utf-8 -*-
# pyrefly: ignore[missing-import]
from odoo import api, fields, models


class HelpdeskManagementTeam(models.Model):
    _inherit = 'helpdesk.management.team'

    use_website_helpdesk_knowledge = fields.Boolean('Knowledge')
    website_article_id = fields.Many2one(
        'knowledge.management.article', string='Knowledge Article',
        domain=[('is_article_item', '=', False)],
        help="Article (and its sub-articles) published to the help center of this team.")

    @api.model_create_multi
    def create(self, vals_list):
        teams = super().create(vals_list)
        teams._publish_knowledge_article()
        return teams

    def write(self, vals):
        res = super().write(vals)
        if {'use_website_helpdesk_knowledge', 'website_article_id'} & set(vals):
            self._publish_knowledge_article()
        return res

    def _publish_knowledge_article(self):
        """ Share the help center article and its sub-articles to the web, as the standard
        helpdesk knowledge integration publishes the team article. """
        for team in self.filtered(lambda t: t.use_website_helpdesk_knowledge and t.website_article_id):
            article = team.website_article_id.sudo()
            if not article.share_to_web:
                article.set_share_to_web(True)

    @api.model
    def _get_help_center_feature_fields(self):
        return super()._get_help_center_feature_fields() + ['use_website_helpdesk_knowledge']

    def _get_help_center_content(self):
        content = super()._get_help_center_content()
        knowledge_teams = self.filtered(lambda t: t.use_website_helpdesk_knowledge and t.website_article_id)
        articles = self.env['knowledge.management.article'].sudo()
        if knowledge_teams:
            articles = articles.search([
                ('id', 'child_of', knowledge_teams.website_article_id.ids),
                ('share_to_web', '=', True),
                ('is_article_item', '=', False),
            ], order='sequence, id')
        content.update({
            'show_knowledge': bool(knowledge_teams),
            'root_articles': knowledge_teams.website_article_id.filtered('share_to_web'),
            'articles': articles,
        })
        return content
