# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleSubscriptionCloseWizard(models.TransientModel):
    _name = 'sale.subscription.close.wizard'
    _description = 'Subscription Close / Churn Wizard'

    subscription_id = fields.Many2one('sale.order', string='Subscription', required=True)
    close_reason_id = fields.Many2one('sale.subscription.close.reason', string='Close Reason', required=True)
    close_date = fields.Date(string='Close Date', default=fields.Date.context_today, required=True)
    notes = fields.Text(string='Closing Notes')

    def action_close(self):
        self.ensure_one()
        if not self.subscription_id:
            raise UserError(_("No subscription selected."))
        self.subscription_id.write({
            'subscription_state': '6_churn',
            'close_reason_id': self.close_reason_id.id,
            'close_date': self.close_date,
            'close_reason_notes': self.notes,
        })
        body = _("Subscription has been <b>Closed / Churned</b>.<br/>Reason: %s") % (self.close_reason_id.name)
        if self.notes:
            body += _("<br/>Notes: %s") % self.notes
        self.subscription_id.message_post(body=body)
        return {'type': 'ir.actions.act_window_close'}
