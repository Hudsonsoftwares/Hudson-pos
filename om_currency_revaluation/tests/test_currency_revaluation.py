from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestCurrencyRevaluation(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # in Odoo a rate applies to the days after its date: 1.6 on the 30th is the rate of the 31st
        cls.foreign = cls.setup_other_currency('EUR', rates=[('2026-01-01', 2.0), ('2026-01-30', 1.6),
                                                             ('2026-02-27', 1.25)])
        cls.gain_account = cls.env['account.account'].create({
            'name': 'Unrealized Gain', 'code': 'REVGAIN', 'account_type': 'income_other',
        })
        cls.loss_account = cls.env['account.account'].create({
            'name': 'Unrealized Loss', 'code': 'REVLOSS', 'account_type': 'expense',
        })
        cls.company.write({
            'currency_reval_journal_id': cls.company_data['default_journal_misc'].id,
            'currency_reval_gain_account_id': cls.gain_account.id,
            'currency_reval_loss_account_id': cls.loss_account.id,
        })
        cls.receivable = cls.company_data['default_account_receivable']

    def _wizard(self, date='2026-01-31', **values):
        return self.env['currency.revaluation'].create({'date': date, **values})

    def _revalue(self, date='2026-01-31', **values):
        return self.env['account.move'].browse(self._wizard(date, **values).action_revalue()['res_id'])

    def _invoice(self, amount=1000.0, date='2026-01-01', move_type='out_invoice'):
        invoice = self.init_invoice(move_type, partner=self.partner_a, invoice_date=date, amounts=[amount],
                                    currency=self.foreign, post=True)
        return invoice

    def _adjustment_of(self, move, account):
        return sum(move.line_ids.filtered(lambda line: line.account_id == account).mapped('balance'))

    def test_open_invoice_is_revalued_at_the_closing_rate(self):
        # 1000 EUR booked at a rate of 2.0 is worth 500, and 625 at the closing rate of 1.6
        invoice = self._invoice()
        self.assertEqual(self._adjustment_of(invoice, self.receivable), 500.0)

        wizard = self._wizard()
        self.assertEqual(wizard.line_ids.mapped('amount_currency'), [1000.0])
        self.assertEqual(wizard.line_ids.balance, 500.0)
        self.assertEqual(wizard.line_ids.revalued, 625.0)
        self.assertEqual(wizard.adjustment, 125.0)

        action = wizard.action_revalue()
        move = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(move.state, 'posted')
        self.assertEqual(move.currency_reval_date, wizard.date)
        self.assertEqual(move.journal_id, self.company_data['default_journal_misc'])
        # the receivable is worth 125 more, against the unrealized gain account
        self.assertEqual(self._adjustment_of(move, self.receivable), 125.0)
        self.assertEqual(self._adjustment_of(move, self.gain_account), -125.0)
        self.assertFalse(self._adjustment_of(move, self.loss_account))
        # the amount in the foreign currency of the receivable does not change, only what it is worth
        receivable_line = move.line_ids.filtered(lambda line: line.account_id == self.receivable)
        self.assertEqual(receivable_line.currency_id, self.foreign)
        self.assertEqual(receivable_line.amount_currency, 0.0)
        self.assertFalse(receivable_line.partner_id)
        self.assertEqual(sum(move.line_ids.mapped('balance')), 0.0)

        # the revaluation is always reversed, on the next day by default
        reversal = move.reversal_move_ids
        self.assertEqual(reversal.state, 'posted')
        self.assertEqual(str(reversal.date), '2026-02-01')
        self.assertEqual(self._adjustment_of(reversal, self.receivable), -125.0)
        # matched with its reversal, the adjustment is never an open item of a customer (follow-ups, aged balance)
        self.assertTrue(receivable_line.reconciled)
        self.assertFalse(self.env['account.move.line'].search_count([
            ('move_id', 'in', (move | reversal).ids), ('account_id', '=', self.receivable.id),
            ('reconciled', '=', False)]))
        invoice_line = invoice.line_ids.filtered(lambda line: line.account_id == self.receivable)
        self.assertEqual(invoice_line.amount_residual, 500.0)
        self.assertEqual(invoice.payment_state, 'not_paid')

    def test_a_bill_worth_more_at_the_closing_rate_is_a_loss(self):
        # the foreign currency gains on the company one: what is owed in it costs more
        foreign = self.setup_other_currency('GBP', rates=[('2026-01-01', 2.0), ('2026-01-30', 1.6)])
        bill = self.init_invoice('in_invoice', partner=self.partner_a, invoice_date='2026-01-01',
                                 amounts=[1000.0], currency=foreign, post=True)
        self.assertEqual(bill.amount_total_signed, -500.0)

        # 1000 GBP owed is worth 625 at the closing rate instead of the 500 in the books
        wizard = self._wizard(currency_ids=[Command.set(foreign.ids)])
        self.assertEqual(wizard.adjustment, -125.0)
        move = self.env['account.move'].browse(wizard.action_revalue()['res_id'])
        payable = self.company_data['default_account_payable']
        self.assertEqual(self._adjustment_of(move, payable), -125.0)
        self.assertEqual(self._adjustment_of(move, self.loss_account), 125.0)
        self.assertFalse(self._adjustment_of(move, self.gain_account))

    def test_paid_invoices_and_the_rate_of_the_date_are_left_out(self):
        paid = self._invoice()
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=paid.ids,
        ).create({'payment_date': '2026-01-15', 'currency_id': self.foreign.id})._create_payments()
        # om_account_accountant keeps an invoice 'in payment' until the payment is matched with a statement
        self.assertFalse(paid.line_ids.filtered(
            lambda line: line.account_type == 'asset_receivable' and not line.reconciled))
        later = self._invoice(date='2026-02-05')
        open_invoice = self._invoice(amount=500.0)

        receivable_lines = self._wizard().line_ids.filtered(lambda line: line.account_id == self.receivable)
        # the invoice paid before the date and the one posted after it are not revalued
        self.assertEqual(receivable_lines.mapped('amount_currency'), [500.0])
        self.assertNotIn(later.name, receivable_lines.mapped('account_id.name'))

        # a payment after the revaluation date does not change what was open on that date
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=open_invoice.ids,
        ).create({'payment_date': '2026-02-10', 'currency_id': self.foreign.id})._create_payments()
        self.assertEqual(self._wizard().line_ids.filtered(
            lambda line: line.account_id == self.receivable).mapped('amount_currency'), [500.0])

    def test_a_bank_account_in_a_foreign_currency_is_revalued(self):
        journal = self.env['account.journal'].create({
            'name': 'Foreign Bank', 'type': 'bank', 'code': 'FBNK', 'currency_id': self.foreign.id,
        })
        statement = self.env['account.bank.statement'].create({
            'name': 'Opening', 'line_ids': [Command.create({
                'journal_id': journal.id, 'date': '2026-01-02', 'payment_ref': 'Transfer',
                'amount': 800.0, 'foreign_currency_id': False,
            })],
        })
        self.assertEqual(statement.line_ids.move_id.state, 'posted')
        bank_account = journal.default_account_id
        self.assertEqual(bank_account.currency_id, self.foreign)

        wizard = self._wizard()
        bank_line = wizard.line_ids.filtered(lambda line: line.account_id == bank_account)
        # 800 EUR booked at 2.0 is worth 400, and 500 at the closing rate
        self.assertEqual(bank_line.amount_currency, 800.0)
        self.assertEqual(bank_line.balance, 400.0)
        self.assertEqual(bank_line.adjustment, 100.0)

        move = self.env['account.move'].browse(wizard.action_revalue()['res_id'])
        adjustment_line = move.line_ids.filtered(lambda line: line.account_id == bank_account)
        self.assertEqual(adjustment_line.balance, 100.0)
        # the balance of the bank account in its own currency stays the same
        self.assertEqual(adjustment_line.amount_currency, 0.0)
        self.assertEqual(adjustment_line.currency_id, self.foreign)
        # nothing left on the same date
        self.assertFalse(self._wizard().line_ids.filtered(lambda line: line.account_id == bank_account))
        # reversed on the 1st: February is revalued from the 400 in the books, 640 at the rate of 1.25
        self.assertEqual(self._wizard(date='2026-02-28').line_ids.filtered(
            lambda line: line.account_id == bank_account).adjustment, 240.0)

    def test_the_same_date_is_not_revalued_twice(self):
        self._invoice()
        self._revalue()
        # what was posted on that date counts: nothing is left to post
        self.assertFalse(self._wizard().line_ids)
        with self.assertRaises(UserError):
            self._wizard().action_revalue()
        # an invoice posted afterwards in the period: only its own adjustment is posted
        self._invoice(amount=200.0, date='2026-01-20')
        wizard = self._wizard()
        self.assertEqual(wizard.adjustment, 25.0)
        move = self.env['account.move'].browse(wizard.action_revalue()['res_id'])
        self.assertEqual(self._adjustment_of(move, self.receivable), 25.0)
        # another date is fine
        self.assertTrue(self._revalue(date='2026-02-28'))

    def test_a_reversed_revaluation_can_be_done_again(self):
        self._invoice()
        move = self._revalue()
        # reversed on its own date, e.g. because it was wrong: the date is revalued again in full
        cancel = move._reverse_moves(default_values_list=[{'date': move.date}])
        cancel.action_post()
        wizard = self._wizard()
        self.assertEqual(wizard.adjustment, 125.0)
        again = self.env['account.move'].browse(wizard.action_revalue()['res_id'])
        self.assertEqual(self._adjustment_of(again, self.receivable), 125.0)

    def test_a_cancelled_revaluation_can_be_done_again(self):
        self._invoice()
        move = self._revalue()
        (move.reversal_move_ids | move).button_draft()
        (move.reversal_move_ids | move).button_cancel()
        self.assertEqual(self._wizard().adjustment, 125.0)

    def test_every_period_only_adjusts_what_is_left(self):
        # 1000 EUR booked at 2.0 = 500, worth 625 at the end of January and 800 at the end of February
        self._invoice()
        january = self._revalue()
        self.assertEqual(self._adjustment_of(january, self.gain_account), -125.0)
        february = self._wizard(date='2026-02-28')
        # the January adjustment is reversed on the 1st of February: February is revalued from the books, 300
        self.assertEqual(february.adjustment, 300.0)
        move = self.env['account.move'].browse(february.action_revalue()['res_id'])
        self.assertEqual(self._adjustment_of(move, self.gain_account), -300.0)
        # on the 28th of February the unrealized gain in the books is the 300 of the February rate, not 425
        gain = sum(self.env['account.move.line'].search([
            ('account_id', '=', self.gain_account.id), ('parent_state', '=', 'posted'),
            ('date', '<=', '2026-02-28')]).mapped('balance'))
        self.assertEqual(gain, -300.0)

    def test_an_unreversed_revaluation_is_not_booked_again(self):
        # an adjustment entry of an earlier version, never reversed: +125 on the 31st of January, in the
        # currency of the company
        self._invoice()
        self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.company_data['default_journal_misc'].id,
            'date': '2026-01-31', 'currency_reval_date': '2026-01-31',
            'line_ids': [
                Command.create({'account_id': self.receivable.id, 'partner_id': self.partner_a.id,
                                'balance': 125.0, 'amount_currency': 125.0,
                                'currency_id': self.company.currency_id.id}),
                Command.create({'account_id': self.gain_account.id, 'balance': -125.0}),
            ],
        }).action_post()
        # only the 175 still missing to reach the 800 of February is posted, not 300 again
        self.assertEqual(self._wizard(date='2026-02-28').adjustment, 175.0)

    def test_other_reconcilable_accounts_are_revalued(self):
        advance = self.env['account.account'].create({
            'name': 'Advances to Suppliers', 'code': 'ADV001', 'account_type': 'asset_current', 'reconcile': True,
        })
        self.env['account.move'].create({
            'move_type': 'entry', 'journal_id': self.company_data['default_journal_misc'].id,
            'date': '2026-01-05',
            'line_ids': [
                Command.create({'account_id': advance.id, 'partner_id': self.partner_a.id,
                                'currency_id': self.foreign.id, 'amount_currency': 1000.0, 'balance': 500.0}),
                Command.create({'account_id': self.company_data['default_account_assets'].id,
                                'balance': -500.0}),
            ],
        }).action_post()
        wizard = self._wizard()
        line = wizard.line_ids.filtered(lambda line: line.account_id == advance)
        self.assertEqual(line.adjustment, 125.0)
        move = self.env['account.move'].browse(wizard.action_revalue()['res_id'])
        self.assertEqual(self._adjustment_of(move, advance), 125.0)
        self.assertFalse(move.line_ids.filtered(lambda line: line.account_id == advance and not line.reconciled))

    def test_custom_rates(self):
        self._invoice()
        wizard = self._wizard().with_context(currency_reval_rates={str(self.foreign.id): 1.25})
        self.assertEqual(wizard._get_revaluation_values()[0]['adjustment'], 300.0)

    def test_the_reversal_date_is_after_the_revaluation(self):
        self._invoice()
        with self.assertRaises(UserError):
            self._wizard(reversal_date='2026-01-31').action_revalue()

    def test_nothing_to_revalue(self):
        self.init_invoice('out_invoice', partner=self.partner_a, invoice_date='2026-01-01',
                          amounts=[100.0], post=True)
        wizard = self._wizard()
        self.assertFalse(wizard.line_ids)
        with self.assertRaises(UserError):
            wizard.action_revalue()

    def test_only_the_managers_post_a_revaluation(self):
        self._invoice()
        accountant = new_test_user(self.env, login='reval_accountant',
                                   groups='base.group_user,account.group_account_user',
                                   company_id=self.company.id)
        wizard = self.env['currency.revaluation'].with_user(accountant).create({'date': '2026-01-31'})
        self.assertTrue(wizard.line_ids)
        with self.assertRaises(UserError):
            wizard.action_revalue()
