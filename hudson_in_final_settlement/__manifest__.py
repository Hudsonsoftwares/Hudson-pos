# -*- coding: utf-8 -*-
{
    'name': 'Hudson Indian Final Settlement',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'India Statutory Final Settlement (Gratuity Act 1972, Leave Encashment, Notice Pay) for Hudson HRMS',
    'author': 'Hudson Software Solutions',
    'depends': [
        'hr',
        'hudson_exit_management',
        'hudson_payroll_base',
        'hudson_in_payroll',
    ],
    'data': [
        'security/ir.access.csv',
        'data/hr_departure_reason_data.xml',
        'data/final_settlement_sequence.xml',
        'reports/final_settlement_report.xml',
        'views/final_settlement_views.xml',
        'views/hr_resignation_views.xml',
        'views/hr_employee_views.xml',
        'views/payroll_dashboard_views.xml',
    ],
    'installable': True,
    # Installed with the Indian payroll
    'countries': ['in'],
    'auto_install': ['hudson_in_payroll'],
    'application': False,
    'license': 'LGPL-3',
}
