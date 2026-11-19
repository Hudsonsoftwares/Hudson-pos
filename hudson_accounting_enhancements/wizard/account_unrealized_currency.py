from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountUnrealizedCurrencyWizard(models.TransientModel):
    """
    Unrealized Currency Gains/Losses Report (read only).

    The amounts come from the currency revaluation engine of om_currency_revaluation, which also posts the
    adjustment entries: for each foreign currency item, what was still open on the as-of date (the matchings made
    afterwards are not deducted) is valued at the rate of that date:
    - the open items of every reconcilable account (receivables, payables, advances, intercompany...),
    - the whole balance of the accounts held in a foreign currency (bank, cash...),
    - the revaluation entries still in effect on that date, so that the adjustment shown is what is left to post.

    Positive = Unrealized Gain, Negative = Unrealized Loss.
    """
    _name = 'account.unrealized.currency.wizard'
    _description = 'Unrealized Currency Gains/Losses'

    as_of_date = fields.Date(
        string='As Of Date',
        required=True,
        default=fields.Date.context_today,
        help='Compute unrealized gains/losses using exchange rates as of this date.',
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    # only the posted entries are revalued; kept for the dynamic report, which sends it
    target_move = fields.Selection(
        [('posted', 'All Posted Entries'), ('all', 'All Entries')],
        string='Target Moves',
        required=True,
        default='posted',
    )

    def _compute_unrealized_data(self):
        self.ensure_one()
        if self.company_id not in self.env.companies:
            raise UserError(_("You are not allowed to access this company's data."))
        company = self.company_id
        as_of = self.as_of_date
        engine = self.env['currency.revaluation'].new({'company_id': company.id, 'date': as_of})

        by_currency = {}
        for item in engine._get_revaluation_items():
            curr = item['currency']
            if curr not in by_currency:
                by_currency[curr] = {
                    'currency_name': curr.name,
                    'currency_symbol': curr.symbol,
                    # units of the company currency for 1 unit of the foreign currency
                    'rate': curr._convert(1.0, company.currency_id, company, as_of, round=False),
                    'items': [],
                    'total_original': 0.0,
                    'total_current': 0.0,
                    'total_gain_loss': 0.0,
                }
            line = item['line']
            amount_foreign = item['amount_currency']
            original_company = item['balance']
            current_company = engine._get_closing_value(amount_foreign, curr) if amount_foreign else 0.0
            unrealized = current_company - original_company
            group = by_currency[curr]
            group['items'].append({
                'partner': line.partner_id.name or '',
                'date': line.date,
                'ref': (_('Revaluation: %s', line.move_id.name) if item['is_revaluation']
                        else line.move_id.name or line.name or ''),
                'account': line.account_id.display_name,
                'amount_foreign': amount_foreign,
                'original_company': original_company,
                'current_rate': round(group['rate'], 6),
                'current_company': current_company,
                'unrealized': unrealized,
            })
            group['total_original'] += original_company
            group['total_current'] += current_company
            group['total_gain_loss'] += unrealized

        results = [group for group in by_currency.values() if group['items']]
        return {
            'as_of_date': as_of,
            'company': company.id,
            'results': results,
            'total_unrealized': sum(group['total_gain_loss'] for group in results),
        }

    def action_print_report(self):
        self.ensure_one()
        data = self._compute_unrealized_data()
        return self.env.ref(
            'hudson_accounting_enhancements.action_report_unrealized_currency'
        ).report_action(self, data={'form': data})

    def check_report(self):
        return self.action_print_report()


class AccountUnrealizedCurrencyAdjustmentWizard(models.TransientModel):
    """ "Make Adjustment Entry" of the Unrealized Currencies report, as in Odoo: a preview of the adjustment, posted
    by the currency revaluation engine of om_currency_revaluation, the one posting engine. The entry is always
    reversed (by default on the next day) and only what is left to adjust on the date is posted. """
    _name = 'account.unrealized.currency.adjustment.wizard'
    _description = 'Make Adjustment Entry'

    def _default_journal(self):
        company = self.env.company
        return (
            company.currency_reval_journal_id
            or self.env['account.journal'].search([('company_id', '=', company.id), ('code', '=', 'EXCH')], limit=1)
            or self.env['account.journal'].search([('company_id', '=', company.id), ('type', '=', 'general')], limit=1)
        )

    def _default_expense_account(self):
        company = self.env.company
        return (
            company.currency_reval_loss_account_id
            or company.expense_currency_exchange_account_id
            or self.env['account.account'].search([('company_ids', 'in', company.id), ('account_type', '=', 'expense')], limit=1)
        )

    def _default_income_account(self):
        company = self.env.company
        return (
            company.currency_reval_gain_account_id
            or company.income_currency_exchange_account_id
            or self.env['account.account'].search([('company_ids', 'in', company.id), ('account_type', '=', 'income_other')], limit=1)
            or self.env['account.account'].search([('company_ids', 'in', company.id), ('account_type', '=', 'income')], limit=1)
        )

    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=True,
        domain="[('company_id', '=', company_id), ('type', '=', 'general')]",
        default=_default_journal,
    )
    expense_account_id = fields.Many2one(
        'account.account',
        string='Expense Account',
        required=True,
        check_company=True,
        domain="[('account_type', '=', 'expense')]",
        default=_default_expense_account,
    )
    income_account_id = fields.Many2one(
        'account.account',
        string='Income Account',
        required=True,
        check_company=True,
        domain="[('account_type', 'in', ['income', 'income_other'])]",
        default=_default_income_account,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
    )
    reversal_date = fields.Date(
        string='Reversal Date',
        required=True,
        compute='_compute_reversal_date', store=True, readonly=False, precompute=True,
        help="The adjustment entry is always reversed, by default on the day after its date.",
    )
    header_note = fields.Char(string='Section Note', compute='_compute_header_note')
    line_ids = fields.One2many(
        'account.unrealized.currency.adjustment.line',
        'wizard_id',
        string='Adjustment Lines',
        compute='_compute_lines',
    )

    @api.depends('date')
    def _compute_reversal_date(self):
        for wiz in self:
            wiz.reversal_date = wiz.date and wiz.date + relativedelta(days=1)

    @api.depends('date')
    def _compute_header_note(self):
        for wiz in self:
            if wiz.date:
                df = wiz.date.strftime('%d/%m/%Y')
                wiz.header_note = f"{df}, Foreign currencies adjustment entry as of {df}"
            else:
                wiz.header_note = ''

    def _custom_rates_context(self):
        """ The rates typed in the Exchange Rates popover of the report, for the revaluation engine """
        return {'currency_reval_rates': self.env.context.get('unrealized_custom_rates') or {}}

    def _get_engine_values(self):
        self.ensure_one()
        return {
            'company_id': self.company_id.id,
            'date': self.date,
            'reversal_date': self.reversal_date,
            'journal_id': self.journal_id.id,
            'gain_account_id': self.income_account_id.id,
            'loss_account_id': self.expense_account_id.id,
        }

    @api.depends('date', 'company_id', 'expense_account_id', 'income_account_id')
    def _compute_lines(self):
        for wiz in self:
            if not wiz.date or not wiz.company_id:
                wiz.line_ids = [(5, 0, 0)]
                continue
            engine = self.env['currency.revaluation'].with_context(**wiz._custom_rates_context()).new({
                'company_id': wiz.company_id.id, 'date': wiz.date,
            })
            company_currency = wiz.company_id.currency_id
            new_lines = []
            for value in engine._get_revaluation_values():
                currency = self.env['res.currency'].browse(value['currency_id'])
                adjustment = value['adjustment']
                rate = value['amount_currency'] / value['revalued'] if value['revalued'] else 0.0
                label = _("Provision for %(currency)s (1 %(company_currency)s = %(rate)s %(currency)s)",
                          currency=currency.name, company_currency=company_currency.name, rate=f"{rate:.6g}")
                counterpart = wiz.income_account_id if adjustment > 0 else wiz.expense_account_id
                new_lines += [
                    (0, 0, {
                        'account_id': value['account_id'],
                        'name': label,
                        'debit': max(adjustment, 0.0),
                        'credit': max(-adjustment, 0.0),
                        'currency_id': company_currency.id,
                    }),
                    (0, 0, {
                        'account_id': counterpart.id,
                        'name': (_("Income Provision for %s", currency.name) if adjustment > 0
                                 else _("Expense Provision for %s", currency.name)),
                        'debit': max(-adjustment, 0.0),
                        'credit': max(adjustment, 0.0),
                        'currency_id': company_currency.id,
                    }),
                ]
            wiz.line_ids = [(5, 0, 0)] + new_lines

    def action_create_entry(self):
        """ Post the adjustment and its reversal with the currency revaluation engine """
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("There are no adjustment lines to create an entry for."))
        if not self.reversal_date or self.reversal_date <= self.date:
            raise UserError(_("The reversal date must be after the adjustment date."))
        engine = self.env['currency.revaluation'].with_context(**self._custom_rates_context()).create(
            self._get_engine_values())
        move, reversal = engine._create_revaluation_entries()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Adjustment Entries'),
            'res_model': 'account.move',
            'domain': [('id', 'in', (move | reversal).ids)],
            'view_mode': 'list,form',
            'views': [[False, 'list'], [False, 'form']],
        }


class AccountUnrealizedCurrencyAdjustmentLine(models.TransientModel):
    _name = 'account.unrealized.currency.adjustment.line'
    _description = 'Adjustment Entry Line'

    wizard_id = fields.Many2one('account.unrealized.currency.adjustment.wizard', ondelete='cascade')
    account_id = fields.Many2one('account.account', string='Account', required=True)
    partner_id = fields.Many2one('res.partner', string='Partner')
    name = fields.Char(string='Label', required=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    debit = fields.Monetary(string='Debit', currency_field='currency_id')
    credit = fields.Monetary(string='Credit', currency_field='currency_id')
