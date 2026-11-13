# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

{
    'name': 'POS Demo Data (Restaurant, Cafe, Loyalty & Inventory)',
    'version': '20.0.1.0.4',
    'category': 'Sales/Point of Sale',
    'author': 'Hudson',
    'summary': 'Declarative XML & Python Demo Data for POS (Restaurant, Cafe, Loyalty & Inventory) loaded on manual module activation',
    'description': """
        Declarative Standard Odoo Demo Data for Point of Sale:
        - Does NOT auto-install; install/activate this module manually when demo data is needed.
        - Categories: Food, Drinks, Desserts, Chocolates & Sweets
        - Products: 40+ Restaurant & Cafe POS products with product images and combos
        - Floors & Tables: Main Floor (12 Tables) & Patio (12 Tables)
        - Courses: Starter, Main Course, Dessert, Drinks
        - Notes: Preparation Note Models (Extra Spicy, Less Sugar, No Ice, etc.)
        - Pricelists: Happy Hour (20% off), VIP Member (15% off)
        - Loyalty: Gift Cards, eWallet, and Promotional Programs
        - Inventory: Restaurant ingredients, packaging, vendors, Cold/Dry/Kitchen locations, reordering rules, BoMs, and move history
        - Automatically loads demo data on module activation via post_init_hook and cleans up on uninstall.
    """,
    'depends': ['point_of_sale', 'pos_restaurant', 'pos_loyalty', 'stock'],
    'auto_install': False,
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'hudson_pos_demo_data/static/src/overrides/control_buttons.js',
        ],
    },
    'demo': [],
    'post_init_hook': '_post_init_hook',
    'uninstall_hook': '_uninstall_hook',
    'installable': True,
    'license': 'LGPL-3',
}
