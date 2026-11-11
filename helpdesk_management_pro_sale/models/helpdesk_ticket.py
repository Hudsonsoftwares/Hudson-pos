# -*- coding: utf-8 -*-
from odoo import fields, models, _

class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.management.ticket'

    use_credit_notes = fields.Boolean(related='team_id.use_credit_notes')
    use_gift_cards = fields.Boolean(related='team_id.use_gift_cards')
    use_coupons = fields.Boolean(related='team_id.use_coupons')
    use_product_returns = fields.Boolean(related='team_id.use_product_returns')
    use_product_replacements = fields.Boolean(related='team_id.use_product_replacements')
    use_product_repairs = fields.Boolean(related='team_id.use_product_repairs')

    def action_open_refund_wizard(self):
        self.ensure_one()
        return {
            'name': _('Refund'),
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.ticket.refund',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ticket_id': self.id}
        }

    def action_open_gift_card_wizard(self):
        self.ensure_one()
        return {
            'name': _('Generate & Send Gift Card'),
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.ticket.giftcard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ticket_id': self.id}
        }

    def action_open_coupon_wizard(self):
        self.ensure_one()
        return {
            'name': _('Generate a Coupon'),
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.ticket.coupon',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ticket_id': self.id}
        }

    def action_return(self):
        self.ensure_one()
        return {
            'name': _('Return'),
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.ticket.return',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ticket_id': self.id}
        }

    def action_replace(self):
        self.ensure_one()
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'outgoing'),
            ('company_id', '=', self.company_id.id or self.env.company.id)
        ], limit=1)
        return {
            'name': _('New Delivery'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_picking_type_id': picking_type.id if picking_type else False,
                'default_origin': f'Ticket: {self.name}',
            }
        }

    def action_repair(self):
        self.ensure_one()
        return {
            'name': _('New Repair'),
            'type': 'ir.actions.act_window',
            'res_model': 'repair.order',
            'view_mode': 'form',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_company_id': self.company_id.id,
            }
        }

