# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestHelpdeskKnowledge(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env['website'].search([], order='sequence, id', limit=1)
        cls.article = cls.env['knowledge.management.article'].create({'name': 'Router FAQ', 'body_html': '<p>Routers</p>'})
        cls.sub_article = cls.env['knowledge.management.article'].create({
            'name': 'Router lights explained', 'parent_id': cls.article.id,
        })
        cls.team = cls.env['helpdesk.management.team'].create({
            'name': 'Knowledge Support',
            'use_website_helpdesk_knowledge': True,
            'website_article_id': cls.article.id,
        })

    def test_knowledge_team_content(self):
        self.assertTrue(self.article.share_to_web and self.sub_article.share_to_web,
                        "The help center article and its sub-articles are shared to the web.")
        self.assertIn(self.team, self.env['helpdesk.management.team']._get_help_center_teams(self.website),
                      "A team only using Knowledge is exposed on the help center.")
        content = self.team._get_help_center_content()
        self.assertTrue(content['show_knowledge'])
        self.assertEqual(content['articles'], self.article | self.sub_article)

    def test_knowledge_help_center_page_and_search(self):
        res = self.url_open('/helpdesk')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Knowledge Base', res.text)
        self.assertIn('/knowledge/article/%s' % self.article.id, res.text)

        res = self.url_open(self.team.website_url + '?search=lights')
        self.assertEqual(res.status_code, 200)
        self.assertIn('Router lights explained', res.text)
