# -*- coding: utf-8 -*-
# pyrefly: ignore[missing-import]
from odoo import models, fields, _
# pyrefly: ignore[missing-import]
from odoo.exceptions import UserError

class HelpdeskTicketRefund(models.TransientModel):
    _name = 'helpdesk.ticket.refund'
    _description = 'Refund Wizard'

    ticket_id = fields.Many2one('helpdesk.management.ticket', required=True)
    sale_order_id = fields.Many2one('sale.order', string='Sales Order')
    product_id = fields.Many2one('product.product', string='Product')
    lot_id = fields.Many2one('stock.lot', string='Lot/Serial Number')
    journal_id = fields.Many2one('account.journal', string='Journal', domain=[('type', '=', 'sale')])
    reversal_date = fields.Date(string='Reversal date', default=fields.Date.context_today)

    def action_reverse(self):
        self.ensure_one()
        if not self.sale_order_id or not self.product_id:
            return {'type': 'ir.actions.act_window_close'}
            
        sale_line = self.sale_order_id.order_line.filtered(lambda l: l.product_id.id == self.product_id.id)
        price_unit = sale_line[0].price_unit if sale_line else self.product_id.lst_price

        journal = self.journal_id or self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
        if not journal:
            raise UserError(_("Please configure at least one Sales Journal to create a Credit Note."))

        move = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': self.ticket_id.partner_id.id,
            'invoice_origin': self.sale_order_id.name,
            'journal_id': journal.id,
            'invoice_date': self.reversal_date,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product_id.id,
                'quantity': 1.0,
                'price_unit': price_unit,
            })]
        })
        self.ticket_id.message_post(body=f"Credit Note Created: {move.name}")
        return {
            'name': _('Credit Note'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
        }


class HelpdeskTicketGiftcard(models.TransientModel):
    _name = 'helpdesk.ticket.giftcard'
    _description = 'Gift Card Wizard'

    ticket_id = fields.Many2one('helpdesk.management.ticket', required=True)
    program_id = fields.Many2one('loyalty.program', string='Program', domain=[('program_type', '=', 'gift_card')])
    gift_card_value = fields.Float(string='Gift Card value', default=1.00)
    valid_until = fields.Date(string='Valid Until')
    description = fields.Char(string='Description', default='Example: Gift for customer')

    def action_generate(self):
        self.ensure_one()
        if not self.program_id:
            return {'type': 'ir.actions.act_window_close'}
            
        card = self.env['loyalty.card'].create({
            'program_id': self.program_id.id,
            'partner_id': self.ticket_id.partner_id.id,
            'points': self.gift_card_value,
        })
        self.ticket_id.message_post(body=f"Gift Card Created: {card.code} for value {self.gift_card_value}")
        return {
            'name': _('Gift Card'),
            'type': 'ir.actions.act_window',
            'res_model': 'loyalty.card',
            'res_id': card.id,
            'view_mode': 'form',
        }


class HelpdeskTicketCoupon(models.TransientModel):
    _name = 'helpdesk.ticket.coupon'
    _description = 'Coupon Wizard'

    ticket_id = fields.Many2one('helpdesk.management.ticket', required=True)
    program_id = fields.Many2one('loyalty.program', string='Coupon Program', domain=[('program_type', '=', 'coupons')])
    valid_until = fields.Date(string='Valid Until')

    def _create_coupon(self):
        self.ensure_one()
        return self.env['loyalty.card'].create({
            'program_id': self.program_id.id,
            'partner_id': self.ticket_id.partner_id.id,
            'points': 1,
        })

    def action_send_email(self):
        self.ensure_one()
        if not self.program_id:
            return {'type': 'ir.actions.act_window_close'}
            
        card = self._create_coupon()
        self.ticket_id.message_post(body=f"Coupon Created and sent to customer: {card.code}")
        mail_template = self.env.ref('loyalty.mail_template_loyalty_card', raise_if_not_found=False)
        if mail_template:
            mail_template.send_mail(card.id)
            
        return {'type': 'ir.actions.act_window_close'}

    def action_get_share_link(self):
        self.ensure_one()
        if not self.program_id:
            return {'type': 'ir.actions.act_window_close'}
        card = self._create_coupon()
        self.ticket_id.message_post(body=f"Coupon Created: {card.code}")
        return {
            'name': _('Coupon'),
            'type': 'ir.actions.act_window',
            'res_model': 'loyalty.card',
            'res_id': card.id,
            'view_mode': 'form',
        }


class HelpdeskTicketReturn(models.TransientModel):
    _name = 'helpdesk.ticket.return'
    _description = 'Return Wizard'

    ticket_id = fields.Many2one('helpdesk.management.ticket', required=True)
    sale_order_id = fields.Many2one('sale.order', string='Sales Order')
    picking_id = fields.Many2one('stock.picking', string='Delivery to Return', domain="[('sale_id', '=', sale_order_id), ('state', '=', 'done')]")

    def action_return(self):
        # Trigger the standard stock return picking wizard
        self.ensure_one()
        if not self.picking_id:
            return {'type': 'ir.actions.act_window_close'}
        
        return {
            'name': _('Reverse Transfer'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.return.picking',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.picking_id.id,
                'active_ids': [self.picking_id.id],
                'active_model': 'stock.picking',
            }
        }
