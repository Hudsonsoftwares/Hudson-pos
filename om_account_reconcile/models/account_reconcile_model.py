import re

from odoo import api, models, _
from odoo.exceptions import ValidationError


class AccountReconcileModelLine(models.Model):
    _inherit = 'account.reconcile.model.line'

    @api.constrains('account_id')
    def _om_check_not_suspense_account(self):
        """ The counterpart of a model can be neither the suspense account of a bank journal (where a
        transaction waits until it is reconciled: it would reconcile nothing) nor the account of a bank
        journal the model applies to (it would cancel the transaction). """
        journals = self.env['account.journal'].sudo().search([('type', 'in', ('bank', 'cash', 'credit'))])
        suspense_accounts = journals.suspense_account_id
        for line in self:
            if line.account_id in suspense_accounts:
                raise ValidationError(_(
                    'The bank suspense account %(account)s cannot be the counterpart of the reconciliation model '
                    '"%(model)s": choose the account the transactions must be booked on.',
                    account=line.account_id.display_name, model=line.model_id.name))
            model_journals = line.model_id.match_journal_ids or journals.filtered(
                lambda journal: not line.model_id.company_id or journal.company_id == line.model_id.company_id)
            own_journals = model_journals.filtered(lambda journal: journal.default_account_id == line.account_id)
            if own_journals:
                raise ValidationError(_(
                    'The account %(account)s of the journal %(journal)s cannot be the counterpart of the '
                    'reconciliation model "%(model)s", which applies to that journal: it would cancel the '
                    'transactions. Choose the account the transactions must be booked on.',
                    account=line.account_id.display_name, journal=own_journals[0].display_name,
                    model=line.model_id.name))


