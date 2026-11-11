from odoo import models, fields, api, _
from odoo.exceptions import UserError, RedirectWarning
from datetime import date

class HudsonInventoryValuationWizard(models.TransientModel):
    _name = 'hudson.inventory.valuation.wizard'
    _description = 'Inventory Valuation'
    _rec_name = 'display_name'

    display_name = fields.Char(string='Name', default='Inventory Valuation', compute='_compute_display_name')
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    as_of_date = fields.Date(string='As of', default=fields.Date.context_today, required=True)
    
    initial_balance = fields.Monetary(string='Initial Balance', compute='_compute_valuation', currency_field='currency_id')
    stock_variation = fields.Monetary(string='Stock Variation', compute='_compute_valuation', currency_field='currency_id')
    ending_stock = fields.Monetary(string='Ending Stock', compute='_compute_valuation', currency_field='currency_id')
    
    currency_id = fields.Many2one(related='company_id.currency_id')
    
    report_html = fields.Html(string='Report', compute='_compute_report_html', sanitize=False)

    @api.depends('as_of_date', 'company_id')
    def _compute_valuation(self):
        for wiz in self:
            if not wiz.as_of_date:
                wiz.initial_balance = 0.0
                wiz.stock_variation = 0.0
                wiz.ending_stock = 0.0
                continue
                
            val_account = wiz.company_id.hudson_stock_valuation_account_id
            if not val_account:
                wiz.initial_balance = 0.0
                wiz.stock_variation = 0.0
                wiz.ending_stock = 0.0
                continue
                
            # Initial Balance: GL balance up to the selected date
            domain = [
                ('account_id', '=', val_account.id),
                ('date', '<=', wiz.as_of_date),
                ('company_id', '=', wiz.company_id.id),
                ('parent_state', '=', 'posted')
            ]
            lines = self.env['account.move.line'].search_read(domain, ['balance'])
            wiz.initial_balance = sum(l['balance'] for l in lines)
            
            # Ending Stock: stock value at the end of the as-of day. Odoo 20 has no
            # stock.valuation.layer anymore; product.total_value computes it with `to_date`.
            company = wiz.company_id
            Product = self.env['product.product'].with_company(company).with_context(
                allowed_company_ids=company.ids, to_date=wiz.as_of_date)
            products = Product.search([
                ('is_storable', '=', True),
                *Product._check_company_domain(company),
            ])
            ending_stock = sum(products.mapped('total_value'))

            wiz.ending_stock = ending_stock
            wiz.stock_variation = ending_stock - wiz.initial_balance

    @api.depends('as_of_date')
    def _compute_display_name(self):
        for wiz in self:
            wiz.display_name = _("Inventory Valuation")

    @api.depends('initial_balance', 'stock_variation', 'ending_stock', 'company_id', 'as_of_date')
    def _compute_report_html(self):
        for wiz in self:
            val_acc = wiz.company_id.hudson_stock_valuation_account_id
            exp_acc = wiz.company_id.hudson_stock_expense_account_id
            
            val_code = f"{val_acc.code} {val_acc.name}" if val_acc else "Inventory Account Not Configured"
            exp_code = f"{exp_acc.code} {exp_acc.name}" if exp_acc else "Expense Account Not Configured"
            
            def format_monetary(amount):
                return wiz.currency_id.symbol + ' ' + f"{amount:,.2f}"

            variation_debit = wiz.stock_variation if wiz.stock_variation > 0 else 0.0
            variation_credit = -wiz.stock_variation if wiz.stock_variation < 0 else 0.0
            
            # Replicate Enterprise UI via HTML table
            html = f"""
            <div style="background-color: white; width: 100%; padding-top: 10px;">
                <table class="table table-sm table-borderless mb-0" style="width: 100%; table-layout: fixed;">
                    <tbody>
                        <!-- Initial Balance -->
                        <tr style="background-color: #e9ecef; font-weight: bold;">
                            <td colspan="2" style="color: #017e84; width: 50%;">Initial Balance</td>
                            <td class="text-end" colspan="2" style="width: 50%;">{format_monetary(wiz.initial_balance)}</td>
                        </tr>
                        <tr>
                            <td colspan="2" class="text-muted">{val_code}</td>
                            <td class="text-end" colspan="2" class="text-muted">{format_monetary(wiz.initial_balance)}</td>
                        </tr>
                        <tr><td colspan="4" style="border-bottom: 1px solid #e9ecef; height: 10px;"></td></tr>
                        
                        <!-- Stock Variation -->
                        <tr style="background-color: #e9ecef; font-weight: bold;">
                            <td colspan="2" style="color: #017e84;">Stock Variation</td>
                            <td class="text-end" colspan="2">{format_monetary(wiz.stock_variation)}</td>
                        </tr>
                        <tr class="text-muted" style="font-size: 0.9em;">
                            <td colspan="2"></td>
                            <td class="text-end" style="width: 25%;">Debit</td>
                            <td class="text-end" style="width: 25%;">Credit</td>
                        </tr>
                        <tr>
                            <td colspan="2" class="text-muted">{exp_code}</td>
                            <td class="text-end" class="text-muted">{format_monetary(variation_credit)}</td>
                            <td class="text-end" class="text-muted">{format_monetary(variation_debit)}</td>
                        </tr>
                        <tr>
                            <td colspan="2" class="text-muted">{val_code}</td>
                            <td class="text-end" class="text-muted">{format_monetary(variation_debit)}</td>
                            <td class="text-end" class="text-muted">{format_monetary(variation_credit)}</td>
                        </tr>
                        <tr><td colspan="4" style="border-bottom: 1px solid #e9ecef; height: 10px;"></td></tr>
                        
                        <!-- Ending Stock -->
                        <tr style="background-color: #e9ecef; font-weight: bold;">
                            <td colspan="2" style="color: #017e84;">Ending Stock</td>
                            <td class="text-end" colspan="2">{format_monetary(wiz.ending_stock)}</td>
                        </tr>
                        <tr>
                            <td colspan="2" class="text-muted">{val_code}</td>
                            <td class="text-end" colspan="2" class="text-muted">{format_monetary(wiz.ending_stock)}</td>
                        </tr>
                        <tr>
                            <td colspan="2"></td>
                            <td class="text-end" colspan="2" class="text-muted">{format_monetary(variation_credit)}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            """
            wiz.report_html = html

    def action_generate_entry(self):
        self.ensure_one()
        
        journal = self.company_id.hudson_stock_journal_id
        val_acc = self.company_id.hudson_stock_valuation_account_id
        exp_acc = self.company_id.hudson_stock_expense_account_id
        
        if not (journal and val_acc and exp_acc):
            action = self.env.ref('account.action_account_config')
            msg = _('Please configure the Inventory Valuation Settings (Journal, Valuation Account, Expense Account) in Accounting Settings before generating entries.')
            raise RedirectWarning(msg, action.id, _('Go to Settings'))
            
        if self.stock_variation == 0.0:
            raise UserError(_("There is no stock variation to post!"))
            
        move_vals = {
            'date': self.as_of_date,
            'journal_id': journal.id,
            'ref': 'Stock Closing',
            'line_ids': [
                (0, 0, {
                    'name': f'Closing: Stock Variation Global for company [{self.company_id.name}]',
                    'account_id': val_acc.id,
                    'debit': self.stock_variation if self.stock_variation > 0 else 0.0,
                    'credit': -self.stock_variation if self.stock_variation < 0 else 0.0,
                }),
                (0, 0, {
                    'name': f'Closing: Stock Variation Global for company [{self.company_id.name}]',
                    'account_id': exp_acc.id,
                    'debit': -self.stock_variation if self.stock_variation < 0 else 0.0,
                    'credit': self.stock_variation if self.stock_variation > 0 else 0.0,
                })
            ]
        }
        
        move = self.env['account.move'].create(move_vals)
        
        return {
            'name': _('Draft Entry (Stock Closing)'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
        }

    @api.model
    def action_open_inventory_valuation(self):
        wiz = self.search([
            ('company_id', '=', self.env.company.id)
        ], limit=1, order='id desc')
        if not wiz:
            wiz = self.create({
                'company_id': self.env.company.id,
                'as_of_date': fields.Date.context_today(self),
            })
        else:
            wiz.write({'as_of_date': fields.Date.context_today(self)})
        return {
            'name': _('Inventory Valuation'),
            'type': 'ir.actions.act_window',
            'res_model': 'hudson.inventory.valuation.wizard',
            'res_id': wiz.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'create': False, 'delete': False, 'duplicate': False},
        }

