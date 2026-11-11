from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class HudsonAutoReconcileWizard(models.TransientModel):
    _name = 'hudson.auto.reconcile.wizard'
    _description = 'Auto Reconcile Wizard'

    reconcile_mode = fields.Selection([
        ('perfect', 'Perfect Match'),
        ('clear', 'Clear Account')
    ], string='Reconcile', default='perfect', required=True)

    account_ids = fields.Many2many('account.account', string='Accounts', 
                                   domain="[('reconcile', '=', True)]")
    partner_ids = fields.Many2many('res.partner', string='Partners')
    date_from = fields.Date(string='From')
    date_to = fields.Date(string='To')

    @api.model
    def default_get(self, fields_list):
        res = super(HudsonAutoReconcileWizard, self).default_get(fields_list)
        if self._context.get('active_model') == 'account.move.line' and self._context.get('active_ids'):
            lines = self.env['account.move.line'].browse(self._context.get('active_ids'))
            accounts = lines.mapped('account_id')
            partners = lines.mapped('partner_id')
            if 'account_ids' in fields_list and accounts:
                res['account_ids'] = [(6, 0, accounts.ids)]
            if 'partner_ids' in fields_list and partners:
                res['partner_ids'] = [(6, 0, partners.ids)]
        return res

    def action_reconcile(self):
        # Build domain to fetch unreconciled journal items
        domain = [
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
            ('account_id.reconcile', '=', True),
            ('amount_residual', '!=', 0),
            ('company_id', 'in', self.env.companies.ids),
        ]
        
        if self.account_ids:
            domain.append(('account_id', 'in', self.account_ids.ids))
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))

        lines = self.env['account.move.line'].search(domain, order='date ASC')
        if not lines:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Auto-reconciliation Complete'),
                    'message': _('Nothing to reconcile. No unreconciled journal items found.'),
                    'type': 'warning',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }
        reconciled_count = 0

        def _try_reconcile(amls):
            # Savepoint: a failed reconcile must not abort the whole transaction
            try:
                with self.env.cr.savepoint():
                    amls.reconcile()
                return True
            except UserError as e:
                _logger.info("Auto-reconcile skipped lines %s: %s", amls.ids, e)
                return False

        # Group lines by Account, Partner and Currency (residuals of different
        # currencies cannot be summed or matched against each other)
        grouped_lines = {}
        for line in lines:
            key = (line.account_id.id, line.partner_id.id, line.currency_id.id)
            if key not in grouped_lines:
                grouped_lines[key] = self.env['account.move.line']
            grouped_lines[key] |= line

        for (account_id, partner_id, currency_id), group in grouped_lines.items():
            currency = group[:1].currency_id
            if self.reconcile_mode == 'clear':
                # Reconcile all lines in the group if the sum of residuals is 0
                if currency.is_zero(sum(group.mapped('amount_residual_currency'))):
                    if _try_reconcile(group):
                        reconciled_count += len(group)
            elif self.reconcile_mode == 'perfect':
                # Pair each line with an opposite line of exactly the same residual
                open_by_amount = {}
                for line in group.sorted('date'):
                    amount = currency.round(line.amount_residual_currency)
                    candidates = open_by_amount.get(-amount)
                    if candidates:
                        other = candidates.pop(0)
                        if _try_reconcile(line | other):
                            reconciled_count += 2
                            continue
                        candidates.insert(0, other)
                    open_by_amount.setdefault(amount, []).append(line)

        if reconciled_count == 0:
            message = _('Nothing to reconcile.')
            msg_type = 'warning'
        else:
            message = _('Successfully reconciled %s journal items.', reconciled_count)
            msg_type = 'success'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Auto-reconciliation Complete'),
                'message': message,
                'type': msg_type,
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
