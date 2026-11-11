# -*- coding: utf-8 -*-
{
    'name': 'Helpdesk Pro - Project',
    'version': '20.0.1.0.0',
    'category': 'Services/Helpdesk',
    'summary': 'Link Helpdesk Pro Tickets with Project Tasks',
    'description': """
        Integrates Helpdesk Management Pro with Project:
        - Convert helpdesk tickets to project tasks.
        - Plan interventions on tickets.
        - View linked tasks from tickets.
    """,
    'author': 'Antigravity',
    'depends': ['helpdesk_management_pro', 'project'],
    'data': [
        'security/ir.access.csv',
        'wizard/ticket_convert_views.xml',
        'views/helpdesk_ticket_views.xml',
        'views/project_task_views.xml',
    ],
    'installable': True,
    'auto_install': True,
    'license': 'LGPL-3',
}

