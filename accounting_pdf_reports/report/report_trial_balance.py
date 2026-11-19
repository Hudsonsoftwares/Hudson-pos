import time
from odoo import api, models, _
from odoo.exceptions import UserError

from .fiscal_year import (
    day_before, fiscal_year_start, report_company, reset_account_types, unaffected_earnings_account,
)


class ReportTrialBalance(models.AbstractModel):
    _name = 'report.accounting_pdf_reports.report_trialbalance'
    _description = 'Trial Balance Report'

    def _sum_by_account(self, accounts, context, domain=None):
        """ :return: {account_id: {'debit', 'credit', 'balance'}} of the journal items selected by
                     `context` (see account.move.line._query_get) and `domain` """
        tables, where_clause, where_params = self.env['account.move.line'].with_context(context)._query_get(
            list(domain or []))
        tables = tables.replace('"', '') or 'account_move_line'
        filters = (" AND " + where_clause.strip()) if where_clause.strip() else ""
        self.env.cr.execute(
            "SELECT account_id AS id, SUM(debit) AS debit, SUM(credit) AS credit, "
            "(SUM(debit) - SUM(credit)) AS balance FROM " + tables + " WHERE account_id IN %s" + filters
            + " GROUP BY account_id", (tuple(accounts.ids),) + tuple(where_params))
        return {row.pop('id'): row for row in self.env.cr.dictfetchall()}

    def _get_initial_balances(self, accounts, context, date_from):
        """ :return: {account_id: initial balance} before `date_from`, as in Odoo Enterprise: the balance
            sheet accounts carry their whole history, the income and expense accounts only the current
            fiscal year, and what they held in the previous fiscal years is carried by the
            "Current Year Earnings" account (undistributed profits/losses). """
        company = report_company(self.env, context.get('company_id'))
        fy_start = fiscal_year_start(company, date_from)
        reset_types = reset_account_types(self.env)
        before = dict(context, date_from=date_from, date_to=False, strict_range=True, initial_bal=True)
        initial = {
            account_id: values['balance']
            for account_id, values in self._sum_by_account(
                accounts, before,
                ['|', ('account_id.account_type', 'not in', reset_types), ('date', '>=', fy_start)],
            ).items()
        }
        target = unaffected_earnings_account(company, accounts)
        if target:
            previous_years = dict(context, date_from=False, date_to=day_before(fy_start), strict_range=False,
                                  initial_bal=False)
            reset_accounts = self.env['account.account'].with_context(active_test=False).search(
                [('account_type', 'in', reset_types)])
            if reset_accounts:
                previous = sum(values['balance'] for values in self._sum_by_account(
                    reset_accounts, previous_years).values())
                initial[target.id] = initial.get(target.id, 0.0) + previous
        return initial

    def _get_accounts(self, accounts, display_account):
        """ compute the balance, debit and credit for the provided accounts
            :Arguments:
                `accounts`: list of accounts record,
                `display_account`: it's used to display either all accounts or those accounts which balance is > 0
            :Returns a list of dictionary of Accounts with following key and value
                `name`: Account name,
                `code`: Account code,
                `initial_balance`: balance before the period,
                `credit`: total amount of credit of the period,
                `debit`: total amount of debit of the period,
                `balance`: end balance (initial balance + debit - credit),
        """
        context = dict(self.env.context)
        company = report_company(self.env, context.get('company_id'))
        # A trial balance is the movements of a period between the balances it starts and ends with.
        # Without a start date the period is the current fiscal year, as in Odoo Enterprise.
        date_from = context.get('date_from') or fiscal_year_start(company, context.get('date_to'))
        period_context = dict(context, date_from=date_from, strict_range=True, initial_bal=False)
        account_result = self._sum_by_account(accounts, period_context)
        initial_balances = self._get_initial_balances(accounts, context, date_from)

        account_res = []
        for account in accounts:
            res = dict((fn, 0.0) for fn in ['initial_balance', 'credit', 'debit', 'balance'])
            currency = account.currency_id and account.currency_id or self.env.company.currency_id
            res['code'] = account.code
            res['name'] = account.name
            res['initial_balance'] = initial_balances.get(account.id) or 0.0
            if account.id in account_result:
                res['debit'] = account_result[account.id].get('debit') or 0.0
                res['credit'] = account_result[account.id].get('credit') or 0.0
            res['balance'] = res['initial_balance'] + res['debit'] - res['credit']
            if display_account == 'all':
                account_res.append(res)
            if display_account == 'not_zero' and not currency.is_zero(res['balance']):
                account_res.append(res)
            if display_account == 'movement' and (
                    not currency.is_zero(res['debit']) or not currency.is_zero(res['credit'])
                    or not currency.is_zero(res['initial_balance'])):
                account_res.append(res)
        return account_res

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form') or not self.env.context.get('active_model'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        # the entries are read with SQL: write the pending changes first
        self.env.flush_all()

        model = self.env.context.get('active_model')
        docs = self.env[model].browse(self.env.context.get('active_ids', []))
        display_account = data['form'].get('display_account')
        accounts = docs if model == 'account.account' else self.env['account.account'].search([])
        context = dict(data['form'].get('used_context') or {})
        analytic_accounts = []
        if data['form'].get('analytic_account_ids'):
            analytic_account_ids = self.env['account.analytic.account'].browse(data['form'].get('analytic_account_ids'))
            context['analytic_account_ids'] = analytic_account_ids
            analytic_accounts = [account.name for account in analytic_account_ids]
        account_res = self.with_context(context)._get_accounts(accounts, display_account)
        codes = []
        if data['form'].get('journal_ids', False):
            codes = [journal.code for journal in
                     self.env['account.journal'].search(
                         [('id', 'in', data['form']['journal_ids'])])]
        return {
            'doc_ids': self.ids,
            'doc_model': model,
            'data': data['form'],
            'docs': docs,
            'print_journal': codes,
            'analytic_accounts': analytic_accounts,
            'time': time,
            'Accounts': account_res,
        }
