# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class SaleSubscriptionCloseReason(models.Model):
    _name = 'sale.subscription.close.reason'
    _description = 'Subscription Close Reason'
    _order = 'sequence, name'

    name = fields.Char(string='Reason', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    empty_reason = fields.Boolean(string='Empty Reason', default=False)
    subscription_count = fields.Integer(
        string='Closed Subscriptions',
        compute='_compute_subscription_count'
    )

    def _compute_subscription_count(self):
        subscription_data = self.env['sale.order']._read_group(
            domain=[('is_subscription', '=', True), ('close_reason_id', 'in', self.ids)],
            groupby=['close_reason_id'],
            aggregates=['__count']
        )
        mapped_data = {reason.id: count for reason, count in subscription_data}
        for reason in self:
            reason.subscription_count = mapped_data.get(reason.id, 0)
