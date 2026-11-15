# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    subscription_default_plan_id = fields.Many2one(
        'sale.subscription.plan',
        string='Default Recurring Plan',
        config_parameter='hudson_subscriptions.default_plan_id'
    )
    subscription_default_template_id = fields.Many2one(
        'sale.order.template',
        string='Default Subscription Template',
        config_parameter='hudson_subscriptions.default_template_id'
    )
    subscription_renewal_days = fields.Integer(
        string='Renewal Notice (Days)',
        default=30,
        config_parameter='hudson_subscriptions.renewal_days',
        help='Days prior to subscription end date to mark subscription as To Renew'
    )
    subscription_auto_invoice = fields.Boolean(
        string='Automatic Recurring Invoicing',
        default=True,
        config_parameter='hudson_subscriptions.auto_invoice',
        help='Automatically generate invoices on next invoice date using scheduled cron'
    )
