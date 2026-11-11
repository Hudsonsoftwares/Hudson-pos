# -*- coding: utf-8 -*-
{
    'name': 'Helpdesk Pro - CRM',
    'version': '20.0.1.0.0',
    'category': 'Services/Helpdesk',
    'summary': 'Link Helpdesk Pro Tickets with CRM Leads',
    'description': """
        Integrates Helpdesk Management Pro with CRM:
        - Convert helpdesk tickets to CRM leads/opportunities.
        - View leads linked to tickets directly from the ticket form.
    """,
    'author': 'Antigravity',
    'depends': ['helpdesk_management_pro', 'crm'],
    'data': [
        'security/ir.access.csv',
        'wizard/ticket_convert_views.xml',
        'views/helpdesk_ticket_views.xml',
    ],
    'installable': True,
    'auto_install': True,
    'license': 'LGPL-3',
}

