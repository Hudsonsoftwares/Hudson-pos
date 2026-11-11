# pyrefly: ignore [missing-import]
from odoo.addons.payment.controllers.payment_status import PaymentStatus
# pyrefly: ignore [missing-import]
from odoo import http
# pyrefly: ignore [missing-import]
from odoo.http import request

class AppointmentPaymentPostProcessing(PaymentStatus):

    @http.route('/payment/status', type='http', auth='public', website=True, sitemap=False)
    def display_status(self, **kwargs):
        # We intercept the display_status route to bypass it completely for Appointments
        tx_id = request.session.get('__payment_monitored_tx_id__')
        if tx_id:
            tx = request.env['payment.transaction'].sudo().browse(tx_id)
            if tx.exists() and tx.sale_order_ids:
                # Check if this sale order belongs to an appointment booking
                booking = request.env['appointment.booking'].sudo().search([('sale_order_id', 'in', tx.sale_order_ids.ids)], limit=1)
                if booking and booking.state != 'pending_payment':
                    # If it's an appointment and the payment succeeded (state changed from pending_payment),
                    # immediately redirect to the beautiful confirmation page instead of showing the "Skip" screen!
                    return request.redirect(f'/appointment/manage/{booking.id}?token={booking.access_token}')
                    
        # If it's a normal e-commerce order or a failed appointment payment, just show the normal status page
        return super().display_status(**kwargs)
