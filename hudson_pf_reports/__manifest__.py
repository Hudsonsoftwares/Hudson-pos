# -*- coding: utf-8 -*-
{
    'name': 'Hudson Indian Payroll — Statutory PF Reporting Suite',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Complete EPFO PF statutory reporting, ECR export (.txt/.xlsx), register, ledgers, and audit tools for Hudson HRMS',
    'description': """
Hudson Indian Payroll — Statutory PF Reporting Suite
=====================================================
Comprehensive EPFO Indian Provident Fund reporting suite for Hudson HRMS:
- EPFO ECR Text & Excel Exporter with UAN validation
- PF Register (PDF & XLSX)
- Monthly PF Summary
- Employee / Employer PF Contribution Reports
- Employee PF Ledger
- Contribution Basis & Wage Ceiling Exception Reports
- PF Variance Report with heuristic analysis
- New Joiners & Resigned Employees PF Reports
- HR Snapshot PF Report
- PF Accounting Reconciliation Report
- Salary Revision Impact Report
- UAN Register
    """,
    'author': 'Hudson Softwares',
    'website': 'https://www.hudsonsoftwares.com',
    'depends': [
        'hr',
        'hudson_payroll_base',
        'hudson_in_payroll',
    ],
    'data': [
        'security/hds_pf_reports_security.xml',
        'security/ir.access.csv',
        'report/hds_pf_report_actions.xml',
        'report/pf_report_templates.xml',
        'views/hds_pf_ecr_wizard_views.xml',
        'views/hds_pf_register_wizard_views.xml',
        'views/hds_pf_reports_views.xml',
        'views/hds_statutory_report_tile_views.xml',
        'data/hds_statutory_report_tiles.xml',
        'views/pf_report_menu_views.xml',
    ],
    'installable': True,
    # Installed with the Indian payroll
    'countries': ['in'],
    'auto_install': ['hudson_in_payroll'],
    'application': False,
    'license': 'LGPL-3',
}
