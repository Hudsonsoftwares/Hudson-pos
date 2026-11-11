# -*- coding: utf-8 -*-
{
    'name': 'Helpdesk Pro',
    'version': '20.0.1.2.3',
    'category': 'Services/Helpdesk',
    'summary': 'Advanced Helpdesk Management Pro',
    'description': """
        Standalone Helpdesk Management application for Odoo.
        Provides ticketing, SLA management, teams, and customer portal.
    """,
    'author': 'Antigravity',
    'website': 'https://www.example.com',
    'depends': ['base', 'mail', 'portal', 'resource', 'website'],
    'data': [
        'security/helpdesk_security.xml',
        'security/ir.access.csv',
        'data/mail_template_data.xml',
        'data/helpdesk_data.xml',
        'data/website_menu_data.xml',
        'data/website_form_data.xml',
        'views/helpdesk_menu_views.xml',
        'views/helpdesk_ticket_views.xml',
        'views/helpdesk_stage_views.xml',
        'views/mail_activity_type_views.xml',
        'views/helpdesk_category_views.xml',
        'views/helpdesk_sla_views.xml',
        'views/helpdesk_reporting_views.xml',
        'views/helpdesk_team_views.xml',
        'views/helpdesk_portal_templates.xml',
    ],
    'assets': {
        # Website Form Builder "Create a Ticket" action
        'website.website_builder_assets': [
            'helpdesk_management_pro/static/src/js/website_helpdesk_form_editor.js',
        ],
        'website.assets_inside_builder_iframe': [
            'helpdesk_management_pro/static/src/js/website_helpdesk_form_editor.edit.js',
        ],
        'web.assets_backend': [
            'helpdesk_management_pro/static/src/dashboard/helpdesk_dashboard.js',
            'helpdesk_management_pro/static/src/dashboard/helpdesk_dashboard.xml',
            'helpdesk_management_pro/static/src/dashboard/helpdesk_dashboard.scss',
            'helpdesk_management_pro/static/src/scss/helpdesk_team_form.scss',
        ],
        'web.assets_web_dark': [
            'helpdesk_management_pro/static/src/dashboard/helpdesk_dashboard.dark.scss',
        ],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
