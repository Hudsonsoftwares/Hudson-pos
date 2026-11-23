# -*- coding: utf-8 -*-
from odoo import api, fields, models


class KnowledgeItem(models.Model):
    _name = 'knowledge.management.item'
    _description = 'Knowledge Article Item'
    _inherit = ['mail.thread']
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, default='New Item', tracking=True)
    article_id = fields.Many2one(
        'knowledge.management.article',
        string='Article',
        required=True,
        ondelete='cascade',
        index=True,
    )
    # Tag that groups items into a specific embedded view block
    # Multiple embedded views can exist per article; each has a unique view_ref_id
    view_ref_id = fields.Char(
        string='View Reference ID',
        help='Groups items belonging to the same embedded view block',
        index=True,
    )
    view_type = fields.Selection([
        ('kanban', 'Kanban'),
        ('list', 'List'),
        ('calendar', 'Calendar'),
    ], string='View Type', required=True, default='kanban')

    stage_id = fields.Many2one(
        'knowledge.management.item.stage',
        string='Stage',
        domain="[('article_id', '=', article_id)]",
        ondelete='set null',
        group_expand='_read_group_stage_ids',
        tracking=True,
    )

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        article_id = self.env.context.get('default_article_id')
        if not article_id and isinstance(domain, list):
            for item in domain:
                if isinstance(item, (list, tuple)) and len(item) == 3 and item[0] == 'article_id' and item[1] == '=':
                    article_id = item[2]
                    break
        search_domain = [('article_id', '=', article_id)] if article_id else []
        found_stages = self.env['knowledge.management.item.stage'].search(search_domain, order='sequence, id')
        if not found_stages and article_id:
            self.env['knowledge.management.item.stage'].create([{
                'name': 'New',
                'article_id': article_id,
                'sequence': 10,
                'fold': False,
            }, {
                'name': 'Ongoing',
                'article_id': article_id,
                'sequence': 20,
                'fold': False,
            }, {
                'name': 'Done',
                'article_id': article_id,
                'sequence': 30,
                'fold': True,
            }])
            found_stages = self.env['knowledge.management.item.stage'].search(search_domain, order='sequence, id')
        return found_stages
    date = fields.Date(string='Date')
    date_end = fields.Date(string='End Date')
    description = fields.Text(string='Description')
    user_id = fields.Many2one('res.users', string='Assigned To', default=lambda self: self.env.user)
    color = fields.Integer(string='Color')
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)

    child_article_id = fields.Many2one(
        'knowledge.management.article',
        string='Linked Article',
        ondelete='cascade',
        index=True,
    )

    # Kanban state
    kanban_state = fields.Selection([
        ('normal', 'In Progress'),
        ('done', 'Ready'),
        ('blocked', 'Blocked'),
    ], string='Kanban State', default='normal')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('child_article_id') and vals.get('article_id'):
                parent_art = self.env['knowledge.management.article'].browse(vals['article_id'])
                if parent_art.exists():
                    child_art = self.env['knowledge.management.article'].create({
                        'name': vals.get('name') or 'New Item',
                        'parent_id': parent_art.id,
                        'visibility': parent_art.visibility or 'workspace',
                        'is_article_item': True,
                        'body_html': '<h1><br></h1><p><br></p>',
                    })
                    vals['child_article_id'] = child_art.id
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        if 'name' in vals:
            for item in self:
                if item.child_article_id and item.child_article_id.name != vals['name']:
                    item.child_article_id.write({'name': vals['name']})
        return res

    def unlink(self):
        child_articles = self.mapped('child_article_id')
        res = super().unlink()
        if child_articles:
            child_articles.unlink()
        return res

    @api.model
    def get_items_for_view(self, article_id, view_ref_id):
        """Return items for a specific embedded view block."""
        items = self.search([
            ('article_id', '=', article_id),
            ('view_ref_id', '=', view_ref_id),
            ('active', '=', True),
        ], order='sequence, id')
        return [{
            'id': item.id,
            'name': item.name,
            'child_article_id': item.child_article_id.id if item.child_article_id else False,
            'stage_id': item.stage_id.id if item.stage_id else False,
            'stage_name': item.stage_id.name if item.stage_id else '',
            'date': item.date.isoformat() if item.date else False,
            'date_end': item.date_end.isoformat() if item.date_end else False,
            'description': item.description or '',
            'user_id': item.user_id.id if item.user_id else False,
            'user_name': item.user_id.name if item.user_id else '',
            'color': item.color,
            'kanban_state': item.kanban_state,
        } for item in items]

    @api.model
    def get_stages_for_view(self, article_id):
        """Return kanban stages for an article."""
        stages = self.env['knowledge.management.item.stage'].search([
            ('article_id', '=', article_id),
        ], order='sequence, id')
        if not stages and article_id:
            self.env['knowledge.management.item.stage'].create([{
                'name': 'New',
                'article_id': article_id,
                'sequence': 10,
                'fold': False,
            }, {
                'name': 'Ongoing',
                'article_id': article_id,
                'sequence': 20,
                'fold': False,
            }, {
                'name': 'Done',
                'article_id': article_id,
                'sequence': 30,
                'fold': True,
            }])
            stages = self.env['knowledge.management.item.stage'].search([
                ('article_id', '=', article_id),
            ], order='sequence, id')
        return [{
            'id': s.id,
            'name': s.name,
            'sequence': s.sequence,
            'fold': s.fold,
        } for s in stages]
