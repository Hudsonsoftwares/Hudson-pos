# -*- coding: utf-8 -*-
{
    'name': 'Hudson Exit & Resignation Management',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Exit Management',
    'summary': 'Country-Independent Employee Resignation, Notice Period, Department Clearances & Offboarding Lifecycle',
    'description': """
Hudson Exit & Resignation Management (Core)
===========================================
A clean, country-agnostic exit and offboarding framework for Odoo 19:
- Resignation requests submitted by employees or HR managers
- Resignation types: Resignation, Termination, Retirement, End of Contract, Mutual Agreement
- Automated notice period calculation and notice shortage tracking via hr.version contract
- Multi-tier approval workflow: Draft -> Submitted -> Approved -> Done / Cancelled
- Department Clearance checklist (IT, Finance, Admin, HR) with asset/dues tracking
- Pluggable statutory settlement hook for country modules (e.g. India Gratuity/Encashment, UAE EOSB)
- Full chatter, activities, and audit trail
    """,
    'author': 'Hudson Software Solutions',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'hr',
        'mail',
    ],
    'data': [
        'security/ir.access.csv',
        'data/resignation_sequence.xml',
        'views/hr_resignation_views.xml',
        'views/hudson_exit_clearance_views.xml',
        'views/hr_employee_departure_views.xml',
        'views/exit_menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
