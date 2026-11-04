# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

class PosOrder(models.Model):
    _inherit = 'pos.order'

    is_delivery_order = fields.Boolean(string='Is Delivery Order', default=False, index=True)
    delivery_platform_id = fields.Many2one('pos.delivery.platform', string='Delivery Platform', index=True)
    delivery_order_ref = fields.Char(string='External Order ID / Ref', copy=False, index=True)
    delivery_customer_name = fields.Char(string='Delivery Customer')
    delivery_customer_phone = fields.Char(string='Delivery Phone')
    delivery_customer_address = fields.Text(string='Delivery Address')
    delivery_rider_name = fields.Char(string='Rider / Driver Name')
    delivery_rider_phone = fields.Char(string='Rider Phone')
    delivery_instructions = fields.Text(string='Delivery Instructions / Notes')
    delivery_prep_time = fields.Integer(string='Preparation Time (Mins)', default=20)
    
    delivery_status = fields.Selection([
        ('new', 'New'),
        ('accepted', 'Accepted'),
        ('preparing', 'Preparing'),
        ('ready', 'Ready for Pickup'),
        ('dispatched', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled')
    ], string='Delivery Status', default='new')

    def action_accept_delivery_order(self):
        for order in self:
            order.write({'delivery_status': 'accepted'})
        return True

    def action_ready_delivery_order(self):
        for order in self:
            order.write({'delivery_status': 'ready'})
        return True

    def action_dispatch_delivery_order(self):
        for order in self:
            order.write({'delivery_status': 'dispatched'})
        return True

    def action_complete_delivery_order(self):
        for order in self:
            order.write({'delivery_status': 'delivered'})
        return True

    def action_cancel_delivery_order(self):
        for order in self:
            order.write({'delivery_status': 'cancelled'})
        return True
