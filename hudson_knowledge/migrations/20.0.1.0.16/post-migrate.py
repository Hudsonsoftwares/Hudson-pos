# -*- coding: utf-8 -*-
"""Odoo Online style sharing.

* every root article gets its creator as "Can Edit" member (owner);
* a Shared article that is shared with nobody becomes Private;
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    Article = env['knowledge.management.article']
    roots = Article.search([('parent_id', '=', False)])
    for article in roots:
        owner = article.create_uid.partner_id
        if owner and owner not in article.member_ids.partner_id:
            article.member_ids = [(0, 0, {'partner_id': owner.id, 'permission': 'write'})]
    for article in roots.filtered(lambda a: a.visibility == 'shared'):
        owner = article.create_uid.partner_id
        if not (article.member_ids.filtered(lambda m: m.permission != 'none').partner_id - owner):
            descendants = Article.search([('id', 'child_of', article.id)])
            descendants.write({'visibility': 'private'})
    env.flush_all()
