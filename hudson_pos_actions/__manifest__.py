# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

{
    'name': 'POS Actions Menu Enhancements',
    'version': '20.0.1.0.13',
    'category': 'Sales/Point of Sale',
    'author': 'Hudson',
    'summary': 'Enhanced POS Actions (3-dot) menu and Self-Order configuration matching Odoo Online SaaS',
    'description': """
        Extends the Odoo POS Actions (3-dot) menu with:
        - 5-column grid layout matching Odoo Online
        - Customer Note with backend persistence
        - Bill generation and printing
        - Enter Code with coupon/promo/discount validation
        - Seamless integration with Guest, Split, Transfer, Set Order Name, Reward, Pricelist, and Info
        - Enables Mobile Self-Order Table service with Pay after Each Order without enterprise restrictions
        - Enables persistent 'Order Now' button and streamlined Cancel Order on Self-Order Landing & Cart
    """,
    'depends': ['point_of_sale', 'pos_restaurant', 'pos_sale', 'pos_self_order', 'pos_online_payment_self_order'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/pos_online_payment_templates.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'hudson_pos_actions/static/src/scss/pos_actions_modal.scss',
            'hudson_pos_actions/static/src/js/control_buttons_patch.js',
            'hudson_pos_actions/static/src/xml/control_buttons.xml',
        ],
        'pos_self_order.assets': [
            'hudson_pos_actions/static/src/js/landing_page_patch.js',
        ],
    },
    'installable': True,
    'auto_install': ['point_of_sale', 'pos_restaurant'],
    'license': 'LGPL-3',
}
