from datetime import date

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestHudsonLoansAccrualsDeferrals(AccountTestInvoicingCommon):
    """ Loans (term, 0% rate, rounding, cancellation), deferral reset, accruals and bill quantities. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.long_term_account = Account.create({
            'code': '170100', 'name': 'Loan Long Term', 'account_type': 'liability_non_current'})
        cls.short_term_account = Account.create({
            'code': '170200', 'name': 'Loan Short Term', 'account_type': 'liability_current', 'reconcile': True})
        cls.interest_account = Account.create({
            'code': '661100', 'name': 'Loan Interest', 'account_type': 'expense'})
        cls.misc_journal = cls.company_data['default_journal_misc']
        cls.eur = cls.setup_other_currency('EUR')  # 2 EUR for 1 USD since 2016

    # -------------------------------------------------------------------------
    # Loans
    # -------------------------------------------------------------------------

    def _create_loan(self, **vals):
        return self.env['hudson.loan'].create({
            'name': 'Bank Loan',
            'amount_borrowed': 10000.0,
            'date': date(2025, 1, 1),
            'duration': 18,
            'long_term_account_id': self.long_term_account.id,
            'short_term_account_id': self.short_term_account.id,
            'expense_account_id': self.interest_account.id,
            'journal_id': self.misc_journal.id,
            **vals,
        })

    def _compute_loan(self, loan, **vals):
        action = loan.action_compute()
        wizard = self.env['hudson.loan.compute.wizard'].with_context(action['context']).create({
            'interest_rate': 5.0,
            **vals,
        })
        wizard.action_apply()
        return wizard

    def test_loan_term_in_months(self):
        loan = self._create_loan()
        wizard = self._compute_loan(loan)
        self.assertEqual(wizard.term_months, 18, 'the term of the loan is the default of the wizard')
        self.assertEqual(len(loan.line_ids), 18)
        self.assertEqual(loan.duration, 18)

    def test_loan_zero_interest(self):
        loan = self._create_loan(amount_borrowed=1000.0)
        self._compute_loan(loan, interest_rate=0.0, term_months=3)
        lines = loan.line_ids.sorted('date')
        self.assertEqual(lines.mapped('interest'), [0.0, 0.0, 0.0])
        self.assertEqual(lines.mapped('principal'), [333.33, 333.33, 333.34])
        self.assertEqual(lines[-1].balance, 0.0)

    def test_loan_negative_interest_refused(self):
        loan = self._create_loan()
        with self.assertRaises(UserError):
            self._compute_loan(loan, interest_rate=-1.0)

    def test_loan_rounding_absorbed_by_last_instalment(self):
        loan = self._create_loan(amount_borrowed=10000.0)
        self._compute_loan(loan, interest_rate=7.3, term_months=7)
        lines = loan.line_ids
        for line in lines:
            for amount in (line.principal, line.interest, line.payment):
                self.assertEqual(round(amount, 2), amount)
        self.assertAlmostEqual(sum(lines.mapped('principal')), 10000.0, places=6)
        self.assertEqual(lines.sorted('date')[-1].balance, 0.0)

        with freeze_time('2025-12-31'):
            loan.action_confirm()
        principal_moves = loan.move_ids.filtered(lambda m: 'Principal' in (m.ref or ''))
        repaid = sum(principal_moves.line_ids.filtered(
            lambda l: l.account_id == self.long_term_account and l.name == 'Principal Repayment').mapped('debit'))
        self.assertAlmostEqual(repaid, 10000.0, places=2, msg='nothing is left on the loan account')

    def test_loan_cancel_reverses_posted_and_blocks_reconciled(self):
        loan = self._create_loan(amount_borrowed=1200.0)
        self._compute_loan(loan, interest_rate=0.0, term_months=12)
        with freeze_time('2025-03-15'):
            loan.action_confirm()
        instalments = loan.move_ids.filtered(lambda m: 'Principal' in (m.ref or ''))
        posted = instalments.filtered(lambda m: m.state == 'posted')
        self.assertEqual(len(posted), 2)  # January and February
        drafts = loan.move_ids.filtered(lambda m: m.state == 'draft')
        self.assertTrue(drafts)

        # the January instalment is matched with the bank
        january = posted.sorted('date')[0]
        payment = self.env['account.move'].create({
            'journal_id': self.misc_journal.id,
            'date': date(2025, 1, 31),
            'line_ids': [
                Command.create({'name': 'Bank', 'account_id': self.short_term_account.id, 'debit': 100.0}),
                Command.create({'name': 'Bank', 'account_id': self.company_data['default_account_assets'].id,
                                'credit': 100.0}),
            ],
        })
        payment.action_post()
        matched = (payment.line_ids | january.line_ids).filtered(lambda l: l.account_id == self.short_term_account)
        matched.reconcile()

        with freeze_time('2025-03-15'), self.assertRaises(UserError):
            loan.action_cancel()
        self.assertEqual(loan.state, 'running')

        matched.remove_move_reconcile()
        with freeze_time('2025-03-15'):
            loan.action_cancel()
        self.assertEqual(loan.state, 'cancelled')
        self.assertFalse(drafts.exists(), 'the instalments to come are deleted')
        self.assertEqual(posted.exists(), posted, 'the posted instalments are kept...')
        self.assertTrue(all(move.reversal_move_ids.filtered(lambda r: r.state == 'posted') for move in posted),
                        '...and reversed')

    # -------------------------------------------------------------------------
    # Deferrals
    # -------------------------------------------------------------------------

    def test_reset_invoice_reverses_posted_deferrals(self):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2025-01-01',
            'invoice_line_ids': [Command.create({
                'name': 'Subscription',
                'price_unit': 1200.0,
                'tax_ids': [],
                'hudson_deferred_start_date': date(2025, 1, 1),
                'hudson_deferred_end_date': date(2025, 12, 31),
            })],
        })
        with freeze_time('2025-02-15'):
            invoice.action_post()
            deferrals = invoice.hudson_deferral_move_ids
            self.assertEqual(len(deferrals), 13)
            # the auto-post job posts January
            deferrals.filtered(lambda m: m.state == 'draft' and m.date <= date(2025, 2, 15))._post()
            posted = deferrals.filtered(lambda m: m.state == 'posted')
            self.assertEqual(len(posted), 2)  # the initial deferral and January

            invoice.button_draft()
        self.assertEqual(posted.exists(), posted, 'posted deferral entries are never deleted')
        self.assertTrue(all(move.reversal_move_ids for move in posted))
        self.assertFalse((deferrals - posted).exists(), 'the draft deferral entries are deleted')

        with freeze_time('2025-02-15'):
            invoice.action_post()
        self.assertEqual(len(invoice._get_active_hudson_deferrals()), 13, 'the deferrals are generated again')

    # -------------------------------------------------------------------------
    # Purchase: bill quantities and accruals
    # -------------------------------------------------------------------------

    def _create_po(self, purchase_method, **vals):
        product = self.env['product.product'].create({
            'name': 'Consulting',
            'type': 'service',
            'purchase_method': purchase_method,
            'standard_price': 100.0,
        })
        order = self.env['purchase.order'].create({
            'partner_id': self.partner_a.id,
            'order_line': [Command.create({
                'product_id': product.id,
                'product_qty': 10.0,
                'price_unit': 100.0,
                'tax_ids': [],
            })],
            **vals,
        })
        order.button_confirm()
        order.order_line.qty_received = 4.0
        return order

    def test_bill_quantity_follows_control_policy(self):
        order = self._create_po('receive')
        order.action_create_invoice()
        self.assertEqual(order.invoice_ids.invoice_line_ids.quantity, 4.0, 'billed on received quantities')

        order = self._create_po('purchase')
        order.action_create_invoice()
        self.assertEqual(order.invoice_ids.invoice_line_ids.quantity, 10.0, 'billed on ordered quantities')

    def test_accrual_wizard_currency_discount_analytic(self):
        analytic_plan = self.env['account.analytic.plan'].create({'name': 'Projects'})
        analytic_account = self.env['account.analytic.account'].create({
            'name': 'Project X', 'plan_id': analytic_plan.id})
        order = self._create_po('receive', currency_id=self.eur.id)
        order.order_line.write({
            'discount': 10.0,
            'analytic_distribution': {str(analytic_account.id): 100.0},
        })
        accrual_account = self.env['account.account'].create({
            'code': '218100', 'name': 'Accrued Expenses', 'account_type': 'liability_current'})
        wizard = self.env['hudson.account.accrued.orders.wizard'].with_context(
            active_model='purchase.order.line', active_ids=order.order_line.ids,
        ).create({'account_id': accrual_account.id, 'date': date(2025, 3, 15)})
        self.assertEqual(wizard.reversal_date, date(2025, 4, 1))
        line = wizard.preview_line_ids
        # 4 received x 100 EUR - 10% = 360 EUR = 180 USD
        self.assertEqual(line.amount_currency, 360.0)
        self.assertEqual(line.debit, 180.0)
        self.assertEqual(line.analytic_distribution, {str(analytic_account.id): 100.0})

        with freeze_time('2025-03-20'):
            wizard.create_entries()
        move = self.env['account.move'].search([('line_ids.account_id', '=', accrual_account.id)], order='id')
        accrual, reversal = move.sorted('date')
        self.assertEqual(accrual.state, 'posted')
        self.assertEqual(reversal.date, date(2025, 4, 1))
        self.assertEqual(reversal.state, 'draft', 'posted by the auto-post job on its date')
        expense_line = accrual.line_ids.filtered(lambda l: l.account_id != accrual_account)
        self.assertEqual((expense_line.balance, expense_line.amount_currency, expense_line.currency_id),
                         (180.0, 360.0, self.eur))

    def test_standard_accrual_reversal_default(self):
        order = self._create_po('receive')
        wizard = self.env['account.accrued.orders.wizard'].with_context(
            active_model='purchase.order', active_ids=order.ids,
        ).create({'accrual_type': 'bill_to_receive', 'date': date(2025, 3, 15)})
        self.assertEqual(wizard.reversal_date, date(2025, 4, 1))
