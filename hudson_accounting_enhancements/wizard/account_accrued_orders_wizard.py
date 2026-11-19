from dateutil.relativedelta import relativedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


def _first_day_of_next_period(day):
    return day + relativedelta(months=1, day=1)


class HudsonAccountAccruedOrdersWizard(models.TransientModel):
    _name = 'hudson.account.accrued.orders.wizard'
    _description = 'Accrued Orders Wizard'

    order_type = fields.Selection([('purchase', 'Purchase'), ('sale', 'Sale')], string="Order Type", required=True)
    journal_id = fields.Many2one('account.journal', string='Journal', required=True, domain="[('type', '=', 'general')]")
    account_id = fields.Many2one('account.account', string='Accrual Account', required=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    reversal_date = fields.Date(
        string='Reversal Date', required=True,
        compute='_compute_reversal_date', store=True, readonly=False, precompute=True,
        help="Date of the entry reversing the accrual, the first day of the next period by default.")
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
        company = self.env.company
        accrual_date = res.get('date') or fields.Date.context_today(self)
        preview_lines = []
        for line in lines:
            vals = self._prepare_preview_line_vals(line, order_type, company, accrual_date)
            if vals:
                preview_lines.append((0, 0, vals))

        res['preview_line_ids'] = preview_lines
        return res

    @api.model
    def _prepare_preview_line_vals(self, line, order_type, company, accrual_date):
        """ Accrual line of an order line: the quantity received (delivered) but not billed (invoiced) yet,
        or billed but not received, at its net price (discount included), converted from the currency of
        the order to the company currency at the accrual date, with the analytic distribution of the line.

        Amounts follow the expense/income account: received not billed debits the expense, delivered not
        invoiced credits the income; billed (invoiced) but not received (delivered) the other way round.
        """
        order = line.order_id
        if order_type == 'purchase':
            qty_done, label_done, label_invoiced = line.qty_received, _("Received"), _("Billed")
        else:
            qty_done, label_done, label_invoiced = line.qty_delivered, _("Delivered"), _("Invoiced")
        qty_diff = qty_done - line.qty_invoiced
        precision = self.env['decimal.precision'].precision_get('Product Unit')
        if float_is_zero(qty_diff, precision_digits=precision):
            return {}
        net_price = line.price_unit * (1.0 - (line.discount or 0.0) / 100.0)
        currency = order.currency_id or company.currency_id
        amount_currency = currency.round(qty_diff * net_price)
        balance = company.currency_id.round(
            currency._convert(amount_currency, company.currency_id, company, accrual_date))
        if company.currency_id.is_zero(balance):
            return {}

        accounts = line.product_id.with_company(order.company_id).product_tmpl_id.get_product_accounts(
            fiscal_pos=order.fiscal_position_id)
        if order_type == 'purchase':
            account = accounts['expense']
            if not account:
                raise UserError(_("No expense account defined for product %s.", line.product_id.display_name))
        else:
            account = accounts['income']
            if not account:
                raise UserError(_("No income account defined for product %s.", line.product_id.display_name))
            balance, amount_currency = -balance, -amount_currency

        label = _(
            "%(order)s - %(line)s; %(invoiced)s %(invoiced_label)s, %(done)s %(done_label)s at %(price)s each",
            order=order.name, line=line.name, invoiced=line.qty_invoiced, invoiced_label=label_invoiced,
            done=qty_done, done_label=label_done, price=net_price,
        )
        return {
            'account_id': account.id,
            'name': label,
            'debit': balance if balance > 0 else 0.0,
            'credit': -balance if balance < 0 else 0.0,
            'amount_currency': amount_currency,
            'line_currency_id': currency.id,
            'analytic_distribution': line.analytic_distribution or False,
        }

    @api.depends('date')
    def _compute_reversal_date(self):
        for wiz in self:
            if wiz.date and (not wiz.reversal_date or wiz.reversal_date <= wiz.date):
                wiz.reversal_date = _first_day_of_next_period(wiz.date)
            else:
                wiz.reversal_date = wiz.reversal_date

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
        if self.reversal_date <= self.date:
            raise UserError(_('Reversal date must be posterior to date.'))

        company_currency = self.env.company.currency_id
        move_lines = []
        total_debit = 0.0
        total_credit = 0.0

        for pl in self.preview_line_ids:
            vals = {
                'account_id': pl.account_id.id,
                'name': pl.name,
                'debit': pl.debit,
                'credit': pl.credit,
            }
            if pl.line_currency_id and pl.line_currency_id != company_currency:
                vals.update({'currency_id': pl.line_currency_id.id, 'amount_currency': pl.amount_currency})
            if pl.analytic_distribution:
                vals['analytic_distribution'] = pl.analytic_distribution
            move_lines.append((0, 0, vals))
            total_debit += pl.debit
            total_credit += pl.credit

        # Add the balancing line for the Accrual Account
        balance = company_currency.round(total_debit - total_credit)
        if not company_currency.is_zero(balance):
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

        # like Odoo: the reversal is posted on its own date by the auto-post job, not right away
        reverse_move = move._reverse_moves([{
            'date': self.reversal_date,
            'journal_id': self.journal_id.id,
            'ref': _('Reversal of: %s', move.ref or move.name),
            'auto_post': 'at_date',
        }])
        reverse_move._post(soft=True)

        return {'type': 'ir.actions.act_window_close'}


class HudsonAccountAccruedOrdersWizardLine(models.TransientModel):
    _name = 'hudson.account.accrued.orders.wizard.line'
    _description = 'Accrued Orders Wizard Line'

    wizard_id = fields.Many2one('hudson.account.accrued.orders.wizard', required=True, ondelete='cascade')
    account_id = fields.Many2one('account.account', string='Account', required=True)
    name = fields.Char(string='Label')
    debit = fields.Float(string='Debit')
    credit = fields.Float(string='Credit')
    line_currency_id = fields.Many2one('res.currency', string='Currency')
    amount_currency = fields.Monetary(string='Amount in Currency', currency_field='line_currency_id')
    analytic_distribution = fields.Json(string='Analytic Distribution')


class AccountAccruedOrdersWizard(models.TransientModel):
    _inherit = 'account.accrued.orders.wizard'

    @api.depends('date')
    def _compute_reversal_date(self):
        # the accrual is reversed on the first day of the next period (Odoo: the day after the accrual,
        # which is the same day when the accrual is dated on the last day of a month)
        for record in self:
            if record.date and (not record.reversal_date or record.reversal_date <= record.date):
                record.reversal_date = _first_day_of_next_period(record.date)
            else:
                record.reversal_date = record.reversal_date

    def create_entries(self, auto_post=True):
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
        res = super().create_entries(auto_post=auto_post)

        # Extract the created move IDs from the action domain
        domain = res.get('domain', [])
        if domain and len(domain) > 0 and domain[0][0] == 'id' and domain[0][1] == 'in':
            move_ids = domain[0][2]
            moves = self.env['account.move'].browse(move_ids)
            for order in orders:
                order.hudson_accrual_move_ids = [(4, m.id) for m in moves]

        return res
