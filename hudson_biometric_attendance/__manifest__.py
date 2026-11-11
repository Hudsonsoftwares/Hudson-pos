# -*- coding: utf-8 -*-
{
    'name': 'Hudson Universal Biometric Attendance Integration',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Unified biometric device and API/webhook attendance integration engine',
    'description': """
This module provides a robust, multi-source biometric and attendance integration engine.
It ingests attendance raw punches from ZK-protocol devices, REST APIs, and webhooks,
normalizes them into a canonical format, validates them, and projects them safely
into Odoo standard hr.attendance.
    """,
    'author': 'Hudson Softwares',
    'depends': [
        'hr_attendance',
        'mail',
        'web',
    ],
    'data': [
        'security/security.xml',
        'security/ir.access.csv',
        'wizard/hudson_attendance_map_reprocess_wizard_views.xml',
        'views/hr_employee_views.xml',
        'views/hudson_attendance_device_views.xml',
        'views/hudson_attendance_raw_punch_views.xml',
        'views/hudson_biometric_integration_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
