# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

{
    'name': 'POS Table Booking Bridge',
    'version': '20.0.1.3.11',
    'category': 'Sales/Point of Sale',
    'author': 'Hudson',
    'summary': 'Connects Appointment booking engine to Odoo Restaurant POS',
    'description': """
        Bridge module connecting the stock Appointment module to Odoo 20 POS Restaurant.
        The Appointment module is used unmodified: every customisation needed by the
        table booking flow (celebration fields, Date questions, phone-first guest
        details, Email/SMS confirmations, yearly celebration wishes) lives here.
        - Table booking badges on POS Floor Plan
        - Bookings management screen inside POS (Booked, Checked-in, No-show)
        - Walk-in booking creation without email requirement
        - Direct linking between POS Orders and Bookings
        - Scheduled no-show processing
        - Real-time bus synchronization
        - Permanent Pre-Order Food preset & schedule
    """,
    'depends': ['pos_restaurant', 'appointment', 'pos_self_order', 'account', 'payment_demo', 'sms'],
    'data': [
        'security/ir.access.csv',
        'data/ir_cron_data.xml',
        'data/ir_cron_celebration_data.xml',
        'data/mail_template_celebration_data.xml',
        'data/pos_preset_data.xml',
        'views/restaurant_table_views.xml',
        'views/pos_config_views.xml',
        'views/appointment_type_views.xml',
        'views/appointment_resource_views.xml',
        'views/appointment_booking_views.xml',
        'views/appointment_celebration_views.xml',
        'views/appointment_templates.xml',
        'views/appointment_celebration_templates.xml',
        'views/account_invoice_report_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'hudson_pos_booking/static/src/scss/appointment_booking_frontend.scss',
        ],
        'point_of_sale._assets_pos': [
            'hudson_pos_booking/static/src/scss/booking_screen.scss',
            'hudson_pos_booking/static/src/js/booking_model.js',
            'hudson_pos_booking/static/src/js/restaurant_table_patch.js',
            'hudson_pos_booking/static/src/js/pos_store_patch.js',
            'hudson_pos_booking/static/src/js/pos_receipt_survey_qr.js',
            'hudson_pos_booking/static/src/js/booking_screen.js',
            'hudson_pos_booking/static/src/xml/floor_plan_booking_badge.xml',
            'hudson_pos_booking/static/src/xml/booking_screen.xml',
        ],
    },
    'post_init_hook': '_post_init_hook',
    'installable': True,
    'auto_install': True,
    'license': 'LGPL-3',
}
