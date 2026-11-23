# -*- coding: utf-8 -*-
from odoo import models, fields, api


class KnowledgeArticleVersion(models.Model):
    _name = 'knowledge.management.article.version'
    _description = 'Knowledge Article Version Snapshot'
    _order = 'create_date desc, id desc'

    article_id = fields.Many2one(
        'knowledge.management.article',
        string='Article',
        required=True,
        ondelete='cascade',
        index=True,
    )
    name = fields.Char(string='Title Snapshot', required=True)
    body_html = fields.Html(string='Content Snapshot', sanitize=False)
    user_id = fields.Many2one(
        'res.users',
        string='Author',
        default=lambda self: self.env.user,
        index=True,
    )
