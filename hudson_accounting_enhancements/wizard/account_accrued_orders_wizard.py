from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HudsonAccountAccruedOrdersWizard(models.TransientModel):
    _name = 'hudson.account.accrued.orders.wizard'
    _description = 'Accrued Orders Wizard'

    order_type = fields.Selection([('purchase', 'Purchase'), ('sale', 'Sale')], string="Order Type", required=True)
    journal_id = fields.Many2one('account.journal', string='Journal', required=True, domain="[('type', '=', 'general')]")
    account_id = fields.Many2one('account.account', string='Accrual Account', required=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    reversal_date = fields.Date(string='Reversal Date')
    preview_line_ids = fields.One2many('hudson.account.accrued.orders.wizard.line', 'wizard_id', string='Preview Lines')
    amount_total = fields.Monetary(compute='_compute_amount_total', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', compute='_compute_currency_id')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'journal_id' not in res:
            journal = self.env['account.journal'].search([('type', '=', 'general'), ('company_id', '=', self.env.company.id)], limit=1)
            if journal:
                res['journal_id'] = journal.id

        active_model = self.env.context.get('active_model')
        active_ids = self.env.context.get('active_ids')
        if not active_ids or active_model not in ['purchase.order.line', 'sale.order.line']:
            return res

        order_type = 'purchase' if active_model == 'purchase.order.line' else 'sale'
        res['order_type'] = order_type

        lines = self.env[active_model].browse(active_ids)
        preview_lines = []
        total_amount = 0.0

        for line in lines:
            if order_type == 'purchase':
                qty_diff = line.qty_received - line.qty_invoiced
                if qty_diff == 0:
                    continue
                # If qty_diff > 0: received > invoiced -> Bill to receive (Expense)
                # If qty_diff < 0: invoiced > received -> Billed not received (Deferred Expense)
                amount = abs(qty_diff * line.price_unit)
                total_amount += amount if qty_diff > 0 else -amount
                
                # Product Expense account
                account = line.product_id.property_account_expense_id or line.product_id.categ_id.property_account_expense_categ_id
                if not account:
                    raise UserError(_("No expense account defined for product %s.", line.product_id.display_name))
                
                label = f"{line.order_id.name} - {line.name}; {line.qty_invoiced} Billed, {line.qty_received} Received at {line.price_unit} each"
                
                preview_lines.append((0, 0, {
                    'account_id': account.id,
                    'name': label,
                    'debit': amount if qty_diff > 0 else 0.0,
                    'credit': amount if qty_diff < 0 else 0.0,
                }))

            else:
                qty_diff = line.qty_delivered - line.qty_invoiced
                if qty_diff == 0:
                    continue
                # If qty_diff > 0: delivered > invoiced -> Invoice to issue (Revenue)
                # If qty_diff < 0: invoiced > delivered -> Invoiced not delivered (Deferred Revenue)
                amount = abs(qty_diff * line.price_unit)
                total_amount += amount if qty_diff > 0 else -amount
                
                # Product Income account
                account = line.product_id.property_account_income_id or line.product_id.categ_id.property_account_income_categ_id
                if not account:
                    raise UserError(_("No income account defined for product %s.", line.product_id.display_name))
                
                label = f"{line.order_id.name} - {line.name}; {line.qty_invoiced} Invoiced, {line.qty_delivered} Delivered at {line.price_unit} each"
                
                preview_lines.append((0, 0, {
                    'account_id': account.id,
                    'name': label,
                    'debit': amount if qty_diff < 0 else 0.0,
                    'credit': amount if qty_diff > 0 else 0.0,
                }))

        res['preview_line_ids'] = preview_lines
        return res

    @api.depends('preview_line_ids')
    def _compute_amount_total(self):
        for wiz in self:
            total_debit = sum(wiz.preview_line_ids.mapped('debit'))
            total_credit = sum(wiz.preview_line_ids.mapped('credit'))
            wiz.amount_total = total_debit - total_credit

    def _compute_currency_id(self):
        for wiz in self:
            wiz.currency_id = self.env.company.currency_id

    def create_entries(self):
        self.ensure_one()
        if not self.preview_line_ids:
            raise UserError(_("No accrual lines to create."))

        move_lines = []
        total_debit = 0.0
        total_credit = 0.0

        for pl in self.preview_line_ids:
            move_lines.append((0, 0, {
                'account_id': pl.account_id.id,
                'name': pl.name,
                'debit': pl.debit,
                'credit': pl.credit,
            }))
            total_debit += pl.debit
            total_credit += pl.credit

        # Add the balancing line for the Accrual Account
        balance = total_debit - total_credit
        if balance != 0:
            move_lines.append((0, 0, {
                'account_id': self.account_id.id,
                'name': _("Accrued Total"),
                'debit': -balance if balance < 0 else 0.0,
                'credit': balance if balance > 0 else 0.0,
            }))

        move_vals = {
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'date': self.date,
            'line_ids': move_lines,
        }
        
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        
        if self.reversal_date:
            move._reverse_moves([{'date': self.reversal_date, 'journal_id': self.journal_id.id}], cancel=True)
            
        return {'type': 'ir.actions.act_window_close'}


class HudsonAccountAccruedOrdersWizardLine(models.TransientModel):
    _name = 'hudson.account.accrued.orders.wizard.line'
    _description = 'Accrued Orders Wizard Line'

    wizard_id = fields.Many2one('hudson.account.accrued.orders.wizard', required=True, ondelete='cascade')
    account_id = fields.Many2one('account.account', string='Account', required=True)
    name = fields.Char(string='Label')
    debit = fields.Float(string='Debit')
    credit = fields.Float(string='Credit')


class AccountAccruedOrdersWizard(models.TransientModel):
    _inherit = 'account.accrued.orders.wizard'

    def create_entries(self):
        # Prevent Duplicates
        active_model = self.env.context.get('active_model')
        active_ids = self.env.context.get('active_ids')
        orders = self.env[active_model].browse()
        if active_model in ['purchase.order', 'sale.order']:
            orders = self.env[active_model].browse(active_ids)
        elif active_model in ['purchase.order.line', 'sale.order.line']:
            lines = self.env[active_model].browse(active_ids)
            orders = lines.mapped('order_id')
            
        for order in orders:
            # Check for existing active accrual moves for the same date
            active_accruals = order.hudson_accrual_move_ids.filtered(
                lambda m: m.state == 'posted' and not m.reversed_entry_id and m.date == self.date
            )
            if active_accruals:
                raise UserError(_("An active accrual entry already exists for order %s on %s. You cannot create a duplicate.", order.name, self.date))

        # Create entries using standard logic
        res = super().create_entries()
        
        # Extract the created move IDs from the action domain
        domain = res.get('domain', [])
        if domain and len(domain) > 0 and domain[0][0] == 'id' and domain[0][1] == 'in':
            move_ids = domain[0][2]
            moves = self.env['account.move'].browse(move_ids)
            for order in orders:
                order.hudson_accrual_move_ids = [(4, m.id) for m in moves]
                
        return res
