import time
from collections import defaultdict

from odoo import api, models, _
from odoo.exceptions import UserError


# the amounts the report sums, as the template asks for them
SUMMED_FIELDS = {
    'debit': lambda values: values['debit'],
    'credit': lambda values: values['credit'],
    'debit - credit': lambda values: values['debit'] - values['credit'],
}


class ReportPartnerLedger(models.AbstractModel):
    _name = 'report.accounting_pdf_reports.report_partnerledger'
    _description = 'Partner Ledger Report'

    def _reconcile_clause(self, data, context):
        """ :return: (sql, params) keeping only the journal items still open at the end date of the
            report when the reconciled entries are not wanted. An item paid after the end date was
            still open at that date: it is kept, whatever its reconciliation status today. """
        if data['form'].get('reconciled', True):
            return "", []
        date_to = context.get('date_to')
        if not date_to:
            return ' AND "account_move_line".full_reconcile_id IS NULL ', []
        return """ AND ("account_move_line".full_reconcile_id IS NULL OR EXISTS (
                    SELECT 1 FROM account_partial_reconcile apr
                    WHERE (apr.debit_move_id = "account_move_line".id OR apr.credit_move_id = "account_move_line".id)
                      AND apr.max_date > %s)) """, [date_to]

    def _get_ledger_data(self, data, partner_ids=None):
        """ Read the journal items of the report with one query for all the partners (and one more for
        the initial balances), instead of several queries for each partner.

        :return: {'lines': {partner_id: [line values]}, 'sums': {partner_id: {'debit', 'credit'}}}
                 the lines of a partner start with its initial balance when the report has a start date
        """
        context = dict(data['form'].get('used_context') or {})
        MoveLine = self.env['account.move.line']
        move_state = tuple(data['computed']['move_state'])
        account_ids = tuple(data['computed']['account_ids'])
        reconcile_clause, reconcile_params = self._reconcile_clause(data, context)
        partner_clause, partner_params = "", []
        if partner_ids is not None:
            partner_clause = ' AND "account_move_line".partner_id IN %s '
            partner_params = [tuple(partner_ids) or (0,)]

        lines = defaultdict(list)
        sums = defaultdict(lambda: {'debit': 0.0, 'credit': 0.0})

        # initial balance: everything before the start date (receivables and payables are balance
        # sheet accounts: their whole history counts)
        if context.get('date_from'):
            init_context = dict(context, date_to=False, initial_bal=True, strict_range=True)
            tables, where_clause, where_params = MoveLine.with_context(init_context)._query_get()
            self.env.cr.execute("""
                SELECT "account_move_line".partner_id, COALESCE(SUM("account_move_line".debit), 0) AS debit,
                       COALESCE(SUM("account_move_line".credit), 0) AS credit
                FROM """ + tables + """, account_move AS m
                WHERE "account_move_line".partner_id IS NOT NULL
                    AND m.id = "account_move_line".move_id
                    AND m.state IN %s
                    AND "account_move_line".account_id IN %s
                    AND """ + where_clause + reconcile_clause + partner_clause + """
                GROUP BY "account_move_line".partner_id""",
                (move_state, account_ids, *where_params, *reconcile_params, *partner_params))
            for row in self.env.cr.dictfetchall():
                if not row['debit'] and not row['credit']:
                    continue
                lines[row['partner_id']].append({
                    'id': 0, 'date': '', 'code': '', 'a_name': '', 'ref': '', 'move_name': '',
                    'name': _('Initial Balance'), 'displayed_name': _('Initial Balance'),
                    'debit': row['debit'], 'credit': row['credit'], 'amount_currency': 0.0,
                    'currency_id': self.env['res.currency'], 'currency_code': '',
                    'progress': row['debit'] - row['credit'], 'is_initial_balance': True,
                })
                sums[row['partner_id']]['debit'] += row['debit']
                sums[row['partner_id']]['credit'] += row['credit']

        lang_code = self.env.context.get('lang') or 'en_US'
        tables, where_clause, where_params = MoveLine.with_context(context)._query_get()
        self.env.cr.execute("""
            SELECT "account_move_line".id, "account_move_line".partner_id, "account_move_line".date, j.code,
                COALESCE(acc.name->>%s, acc.name->>'en_US') as a_name,
                "account_move_line".ref, m.name as move_name, "account_move_line".name,
                "account_move_line".debit, "account_move_line".credit, "account_move_line".amount_currency,
                "account_move_line".currency_id, c.symbol AS currency_code
            FROM """ + tables + """
            LEFT JOIN account_journal j ON ("account_move_line".journal_id = j.id)
            LEFT JOIN account_account acc ON ("account_move_line".account_id = acc.id)
            LEFT JOIN res_currency c ON ("account_move_line".currency_id=c.id)
            LEFT JOIN account_move m ON (m.id="account_move_line".move_id)
            WHERE "account_move_line".partner_id IS NOT NULL
                AND m.state IN %s
                AND "account_move_line".account_id IN %s AND """ + where_clause + reconcile_clause + partner_clause
            + """ ORDER BY "account_move_line".partner_id, "account_move_line".date, "account_move_line".id""",
            (lang_code, move_state, account_ids, *where_params, *reconcile_params, *partner_params))
        currencies = self.env['res.currency']
        for r in self.env.cr.dictfetchall():
            partner_id = r.pop('partner_id')
            # move name, reference and label often repeat each other - the label
            # frequently ends with the move name - so anything a part already says is
            # dropped rather than printed twice
            parts = []
            for field_name in ('move_name', 'ref', 'name'):
                value = (r[field_name] or '').strip()
                if value in ('', '/') or any(value in kept for kept in parts):
                    continue
                parts = [kept for kept in parts if kept not in value]
                parts.append(value)
            r['displayed_name'] = ' - '.join(parts)
            partner_lines = lines[partner_id]
            r['progress'] = (partner_lines[-1]['progress'] if partner_lines else 0.0) + r['debit'] - r['credit']
            r['currency_id'] = currencies.browse(r.get('currency_id'))
            partner_lines.append(r)
            sums[partner_id]['debit'] += r['debit']
            sums[partner_id]['credit'] += r['credit']
        return {'lines': lines, 'sums': sums}

    def _lines(self, data, partner):
        return self._get_ledger_data(data, [partner.id])['lines'].get(partner.id, [])

    def _sum_partner(self, data, partner, field):
        if field not in SUMMED_FIELDS:
            return
        values = self._get_ledger_data(data, [partner.id])['sums'].get(partner.id)
        return SUMMED_FIELDS[field](values) if values else 0.0

    @api.model
    def _get_report_values(self, docids, data=None):
        if not data.get('form'):
            raise UserError(_("Form content is missing, this report cannot be printed."))
        # the entries are read with SQL: write the pending changes first
        self.env.flush_all()
        custom_account_ids = data.get('computed', {}).get('account_ids')
        data['computed'] = {}

        obj_partner = self.env['res.partner']
        data['computed']['move_state'] = ['draft', 'posted']
        if data['form'].get('target_move', 'all') == 'posted':
            data['computed']['move_state'] = ['posted']
        result_selection = data['form'].get('result_selection', 'customer')
        if result_selection == 'supplier':
            data['computed']['ACCOUNT_TYPE'] = ['liability_payable']
        elif result_selection == 'customer':
            data['computed']['ACCOUNT_TYPE'] = ['asset_receivable']
        else:
            data['computed']['ACCOUNT_TYPE'] = ['asset_receivable', 'liability_payable']

        if custom_account_ids:
            data['computed']['account_ids'] = list(custom_account_ids)
        else:
            self.env.cr.execute("""
                SELECT a.id
                FROM account_account a
                WHERE a.account_type IN %s
                AND a.active""", (tuple(data['computed']['ACCOUNT_TYPE']),))
            data['computed']['account_ids'] = [a for (a,) in self.env.cr.fetchall()]
        if not data['computed']['account_ids']:
            data['computed']['account_ids'] = [0]

        form_partner_ids = data['form'].get('partner_ids') or None
        ledger = self._get_ledger_data(data, form_partner_ids)
        currency = self.env.company.currency_id
        if form_partner_ids:
            partner_ids = form_partner_ids
        else:
            # the partners with items in the period, or a balance brought forward
            partner_ids = [
                partner_id for partner_id, partner_lines in ledger['lines'].items()
                if any(not line.get('is_initial_balance') for line in partner_lines)
                or not currency.is_zero(ledger['sums'][partner_id]['debit'] - ledger['sums'][partner_id]['credit'])
            ]
        partners = obj_partner.browse(partner_ids)
        partners = sorted(partners, key=lambda x: (x.ref or '', x.name or ''))

        def lines(_data, partner):
            return ledger['lines'].get(partner.id, [])

        def sum_partner(_data, partner, field):
            if field not in SUMMED_FIELDS:
                return
            values = ledger['sums'].get(partner.id)
            return SUMMED_FIELDS[field](values) if values else 0.0

        return {
            'doc_ids': partner_ids,
            'doc_model': self.env['res.partner'],
            'data': data,
            'docs': partners,
            'time': time,
            'lines': lines,
            'sum_partner': sum_partner,
        }
