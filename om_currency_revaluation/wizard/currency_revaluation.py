import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL
from odoo.tools.misc import format_date

_logger = logging.getLogger(__name__)


class CurrencyRevaluation(models.TransientModel):
    """ Restate the open foreign currency balances at the rate of a date, as Odoo does it:

    - the reconcilable accounts (receivables, payables, advances, intercompany...) are revalued for what was still
      open on each journal item on the date: the amounts matched afterwards are not deducted;
    - the accounts held in a foreign currency (bank, cash...) for their whole balance.

    The adjustment entry is always reversed, by default on the next day: its lines on the reconcilable accounts are
    matched with the reversal, so they never stay open on a customer or a vendor. The revaluation entries still in
    effect on the date (posted up to that date and not reversed by then) count in the balance of the books, so a
    revaluation run twice, or after an entry that was never reversed, only posts what is left to adjust.
    """
    _name = 'currency.revaluation'
    _description = 'Currency Revaluation'

    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    company_currency_id = fields.Many2one(related='company_id.currency_id')
    date = fields.Date(
        string='Revaluation Date', required=True, default=fields.Date.context_today,
        help="The open balances are revalued at the rate of this date, usually the last day of a period.")
    currency_ids = fields.Many2many(
        'res.currency', string='Currencies',
        help="Leave empty to revalue every currency other than the one of the company.")
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True, check_company=True,
        compute='_compute_from_company', store=True, readonly=False, precompute=True,
        domain="[('type', '=', 'general')]")
    gain_account_id = fields.Many2one(
        'account.account', string='Unrealized Gain Account', required=True, check_company=True,
        compute='_compute_from_company', store=True, readonly=False, precompute=True)
    loss_account_id = fields.Many2one(
        'account.account', string='Unrealized Loss Account', required=True, check_company=True,
        compute='_compute_from_company', store=True, readonly=False, precompute=True)
    reversal_date = fields.Date(
        string='Reversal Date', required=True, compute='_compute_reversal_date', store=True, readonly=False,
        precompute=True,
        help="The adjustment is always reversed, by default on the day after the revaluation: nothing is gained or "
             "lost until the items are settled.")
    line_ids = fields.One2many(
        'currency.revaluation.line', 'revaluation_id', string='Revaluation',
        compute='_compute_line_ids', store=True)
    adjustment = fields.Monetary(
        string='Adjustment', compute='_compute_line_ids', store=True, currency_field='company_currency_id')

    @api.depends('company_id')
    def _compute_from_company(self):
        for wizard in self:
            company = wizard.company_id
            wizard.journal_id = company.currency_reval_journal_id
            wizard.gain_account_id = company.currency_reval_gain_account_id
            wizard.loss_account_id = company.currency_reval_loss_account_id

    @api.depends('date')
    def _compute_reversal_date(self):
        for wizard in self:
            wizard.reversal_date = wizard.date and wizard.date + relativedelta(days=1)

    @api.depends('date', 'currency_ids', 'company_id')
    def _compute_line_ids(self):
        for wizard in self:
            values = wizard._get_revaluation_values()
            wizard.line_ids = [(5, 0, 0)] + [(0, 0, value) for value in values]
            wizard.adjustment = sum(value['adjustment'] for value in values)

    # -------------------------------------------------------------------------
    # Revaluation
    # -------------------------------------------------------------------------

    def _base_domain(self):
        self.ensure_one()
        return [
            ('parent_state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
            ('date', '<=', self.date),
        ]

    def _revaluation_domain(self):
        """ The items in a foreign currency of the reconcilable accounts that were open on the date of the
        revaluation: not matched, or matched afterwards """
        self.ensure_one()
        domain = self._base_domain() + [
            ('account_id.reconcile', '=', True),
            ('currency_id', '!=', self.company_currency_id.id),
            ('amount_currency', '!=', 0),
            ('move_id.currency_reval_date', '=', False),
            '|', ('reconciled', '=', False),
            '|', ('matched_debit_ids.max_date', '>', self.date), ('matched_credit_ids.max_date', '>', self.date),
        ]
        if self.currency_ids:
            domain.append(('currency_id', 'in', self.currency_ids.ids))
        return domain

    def _foreign_account_domain(self):
        """ Every item of the accounts held in a foreign currency, such as the bank accounts, the revaluations
        already posted on them included """
        self.ensure_one()
        domain = self._base_domain() + [
            ('account_id.reconcile', '=', False),
            ('account_id.currency_id', '!=', False),
            ('account_id.currency_id', '!=', self.company_currency_id.id),
        ]
        if self.currency_ids:
            domain.append(('account_id.currency_id', 'in', self.currency_ids.ids))
        return domain

    def _get_revaluation_items(self):
        """ What is exposed to the exchange rate on the date of the revaluation, journal item by journal item.

        :return: list of dicts {line, account, currency, amount_currency, balance, is_revaluation}: the amounts in
            the foreign currency and in the currency of the company held in the books for that item on the date
        """
        self.ensure_one()
        if not self.date or not self.company_id:
            return []
        company_currency = self.company_currency_id
        AccountMoveLine = self.env['account.move.line'].sudo()
        items = []
        open_items = AccountMoveLine.search(self._revaluation_domain(), order='date, id')
        for line, residual_currency, residual_balance in self._residuals_at_date(open_items):
            if line.currency_id.is_zero(residual_currency) and company_currency.is_zero(residual_balance):
                continue
            items.append({
                'line': line, 'account': line.account_id, 'currency': line.currency_id,
                'amount_currency': residual_currency, 'balance': residual_balance, 'is_revaluation': False,
            })
        for line in AccountMoveLine.search(self._foreign_account_domain(), order='date, id'):
            items.append({
                'line': line, 'account': line.account_id, 'currency': line.account_id.currency_id,
                'amount_currency': line.amount_currency, 'balance': line.balance,
                'is_revaluation': bool(line.move_id.currency_reval_date
                                       or line.move_id.reversed_entry_id.currency_reval_date),
            })
        items += self._get_revaluations_in_effect(items)
        return items

    def _get_revaluations_in_effect(self, items):
        """ The lines of the revaluation entries and of their reversals dated up to the date of the revaluation, on
        the reconcilable accounts: what the earlier revaluations still add to the open items on that date.

        :param items: the open items, to find the currency of the lines posted in the currency of the company by
            the earlier versions of this module
        """
        self.ensure_one()
        company_currency = self.company_currency_id
        lines = self.env['account.move.line'].sudo().search(self._base_domain() + [
            ('account_id.reconcile', '=', True),
            '|', ('move_id.currency_reval_date', '!=', False),
            ('move_id.reversed_entry_id.currency_reval_date', '!=', False),
        ], order='date, id')
        currencies_by_account = {}
        for item in items:
            currencies_by_account.setdefault(item['account'], set()).add(item['currency'])
        result = []
        for line in lines:
            if company_currency.is_zero(line.balance):
                continue
            currency = line.currency_id
            if currency == company_currency:
                candidates = currencies_by_account.get(line.account_id, set())
                if len(candidates) != 1:
                    if candidates:
                        _logger.warning("Currency revaluation: the currency of %s on %s is unknown, it is left out.",
                                        line.move_id.display_name, line.account_id.display_name)
                    continue
                currency = next(iter(candidates))
            if self.currency_ids and currency not in self.currency_ids:
                continue
            result.append({
                'line': line, 'account': line.account_id, 'currency': currency,
                'amount_currency': 0.0, 'balance': line.balance, 'is_revaluation': True,
            })
        return result

    def _get_closing_value(self, amount, currency):
        """ The amount in the currency of the company at the rate of the date, or at the rate given in the context
        key `currency_reval_rates`: {currency id: units of the currency for 1 unit of the company currency} """
        self.ensure_one()
        custom_rates = self.env.context.get('currency_reval_rates') or {}
        rate = custom_rates.get(currency.id) or custom_rates.get(str(currency.id))
        try:
            rate = float(rate or 0.0)
        except (TypeError, ValueError):
            rate = 0.0
        if rate > 0:
            return self.company_currency_id.round(amount / rate)
        return currency._convert(amount, self.company_currency_id, self.company_id, self.date)

    def _get_revaluation_values(self):
        """ The amounts to adjust, one per account and currency.

        :return: list of the values of `currency.revaluation.line`
        """
        self.ensure_one()
        company_currency = self.company_currency_id
        groups = {}
        for item in self._get_revaluation_items():
            group = groups.setdefault((item['account'], item['currency']), {'amount_currency': 0.0, 'balance': 0.0})
            group['amount_currency'] += item['amount_currency']
            group['balance'] += item['balance']
        values = []
        for (account, currency), group in groups.items():
            if currency.is_zero(group['amount_currency']) and company_currency.is_zero(group['balance']):
                continue
            revalued = self._get_closing_value(group['amount_currency'], currency)
            adjustment = company_currency.round(revalued - group['balance'])
            if company_currency.is_zero(adjustment):
                continue
            values.append({
                'account_id': account.id,
                'currency_id': currency.id,
                'amount_currency': group['amount_currency'],
                'balance': group['balance'],
                'revalued': revalued,
                'adjustment': adjustment,
            })
        return sorted(values, key=lambda value: (value['currency_id'], value['account_id']))

    def _residuals_at_date(self, lines):
        """ What was left on each journal item of a reconcilable account on the date of the revaluation: the amounts
        matched afterwards are not deducted, so that a revaluation of a past period stays the same once the invoices
        are paid.

        :return: [(line, residual in its currency, residual in the currency of the company)]
        """
        self.ensure_one()
        matched = self._matched_at_date(lines)
        for line in lines:
            paid_currency, paid_balance = matched.get(line.id, (0.0, 0.0))
            sign = 1 if line.balance > 0 or (not line.balance and line.amount_currency > 0) else -1
            yield line, line.amount_currency - sign * paid_currency, line.balance - sign * paid_balance

    def _matched_at_date(self, lines):
        """ :return: {line id: (amount matched in the currency of the line, in the currency of the company)} on the
        date of the revaluation, the amounts always positive """
        if not lines:
            return {}
        rows = self.env.execute_query(SQL(
            """
              SELECT part.debit_move_id AS line_id,
                     SUM(part.debit_amount_currency) AS amount_currency,
                     SUM(part.amount) AS balance
                FROM account_partial_reconcile part
                JOIN account_move_line credit_line ON credit_line.id = part.credit_move_id
                JOIN account_move_line debit_line ON debit_line.id = part.debit_move_id
               WHERE part.debit_move_id = ANY(%(ids)s)
                 AND GREATEST(credit_line.date, debit_line.date) <= %(date)s
            GROUP BY part.debit_move_id
               UNION ALL
              SELECT part.credit_move_id AS line_id,
                     SUM(part.credit_amount_currency) AS amount_currency,
                     SUM(part.amount) AS balance
                FROM account_partial_reconcile part
                JOIN account_move_line credit_line ON credit_line.id = part.credit_move_id
                JOIN account_move_line debit_line ON debit_line.id = part.debit_move_id
               WHERE part.credit_move_id = ANY(%(ids)s)
                 AND GREATEST(credit_line.date, debit_line.date) <= %(date)s
            GROUP BY part.credit_move_id
            """,
            ids=lines.ids, date=self.date,
        ))
        matched = {}
        for line_id, amount_currency, balance in rows:
            # a line both debit and credit side of partials (rare) adds up
            previous_currency, previous_balance = matched.get(line_id, (0.0, 0.0))
            matched[line_id] = (previous_currency + (amount_currency or 0.0), previous_balance + (balance or 0.0))
        return matched

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_revalue(self):
        self.ensure_one()
        move, _reversal = self._create_revaluation_entries()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Currency Revaluation'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'views': [[False, 'form']],
        }

    def _create_revaluation_entries(self):
        """ Post the adjustment entry and its reversal, as Odoo does: the revaluation is always reversed.

        :return: (adjustment entry, reversal)
        """
        self.ensure_one()
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_("Only the accounting managers can post a currency revaluation."))
        if not self.reversal_date or self.reversal_date <= self.date:
            raise UserError(_("The reversal date must be after the revaluation date."))
        values = self._get_revaluation_values()
        if not values:
            raise UserError(_(
                "Nothing is left to revalue in a foreign currency on %s: the open balances are already at the rate "
                "of that date, the revaluations posted on it included.", format_date(self.env, self.date)))
        move = self.env['account.move'].create(self._get_move_values(values))
        move.action_post()
        reversal = move._reverse_moves(default_values_list=[{
            'date': self.reversal_date,
            'ref': _('Reversal of the currency revaluation of %s', format_date(self.env, self.date)),
        }])
        # posting the reversal matches it with the adjustment on the reconcilable accounts: the adjustment never
        # stays open on a customer or a vendor
        reversal.action_post()
        return move, reversal

    def _get_move_values(self, values):
        """ :return: the values of the adjustment entry: the difference on each account, against the unrealized
        gain and loss accounts """
        self.ensure_one()
        company_currency = self.company_currency_id
        line_values = []
        gain = loss = 0.0
        for value in values:
            adjustment = value['adjustment']
            currency = self.env['res.currency'].browse(value['currency_id'])
            if adjustment > 0:
                gain += adjustment
            else:
                loss -= adjustment
            line_values.append((0, 0, {
                'name': _('Revaluation of %(amount)s at the rate of %(date)s',
                          amount=currency.format(value['amount_currency']),
                          date=format_date(self.env, self.date)),
                'account_id': value['account_id'],
                # no partner: the adjustment is not an item to collect or to pay
                'partner_id': False,
                # the amount in the foreign currency does not change: only what it is worth does
                'currency_id': currency.id,
                'amount_currency': 0.0,
                'balance': adjustment,
            }))
        for amount, account in ((gain, self.gain_account_id), (loss, self.loss_account_id)):
            if company_currency.is_zero(amount):
                continue
            balance = -amount if account == self.gain_account_id else amount
            line_values.append((0, 0, {
                'name': _('Unrealized gain') if account == self.gain_account_id else _('Unrealized loss'),
                'account_id': account.id,
                'currency_id': account.currency_id.id or company_currency.id,
                'amount_currency': 0.0 if account.currency_id and account.currency_id != company_currency
                else balance,
                'balance': balance,
            }))
        return {
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'company_id': self.company_id.id,
            'date': self.date,
            'currency_reval_date': self.date,
            'ref': _('Currency revaluation of %s', format_date(self.env, self.date)),
            'line_ids': line_values,
        }


class CurrencyRevaluationLine(models.TransientModel):
    _name = 'currency.revaluation.line'
    _description = 'Currency Revaluation Line'
    _order = 'currency_id, account_id'

    revaluation_id = fields.Many2one('currency.revaluation', required=True, ondelete='cascade')
    company_currency_id = fields.Many2one(
        related='revaluation_id.company_currency_id', string='Company Currency')
    account_id = fields.Many2one('account.account', string='Account', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    amount_currency = fields.Monetary(string='Open Amount', currency_field='currency_id', readonly=True)
    balance = fields.Monetary(string='In the Books', currency_field='company_currency_id', readonly=True)
    revalued = fields.Monetary(string='At the Closing Rate', currency_field='company_currency_id', readonly=True)
    adjustment = fields.Monetary(string='Adjustment', currency_field='company_currency_id', readonly=True)
