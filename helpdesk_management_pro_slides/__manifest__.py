# -*- coding: utf-8 -*-
{
    'name': 'Helpdesk Pro - eLearning',
    'version': '20.0.1.0.0',
    'category': 'Services/Helpdesk',
    'summary': 'Link Helpdesk Pro Tickets and Teams with eLearning Courses',
    'description': """
        Integrates Helpdesk Management Pro with Website Slides (eLearning):
        - Publish eLearning courses in helpdesk team help centers.
        - Link eLearning lessons and slides to tickets.
    """,
    'author': 'Antigravity',
    'depends': ['helpdesk_management_pro', 'website_slides'],
    'data': [
        'views/helpdesk_team_views.xml',
        'views/helpdesk_ticket_views.xml',
    ],
    'installable': True,
    'auto_install': True,
    'license': 'LGPL-3',
}
