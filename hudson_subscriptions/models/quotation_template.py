# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class SaleOrderTemplate(models.Model):
    _name = 'sale.order.template'
    _inherit = ['sale.order.template']

    is_subscription = fields.Boolean(
        string='Is Subscription Template',
        default=False,
        help='Check this box if this template is for recurring subscriptions.'
    )
    plan_id = fields.Many2one(
        'sale.subscription.plan',
        string='Recurring Plan',
        help='Default recurring plan for subscriptions created with this template'
    )
