import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class AccountBankStatementLine(models.Model):
    _inherit = 'account.bank.statement.line'

    @api.model_create_multi
    def create(self, vals_list):
        st_lines = super(AccountBankStatementLine, self).create(vals_list)
        # Synchronously auto-reconcile new lines if an automated reconciliation model or keyword matches
        st_lines._hudson_auto_reconcile_sync()
        return st_lines

    def write(self, vals):
        res = super(AccountBankStatementLine, self).write(vals)
        if 'hudson_account_id' in vals and vals.get('hudson_account_id'):
            for line in self:
                bank_account = line.journal_id.default_account_id
                suspense_lines = line.line_ids.filtered(lambda l: l.account_id != bank_account)
                if suspense_lines:
                    suspense_lines[0].with_context(
                        skip_account_move_synchronization=True,
                        skip_readonly_check=True,
                        check_move_validity=False,
                    ).write({'account_id': vals['hudson_account_id']})
                    line.invalidate_recordset(['line_ids', 'is_reconciled'])
                    line.is_reconciled = True
                    acc = self.env['account.account'].browse(vals['hudson_account_id'])
                    line.hudson_matched_account_name = f"{acc.code} {acc.name}" if acc.code else acc.name

        trigger_fields = {'payment_ref', 'amount', 'partner_id', 'journal_id', 'narration', 'ref'}
        if trigger_fields & set(vals.keys()) and not self.env.context.get('skip_auto_reconcile_sync'):
            unrec_lines = self.filtered(lambda l: not l.is_reconciled)
            if unrec_lines:
                unrec_lines.with_context(skip_auto_reconcile_sync=True)._hudson_auto_reconcile_sync()
        return res

    def _hudson_auto_reconcile_sync(self, selected_model_id=None):
        """ Reconcile the transactions right away, as Odoo does when they are created.

        With `selected_model_id` (the model picked by the user on the inline row) that model is applied and
        any failure is reported. Otherwise the engine of om_account_reconcile decides, exactly as its
        automatic reconciliation does: the partner mappings, then the reconciliation models set to
        "Automated" (a "Manual" model is a button the user clicks, whatever its conditions), then the
        perfect matches when the automatic matching is enabled on the company.
        """
        to_reconcile = self.filtered(lambda line: not line.is_reconciled)
        if not to_reconcile:
            return self.browse()
        if selected_model_id:
            model = self.env['account.reconcile.model'].browse(selected_model_id).exists()
            if not model:
                return self.browse()
            for line in to_reconcile:
                if not model.company_id or model.company_id == line.company_id:
                    self._hudson_apply_reconcile_model(line, model, explicit=True)
            return to_reconcile.filtered('is_reconciled')
        # as the automatic reconciliation of om_account_reconcile: only for the companies where
        # "Reconcile New Transactions Automatically" is enabled
        to_reconcile = to_reconcile.filtered(lambda line: line.company_id.om_reconcile_auto)
        if not to_reconcile:
            return self.browse()
        reconciled = to_reconcile._om_auto_reconcile()
        for line in reconciled:
            line._compute_hudson_matched_account_name()
            line._compute_hudson_suggestions()
        return reconciled

    def _hudson_apply_reconcile_model(self, line, model, explicit=False):
        """ Applies a reconciliation model to a single statement line.

        Automatic matching only reconciles when the model applies to the line and
        its proposal fully balances it; otherwise the line is left for manual review.
        When the user picked the model explicitly, failures are reported to them.
        """
        if model.company_id and model.company_id != line.company_id:
            return False
        if not explicit and not model._om_is_applicable(line):
            return False

        proposal = model._om_get_proposal(line)
        if not proposal or not (proposal.get('matches') or proposal.get('writeoffs')):
            if explicit:
                raise UserError(_("The reconciliation model '%s' does not propose anything for this transaction.", model.name))
            return False
        if not explicit and not line._om_is_complete(proposal):
            return False

        try:
            with self.env.cr.savepoint():
                line._om_reconcile(proposal)
        except UserError:
            if explicit:
                raise
            _logger.warning("Reconciliation model %s could not be applied on statement line %s", model.name, line.id, exc_info=True)
            return False
        line.invalidate_recordset()
        line._compute_hudson_matched_account_name()
        line._compute_hudson_suggestions()
        return line.is_reconciled
    
    def action_hudson_upload_bills(self):
        """ Open a wizard or form to attach/upload bills """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            }
        }

    @api.model
    def action_hudson_dummy_upload(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'Upload', 'message': 'Upload feature triggered!', 'sticky': False}
        }

    hudson_action_dummy = fields.Boolean(compute='_compute_hudson_action_dummy')
    def _compute_hudson_action_dummy(self):
        for rec in self:
            rec.hudson_action_dummy = False

    # --- New UI Backend Fields & Methods ---
    
    hudson_matched_account_name = fields.Char(
        string='Matched Account', 
        compute='_compute_hudson_matched_account_name',
        store=False
    )
    
    @api.depends('is_reconciled', 'move_id.line_ids.reconciled', 'move_id.line_ids.matched_debit_ids', 'move_id.line_ids.matched_credit_ids', 'move_id.line_ids.reconcile_model_id')
    def _compute_hudson_matched_account_name(self):
        for line in self:
            if not line.is_reconciled:
                line.hudson_matched_account_name = False
                continue

            liquidity_lines = line.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type in ('asset_cash', 'liability_credit_card')
            )
            counterpart_lines = line.move_id.line_ids - liquidity_lines

            matched_refs = []
            for cp in counterpart_lines:
                for partial in (cp.matched_debit_ids | cp.matched_credit_ids):
                    other_line = partial.debit_move_id if partial.credit_move_id == cp else partial.credit_move_id
                    if other_line.move_id and other_line.move_id.name and other_line.move_id.name not in matched_refs:
                        matched_refs.append(other_line.move_id.name)

            if matched_refs:
                line.hudson_matched_account_name = ", ".join(matched_refs)
            elif counterpart_lines:
                acc_labels = []
                for cp in counterpart_lines:
                    acc = cp.account_id
                    acc_str = f"{acc.code} {acc.name}" if acc.code else acc.name
                    if acc_str not in acc_labels:
                        acc_labels.append(acc_str)
                line.hudson_matched_account_name = ", ".join(acc_labels) if acc_labels else 'Reconciled'
            else:
                line.hudson_matched_account_name = 'Reconciled'

    hudson_account_id = fields.Many2one(
        'account.account',
        string="Account",
        help="Temporary account field for new statement lines."
    )

    hudson_suggested_account_id = fields.Many2one(
        'account.account',
        string='Suggested Account',
        compute='_compute_hudson_suggestions',
        store=False
    )
    hudson_suggested_account_name = fields.Char(
        string='Suggested Account Name',
        compute='_compute_hudson_suggestions',
        store=False
    )
    hudson_match_count = fields.Integer(
        string='Match Count',
        compute='_compute_hudson_suggestions',
        store=False
    )
    hudson_has_matches = fields.Boolean(
        string='Has Matches',
        compute='_compute_hudson_suggestions',
        store=False
    )

    @api.depends('is_reconciled', 'partner_id', 'amount', 'payment_ref')
    def _compute_hudson_suggestions(self):
        for line in self:
            if line.is_reconciled:
                line.hudson_has_matches = False
                line.hudson_match_count = 0
                line.hudson_suggested_account_id = False
                line.hudson_suggested_account_name = False
                continue

            suggested_acc = False
            suggested_name = False
            match_count = 0
            has_matches = False

            rounded_amount = line.currency_id.round(line.amount) if line.currency_id else round(line.amount, 2)
            base_exact_domain = [
                ('account_id.reconcile', '=', True),
                ('reconciled', '=', False),
                ('move_id.state', '=', 'posted'),
                ('company_id', '=', line.company_id.id),
                ('id', 'not in', line.move_id.line_ids.ids),
                ('account_id.account_type', 'not in', ('asset_cash', 'liability_credit_card')),
                ('amount_residual', '>=', rounded_amount - 0.005),
                ('amount_residual', '<=', rounded_amount + 0.005),
            ]
            if line.journal_id.default_account_id:
                base_exact_domain.append(('account_id', '!=', line.journal_id.default_account_id.id))
            if line.journal_id.suspense_account_id:
                base_exact_domain.append(('account_id', '!=', line.journal_id.suspense_account_id.id))

            # Count + fetch one: this compute runs for every row of the list view
            AML = self.env['account.move.line']
            if line.partner_id:
                partner_ids = [line.partner_id.id]
                if line.partner_id.commercial_partner_id:
                    partner_ids.append(line.partner_id.commercial_partner_id.id)
                partner_domain = base_exact_domain + [('partner_id', 'in', partner_ids)]
                exact_matches = AML.search(partner_domain, limit=1)
                if exact_matches:
                    match_count = AML.search_count(partner_domain)
                    has_matches = True
                    suggested_acc = exact_matches[0].account_id
                    suggested_name = exact_matches[0].account_id.name
                else:
                    match_count = 0
                    has_matches = False
                    suggested_acc = line.partner_id.property_account_receivable_id if line.amount >= 0 else line.partner_id.property_account_payable_id
                    suggested_name = "Receivable" if line.amount >= 0 else "Payable"
            else:
                exact_matches = AML.search(base_exact_domain, limit=1)
                if exact_matches:
                    match_count = AML.search_count(base_exact_domain)
                    has_matches = True
                    suggested_acc = exact_matches[0].account_id
                    suggested_name = exact_matches[0].account_id.name
                else:
                    match_count = 0
                    has_matches = False
                    suggested_acc = False
                    suggested_name = False

            line.hudson_suggested_account_id = suggested_acc
            line.hudson_suggested_account_name = suggested_name
            line.hudson_match_count = match_count
            line.hudson_has_matches = has_matches

    def action_apply_suggested_account(self):
        self.ensure_one()
        # 1. Check if there are exact matching items (invoices/bills/payments) with same value
        rounded_amount = self.currency_id.round(self.amount) if self.currency_id else round(self.amount, 2)
        base_exact_domain = [
            ('account_id.reconcile', '=', True),
            ('reconciled', '=', False),
            ('move_id.state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
            ('id', 'not in', self.move_id.line_ids.ids),
            ('account_id.account_type', 'not in', ('asset_cash', 'liability_credit_card')),
            ('amount_residual', '>=', rounded_amount - 0.005),
            ('amount_residual', '<=', rounded_amount + 0.005),
        ]
        if self.journal_id.default_account_id:
            base_exact_domain.append(('account_id', '!=', self.journal_id.default_account_id.id))
        if self.journal_id.suspense_account_id:
            base_exact_domain.append(('account_id', '!=', self.journal_id.suspense_account_id.id))
        if self.partner_id:
            partner_ids = [self.partner_id.id]
            if self.partner_id.commercial_partner_id:
                partner_ids.append(self.partner_id.commercial_partner_id.id)
            exact_matches = self.env['account.move.line'].search(base_exact_domain + [('partner_id', 'in', partner_ids)], limit=1)
        else:
            exact_matches = self.env['account.move.line'].search(base_exact_domain, limit=1)

        if exact_matches:
            return self.action_hudson_reconcile_items(exact_matches.ids)

        # 2. Otherwise direct counterpart account writeoff
        acc = self.hudson_suggested_account_id
        if not acc and self.partner_id:
            acc = self.partner_id.property_account_receivable_id if self.amount >= 0 else self.partner_id.property_account_payable_id
        if acc:
            # Book the whole open amount on the account through the reconcile engine,
            # which keeps the entry balanced (several suspense lines, currencies).
            remaining_trans, _remaining_balance = self._om_remaining([])
            if not self.currency_id.is_zero(remaining_trans):
                self._om_reconcile({'writeoffs': [{
                    'account_id': acc.id,
                    'amount': remaining_trans,
                    'label': self.payment_ref,
                    'partner_id': self.partner_id.id,
                }]})
            self.invalidate_recordset()
            self._compute_is_reconciled()
            self._compute_hudson_matched_account_name()
        return True

    def action_hudson_reconcile_items(self, item_ids):
        """ Reconciles the statement line with the selected move line ids """
        self.ensure_one()
        if not item_ids:
            return True

        # Verify the selected lines actually exist (guard against stale IDs)
        matching_lines = self.env['account.move.line'].browse(item_ids).exists()
        if not matching_lines:
            return True

        first_match = matching_lines[0]

        # Reconcile through the om_account_reconcile engine only: it keeps the
        # entry balanced and handles partials/currencies. Errors are shown to the
        # user instead of being patched over by rewriting the move by hand.
        proposal = {
            'matches': [{'aml_id': aml.id} for aml in matching_lines],
        }
        if not self.partner_id and first_match.partner_id:
            proposal['partner_id'] = first_match.partner_id.id
        self._om_reconcile(proposal)
        self.invalidate_recordset()
        self._compute_is_reconciled()
        self._compute_hudson_matched_account_name()

        # Ensure all affected invoices and payments have updated states
        affected_moves = matching_lines.move_id.filtered(lambda m: m.is_invoice(True))
        affected_payments = self.env['account.payment'].search([
            '|', '|',
            ('move_id', 'in', matching_lines.move_id.ids),
            ('reconciled_bill_ids', 'in', affected_moves.ids),
            ('reconciled_invoice_ids', 'in', affected_moves.ids),
        ]) | affected_moves.matched_payment_ids

        if affected_payments:
            affected_payments.invalidate_recordset(['state', 'is_matched', 'is_reconciled'])
            affected_payments._compute_state()
            affected_payments._compute_reconciliation_status()
            affected_moves |= affected_payments.reconciled_bill_ids | affected_payments.reconciled_invoice_ids

        if affected_moves:
            affected_moves.invalidate_recordset(['payment_state', 'status_in_payment', 'amount_residual'])
            affected_moves._compute_payment_state()
        return True

    def action_hudson_internal_transfer(self):
        """ Reconciles the statement line as an internal transfer """
        self.ensure_one()
        transfer_account = self.company_id.transfer_account_id
        if not transfer_account:
            raise UserError(_("Please configure an Internal Transfer account in the accounting settings."))
        # Book the open amount on the internal transfer account so the suspense account is cleared
        remaining_trans, _remaining_balance = self._om_remaining([])
        if not self.currency_id.is_zero(remaining_trans):
            self._om_reconcile({'writeoffs': [{
                'account_id': transfer_account.id,
                'amount': remaining_trans,
                'label': self.payment_ref or _("Internal Transfer"),
            }]})
        self.invalidate_recordset()
        self._compute_is_reconciled()
        self._compute_hudson_matched_account_name()
        return True

    def action_hudson_reset(self):
        """ Resets the statement line matching natively """
        self.ensure_one()
        counterpart_lines = self.move_id.line_ids.filtered(lambda l: l.account_id != self.journal_id.default_account_id)
        partials = counterpart_lines.matched_debit_ids | counterpart_lines.matched_credit_ids
        other_lines = (partials.debit_move_id | partials.credit_move_id) - counterpart_lines
        affected_moves = other_lines.move_id.filtered(lambda m: m.is_invoice(True))
        affected_payments = self.env['account.payment'].search([
            '|', '|',
            ('move_id', 'in', other_lines.move_id.ids),
            ('reconciled_bill_ids', 'in', affected_moves.ids),
            ('reconciled_invoice_ids', 'in', affected_moves.ids),
        ]) | affected_moves.matched_payment_ids

        if hasattr(self, '_om_undo'):
            try:
                self._om_undo()
            except Exception:
                self.action_undo_reconciliation()
        else:
            self.action_undo_reconciliation()

        self.is_reconciled = False
        self.hudson_matched_account_name = False

        if affected_payments:
            affected_payments.invalidate_recordset(['state', 'is_matched', 'is_reconciled'])
            affected_payments._compute_state()
            affected_payments._compute_reconciliation_status()
            affected_moves |= affected_payments.reconciled_bill_ids | affected_payments.reconciled_invoice_ids

        if affected_moves:
            affected_moves.invalidate_recordset(['payment_state', 'status_in_payment', 'amount_residual'])
            affected_moves._compute_payment_state()

        return True

    def action_set_partner(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'hudson_set_partner',
            'context': {
                'default_statement_line_id': self.id,
            }
        }
        
    def action_set_account(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'hudson_set_account',
            'context': {
                'default_statement_line_id': self.id,
            }
        }
        
    def action_needs_attention(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'Attention', 'message': 'Needs attention!', 'sticky': False}
        }
        
    # Duplicate action_hudson_reset removed — the full implementation is above at line 245.

    def action_expand_line(self):
        self.ensure_one()
        # Open standard form view for the statement line
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.bank.statement.line',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def action_hudson_create_inline_transaction(self, vals):
        """ Creates a new statement line directly from the inline row and applies auto-reconciliation """
        label = (vals.get('payment_ref') or '').strip()
        if not label:
            raise UserError(_("Label is required to create a new transaction."))
        amount = float(vals.get('amount') or 0.0)
        if amount == 0.0:
            raise UserError(_("Please provide a valid non-zero amount."))

        journal_id = vals.get('journal_id')
        if not journal_id:
            bank_journal = self.env['account.journal'].search([
                ('company_id', '=', self.env.company.id),
                ('type', 'in', ['bank', 'cash'])
            ], limit=1)
            journal_id = bank_journal.id if bank_journal else False

        create_vals = {
            'journal_id': journal_id,
            'date': vals.get('date') or fields.Date.context_today(self),
            'payment_ref': label,
            'amount': amount,
            'partner_id': vals.get('partner_id') or False,
        }
        st_line = self.create(create_vals)
        if vals.get('reconcile_model_id'):
            st_line._hudson_auto_reconcile_sync(selected_model_id=vals['reconcile_model_id'])
        return {
            'id': st_line.id,
            'is_reconciled': st_line.is_reconciled,
            'matched_account_name': st_line.hudson_matched_account_name or '',
        }

    @api.model
    def get_available_reconcile_models(self, journal_id=None):
        """ Returns available reconciliation models for selection in inline row """
        domain = ['|', ('company_id', '=', False), ('company_id', '=', self.env.company.id), ('active', '=', True)]
        models = self.env['account.reconcile.model'].search(domain, order='sequence, name')
        if journal_id:
            models = models.filtered(lambda m: not m.match_journal_ids or int(journal_id) in m.match_journal_ids.ids)
        return [{'id': m.id, 'name': m.name} for m in models]

    @api.model
    def get_hudson_bank_matching_context(self, journal_id=None):
        """ Returns currency, position, symbol and available reconciliation models for the bank matching list view """
        journal = self.env['account.journal'].browse(int(journal_id)) if journal_id else self.env['account.journal']
        company = journal.company_id if journal else self.env.company
        currency = journal.currency_id or company.currency_id
        
        domain = ['|', ('company_id', '=', False), ('company_id', '=', company.id), ('active', '=', True)]
        models = self.env['account.reconcile.model'].search(domain, order='sequence, name')
        if journal:
            models = models.filtered(lambda m: not m.match_journal_ids or journal.id in m.match_journal_ids.ids)
            
        return {
            'currency_id': currency.id,
            'currency_name': currency.name or '',
            'currency_symbol': currency.symbol or '',
            'currency_position': currency.position or 'before',
            'reconcile_models': [{'id': m.id, 'name': m.name} for m in models],
        }

    @api.model
    def get_hudson_matching_candidates(self, statement_line_id, search_term=None, limit=30, offset=0):
        """ Returns matching journal items (account.move.line) formatted for the Enterprise-style matching modal """
        st_line = self.browse(int(statement_line_id))
        if not st_line.exists():
            return {'candidates': [], 'total_count': 0}

        domain = [
            ('account_id.reconcile', '=', True),
            ('reconciled', '=', False),
            ('move_id.state', '=', 'posted'),
            ('company_id', '=', st_line.company_id.id),
            ('id', 'not in', st_line.move_id.line_ids.ids),
            ('account_id.account_type', 'not in', ('asset_cash', 'liability_credit_card')),
        ]
        if st_line.journal_id.default_account_id:
            domain.append(('account_id', '!=', st_line.journal_id.default_account_id.id))
        if st_line.journal_id.suspense_account_id:
            domain.append(('account_id', '!=', st_line.journal_id.suspense_account_id.id))

        if search_term and str(search_term).strip():
            term = str(search_term).strip()
            domain += [
                '|', '|', '|',
                ('move_id.name', 'ilike', term),
                ('partner_id.name', 'ilike', term),
                ('name', 'ilike', term),
                ('ref', 'ilike', term),
            ]

        MoveLine = self.env['account.move.line']
        total_count = MoveLine.search_count(domain)

        target_amount = abs(st_line.amount)
        partner_id = st_line.partner_id.id if st_line.partner_id else False

        lines = MoveLine.with_context(
            hudson_match_amount=target_amount,
            hudson_match_partner_id=partner_id,
        ).search(domain, order='date desc, id desc', limit=int(limit or 30), offset=int(offset or 0))

        comp_curr = st_line.company_id.currency_id
        comp_curr_symbol = comp_curr.symbol or ''
        comp_curr_pos = comp_curr.position or 'before'

        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"]

        candidates = []
        for line in lines:
            line_curr = line.currency_id if (line.currency_id and line.currency_id != comp_curr) else False
            
            # amount_residual is natively signed in Odoo:
            # - Negative for vendor bills (credit on AP): e.g. -977.50
            # - Positive for vendor refunds / customer invoices: e.g. 750.00
            residual = line.amount_residual if hasattr(line, 'amount_residual') and line.amount_residual else line.balance
            is_negative = residual < 0

            abs_comp = abs(residual)
            if comp_curr_pos == 'after':
                comp_amt_str = f"-{abs_comp:,.2f} {comp_curr_symbol}" if is_negative else f"{abs_comp:,.2f} {comp_curr_symbol}"
            else:
                comp_amt_str = f"{comp_curr_symbol} -{abs_comp:,.2f}" if is_negative else f"{comp_curr_symbol} {abs_comp:,.2f}"

            # Foreign currency formatting if applicable
            foreign_amt_str = ""
            if line_curr:
                foreign_sym = line_curr.symbol or ''
                foreign_pos = line_curr.position or 'before'
                res_curr = line.amount_residual_currency if hasattr(line, 'amount_residual_currency') and line.amount_residual_currency else line.amount_currency
                abs_foreign = abs(res_curr)
                if foreign_pos == 'after':
                    foreign_amt_str = f"-{abs_foreign:,.2f} {foreign_sym}" if is_negative else f"{abs_foreign:,.2f} {foreign_sym}"
                else:
                    foreign_amt_str = f"{foreign_sym} -{abs_foreign:,.2f}" if is_negative else f"{foreign_sym} {abs_foreign:,.2f}"

            display_date = f"{line.date.day} {months[line.date.month - 1]}" if line.date else ""

            candidates.append({
                'id': line.id,
                'move_id': line.move_id.id,
                'move_name': line.move_id.name or '',
                'date': display_date,
                'partner_id': line.partner_id.id or False,
                'partner_name': line.partner_id.display_name or line.partner_id.name or '',
                'name': line.name if (line.name and line.name != '/') else (line.ref or ''),
                'amount_due_str': comp_amt_str,
                'foreign_amount_due_str': foreign_amt_str,
                'has_foreign_currency': bool(foreign_amt_str),
                'is_negative': is_negative,
            })

        return {
            'candidates': candidates,
            'total_count': total_count,
        }

    def get_hudson_edit_line_data(self):
        """ Returns all field data for the Edit Line popup modal """
        self.ensure_one()
        liquidity_lines = self.move_id.line_ids.filtered(
            lambda l: l.account_id.account_type in ('asset_cash', 'liability_credit_card')
        )
        counterpart_lines = self.move_id.line_ids - liquidity_lines
        matched_moves = []
        for cp in counterpart_lines:
            for partial in (cp.matched_debit_ids | cp.matched_credit_ids):
                other = partial.debit_move_id if partial.credit_move_id == cp else partial.credit_move_id
                if other.move_id and other.move_id.name and other.move_id.name not in matched_moves:
                    matched_moves.append(other.move_id.name)

        is_matched_bill = bool(matched_moves)
        matched_bill_text = f"{matched_moves[0]} will be entirely paid by the transaction." if is_matched_bill else False
        is_editable = not is_matched_bill

        counterpart_acc = counterpart_lines[0].account_id if counterpart_lines else False

        months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"]
        display_date = f"{self.date.day} {months[self.date.month - 1]}" if self.date else ""

        return {
            'id': self.id,
            'date': display_date,
            'raw_date': str(self.date or ''),
            'amount': self.amount,
            'balance_formatted': f"{self.currency_id.symbol or '$'} {abs(self.amount):,.2f}",
            'currency_name': self.currency_id.name or 'USD',
            'is_matched_bill': is_matched_bill,
            'matched_bill_text': matched_bill_text,
            'is_account_editable': is_editable,
            'is_partner_editable': is_editable,
            'account_id': counterpart_acc.id if counterpart_acc else False,
            'account_code': counterpart_acc.code if counterpart_acc else '',
            'account_name': counterpart_acc.name if counterpart_acc else '',
            'account_display_name': counterpart_acc.display_name if counterpart_acc else '',
            'partner_id': self.partner_id.id if self.partner_id else False,
            'partner_name': self.partner_id.display_name if self.partner_id else '',
            'description': self.payment_ref or '',
            'analytic_distribution': counterpart_lines[0].analytic_distribution if counterpart_lines else {},
            'vehicle': getattr(self, 'vehicle_id', None) and self.vehicle_id.display_name or False,
        }

    def action_hudson_save_edit_line(self, vals):
        """ Saves modifications from the Edit Line popup modal safely on posted or draft entries """
        self.ensure_one()
        # ORM writes (not raw SQL) so lock dates, hashed entries, company
        # consistency and reconciled-line protections are enforced.
        st_line = self.with_context(skip_auto_reconcile_sync=True)
        if 'description' in vals and vals['description'] is not None:
            st_line.write({'payment_ref': vals['description']})

        is_locked = vals.get('is_locked', False)
        if not is_locked:
            bank_account = self.journal_id.default_account_id
            counterparts = self.line_ids.filtered(lambda l: l.account_id != bank_account)
            counterparts = counterparts.with_context(skip_account_move_synchronization=True)

            if 'partner_id' in vals:
                partner_id = vals['partner_id'] or False
                st_line.write({'partner_id': partner_id})
                if counterparts:
                    counterparts.write({'partner_id': partner_id})

            if 'account_id' in vals and vals['account_id']:
                new_acc = self.env['account.account'].browse(vals['account_id']).exists()
                if new_acc and counterparts:
                    if counterparts.filtered('reconciled'):
                        raise UserError(_("The counterpart of this transaction is already reconciled. "
                                          "Reset the matching before changing its account."))
                    counterparts.write({'account_id': new_acc.id})
                    self.hudson_matched_account_name = f"{new_acc.code} {new_acc.name}" if new_acc.code else new_acc.name
        return True
