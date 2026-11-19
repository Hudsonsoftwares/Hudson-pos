from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestHudsonDynamicReports(AccountTestInvoicingCommon):
    """Regression tests of the on-screen accounting reports (hudson.dynamic.report)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data['company']
        cls.company.write({'fiscalyear_last_day': 31, 'fiscalyear_last_month': '12'})
        cls.report = cls.env['hudson.dynamic.report']
        cls.bank = cls.company_data['default_journal_bank'].default_account_id
        cls.receivable = cls.company_data['default_account_receivable']
        cls.revenue = cls.company_data['default_account_revenue']
        cls.misc_journal = cls.company_data['default_journal_misc']
        cls.capital = cls.env['account.account'].create({
            'name': 'Share Capital', 'code': 'HCAP01', 'account_type': 'equity',
        })
        cls.customer = cls.env['res.partner'].create({'name': 'Hudson Customer'})

        # 2025: capital 1000 in the bank, a sale of 500 on credit
        cls._entry('2025-03-01', [(cls.bank, 1000, 0), (cls.capital, 0, 1000)])
        sale = cls._entry('2025-06-01', [(cls.receivable, 500, 0, cls.customer), (cls.revenue, 0, 500)])
        # 2026: a cash sale of 200, and the 2025 sale paid on 10/02/2026
        cls._entry('2026-02-01', [(cls.bank, 200, 0), (cls.revenue, 0, 200)])
        payment = cls._entry('2026-02-10', [(cls.bank, 500, 0), (cls.receivable, 0, 500, cls.customer)])
        (sale + payment).line_ids.filtered(lambda l: l.account_id == cls.receivable).reconcile()

    @classmethod
    def _entry(cls, date, lines, post=True):
        move = cls.env['account.move'].create({
            'move_type': 'entry',
            'date': date,
            'journal_id': cls.misc_journal.id,
            'line_ids': [(0, 0, {
                'account_id': line[0].id,
                'debit': line[1],
                'credit': line[2],
                'partner_id': line[3].id if len(line) > 3 else False,
                'name': 'test',
            }) for line in lines],
        })
        if post:
            move.action_post()
        return move

    # ------------------------------------------------------------------
    def _get(self, model_name, **form):
        form.setdefault('target_move', 'posted')
        return self.report.get_report_data(model_name, False, {'form': form})

    def _bs(self, **form):
        bs = self.env.ref('accounting_pdf_reports.account_financial_report_balancesheet0')
        form.setdefault('debit_credit', False)
        return self._get('accounting.report', account_report_id=[bs.id, bs.name], **form)

    def _line(self, result, name, field='balance', line_type=None):
        matches = [line for line in result['lines'] if (line.get('name') or '').strip() == name
                   and (line_type is None or line.get('type') == line_type)]
        self.assertEqual(len(matches), 1, (name, [line.get('name') for line in result['lines']]))
        return matches[0].get(field)

    # ------------------------------------------------------------------
    # 1 + 2. Balance Sheet: cumulative, equity counted once, balanced
    # ------------------------------------------------------------------
    def test_balance_sheet_cumulative_and_balanced(self):
        res = self._bs(date_from='2026-01-01', date_to='2026-12-31',
                       comparison='same_last_year', previous_periods=1)
        assets = self._line(res, 'Assets')
        liabilities = self._line(res, 'Liabilities')
        equity = self._line(res, 'Equity')
        # cumulative: the 2025 capital and receivable still count in 2026
        self.assertAlmostEqual(assets, 1700.0)
        self.assertAlmostEqual(liabilities, 0.0)
        self.assertAlmostEqual(equity, 1700.0)
        self.assertAlmostEqual(assets, liabilities + equity)
        self.assertAlmostEqual(self._line(res, 'Previous Years Unallocated Earnings'), 500.0)
        self.assertAlmostEqual(self._line(res, 'Current Year Profit / (Loss)'), 200.0)
        # comparison column: the position at 31/12/2025
        self.assertAlmostEqual(self._line(res, 'Assets', 'balance_cmp_1'), 1500.0)
        self.assertAlmostEqual(self._line(res, 'Equity', 'balance_cmp_1'), 1500.0)
        self.assertAlmostEqual(self._line(res, 'Previous Years Unallocated Earnings', 'balance_cmp_1'), 0.0)
        # the legacy Equity node of accounting_pdf_reports is out of the tree
        names = [line['name'] for line in res['lines']]
        self.assertNotIn('Capital and Reserves', names)
        self.assertEqual(names.count('Equity'), 1)
        self.assertFalse(self.env.ref('accounting_pdf_reports.account_financial_report_equity0').parent_id)

    def test_balance_sheet_as_of_date(self):
        res = self._bs(date_to='2026-01-31')
        self.assertAlmostEqual(self._line(res, 'Assets'), 1500.0)
        self.assertAlmostEqual(self._line(res, 'Equity'), 1500.0)
        self.assertAlmostEqual(self._line(res, 'Previous Years Unallocated Earnings'), 500.0)

    def test_profit_and_loss_defaults_to_fiscal_year(self):
        pl = self.env.ref('accounting_pdf_reports.account_financial_report_profitandloss0')
        res = self._get('accounting.report', account_report_id=[pl.id, pl.name], debit_credit=False,
                        date_to='2026-12-31')
        self.assertAlmostEqual(self._line(res, 'Net Profit'), 200.0)

    # ------------------------------------------------------------------
    # 3. Trial Balance / General Ledger: P&L accounts restart every fiscal year
    # ------------------------------------------------------------------
    def test_trial_balance_resets_pl_accounts(self):
        res = self._get('account.balance.report', date_from='2026-01-01', date_to='2026-12-31',
                        display_account='movement')
        rev = next(line for line in res['lines'] if line.get('account_id') == self.revenue.id)
        self.assertAlmostEqual(rev['initial_balance'], 0.0)
        self.assertAlmostEqual(rev['end_balance'], -200.0)
        self.assertAlmostEqual(self._line(res, 'Undistributed Profits/Losses', 'initial_balance'), -500.0)
        self.assertAlmostEqual(self._line(res, 'Total', 'initial_balance'), 0.0)
        self.assertAlmostEqual(self._line(res, 'Total', 'end_balance'), 0.0)

    def test_trial_balance_follows_fiscal_year(self):
        # April - March fiscal year: June 2025 belongs to the year started on 1 April 2025
        self.company.write({'fiscalyear_last_day': 31, 'fiscalyear_last_month': '3'})
        res = self._get('account.balance.report', date_from='2026-01-01', date_to='2026-01-31',
                        display_account='all')
        rev = next(line for line in res['lines'] if line.get('account_id') == self.revenue.id)
        self.assertAlmostEqual(rev['initial_balance'], -500.0)
        self.assertFalse([line for line in res['lines'] if line['id'] == 'unallocated'])

    def test_general_ledger_resets_pl_accounts(self):
        res = self._get('account.report.general.ledger', date_from='2026-01-01', date_to='2026-12-31',
                        display_account='movement')
        rev = next(line for line in res['lines']
                   if line.get('account_id') == self.revenue.id and line['type'] == 'account')
        self.assertAlmostEqual(rev['balance'], -200.0)
        self.assertFalse([line for line in res['lines'] if line['id'] == f'aml_init_{self.revenue.id}'])
        bank = next(line for line in res['lines']
                    if line.get('account_id') == self.bank.id and line['type'] == 'account')
        self.assertAlmostEqual(bank['balance'], 1700.0)
        self.assertAlmostEqual(self._line(res, 'Undistributed Profits/Losses'), -500.0)
        self.assertAlmostEqual(self._line(res, 'Total General Ledger'), 0.0)

    # ------------------------------------------------------------------
    # 4. Partner Ledger: opening balance, paid items shown, open at the report date
    # ------------------------------------------------------------------
    def test_partner_ledger_opening_balance(self):
        res = self._get('account.report.partner.ledger', date_from='2026-01-01', date_to='2026-12-31')
        partner_line = next(line for line in res['lines']
                            if line['type'] == 'partner' and line['partner_id'] == self.customer.id)
        self.assertAlmostEqual(partner_line['balance'], 0.0)
        initial = next(line for line in res['lines']
                       if line['type'] == 'initial_balance' and line['partner_id'] == self.customer.id)
        self.assertAlmostEqual(initial['balance'], 500.0)
        moves = [line for line in res['lines']
                 if line['type'] == 'move_line' and line['partner_id'] == self.customer.id]
        self.assertEqual(len(moves), 1, "the (reconciled) payment is shown by default")
        self.assertAlmostEqual(moves[0]['balance'], 0.0)

    def test_partner_ledger_unreconciled_at_report_date(self):
        # paid on 10/02/2026: still open at 31/01/2026
        res = self._get('account.report.partner.ledger', date_from='2026-01-01', date_to='2026-01-31',
                        unreconciled=True)
        partner_line = next(line for line in res['lines']
                            if line['type'] == 'partner' and line['partner_id'] == self.customer.id)
        self.assertAlmostEqual(partner_line['balance'], 500.0)
        res = self._get('account.report.partner.ledger', date_from='2026-01-01', date_to='2026-12-31',
                        unreconciled=True)
        self.assertFalse([line for line in res['lines'] if line.get('partner_id') == self.customer.id])

    # ------------------------------------------------------------------
    # 6. Deferred revenue: credit notes are deducted
    # ------------------------------------------------------------------
    def test_deferred_revenue_credit_note(self):
        deferral = {'hudson_deferred_start_date': '2026-01-01', 'hudson_deferred_end_date': '2026-12-31'}
        invoice = self._entry('2026-01-01', [(self.receivable, 1200, 0, self.customer), (self.revenue, 0, 1200)],
                              post=False)
        invoice.line_ids.filtered(lambda l: l.account_id == self.revenue).write(deferral)
        invoice.action_post()
        res = self._get('account.deferred.revenue.report', date_from='2026-01-01', date_to='2026-01-31')
        self.assertAlmostEqual(self._line(res, 'Total', 'total', 'total'), 1200.0)

        refund = self._entry('2026-01-15', [(self.revenue, 1200, 0), (self.receivable, 0, 1200, self.customer)],
                             post=False)
        refund.line_ids.filtered(lambda l: l.account_id == self.revenue).write(deferral)
        refund.action_post()
        res = self._get('account.deferred.revenue.report', date_from='2026-01-01', date_to='2026-01-31')
        for field in ('total', 'period', 'recognized', 'later'):
            self.assertAlmostEqual(self._line(res, 'Total', field, 'total'), 0.0, msg=field)

    # ------------------------------------------------------------------
    # 9, 10, 11
    # ------------------------------------------------------------------
    def test_unposted_alert(self):
        self._entry('2026-03-01', [(self.bank, 10, 0), (self.revenue, 0, 10)], post=False)
        res = self._get('account.balance.report', date_from='2026-01-01', date_to='2026-12-31', target_move='posted')
        self.assertTrue(res.get('alert_message'))
        res = self._get('account.balance.report', date_from='2026-01-01', date_to='2026-12-31', target_move='all')
        self.assertFalse(res.get('alert_message'))
        res = self._get('account.balance.report', date_from='2025-01-01', date_to='2025-12-31', target_move='posted')
        self.assertFalse(res.get('alert_message'))

    def test_vacuumed_wizard(self):
        for model in ('account.tax.extended.wizard', 'account.executive.summary.wizard'):
            res = self.report.get_report_data(model, 987654321, {'form': {
                'date_from': '2026-01-01', 'date_to': '2026-12-31', 'target_move': 'posted',
                'company_id': [self.company.id, self.company.name],
                'comparison': 'no_comparison', 'date_type': 'year', 'unknown_option': 1,
            }})
            self.assertIsInstance(res['lines'], list, model)

    def test_dates_validated(self):
        with self.assertRaises(UserError):
            self._get('account.balance.report', date_from='2026-12-31', date_to='2026-01-01')
