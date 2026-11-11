# -*- coding: utf-8 -*-
{
    'name': 'Hudson Attendance and Payroll Connection',
    'version': '20.0.1.0.2',

    'category': 'Human Resources',
    'summary': 'Connects biometric attendance, contract rates, leave deductions, and auto-regularization with payroll.',
    'description': """
This module connects biometric attendance anomalies, contract rates, unpaid leaves, and regularizations with payroll.
    """,
    'author': 'Hudson Softwares',
    'depends': [
        'hudson_payroll_base',
        'hr_attendance',
        'hr_holidays',
        'hudson_biometric_attendance',
        'mail',
        'calendar',
    
    ],
    'data': [
        'views/hr_version_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_payslip_views.xml',
        'views/resource_calendar_leaves_views.xml',
        'views/ir_cron_data.xml',
        'data/hr_salary_rule_data.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
