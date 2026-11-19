from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta
from datetime import date
from odoo.tools import float_round

from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = 'account.move'

    hudson_deferred_original_move_id = fields.Many2one('account.move', string="Original Move", copy=False)
    hudson_deferral_move_ids = fields.One2many('account.move', 'hudson_deferred_original_move_id', string="Deferral Entries")
    hudson_deferral_count = fields.Integer(compute='_compute_hudson_deferral_count')

    @api.depends('hudson_deferral_move_ids')
    def _compute_hudson_deferral_count(self):
        for move in self:
            move.hudson_deferral_count = len(move.hudson_deferral_move_ids)

    def action_view_hudson_deferrals(self):
        self.ensure_one()
        return {
            'name': _('Deferral Entries'),
            'view_mode': 'list,form',
            'res_model': 'account.move.line',
            'domain': [('move_id.hudson_deferred_original_move_id', '=', self.id)],
            'type': 'ir.actions.act_window',
            'context': {
                'create': False, 
                'delete': False, 
                'group_by': ['move_id'],
                'expand': 1
            }
        }

    def _post(self, soft=True):
        res = super(AccountMove, self)._post(soft=soft)
        # With soft=True, future-dated moves stay in draft: only act on what was really posted
        posted = res.filtered(lambda m: m.state == 'posted')
        posted._generate_hudson_deferrals()
        posted._auto_reconcile_hudson_deferrals()
        return res

    def _auto_reconcile_hudson_deferrals(self):
        for move in self:
            if move.hudson_deferred_original_move_id and move.state == 'posted':
                orig_move = move.hudson_deferred_original_move_id
                
                # Find all posted lines for this deferral chain that hit a reconcilable account (like Deferred Expenses)
                deferred_lines = self.env['account.move.line'].search([
                    ('move_id.hudson_deferred_original_move_id', '=', orig_move.id),
                    ('move_id.state', '=', 'posted'),
                    ('account_id.reconcile', '=', True),
                ])
                
                for account in deferred_lines.mapped('account_id'):
                    lines_to_reconcile = deferred_lines.filtered(lambda l: l.account_id == account and not l.reconciled)
                    if len(lines_to_reconcile) > 1:
                        try:
                            with self.env.cr.savepoint():
                                lines_to_reconcile.reconcile()
                        except UserError as e:
                            _logger.warning("Could not reconcile deferral lines of %s: %s", orig_move.name, e)

    def _get_active_hudson_deferrals(self):
        """ Deferral entries of the moves still in effect: not cancelled nor reversed. """
        return self.hudson_deferral_move_ids.filtered(
            lambda m: m.state != 'cancel' and not m.reversal_move_ids.filtered(lambda r: r.state != 'cancel'))

    def _remove_hudson_deferrals(self):
        """ Remove the deferral entries of the moves like Odoo does: the drafts (the months to come) are
        deleted, the posted ones are in the books and are reversed, never deleted. """
        deferrals = self._get_active_hudson_deferrals()
        deferrals.filtered(lambda m: m.state == 'draft').unlink()
        posted = deferrals.filtered(lambda m: m.state == 'posted')
        if posted:
            # the lines are matched with each other and with the invoice: each reversal matches its entry instead
            posted.line_ids.filtered(lambda l: l.matched_debit_ids or l.matched_credit_ids).remove_move_reconcile()
            posted._reverse_moves(default_values_list=[{
                'ref': _("Reversal of: %s", move.ref or move.name),
            } for move in posted], cancel=True)

    def button_draft(self):
        res = super(AccountMove, self).button_draft()
        # after super: the invoice lines are no longer reconciled with the deferral entries
        self._remove_hudson_deferrals()
        return res

    def button_cancel(self):
        self._remove_hudson_deferrals()
        return super(AccountMove, self).button_cancel()

    def _get_or_create_deferred_account(self, company, is_income):
        Account = self.env['account.account'].with_company(company)
        company_domain = list(Account._check_company_domain(company))
        if is_income:
            # Look for existing Deferred Revenue / Income account
            deferred_acc = Account.search(company_domain + [
                ('account_type', 'in', ('liability_current', 'liability_non_current')),
                '|', '|',
                ('name', 'ilike', 'deferred revenue'),
                ('name', 'ilike', 'deferred income'),
                ('name', 'ilike', 'unearned revenue'),
            ], limit=1)
            if not deferred_acc:
                # Auto-create one for this company
                code = '210000'
                existing = Account.search(company_domain + [('code', '=', code)], limit=1)
                if existing:
                    code = '210099'
                deferred_acc = Account.create({
                    'name': 'Deferred Revenue',
                    'code': code,
                    'account_type': 'liability_current',
                    'reconcile': True,
                })
        else:
            # Look for existing Deferred Expense / Prepaid Expense account
            deferred_acc = Account.search(company_domain + [
                ('account_type', 'in', ('asset_current', 'asset_prepayments')),
                '|', '|',
                ('name', 'ilike', 'deferred expense'),
                ('name', 'ilike', 'prepaid expense'),
                ('name', 'ilike', 'prepayment'),
            ], limit=1)
            if not deferred_acc:
                code = '130000'
                existing = Account.search(company_domain + [('code', '=', code)], limit=1)
                if existing:
                    code = '130099'
                deferred_acc = Account.create({
                    'name': 'Deferred Expense',
                    'code': code,
                    'account_type': 'asset_current',
                    'reconcile': True,
                })
        return deferred_acc

    def _generate_hudson_deferrals(self):
        for move in self:
            if move.state != 'posted' or move.hudson_deferred_original_move_id or move._get_active_hudson_deferrals():
                continue

            deferral_lines = move.line_ids.filtered(lambda l: l.hudson_deferred_start_date and l.hudson_deferred_end_date and l.display_type == 'product')
            if not deferral_lines:
                continue

            for line in deferral_lines:
                try:
                    is_income = line.account_id.account_type in ('income', 'income_other')
                    deferred_account = line.account_id.hudson_deferred_account_id
                    
                    if not deferred_account:
                        company = line.company_id or move.company_id or self.env.company
                        deferred_account = self._get_or_create_deferred_account(company, is_income)
                        if deferred_account and not line.account_id.hudson_deferred_account_id:
                            line.account_id.sudo().write({'hudson_deferred_account_id': deferred_account.id})

                    if not deferred_account:
                        continue

                    # We need to determine the sign based on the line amount.
                    # For an invoice, income line has credit > 0, balance < 0.
                    amount = line.balance
                    
                    if amount == 0:
                        continue

                    start_date = line.hudson_deferred_start_date
                    end_date = line.hudson_deferred_end_date
                    total_days = (end_date - start_date).days + 1
                    if total_days <= 0:
                        continue

                    # 1. Generate the initial Reversal Entry (Original Account -> Deferred Account)
                    # If balance < 0 (Credit on income), reversal needs Debit on Income, Credit on Deferred
                    reversal_vals = {
                        'move_type': 'entry',
                        'date': move.date, # Date of the invoice
                        'journal_id': line.journal_id.id,
                        'hudson_deferred_original_move_id': move.id,
                        'ref': f"Deferral of {move.name}",
                        'line_ids': [
                            (0, 0, {
                                'name': f"Deferral of {move.name}",
                                'account_id': line.account_id.id,
                                'debit': -amount if amount < 0 else 0.0,
                                'credit': amount if amount > 0 else 0.0,
                                'partner_id': move.partner_id.id,
                            }),
                            (0, 0, {
                                'name': f"Deferral of {move.name}",
                                'account_id': deferred_account.id,
                                'debit': amount if amount > 0 else 0.0,
                                'credit': -amount if amount < 0 else 0.0,
                                'partner_id': move.partner_id.id,
                            })
                        ]
                    }
                    reversal_move = self.env['account.move'].create(reversal_vals)
                    reversal_move.action_post()
                    
                    # Auto-reconcile the original line with the reversal line
                    if line.account_id.reconcile:
                        reversal_line = reversal_move.line_ids.filtered(lambda l: l.account_id == line.account_id)
                        if reversal_line:
                            (line + reversal_line).reconcile()

                    # 2. Generate the Draft Entries for each month (Deferred Account -> Original Account)
                    current_date = start_date
                    residual_amount = amount

                    while current_date <= end_date:
                        # Calculate end of current month or end_date, whichever is sooner
                        next_month_start = (current_date + relativedelta(months=1)).replace(day=1)
                        end_of_month = next_month_start - relativedelta(days=1)
                        period_end = min(end_of_month, end_date)
                        
                        period_days = (period_end - current_date).days + 1
                        
                        if period_end == end_date:
                            period_amount = residual_amount
                        else:
                            period_amount = float_round(amount * (period_days / total_days), precision_digits=2)
                            residual_amount -= period_amount

                        draft_vals = {
                            'move_type': 'entry',
                            'date': period_end,
                            'journal_id': line.journal_id.id,
                            'hudson_deferred_original_move_id': move.id,
                            'ref': f"Deferral of {move.name}",
                            'auto_post': 'at_date',
                            'line_ids': [
                                (0, 0, {
                                    'name': f"Deferral of {move.name}",
                                    'account_id': deferred_account.id,
                                    'debit': -period_amount if period_amount < 0 else 0.0,
                                    'credit': period_amount if period_amount > 0 else 0.0,
                                    'partner_id': move.partner_id.id,
                                }),
                                (0, 0, {
                                    'name': f"Deferral of {move.name}",
                                    'account_id': line.account_id.id,
                                    'debit': period_amount if period_amount > 0 else 0.0,
                                    'credit': -period_amount if period_amount < 0 else 0.0,
                                    'partner_id': move.partner_id.id,
                                })
                            ]
                        }
                        self.env['account.move'].create(draft_vals)
                        current_date = next_month_start
                except UserError:
                    raise
                except Exception as e:
                    # Never post an invoice with a silently incomplete deferral schedule
                    _logger.exception("Deferral generation failed for %s", move.name)
                    raise UserError(_("Could not generate the deferral entries for %(move)s: %(error)s",
                                      move=move.name, error=e)) from e

    @api.depends(
        'amount_residual', 'move_type', 'state', 'company_id',
        'reconciled_payment_ids.state', 'reconciled_payment_ids.is_matched',
        'matched_payment_ids.state', 'matched_payment_ids.is_matched',
    )
    def _compute_payment_state(self):
        super()._compute_payment_state()
        for invoice in self:
            if not invoice.is_invoice(True) or invoice.state != 'posted':
                continue
            if invoice.payment_state in ('reversed', 'blocked', 'invoicing_legacy'):
                continue

            currency = invoice.currency_id or invoice.company_id.currency_id or self.env.company.currency_id
            linked_payments = (invoice.reconciled_payment_ids | invoice.matched_payment_ids).exists()

            # Case A: Amount residual is zero (the bill/invoice is fully covered)
            if currency.is_zero(invoice.amount_residual):
                if not linked_payments:
                    invoice.payment_state = 'paid'
                elif all(p.state == 'reconciled' or p.is_matched for p in linked_payments):
                    invoice.payment_state = 'paid'
                elif any(p.state in ('paid', 'in_payment') for p in linked_payments):
                    invoice.payment_state = 'in_payment'
                else:
                    invoice.payment_state = 'paid'

            # Case B: Enterprise-style registered payments without move_id
            elif invoice.matched_payment_ids.filtered(lambda p: not p.move_id):
                unmoved_payments = invoice.matched_payment_ids.filtered(lambda p: not p.move_id)
                total_unmoved = sum(abs(p.amount_company_currency_signed or p.amount) for p in unmoved_payments)
                if currency.compare_amounts(total_unmoved, invoice.amount_total) >= 0:
                    if all(p.state == 'reconciled' or p.is_matched for p in unmoved_payments):
                        invoice.payment_state = 'paid'
                    elif any(p.state in ('paid', 'in_payment') for p in unmoved_payments):
                        invoice.payment_state = 'in_payment'
                else:
                    invoice.payment_state = 'partial'

