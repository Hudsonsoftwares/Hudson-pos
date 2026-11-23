# -*- coding: utf-8 -*-
import json

from markupsafe import escape
from werkzeug.urls import url_encode

from odoo import http, _
from odoo.exceptions import UserError
from odoo.http import request

from odoo.addons.portal.controllers.portal import CustomerPortal

BACKEND_URL = '/odoo/action-hudson_knowledge.action_knowledge_home'
ARTICLE_MODEL = 'knowledge.management.article'


def _is_knowledge_user(user):
    return not user._is_public() and user._is_internal() \
        and user.has_group('hudson_knowledge.group_knowledge_user')


def _redirect_to_backend(url):
    """Redirect a Knowledge user to the backend app.

    The backend refuses to be framed (X-Frame-Options: DENY), so when the
    link is opened inside a frame -- typically the website builder, which
    shows every frontend page to internal users in an iframe -- a plain
    redirect would leave a blocked frame and crash the builder. Navigate the
    whole window instead.

    Sec-Fetch-Dest is only sent on secure origins (HTTPS / localhost), so on a
    plain-HTTP host it is absent. Only a header explicitly saying this is a
    top-level navigation may take the plain redirect; otherwise (iframe, or
    unknown) use the top-window navigation page."""
    if request.httprequest.headers.get('Sec-Fetch-Dest') in ('document', 'empty'):
        return request.redirect(url)
    html = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Knowledge</title></head><body>'
        '<p><a href="%(href)s" target="_top">Open the article in Knowledge</a></p>'
        '<script>window.top.location.assign(%(js)s);</script>'
        '</body></html>'
    ) % {'href': escape(url), 'js': json.dumps(url)}  # url is built by the server
    return request.make_response(html, headers=[('Content-Type', 'text/html; charset=utf-8')])


class KnowledgePortal(CustomerPortal):

    def _prepare_portal_counter_values(self, counter):
        if counter == 'knowledge_count':
            return ARTICLE_MODEL, [('is_article_item', '=', False)], 'read'
        return super()._prepare_portal_counter_values(counter)


class KnowledgePublicController(http.Controller):

    # ── Pages ────────────────────────────────────────────────────────
    @http.route('/knowledge/home', type='http', auth='user', website=True, sitemap=False)
    def knowledge_home(self, **kwargs):
        """Entry point of the portal (and target of the portal home card)."""
        user = request.env.user
        if _is_knowledge_user(user):
            return _redirect_to_backend(BACKEND_URL)
        Article = request.env[ARTICLE_MODEL]
        tree = Article._portal_get_tree(user)
        for _key, _label, articles in tree['sections']:
            if articles:
                return request.redirect(articles[0]._portal_url())
        return request.render('hudson_knowledge.knowledge_portal_page', self._prepare_values(None, 'none', tree))

    @http.route('/knowledge/article/<int:article_id>', type='http', auth='public', website=True, sitemap=False)
    def knowledge_article_page(self, article_id, **kwargs):
        """Article page: Knowledge users are sent to the backend app, members
        (portal guests, internal users without Knowledge) get the portal app
        and anonymous visitors the read-only page of a "Shared to web"
        article."""
        user = request.env.user
        article = request.env[ARTICLE_MODEL].sudo().browse(article_id).exists()
        if not article or not article.active:
            raise request.not_found()
        if _is_knowledge_user(user):
            return _redirect_to_backend('%s?%s' % (BACKEND_URL, url_encode({'article_id': article.id})))
        access = article._portal_get_access(user)
        if access == 'none':
            if user._is_public():
                return request.redirect('/web/login?%s' % url_encode({'redirect': article._portal_url()}))
            raise request.not_found()
        if access == 'public':
            tree = article._portal_get_tree(user, public_article=article)
        else:
            tree = article._portal_get_tree(user)
        return request.render('hudson_knowledge.knowledge_portal_page', self._prepare_values(article, access, tree))

    def _prepare_values(self, article, access, tree):
        user = request.env.user
        values = {
            'article': article,
            'access': access,
            'tree': tree,
            'is_public_user': user._is_public(),
            'can_create': not user._is_public(),
            'can_write': False,
            'open_ids': [],
        }
        if article:
            values.update({
                'body': article._portal_get_body_html(),
                # plain str (not Markup): escaped into the editor's <textarea>
                'raw_body': '%s' % (article.body_html or ''),
                'cover_url': article._portal_get_cover_url(),
                'ancestors': article._portal_visible_ancestors(access),
                'can_write': access == 'write' and not article.is_locked,
                'is_favorite': user in article.favorite_user_ids,
                'can_trash': access == 'write' and (not user.share or article.visibility == 'private'),
                'open_ids': article._get_ancestors_sudo().ids,
            })
        return values

    # ── Portal actions ───────────────────────────────────────────────
    def _article(self, article_id):
        article = request.env[ARTICLE_MODEL].browse(int(article_id)).exists()
        if not article:
            raise UserError(_('This article does not exist anymore.'))
        return article

    @http.route('/knowledge/portal/article/create', type='jsonrpc', auth='user', methods=['POST'])
    def portal_article_create(self, parent_id=False):
        article = request.env[ARTICLE_MODEL]._portal_create_article(parent_id)
        return {'id': article.id, 'url': article._portal_url()}

    @http.route('/knowledge/portal/article/<int:article_id>/save', type='jsonrpc', auth='user', methods=['POST'])
    def portal_article_save(self, article_id, name=None, body_html=None):
        return self._article(article_id)._portal_save(name=name, body_html=body_html)

    @http.route('/knowledge/portal/article/<int:article_id>/favorite', type='jsonrpc', auth='user', methods=['POST'])
    def portal_article_favorite(self, article_id):
        return {'is_favorite': self._article(article_id)._portal_toggle_favorite()}

    @http.route('/knowledge/portal/article/<int:article_id>/copy', type='jsonrpc', auth='user', methods=['POST'])
    def portal_article_copy(self, article_id):
        copy = self._article(article_id)._portal_copy()
        return {'id': copy.id, 'url': copy._portal_url()}

    @http.route('/knowledge/portal/article/<int:article_id>/trash', type='jsonrpc', auth='user', methods=['POST'])
    def portal_article_trash(self, article_id):
        parent = self._article(article_id)._portal_trash()
        if parent and parent._portal_get_access() in ('read', 'write'):
            return {'url': parent._portal_url()}
        return {'url': '/knowledge/home'}

    @http.route('/knowledge/portal/search', type='jsonrpc', auth='user', methods=['POST'], readonly=True)
    def portal_search(self, term='', limit=30):
        """Search in the titles and contents of the articles of the user."""
        user = request.env.user
        Article = request.env[ARTICLE_MODEL]
        articles = Article._portal_accessible_articles(user)
        if term:
            articles = articles.filtered_domain(['|', ('name', 'ilike', term), ('body_html', 'ilike', term)])
        return [{
            'id': a.id,
            'name': a.name,
            'icon': a.icon or '',
            'path': ' / '.join(p.name for p in a._portal_visible_ancestors('read')),
            'url': a._portal_url(),
        } for a in articles[:int(limit)]]
