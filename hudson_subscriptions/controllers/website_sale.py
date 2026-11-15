# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import http, fields
from odoo.http import request
from odoo.fields import Command
from odoo.addons.website_sale.controllers.cart import Cart
from odoo.addons.website_sale.controllers.main import WebsiteSale
import logging

_logger = logging.getLogger(__name__)


class SubscriptionCart(Cart):
    """Extend the eCommerce cart controller to handle subscription plan selection."""

    @http.route(
        route='/shop/cart/add',
        type='jsonrpc',
        auth='public',
        methods=['POST'],
        website=True,
        sitemap=False,
    )
    def add_to_cart(self, product_template_id, product_id, quantity=1.0, uom_id=None,
                    product_custom_attribute_values=None, no_variant_attribute_value_ids=None,
                    linked_products=None, **kwargs):
        """Override to handle subscription_plan_id passed from the product page."""
        subscription_plan_id = kwargs.pop('subscription_plan_id', None)

        # Call standard add-to-cart
        result = super().add_to_cart(
            product_template_id=product_template_id,
            product_id=product_id,
            quantity=quantity,
            uom_id=uom_id,
            product_custom_attribute_values=product_custom_attribute_values,
            no_variant_attribute_value_ids=no_variant_attribute_value_ids,
            linked_products=linked_products,
            **kwargs,
        )

        # After adding, apply the selected subscription plan to the order
        if subscription_plan_id:
            try:
                plan_id = int(subscription_plan_id)
                order = request.cart
                if order:
                    plan = request.env['sale.subscription.plan'].sudo().browse(plan_id)
                    if plan.exists():
                        # Set plan and mark as subscription on the order
                        order.sudo().write({
                            'is_subscription': True,
                            'plan_id': plan_id,
                        })
                        # Recompute prices now that plan is set
                        for line in order.sudo().order_line.filtered(
                            lambda l: l.product_id.id == int(product_id)
                        ):
                            line.sudo()._compute_pricelist_item_id()
                            line.sudo()._compute_price_unit()
            except Exception as e:
                _logger.warning("Error applying subscription plan to cart: %s", e)

        return result


class WebsiteSaleSubscription(WebsiteSale):
    """Extend the eCommerce checkout validate route to ensure subscription orders
    and invoices are fully confirmed and posted upon checkout completion."""

    @http.route('/shop/payment/validate', type='http', auth="public", website=True, sitemap=False)
    def shop_payment_validate(self, sale_order_id=None, **post):
        # Retrieve the order before reset
        order_id = sale_order_id or request.session.get('sale_last_order_id')
        order_sudo = request.env['sale.order'].sudo().browse(order_id).exists() if order_id else None

        res = super().shop_payment_validate(sale_order_id=sale_order_id, **post)

        if order_sudo and order_sudo.is_subscription:
            tx_sudo = order_sudo.get_portal_last_transaction()
            if tx_sudo and tx_sudo.state in ('done', 'authorized'):
                # 1. Trigger post_process if not done yet
                if not tx_sudo.is_post_processed:
                    try:
                        tx_sudo._post_process()
                    except Exception as e:
                        _logger.warning("Error running tx._post_process in shop_payment_validate: %s", e)

                # 2. Ensure order is confirmed
                if order_sudo.state in ('draft', 'sent'):
                    try:
                        order_sudo.with_context(send_email=True).action_confirm()
                    except Exception as e:
                        _logger.warning("Error confirming subscription order %s: %s", order_sudo.name, e)

                # 3. Ensure subscription status is set to in_progress
                if order_sudo.subscription_state in ('draft', 'sent'):
                    vals = {'subscription_state': '3_progress'}
                    if not order_sudo.start_date:
                        vals['start_date'] = fields.Date.context_today(order_sudo)
                    if not order_sudo.next_invoice_date and order_sudo.plan_id:
                        vals['next_invoice_date'] = order_sudo.plan_id.get_next_date(vals.get('start_date', order_sudo.start_date))
                    order_sudo.write(vals)

                # 4. Ensure initial invoice is created & posted
                if not order_sudo.invoice_ids:
                    try:
                        order_sudo._force_lines_to_invoice_policy_order()
                        invoices = order_sudo.with_context(raise_if_nothing_to_invoice=False)._create_invoices(final=True)
                        for inv in invoices:
                            inv.action_post()
                            inv._portal_ensure_token()
                        if invoices and not tx_sudo.payment_id:
                            tx_sudo.invoice_ids = [Command.set(invoices.ids)]
                            tx_sudo.with_company(tx_sudo.company_id)._create_payment()
                    except Exception as e:
                        _logger.warning("Error generating initial invoice for subscription %s: %s", order_sudo.name, e)
                else:
                    for inv in order_sudo.invoice_ids.filtered(lambda i: i.state == 'draft'):
                        try:
                            inv.action_post()
                        except Exception as e:
                            _logger.warning("Error posting draft invoice %s: %s", inv.name, e)
                    if not tx_sudo.payment_id:
                        try:
                            tx_sudo.with_company(tx_sudo.company_id)._create_payment()
                        except Exception as e:
                            _logger.warning("Error creating payment for tx %s: %s", tx_sudo.reference, e)

        return res
