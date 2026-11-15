# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

{
    'name': 'Planning',
    'version': '20.0.1.13.0',
    'category': 'Human Resources/Planning',
    'sequence': 56,
    'summary': 'Manage shifts, planning roles, and assignments',
    'description': """
Planning Management
===================

A planning management module for Odoo 19 that provides:
* **Shift Management** - Plan and assign shifts to employees.
* **Planning Roles** - Define roles for shift assignments.
* **Attendance Integration** - Link shifts to attendance records.
* **Plan Services** - Services sold generate open shifts for a role when the Sales Order is confirmed.
* **Field Service** - With Field Service installed, a shift with a customer is a field service job.
    """,
    'website': 'https://github.com/nandusaji2001/hudson-community',
    'author': 'Hudson Community',
    'depends': [
        'hr',
        'hr_attendance',
        'mail',
        'base_geolocalize',  # customers located on the map view
        'project',
        'sale',
        'web',
    ],
    'data': [
        'security/planning_security.xml',
        'security/ir.access.csv',
        'data/fs_planning_role_data.xml',
        'wizard/fs_shift_template_apply_wizard_views.xml',
        'wizard/fs_shift_confirm_wizard_views.xml',
        'views/fs_planning_slot_views.xml',
        'views/fs_planning_role_views.xml',
        'views/fs_shift_template_views.xml',
        'views/field_service_planning_board_views.xml',
        'views/res_config_settings_views.xml',
        'views/product_sale_views.xml',
        'views/planning_menus.xml',
        'report/fs_schedule_report.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hudson_planning/static/src/css/fs_planning_board.css',
            'hudson_planning/static/src/js/fs_planning_board.js',
            'hudson_planning/static/src/xml/fs_planning_board.xml',
            'hudson_planning/static/src/css/fs_planning_schedule.css',
            'hudson_planning/static/src/js/shift_template_badges.js',
            'hudson_planning/static/src/js/shift_conflict_suggestions.js',
            'hudson_planning/static/src/xml/shift_conflict_suggestions.xml',
            'hudson_planning/static/src/js/form_chatter_thread.js',
            'hudson_planning/static/src/views/fs_schedule/fs_schedule_view.js',
            'hudson_planning/static/src/views/fs_schedule/fs_schedule_view.xml',
            'hudson_planning/static/src/views/fs_schedule/fs_schedule_view.scss',
            'hudson_planning/static/src/views/fs_map/fs_map_view.js',
            'hudson_planning/static/src/views/fs_map/fs_map_view.xml',
            'hudson_planning/static/src/views/fs_map/fs_map_view.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
