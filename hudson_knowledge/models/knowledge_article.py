# -*- coding: utf-8 -*-
import json
import re
from datetime import timedelta

from lxml import html as lxml_html
from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import html_escape


# PDF export: text between tags, and emoji (incl. ZWJ / variation / skin tone sequences)
_PDF_TEXT_RE = re.compile(r'>([^<>]+)<')
_PDF_EMOJI_RE = re.compile(
    '(?:[\\U0001F000-\\U0001FAFF\\u2600-\\u27BF\\u2B00-\\u2BFF\\u2300-\\u23FF]'
    '[\\uFE0F\\u200D\\U0001F3FB-\\U0001F3FF]*)+'
)


class KnowledgeArticle(models.Model):
    _name = 'knowledge.management.article'
    _description = 'Knowledge Article'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    # Chatter panel: like Odoo Knowledge, readers can comment on an article.
    _mail_post_access = 'read'
    _order = 'sequence, id'
    _parent_name = 'parent_id'
    _parent_store = True

    # ── Core Fields ──────────────────────────────────────────────────
    name = fields.Char(
        string='Article Name',
        default='Untitled',
        required=True,
        tracking=True,
    )
    icon = fields.Char(string='Icon')
    cover_image_url = fields.Text(string='Cover Image URL')
    cover_position = fields.Char(string='Cover Position', default='50%')
    body_html = fields.Html(
        string='Body',
        sanitize=False,
        strip_style=False,
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True, tracking=True)
    to_delete_date = fields.Date(
        string='Deletion Date',
        copy=False,
        help='Articles in the trash are permanently deleted on this date.',
    )

    # ── Hierarchy ─────────────────────────────────────────────────────
    parent_id = fields.Many2one(
        'knowledge.management.article',
        string='Parent Article',
        index=True,
        ondelete='cascade',
    )
    child_ids = fields.One2many(
        'knowledge.management.article',
        'parent_id',
        string='Child Articles',
    )
    parent_path = fields.Char(index=True, unaccent=False)

    # ── Properties (Odoo Knowledge "Add Properties") ─────────────────
    # The parent article holds the definition, shared by all its
    # sub-articles (and items), each one storing its own values.
    article_properties_definition = fields.PropertiesDefinition('Article Item Properties')
    article_properties = fields.Properties(
        'Properties',
        definition='parent_id.article_properties_definition',
        copy=True,
    )
    child_count = fields.Integer(
        string='Children',
        compute='_compute_child_count',
        store=False,
    )

    # ── Visibility ────────────────────────────────────────────────────
    visibility = fields.Selection([
        ('workspace', 'Workspace'),
        ('shared', 'Shared'),
        ('private', 'Private'),
    ], string='Visibility', default='workspace', required=True, tracking=True)

    # ── Favorites ─────────────────────────────────────────────────────
    favorite_user_ids = fields.Many2many(
        'res.users',
        'knowledge_article_favorite_rel',
        'article_id',
        'user_id',
        string='Favorited By',
    )
    is_user_favorite = fields.Boolean(
        string='Is Favorite',
        compute='_compute_is_user_favorite',
        inverse='_inverse_is_user_favorite',
    )

    # ── Sharing / Members ─────────────────────────────────────────────
    member_ids = fields.One2many(
        'knowledge.management.article.member',
        'article_id',
        string='Members',
    )

    # ── Options ──────────────────────────────────────────────────────
    is_locked = fields.Boolean(string='Locked', default=False, tracking=True)
    full_width = fields.Boolean(string='Full Width', default=False)
    is_article_item = fields.Boolean(
        string='Is Article Item',
        default=False,
        tracking=True,
        help='True if this article represents an item in an embedded list/kanban view, hidden from the sidebar menu',
    )

    # ── Article items (Odoo Online style) ─────────────────────────────
    # An "item" is a child article (is_article_item=True). The embedded
    # Item Kanban / List / Calendar blocks of the parent article are real
    # Odoo views on this model, filtered on parent_id.
    stage_id = fields.Many2one(
        'knowledge.management.item.stage',
        string='Stage',
        index=True,
        ondelete='set null',
        tracking=True,
        group_expand='_read_group_stage_id',
        domain="[('article_id', '=', parent_id)]",
        copy=False,
    )
    item_date_start = fields.Datetime(string='Start Date Time', copy=False)
    item_date_end = fields.Datetime(string='End Date Time', copy=False)

    # ── Legacy items (pre 20.0.1.0.15, data migrated to child articles) ─
    article_item_ids = fields.One2many(
        'knowledge.management.item',
        'article_id',
        string='Article Items',
    )
    version_ids = fields.One2many(
        'knowledge.management.article.version',
        'article_id',
        string='History Versions',
    )

    # ── Computed ─────────────────────────────────────────────────────
    @api.depends('child_ids', 'child_ids.active', 'child_ids.is_article_item')
    def _compute_child_count(self):
        for rec in self:
            rec.child_count = len(rec.child_ids.filtered(lambda c: c.active and not c.is_article_item))

    @api.depends('favorite_user_ids')
    def _compute_is_user_favorite(self):
        for rec in self:
            rec.is_user_favorite = self.env.user in rec.favorite_user_ids

    def _inverse_is_user_favorite(self):
        for rec in self:
            if rec.is_user_favorite:
                rec.favorite_user_ids = [(4, self.env.uid)]
            else:
                rec.favorite_user_ids = [(3, self.env.uid)]

    # ── Actions ──────────────────────────────────────────────────────
    def action_set_favorite(self):
        """Toggle favorite status for current user (frontend compatibility)."""
        self.ensure_one()
        user = self.env.user
        is_fav = user in self.favorite_user_ids
        if is_fav:
            self.write({'favorite_user_ids': [(3, user.id)]})
            return False
        else:
            self.write({'favorite_user_ids': [(4, user.id)]})
            return True

    def action_toggle_favorite(self):
        return self.action_set_favorite()

    def action_toggle_lock(self):
        self.ensure_one()
        self.is_locked = not self.is_locked

    TRASH_RETENTION_DAYS = 30
    # Fields frozen by "Lock Content": the whole article (title, icon, cover
    # and body), not only the body.
    LOCKED_CONTENT_FIELDS = ('name', 'icon', 'cover_image_url', 'cover_position', 'body_html')

    def write(self, vals):
        if (not self.env.su and 'is_locked' not in vals
                and set(vals) & set(self.LOCKED_CONTENT_FIELDS)):
            locked = self.filtered('is_locked')
            if locked:
                raise UserError(_(
                    'The article "%s" is locked. Unlock it before editing its '
                    'title, icon, cover or content.', locked[0].name))
        return super().write(vals)

    def action_move_to_trash(self):
        deletion_date = fields.Date.today() + timedelta(days=self.TRASH_RETENTION_DAYS)
        for rec in self:
            rec.write({'active': False, 'to_delete_date': deletion_date})
            # Also deactivate all child articles recursively
            children = self.search([('parent_id', '=', rec.id)])
            if children:
                children.action_move_to_trash()

    def action_restore_from_trash(self):
        """Restore the articles and the descendants trashed along with them."""
        articles = self.with_context(active_test=False)
        descendants = articles.search([
            ('id', 'child_of', articles.ids),
            ('active', '=', False),
        ])
        (articles | descendants).write({'active': True, 'to_delete_date': False})
        # A restored article whose parent is still in the trash would be
        # invisible in the sidebar: move it to the root instead.
        for rec in articles:
            if rec.parent_id and not rec.parent_id.active:
                rec.parent_id = False
        return True

    def _get_deletion_date(self):
        """Deletion date, with a fallback for articles trashed before the
        to_delete_date field existed."""
        self.ensure_one()
        if self.active:
            return False
        if self.to_delete_date:
            return self.to_delete_date
        base = (self.write_date or fields.Datetime.now()).date()
        return base + timedelta(days=self.TRASH_RETENTION_DAYS)

    def action_open_in_knowledge(self):
        """Open the article in the Knowledge client action (used by the Trash
        list so a trashed article shows its content, not a form)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'hudson_knowledge.action_knowledge',
            'name': self.name,
            'params': {'article_id': self.id},
        }

    @api.model
    def _gc_trashed_articles(self):
        """Cron: permanently delete articles whose trash period is over."""
        expired = self.with_context(active_test=False).search([
            ('active', '=', False),
            ('to_delete_date', '!=', False),
            ('to_delete_date', '<=', fields.Date.today()),
        ])
        expired.unlink()

    def action_create_copy(self):
        self.ensure_one()
        new_name = _('Copy of %s') % self.name
        copy = self.copy({'name': new_name})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'knowledge.management.article',
            'res_id': copy.id,
            'views': [[False, 'form']],
            'target': 'current',
        }

    # ── Version History & Lifecycle Methods ───────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            parent_id = vals.get('parent_id') or self.env.context.get('default_parent_id')
            if parent_id and not vals.get('visibility'):
                parent = self.browse(parent_id)
                if parent.exists() and parent.visibility:
                    vals['visibility'] = parent.visibility
            is_item = vals.get('is_article_item', self.env.context.get('default_is_article_item'))
            if is_item and not vals.get('body_html'):
                # The knowledge editor uses the first <h1> as the title.
                vals['body_html'] = '<h1>%s</h1><p><br></p>' % html_escape(vals.get('name') or _('Untitled'))
        return super(KnowledgeArticle, self).create(vals_list)

    # ── Article items ────────────────────────────────────────────────
    @api.model
    def _get_item_parent_id(self, domain=None):
        parent_id = self.env.context.get('default_parent_id')
        if not parent_id and domain:
            for leaf in domain:
                if isinstance(leaf, (list, tuple)) and len(leaf) == 3 \
                        and leaf[0] == 'parent_id' and leaf[1] == '=' and isinstance(leaf[2], int):
                    parent_id = leaf[2]
                    break
        return parent_id

    @api.model
    def _read_group_stage_id(self, stages, domain):
        """Show every stage of the parent article, even empty ones."""
        parent_id = self._get_item_parent_id(domain)
        if not parent_id:
            return stages
        return self.browse(parent_id)._ensure_item_stages()

    def _ensure_item_stages(self):
        """Return the item stages of this (parent) article, creating the
        Odoo default ones (New / Ongoing / Done) the first time."""
        self.ensure_one()
        Stage = self.env['knowledge.management.item.stage']
        stages = Stage.search([('article_id', '=', self.id)], order='sequence, id')
        if not stages:
            stages = Stage.create([
                {'name': _('New'), 'article_id': self.id, 'sequence': 10},
                {'name': _('Ongoing'), 'article_id': self.id, 'sequence': 20},
                {'name': _('Done'), 'article_id': self.id, 'sequence': 30, 'fold': True},
            ])
        return stages

    def action_prepare_item_view(self, view_type):
        """Called when an Item Kanban/List/Calendar block is inserted."""
        self.ensure_one()
        if view_type == 'kanban':
            self._ensure_item_stages()
        return True

    @api.model
    def get_item_view_ids(self):
        views = {}
        for view_type in ('kanban', 'list', 'calendar', 'search'):
            view = self.env.ref('hudson_knowledge.view_knowledge_article_item_%s' % view_type,
                                raise_if_not_found=False)
            views[view_type] = view.id if view else False
        return views

    @api.model
    def get_sidebar_articles(self):
        """Return structured sidebar data for the Knowledge client action."""
        user = self.env.user
        domain_active = [('active', '=', True), ('is_article_item', '=', False)]

        def _serialize(articles):
            result = []
            for art in articles:
                result.append({
                    'id': art.id,
                    'name': art.name,
                    'icon': art.icon or '',
                    'visibility': art.visibility,
                    'user_can_write': art.user_can_write,
                    'parent_id': art.parent_id.id,
                    'is_user_favorite': user in art.favorite_user_ids,
                    'is_locked': art.is_locked,
                    'child_count': self.search_count([('parent_id', '=', art.id), ('is_article_item', '=', False)]),
                    'sequence': art.sequence,
                    'write_uid': {
                        'id': art.write_uid.id,
                        'name': art.write_uid.name,
                        'avatar': '/web/image/res.users/%d/avatar_128' % art.write_uid.id,
                    } if art.write_uid else None,
                    'write_date': art.write_date.strftime('%Y-%m-%dT%H:%M:%SZ') if art.write_date else False,
                })
            return result

        favorites = self.search(domain_active + [
            ('favorite_user_ids', 'in', [user.id]),
        ], order='sequence, id')

        workspace = self.search(domain_active + [
            ('visibility', '=', 'workspace'),
            ('parent_id', '=', False),
        ], order='sequence, id')

        # Shared: root shared articles, plus sub-articles shared with the user
        # whose parent he cannot see (record rules filter the search).
        shared_all = self.search(domain_active + [('visibility', '=', 'shared')], order='sequence, id')
        shared = shared_all.filtered(lambda a: not a.parent_id or a.parent_id not in shared_all)
        if shared - shared.filtered(lambda a: not a.parent_id):
            visible_parents = self.search([('id', 'in', shared.parent_id.ids)])
            shared = shared.filtered(lambda a: not a.parent_id or a.parent_id not in visible_parents)

        private = self.search(domain_active + [
            ('visibility', '=', 'private'),
            ('parent_id', '=', False),
        ], order='sequence, id')

        return {
            'favorites': _serialize(favorites),
            'workspace': _serialize(workspace),
            'shared': _serialize(shared),
            'private': _serialize(private),
        }

    @api.model
    def get_article_children(self, parent_id):
        """Return children of a given article for sidebar lazy loading."""
        children = self.search([
            ('parent_id', '=', parent_id),
            ('active', '=', True),
            ('is_article_item', '=', False),
        ], order='sequence, id')
        user = self.env.user
        return [{
            'id': art.id,
            'name': art.name,
            'icon': art.icon or '',
            'visibility': art.visibility,
            'user_can_write': art.user_can_write,
            'parent_id': art.parent_id.id,
            'is_user_favorite': user in art.favorite_user_ids,
            'is_locked': art.is_locked,
            'child_count': self.search_count([('parent_id', '=', art.id), ('is_article_item', '=', False)]),
            'sequence': art.sequence,
            'write_uid': {
                'id': art.write_uid.id,
                'name': art.write_uid.name,
                'avatar': '/web/image/res.users/%d/avatar_128' % art.write_uid.id,
            } if art.write_uid else None,
            'write_date': art.write_date.strftime('%Y-%m-%dT%H:%M:%SZ') if art.write_date else False,
        } for art in children]

    @api.model
    def get_top_article(self):
        """Return the ID of the topmost article to auto-open."""
        user = self.env.user
        # First try favorites
        fav = self.search([
            ('active', '=', True),
            ('favorite_user_ids', 'in', [user.id]),
        ], order='sequence, id', limit=1)
        if fav:
            return fav.id
        # Then workspace
        ws = self.search([
            ('active', '=', True),
            ('visibility', '=', 'workspace'),
        ], order='sequence, id', limit=1)
        if ws:
            return ws.id
        # Then any
        any_art = self.search([('active', '=', True)], order='sequence, id', limit=1)
        return any_art.id if any_art else False

    @api.model
    def get_command_palette_articles(self, search_term='', limit=10):
        """Articles for the "?" namespace of the command palette (the
        Knowledge button of form views). Without a search term the user's
        favorites are listed (then the most recently edited articles),
        otherwise the articles whose title matches, favorites first."""
        user = self.env.user
        search_term = (search_term or '').strip()
        domain = [('active', '=', True), ('is_article_item', '=', False)]
        if search_term:
            articles = self.search(domain + [('name', 'ilike', search_term)], limit=100)
        else:
            articles = self.search(domain + [('favorite_user_ids', 'in', [user.id])], limit=limit)
            if len(articles) < limit:
                articles |= self.search(
                    domain + [('id', 'not in', articles.ids)],
                    order='write_date desc, id desc', limit=limit - len(articles),
                )
        favorites = articles.filtered(lambda a: user in a.favorite_user_ids)
        if search_term:
            articles = (favorites | (articles - favorites))[:limit]
        result = []
        for art in articles:
            # Ancestors the user can read, e.g. "Workspace / Accounting".
            parent_ids = [int(pid) for pid in (art.parent_path or '').split('/')[:-2] if pid]
            parents = self.browse(parent_ids)._filtered_access('read') if parent_ids else self.browse()
            result.append({
                'id': art.id,
                'name': art.name or _('Untitled'),
                'icon': art.icon or '',
                'is_user_favorite': art in favorites,
                'parent_path': ' / '.join(p.name or _('Untitled') for p in parents),
            })
        return result

    # ── PDF export ────────────────────────────────────────────────────
    def _get_pdf_body_html(self):
        """Article body ready for the PDF report: embedded Item Kanban / List
        / Calendar blocks (interactive views in the app, empty <div>s in the
        stored HTML) are replaced by a table of their items, and the title is
        added when the body does not start with one."""
        self.ensure_one()
        body = self.body_html or ''
        try:
            root = lxml_html.fragment_fromstring(body or '<p></p>', create_parent='div')
        except Exception:
            return Markup(body)

        self._replace_embedded_item_views(root)

        has_title = bool(root.xpath('//h1'))
        content = ''.join(
            lxml_html.tostring(child, encoding='unicode') for child in root
        )
        if root.text:
            content = html_escape(root.text) + content
        if not has_title:
            content = '<h1>%s</h1>%s' % (html_escape(self.name or ''), content)
        # wkhtmltopdf does not fall back to another font per character: give
        # emoji their own font or they print as empty boxes.
        content = _PDF_TEXT_RE.sub(
            lambda m: '>' + _PDF_EMOJI_RE.sub(
                r'<span class="o_knowledge_pdf_emoji">\g<0></span>', m.group(1)) + '<',
            content,
        )
        return Markup(content)

    def _replace_embedded_item_views(self, root):
        """Replace the embedded Item Kanban / List / Calendar blocks of the
        parsed body ``root`` (interactive views in the app, empty <div>s in
        the stored HTML) by a static table of their items."""
        self.ensure_one()
        embedded = root.xpath(
            '//*[@data-embedded="knowledgeItemView"]'
            ' | //*[contains(concat(" ", normalize-space(@class), " "), " o_knowledge_embedded_view_container ")]'
            ' | //*[@data-embedded-view]'
        )
        items = False
        for node in embedded:
            if node.getparent() is None:
                continue
            try:
                props = json.loads(node.get('data-embedded-props') or '{}')
            except ValueError:
                props = {}
            if items is False:
                items = self.search([
                    ('parent_id', '=', self.id),
                    ('is_article_item', '=', True),
                ], order='sequence, id')
            new = lxml_html.fragment_fromstring(
                self._render_pdf_item_table(items, props.get('viewType'), props.get('name')),
                create_parent='div',
            )
            node.getparent().replace(node, new)
        return root

    def _render_pdf_item_table(self, items, view_type, view_name):
        show_dates = view_type == 'calendar' or any(items.mapped('item_date_start'))
        show_stage = view_type == 'kanban' or any(items.mapped('stage_id'))
        title = view_name or {
            'kanban': _('Item Kanban'), 'list': _('Item List'), 'calendar': _('Item Calendar'),
        }.get(view_type, _('Items'))

        def fmt(dt):
            return fields.Datetime.context_timestamp(self, dt).strftime('%Y-%m-%d %H:%M') if dt else ''

        head = '<th>%s</th>' % _('Name')
        if show_stage:
            head += '<th>%s</th>' % _('Stage')
        if show_dates:
            head += '<th>%s</th><th>%s</th>' % (_('Start'), _('End'))
        rows = []
        for item in items:
            row = '<td>%s %s</td>' % (html_escape(item.icon or ''), html_escape(item.name or ''))
            if show_stage:
                row += '<td>%s</td>' % html_escape(item.stage_id.name or '')
            if show_dates:
                row += '<td>%s</td><td>%s</td>' % (fmt(item.item_date_start), fmt(item.item_date_end))
            rows.append('<tr>%s</tr>' % row)
        if not rows:
            colspan = 1 + show_stage + 2 * show_dates
            rows.append('<tr><td colspan="%d" class="text-muted">%s</td></tr>' % (colspan, _('No items')))
        return (
            '<div class="o_knowledge_pdf_items">'
            '<h4>%s</h4>'
            '<table class="table table-sm table-bordered"><thead><tr>%s</tr></thead>'
            '<tbody>%s</tbody></table></div>'
        ) % (html_escape(title), head, ''.join(rows))

    def _get_pdf_cover_url(self):
        """Absolute cover URL, so wkhtmltopdf can load it."""
        self.ensure_one()
        url = self.cover_image_url or ''
        if url.startswith('/'):
            url = self.get_base_url() + url
        return url

    @api.model
    def get_article_data(self):
        """Return full article data for the frontend.
        Can be called via orm.call with active_id in context.
        """
        article_id = self.env.context.get('active_id')
        if article_id:
            self = self.browse(article_id)
        self.ensure_one()
        user = self.env.user
        return {
            'id': self.id,
            'name': self.name,
            'icon': self.icon or '',
            'cover_image_url': self.cover_image_url or False,
            'cover_position': self.cover_position or '50%',
            'body_html': self.body_html or '',
            'visibility': self.visibility,
            'is_locked': self.is_locked,
            'full_width': self.full_width,
            'is_user_favorite': user in self.favorite_user_ids,
            'write_uid': {
                'id': self.write_uid.id,
                'name': self.write_uid.name,
                'avatar': '/web/image/res.users/%d/avatar_128' % self.write_uid.id,
            } if self.write_uid else None,
            'write_date': self.write_date.strftime('%Y-%m-%dT%H:%M:%SZ') if self.write_date else False,
            'parent_id': self.parent_id.id if self.parent_id else False,
            'parent_name': self.parent_id.name if self.parent_id else False,
            'is_article_item': self.is_article_item,
            'user_permission': self.user_permission,
            'user_can_write': self.user_can_write,
            'active': self.active,
            'to_delete_date': fields.Date.to_string(self._get_deletion_date()) if not self.active else False,
            'has_properties': bool(self.parent_id and self.parent_id.sudo().article_properties_definition),
        }

