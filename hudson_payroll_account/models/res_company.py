# -*- coding: utf-8 -*-
from odoo import fields, models

# Payroll accounts of a company: key -> (default code, name, account type, reconcilable).
# The codes are only used when the account is created; the accounts themselves are chosen
# per company in Payroll Settings > Payroll Accounts.
PAYROLL_ACCOUNTS = {
    'salary_expense': ('210100', 'Salary Expense', 'expense', False),
    'employer_expense': ('210110', 'Employer Statutory Contribution Expense', 'expense', False),
    'pf_employee': ('300007', 'Provident Fund - Employee Payable', 'liability_current', False),
    'pf_employer': ('300008', 'Provident Fund - Employer Payable', 'liability_current', False),
    'pf_admin': ('300009', 'EPF Admin & EDLI Payable', 'liability_current', False),
    'net_payable': ('300010', 'Salary Payable', 'liability_current', True),
    'tds': ('300011', 'TDS on Salary Payable', 'liability_current', False),
    'pt': ('300012', 'Professional Tax Payable', 'liability_current', False),
    'esic_employee': ('300014', 'ESIC - Employee Payable', 'liability_current', False),
    'esic_employer': ('300015', 'ESIC - Employer Payable', 'liability_current', False),
    'lwf_employee': ('300016', 'LWF - Employee Payable', 'liability_current', False),
    'lwf_employer': ('300017', 'LWF - Employer Payable', 'liability_current', False),
    'other_deductions': ('300018', 'Other Salary Deductions Payable', 'liability_current', False),
}


# Accounts of the chart of accounts used by default (first found), by payroll account key: the
# Indian chart (l10n_in) has the payroll accounts used by Odoo's Indian payroll
CHART_ACCOUNTS = {
    'salary_expense': ['p2101'],
    'employer_expense': ['p2101'],
    'net_payable': ['p300010'],
    'tds': ['p300019', 'p11231'],
    'pf_employee': ['p300007'],
    'pf_employer': ['p300008'],
    'pf_admin': ['p300008'],
    'esic_employee': ['p300014'],
    'esic_employer': ['p300015'],
    'pt': ['p300012'],
    'lwf_employee': ['p300016'],
    'lwf_employer': ['p300017'],
}


def _account_field(key):
    return f'hds_payroll_account_{key}_id'


class ResCompany(models.Model):
    _inherit = 'res.company'

    hds_payroll_account_salary_expense_id = fields.Many2one('account.account', string='Salary Expense')
    hds_payroll_account_employer_expense_id = fields.Many2one('account.account', string='Employer Contribution Expense')
    hds_payroll_account_pf_employee_id = fields.Many2one('account.account', string='PF - Employee Payable')
    hds_payroll_account_pf_employer_id = fields.Many2one('account.account', string='PF - Employer Payable')
    hds_payroll_account_pf_admin_id = fields.Many2one('account.account', string='EPF Admin & EDLI Payable')
    hds_payroll_account_net_payable_id = fields.Many2one('account.account', string='Salary Payable (Net)')
    hds_payroll_account_tds_id = fields.Many2one('account.account', string='TDS Payable')
    hds_payroll_account_pt_id = fields.Many2one('account.account', string='Professional Tax Payable')
    hds_payroll_account_esic_employee_id = fields.Many2one('account.account', string='ESIC - Employee Payable')
    hds_payroll_account_esic_employer_id = fields.Many2one('account.account', string='ESIC - Employer Payable')
    hds_payroll_account_lwf_employee_id = fields.Many2one('account.account', string='LWF - Employee Payable')
    hds_payroll_account_lwf_employer_id = fields.Many2one('account.account', string='LWF - Employer Payable')
    hds_payroll_account_other_deductions_id = fields.Many2one('account.account', string='Other Deductions Payable')

    def _hds_has_chart_of_accounts(self):
        """Accounting is set up for the company (a chart of accounts is installed)."""
        self.ensure_one()
        return bool(self.chart_template) or bool(self.env['account.account'].sudo().search_count(
            [('company_ids', 'in', self.ids)], limit=1))

    def _hds_assign_default_payroll_accounts(self):
        """Fill the empty payroll accounts with the matching accounts of the company's chart of
        accounts (accounts already chosen are kept)."""
        for company in self.sudo():
            values = {}
            for key, xmlids in CHART_ACCOUNTS.items():
                if company[_account_field(key)]:
                    continue
                for xmlid in xmlids:
                    account = self.env.ref(f'account.{company.id}_{xmlid}', raise_if_not_found=False)
                    if account and account._name == 'account.account' and company in account.company_ids:
                        values[_account_field(key)] = account.id
                        break
            if values:
                company.write(values)

    def _hds_get_payroll_accounts(self):
        """The company's payroll accounts by key; missing ones are created with their default code
        and name (the next free code is used when the default one belongs to another account)."""
        self.ensure_one()
        self._hds_assign_default_payroll_accounts()
        Account = self.env['account.account'].sudo().with_company(self)
        company = self.sudo()
        accounts = {}
        for key, (code, name, account_type, reconcile) in PAYROLL_ACCOUNTS.items():
            account = company[_account_field(key)]
            if not account or self not in account.company_ids:
                existing = Account.search([('company_ids', 'in', self.ids), ('code', '=', code)], limit=1)
                if existing and existing.name.strip().lower() == name.lower():
                    account = existing
                else:
                    free_code = code
                    while Account.search_count([('company_ids', 'in', self.ids), ('code', '=', free_code)], limit=1):
                        free_code = str(int(free_code) + 1)
                    account = Account.create({
                        'code': free_code,
                        'name': name,
                        'account_type': account_type,
                        'reconcile': reconcile,
                        'company_ids': [(6, 0, self.ids)],
                    })
                company[_account_field(key)] = account
            accounts[key] = account
        return accounts
