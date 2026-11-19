from datetime import date, timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from odoo.addons.accounting_pdf_reports.report.report_cash_flow import CASH_ACCOUNT_TYPES


class AccountCashFlowWizard(models.TransientModel):
    """
    Cash Flow Statement wizard using the Indirect Method.

    Indirect Method structure:
    A. Operating Activities
       1. Net Profit for the period (from P&L accounts)
       2. Add back: Depreciation & Amortisation (non-cash expense)
       3. Changes in Working Capital:
          - (Increase)/Decrease in Trade Receivables
          - (Increase)/Decrease in Inventories & Prepayments
          - (Increase)/Decrease in Other Current Assets
          - Increase/(Decrease) in Trade Payables
          - Increase/(Decrease) in Other Current Liabilities
    B. Investing Activities
       - Net purchase of Fixed Assets (increase in fixed asset accounts)
       - Net proceeds from asset disposals
    C. Financing Activities
       - Net proceeds from long-term borrowings
       - Changes in equity (capital injections / dividends)
    D. Net Change in Cash = A + B + C
    E. Opening Cash Balance
    F. Closing Cash Balance = D + E
    """
    _name = 'account.cash.flow.wizard'
    _description = 'Cash Flow Statement (Indirect Method)'

    date_from = fields.Date(
        string='Date From',
        required=True,
        default=lambda self: date.today().replace(day=1, month=1),
    )
    date_to = fields.Date(
        string='Date To',
        required=True,
        default=lambda self: date.today(),
    )
    target_move = fields.Selection(
        [('posted', 'All Posted Entries'), ('all', 'All Entries')],
        string='Target Moves',
        required=True,
        default='posted',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    def _report_company_ids(self):
        """The companies the report covers: the ones selected in the company
        switcher, which always include the wizard's company (checked above)."""
        return (self.env.companies | self.company_id).ids

    def _get_journal_clause(self):
        """Restrict to the journals of the selected Multi Ledgers (passed in context)."""
        journal_ids = self.env.context.get('report_journal_ids')
        if journal_ids:
            return "AND aml.journal_id IN %s", (tuple(journal_ids),)
        return '', ()

    def _get_balance_at_date(self, account_types, at_date, company_id, state='posted'):
        """
        Returns the cumulative debit-credit balance for accounts of given types
        up to (and including) at_date.
        Positive = net debit balance (assets/expenses)
        Negative = net credit balance (liabilities/income/equity)
        """
        type_list = tuple(account_types) if len(account_types) > 1 else f"('{account_types[0]}')"
        state_clause = "AND aml.parent_state = 'posted'" if state == 'posted' else "AND aml.parent_state IN ('draft', 'posted')"
        journal_clause, journal_params = self._get_journal_clause()
        query = f"""
            SELECT COALESCE(SUM(aml.debit - aml.credit), 0.0)
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE aa.account_type IN %s
              AND aml.date <= %s
              AND aml.company_id IN %s
              AND aml.display_type NOT IN ('line_section', 'line_note')
              {state_clause}
              {journal_clause}
        """
        self.env.cr.execute(query, (tuple(account_types), at_date, company_id) + journal_params)
        result = self.env.cr.fetchone()
        return result[0] if result else 0.0

    def _get_period_movement(self, account_types, date_from, date_to, company_id, state='posted'):
        """
        Returns the net debit-credit movement for accounts of given types
        within the period [date_from, date_to].
        """
        state_clause = "AND aml.parent_state = 'posted'" if state == 'posted' else "AND aml.parent_state IN ('draft', 'posted')"
        journal_clause, journal_params = self._get_journal_clause()
        query = f"""
            SELECT COALESCE(SUM(aml.debit - aml.credit), 0.0)
            FROM account_move_line aml
            JOIN account_account aa ON aa.id = aml.account_id
            WHERE aa.account_type IN %s
              AND aml.date >= %s
              AND aml.date <= %s
              AND aml.company_id IN %s
              AND aml.display_type NOT IN ('line_section', 'line_note')
              {state_clause}
              {journal_clause}
        """
        self.env.cr.execute(query, (tuple(account_types), date_from, date_to, company_id) + journal_params)
        result = self.env.cr.fetchone()
        return result[0] if result else 0.0

    def _compute_cash_flow_data(self):
        self.ensure_one()
        # company_id can come from client data and is used in raw SQL
        if self.company_id not in self.env.companies:
            raise UserError(_("You are not allowed to access this company's data."))
        if self.date_from > self.date_to:
            raise UserError(_('Date From must be before Date To.'))

        # all the companies of the company switcher, as in Odoo
        company_id = tuple(self._report_company_ids())
        date_from = self.date_from
        date_to = self.date_to
        state = self.target_move

        date_before = date_from - timedelta(days=1)
        # bank and cash accounts, and the credit cards: paying with a card is spending cash (in Odoo
        # Enterprise the credit card journals are liquidity journals)
        cash_types = list(CASH_ACCOUNT_TYPES)

        opening_cash = self._get_balance_at_date(cash_types, date_before, company_id, state)
        closing_cash = self._get_balance_at_date(cash_types, date_to, company_id, state)

        def init_bucket():
            return {'total': 0.0, 'accounts': {}}

        # Initialize buckets
        results = {
            'op_adv_in': init_bucket(),
            'op_cash_in': init_bucket(),
            'op_adv_out': init_bucket(),
            'op_cash_out': init_bucket(),
            'inv_in': init_bucket(),
            'inv_out': init_bucket(),
            'fin_in': init_bucket(),
            'fin_out': init_bucket(),
            'unclass_in': init_bucket(),
            'unclass_out': init_bucket(),
        }

        def add_to_bucket(bucket_name, cf_amount, account, tx_data=None):
            results[bucket_name]['total'] += cf_amount
            key = (account.id, account.code or '', account.name or '')
            if key not in results[bucket_name]['accounts']:
                results[bucket_name]['accounts'][key] = {
                    'balance': 0.0,
                    'transactions': []
                }
            results[bucket_name]['accounts'][key]['balance'] += cf_amount
            if tx_data:
                results[bucket_name]['accounts'][key]['transactions'].append(tx_data)

        cash_domain = [
            ('company_id', 'in', list(company_id)),
            ('account_id.account_type', 'in', cash_types),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('parent_state', 'in', ('posted',) if state == 'posted' else ('draft', 'posted')),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]
        journal_ids = self.env.context.get('report_journal_ids')
        if journal_ids:
            cash_domain.append(('journal_id', 'in', list(journal_ids)))
        cash_lines = self.env['account.move.line'].search(cash_domain)

        # What the cash was paid or received for, followed through the outstanding accounts and the
        # reconciliations of the receivables and payables with the invoices and bills, as in Odoo
        # Enterprise: a supplier payment for equipment is an investing flow, a loan repayment or a
        # dividend paid a financing one.
        engine = self.env['report.accounting_pdf_reports.report_cash_flow']
        for entry in engine._trace_cash_lines(cash_lines, self.env['res.company'].browse(company_id)):
            cf_amount = entry['amount']
            if not cf_amount:
                continue
            is_in = cf_amount > 0
            origin = entry['origin']
            account = entry['account'] or origin.account_id
            activity, line_key = entry['activity'], entry['line']
            if activity == 'investing':
                bucket = 'inv_in' if is_in else 'inv_out'
            elif activity == 'financing':
                bucket = 'fin_in' if is_in else 'fin_out'
            elif entry['partner_line']:
                # paid invoices and bills: cash received from / paid for operating activities
                bucket = 'op_cash_in' if is_in else 'op_cash_out'
            elif line_key == 'receivable':
                # not matched with an invoice: advance of (or refund to) a customer
                bucket = 'op_adv_in'
            elif line_key == 'payable':
                # not matched with a bill: advance to (or refund from) a supplier
                bucket = 'op_adv_out'
            elif line_key in ('unmatched', 'transfer', 'other'):
                bucket = 'unclass_in' if is_in else 'unclass_out'
            else:
                bucket = 'op_cash_in' if is_in else 'op_cash_out'

            # Transaction detail dict for drill-down
            move = origin.move_id
            partner = move.partner_id or origin.partner_id
            move_display_name = move.name or '/'
            tx_label = origin.name or move.ref or move_display_name
            if partner:
                tx_label = f"{move_display_name} - {partner.name} ({tx_label})"
            else:
                tx_label = f"{move_display_name} ({tx_label})"

            tx_data = {
                'id': origin.id,
                'move_id': move.id,
                'move_name': move_display_name,
                'move_type': move.move_type or 'entry',
                'name': tx_label,
                'ref': move.ref or origin.ref or '',
                'date': str(origin.date or ''),
                'partner_id': partner.id or False,
                'partner_name': partner.name or '',
                'balance': cf_amount,
                'account_id': account.id,
            }
            add_to_bucket(bucket, cf_amount, account, tx_data)

        # Format buckets to lists
        for b_name in results:
            acc_list = []
            for (acc_id, code, name), acc_data in results[b_name]['accounts'].items():
                bal = acc_data['balance']
                if round(bal, 2) != 0:
                    acc_list.append({
                        'id': acc_id,
                        'name': f"{code} {name}",
                        'balance': bal,
                        'transactions': acc_data['transactions'],
                    })
            acc_list.sort(key=lambda x: x['name'])
            results[b_name]['account_lines'] = acc_list
            del results[b_name]['accounts']

        # Calculate subtotals
        operating_total = results['op_adv_in']['total'] + results['op_cash_in']['total'] + results['op_adv_out']['total'] + results['op_cash_out']['total']
        investing_total = results['inv_in']['total'] + results['inv_out']['total']
        financing_total = results['fin_in']['total'] + results['fin_out']['total']
        unclassified_total = results['unclass_in']['total'] + results['unclass_out']['total']
        
        net_increase = operating_total + investing_total + financing_total + unclassified_total

        return {
            'date_from': date_from,
            'date_to': date_to,
            'company': self.company_id.id,
            'target_move': self.target_move,
            'opening_cash': opening_cash,
            'closing_cash': closing_cash,
            'net_increase': net_increase,
            'op_adv_in': results['op_adv_in'],
            'op_cash_in': results['op_cash_in'],
            'op_adv_out': results['op_adv_out'],
            'op_cash_out': results['op_cash_out'],
            'operating_total': operating_total,
            'inv_in': results['inv_in'],
            'inv_out': results['inv_out'],
            'investing_total': investing_total,
            'fin_in': results['fin_in'],
            'fin_out': results['fin_out'],
            'financing_total': financing_total,
            'unclass_in': results['unclass_in'],
            'unclass_out': results['unclass_out'],
            'unclassified_total': unclassified_total,
        }

    def action_print_report(self):
        self.ensure_one()
        data = self._compute_cash_flow_data()
        return self.env.ref(
            'hudson_accounting_enhancements.action_report_cash_flow'
        ).report_action(self, data={'form': data})

    def check_report(self):
        return self.action_print_report()
