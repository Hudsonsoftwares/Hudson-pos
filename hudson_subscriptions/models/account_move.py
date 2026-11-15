# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from markupsafe import Markup

from odoo import fields, models, _


class AccountMove(models.Model):
    _inherit = 'account.move'

    subscription_order_id = fields.Many2one(
        'sale.order', string='Subscription', copy=False, index='btree_not_null', readonly=True,
        help='Subscription whose recurring invoicing generated this invoice.')
    subscription_prev_next_date = fields.Date(copy=False, readonly=True)
    subscription_new_next_date = fields.Date(copy=False, readonly=True)

    def _restore_subscription_next_invoice_date(self):
        """A cancelled or deleted recurring invoice gives its period back, so
        the subscription can be invoiced again for it (like Odoo Online)."""
        for move in self.filtered(lambda m: m.subscription_order_id and m.subscription_new_next_date):
            order = move.subscription_order_id.sudo()
            # Only roll back if no later invoice already moved the date again.
            if order.next_invoice_date != move.subscription_new_next_date:
                continue
            order.next_invoice_date = move.subscription_prev_next_date
            order.message_post(body=Markup(_(
                "Invoice %(invoice)s was cancelled: next invoice date set back to %(date)s.",
                invoice=move.name or _("Draft"),
                date=move.subscription_prev_next_date or _("none"),
            )))
            move.subscription_new_next_date = False

    def button_cancel(self):
        res = super().button_cancel()
        self._restore_subscription_next_invoice_date()
        return res

    def unlink(self):
        self.filtered(lambda m: m.state != 'cancel')._restore_subscription_next_invoice_date()
        return super().unlink()