class AccountReconcileModel(models.Model):
    _inherit = 'account.reconcile.model'

    # Creating or saving a model does not reconcile anything (as in Odoo): the automatic models are applied
    # to the new transactions only (see `account.bank.statement.line._om_auto_reconcile`), or to the
    # transactions the user asks for with the "Auto-reconcile" button of the reconciliation screen.

    def _om_is_auto(self):
        """ Whether the model is applied without the user clicking on it. """
        self.ensure_one()
        return self.trigger == 'auto_reconcile' and not self.mapped_partner_id

    def _om_label_texts(self, st_line):
        texts = [st_line.payment_ref or '']
        if st_line.transaction_details:
            texts.append(str(st_line.transaction_details))
        if st_line.narration:
            texts.append(str(st_line.narration))
        if st_line.ref:
            texts.append(str(st_line.ref))
        return texts

    def _om_is_applicable(self, st_line):
        """ Whether the conditions of the model are fulfilled by the transaction. """
        self.ensure_one()
        if self.company_id and self.company_id != st_line.company_id:
            return False
        if self.match_journal_ids and st_line.journal_id not in self.match_journal_ids:
            return False
        amount = abs(st_line.amount_currency if st_line.foreign_currency_id else st_line.amount)
        if self.match_amount == 'lower' and amount > self.match_amount_max:
            return False
        if self.match_amount == 'greater' and amount < self.match_amount_min:
            return False
        if self.match_amount == 'between' and not (self.match_amount_min <= amount <= self.match_amount_max):
            return False
        if self.match_label and self.match_label_param:
            texts = self._om_label_texts(st_line)
            if self.match_label == 'contains':
                if not any(self.match_label_param.lower() in text.lower() for text in texts):
                    return False
            elif self.match_label == 'not_contains':
                if any(self.match_label_param.lower() in text.lower() for text in texts):
                    return False
            elif self.match_label == 'match_regex':
                try:
                    if not any(re.search(self.match_label_param, text) for text in texts):
                        return False
                except Exception:
                    return False
        if self.match_partner_ids:
            if not st_line.partner_id or st_line.partner_id.commercial_partner_id not in self.match_partner_ids.commercial_partner_id:
                return False
        return True

    def _om_get_proposal(self, st_line):
        """ Proposal (see `account.bank.statement.line._om_reconcile`) of the model for the transaction. """
        self.ensure_one()
        if self.rule_type == 'matching_rule':
            return self._om_get_matching_rule_proposal(st_line)
        return {'writeoffs': self._om_get_writeoffs(st_line)}

    def _om_get_writeoffs(self, st_line, residual=None):
        """ Counterparts of the lines of the model.

        :param residual: amount left to cover, as a journal item amount in transaction currency;
                         what is left on the suspense account of the transaction by default.
        """
        self.ensure_one()
        trans_currency, _company_currency = st_line._om_currencies()
        if residual is None:
            residual = st_line.amount_residual
        trans_amount = -(st_line.amount_currency if st_line.foreign_currency_id else st_line.amount)
        writeoffs = []
        for line in self.line_ids.filtered('account_id'):
            if line.amount_type == 'fixed':
                # as in Odoo, a fixed amount follows the direction of what is left to cover: a bank fee is a
                # debit on a payment and a credit on a receipt (a negative amount on the model reverses it)
                direction = residual if not trans_currency.is_zero(residual) else trans_amount
                amount = line.amount if direction > 0 else -line.amount
            elif line.amount_type == 'percentage':
                amount = residual * line.amount / 100.0
            elif line.amount_type == 'percentage_st_line':
                amount = trans_amount * line.amount / 100.0
            else:
                amount = self._om_amount_from_label(st_line, line.amount_string)
                if amount is None:
                    continue
                amount = amount if trans_amount >= 0 else -amount
            amount = trans_currency.round(amount)
            if trans_currency.is_zero(amount):
                continue
            writeoffs.append({
                'account_id': line.account_id.id,
                'amount': amount,
                'label': line.label or st_line.payment_ref,
                'partner_id': (line.partner_id or st_line.partner_id).id,
                'tax_ids': line.tax_ids.ids,
                'tax_included': bool(line.tax_ids),
                'analytic_distribution': line.analytic_distribution or False,
                'reconcile_model_id': self.id,
            })
            residual -= amount
        return writeoffs

    def _om_amount_from_label(self, st_line, pattern):
        for text in self._om_label_texts(st_line):
            match = re.search(pattern, text)
            if not match:
                continue
            groups = [group for group in match.groups() if group is not None] or [match.group(0)]
            try:
                if len(groups) >= 2:
                    return float('%s.%s' % (re.sub(r'\D', '', groups[0]), re.sub(r'\D', '', groups[1])))
                value = groups[0].strip()
                if ',' in value and '.' in value:
                    value = (value.replace(',', '') if value.rfind('.') > value.rfind(',')
                             else value.replace('.', '').replace(',', '.'))
                else:
                    value = value.replace(',', '.')
                return abs(float(value))
            except ValueError:
                continue
        return None

    def _om_get_matching_rule_proposal(self, st_line):
        """ Open items of the partner of the transaction matching its amount within the payment tolerance,
        the difference being written off with the lines of the model. """
        self.ensure_one()
        partner = st_line.partner_id.commercial_partner_id
        if not partner and self.match_partner_ids:
            partner = self.match_partner_ids[0].commercial_partner_id
        trans_currency, _company_currency = st_line._om_currencies()
        residual = -st_line.amount_residual
        if trans_currency.is_zero(residual):
            return {}
        domain = st_line._om_candidates_domain() + [
            ('account_id.account_type', 'in',
             ('asset_receivable', 'liability_payable', 'asset_current', 'liability_current')),
        ]
        if partner:
            domain += [('partner_id', 'child_of', partner.id)]
        else:
            # As in Odoo: without a partner, only the open items whose reference is written on the
            # transaction can be matched, never the open items of whoever happens to owe the same amount.
            tokens = st_line._om_reference_tokens()
            if not tokens:
                return {}
            token_domain = []
            for token in tokens:
                token_domain = (['|'] + token_domain if token_domain else []) + [
                    '|', '|', ('move_id.name', 'ilike', token), ('move_id.payment_reference', 'ilike', token),
                    ('move_id.ref', 'ilike', token)]
            domain += token_domain
        amls = self.env['account.move.line'].search(
            domain,
            order='date_maturity %s, date %s, id' % (
                ('asc', 'asc') if self.matching_order == 'old_first' else ('desc', 'desc')
            ),
        )
        amls = amls.filtered(lambda aml: (aml.amount_residual > 0) == (residual > 0))
        if not partner:
            label = ' '.join(self._om_label_texts(st_line)).upper().replace(' ', '')
            amls = amls.filtered(lambda aml: any(
                reference and len(reference) > 3 and reference.upper().replace(' ', '') in label
                for reference in (aml.move_id.name, aml.move_id.payment_reference, aml.move_id.ref)))
            # the items of one partner at a time: one transaction never pays several partners
            for commercial_partner in amls.partner_id.commercial_partner_id:
                proposal = self._om_select_amls(
                    st_line, amls.filtered(lambda aml: aml.partner_id.commercial_partner_id == commercial_partner),
                    residual, commercial_partner)
                if proposal:
                    return proposal
            without_partner = amls.filtered(lambda aml: not aml.partner_id)
            return self._om_select_amls(st_line, without_partner, residual, partner) if without_partner else {}
        return self._om_select_amls(st_line, amls, residual, partner)

    def _om_select_amls(self, st_line, amls, residual, partner):
        """ The first of `amls` (in the order of the model) adding up to the amount of the transaction within
        the payment tolerance, the difference being written off with the lines of the model. """
        trans_currency, _company_currency = st_line._om_currencies()
        tolerance = (self.payment_tolerance if self.payment_tolerance_type == 'amount'
                     else abs(residual) * self.payment_tolerance / 100.0)

        selected = self.env['account.move.line']
        total = 0.0
        for aml in amls:
            aml_amount = st_line._om_to_transaction_amount(
                aml.currency_id, aml.amount_residual_currency, aml.amount_residual,
            )
            total += aml_amount
            selected |= aml
            difference = trans_currency.round(abs(residual) - abs(total))
            if abs(difference) <= tolerance + trans_currency.rounding / 2:
                # matched in full: the difference within the tolerance is written off below
                proposal = {
                    'matches': [{'aml_id': aml.id, 'amount': abs(aml.amount_residual_currency)} for aml in selected],
                }
                matched_partner = partner or (selected and selected[0].partner_id and selected[0].partner_id.commercial_partner_id)
                if matched_partner:
                    proposal['partner_id'] = matched_partner.id
                if not trans_currency.is_zero(difference):
                    if not self.line_ids.filtered('account_id'):
                        return {}
                    # what the matched items do not cover, as a journal item amount
                    left = trans_currency.round(residual - total)
                    proposal['writeoffs'] = self._om_get_writeoffs(st_line, residual=-left)
                return proposal
            if abs(total) > abs(residual) + tolerance:
                break
        return {}
