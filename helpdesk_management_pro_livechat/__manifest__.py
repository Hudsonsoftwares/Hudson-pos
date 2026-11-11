# -*- coding: utf-8 -*-
{
    'name': 'Helpdesk Pro - Live Chat',
    'version': '20.0.1.0.0',
    'category': 'Services/Helpdesk',
    'summary': 'Link Helpdesk Pro Tickets with Live Chat and Chatbots',
    'description': """
        Integrates Helpdesk Management Pro with Live Chat:
        - Create helpdesk tickets directly from livechat conversations using /ticket command.
        - Chatbot script step to generate tickets automatically.
    """,
    'author': 'Antigravity',
    'depends': ['helpdesk_management_pro', 'im_livechat'],
    'data': [
        'data/livechat_chatbot_data.xml',
        'views/livechat_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'helpdesk_management_pro_livechat/static/src/livechat/channel_commands.js',
        ],
    },
    'installable': True,
    'auto_install': True,
    'license': 'LGPL-3',
}

