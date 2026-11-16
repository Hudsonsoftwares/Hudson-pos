# -*- encoding: utf-8 -*-
##############################################################################
#
# ERP Heritage
# Copyright (C) 2026 (https://www.erpheritage.com.au/)
#
##############################################################################
{
    'name': 'Visitor Management',
    'summary': 'Self-hosted front-desk visitor sign-in for Odoo 19 Community that runs on the same reception tablet as the attendance kiosk, just a different URL. Visitors enter their details, pick a host by typeahead, accept an NDA when the purpose requires it, optionally take a photo, and tap Sign in. The host gets an email, the NDA text is snapshotted onto the record, an end-of-day cron closes overstays, and a retention cron deletes old rows with their photos and NDA snapshots. Visitor management, front desk sign-in, visitor log book, NDA capture, contractor sign-in, reception kiosk, guest check-in, host notification, visitor badge log, hr attendance visitor, Odoo 19 Community visitor management.',
    'description': 'Front-desk visitor sign-in built on the ERP Heritage attendance suite kiosk infrastructure. Configurable visit purposes with per-purpose NDA and photo rules, device-token-authenticated public endpoints with rate limiting, host email notification, NDA text snapshot, optional camera photo with consent, per-company auto check-out and retention crons, and per-company record isolation.',
    'author': 'ERP Heritage',
    'website': 'https://www.erpheritage.com.au/',
    'license': 'LGPL-3',
    'category': 'Human Resources',
    'version': '1.1.0',
    'depends': [
        'eh_hr_attendance_base',
        'eh_hr_core',
        'mail',
        'hr',
    ],
    'data': [
        'security/ir.access.csv',
        'security/eh_hr_isolation_rules.xml',
        'data/visitor_purposes.xml',
        'data/visitor_drinks.xml',
        'data/email_templates.xml',
        'data/ir_mail_server_data.xml',
        'data/cron.xml',
        'views/dashboard_views.xml',
        'views/eh_hr_visitor_drink_views.xml',
        'views/eh_hr_visitor_station_views.xml',
        'views/eh_hr_visitor_views.xml',
        'views/eh_hr_visitor_qr_scan_wizard_views.xml',
        'views/eh_hr_visitor_invitation_views.xml',
        'report/visitor_agreement_report.xml',
        'views/frontdesk_kiosk_template.xml',
        'views/visitor_kiosk_template.xml',
        'views/visitor_preregistration_templates.xml',
        'views/eh_hr_visitor_scanner_template.xml',
        'views/res_config_settings_views.xml',
        'views/menus.xml',
        'views/eh_hr_visitor_reports.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'eh_hr_visitor/static/src/dashboard/dashboard.js',
            'eh_hr_visitor/static/src/dashboard/dashboard.xml',
            'eh_hr_visitor/static/src/dashboard/dashboard.scss',
        ],
    },
    'images': ['static/description/banner.gif'],
    'installable': True,
    'application': True,
    'auto_install': False,
}
