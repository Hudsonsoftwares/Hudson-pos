# -*- coding: utf-8 -*-
{
    'name': 'Kitchen Mode Terminology for Manufacturing',
    'version': '1.0.0',
    'category': 'Manufacturing/Manufacturing',
    'summary': 'Presentation-level Kitchen Mode terminology for Manufacturing (Recipes, Kitchen Stations, Tasks, etc.)',
    'description': """
Kitchen Mode Terminology for Odoo Manufacturing
===============================================
Enables restaurant/kitchen terminology for the Manufacturing module without
altering any underlying business logic, models, workflows, or database records.

When Kitchen Mode is enabled:
- Bills of Materials -> Recipes
- Work Centers -> Kitchen Stations
- Work Orders -> Kitchen Tasks
- Manufacturing Orders -> Production Orders
- Components -> Ingredients
- Operations -> Prep Steps
- Scrap Orders -> Wastage
- Unbuild Orders -> Batch Reversals
- Overall Equipment Effectiveness -> Station Efficiency
- Shop Floor -> Kitchen Floor

Administrators can customize or add terminology mappings in:
Manufacturing -> Configuration -> Kitchen Labels
    """,
    'author': 'Hudson POS Team',
    'depends': ['mrp', 'web'],
    'data': [
        'security/ir.access.csv',
        'data/kitchen_label_data.xml',
        'views/kitchen_label_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hudson_kitchen_terms/static/src/js/kitchen_terms.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': True,
    'license': 'LGPL-3',
}
