# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import math

from odoo import models, fields, api

# Length of each rental period unit, in days
RENTAL_PERIOD_DAYS = {
    'hour': 1.0 / 24.0,
    'day': 1.0,
    'week': 7.0,
    'month': 30.0,
}


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Like Odoo's Rental app, a product is rentable as soon as it has a periodicity:
    # leaving it blank means "Not for Rent".
    rental_periodicity = fields.Selection([
        ('hour', 'Hours'),
        ('day', 'Days'),
        ('week', 'Weeks'),
        ('month', 'Months'),
    ], string='Periodicity',
        help='Rental period the sales price applies to. Leave empty if the product is not for rent.')
    rental_period_label = fields.Char(compute='_compute_rental_period_label')

    rental_pickup_time = fields.Float(
        string='Pickup',
        default=14.0
    )

    rental_return_time = fields.Float(
        string='Return',
        default=10.0
    )

    is_rental = fields.Boolean(
        string='Can be Rented',
        compute='_compute_is_rental',
        store=True,
        help='A product can be rented when a rental periodicity is set'
    )
    rent_ok = fields.Boolean(
        string='Rentable',
        related='is_rental',
    )
    rental_pricing_ids = fields.One2many(
        'rental.pricing',
        'product_tmpl_id',
        string='Rental Pricing'
    )
    rental_ok = fields.Boolean(
        string='Available for Rent',
        compute='_compute_rental_ok',
        store=True
    )
    min_rental_duration = fields.Float(
        string='Minimum Rental Duration (Days)',
        default=1.0,
        help='Minimum rental period required'
    )
    max_rental_duration = fields.Float(
        string='Maximum Rental Duration (Days)',
        default=365.0,
        help='Maximum rental period allowed'
    )
    rental_stock_available = fields.Float(
        string='Rental Stock Available',
        compute='_compute_rental_stock_available'
    )
    rental_order_count = fields.Integer(
        string='Rental Orders',
        compute='_compute_rental_order_count'
    )
    qty_in_rent = fields.Float(
        string='In Rental',
        compute='_compute_qty_in_rent',
        digits='Product Unit',
    )
    late_fee_per_day = fields.Float(
        string='Late Fee Per Day',
        help='Additional fee charged per day if product is returned late'
    )
    security_deposit = fields.Float(
        string='Security Deposit',
        help='Refundable security deposit amount'
    )

    @api.depends('rental_periodicity')
    def _compute_is_rental(self):
        for product in self:
            product.is_rental = bool(product.rental_periodicity)

    @api.depends('rental_periodicity')
    def _compute_rental_period_label(self):
        labels = {'hour': self.env._('Hour'), 'day': self.env._('Day'),
                  'week': self.env._('Week'), 'month': self.env._('Month')}
        for product in self:
            product.rental_period_label = labels.get(product.rental_periodicity, '')

    @api.depends('is_rental', 'rental_pricing_ids')
    def _compute_rental_ok(self):
        for product in self:
            product.rental_ok = bool(product.is_rental)

    def _rental_lines(self, domain=()):
        """Rental lines of confirmed orders for these products."""
        return self.env['sale.order.line'].search([
            ('product_id', 'in', self.product_variant_ids.ids),
            ('is_rental', '=', True),
            ('state', '=', 'sale'),
            *domain,
        ])

    def _compute_rental_stock_available(self):
        for product in self:
            # On-hand quantity minus what is reserved or out with customers
            lines = product._rental_lines()
            rented = sum(lines.mapped('product_uom_qty')) - sum(lines.mapped('qty_returned'))
            available_qty = sum(product.product_variant_ids.mapped('qty_available'))
            product.rental_stock_available = max(0.0, available_qty - rented)

    def _compute_rental_order_count(self):
        for product in self:
            product.rental_order_count = len(product._rental_lines().order_id)

    def _compute_qty_in_rent(self):
        for product in self:
            lines = product._rental_lines()
            product.qty_in_rent = sum(lines.mapped('qty_delivered')) - sum(lines.mapped('qty_returned'))

    def action_view_rental_orders(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('hudson_rental.action_rental_order')
        action['domain'] = [('order_line.product_id', 'in', self.product_variant_ids.ids)]
        return action

    def get_rental_price(self, duration, duration_unit='day'):
        """Return the rental price of one unit for the given duration.

        Every started period is charged. The cheapest of the pricing rules is used;
        without rules, the sales price is charged per period of the product's periodicity.
        """
        self.ensure_one()
        duration_days = duration * RENTAL_PERIOD_DAYS.get(duration_unit, 1.0)
        if duration_days <= 0:
            return 0.0

        def periods(period_days):
            # round() avoids charging an extra period for float noise (e.g. 7.0000001 days)
            return max(1, math.ceil(round(duration_days / period_days, 6)))

        prices = [
            periods(pricing.duration * RENTAL_PERIOD_DAYS[pricing.duration_unit]) * pricing.price
            for pricing in self.rental_pricing_ids
            if pricing.duration > 0
        ]
        if not prices and self.rental_periodicity:
            prices.append(periods(RENTAL_PERIOD_DAYS[self.rental_periodicity]) * self.list_price)
        return min(prices) if prices else 0.0


class ProductProduct(models.Model):
    _inherit = 'product.product'

    qty_in_rent = fields.Float("Quantity currently in rent", compute="_compute_qty_in_rent")

    def _compute_qty_in_rent(self):
        for product in self:
            product.qty_in_rent = product.product_tmpl_id.qty_in_rent

    def action_view_rental_orders(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('hudson_rental.action_rental_order')
        action['domain'] = [('order_line.product_id', '=', self.id)]
        return action

