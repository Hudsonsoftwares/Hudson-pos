from datetime import date

from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import Form, new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestAssetFixes(AccountTestInvoicingCommon):
    """ Degressive rate per period, first depreciation date, multi-company, disposal and assets created
    by every posting path. """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Account = cls.env['account.account']
        cls.asset_account = Account.create({'code': '151100', 'name': 'Equipment', 'account_type': 'asset_fixed'})
        cls.accumulated_account = Account.create({
            'code': '151900', 'name': 'Accumulated Depreciation', 'account_type': 'asset_fixed'})
        cls.expense_account = Account.create({
            'code': '681100', 'name': 'Depreciation Expense', 'account_type': 'expense_depreciation'})
        cls.loss_account = Account.create({
            'code': '671100', 'name': 'Loss on Asset Disposal', 'account_type': 'expense'})
        cls.env.company.asset_loss_account_id = cls.loss_account
        cls.category = cls.env['account.asset.category'].create({
            'name': 'Equipment',
            'type': 'purchase',
            'journal_id': cls.company_data['default_journal_misc'].id,
            'account_asset_id': cls.asset_account.id,
            'account_depreciation_id': cls.accumulated_account.id,
            'account_depreciation_expense_id': cls.expense_account.id,
            'method_number': 12,
            'method_period': 1,
            'date_first_depreciation': 'manual',
            'open_asset': True,
        })

    def _create_asset(self, validate_on='2024-12-15', **vals):
        asset = self.env['account.asset.asset'].create({
            'name': 'Machine',
            'category_id': self.category.id,
            'value': 1200.0,
            'date': date(2025, 1, 1),
            'method': 'linear',
            'method_time': 'number',
            'method_number': 12,
            'method_period': 1,
            'date_first_depreciation': 'last_day_period',
            **vals,
        })
        if validate_on:
            with freeze_time(validate_on):
                asset.validate()
        return asset

    def _board(self, asset):
        return asset._get_board_moves().sorted(lambda m: (m.date, m.id))

    def _create_bill(self, **vals):
        return self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2025-01-15',
            'invoice_line_ids': [Command.create({
                'name': 'Machine',
                'price_unit': 1200.0,
                'account_id': self.asset_account.id,
                'asset_category_id': self.category.id,
                'tax_ids': [],
            })],
            **vals,
        })

    # -------------------------------------------------------------------------
    # 1. Degressive factor is yearly
    # -------------------------------------------------------------------------

    def test_degressive_monthly_uses_yearly_rate(self):
        asset = self._create_asset(value=12000.0, method='degressive', method_progress_factor=0.3,
                                   method_number=60)
        amounts = self._board(asset).mapped('asset_depreciation_amount')
        # 30% a year of 12,000 is 300 a month, not 3,600
        self.assertEqual(amounts[0], 300.0)
        self.assertEqual(amounts[:12], [300.0] * 12)
        # second year: 30% of the 8,400 left at its start
        self.assertEqual(amounts[12:24], [210.0] * 12)
        self.assertEqual(len(amounts), 60)
        self.assertAlmostEqual(sum(amounts), 12000.0)

    def test_degressive_then_linear_monthly(self):
        asset = self._create_asset(value=12000.0, method='degressive_then_linear', method_progress_factor=0.3,
                                   method_number=60)
        amounts = self._board(asset).mapped('asset_depreciation_amount')
        self.assertEqual(amounts[0], 300.0)
        self.assertEqual(amounts[12], 210.0)
        # third year: 30% of 5,880 is 147 a month, less than 5,880 over the 36 months left
        self.assertEqual(amounts[24], 163.33)
        self.assertEqual(len(amounts), 60)
        self.assertAlmostEqual(sum(amounts), 12000.0)

    def test_degressive_yearly_unchanged(self):
        asset = self._create_asset(value=1000.0, method='degressive_then_linear', method_progress_factor=0.4,
                                   method_number=4, method_period=12)
        self.assertEqual(self._board(asset).mapped('asset_depreciation_amount'), [400.0, 240.0, 180.0, 180.0])

    # -------------------------------------------------------------------------
    # 2. First depreciation date
    # -------------------------------------------------------------------------

    def test_manual_without_date_ends_purchase_period(self):
        asset = self._create_asset(date=date(2025, 1, 15), date_first_depreciation='manual')
        board = self._board(asset)
        self.assertEqual(board[0].date, date(2025, 1, 31))
        self.assertEqual(board[-1].date, date(2025, 12, 31))
        self.assertEqual(board.mapped('asset_depreciation_amount'), [100.0] * 12)

    def test_manual_without_date_yearly(self):
        asset = self._create_asset(date=date(2025, 3, 1), date_first_depreciation='manual', method_number=5,
                                   method_period=12, value=1000.0)
        board = self._board(asset)
        # the asset does not finish a year early
        self.assertEqual(board.mapped('date'), [date(year, 12, 31) for year in range(2025, 2030)])

    def test_manual_without_date_prorata_has_no_one_day_entry(self):
        asset = self._create_asset(date=date(2025, 1, 15), date_first_depreciation='manual', prorata=True)
        amounts = self._board(asset).mapped('asset_depreciation_amount')
        # 17 days of January, 11 months, the 14 days left in January 2026: like Odoo's prorata temporis
        self.assertEqual(amounts, [54.84] + [100.0] * 11 + [45.16])

    def test_manual_date_onchange_default(self):
        with Form(self.env['account.asset.asset']) as asset_form:
            asset_form.name = 'Machine'
            asset_form.category_id = self.category
            asset_form.value = 1200.0
            asset_form.date = date(2025, 1, 15)
            asset_form.date_first_depreciation = 'last_day_period'
            asset_form.date_first_depreciation = 'manual'
            self.assertEqual(asset_form.first_depreciation_manual_date, date(2025, 1, 31))

    # -------------------------------------------------------------------------
    # 5. Assets created on every posting path
    # -------------------------------------------------------------------------

    def test_asset_created_when_posted_from_list(self):
        bill = self._create_bill()
        with freeze_time('2025-01-20'):
            wizard = self.env['validate.account.move'].with_context(
                active_model='account.move', active_ids=bill.ids).create({})
            wizard.validate_move()
        self.assertEqual(bill.state, 'posted')
        self.assertEqual(len(bill.asset_ids), 1)
        self.assertEqual(bill.asset_ids.state, 'open')
        self.assertEqual(bill.asset_ids.first_depreciation_manual_date, date(2025, 1, 31))

    def test_asset_created_by_auto_post(self):
        bill = self._create_bill(auto_post='at_date')
        with freeze_time('2025-01-20'):
            # what the auto-post job does
            self.env['account.move'].search([
                ('state', '=', 'draft'), ('auto_post', '!=', 'no'), ('date', '<=', fields.Date.today()),
                ('id', '=', bill.id),
            ])._post()
        self.assertEqual(bill.state, 'posted')
        self.assertEqual(len(bill.asset_ids), 1)

    def test_asset_created_once(self):
        bill = self._create_bill()
        with freeze_time('2025-01-20'):
            bill.action_post()
            bill._post()  # posting again (e.g. another override) does not duplicate the asset
        self.assertEqual(len(bill.asset_ids), 1)

    # -------------------------------------------------------------------------
    # 3. Multi-company
    # -------------------------------------------------------------------------

    def test_multi_company_isolation(self):
        company_b_data = self.setup_other_company(name='Asset Company B')
        company_b = company_b_data['company']
        asset = self._create_asset()
        user_b = new_test_user(
            self.env, login='asset_user_b', groups='account.group_account_manager',
            company_id=company_b.id, company_ids=[Command.set(company_b.ids)])
        Asset = self.env['account.asset.asset'].with_user(user_b)
        self.assertFalse(Asset.search([('id', '=', asset.id)]))
        self.assertFalse(self.env['account.asset.category'].with_user(user_b).search([('id', '=', self.category.id)]))
        with self.assertRaises(AccessError):
            asset.with_user(user_b).read(['name'])

        # an asset of company B cannot use a category (journal, accounts) of company A
        with self.assertRaises(UserError):
            self.env['account.asset.asset'].with_company(company_b).create({
                'name': 'Wrong company',
                'category_id': self.category.id,
                'value': 100.0,
                'company_id': company_b.id,
            })
        # nor a category of company B the journal of company A
        with self.assertRaises(UserError):
            self.category.copy({'company_id': company_b.id})

    # -------------------------------------------------------------------------
    # 4. Disposal
    # -------------------------------------------------------------------------

    def test_disposal_posted_and_not_in_future(self):
        asset = self._create_asset(validate_on='2025-03-31')
        with freeze_time('2025-03-31'), self.assertRaises(UserError):
            asset.set_to_close(disposal_date=date(2025, 6, 30))
        self.assertEqual(asset.state, 'open')
        with freeze_time('2025-03-31'):
            asset.set_to_close(disposal_date=date(2025, 3, 31))
        self.assertEqual(asset.state, 'close')
        self.assertEqual(asset.disposal_move_id.state, 'posted')
