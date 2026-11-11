# -*- coding: utf-8 -*-
{
    'name': 'Helpdesk Pro - Community Forum',
    'version': '20.0.1.0.0',
    'category': 'Services/Helpdesk',
    'summary': 'Link Helpdesk Pro Tickets with Website Forum',
    'description': """
        Integrates Helpdesk Management Pro with Community Forum:
        - Share tickets on forum.
        - Create tickets from forum questions.
    """,
    'author': 'Antigravity',
    'depends': ['helpdesk_management_pro', 'website_forum'],
    'data': [
        'security/ir.access.csv',
        'wizard/ticket_share_forum_views.xml',
        'views/helpdesk_team_views.xml',
        'views/helpdesk_ticket_views.xml',
        'views/forum_post_views.xml',
    ],
    'installable': True,
    'auto_install': True,
    'license': 'LGPL-3',
}
