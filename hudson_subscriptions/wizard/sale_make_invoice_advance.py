# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import models


class SaleAdvancePaymentInv(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    def _create_invoices(self, sale_orders):
        """Running subscriptions are billed per period, not per delivery.

        The standard "Create invoices" wizard (also reachable from the list
        view Action menu) invoices delivered quantities only, so a service
        with the "Delivered Quantities" policy raises "No items are available
        to invoice". Route those orders through the recurring invoicer.
        """
        if self.advance_payment_method != 'delivered':
            return super()._create_invoices(sale_orders)
        subscriptions = sale_orders.filtered(
            lambda o: o.is_subscription and o.state == 'sale'
            and o.subscription_state in ('3_progress', '5_renew', '7_upsell')
        )
        invoices = self.env['account.move']
        for order in subscriptions:
            invoices |= order._create_subscription_invoice()
        others = sale_orders - subscriptions
        if others:
            invoices |= super()._create_invoices(others)
        return invoices
