# -*- coding: utf-8 -*-
{
    'name': 'Hudson Payroll Accounting',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Link Hudson Payroll computations to Odoo 19 Financial Accounting Journal Entries',
    'description': """
Hudson Payroll Accounting
=========================
Seamlessly links Hudson Payroll Base with Odoo 19 Financial Accounting:
- Map Debit and Credit accounts on Salary Rules
- Automatically generate draft Journal Entries (account.move) upon payslip validation
- Automatically clean up / cancel journal entries when payslips are cancelled
- Smart buttons on Payslip and Pay Run batches to view linked Accounting Entries
- Support for Analytic Account distribution and Taxes on salary rules
    """,
    'author': 'Hudson',
    'depends': ['hudson_payroll_base', 'account', 'analytic'],
    'data': [
        'views/hr_salary_rule_views.xml',
        'views/hr_contract_views.xml',
        'views/hr_payslip_views.xml',
        'views/hr_payslip_run_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
