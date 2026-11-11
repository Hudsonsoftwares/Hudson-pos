{
    'name': 'Payroll Spreadsheet Dashboard',
    'version': '20.0.1.0.0',
    'category': 'Productivity/Dashboard',
    'summary': 'Payroll dashboard in Odoo Dashboards (spreadsheet) with a payroll analysis report',
    'description': """
Payroll dashboard for the standard Odoo Dashboards app (spreadsheet dashboards):
key figures with previous-period comparison, payroll cost trend, top wage earners,
department costs, statutory deductions, TDS by tax regime, and the final settlements and
leave encashment requests of the period.

Data comes from the Payroll Analysis report (one row per validated / paid payslip).
""",
    'author': 'Hudson Softwares',
    'license': 'LGPL-3',
    'depends': [
        'spreadsheet_dashboard',
        'hudson_in_payroll',
        'hudson_in_final_settlement',
    ],
    'data': [
        'security/ir.access.csv',
        'views/hds_payroll_analysis_views.xml',
        'data/dashboards.xml',
    ],
    # Installed with the Indian payroll (and its final settlement), with Odoo Dashboards
    'countries': ['in'],
    'auto_install': ['hudson_in_payroll', 'hudson_in_final_settlement'],
    'installable': True,
}
