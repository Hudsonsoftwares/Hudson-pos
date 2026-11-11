# -*- coding: utf-8 -*-
{
    'name': 'Helpdesk Pro - Knowledge',
    'version': '20.0.1.0.0',
    'category': 'Services/Helpdesk',
    'summary': 'Publish Knowledge articles in the Helpdesk Pro help center',
    'description': """
        Bridge between Helpdesk Management Pro and Hudson Knowledge.
        Lets a helpdesk team publish a Knowledge article (and its sub-articles)
        in the website help center, and makes those articles searchable there.
        Installed automatically when both modules are installed.
    """,
    'author': 'Antigravity',
    'website': 'https://www.example.com',
    'depends': ['helpdesk_management_pro', 'hudson_knowledge'],
    'data': [
        'views/helpdesk_team_views.xml',
        'views/helpdesk_portal_templates.xml',
    ],
    'installable': True,
    'auto_install': True,
    'license': 'LGPL-3',
}
