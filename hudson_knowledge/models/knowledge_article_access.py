# -*- coding: utf-8 -*-
"""Odoo Online style access model for knowledge articles.

Sidebar sections ("visibility"):

* ``workspace`` – every internal Knowledge user gets the *General Access*
  permission (``internal_permission``: Can Edit / Can Read). Members are
  per-person overrides (they can also be set to "No Access").
* ``shared``    – members only, and there must be at least one member besides
  the owner. Removing the last one turns the article back into a private one.
* ``private``   – only its owner. Moving an article to Private removes every
  other member of the article and of its sub-articles.

Members are inherited by sub-articles; a member line on a sub-article
overrides the inherited permission of that person. The effective result is
stored in ``access_partner_ids`` / ``write_partner_ids`` /
``readonly_partner_ids`` / ``blocked_partner_ids`` so that the ``ir.access``
domains (security/ir.access.csv) can filter on it.

All membership / visibility changes go through the ``action_*`` methods below,
which check the permission of the current user explicitly and then write with
sudo.
"""
from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.tools import email_normalize

PERMISSION_RANK = {'none': 0, 'read': 1, 'write': 2}


class KnowledgeArticle(models.Model):
    _inherit = 'knowledge.management.article'

    internal_permission = fields.Selection([
        ('write', 'Can Edit'),
        ('read', 'Can Read'),
    ], string='General Access', default='write', required=True,
        help='Permission of every internal user on a Workspace article.')

    access_partner_ids = fields.Many2many(
        'res.partner', 'knowledge_article_access_partner_rel', 'article_id', 'partner_id',
        string='Members with access', compute='_compute_effective_members',
        store=True, recursive=True, compute_sudo=True)
    write_partner_ids = fields.Many2many(
        'res.partner', 'knowledge_article_write_partner_rel', 'article_id', 'partner_id',
        string='Members who can edit', compute='_compute_effective_members',
        store=True, recursive=True, compute_sudo=True)
    readonly_partner_ids = fields.Many2many(
        'res.partner', 'knowledge_article_readonly_partner_rel', 'article_id', 'partner_id',
        string='Read-only members', compute='_compute_effective_members',
        store=True, recursive=True, compute_sudo=True)
    blocked_partner_ids = fields.Many2many(
        'res.partner', 'knowledge_article_blocked_partner_rel', 'article_id', 'partner_id',
        string='Members without access', compute='_compute_effective_members',
        store=True, recursive=True, compute_sudo=True)

    website_published = fields.Boolean(
        string='Shared to web', copy=False,
        help='Publish this article and its sub-articles on a public link.')
    user_permission = fields.Selection([
        ('none', 'No Access'),
        ('read', 'Can Read'),
        ('write', 'Can Edit'),
    ], compute='_compute_user_permission', string='My Permission')
    user_can_write = fields.Boolean(compute='_compute_user_permission')

    # ── Effective members ────────────────────────────────────────────
    def _get_member_permissions(self):
        """{partner: permission} of this article, inherited members included."""
        self.ensure_one()
        result = {}
        if self.parent_id:
            parent = self.parent_id
            for partner in parent.access_partner_ids:
                result[partner] = 'write' if partner in parent.write_partner_ids else 'read'
            for partner in parent.blocked_partner_ids:
                result[partner] = 'none'
        for member in self.member_ids:
            result[member.partner_id] = member.permission
        return result

    @api.depends('member_ids.partner_id', 'member_ids.permission',
                 'parent_id.access_partner_ids', 'parent_id.write_partner_ids',
                 'parent_id.blocked_partner_ids')
    def _compute_effective_members(self):
        Partner = self.env['res.partner']
        for article in self:
            perms = article._get_member_permissions()
            access = write = readonly = blocked = Partner
            for partner, permission in perms.items():
                if permission == 'write':
                    access |= partner
                    write |= partner
                elif permission == 'read':
                    access |= partner
                    readonly |= partner
                else:
                    blocked |= partner
            article.access_partner_ids = access
            article.write_partner_ids = write
            article.readonly_partner_ids = readonly
            article.blocked_partner_ids = blocked

    def _get_permission_for_user(self, user):
        self.ensure_one()
        if user._is_superuser():
            return 'write'
        article = self.sudo()
        partner = user.partner_id
        if partner in article.write_partner_ids:
            member_permission = 'write'
        elif partner in article.readonly_partner_ids:
            member_permission = 'read'
        elif partner in article.blocked_partner_ids:
            member_permission = 'none'
        else:
            member_permission = False
        if article.visibility == 'workspace' and not user.share \
                and user.has_group('hudson_knowledge.group_knowledge_user'):
            return member_permission or article.internal_permission
        return member_permission or 'none'

    @api.depends_context('uid')
    @api.depends('visibility', 'internal_permission', 'access_partner_ids',
                 'write_partner_ids', 'blocked_partner_ids')
    def _compute_user_permission(self):
        for article in self:
            permission = article._get_permission_for_user(self.env.user) if article.id else 'write'
            article.user_permission = permission
            article.user_can_write = permission == 'write'

    def _check_user_can_write(self):
        for article in self:
            if article._get_permission_for_user(self.env.user) != 'write':
                raise AccessError(_('You need "Can Edit" access on "%s" to change it.', article.name))

    def _check_user_can_read(self):
        for article in self:
            if article._get_permission_for_user(self.env.user) == 'none':
                raise AccessError(_('You do not have access to "%s".', article.name))

    # ── Creation / hierarchy ─────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        partner_id = self.env.user.partner_id.id
        for vals in vals_list:
            parent_id = vals.get('parent_id') or self.env.context.get('default_parent_id')
            if parent_id:
                parent = self.browse(parent_id).sudo()
                vals.setdefault('internal_permission', parent.internal_permission)
            elif not vals.get('member_ids'):
                # The creator owns a root article.
                vals['member_ids'] = [(0, 0, {'partner_id': partner_id, 'permission': 'write'})]
        if self.env.su:
            return super().create(vals_list)
        # Users cannot create member lines themselves (memberships only change
        # through the share methods), so create with sudo -- create_uid stays
        # the user -- then apply the user's create rule to the result.
        self.check_access('create')
        records = super(KnowledgeArticle, self.sudo()).create(vals_list).sudo(False)
        records.check_access('create')
        return records

    def _get_descendants(self):
        return self.with_context(active_test=False).sudo().search([('id', 'child_of', self.ids)]) - self.sudo()

    def _set_category(self, visibility, internal_permission=None):
        """Apply a sidebar section to the articles and their descendants."""
        articles = self.sudo() | self._get_descendants()
        vals = {'visibility': visibility}
        if internal_permission:
            vals['internal_permission'] = internal_permission
        articles.write(vals)
        if visibility == 'private':
            me = self.env.user.partner_id
            articles.member_ids.filtered(lambda m: m.partner_id != me).unlink()
            for article in self.sudo().filtered(lambda a: not a.parent_id or a.parent_id.visibility != 'private'):
                if me not in article.member_ids.partner_id:
                    article.member_ids = [(0, 0, {'partner_id': me.id, 'permission': 'write'})]

    def _has_other_members(self):
        self.ensure_one()
        me = self.env.user.partner_id
        return bool((self.sudo().access_partner_ids - me))

    def _normalize_after_member_change(self):
        """Shared without anyone else -> Private (Odoo behaviour)."""
        for article in self.sudo():
            if article.visibility == 'shared' and not article.parent_id and not article._has_other_members():
                article.with_user(self.env.user)._set_category('private')

    # ── Sidebar move (drag & drop / Move To) ─────────────────────────
    def action_move_article(self, category=False, parent_id=False, before_id=False):
        """Move the article in the sidebar.

        :param category: 'workspace' | 'shared' | 'private' when dropped at the
            root of a section (parent_id False)
        :param parent_id: new parent article (becomes a sub-article)
        :param before_id: sibling to insert before (False = last)
        :return: dict with the resulting visibility
        """
        self.ensure_one()
        self._check_user_can_write()
        article = self.sudo()
        if parent_id:
            parent = self.browse(parent_id)
            parent._check_user_can_write()
            parent = parent.sudo()
            if parent == article or parent in article._get_descendants():
                raise UserError(_('An article cannot be moved inside one of its own sub-articles.'))
            category = parent.visibility
        elif category not in ('workspace', 'shared', 'private'):
            raise UserError(_('Unknown section.'))
        if category == 'shared' and not parent_id and not article._has_other_members():
            raise UserError(_('Invite at least one person to move this article to Shared.'))

        article.write({'parent_id': parent_id or False})
        internal = None
        if category == 'workspace' and article.visibility != 'workspace' and not parent_id:
            internal = 'write'
        self._set_category(category, internal)
        if parent_id:
            article.internal_permission = parent.internal_permission
        article._resequence(before_id)
        return {'visibility': article.visibility, 'parent_id': article.parent_id.id}

    def _resequence(self, before_id=False):
        self.ensure_one()
        siblings = self.sudo().search([
            ('parent_id', '=', self.parent_id.id),
            ('visibility', '=', self.visibility),
            ('is_article_item', '=', False),
            ('id', '!=', self.id),
        ], order='sequence, id')
        ordered = list(siblings)
        index = len(ordered)
        if before_id:
            for i, sibling in enumerate(ordered):
                if sibling.id == before_id:
                    index = i
                    break
        ordered.insert(index, self.sudo())
        for sequence, article in enumerate(ordered, start=1):
            if article.sequence != sequence:
                article.sequence = sequence

    def get_move_targets(self, search=''):
        """Targets of the "Move To" dialog: sections + editable articles."""
        self.ensure_one()
        excluded = (self.sudo() | self._get_descendants()).ids
        domain = Domain([
            ('id', 'not in', excluded),
            ('is_article_item', '=', False),
        ])
        if search:
            domain &= Domain('name', 'ilike', search)
        candidates = self.search(domain, limit=80, order='sequence, id')
        articles = candidates.filtered('user_can_write')[:40]
        return [{
            'id': a.id,
            'name': a.name,
            'icon': a.icon or '',
            'visibility': a.visibility,
            'path': ' / '.join(p.name for p in a._get_ancestors_sudo()),
        } for a in articles]

    def _get_ancestors_sudo(self):
        self.ensure_one()
        ids = [int(i) for i in (self.sudo().parent_path or '').split('/') if i][:-1]
        return self.sudo().browse(ids)

    # ── Share dialog ─────────────────────────────────────────────────
    def _member_info(self, partner, permission, inherited):
        users = partner.user_ids
        user = users[:1]
        return {
            'partner_id': partner.id,
            'name': partner.name,
            'email': partner.email or '',
            'avatar': '/web/image/res.partner/%d/avatar_128' % partner.id,
            'permission': permission,
            'inherited': inherited,
            'is_me': partner == self.env.user.partner_id,
            'is_guest': not user or user.share,
            'is_admin': bool(user) and user.has_group('hudson_knowledge.group_knowledge_manager'),
        }

    def get_share_data(self):
        self.ensure_one()
        self._check_user_can_read()
        article = self.sudo()
        own = {m.partner_id: m.permission for m in article.member_ids}
        perms = article._get_member_permissions()
        me = self.env.user.partner_id
        members = [article._member_info(partner, permission, partner not in own)
                   for partner, permission in perms.items()]
        members.sort(key=lambda m: (not m['is_me'], m['name'].lower()))
        published_ancestor = article._get_ancestors_sudo().filtered('website_published')[:1]
        return {
            'id': article.id,
            'name': article.name,
            'icon': article.icon or '',
            'visibility': article.visibility,
            'internal_permission': article.internal_permission,
            'is_root': not article.parent_id,
            'can_edit': article._get_permission_for_user(self.env.user) == 'write',
            'website_published': article.website_published or bool(published_ancestor),
            'published_by_parent': bool(published_ancestor) and not article.website_published,
            'public_url': article.get_base_url() + '/knowledge/article/%d' % article.id,
            'members': members,
            'me_is_member': me in perms,
        }

    def action_share_search_users(self, search=''):
        """Autocomplete of the "Add people..." input: users, then contacts
        with an email (they get portal access when invited), then the typed
        email address itself when nobody matches it."""
        self.ensure_one()
        self._check_user_can_write()
        existing = self.sudo().access_partner_ids | self.sudo().blocked_partner_ids
        domain = [('active', '=', True), ('partner_id', 'not in', existing.ids)]
        if search:
            domain += ['|', '|', ('name', 'ilike', search), ('login', 'ilike', search),
                       ('partner_id.email', 'ilike', search)]
        users = self.env['res.users'].sudo().search(domain, limit=8, order='share, name')
        result = [{
            'partner_id': u.partner_id.id,
            'name': u.name,
            'email': u.partner_id.email or u.login or '',
            'avatar': '/web/image/res.partner/%d/avatar_128' % u.partner_id.id,
            'is_guest': u.share,
        } for u in users]
        if search and len(result) < 8:
            Partner = self.env['res.partner']
            contacts = Partner.search([
                ('id', 'not in', existing.ids + [r['partner_id'] for r in result]),
                ('email', '!=', False),
                ('user_ids', '=', False),
                ('is_company', '=', False),
                '|', ('name', 'ilike', search), ('email', 'ilike', search),
            ], limit=8 - len(result))
            result += [{
                'partner_id': p.id,
                'name': p.name,
                'email': p.email,
                'avatar': '/web/image/res.partner/%d/avatar_128' % p.id,
                'is_guest': True,
            } for p in contacts]
        email = email_normalize(search or '')
        if email and not any(email_normalize(r['email']) == email for r in result):
            result.append({
                'partner_id': 'email:%s' % email,
                'name': email,
                'email': email,
                'avatar': '/web/static/img/user_placeholder.jpg',
                'is_guest': True,
                'is_new': True,
            })
        return result

    def _knowledge_grant_portal_access(self, partner):
        """Create a portal user for a contact invited to an article (like the
        "Grant portal access" wizard). The invitation mail then carries the
        link to choose a password."""
        partner = partner.sudo()
        email = email_normalize(partner.email or '')
        if not email:
            raise UserError(_('%s has no email address and cannot be invited.', partner.name))
        Users = self.env['res.users'].sudo().with_context(active_test=False)
        user = Users.search([('login', '=', email)], limit=1)
        if user and user.partner_id != partner:
            raise UserError(_('Another user already uses the email %s.', email))
        if not user:
            company = partner.company_id or self.env.company
            user = Users.with_company(company).with_context(no_reset_password=True)._create_user_from_template({
                'email': email,
                'login': email,
                'partner_id': partner.id,
                'company_id': company.id,
                'company_ids': [(6, 0, company.ids)],
            })
        group_portal = self.env.ref('base.group_portal')
        group_public = self.env.ref('base.group_public')
        if not user.active or group_public in user.group_ids:
            user.write({'active': True, 'group_ids': [(4, group_portal.id), (3, group_public.id)]})
        partner.signup_prepare()
        return user

    def action_share_invite(self, partner_ids, permission='write', message=''):
        """:param partner_ids: partner ids, or 'email:<address>' entries of
            the autocomplete for people who are not contacts yet"""
        self.ensure_one()
        self._check_user_can_write()
        if permission not in ('read', 'write'):
            raise UserError(_('Invalid permission.'))
        article = self.sudo()
        Partner = self.env['res.partner'].sudo()
        ids = []
        for value in partner_ids or []:
            if isinstance(value, str) and value.startswith('email:'):
                email = email_normalize(value[6:])
                if not email:
                    raise UserError(_('"%s" is not a valid email address.', value[6:]))
                partner = Partner.search([('email_normalized', '=', email)], limit=1) \
                    or Partner.create({'name': email, 'email': email})
                ids.append(partner.id)
            else:
                ids.append(int(value))
        partners = Partner.browse(ids).exists()
        if not partners:
            return self.get_share_data()
        for partner in partners:
            user = partner.user_ids[:1] or self._knowledge_grant_portal_access(partner)
            partner_permission = 'read' if user.share else permission
            member = article.member_ids.filtered(lambda m: m.partner_id == partner)
            if member:
                member.permission = partner_permission
            else:
                article.member_ids = [(0, 0, {'partner_id': partner.id, 'permission': partner_permission})]
        if article.visibility == 'private' and not article.parent_id:
            article.visibility = 'shared'
            article._get_descendants().write({'visibility': 'shared'})
        article._send_invitation(partners, message)
        return self.get_share_data()

    def _send_invitation(self, partners, message=''):
        """/knowledge/article/<id> opens the backend app for Knowledge users
        and the portal page for everyone else. Guests who never logged in get
        a link to choose their password first."""
        self.ensure_one()
        path = '/knowledge/article/%d' % self.id
        url = self.get_base_url() + path
        for partner in partners:
            user = partner.user_ids[:1]
            link = url
            if user and user.share and not user.login_date:
                link = partner.sudo().with_context(signup_valid=True)._get_signup_url_for_action(url=path)[partner.id]
            body = Markup(_(
                '%(user)s invited you to the article <a href="%(url)s">%(icon)s %(name)s</a>.'
                '%(comment)s<br/><br/><a href="%(url)s" style="background-color:#714B67;padding:8px 16px;'
                'text-decoration:none;color:#fff;border-radius:5px;font-size:13px;">Open the article</a>'
            )) % {
                'user': self.env.user.name, 'url': link, 'icon': self.icon or '', 'name': self.name,
                'comment': Markup('<br/><br/>%s') % message if message else '',
            }
            self.with_context(mail_notify_force_send=False).message_notify(
                partner_ids=partner.ids,
                subject=_('Invitation to access "%s"', self.name),
                body=body,
            )

    def action_share_set_member_permission(self, partner_id, permission):
        self.ensure_one()
        self._check_user_can_write()
        if permission not in PERMISSION_RANK:
            raise UserError(_('Invalid permission.'))
        if partner_id == self.env.user.partner_id.id:
            raise UserError(_('You cannot change your own access.'))
        article = self.sudo()
        partner = self.env['res.partner'].sudo().browse(partner_id)
        user = partner.user_ids[:1]
        if permission == 'write' and user and user.share:
            raise UserError(_('Portal users can only read articles.'))
        member = article.member_ids.filtered(lambda m: m.partner_id == partner)
        if member:
            member.permission = permission
        else:
            article.member_ids = [(0, 0, {'partner_id': partner.id, 'permission': permission})]
        self._normalize_after_member_change()
        return self.get_share_data()

    def action_share_remove_member(self, partner_id):
        self.ensure_one()
        self._check_user_can_write()
        if partner_id == self.env.user.partner_id.id:
            raise UserError(_('You cannot remove yourself.'))
        article = self.sudo()
        member = article.member_ids.filtered(lambda m: m.partner_id.id == partner_id)
        if member:
            member.unlink()
        elif partner_id in article.access_partner_ids.ids:
            # Inherited from a parent article: remove the access here.
            article.member_ids = [(0, 0, {'partner_id': partner_id, 'permission': 'none'})]
        self._normalize_after_member_change()
        return self.get_share_data()

    def action_share_set_general_access(self, value):
        """value: 'write' / 'read' (Workspace) or 'members' (Members only)."""
        self.ensure_one()
        self._check_user_can_write()
        article = self.sudo()
        if article.parent_id:
            raise UserError(_('General access is inherited from the parent article.'))
        if value in ('write', 'read'):
            self._set_category('workspace', value)
        elif value == 'members':
            self._set_category('shared' if article._has_other_members() else 'private')
        else:
            raise UserError(_('Invalid general access.'))
        return self.get_share_data()

    def action_share_set_published(self, published):
        self.ensure_one()
        self._check_user_can_write()
        self.sudo().website_published = bool(published)
        return self.get_share_data()

    def action_set_favorite(self):
        """Favorites only need read access (the list lives on the article)."""
        self.ensure_one()
        self._check_user_can_read()
        return self.sudo()._toggle_favorite_no_write(self.env.user)

    # ── Public page ──────────────────────────────────────────────────
    def _is_published_on_web(self):
        self.ensure_one()
        article = self.sudo()
        return article.active and (article.website_published
                                   or bool(article._get_ancestors_sudo().filtered('website_published')))

