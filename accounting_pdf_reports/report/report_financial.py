import time
from odoo import api, models, _
from odoo.exceptions import UserError

from .fiscal_year import (
    day_before, fiscal_year_start, profit_and_loss_types, report_company,
    reset_account_types, unaffected_earnings_account,
)


class ReportFinancial(models.AbstractModel):
    _name = 'report.accounting_pdf_reports.report_financial'
    _description = 'Financial Reports'

    def _compute_account_balance(self, accounts):
        """ compute the balance, debit and credit for the provided accounts
        """
        mapping = {
            'balance': "COALESCE(SUM(debit),0) - COALESCE(SUM(credit), 0) as balance",
            'debit': "COALESCE(SUM(debit), 0) as debit",
            'credit': "COALESCE(SUM(credit), 0) as credit",
        }

        res = {}
        for account in accounts:
            res[account.id] = dict.fromkeys(mapping, 0.0)
        if accounts:
            # the query below reads the journal items from the database
            self.env['account.move.line'].flush_model()
            tables, where_clause, where_params = self.env['account.move.line']._query_get()
            tables = tables.replace('"', '') if tables else "account_move_line"
            wheres = [""]
            if where_clause.strip():
                wheres.append(where_clause.strip())
            filters = " AND ".join(wheres)
            request = "SELECT account_id as id, " + ', '.join(mapping.values()) + \
                       " FROM " + tables + \
                       " WHERE account_id IN %s " \
                            + filters + \
                       " GROUP BY account_id"
            params = (tuple(accounts._ids),) + tuple(where_params)
            self.env.cr.execute(request, params)
            for row in self.env.cr.dictfetchall():
                res[row['id']] = row
            self._add_previous_years_earnings(accounts, res)
        return res

    def _add_previous_years_earnings(self, accounts, res):
        """ On a balance sheet, the income and expense accounts only hold the current fiscal year:
        what they and the "Current Year Earnings" account hold from the previous fiscal years is
        reported on the "Current Year Earnings" account, as in Odoo Enterprise (unallocated
        earnings of the previous years). Otherwise the balance sheet would not balance. """
        until = self.env.context.get('previous_years_earnings_until')
        if not until:
            return
        company = report_company(self.env, self.env.context.get('company_id'))
        target = unaffected_earnings_account(company, accounts)
        if not target:
            return
        context = dict(self.env.context, date_from=False, date_to=day_before(until), strict_range=False,
                       initial_bal=False, account_ids=False)
        tables, where_clause, where_params = self.env['account.move.line'].with_context(context)._query_get(
            [('account_id.account_type', 'in', reset_account_types(self.env))])
        tables = tables.replace('"', '') if tables else "account_move_line"
        self.env.cr.execute(
            "SELECT COALESCE(SUM(debit), 0) - COALESCE(SUM(credit), 0) FROM " + tables
            + " WHERE " + (where_clause.strip() or "TRUE"), tuple(where_params))
        previous = self.env.cr.fetchone()[0] or 0.0
        if not previous:
            return
        values = res.setdefault(target.id, {'balance': 0.0, 'debit': 0.0, 'credit': 0.0})
        values['balance'] = (values.get('balance') or 0.0) + previous
        if previous > 0:
            values['debit'] = (values.get('debit') or 0.0) + previous
        else:
            values['credit'] = (values.get('credit') or 0.0) - previous

    @api.model
    def _is_balance_sheet(self, account_report):
        """ A report is a balance sheet when it reports balance sheet accounts: their balances are
        as of the end date, whatever the start date. A profit and loss only has income and expense
        accounts, whose amounts are the ones of a period. """
        reports = account_report._get_children_by_order()
        account_types = set(reports.filtered(lambda r: r.type == 'account_type').account_type_ids.mapped('type'))
        account_types |= set(reports.filtered(lambda r: r.type == 'accounts').account_ids.mapped('account_type'))
        not_balance_sheet = set(profit_and_loss_types(self.env)) | {'off_balance'}
        return bool(account_types - not_balance_sheet)

    @api.model
    def _get_report_context(self, context, is_balance_sheet):
        """ :return: the context to compute the report with, like Odoo Enterprise:
            - a balance sheet is as of its end date: the balance sheet accounts are cumulated since
              the beginning, the profit of the current fiscal year is the one since its first day,
              the earnings of the previous fiscal years go to the "Current Year Earnings" account;
            - a profit and loss without a start date starts at the beginning of the fiscal year.
        """
        context = dict(context or {})
        company = report_company(self.env, context.get('company_id'))
        fy_start = fiscal_year_start(company, context.get('date_to'))
        if is_balance_sheet:
            context.update(date_from=fy_start, strict_range=False, initial_bal=False,
                           previous_years_earnings_until=fy_start)
        elif not context.get('date_from'):
            context.update(date_from=fy_start, strict_range=True)
        return context

    def _compute_report_balance(self, reports):
        '''returns a dictionary with key=the ID of a record and value=the credit, debit and balance amount
           computed for this record. If the record is of type :
               'accounts' : it's the sum of the linked accounts
               'account_type' : it's the sum of leaf accoutns with such an account_type
               'account_report' : it's the amount of the related report
               'sum' : it's the sum of the children of this record (aka a 'view' record)'''
        res = {}
        fields = ['credit', 'debit', 'balance']
        for report in reports:
            if report.id in res:
                continue
            res[report.id] = dict((fn, 0.0) for fn in fields)
            if report.type == 'accounts':
                # it's the sum of the linked accounts
                res[report.id]['account'] = self._compute_account_balance(report.account_ids)
                for value in res[report.id]['account'].values():
                    for field in fields:
                        res[report.id][field] += value.get(field)
            elif report.type == 'account_type':
                # it's the sum the leaf accounts with such an account type
                accounts = self.env['account.account'].search(
                    [('account_type', 'in', report.account_type_ids.mapped('type'))])

                res[report.id]['account'] = self._compute_account_balance(accounts)
                for value in res[report.id]['account'].values():
                    for field in fields:
                        res[report.id][field] += value.get(field)
            elif report.type == 'account_report' and report.account_report_id:
                # it's the amount of the linked report
                res2 = self._compute_report_balance(report.account_report_id)
                for key, value in res2.items():
                    for field in fields:
                        res[report.id][field] += value[field]
            elif report.type == 'sum':
                # it's the sum of the children of this account.report
                res2 = self._compute_report_balance(report.children_ids)
                for key, value in res2.items():
                    for field in fields:
                        res[report.id][field] += value[field]
        return res

    def get_account_lines(self, data):
        lines = []
        account_report = self.env['account.financial.report'].search(
            [('id', '=', data['account_report_id'][0])])
        child_reports = account_report._get_children_by_order()
        res = self.with_context(data.get('used_context'))._compute_report_balance(child_reports)
        if data['enable_filter']:
            comparison_res = self.with_context(
                data.get('comparison_context'))._compute_report_balance(
                child_reports)
            for report_id, value in comparison_res.items():
                res[report_id]['comp_bal'] = value['balance']
                report_acc = res[report_id].get('account')
                if report_acc:
                    for account_id, val in comparison_res[report_id].get('account').items():
                        report_acc[account_id]['comp_bal'] = val['balance']
        for report in child_reports:
            vals = {
                'name': report.name,
                'balance': res[report.id]['balance'] * float(report.sign),
                'type': 'report',
                # the style is a selection of strings: '0' is the automatic formatting, i.e. the level in the tree
                'level': int(report.style_overwrite or 0) or report.level,
                'account_type': report.type or False, #used to underline the financial report balances
            }
            if data['debit_credit']:
                vals['debit'] = res[report.id]['debit']
                vals['credit'] = res[report.id]['credit']

            if data['enable_filter']:
                vals['balance_cmp'] = res[report.id]['comp_bal'] * float(report.sign)

            lines.append(vals)
            if report.display_detail == 'no_detail':
                #the rest of the loop is used to display the details of the financial report, so it's not needed here.
                continue
            if res[report.id].get('account'):
                sub_lines = []
                for account_id, value in res[report.id]['account'].items():
                    #if there are accounts to display, we add them to the lines with a level equals to their level in
                    #the COA + 1 (to avoid having them with a too low level that would conflicts with the level of data
                    #financial reports for Assets, liabilities...)
                    flag = False
                    account = self.env['account.account'].browse(account_id)
                    vals = {
                        'account_id': account.id,
                        'account_code': account.code,
                        'name': ' '.join(part for part in (account.code, account.name) if part),
                        'balance': value['balance'] * float(report.sign) or 0.0,
                        'type': 'account',
                        # must never be False: the template skips rows whose level is 0/False
                        'level': 4 if report.display_detail == 'detail_with_hierarchy' else report.level + 1,
                        'account_type': account.account_type,
                    }
                    if data['debit_credit']:
                        vals['debit'] = value['debit']
                        vals['credit'] = value['credit']
                        if (not self.env.company.currency_id.is_zero(vals['debit'])
                                or not self.env.company.currency_id.is_zero(vals['credit'])):
                            flag = True
                    if not self.env.company.currency_id.is_zero(vals['balance']):
                        flag = True
                    if data['enable_filter']:
                        vals['balance_cmp'] = value['comp_bal'] * float(report.sign)
                        if not self.env.company.currency_id.is_zero(vals['balance_cmp']):
                            flag = True
                    if flag:
                        sub_lines.append(vals)
                lines += sorted(sub_lines, key=lambda sub_line: sub_line['name'])
        return lines

    @api.model
    def _get_report_values(self, docids, data=None):
        if (not data.get('form') or not self.env.context.get('active_model')
                or self.env.context.get('active_id') is None):
            raise UserError(_("Form content is missing, this report cannot be printed."))

        model = self.env.context.get('active_model')
        docs = self.env[model].browse(self.env.context.get('active_id'))
        form = dict(data['form'])
        account_report = self.env['account.financial.report'].browse(form['account_report_id'][0])
        is_balance_sheet = self._is_balance_sheet(account_report)
        form['used_context'] = self._get_report_context(form.get('used_context'), is_balance_sheet)
        if form.get('enable_filter'):
            form['comparison_context'] = self._get_report_context(form.get('comparison_context'), is_balance_sheet)
        report_lines = self.get_account_lines(form)
        return {
            'is_balance_sheet': is_balance_sheet,
            'doc_ids': self.ids,
            'doc_model': model,
            'data': data['form'],
            'docs': docs,
            'time': time,
            'get_account_lines': report_lines,
        }
