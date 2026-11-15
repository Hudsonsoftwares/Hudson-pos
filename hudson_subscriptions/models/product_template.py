# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    recurring_invoice = fields.Boolean(
        string='Subscription Product',
        default=False,
        help='Check if this product is sold on a recurring subscription basis.'
    )
    subscription_plan_id = fields.Many2one(
        'sale.subscription.plan',
        string='Default Recurring Plan',
        help='Default billing plan applied when this product is selected.'
    )

    def _get_subscription_pricing_plans(self):
        self.ensure_one()
        if not self.recurring_invoice:
            return []

        # Resolve current pricelist
        from odoo.http import request
        website = self.env['website'].get_current_website() if 'website' in self.env else False
        pricelist = False
        if request and hasattr(request, 'pricelist') and request.pricelist:
            pricelist = request.pricelist
        if not pricelist and website and hasattr(website, 'get_pricelist_available'):
            pricelists = website.get_pricelist_available()
            if pricelists:
                pricelist = pricelists[0]
        if not pricelist:
            pricelist = self.env['product.pricelist'].search(
                [('company_id', 'in', (False, self.env.company.id))], limit=1
            )

        items = self.env['product.pricelist.item'].search([
            ('product_tmpl_id', '=', self.id),
            ('pricelist_id', '=', pricelist.id),
            ('subscription_plan_id', '!=', False),
        ])

        if not items:
            return []

        # Unit hierarchy: smaller index = shorter period
        UNIT_PRIORITY = {'days': 0, 'weeks': 1, 'months': 2, 'years': 3}
        # Use standard average values: 1 year = 365.25 days, 1 month = 365.25/12
        UNIT_TO_DAYS = {
            'days': 1.0,
            'weeks': 7.0,
            'months': 365.25 / 12.0,   # ≈ 30.44 days
            'years': 365.25,
        }
        UNIT_SINGULAR = {'days': 'day', 'weeks': 'week', 'months': 'month', 'years': 'year'}

        # Find the SMALLEST unit TYPE present (e.g. if weekly + monthly → "week")
        all_units = [item.subscription_plan_id.billing_period_unit for item in items
                     if item.subscription_plan_id.billing_period_unit in UNIT_PRIORITY]
        comparison_unit = min(all_units, key=lambda u: UNIT_PRIORITY[u])
        unit_label = UNIT_SINGULAR[comparison_unit]
        comparison_unit_days = UNIT_TO_DAYS[comparison_unit]

        # Build plan list, converting each price to price-per-comparison-unit
        raw = []
        for item in items:
            plan = item.subscription_plan_id
            v = plan.billing_period_value or 1
            unit = plan.billing_period_unit or 'months'
            total_days = v * UNIT_TO_DAYS.get(unit, 30)
            price_per_unit = (item.fixed_price / total_days) * comparison_unit_days if total_days else item.fixed_price
            raw.append({
                'plan': plan,
                'price': item.fixed_price,
                'days': total_days,
                'price_per_unit': price_per_unit,
            })

        # Sort ascending by total days (shortest plan first)
        raw.sort(key=lambda x: x['days'])

        # Reference point = highest price-per-unit (always the shortest-period plan)
        highest_price_per_unit = max(p['price_per_unit'] for p in raw)

        plans = []
        for p in raw:
            if highest_price_per_unit > 0 and p['price_per_unit'] < highest_price_per_unit:
                savings = round(
                    ((highest_price_per_unit - p['price_per_unit']) / highest_price_per_unit) * 100
                )
            else:
                savings = 0

            plans.append({
                'plan': p['plan'],
                'price': p['price'],
                'price_per_unit': p['price_per_unit'],
                'unit_label': unit_label,
                'savings_percent': savings,
                'price_per_month': p['price_per_unit'],  # backward-compat key
            })

        return plans


class ProductProduct(models.Model):
    _inherit = 'product.product'

    recurring_invoice = fields.Boolean(
        related='product_tmpl_id.recurring_invoice',
        readonly=False,
        store=True
    )
    subscription_plan_id = fields.Many2one(
        related='product_tmpl_id.subscription_plan_id',
        readonly=False,
        store=True
    )
