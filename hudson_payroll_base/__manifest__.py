# -*- coding: utf-8 -*-
{
    'name': 'Hudson Payroll Base',
    'version': '20.0.1.0.1',
    'category': 'Human Resources/Payroll',
    'sequence': 95,
    'summary': 'Clean, Modern, and High-Performance Base Payroll Engine with Pay Runs & Payment Advice for Odoo 20',
    'description': """
Hudson Payroll Base
===================
A modern, modular, and high-performance base payroll engine designed from scratch for Odoo 20.

Key Features:
-------------
* Re-engineered Salary Rule Computation Engine with safe sandboxing and circular reference prevention.
* Modern Salary Structures, Structure Types, and smart code-override inheritance.
* Department & Employee-Type scoped Pay Runs with interactive Kanban board.
* Bank Payment Advice with direct CSV export and PDF statements.
* Built-in Dynamic Rule Parameters for date-versioned statutory configurations.
* 100% compatible hooks for multi-country localizations (India, UAE) and biometric attendance.
    """,
    'author': 'Hudson Software Solutions',
    'website': 'https://hudsonsoftwares.com',
    'license': 'LGPL-3',
    'depends': [
        'hr',
        'hr_holidays',
        'hr_work_entry',
    ],
    'data': [
        'security/hr_payroll_security.xml',
        'security/ir.access.csv',
        'data/hr_payroll_sequence.xml',
        'data/hr_salary_rule_category_data.xml',
        'data/hr_salary_rule_data.xml',
        'data/hr_employee_type_data.xml',
        'data/hr_payroll_dashboard_warning_data.xml',
        'data/hr_payment_advice_sequence.xml',
        'data/hr_payslip_input_type_data.xml',
        'data/hds_payment_mode_data.xml',
        'reports/payment_advice_report.xml',
        'reports/hr_payslip_report.xml',
        'reports/hr_salary_certificate_report.xml',
        'data/mail_template_data.xml',
        'data/mail_template_expiry_data.xml',
        'data/ir_cron_data.xml',
        'wizard/hr_payslip_employees_views.xml',
        'wizard/pay_run_pay_wizard_views.xml',
        'wizard/hr_payslip_run_duplicate_wizard_views.xml',
        'views/payrun_wizard_views.xml',
        'views/hr_salary_rule_category_views.xml',
        'views/hr_payroll_structure_views.xml',
        'views/hr_salary_rule_views.xml',
        'views/hr_rule_parameter_views.xml',
        'views/hr_employee_type_views.xml',
        'views/payment_advice_views.xml',
        'views/hr_payroll_reporting_views.xml',
        'views/hr_payroll_headcount_views.xml',
        'views/hr_payslip_views.xml',
        'views/hr_payslip_run_views.xml',
        'views/hr_contract_views.xml',
        'views/hr_payroll_configuration_views.xml',
        'views/res_config_settings_views.xml',
        'views/hr_payroll_benefit_views.xml',
        'wizard/hr_salary_adjustment_wizard_views.xml',
        'views/hr_salary_adjustment_views.xml',
        'views/res_partner_bank_views.xml',
        'views/hr_payroll_menu_views.xml',
        'views/hds_payment_mode_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hudson_payroll_base/static/src/scss/payroll_settings.scss',
            'hudson_payroll_base/static/src/scss/payroll_dashboard.scss',
            'hudson_payroll_base/static/src/js/payroll_dashboard_navigation.js',
            'hudson_payroll_base/static/src/js/number_comma_parser.js',
            'hudson_payroll_base/static/src/js/display_notification_delay.js',
            'hudson_payroll_base/static/src/js/payslip_generation_loader.js',
            'hudson_payroll_base/static/src/js/payrun_list_view.js',
            'hudson_payroll_base/static/src/js/employee_selection_table.js',
            'hudson_payroll_base/static/src/xml/employee_selection_table.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'pre_init_hook': 'pre_init_hook',
    'post_init_hook': 'post_init_hook',
}
