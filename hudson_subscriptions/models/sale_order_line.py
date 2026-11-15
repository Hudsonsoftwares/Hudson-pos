# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    recurring_monthly = fields.Monetary(
        string='Monthly Subtotal',
        compute='_compute_recurring_monthly',
        store=True,
        currency_field='currency_id',
        help='Monthly Recurring Revenue contribution of this line'
    )

    @api.depends('product_id', 'product_uom_id', 'product_uom_qty')
    def _compute_pricelist_item_id(self):
        for line in self:
            if line.order_id.is_subscription and line.order_id.plan_id:
                line = line.with_context(subscription_plan_id=line.order_id.plan_id.id)
            super(SaleOrderLine, line)._compute_pricelist_item_id()

    @api.depends('price_subtotal', 'order_id.plan_id', 'order_id.plan_id.billing_period_value', 'order_id.plan_id.billing_period_unit')
    def _compute_recurring_monthly(self):
        for line in self:
            plan = line.order_id.plan_id
            if not line.order_id.is_subscription or not plan or plan.billing_period_value <= 0:
                line.recurring_monthly = line.price_subtotal or 0.0
                continue
            val = plan.billing_period_value
            unit = plan.billing_period_unit
            total = line.price_subtotal
            if unit == 'days':
                line.recurring_monthly = (total / val) * 30.0
            elif unit == 'weeks':
                line.recurring_monthly = (total / val) * 4.3333
            elif unit == 'months':
                line.recurring_monthly = total / val
            elif unit == 'years':
                line.recurring_monthly = total / (val * 12.0)
            else:
                line.recurring_monthly = total

    @api.onchange('product_id')
    def _onchange_product_subscription(self):
        if self.product_id and self.product_id.recurring_invoice:
            self.order_id.is_subscription = True
            if self.product_id.subscription_plan_id and not self.order_id.plan_id:
                self.order_id.plan_id = self.product_id.subscription_plan_id
