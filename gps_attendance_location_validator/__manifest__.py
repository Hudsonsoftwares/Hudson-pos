{
    'name': 'Attendance Location Validator (Multi Work Locations)',
    'version': '20.0.1.0.0',
    'summary': 'Enforce office location check-in/out with GPS radius validation and remote exceptions',
    'description': """
Attendance Location Validator
=============================
Enforce attendance check-in and check-out only from a configured office location
using GPS-based radius validation with the Haversine formula.

Key Features:
- GPS radius validation for check-in and check-out.
- Per-employee remote check-in exception toggle.
- Configurable latitude, longitude, and radius per Work Location.
- Graceful handling of geocoding service failures.
- Toast notifications for validation errors instead of blocking dialogs.
    """,
    'category': 'Human Resources/Attendance',
    'author': 'M. Zohaib',
    'website': 'https://github.com/zobi404/odoo-apps-zohaib',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'hr_attendance',
        'base_geolocalize',
        'web',
    ],
    'data': [
        'views/hr_employee_views.xml',
        'views/hr_work_location_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'gps_attendance_location_validator/static/src/attendance_patches.js',
        ],
        'hr_attendance.assets_public_attendance': [
            'gps_attendance_location_validator/static/src/kiosk_patches.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'images': ['static/description/banner.png'],
}
