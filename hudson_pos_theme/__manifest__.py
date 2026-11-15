# -*- coding: utf-8 -*-
{
    'name': 'POS Touch Polish',
    'version': '20.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Bigger touch targets, clearer buttons and table status colours for the POS (visual only)',
    'description': """
POS Touch Polish
================
Visual-only refinements of the standard Odoo POS. Keeps the Odoo colours and layout.

* Product screen: 48px touch targets for categories, control buttons and numpad, cleaner product cards
  with press feedback, larger search field.
* Order panel: roomier order lines, clearly highlighted selected line, aligned quantities and prices,
  readable notes, bigger Payment button and total.
* Floor plan: table status rings (free / occupied / items not sent to kitchen / booked), guest count and
  order amount on occupied tables, a status legend, larger table numbers and floor tabs.
* Payment screen: bigger payment method tiles, clearer selected payment line, larger amounts,
  emphasised change / remaining amount, big Validate button.

No business logic, payment, kitchen or data changes. Uninstall to return to the stock look.
    """,
    'author': 'Hudson Software Solutions',
    'depends': ['point_of_sale', 'pos_restaurant'],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'hudson_pos_theme/static/src/scss/pos_touch_polish.scss',
            'hudson_pos_theme/static/src/xml/floor_table_status.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
