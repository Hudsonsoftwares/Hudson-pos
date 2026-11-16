# -*- encoding: utf-8 -*-
##############################################################################
#
# ERP Heritage
# Copyright (C) 2026 (https://www.erpheritage.com.au/)
#
##############################################################################
{
    'name': 'Attendance Suite Base',
    'summary': 'Shared foundation engine for the ERP Heritage attendance and people operations suite on Odoo 19 Community, providing a biometric and geolocation consent lifecycle, a kiosk site and terminal registry with rotating tokens, a kiosk audit event log, and an attendance exception model, with daily retention crons and multi company record rule isolation, biometric attendance, face attendance consent, kiosk time clock, device pairing PIN, time and attendance audit trail, GDPR consent record, hr_attendance extension, employee clock in clock out, exception management, geofence configuration, retention policy.',
    'description': 'A base engine for the ERP Heritage attendance suite on Odoo 19 Community. It models biometric and location consent with explicit pending, granted, withdrawn, and expired states, a kiosk site and terminal registry with server issued rotating tokens and one shot pairing PINs, a kiosk audit event log, and an attendance exception record. Daily crons expire and prune consent and trim the audit trail to each company configured horizon. Every model is company scoped by global record rule. This is plumbing other modules build on, not a clock in app by itself.',
    'author': 'ERP Heritage',
    'website': 'https://www.erpheritage.com.au/',
    'license': 'LGPL-3',
    'category': 'Human Resources/Attendances',
    'version': '1.0.0',
    'depends': [
        'base',
        'mail',
        'hr',
        'hr_attendance',
        'eh_hr_compat',
    ],
    'post_init_hook': 'post_init_hook',
    'data': [
        'security/eh_hr_security.xml',
        'security/eh_hr_isolation_rules.xml',
        'security/ir.access.csv',
        'data/cron.xml',
        'views/eh_hr_consent_views.xml',
        'views/eh_hr_kiosk_views.xml',
        'views/eh_hr_attendance_exception_views.xml',
        'views/hr_employee_views.xml',
        'views/menus.xml',
        'views/res_config_settings_views.xml',
    ],
    'images': ['static/description/banner.gif'],
    'installable': True,
    'application': False,
    'auto_install': False,
}
