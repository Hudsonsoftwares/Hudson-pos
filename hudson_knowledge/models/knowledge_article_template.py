# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError


class KnowledgeArticleTemplateCategory(models.Model):
    _name = 'knowledge.management.article.template.category'
    _description = 'Knowledge Article Template Category'
    _order = 'sequence, id'

    name = fields.Char(string='Category', required=True, translate=True)
    sequence = fields.Integer(default=10)
    template_ids = fields.One2many(
        'knowledge.management.article.template', 'category_id', string='Templates')


class KnowledgeArticleTemplate(models.Model):
    _name = 'knowledge.management.article.template'
    _description = 'Knowledge Article Template'
    _order = 'sequence, id'

    name = fields.Char(string='Template Name', required=True)
    description = fields.Char(string='Description')
    icon = fields.Char(string='Icon', default='📋')
    body_html = fields.Html(
        string='Template Body',
        sanitize=False,
        strip_style=False,
    )
    category_id = fields.Many2one(
        'knowledge.management.article.template.category', string='Category',
        ondelete='set null', index=True)
    cover_image_url = fields.Text(string='Cover Image URL')
    cover_position = fields.Char(string='Cover Position', default='50%')
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)

    def _prepare_article_vals(self):
        self.ensure_one()
        return {
            'name': self.name,
            'icon': self.icon,
            'body_html': self.body_html,
            'cover_image_url': self.cover_image_url or False,
            'cover_position': self.cover_position or '50%',
        }

    def action_use_template(self):
        """Create a new article from this template."""
        self.ensure_one()
        vals = self._prepare_article_vals()
        vals['visibility'] = 'private'
        article = self.env['knowledge.management.article'].create(vals)
        return {
            'type': 'ir.actions.client',
            'tag': 'hudson_knowledge.action_knowledge',
            'params': {'res_id': article.id},
        }

    @api.model
    def get_templates_by_category(self):
        """Templates grouped by category for the "Browse Templates" dialog.

        Templates without a category are listed under "Other" at the end.
        """
        templates = self.search([])
        groups = {}
        order = []
        for tmpl in templates:
            cat = tmpl.category_id
            key = cat.id or 0
            if key not in groups:
                groups[key] = {
                    'id': key,
                    'name': cat.name if cat else _('Other'),
                    'sequence': cat.sequence if cat else 10 ** 6,
                    'templates': [],
                }
                order.append(key)
            groups[key]['templates'].append({
                'id': tmpl.id,
                'name': tmpl.name,
                'icon': tmpl.icon or '📄',
                'description': tmpl.description or '',
                'body_html': tmpl.body_html or '',
                'cover_image_url': tmpl.cover_image_url or False,
                'cover_position': tmpl.cover_position or '50%',
                'can_delete': tmpl.create_uid == self.env.user
                or self.env.user.has_group('hudson_knowledge.group_knowledge_manager'),
            })
        return sorted((groups[k] for k in order), key=lambda g: (g['sequence'], g['id']))

    @api.model
    def get_template_categories(self):
        return self.env['knowledge.management.article.template.category'].search_read(
            [], ['id', 'name'])

    def action_delete_template(self):
        """Users may delete the templates they saved; managers any template."""
        is_manager = self.env.user.has_group('hudson_knowledge.group_knowledge_manager')
        for tmpl in self:
            if not is_manager and tmpl.create_uid != self.env.user:
                raise AccessError(_('You can only delete the templates you created.'))
        self.sudo().unlink()
        return True


class KnowledgeArticle(models.Model):
    _inherit = 'knowledge.management.article'

    def action_save_as_template(self, name=False, category_id=False):
        """Save the article (content, icon and cover) as a reusable template.

        Any Knowledge user who can read the article may save it; the template
        is created with sudo because users only have read access on templates.
        """
        self.ensure_one()
        self.check_access('read')
        category = self.env['knowledge.management.article.template.category']
        if category_id:
            category = category.browse(int(category_id)).exists()
        if not category:
            category = self.env.ref(
                'hudson_knowledge.knowledge_template_category_custom', raise_if_not_found=False) \
                or category
        template = self.env['knowledge.management.article.template'].sudo().create({
            'name': (name or '').strip() or self.name or _('Untitled'),
            'icon': self.icon or False,
            'body_html': self.body_html or '<p><br></p>',
            'cover_image_url': self.cover_image_url or False,
            'cover_position': self.cover_position or '50%',
            'category_id': category.id or False,
        })
        # sudo() keeps the uid, so create_uid is the real author (who may
        # later delete the template).
        return template.id
