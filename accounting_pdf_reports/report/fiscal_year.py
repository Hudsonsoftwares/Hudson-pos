""" Helpers shared by the reports to split the profit and loss by fiscal year.

The income and expense accounts are never closed in Odoo: as in Odoo Enterprise, the reports
start them again at the beginning of each fiscal year, and what they hold from the previous
fiscal years is reported on the "Current Year Earnings" (equity_unaffected) account, so that
the balances still add up to zero.
"""
from datetime import timedelta

from odoo import fields

UNAFFECTED_EARNINGS_TYPE = 'equity_unaffected'


def profit_and_loss_types(env):
    """ :return: tuple of the account types of the income and expense accounts """
    values = env['account.account']._fields['account_type'].get_values(env)
    return tuple(value for value in values if value.startswith(('income', 'expense')))


def reset_account_types(env):
    """ :return: tuple of the account types restarted at the beginning of each fiscal year """
    return profit_and_loss_types(env) + (UNAFFECTED_EARNINGS_TYPE,)


def report_company(env, company_id=None):
    company = env['res.company'].browse(company_id) if company_id else env['res.company']
    return company.exists() or env.company


def fiscal_year_start(company, date=None):
    """ :return: the first day of the fiscal year of `company` holding `date` (today by default) """
    date = fields.Date.to_date(date) or fields.Date.context_today(company)
    return company.compute_fiscalyear_dates(date)['date_from']


def day_before(date):
    return fields.Date.to_date(date) - timedelta(days=1)


def unaffected_earnings_account(company, accounts):
    """ :return: the account among `accounts` that receives the earnings of the previous fiscal
                 years: the "Current Year Earnings" account of `company`, else the first one """
    candidates = accounts.filtered(lambda account: account.account_type == UNAFFECTED_EARNINGS_TYPE)
    if not candidates:
        return candidates
    own = candidates.filtered(lambda account: company in account.company_ids)
    return (own or candidates)[:1]
