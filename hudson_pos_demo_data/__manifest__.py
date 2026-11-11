# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

{
    'name': 'POS Demo Data (Restaurant, Cafe, Loyalty & Inventory)',
    'version': '20.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'author': 'Hudson',
    'summary': 'Declarative XML Demo Data for POS (Restaurant, Cafe, Clothes & Furniture Shops) with on-demand UI Loader',
    'description': """
        Declarative Standard Odoo Demo Data for Point of Sale:
        - Auto-installs automatically with Point of Sale so you never have to manually install it.
        - Categories: Food, Drinks, Desserts, Chocolates, Clothes (Men, Women, Shoes), Furniture (Living, Bed, Office, Decor)
        - Products: 69 POS products across Restaurant, Cafe, Clothes & Furniture
        - Floors & Tables: Main Floor (12 Tables) & Patio (12 Tables)
        - Courses: Starter, Main Course, Dessert, Drinks
        - Notes: Preparation Note Models (Extra Spicy, Less Sugar, No Ice, etc.)
        - Pricelists: Happy Hour (20% off), VIP Member (15% off)
        - Loyalty: Gift Cards, eWallet, and Promotional Programs
        - On-Demand Loading: Load and clear demo data at any time via UI button in Settings or Configuration menu.
    """,
    'depends': ['point_of_sale', 'pos_restaurant', 'pos_loyalty', 'stock'],
    'auto_install': ['point_of_sale'],
    'data': [
        'views/pos_config_views.xml',
        'views/res_config_settings_views.xml',
        'views/server_actions.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'hudson_pos_demo_data/static/src/overrides/control_buttons.js',
        ],
    },
    # demo list intentionally empty:
    # All demo data loads ON-DEMAND via "Load Demo Data" button only.
    # Nothing auto-loads on fresh install.
    'demo': [],
    'installable': True,
    'license': 'LGPL-3',
}
