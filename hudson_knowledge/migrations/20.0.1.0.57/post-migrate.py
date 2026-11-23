# -*- coding: utf-8 -*-
"""Put the templates users saved before categories existed in "My Templates"."""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    category = env.ref('hudson_knowledge.knowledge_template_category_custom', raise_if_not_found=False)
    if not category:
        return
    env['knowledge.management.article.template'].search(
        [('category_id', '=', False)]).write({'category_id': category.id})
