# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _action_confirm_appointment_bookings(self):
        """After the stock appointment flow confirmed the paid bookings (and
        queued its confirmation email), send the guest SMS once and flag the
        booking as notified so the bridge never sends a second confirmation."""
        bookings = self.env['appointment.booking'].sudo().search([
            ('sale_order_id', 'in', self.ids),
            ('state', '=', 'pending_payment'),
        ])
        res = super()._action_confirm_appointment_bookings()
        bookings.filtered(lambda b: b.state in ('confirmed', 'checked_in'))._send_booking_confirmation_notifications(
            send_email=False)
        return res


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _post_process(self):
        """Paid booking / pre-order: confirm the quotation, invoice it and
        confirm + notify the booking (guest may have no email: SMS only)."""
        super()._post_process()
        Booking = self.env['appointment.booking'].sudo()
        for tx in self.filtered(lambda t: t.state == 'done'):
            for so in tx.sale_order_ids:
                booking = Booking.search([('sale_order_id', '=', so.id)], limit=1)
                if not booking:
                    continue
                so_sudo = so.sudo().with_context(mail_activity_automation_skip=True, tracking_disable=True)
                if so_sudo.state in ('draft', 'sent'):
                    try:
                        with self.env.cr.savepoint():
                            so_sudo.action_confirm()
                    except Exception as err:
                        _logger.warning("Error confirming SO %s on payment transaction %s: %s", so_sudo.id, tx.id, err)
                if not so_sudo.invoice_ids:
                    try:
                        with self.env.cr.savepoint():
                            for line in so_sudo.order_line:
                                if not line.qty_delivered:
                                    line.qty_delivered = line.product_uom_qty
                            invoices = so_sudo._create_invoices()
                            invoices.action_post()
                    except Exception as err:
                        _logger.warning("Error invoicing SO %s on payment transaction %s: %s", so_sudo.id, tx.id, err)
                try:
                    if booking.state == 'pending_payment':
                        booking.write({'state': 'confirmed'})
                    if booking.state in ('confirmed', 'checked_in') and not booking.confirmation_sent:
                        booking._send_booking_confirmation_notifications()
                except Exception as err:
                    _logger.error("Error confirming booking %s after payment: %s", booking.id, err)
