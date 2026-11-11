# -*- coding: utf-8 -*-
{
    'name': 'Payroll Documents',
    'version': '20.0.1.0.0',
    'category': 'Human Resources/Payroll',
    'summary': 'Store validated payslip PDFs in the employee folders of Documents',
    'description': """
Bridge between Payroll and Documents (DMS).

When a payslip is validated, its PDF (the same one as Print and Send by Email) is stored in the
employee's Documents folder, under Payroll / <tax year>, e.g.
Employees / Arun Kumar / Payroll / 2026-27 / Arun Kumar - October 2026.pdf.

* The PDF is generated in the background, so validating a pay run stays fast.
* Validating again replaces the file; resetting to draft or cancelling the payslip moves it to the Trash.
* Employees see their own payslips through their personal folder access (view / download).
* Payroll Settings: switch per company, and a button to store the payslips validated before.
""",
    'author': 'Hudson Software Solutions',
    'depends': [
        'hudson_payroll_base',
        'dms_enterprise_features',
    ],
    'data': [
        'data/ir_cron_data.xml',
        'views/hr_payslip_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
