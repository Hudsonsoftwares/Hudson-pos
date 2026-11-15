# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta


class SaleSubscriptionRenewWizard(models.TransientModel):
    _name = 'sale.subscription.renew.wizard'
    _description = 'Subscription Renewal Wizard'

    subscription_id = fields.Many2one('sale.order', string='Subscription', required=True)
    plan_id = fields.Many2one('sale.subscription.plan', string='Renewal Plan')
    renewal_type = fields.Selection([
        ('extend', 'Extend Current Subscription Period'),
        ('new_quote', 'Create Renewal Quotation'),
    ], string='Renewal Action', default='extend', required=True)
    start_date = fields.Date(string='New Start Date', default=fields.Date.context_today)
    end_date = fields.Date(string='New End Date')

    @api.onchange('subscription_id')
    def _onchange_subscription_id(self):
        if self.subscription_id:
            self.plan_id = self.subscription_id.plan_id
            self.start_date = self.subscription_id._get_renewal_start_date()
            if self.plan_id:
                self.end_date = self.plan_id.get_next_date(self.start_date)

    def action_apply_renewal(self):
        self.ensure_one()
        sub = self.subscription_id
        if not sub:
            raise UserError(_("No subscription selected."))

        if self.renewal_type == 'extend':
            vals = {
                'subscription_state': '3_progress',
                'start_date': self.start_date or sub.start_date,
                'end_date': self.end_date,
                'next_invoice_date': self.start_date or sub.next_invoice_date,
            }
            if self.plan_id:
                vals['plan_id'] = self.plan_id.id
            sub.write(vals)
            sub.message_post(body=_("Subscription renewed until %s.") % (self.end_date or 'Indefinite'))
            return {'type': 'ir.actions.act_window_close'}
        else:
            # Create a linked renewal quotation
            renewal_order = sub.copy({
                'origin_order_id': sub.id,
                'is_renewal': True,
                'is_subscription': True,
                'subscription_state': 'draft',
                'plan_id': self.plan_id.id if self.plan_id else sub.plan_id.id,
                'start_date': self.start_date,
                'end_date': self.end_date,
                'next_invoice_date': self.start_date,
            })
            sub.message_post(body=_("Renewal quotation %s created.", renewal_order._get_html_link()))
            return {
                'name': _('Renewal Quotation'),
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order',
                'view_mode': 'form',
                'res_id': renewal_order.id,
            }
