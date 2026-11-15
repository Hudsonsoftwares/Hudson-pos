# -*- coding: utf-8 -*-
{
    'name': 'Hudson Shop Floor',
    'version': '20.0.1.0.0',
    'category': 'Manufacturing/Manufacturing',
    'summary': 'Custom Shop Floor interface for Odoo Community',
    'description': """
        A dedicated Shop Floor module providing an enterprise-like 
        OWL-based application for manufacturing operations.
    """,
    'author': 'Hudson',
    'depends': ['mrp', 'maintenance', 'web', 'hr'],
    'data': [
        'views/shopfloor_menu.xml',
        'views/mrp_workcenter_views.xml',
        'views/mrp_production_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hudson_shopfloor/static/src/components/**/*.js',
            'hudson_shopfloor/static/src/components/**/*.xml',
            'hudson_shopfloor/static/src/components/**/*.css',
        ],
    },
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
