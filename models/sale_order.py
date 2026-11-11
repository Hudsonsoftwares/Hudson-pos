# pyrefly: ignore [missing-import]
from odoo import models

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _action_confirm(self):
        res = super()._action_confirm()
        
        # Batch lookup all pending bookings linked to confirmed orders
        bookings = self.env['appointment.booking'].search([
            ('sale_order_id', 'in', self.ids),
            ('state', '=', 'pending_payment')
        ])
        
        if bookings:
            bookings.write({'state': 'confirmed'})
            
            template = self.env.ref('appointment.email_template_booking_confirmation', raise_if_not_found=False)
            if template:
                for booking in bookings:
                    template.sudo().send_mail(booking.id, force_send=False)
                    
        return res
