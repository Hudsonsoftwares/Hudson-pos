import logging
import re

from odoo import api, fields, models, Command, _
from odoo.exceptions import LockError, UserError

_logger = logging.getLogger(__name__)

# a token of the transaction label worth looking for in the references of the open items:
# at least 4 characters with at least one digit, e.g. INV/2026/00012, RF18539007547034 or 000123
REFERENCE_TOKEN = re.compile(r'[A-Za-z0-9][A-Za-z0-9/\-_.]{2,}[A-Za-z0-9]')

SCORE_AMOUNT = 50
SCORE_REFERENCE = 40
SCORE_PARTNER = 20
SCORE_PARTNER_NAME = 10
SCORE_WRONG_DIRECTION = -30
SCORE_SUGGESTED = 60
SCORE_PERFECT = 90


class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    om_auto_processed = fields.Boolean(
        string='Automatic Reconciliation Tried', copy=False, default=False,
        help='Technical: the automatic reconciliation already looked at this transaction.')

    @api.model_create_multi
    def create(self, vals_list):
        st_lines = super().create(vals_list)
        if any(st_lines.company_id.mapped('om_reconcile_auto')):
            cron = self.env.ref('om_account_reconcile.ir_cron_auto_reconcile', raise_if_not_found=False)
            if cron:
                cron._trigger()
        return st_lines

    def om_action_reconcile(self):
        """ Open the reconciliation screen on this transaction. """
        self.ensure_one()
        return self.journal_id.om_action_open_bank_reconciliation(state='all', st_line_id=self.id)

    # -------------------------------------------------------------------------
    # Access
    # -------------------------------------------------------------------------

    def _om_check_access(self):
        # the same users as the ones allowed to change bank transactions
        if not self.env.su and not self.env.user.has_group('account.group_account_basic'):
            raise UserError(_('Only accountants can reconcile transactions.'))

    # -------------------------------------------------------------------------
    # Amounts
    # -------------------------------------------------------------------------

    def _om_currencies(self):
        """ :return: (transaction currency, company currency) """
        _trans_amount, trans_currency, _journal_amount, _journal_currency, _company_amount, company_currency = \
            self._get_accounting_amounts_and_currencies()
        return trans_currency, company_currency

    def _om_rate(self):
        """ Rate of the bank between the transaction currency and the company currency. """
        trans_amount, _trans_currency, _journal_amount, _journal_currency, company_amount, _company_currency = \
            self._get_accounting_amounts_and_currencies()
        return abs(trans_amount) / abs(company_amount) if company_amount else 1.0

    def _om_to_transaction_amount(self, currency, amount_currency, balance):
        """ Express a journal item amount in the transaction currency, using the bank rate.

        An item in a foreign currency (other than the one of the transaction) is worth its foreign amount
        at the date of the transaction, not its historical value in company currency: the gap between both
        is the realized exchange difference booked when the items are reconciled. Using the historical
        value would match only a part of a foreign invoice paid by a transaction in company currency and
        leave the exchange difference on the suspense account.
        """
        trans_currency, company_currency = self._om_currencies()
        if currency == trans_currency:
            return amount_currency
        if currency != company_currency and not currency.is_zero(amount_currency):
            balance = company_currency.round(
                currency._convert(amount_currency, company_currency, self.company_id, self.date))
        return self._prepare_counterpart_amounts_using_st_line_rate(
            company_currency, balance, balance)['amount_currency']

    def _om_booked_transaction_amount(self, currency, amount_currency, balance):
        """ Value in transaction currency of a journal item written on the transaction itself.

        When the transaction is in company currency, what an item of the transaction is worth is what it is
        booked at: its balance. Converting its foreign amount again at the rate of the day would differ by a
        rounding from the balance actually written, and that difference would be left on the suspense account
        as an amount in company currency whose balance is zero, which Odoo cannot keep balanced.
        """
        trans_currency, company_currency = self._om_currencies()
        if trans_currency == company_currency:
            return balance
        return self._om_to_transaction_amount(currency, amount_currency, balance)

    # -------------------------------------------------------------------------
    # Lines of a reconciliation
    # -------------------------------------------------------------------------

    def _om_prepare_match_line_vals(self, aml, amount=None):
        """ Counterpart of an open journal item.

        :param amount: part of the residual amount of `aml` to reconcile, in the currency of `aml` and positive;
                       the whole residual amount by default.
        """
        self.ensure_one()
        trans_currency, company_currency = self._om_currencies()
        residual_currency = aml.amount_residual_currency
        residual = aml.amount_residual
        if amount is not None and aml.currency_id.compare_amounts(abs(amount), abs(residual_currency)) < 0:
            ratio = abs(amount) / abs(residual_currency)
            residual_currency = aml.currency_id.round(residual_currency * ratio)
            residual = company_currency.round(residual * ratio)

        if aml.currency_id == trans_currency:
            currency = trans_currency
            amounts = self._prepare_counterpart_amounts_using_st_line_rate(
                trans_currency, -residual, -residual_currency)
        elif aml.currency_id == company_currency:
            currency = trans_currency
            amounts = self._prepare_counterpart_amounts_using_st_line_rate(company_currency, -residual, -residual)
        else:
            # an item in a third currency keeps its currency, converted at the date of the transaction
            currency = aml.currency_id
            amounts = {
                'amount_currency': -residual_currency,
                'balance': company_currency.round(
                    aml.currency_id._convert(-residual_currency, company_currency, self.company_id, self.date)),
            }
        return {
            'name': aml.name or aml.move_id.name,
            'account_id': aml.account_id.id,
            'partner_id': aml.partner_id.id,
            'currency_id': currency.id,
            **amounts,
        }

    def _om_prepare_writeoff_lines_vals(self, writeoff):
        """ Journal items of a counterpart typed by the user or coming from a reconciliation model.

        :param writeoff: dictionary with
            account_id, amount (transaction currency, positive for a debit), label, partner_id,
            tax_ids, tax_included, analytic_distribution, reconcile_model_id
        """
        self.ensure_one()
        AccountTax = self.env['account.tax']
        company = self.company_id
        trans_currency, _company_currency = self._om_currencies()
        amount = writeoff['amount']
        account = self.env['account.account'].browse(writeoff['account_id'])
        if account in (self.journal_id.suspense_account_id | self.journal_id.default_account_id):
            # a counterpart on the suspense account reconciles nothing (it is the account the transaction waits
            # on until it is reconciled) and one on the account of the bank itself cancels the transaction
            raise UserError(_(
                'The account %(account)s of the journal %(journal)s cannot be used as a counterpart: choose the '
                'account the transaction must be booked on.',
                account=account.display_name, journal=self.journal_id.display_name))
        partner = self.env['res.partner'].browse(writeoff.get('partner_id') or [])
        taxes = self.env['account.tax'].browse(writeoff.get('tax_ids') or [])
        analytic_distribution = writeoff.get('analytic_distribution') or False
        common = {
            'name': writeoff.get('label') or self.payment_ref,
            'partner_id': partner.id,
            'currency_id': trans_currency.id,
            'reconcile_model_id': writeoff.get('reconcile_model_id') or False,
        }
        if not taxes:
            amounts = self._prepare_counterpart_amounts_using_st_line_rate(trans_currency, None, amount)
            return [{**common, 'account_id': account.id, 'analytic_distribution': analytic_distribution, **amounts}]

        sign = 1 if amount > 0 else -1
        tax_use = taxes[0].type_tax_use
        base_line = AccountTax._prepare_base_line_for_taxes_computation(
            None,
            price_unit=abs(amount),
            quantity=1.0,
            tax_ids=taxes,
            currency_id=trans_currency,
            special_mode='total_included' if writeoff.get('tax_included') else 'total_excluded',
            rate=self._om_rate(),
            sign=sign,
            is_refund=(tax_use == 'sale' and sign > 0) or (tax_use == 'purchase' and sign < 0),
            partner_id=partner,
            account_id=account,
            analytic_distribution=analytic_distribution,
        )
        base_lines = [base_line]
        AccountTax._add_tax_details_in_base_lines(base_lines, company)
        AccountTax._round_base_lines_tax_details(base_lines, company)
        AccountTax._add_accounting_data_in_base_lines_tax_details(base_lines, company)
        tax_results = AccountTax._prepare_tax_lines(base_lines, company)

        lines_vals = []
        for _base_line, to_update in tax_results['base_lines_to_update']:
            lines_vals.append({
                **common,
                'account_id': account.id,
                'analytic_distribution': analytic_distribution,
                'tax_ids': [Command.set(taxes.ids)],
                'tax_tag_ids': to_update['tax_tag_ids'],
                'amount_currency': to_update['amount_currency'],
                'balance': to_update['balance'],
            })
        for tax_line_vals in tax_results['tax_lines_to_add']:
            lines_vals.append({
                **tax_line_vals,
                **common,
                'name': self.env['account.tax.repartition.line'].browse(
                    tax_line_vals['tax_repartition_line_id']).tax_id.name,
            })
        return lines_vals

    def _om_prepare_proposal_lines(self, proposal):
        """ :return: list of (journal item values, matched journal item or empty recordset) """
        self.ensure_one()
        AccountMoveLine = self.env['account.move.line']
        trans_currency, _company_currency = self._om_currencies()
        lines = []
        # what the counterparts still have to cover, as a journal item amount in transaction currency
        to_cover = -self.amount_residual
        for match in proposal.get('matches') or []:
            aml = AccountMoveLine.browse(match['aml_id'])
            amount = match.get('amount')
            aml_amount = self._om_to_transaction_amount(aml.currency_id, aml.amount_residual_currency,
                                                        aml.amount_residual)
            fit_to_transaction = False
            if amount is None and not trans_currency.is_zero(aml_amount) and (aml_amount > 0) == (to_cover > 0) \
                    and trans_currency.compare_amounts(abs(aml_amount), abs(to_cover)) > 0:
                # by default an item is only matched up to the amount of the transaction
                amount = aml.currency_id.round(abs(aml.amount_residual_currency) * abs(to_cover) / abs(aml_amount))
                fit_to_transaction = True
            vals = self._om_prepare_match_line_vals(aml, amount)
            if fit_to_transaction and vals['currency_id'] != trans_currency.id:
                # an item in another foreign currency covering the rest of the transaction: its value in company
                # currency is what the bank paid, otherwise a rounding difference stays on the suspense account
                vals['balance'] = self._prepare_counterpart_amounts_using_st_line_rate(
                    trans_currency, None, -to_cover)['balance']
            to_cover += self._om_booked_transaction_amount(
                self.env['res.currency'].browse(vals['currency_id']), vals['amount_currency'], vals['balance'])
            lines.append((vals, aml))
        for writeoff in proposal.get('writeoffs') or []:
            if self.company_id.currency_id.is_zero(writeoff.get('amount') or 0.0):
                continue
            lines.extend((vals, AccountMoveLine) for vals in self._om_prepare_writeoff_lines_vals(writeoff))
        return lines

    def _om_check_matches(self, amls):
        for aml in amls:
            if aml.reconciled:
                raise UserError(_('The journal item %s is already reconciled.', aml.display_name))
            if aml.parent_state != 'posted':
                raise UserError(
                    _('The journal entry %s must be posted before being reconciled.', aml.move_id.display_name))
            if (not aml.account_id.reconcile
                    and aml.account_id.account_type not in ('asset_cash', 'liability_credit_card')):
                raise UserError(_('The account %s does not allow reconciliation.', aml.account_id.display_name))
            if aml.move_id == self.move_id:
                raise UserError(_('A transaction cannot be matched with itself.'))
            if aml.company_id.root_id != self.company_id.root_id:
                raise UserError(_('The journal item %s belongs to another company.', aml.display_name))

    def _om_remaining(self, lines):
        """ Amount left on the suspense account once `lines` are added, in transaction and company currency.
        The existing counterparts of an earlier partial reconciliation are kept. """
        self.ensure_one()
        liquidity_lines, _suspense_lines, other_lines = self._seek_for_lines()
        trans_currency, company_currency = self._om_currencies()
        trans_amount, _trans_currency, _journal_amount, _journal_currency, company_amount, _company_currency = \
            self._get_accounting_amounts_and_currencies()
        remaining_trans = -trans_amount
        remaining_balance = -sum(liquidity_lines.mapped('balance'))
        for line in other_lines:
            remaining_trans -= self._om_booked_transaction_amount(line.currency_id, line.amount_currency, line.balance)
            remaining_balance -= line.balance
        for vals, _aml in lines:
            currency = self.env['res.currency'].browse(vals['currency_id'])
            remaining_trans -= self._om_booked_transaction_amount(currency, vals['amount_currency'], vals['balance'])
            remaining_balance -= vals['balance']
        return trans_currency.round(remaining_trans), company_currency.round(remaining_balance)

    # -------------------------------------------------------------------------
    # Reconciliation
    # -------------------------------------------------------------------------

    def _om_reconcile(self, proposal):
        """ Replace the suspense line of the transaction by the counterparts of `proposal` and reconcile them
        with the matched journal items. What is not covered stays on the suspense account.

        :param proposal: dictionary with
            partner_id: partner to set on the transaction (optional)
            matches: list of {'aml_id', 'amount' (optional, see `_om_prepare_match_line_vals`)}
            writeoffs: list of dictionaries (see `_om_prepare_writeoff_lines_vals`)
        """
        self.ensure_one()
        self._om_check_access()
        try:
            self.lock_for_update()
        except LockError:
            raise UserError(_('This transaction is being reconciled by someone else, please try again in a moment.'))
        if self.is_reconciled:
            raise UserError(_('The transaction %s is already reconciled.', self.display_name))

        if proposal.get('partner_id') and proposal['partner_id'] != self.partner_id.id:
            # setting the partner is part of this reconciliation: nothing else may reconcile the transaction
            # in between (an automatic matching would pay a second invoice with the same money)
            self.with_context(om_skip_auto_reconcile=True).partner_id = proposal['partner_id']
            self.invalidate_recordset(['is_reconciled', 'amount_residual'])
            if self.is_reconciled:
                raise UserError(_('The transaction %s was reconciled in the meantime.', self.display_name))

        lines = self._om_prepare_proposal_lines(proposal)
        if not lines:
            raise UserError(_('Select journal items to match or add a counterpart first.'))
        matched_amls = self.env['account.move.line'].union([aml for _vals, aml in lines])
        self._om_check_matches(matched_amls)

        self = self.with_context(skip_account_move_synchronization=True)
        _liquidity_lines, suspense_lines, _other_lines = self._seek_for_lines()
        move = self.move_id.with_context(
            skip_readonly_check=True,
            check_move_validity=False,
            force_delete=True,
            skip_account_move_synchronization=True,
        )
        AccountMoveLine = self.env['account.move.line'].with_context(
            skip_readonly_check=True,
            check_move_validity=False,
            skip_account_move_synchronization=True,
        )
        new_lines = AccountMoveLine.create([{**vals, 'move_id': move.id} for vals, _aml in lines])
        suspense_lines.with_context(
            force_delete=True,
            skip_readonly_check=True,
            check_move_validity=False,
            skip_account_move_synchronization=True,
        ).unlink()
        # What is left is read from the journal items as they were written, so that nothing is ever pushed
        # silently onto one of the counterparts: an amount the counterparts do not cover stays open on the
        # suspense account, a mere difference of rounding in company currency between the rate of the bank
        # and the counterparts in foreign currency is a realized exchange difference.
        trans_currency, company_currency = self._om_currencies()
        remaining_trans, remaining_balance = self._om_remaining([])
        if not trans_currency.is_zero(remaining_trans):
            AccountMoveLine.create({
                'move_id': move.id,
                'name': self.payment_ref,
                'account_id': self.journal_id.suspense_account_id.id,
                'partner_id': self.partner_id.id,
                'currency_id': trans_currency.id,
                'amount_currency': remaining_trans,
                'balance': remaining_balance,
            })
        elif not company_currency.is_zero(remaining_balance):
            company = self.company_id
            exchange_account = (company.expense_currency_exchange_account_id if remaining_balance > 0
                                else company.income_currency_exchange_account_id)
            if not exchange_account:
                raise UserError(_(
                    'Configure the gain and loss exchange difference accounts of the company %s first.',
                    company.display_name))
            AccountMoveLine.create({
                'move_id': move.id,
                'name': _('Exchange Difference'),
                'account_id': exchange_account.id,
                'partner_id': self.partner_id.id,
                'currency_id': trans_currency.id,
                'amount_currency': 0.0,
                'balance': remaining_balance,
            })

        # with `check_move_validity=False` (set above to write the lines one by one) `_check_balanced` checks
        # nothing: switch it back on, an unbalanced entry must never be saved
        with move.with_context(check_move_validity=True)._check_balanced({'records': move}):
            pass

        plan = [line + aml for line, (_vals, aml) in zip(new_lines, lines) if aml]
        if plan:
            self.env['account.move.line'].with_context(skip_account_move_synchronization=True)._reconcile_plan(plan)
        self.invalidate_recordset(['is_reconciled', 'amount_residual'])
        return True

    def _om_undo(self):
        """ Undo the reconciliation; any error is raised to the user, never hidden. """
        self._om_check_access()
        self.action_undo_reconciliation()
        self.invalidate_recordset(['is_reconciled', 'amount_residual'])
        for st_line in self:
            if not st_line.currency_id.is_zero(st_line.amount) and st_line.is_reconciled:
                raise UserError(_('The reconciliation of the transaction %s could not be undone.',
                                  st_line.display_name))
        return True

    # -------------------------------------------------------------------------
    # Candidates
    # -------------------------------------------------------------------------

    def _om_reference_tokens(self):
        self.ensure_one()
        texts = [self.payment_ref or '', self.ref or '', self.narration and str(self.narration) or '']
        tokens = set()
        for text in texts:
            for token in REFERENCE_TOKEN.findall(text):
                if any(char.isdigit() for char in token):
                    tokens.add(token)
        return tokens

    def _om_candidates_domain(self):
        self.ensure_one()
        return self._get_default_amls_matching_domain()

    def _om_search_candidates(self, search=None, limit=40, offset=0):
        """ Open journal items for the manual search of the reconciliation screen. """
        self.ensure_one()
        domain = self._om_candidates_domain()
        if search:
            search = search.strip()
            text_domain = ['|', '|', '|', '|',
                           ('move_id.name', 'ilike', search), ('ref', 'ilike', search), ('name', 'ilike', search),
                           ('move_id.payment_reference', 'ilike', search), ('partner_id.name', 'ilike', search)]
            try:
                number = float(search.replace(',', ''))
            except ValueError:
                number = None
            if number is not None:
                text_domain = ['|', '|', ('amount_residual', 'in', (number, -number)),
                               ('amount_residual_currency', 'in', (number, -number))] + text_domain
            domain += text_domain
        return self.env['account.move.line'].search(domain, order='date_maturity, date, id', limit=limit, offset=offset)

    def _om_scored_candidates(self, limit=20):
        """ Open journal items likely to be the counterpart of the transaction, best first.

        :return: list of (journal item, score)
        """
        self.ensure_one()
        AccountMoveLine = self.env['account.move.line']
        base_domain = self._om_candidates_domain()
        trans_currency, company_currency = self._om_currencies()
        residual = -self.amount_residual  # what the counterparts must cover, as a journal item amount

        candidates = AccountMoveLine
        partner = self.partner_id.commercial_partner_id
        if partner:
            candidates |= AccountMoveLine.search(base_domain + [('partner_id', 'child_of', partner.id)],
                                                 order='date_maturity, date, id', limit=200)
        tokens = self._om_reference_tokens()
        if tokens:
            token_domain = []
            for token in tokens:
                token_domain = (['|'] + token_domain if token_domain else []) + [
                    '|', '|', ('move_id.name', 'ilike', token), ('move_id.payment_reference', 'ilike', token),
                    ('ref', 'ilike', token)]
            candidates |= AccountMoveLine.search(base_domain + token_domain, limit=200)
        if not trans_currency.is_zero(residual):
            candidates |= AccountMoveLine.search(base_domain + [
                '|', ('amount_residual_currency', '=', residual), ('amount_residual', '=', residual),
            ], limit=200)

        scored = []
        normalized_label = (self.payment_ref or '').upper().replace(' ', '')
        for aml in candidates:
            score = 0
            aml_trans_residual = self._om_to_transaction_amount(aml.currency_id, aml.amount_residual_currency,
                                                                aml.amount_residual)
            # amounts are compared in the currency of the transaction only: 100 EUR is not 100 USD
            if trans_currency.compare_amounts(aml_trans_residual, residual) == 0:
                score += SCORE_AMOUNT
            references = [aml.move_id.name, aml.move_id.payment_reference, aml.ref]
            if any(reference and len(reference) > 3 and reference.upper().replace(' ', '') in normalized_label
                   for reference in references):
                score += SCORE_REFERENCE
            if partner and aml.partner_id.commercial_partner_id == partner:
                score += SCORE_PARTNER
            elif not partner and self.partner_name and aml.partner_id and \
                    self.partner_name.strip().lower() in aml.partner_id.name.lower():
                score += SCORE_PARTNER_NAME
            if residual and aml.amount_residual and (residual > 0) != (aml.amount_residual > 0):
                score += SCORE_WRONG_DIRECTION
            scored.append((aml, score))
        scored.sort(key=lambda item: (-item[1], item[0].date_maturity or item[0].date, item[0].id))
        return scored[:limit]

    def _om_suggested_proposal(self):
        """ Journal items proposed for the transaction: the best candidate, or the oldest open items of the
        partner whose total is exactly the amount of the transaction. """
        self.ensure_one()
        scored = self._om_scored_candidates()
        if not scored:
            return {}
        best, best_score = scored[0]
        if best_score >= SCORE_SUGGESTED:
            return {'matches': [{'aml_id': best.id}], 'score': best_score}

        trans_currency, _company_currency = self._om_currencies()
        residual = -self.amount_residual
        partner = self.partner_id.commercial_partner_id
        if partner and residual:
            total = 0.0
            selected = []
            same_direction = [aml for aml, _score in scored
                              if aml.partner_id.commercial_partner_id == partner
                              and (aml.amount_residual > 0) == (residual > 0)]
            same_direction.sort(key=lambda aml: (aml.date_maturity or aml.date, aml.id))
            for aml in same_direction:
                total += self._om_to_transaction_amount(aml.currency_id, aml.amount_residual_currency,
                                                        aml.amount_residual)
                selected.append(aml)
                comparison = trans_currency.compare_amounts(abs(total), abs(residual))
                if comparison == 0 and len(selected) > 1:
                    return {'matches': [{'aml_id': aml.id} for aml in selected], 'score': SCORE_SUGGESTED}
                if comparison > 0:
                    break
        return {}

    # -------------------------------------------------------------------------
    # Automatic reconciliation
    # -------------------------------------------------------------------------

    def _om_auto_reconcile(self):
        """ Apply the partner mappings, the automatic reconciliation models and the perfect matches.

        :return: the reconciled transactions
        """
        reconciled = self.browse()
        models = self.env['account.reconcile.model'].search([
            '|', ('company_id', '=', False), ('company_id', 'in', self.company_id.ids),
        ])
        for st_line in self:
            try:
                with self.env.cr.savepoint():
                    if st_line._om_auto_reconcile_one(models):
                        reconciled |= st_line
            except Exception as error:  # noqa: BLE001 - one transaction must not stop the others
                _logger.warning("Automatic reconciliation of transaction %s failed: %s", st_line.id, error)
        (self - reconciled).filtered(lambda line: not line.om_auto_processed).om_auto_processed = True
        reconciled.om_auto_processed = True
        return reconciled

    def _om_auto_reconcile_one(self, models):
        self.ensure_one()
        if self.is_reconciled:
            return False
        company_models = models.filtered(lambda model: not model.company_id or model.company_id == self.company_id)
        for model in company_models.filtered('mapped_partner_id'):
            if not self.partner_id and model._om_is_applicable(self):
                self.partner_id = model.mapped_partner_id
                break
        # only the models set to "Automated": a "Manual" model is a button the user clicks on the screen,
        # whatever its conditions and counterparts
        for model in company_models.filtered(lambda model: model._om_is_auto()):
            if not model._om_is_applicable(self):
                continue
            proposal = model._om_get_proposal(self)
            if proposal and self._om_is_complete(proposal):
                self._om_reconcile(proposal)
                self.invalidate_recordset()
                if hasattr(self, '_compute_is_reconciled'):
                    self._compute_is_reconciled()
                if hasattr(self, '_compute_hudson_matched_account_name'):
                    self._compute_hudson_matched_account_name()
                if hasattr(self, '_compute_hudson_suggestions'):
                    self._compute_hudson_suggestions()
                if model.next_activity_type_id:
                    self.move_id.activity_schedule(activity_type_id=model.next_activity_type_id.id)
                return True
        if self.company_id.om_reconcile_auto:
            scored = self._om_scored_candidates(limit=2)
            perfect = [aml for aml, score in scored if score >= SCORE_PERFECT]
            if len(perfect) == 1:
                proposal = {'matches': [{'aml_id': perfect[0].id}]}
                if self._om_is_complete(proposal):
                    self._om_reconcile(proposal)
                    self.invalidate_recordset()
                    if hasattr(self, '_compute_is_reconciled'):
                        self._compute_is_reconciled()
                    if hasattr(self, '_compute_hudson_matched_account_name'):
                        self._compute_hudson_matched_account_name()
                    if hasattr(self, '_compute_hudson_suggestions'):
                        self._compute_hudson_suggestions()
                    return True
        return False

    def _om_is_complete(self, proposal):
        remaining_trans, remaining_balance = self._om_remaining(self._om_prepare_proposal_lines(proposal))
        trans_currency, company_currency = self._om_currencies()
        return trans_currency.is_zero(remaining_trans) and company_currency.is_zero(remaining_balance)

    @api.model
    def _om_cron_auto_reconcile(self, batch_size=500):
        companies = self.env['res.company'].search([('om_reconcile_auto', '=', True)])
        st_lines = self.search([
            ('company_id', 'in', companies.ids),
            ('om_auto_processed', '=', False),
            ('is_reconciled', '=', False),
        ], order='date, id', limit=batch_size)
        st_lines._om_auto_reconcile()
        if len(st_lines) == batch_size:
            self.env.ref('om_account_reconcile.ir_cron_auto_reconcile')._trigger()
