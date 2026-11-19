# -*- coding: utf-8 -*-
{
    'name': 'POS Theme & Floor Decor',
    'version': '20.0.1.0.2',
    'category': 'Sales/Point of Sale',
    'summary': 'Touch polish, table status colours, and restaurant floor plan decor library for POS',
    'description': """
POS Theme & Floor Plan Decor
============================
Visual refinements and floor plan decor library for Odoo Point of Sale:

* Floor plan decor library: permanent, reusable restaurant furniture and decor in the "Add Decor" editor:
  - Furniture & Stations: Waiting Lounge sets, Reception desks, Coffee & Mocktail bar counters,
    Booth / Banquette leather sofas, Kitchen pass counters, Dessert displays, Potted palm trees,
    Restrooms signs, Entrance welcome mats.
  - Patio & Outdoor: Live BBQ grill stations, Fire-pit lounges, Tiered water fountains, Patio parasols.
* Floor plan: table status rings (free / occupied / items not sent to kitchen / booked), guest count and
  order amount on occupied tables, a status legend, larger table numbers and floor tabs.
* Product screen: 48px touch targets for categories, control buttons and numpad, cleaner product cards
  with press feedback, larger search field.
* Order panel: roomier order lines, clearly highlighted selected line, aligned quantities and prices,
  readable notes, bigger Payment button and total.
* Payment screen: bigger payment method tiles, clearer selected payment line, larger amounts,
  emphasised change / remaining amount, big Validate button.

Auto-installs automatically whenever Point of Sale Restaurant is installed.
    """,
    'author': 'Hudson Software Solutions',
    'depends': ['point_of_sale', 'pos_restaurant'],
    'data': [],
    'assets': {
        'point_of_sale._assets_pos': [
            'hudson_pos_theme/static/src/scss/pos_touch_polish.scss',
            'hudson_pos_theme/static/src/xml/floor_table_status.xml',
            'hudson_pos_theme/static/src/js/add_decor_popup.js',
            'hudson_pos_theme/static/src/xml/add_decor_popup.xml',
        ],
    },
    'installable': True,
    'auto_install': True,
    'application': False,
    'license': 'LGPL-3',
}
