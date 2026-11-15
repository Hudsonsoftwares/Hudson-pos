# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import models, api, fields
from odoo.fields import Command
from odoo.tools import str2bool
import logging

_logger = logging.getLogger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _check_amount_and_confirm_order(self):
        """ Override to ensure subscription orders are automatically confirmed
            and invoiced upon payment confirmation, matching Enterprise edition behavior. """
        confirmed_orders = super()._check_amount_and_confirm_order()

        for tx in self.filtered(lambda t: t.state in ('done', 'authorized')):
            for order in tx.sale_order_ids.filtered(lambda so: so.is_subscription):
                # 1. Confirm the quotation if not already confirmed
                if order.state in ('draft', 'sent'):
                    _logger.info("Automatically confirming subscription order %s for payment transaction %s", order.name, tx.reference)
                    order.with_context(send_email=True).action_confirm()
                    confirmed_orders |= order

                # 2. Set subscription to in_progress
                if order.subscription_state in ('draft', 'sent'):
                    order.subscription_state = '3_progress'
                    if not order.start_date:
                        order.start_date = fields.Date.context_today(order)
                    if not order.next_invoice_date and order.plan_id:
                        order.next_invoice_date = order.plan_id.get_next_date(order.start_date)

                # 3. Always force initial invoice generation for subscription orders
                auto_invoice = str2bool(
                    self.env['ir.config_parameter'].sudo().get_param('sale.automatic_invoice')
                )
                if not auto_invoice:
                    tx._invoice_sale_orders()

        return confirmed_orders

    def _post_process(self):
        """ Override of payment.transaction post-processing to ensure that
            initial subscription invoices are created, posted, and reconciled
            with the payment transaction. """
        # Pre-process subscription orders before super post-processing
        for tx in self.filtered(lambda t: t.state == 'done'):
            subscription_orders = tx.sale_order_ids.filtered(lambda so: so.is_subscription)
            for order in subscription_orders:
                if order.state in ('draft', 'sent'):
                    order.with_context(send_email=True).action_confirm()
                if order.subscription_state in ('draft', 'sent'):
                    order.subscription_state = '3_progress'
                    if not order.start_date:
                        order.start_date = fields.Date.context_today(order)
                    if not order.next_invoice_date and order.plan_id:
                        order.next_invoice_date = order.plan_id.get_next_date(order.start_date)

                # Ensure order lines are set to invoiceable
                order._force_lines_to_invoice_policy_order()

                # Generate invoice if none exists yet
                if not order.invoice_ids:
                    invoices = order.with_context(raise_if_nothing_to_invoice=False)._create_invoices(final=True)
                    for invoice in invoices:
                        invoice._portal_ensure_token()
                    if invoices:
                        tx.invoice_ids = [Command.set(invoices.ids)]
                else:
                    tx.invoice_ids = [Command.set(order.invoice_ids.ids)]

        res = super()._post_process()

        # Post-process: ensure any subscription invoices in draft are posted and payments reconciled
        for tx in self.filtered(lambda t: t.state == 'done'):
            subscription_orders = tx.sale_order_ids.filtered(lambda so: so.is_subscription)
            for order in subscription_orders:
                draft_invoices = order.invoice_ids.filtered(lambda inv: inv.state == 'draft')
                if draft_invoices:
                    draft_invoices.action_post()
                if not tx.payment_id and order.invoice_ids:
                    try:
                        tx.with_company(tx.company_id)._create_payment()
                    except Exception as e:
                        _logger.warning("Could not auto-create payment for tx %s: %s", tx.reference, e)

        return res
