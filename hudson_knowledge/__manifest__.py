# -*- coding: utf-8 -*-
{
    'name': 'Hudson Knowledge',
    'version': '20.0.1.2.2',
    'category': 'Productivity/Knowledge',
    'summary': 'Create, share and manage knowledge articles with a rich text editor',
    'description': """
        Hudson Knowledge provides a full-featured knowledge base application:
        - Rich text articles with the native Odoo WYSIWYG editor
        - Sidebar with Favorites, Workspace, Shared and Private sections
        - Article hierarchy (parent/child tree)
        - Embedded Item Kanban, Item List and Item Calendar views inside articles
        - Article templates, cover images, icons and properties
        - Share articles with users, portal guests and contacts (portal access is granted on invite)
        - Portal app for guests (/knowledge/home): sidebar, favorites, private articles, editor
        - Lock content, Full-width mode, Move to Trash
        - Knowledge button on every form view with a chatter ("?" in the command palette)
    """,
    'author': 'Hudson Softwares',
    'website': 'https://hudsonsoftwares.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'mail',
        'web',
        'portal',
        'html_editor',
    ],
    'data': [
        'security/knowledge_security.xml',
        'security/ir.access.csv',
        'data/knowledge_template_category_data.xml',
        'data/knowledge_data.xml',
        'data/knowledge_cron.xml',
        'data/knowledge_portal_data.xml',
        'views/knowledge_views.xml',
        'views/knowledge_item_views.xml',
        'views/knowledge_template_views.xml',
        'views/knowledge_menu.xml',
        'views/knowledge_public_templates.xml',
        'report/knowledge_article_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'web/static/src/core/emoji_picker/emoji_data.js',
            'hudson_knowledge/static/src/scss/knowledge.scss',
            'hudson_knowledge/static/src/xml/knowledge_templates.xml',
            'hudson_knowledge/static/src/xml/knowledge_item_view.xml',
            'hudson_knowledge/static/src/xml/knowledge_share_dialog.xml',
            'hudson_knowledge/static/src/xml/knowledge_command_palette.xml',
            'hudson_knowledge/static/src/xml/knowledge_properties_panel.xml',
            'hudson_knowledge/static/src/js/knowledge_properties_panel.js',
            'hudson_knowledge/static/src/js/knowledge_item_view.js',
            'hudson_knowledge/static/src/js/knowledge_share_dialog.js',
            'hudson_knowledge/static/src/js/knowledge_action.js',
            'hudson_knowledge/static/src/js/knowledge_wysiwyg_commands.js',
            'hudson_knowledge/static/src/js/knowledge_command_palette.js',
        ],
        'web.assets_frontend': [
            'hudson_knowledge/static/src/portal/knowledge_portal.scss',
            'hudson_knowledge/static/src/portal/knowledge_portal.js',
        ],
        # Loaded by the portal page only when the visitor can edit the article.
        'hudson_knowledge.assets_portal_editor': [
            ('include', 'web._assets_helpers'),
            ('include', 'web._assets_frontend_helpers'),
            'web/static/src/scss/pre_variables.scss',
            'web/static/lib/bootstrap/scss/_variables.scss',
            'web/static/lib/bootstrap/scss/_variables-dark.scss',
            ('include', 'html_editor.assets_editor'),
            'hudson_knowledge/static/src/portal/editor/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'icon': '/hudson_knowledge/static/description/icon.png',
}
