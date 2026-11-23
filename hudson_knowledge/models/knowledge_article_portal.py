# -*- coding: utf-8 -*-
"""Portal / public front-end of Knowledge (Odoo Online style).

Portal users (and internal users without the Knowledge app) open their
articles on ``/knowledge/article/<id>``: a sidebar with the articles they are
members of (Favorites / Workspace / Shared / Private), the article itself and
an editor for the articles they can edit (their own private articles).
Anonymous visitors get the same page in read-only mode for articles that are
"Shared to web".

Every change made from the portal goes through the methods below, which
check the permission of the current user explicitly and then write with sudo
(portal users have read access only, see security/ir.access.csv).
"""
import re

from lxml import html as lxml_html
from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.tools import html_escape, html_sanitize

# /web/image/123-abc/name.png, /web/image/ir.attachment/123/datas, /web/content/123
_ATTACHMENT_URL_RE = re.compile(r'^(/web/(?:image|content)/(?:ir\.attachment/)?(\d+)[^?#]*)(\?[^#]*)?$')

EMPTY_BODY = '<h1><br></h1><p><br></p>'


class KnowledgeArticle(models.Model):
    _inherit = 'knowledge.management.article'

    # Fields a portal user may change on an article they can edit. Hierarchy,
    # visibility and members only change through the share / move methods.
    PORTAL_WRITABLE_FIELDS = frozenset({
        'name', 'icon', 'cover_image_url', 'cover_position', 'body_html', 'full_width',
    })

    def write(self, vals):
        if not self.env.su and self.env.user.share:
            forbidden = set(vals) - self.PORTAL_WRITABLE_FIELDS
            if forbidden:
                raise AccessError(_('You are not allowed to change %s on an article.', ', '.join(sorted(forbidden))))
        return super().write(vals)

    # ── Access ───────────────────────────────────────────────────────
    def _portal_get_access(self, user=None):
        """'write' / 'read' for a member, 'public' when the visitor only sees
        the article because it is shared to web, 'none' otherwise."""
        self.ensure_one()
        user = user or self.env.user
        article = self.sudo()
        if not article.active:
            return 'none'
        if not user._is_public():
            permission = article._get_permission_for_user(user)
            if permission != 'none':
                return permission
        return 'public' if article._is_published_on_web() else 'none'

    def _portal_check_access(self, mode='read'):
        """Raise unless the current user can read (or edit) the article."""
        self.ensure_one()
        access = self._portal_get_access()
        if mode == 'write':
            if access != 'write':
                raise AccessError(_('You need "Can Edit" access on "%s" to change it.', self.sudo().name))
        elif access in ('none', 'public'):
            raise AccessError(_('You do not have access to "%s".', self.sudo().name))
        return self.sudo()

    @api.model
    def _portal_accessible_articles(self, user=None):
        """Every active article (not items) the user is a member of."""
        user = user or self.env.user
        if user._is_public():
            return self.sudo().browse()
        return self.sudo().search([
            ('access_partner_ids', 'in', user.partner_id.ids),
            ('is_article_item', '=', False),
        ], order='sequence, id')

    # ── Sidebar ──────────────────────────────────────────────────────
    @api.model
    def _portal_get_tree(self, user=None, public_article=None):
        """Sidebar of the portal page.

        :return: {'sections': [(key, label, root articles)],
                  'children': {article id: child articles}}
        """
        user = user or self.env.user
        if public_article:
            # Anonymous / non-member visitor: the published part of the tree.
            article = public_article.sudo()
            published = (article._get_ancestors_sudo() | article).filtered('website_published')
            root = published[:1] or article
            articles = root | root._get_descendants().filtered(lambda a: a.active and not a.is_article_item)
            sections = [('published', '', root)]
        else:
            articles = self._portal_accessible_articles(user)
            roots = articles.filtered(lambda a: a.parent_id not in articles)
            favorites = articles.filtered(lambda a: user in a.favorite_user_ids)
            sections = [
                ('favorites', _('Favorites'), favorites),
                ('workspace', _('Workspace'), roots.filtered(lambda a: a.visibility == 'workspace')),
                ('shared', _('Shared'), roots.filtered(lambda a: a.visibility == 'shared')),
                ('private', _('Private'), roots.filtered(lambda a: a.visibility == 'private')),
            ]
        children = {}
        for article in articles.sorted(lambda a: (a.sequence, a.id)):
            if article.parent_id in articles:
                children.setdefault(article.parent_id.id, self.sudo().browse())
                children[article.parent_id.id] |= article
        return {'sections': sections, 'children': children}

    def _portal_visible_ancestors(self, access):
        """Breadcrumb: the ancestors the visitor can open."""
        self.ensure_one()
        ancestors = self._get_ancestors_sudo()
        if access == 'public':
            published = ancestors.filtered('website_published')[:1]
            if self.website_published or not published:
                return ancestors.browse()
            return ancestors.filtered(lambda a: a == published or published in a._get_ancestors_sudo())
        return ancestors.filtered(lambda a: a._portal_get_access() in ('read', 'write'))

    # ── Content ──────────────────────────────────────────────────────
    def _portal_tokenize_url(self, url):
        """Add an access token to the URL of an image attachment of the
        article, so visitors without access to the attachment's record (e.g.
        images uploaded with the backend editor, or anonymous visitors of a
        published article) can load it."""
        self.ensure_one()
        match = _ATTACHMENT_URL_RE.match(url or '')
        if not match or 'access_token=' in url:
            return url
        attachment = self.env['ir.attachment'].sudo().browse(int(match.group(2))).exists()
        if not attachment or attachment.public or not (attachment.mimetype or '').startswith('image/'):
            return url
        if attachment.res_model == self._name:
            if attachment.res_id != self.id \
                    and self.browse(attachment.res_id).exists()._portal_get_access() == 'none':
                return url
        elif attachment.res_model not in (False, 'ir.ui.view'):
            return url
        token = attachment.access_token or attachment.generate_access_token()[0]
        return '%s%saccess_token=%s' % (url, '&' if match.group(3) else '?', token)

    def _portal_get_body_html(self):
        """Article body for the portal page: embedded item views become
        static tables and attachment images get an access token."""
        self.ensure_one()
        article = self.sudo()
        body = article.body_html or ''
        if not body.strip():
            return Markup('<h1>%s</h1>') % article.name
        try:
            root = lxml_html.fragment_fromstring(body, create_parent='div')
        except Exception:
            return Markup(body)
        article._replace_embedded_item_views(root)
        for img in root.iter('img'):
            src = img.get('src')
            if src:
                img.set('src', self._portal_tokenize_url(src))
        if not root.xpath('//h1'):
            title = lxml_html.fragment_fromstring('<h1>%s</h1>' % html_escape(article.name or ''))
            title.tail, root.text = root.text, None
            root.insert(0, title)
        content = ''.join(lxml_html.tostring(child, encoding='unicode') for child in root)
        if root.text:
            content = html_escape(root.text) + content
        return Markup(content)

    def _portal_get_cover_url(self):
        self.ensure_one()
        return self._portal_tokenize_url(self.sudo().cover_image_url or '')

    def _portal_url(self):
        self.ensure_one()
        return '/knowledge/article/%d' % self.id

    # ── Portal actions (called by the controller) ────────────────────
    @api.model
    def _portal_create_article(self, parent_id=False):
        """New article from the portal: a private root article, or a
        sub-article of an article the user can edit."""
        user = self.env.user
        vals = {'name': _('Untitled'), 'body_html': EMPTY_BODY}
        if parent_id:
            parent = self.browse(int(parent_id)).exists()
            if not parent:
                raise UserError(_('The parent article does not exist anymore.'))
            parent._portal_check_access('write')
            vals['parent_id'] = parent.id
        else:
            vals.update({
                'visibility': 'private',
                'member_ids': [(0, 0, {'partner_id': user.partner_id.id, 'permission': 'write'})],
            })
        # sudo keeps the user as create_uid / write_uid
        return self.sudo().create(vals)

    def _portal_save(self, name=None, body_html=None):
        self.ensure_one()
        article = self._portal_check_access('write')
        if article.is_locked:
            raise UserError(_('The article "%s" is locked.', article.name))
        vals = {}
        if name is not None:
            vals['name'] = (name or '').strip()[:200] or _('Untitled')
        if body_html is not None:
            if self.env.user.share:
                body_html = html_sanitize(body_html, sanitize_attributes=True, sanitize_style=True,
                                          strip_classes=False)
            vals['body_html'] = body_html
        if vals:
            article.write(vals)
        return {'name': article.name, 'write_date': fields.Datetime.to_string(article.write_date)}

    def _toggle_favorite_no_write(self, user):
        """Add / remove the user from the favorites without touching the
        article itself: a favorite must not show up as "Last Edited by"."""
        self.ensure_one()
        cr = self.env.cr
        self.flush_model(['favorite_user_ids'])
        cr.execute('SELECT 1 FROM knowledge_article_favorite_rel WHERE article_id = %s AND user_id = %s',
                   (self.id, user.id))
        if cr.rowcount:
            cr.execute('DELETE FROM knowledge_article_favorite_rel WHERE article_id = %s AND user_id = %s',
                       (self.id, user.id))
            is_favorite = False
        else:
            cr.execute('INSERT INTO knowledge_article_favorite_rel (article_id, user_id) VALUES (%s, %s)',
                       (self.id, user.id))
            is_favorite = True
        self.invalidate_recordset(['favorite_user_ids', 'is_user_favorite'])
        return is_favorite

    def _portal_toggle_favorite(self):
        self.ensure_one()
        article = self._portal_check_access('read')
        return article._toggle_favorite_no_write(self.env.user)

    def _portal_copy(self):
        """"Create a Copy": a private copy owned by the current user (sub-
        articles and items are not copied, so item views become tables)."""
        self.ensure_one()
        article = self._portal_check_access('read')
        body = article._portal_get_body_html()
        return self.sudo().create({
            'name': _('Copy of %s', article.name),
            'icon': article.icon,
            'cover_image_url': article.cover_image_url,
            'cover_position': article.cover_position,
            'body_html': body,
            'full_width': article.full_width,
            'visibility': 'private',
            'member_ids': [(0, 0, {'partner_id': self.env.user.partner_id.id, 'permission': 'write'})],
        })

    def _portal_trash(self):
        """Portal users can only delete their own private articles."""
        self.ensure_one()
        article = self._portal_check_access('write')
        if self.env.user.share and article.visibility != 'private':
            raise AccessError(_('Only private articles can be deleted from the portal.'))
        parent = article.parent_id
        article.action_move_to_trash()
        return parent


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    def _can_bypass_rights_on_media_dialog(self, **attachment_data):
        """Portal users may upload images into the articles they can edit."""
        if attachment_data.get('res_model') == 'knowledge.management.article' and attachment_data.get('res_id'):
            article = self.env['knowledge.management.article'].browse(int(attachment_data['res_id'])).exists()
            if article and article._portal_get_access() == 'write':
                return True
        return super()._can_bypass_rights_on_media_dialog(**attachment_data)
