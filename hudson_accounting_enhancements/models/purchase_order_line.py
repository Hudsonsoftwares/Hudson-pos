from odoo import models, fields, api

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    hudson_accrual_move_ids = fields.Many2many(
        'account.move',
        'purchase_order_hudson_accrual_rel',
        'order_id', 'move_id',
        string='Accrual Moves',
        copy=False,
    )

class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    hudson_billed_not_received = fields.Boolean(
        string='Billed Not Received',
        compute='_compute_hudson_billed_not_received',
        search='_search_hudson_billed_not_received',
        store=False,
    )

    @api.depends('qty_invoiced', 'qty_received')
    def _compute_hudson_billed_not_received(self):
        for line in self:
            line.hudson_billed_not_received = line.qty_invoiced > line.qty_received

    def _search_hudson_billed_not_received(self, operator, value):
        if operator == '=' and value:
            self.env.cr.execute('''
                SELECT id 
                FROM purchase_order_line 
                WHERE qty_invoiced > qty_received 
                  AND state IN ('purchase', 'done')
            ''')
            ids = [row[0] for row in self.env.cr.fetchall()]
            return [('id', 'in', ids)]
        return []

    def action_open_order(self):
        self.ensure_one()
        return {
            'name': self.order_id.name or 'Purchase Order',
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
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
                'name': invoices.name or 'Vendor Bill',
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': invoices.id,
                'view_mode': 'form',
                'target': 'current',
            }
        return {
            'name': 'Vendor Bills',
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
                'active_model': 'purchase.order.line',
                'default_date': fields.Date.context_today(self),
            }
        }

    def _prepare_account_move_line(self, move=False):
        res = super(PurchaseOrderLine, self)._prepare_account_move_line(move=move)
        # Vendor refunds keep the standard quantity (based on what was over-billed/returned)
        if move and move.move_type == 'in_refund':
            return res
        # Override to always default the auto-complete quantity to the remaining ordered quantity,
        # instead of the received quantity (which is 0 for Billed Not Received cases).
        res['quantity'] = max(self.product_qty - self.qty_invoiced, 0)
        return res
