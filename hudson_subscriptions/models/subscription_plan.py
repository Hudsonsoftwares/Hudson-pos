# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from dateutil.relativedelta import relativedelta


class SaleSubscriptionPlan(models.Model):
    _name = 'sale.subscription.plan'
    _description = 'Subscription Recurring Plan'
    _order = 'sequence, name'

    name = fields.Char(string='Plan Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    billing_period_value = fields.Integer(string='Billing Period', default=1, required=True)
    billing_period_unit = fields.Selection([
        ('days', 'Day(s)'),
        ('weeks', 'Week(s)'),
        ('months', 'Month(s)'),
        ('years', 'Year(s)'),
    ], string='Period Unit', default='months', required=True)

    auto_close_limit = fields.Integer(
        string='Auto Close Limit',
        default=15,
        help='Number of days unpaid before marking subscription as churned'
    )
    user_closable = fields.Boolean(
        string='Closable by Customer',
        default=True,
        help='Allow customer to cancel their subscription from customer portal'
    )
    invoice_mail_template_id = fields.Many2one(
        'mail.template',
        string='Invoice Email Template',
        domain="[('model', '=', 'account.move')]",
        help='Email template used when recurring invoices are generated'
    )
    align_to_period_start = fields.Boolean(
        string='Align to Period Start',
        help='Align billing to the first day of the month/year.'
    )
    user_pausable = fields.Boolean(
        string='Pausable by Customer',
        help='Allow customer to pause their subscription from customer portal'
    )
    user_add_products = fields.Boolean(
        string='Add Products',
        help='Allow customer to add products to their subscription'
    )
    user_renew = fields.Boolean(
        string='Renewable by Customer',
        help='Allow customer to renew their subscription'
    )
    optional_plan_ids = fields.Many2many(
        'sale.subscription.plan',
        'subscription_plan_optional_rel',
        'plan_id', 'optional_plan_id',
        string='Optional Plans',
        help='Alternative plans proposed to the customer'
    )

    description = fields.Html(string='Terms & Conditions')

    subscription_count = fields.Integer(
        string='Subscriptions Count',
        compute='_compute_subscription_count'
    )

    def _compute_subscription_count(self):
        subscription_data = self.env['sale.order']._read_group(
            domain=[('is_subscription', '=', True), ('plan_id', 'in', self.ids)],
            groupby=['plan_id'],
            aggregates=['__count']
        )
        mapped_data = {plan.id: count for plan, count in subscription_data}
        for plan in self:
            plan.subscription_count = mapped_data.get(plan.id, 0)

    def action_view_subscriptions(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('hudson_subscriptions.action_subscription_orders')
        action['domain'] = [('is_subscription', '=', True), ('plan_id', '=', self.id)]
        action['context'] = {'default_plan_id': self.id, 'default_is_subscription': True}
        return action

    def get_next_date(self, start_date):
        """Calculate next date based on billing period value and unit."""
        self.ensure_one()
        if not start_date:
            return False
        delta_kwargs = {}
        if self.billing_period_unit == 'days':
            delta_kwargs['days'] = self.billing_period_value
        elif self.billing_period_unit == 'weeks':
            delta_kwargs['weeks'] = self.billing_period_value
        elif self.billing_period_unit == 'months':
            delta_kwargs['months'] = self.billing_period_value
        elif self.billing_period_unit == 'years':
            delta_kwargs['years'] = self.billing_period_value
        return start_date + relativedelta(**delta_kwargs)
