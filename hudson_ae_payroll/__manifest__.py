# -*- coding: utf-8 -*-
{
    'name': 'Hudson UAE Payroll Localization',
    'version': '19.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'UAE Statutory Payroll Localization and Configuration Foundation',
    'description': """
Hudson UAE Payroll Localization Module
======================================
This module establishes the statutory configuration foundation for UAE Payroll:
- UAE Employer Classification (Sector, Jurisdiction, Emirate, Labour Authority)
- Reusable Jurisdiction & Authority Masters (MOHRE, Free Zones, GPSSA, ADPF, DEWS)
- Employee Statutory Classification (National, GCC, Expatriate, Pension Status, Service Date)
- Pure Python Statutory Profile Resolution Service (Multi-Company Safe)
    """,
    'author': 'Hudson Software Solutions',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'hr_payroll_community',
        'hudson_payroll_core',
        'hudson_payroll_payrun',
        'hudson_attendance_payroll_link',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/uae_pension_authority_data.xml',
        'data/uae_pension_scheme_data.xml',
        'data/uae_emirate_data.xml',
        'data/uae_labour_authority_data.xml',
        'data/uae_payroll_jurisdiction_data.xml',
        'data/hr_salary_rule_category_data.xml',
        'data/hr_salary_rule_data.xml',
        'data/hr_payroll_structure_data.xml',
        'data/uae_rule_parameters.xml',
        'views/uae_master_views.xml',
        'views/res_company_views.xml',
        'views/res_config_settings_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_version_views.xml',
        'views/hr_salary_rule_views.xml',
        'views/hr_rule_parameter_views.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
