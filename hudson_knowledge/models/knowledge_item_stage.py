# -*- coding: utf-8 -*-
from odoo import api, fields, models


class KnowledgeItemStage(models.Model):
    """Kanban stage of the article items of one parent article."""
    _name = 'knowledge.management.item.stage'
    _description = 'Knowledge Item Stage'
    _order = 'sequence, id'

    name = fields.Char(string='Stage Name', required=True, translate=False)
    sequence = fields.Integer(string='Sequence', default=10)
    article_id = fields.Many2one(
        'knowledge.management.article',
        string='Parent Article',
        ondelete='cascade',
        index=True,
    )
    fold = fields.Boolean(string='Folded in Kanban', default=False)
    color = fields.Integer(string='Color')

    _name_article_uniq = models.Constraint(
        'UNIQUE(name, article_id)',
        'Stage name must be unique per article.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        # "Add a column" in the embedded item kanban runs name_create with the
        # view context, which carries the parent article as default_parent_id.
        parent_id = self.env.context.get('default_parent_id')
        if parent_id:
            for vals in vals_list:
                vals.setdefault('article_id', parent_id)
        return super().create(vals_list)
