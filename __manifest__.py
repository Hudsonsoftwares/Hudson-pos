{
    'name': 'Appointments',
    'version': '20.0.1.0.0',
    'category': 'Services/Appointments',
    'sequence': 100,
    'summary': 'Allow people to book meetings in your agenda',
    'description': """
        Odoo 20 Appointment Module
        - Appointment Types
        - Booking Engine
        - Resources
        - Availability Calculation
    """,
    'depends': ['base', 'mail', 'website', 'calendar', 'google_calendar', 'resource', 'portal', 'crm', 'product', 'payment', 'sale'],
    'data': [
        'security/appointment_security.xml',
        'security/ir.access.csv',
        'views/appointment_booking_views.xml',
        'views/appointment_closing_day_views.xml',
        'views/appointment_resource_views.xml',
        'views/appointment_type_wizard_views.xml',
        'views/appointment_type_views.xml',
        'views/appointment_question_views.xml',
        'views/appointment_invite_views.xml',
        'views/appointment_menus.xml',
        'views/appointment_templates.xml',
        'views/appointment_portal_templates.xml',
        'data/ir_sequence_data.xml',
        'data/mail_template_data.xml',
        'data/portal_entry_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'appointment/static/src/scss/appointment_type_views.scss',
            'appointment/static/src/js/appointment_type_views.js',
            'appointment/static/src/js/appointment_calendar.js',
            'appointment/static/src/xml/appointment_calendar.xml',
            'appointment/static/src/xml/appointment_type_views.xml',
            'appointment/static/src/js/appointment_list.js',
            'appointment/static/src/xml/appointment_list.xml',
        ],
        'web.assets_frontend': [],
    },
    'demo': [],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
