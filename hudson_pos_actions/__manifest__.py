# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

{
    'name': 'POS Actions Menu Enhancements',
    'version': '20.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'author': 'Hudson',
    'summary': 'Enhanced POS Actions (3-dot) menu matching Odoo Online SaaS',
    'description': """
        Extends the Odoo POS Actions (3-dot) menu with:
        - 5-column grid layout matching Odoo Online
        - Customer Note with backend persistence
        - Bill generation and printing
        - Enter Code with coupon/promo/discount validation
        - Seamless integration with Guest, Split, Transfer, Set Order Name, Reward, Pricelist, and Info
    """,
    'depends': ['point_of_sale', 'pos_restaurant', 'pos_sale'],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'hudson_pos_actions/static/src/scss/pos_actions_modal.scss',
            'hudson_pos_actions/static/src/js/control_buttons_patch.js',
            'hudson_pos_actions/static/src/xml/control_buttons.xml',
        ],
    },
    'installable': True,
    'auto_install': ['point_of_sale', 'pos_restaurant'],
    'license': 'LGPL-3',
}
