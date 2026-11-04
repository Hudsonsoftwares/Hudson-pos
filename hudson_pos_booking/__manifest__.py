# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

{
    'name': 'POS Table Booking Bridge',
    'version': '20.0.1.0.0',
    'category': 'Sales/Point of Sale',
    'author': 'Hudson',
    'summary': 'Connects Appointment booking engine to Odoo Restaurant POS',
    'description': """
        Bridge module connecting the custom Appointment module to Odoo 20 POS Restaurant.
        - Table booking badges on POS Floor Plan
        - Bookings management screen inside POS (Booked, Checked-in, No-show)
        - Walk-in booking creation without email requirement
        - Direct linking between POS Orders and Bookings
        - Scheduled no-show processing
        - Real-time bus synchronization
    """,
    'depends': ['pos_restaurant', 'appointment'],
    'data': [
        'security/ir.access.csv',
        'data/ir_cron_data.xml',
        'views/restaurant_table_views.xml',
        'views/pos_config_views.xml',
        'views/appointment_booking_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            'hudson_pos_booking/static/src/js/booking_model.js',
            'hudson_pos_booking/static/src/js/restaurant_table_patch.js',
            'hudson_pos_booking/static/src/js/pos_store_patch.js',
            'hudson_pos_booking/static/src/js/booking_screen.js',
            'hudson_pos_booking/static/src/xml/floor_plan_booking_badge.xml',
            'hudson_pos_booking/static/src/xml/booking_screen.xml',
        ],
    },
    'installable': True,
    'auto_install': True,
    'license': 'LGPL-3',
}
