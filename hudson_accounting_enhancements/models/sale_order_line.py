from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    hudson_accrual_move_ids = fields.Many2many(
        'account.move',
        'sale_order_hudson_accrual_rel',
        'order_id', 'move_id',
        string='Accrual Moves',
        copy=False,
    )

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    hudson_invoiced_not_delivered = fields.Boolean(
        string='Invoiced Not Delivered',
        compute='_compute_hudson_invoiced_not_delivered',
        search='_search_hudson_invoiced_not_delivered',
        store=False,
    )

    @api.depends('qty_invoiced', 'qty_delivered')
    def _compute_hudson_invoiced_not_delivered(self):
        for line in self:
            line.hudson_invoiced_not_delivered = line.qty_invoiced > line.qty_delivered

    def _search_hudson_invoiced_not_delivered(self, operator, value):
        if operator == '=' and value:
            self.env.cr.execute('''
                SELECT id 
                FROM sale_order_line 
                WHERE qty_invoiced > qty_delivered 
                  AND state IN ('sale', 'done')
            ''')
            ids = [row[0] for row in self.env.cr.fetchall()]
            return [('id', 'in', ids)]
        return []

    def action_open_order(self):
        self.ensure_one()
        return {
            'name': self.order_id.name or 'Sale Order',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_invoices(self):
        self.ensure_one()
        invoices = self.order_id.invoice_ids
        if not invoices:
            return self.action_open_order()
        if len(invoices) == 1:
            return {
                'name': invoices.name or 'Customer Invoice',
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': invoices.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'name': 'Customer Invoices',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'domain': [('id', 'in', invoices.ids)],
            'view_mode': 'list,form',
            'target': 'current',
        }

    def action_open_accrual_wizard(self):
        return {
            'name': 'Create Accrual Entries',
            'type': 'ir.actions.act_window',
            'res_model': 'account.accrued.orders.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_ids': self.ids,
                'active_model': 'sale.order.line',
                'default_date': fields.Date.context_today(self),
            }
        }
