# pyrefly: ignore [missing-import]
from odoo import models, api

class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    @api.model_create_multi
    def create(self, vals_list):
        references = [vals.get('reference') for vals in vals_list if vals.get('reference')]
        
        if references:
            sale_orders = self.env['sale.order'].search([('name', 'in', references)])
            so_by_ref = {so.name: so for so in sale_orders}
            
            if sale_orders:
                bookings = self.env['appointment.booking'].search([('sale_order_id', 'in', sale_orders.ids)])
                booking_by_so = {booking.sale_order_id.id: booking for booking in bookings}
            else:
                booking_by_so = {}
                
            for vals in vals_list:
                ref = vals.get('reference')
                if ref and ref in so_by_ref:
                    so = so_by_ref[ref]
                    vals['sale_order_ids'] = [(4, so.id)]
                    
                    booking = booking_by_so.get(so.id)
                    if booking:
                        vals['landing_route'] = f'/appointment/manage/{booking.id}?token={booking.access_token}'
        
        return super().create(vals_list)
