# -*- coding: utf-8 -*-
# pyrefly: ignore[missing-import]
from odoo.addons.helpdesk_management_pro.controllers.help_center import HelpdeskHelpCenter


class HelpdeskKnowledgeHelpCenter(HelpdeskHelpCenter):

    def _search_help_center(self, content, search):
        results = super()._search_help_center(content, search)
        articles = content.get('articles')
        results['articles'] = articles.filtered_domain([
            '|', ('name', 'ilike', search), ('body_html', 'ilike', search),
        ])[:self._search_limit] if articles else []
        return results
