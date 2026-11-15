# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta
from datetime import date
from markupsafe import Markup
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_subscription = fields.Boolean(
        string='Is a Subscription',
        default=False,
        copy=False,
        index=True,
        tracking=True,
        help='Indicates if this sales order represents a recurring subscription.'
    )
    plan_id = fields.Many2one(
        'sale.subscription.plan',
        string='Recurring Plan',
        tracking=True,
        index=True,
        help='Billing frequency and recurrence rule for this subscription.'
    )
    subscription_state = fields.Selection([
        ('draft', 'Quotation'),
        ('sent', 'Quotation Sent'),
        ('3_progress', 'In Progress'),
        ('4_paused', 'Paused'),
        ('5_renew', 'To Renew'),
        ('5_renewed', 'Renewed'),
        ('6_churn', 'Churned'),
        ('7_upsell', 'Upsell'),
    ], string='Subscription Status', default='draft', tracking=True, copy=False, index=True)

    start_date = fields.Date(
        string='Start Date',
        default=fields.Date.context_today,
        tracking=True,
        help='Date when subscription billing starts.'
    )
    next_invoice_date = fields.Date(
        string='Next Invoice Date',
        tracking=True,
        index=True,
        help='Next planned date to generate the recurring customer invoice.'
    )
    end_date = fields.Date(
        string='End Date',
        tracking=True,
        index=True,
        help='Expiration or contractual end date of the subscription.'
    )
    close_date = fields.Date(
        string='Closed Date',
        readonly=True,
        help='Date when the subscription was closed.',
        copy=False,
        tracking=True
    )

    subscription_paid = fields.Boolean(
        string='Subscription Paid',
        compute='_compute_subscription_paid',
        store=True,
        help='True if at least one confirmed payment transaction exists for this subscription.'
    )

    payment_token_id = fields.Many2one(
        'payment.token',
        string='Payment Token',
        help='Saved payment token used for recurring automatic charges.',
        copy=False
    )
    payment_mode = fields.Selection([
        ('manual', 'Manual Payment'),
        ('automatic', 'Automatic Payments'),
    ], string='Payment Mode', default='manual', compute='_compute_payment_mode', store=True, readonly=False, tracking=True)

    auto_invoice = fields.Boolean(
        string='Automatic Invoicing',
        default=True,
        tracking=True,
        help='Whether invoices are generated automatically by the recurring scheduler.'
    )

    in_error = fields.Boolean(
        string='In Error',
        default=False,
        tracking=True,
        help='Indicates an error occurred during automated invoicing or payment processing.'
    )

    first_contract_date = fields.Date(
        string='First Contract Date',
        compute='_compute_first_contract_date',
        store=True,
        readonly=False,
        copy=False,
        help='Date of the initial contract.'
    )

    @api.depends('origin_order_id', 'start_date', 'date_order')
    def _compute_first_contract_date(self):
        for order in self:
            if order.origin_order_id and order.origin_order_id.first_contract_date:
                order.first_contract_date = order.origin_order_id.first_contract_date
            elif order.start_date:
                order.first_contract_date = order.start_date
            elif order.date_order:
                order.first_contract_date = order.date_order.date()
            else:
                order.first_contract_date = fields.Date.context_today(order)

    @api.depends('transaction_ids', 'transaction_ids.state', 'payment_token_id')
    def _compute_payment_mode(self):
        for order in self:
            if order.payment_token_id or order.subscription_paid or order.transaction_ids.filtered(lambda t: t.state in ('done', 'authorized')):
                order.payment_mode = 'automatic'
            else:
                order.payment_mode = 'manual'

    @api.depends('transaction_ids', 'transaction_ids.state')
    def _compute_subscription_paid(self):
        for order in self:
            order.subscription_paid = bool(
                order.transaction_ids.filtered(lambda tx: tx.state == 'done')
            )

    close_reason_id = fields.Many2one(
        'sale.subscription.close.reason',
        string='Close Reason',
        tracking=True,
        copy=False
    )

    close_reason_notes = fields.Text(
        string='Close Notes',
        copy=False
    )

    recurring_total = fields.Monetary(
        string='Recurring',
        compute='_compute_recurring_total',
        store=True,
        tracking=True,
        help='Total amount billed per recurring period.'
    )
    recurring_monthly = fields.Monetary(
        string='MRR',
        compute='_compute_recurring_monthly',
        store=True,
        index=True,
        help='Monthly Recurring Revenue normalized across periods.'
    )
    mrr_change = fields.Monetary(
        string='MRR Change',
        compute='_compute_mrr_change',
        store=True,
        help='Difference in MRR relative to baseline or prior period.'
    )

    origin_order_id = fields.Many2one(
        'sale.order',
        string='Parent Subscription',
        copy=False,
        index=True
    )
    child_order_ids = fields.One2many(
        'sale.order',
        'origin_order_id',
        string='Child Subscriptions / Renewals'
    )
    is_upsell = fields.Boolean(
        string='Is Upsell Order',
        default=False,
        copy=False
    )
    is_renewal = fields.Boolean(
        string='Is Renewal Order',
        default=False,
        copy=False
    )
    subscription_order_count = fields.Integer(
        string='History Count',
        compute='_compute_subscription_order_count'
    )
    renewal_order_ids = fields.One2many(
        'sale.order', 'origin_order_id',
        string='Renewal Orders',
        domain=[('is_renewal', '=', True)]
    )
    renewal_order_count = fields.Integer(
        string='Renewal Count',
        compute='_compute_renewal_order_count'
    )
    upsell_order_ids = fields.One2many(
        'sale.order', 'origin_order_id',
        string='Upsell Orders',
        domain=[('is_upsell', '=', True)]
    )
    upsell_order_count = fields.Integer(
        string='Upsell Count',
        compute='_compute_upsell_order_count'
    )
    is_subscription_overdue = fields.Boolean(
        string='Is Overdue',
        compute='_compute_is_subscription_overdue'
    )
    subscription_invoice_due = fields.Boolean(
        string='Invoice Due',
        compute='_compute_subscription_invoice_due',
        help='True when the current billing period has not been invoiced yet. '
             'Drives the highlighted "Create Invoice" button.'
    )

    @api.depends('invoice_ids.state', 'next_invoice_date', 'is_subscription')
    def _compute_subscription_invoice_due(self):
        today = fields.Date.context_today(self)
        for order in self:
            if not order.is_subscription:
                order.subscription_invoice_due = False
                continue
            active_invoices = order.invoice_ids.filtered(lambda m: m.state != 'cancel')
            order.subscription_invoice_due = not active_invoices or bool(
                order.next_invoice_date and order.next_invoice_date <= today
            )

    # -------------------------------------------------------------------------
    # COMPUTE METHODS
    # -------------------------------------------------------------------------

    @api.depends('order_line.price_subtotal', 'is_subscription')
    def _compute_recurring_total(self):
        for order in self:
            if order.is_subscription:
                order.recurring_total = sum(line.price_subtotal for line in order.order_line if not line.display_type)
            else:
                order.recurring_total = 0.0

    @api.depends('recurring_total', 'plan_id', 'plan_id.billing_period_value', 'plan_id.billing_period_unit')
    def _compute_recurring_monthly(self):
        for order in self:
            if not order.is_subscription or not order.plan_id or order.plan_id.billing_period_value <= 0:
                order.recurring_monthly = order.recurring_total or 0.0
                continue
            period_val = order.plan_id.billing_period_value
            unit = order.plan_id.billing_period_unit
            total = order.recurring_total
            if unit == 'days':
                order.recurring_monthly = (total / period_val) * 30.0
            elif unit == 'weeks':
                order.recurring_monthly = (total / period_val) * 4.3333
            elif unit == 'months':
                order.recurring_monthly = total / period_val
            elif unit == 'years':
                order.recurring_monthly = total / (period_val * 12.0)
            else:
                order.recurring_monthly = total

    @api.depends('recurring_monthly', 'origin_order_id', 'origin_order_id.recurring_monthly', 'subscription_state')
    def _compute_mrr_change(self):
        for order in self:
            if order.subscription_state == '6_churn':
                order.mrr_change = -order.recurring_monthly
            elif order.origin_order_id:
                order.mrr_change = order.recurring_monthly - order.origin_order_id.recurring_monthly
            else:
                order.mrr_change = order.recurring_monthly

    def _compute_subscription_order_count(self):
        for order in self:
            count = self.env['sale.order'].search_count([('origin_order_id', '=', order.id)])
            order.subscription_order_count = count

    def _compute_renewal_order_count(self):
        for order in self:
            order.renewal_order_count = len(order.renewal_order_ids)

    def _compute_upsell_order_count(self):
        for order in self:
            order.upsell_order_count = len(order.upsell_order_ids)

    @api.depends('next_invoice_date', 'plan_id.auto_close_limit', 'subscription_state')
    def _compute_is_subscription_overdue(self):
        today = fields.Date.context_today(self)
        for order in self:
            if order.is_subscription and order.subscription_state == '3_progress' and order.next_invoice_date and order.plan_id.auto_close_limit:
                from dateutil.relativedelta import relativedelta
                limit_date = order.next_invoice_date + relativedelta(days=order.plan_id.auto_close_limit)
                order.is_subscription_overdue = today > limit_date
            else:
                order.is_subscription_overdue = False

    def _get_invoiced(self):
        super(SaleOrder, self)._get_invoiced()
        for order in self:
            if order.is_subscription:
                child_orders = self.env['sale.order'].search([('origin_order_id', '=', order.id)])
                if child_orders:
                    invoices = order.invoice_ids | child_orders.mapped('invoice_ids')
                    order.invoice_ids = invoices
                    order.invoice_count = len(invoices)

    # -------------------------------------------------------------------------
    # ONCHANGE & LIFECYCLE
    # -------------------------------------------------------------------------

    @api.onchange('plan_id')
    def _onchange_plan_id(self):
        if self.plan_id and not self.next_invoice_date:
            start = self.start_date or fields.Date.context_today(self)
            self.next_invoice_date = self.plan_id.get_next_date(start)
        # Force price recomputation
        for line in self.order_line:
            if line.product_id:
                line._compute_pricelist_item_id()
                line._compute_price_unit()

    @api.onchange('order_line')
    def _onchange_order_line_subscription(self):
        for line in self.order_line:
            if line.product_id and line.product_id.recurring_invoice:
                self.is_subscription = True
                if line.product_id.subscription_plan_id and not self.plan_id:
                    self.plan_id = line.product_id.subscription_plan_id
                break

    def action_confirm(self):
        for order in self:
            has_recurring_product = any(line.product_id.recurring_invoice for line in order.order_line)
            if order.plan_id and not has_recurring_product:
                raise UserError(_("Invalid Operation\n\nPlease add a recurring product in the subscription or remove the recurring plan."))
            if has_recurring_product and not order.plan_id:
                raise UserError(_("Invalid Operation\n\nPlease add a recurring plan on the subscription or remove the recurring product."))

            # If started from subscription app but only normal products added and no plan, revert to normal sale order
            if order.is_subscription and not order.plan_id and not has_recurring_product:
                order.is_subscription = False

            if order.is_renewal and order.origin_order_id:
                order._check_renewal_can_be_confirmed()

        res = super(SaleOrder, self).action_confirm()
        for order in self:
            if order.is_subscription and order.subscription_state in ('draft', 'sent'):
                order.subscription_state = '3_progress'
                if not order.start_date:
                    order.start_date = fields.Date.context_today(order)
                if not order.next_invoice_date and order.plan_id:
                    order.next_invoice_date = order.plan_id.get_next_date(order.start_date)
            if order.is_renewal and order.origin_order_id:
                order._close_renewed_parent()
        return res

    # -------------------------------------------------------------------------
    # RENEWALS (Odoo Online behaviour)
    # -------------------------------------------------------------------------

    def _check_renewal_can_be_confirmed(self):
        """A renewal continues its parent contract: it may not start before the
        end of the period the parent already billed, or it would be billed twice."""
        self.ensure_one()
        parent = self.origin_order_id
        if parent.subscription_state in ('5_renewed', '6_churn') and parent.child_order_ids.filtered(
            lambda o: o.is_renewal and o.state == 'sale' and o != self
        ):
            raise UserError(_(
                "%(parent)s has already been renewed. Cancel this quotation or renew the latest contract instead.",
                parent=parent.name,
            ))
        if parent.next_invoice_date and self.start_date and self.start_date < parent.next_invoice_date \
                and parent.invoice_ids.filtered(lambda m: m.state != 'cancel'):
            raise UserError(_(
                "You cannot validate a renewal quotation starting before the next invoice date of the "
                "parent contract. Please set the start date of %(renewal)s on or after %(date)s.",
                renewal=self.name,
                date=parent.next_invoice_date,
            ))

    def _close_renewed_parent(self):
        """Confirming a renewal closes its parent as "Renewed": the parent stops
        billing at the renewal start date and the renewal takes over. Other
        pending renewal quotations of the same parent are cancelled."""
        self.ensure_one()
        parent = self.origin_order_id.sudo()
        if not parent.is_subscription or parent.subscription_state not in ('3_progress', '4_paused', '5_renew'):
            return
        renewal_start = self.start_date or fields.Date.context_today(self)
        if parent.first_contract_date:
            self.first_contract_date = parent.first_contract_date
        parent.write({
            'subscription_state': '5_renewed',
            'end_date': renewal_start,
            'close_date': fields.Date.context_today(self),
        })
        parent.message_post(body=Markup(_("Subscription renewed by %s, which takes over from %s.")) % (
            self._get_html_link(), renewal_start))
        self.message_post(body=Markup(_("This renewal continues %s.")) % parent._get_html_link())

        other_quotes = parent.child_order_ids.filtered(
            lambda o: o.is_renewal and o != self and o.state in ('draft', 'sent'))
        if other_quotes:
            other_quotes._action_cancel()
            for quote in other_quotes:
                quote.message_post(body=Markup(_("Cancelled because %s renewed the subscription.")) % self._get_html_link())

    def _action_cancel(self):
        """Cancelling a confirmed renewal re-opens the contract it had replaced."""
        renewals = self.filtered(lambda o: o.is_renewal and o.state == 'sale' and o.origin_order_id
                                 and o.origin_order_id.subscription_state == '5_renewed')
        res = super()._action_cancel()
        today = fields.Date.context_today(self)
        for renewal in renewals:
            parent = renewal.origin_order_id.sudo()
            if parent.child_order_ids.filtered(lambda o: o.is_renewal and o.state == 'sale'):
                continue  # another confirmed renewal still continues it
            parent.write({
                'subscription_state': '5_renew' if parent.end_date and parent.end_date <= today else '3_progress',
                'close_date': False,
            })
            parent.message_post(body=Markup(_("Renewal %s was cancelled: the subscription is active again.")) % renewal._get_html_link())
        if renewals:
            renewals.write({'subscription_state': 'draft'})
        return res

    def _can_be_edited_on_portal(self):
        """Let customers change optional products of a running subscription
        from the portal, but only when its plan allows "Add Products"."""
        self.ensure_one()
        if self.is_subscription and self.state == 'sale':
            return bool(self.subscription_state == '3_progress' and self.plan_id.user_add_products)
        return super()._can_be_edited_on_portal()

    def action_confirm_subscription(self):
        """Dedicated action to start/activate subscription directly."""
        for order in self:
            order.is_subscription = True
            order.subscription_state = '3_progress'
            if not order.start_date:
                order.start_date = fields.Date.context_today(order)
            if not order.next_invoice_date and order.plan_id:
                order.next_invoice_date = order.plan_id.get_next_date(order.start_date)
            order.message_post(body=Markup(_("Subscription activated and set to <b>In Progress</b>.")))

    def action_pause_subscription(self):
        for order in self:
            order.subscription_state = '4_paused'
            order.message_post(body=Markup(_("Subscription has been <b>Paused</b>.")))

    def action_resume_subscription(self):
        for order in self:
            order.subscription_state = '3_progress'
            order.message_post(body=Markup(_("Subscription has been <b>Resumed</b> to In Progress.")))

    def action_set_to_renew(self):
        for order in self:
            order.subscription_state = '5_renew'
            order.message_post(body=Markup(_("Subscription marked as <b>To Renew</b>.")))

    def action_close_subscription(self):
        self.ensure_one()
        return {
            'name': _('Close Subscription'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.subscription.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_subscription_id': self.id},
        }
    def action_reopen_subscription(self):
        for order in self:
            if order.subscription_state == '6_churn':
                order.subscription_state = '3_progress'
                order.end_date = False
                order.message_post(body=_("Subscription has been reopened. The end date has been removed."))

    def action_view_renewals(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("sale.action_quotations_with_onboarding")
        action['domain'] = [('id', 'in', self.renewal_order_ids.ids)]
        action['context'] = {'default_origin_order_id': self.id, 'default_is_subscription': True, 'default_is_renewal': True}
        if self.renewal_order_count == 1:
            action['views'] = [(self.env.ref('sale.view_order_form').id, 'form')]
            action['res_id'] = self.renewal_order_ids.id
        return action

    def action_view_upsells(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("sale.action_quotations_with_onboarding")
        action['name'] = _('Upsell Quotes')
        action['domain'] = [('id', 'in', self.upsell_order_ids.ids)]
        action['context'] = {'default_origin_order_id': self.id, 'default_is_subscription': True, 'default_is_upsell': True}
        if self.upsell_order_count == 1:
            action['views'] = [(self.env.ref('sale.view_order_form').id, 'form')]
            action['res_id'] = self.upsell_order_ids.id
        return action

    def action_renew_subscription(self):
        self.ensure_one()
        # Check if any invoice is linked (via sale lines or directly)
        has_invoice = bool(self.invoice_ids) or bool(
            self.transaction_ids.filtered(lambda tx: tx.state == 'done')
        )
        if not has_invoice:
            raise ValidationError(_("You can not upsell or renew a subscription that has not been invoiced yet. Please, update directly the %s contract or invoice it first.") % self.name)
        return {
            'name': _('Renew Subscription'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.subscription.renew.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_subscription_id': self.id},
        }

    def action_upsell_subscription(self):
        self.ensure_one()
        # Check if any invoice is linked (via sale lines or directly)
        has_invoice = bool(self.invoice_ids) or bool(
            self.transaction_ids.filtered(lambda tx: tx.state == 'done')
        )
        if not has_invoice:
            raise ValidationError(_("You can not upsell or renew a subscription that has not been invoiced yet. Please, update directly the %s contract or invoice it first.") % self.name)
        
        
        # Clone the order but as a draft upsell quote
        upsell_order = self.copy({
            'origin_order_id': self.id,
            'is_subscription': True,
            'is_upsell': True,
            'subscription_state': '7_upsell',
            'state': 'draft',
            'client_order_ref': False,
        })
        
        # Set all product quantities to 0 for the upsell quote
        for line in upsell_order.order_line:
            line.product_uom_qty = 0.0

        self.message_post(body=Markup(_("An upsell quotation %s has been created.")) % upsell_order._get_html_link())

        action = self.env["ir.actions.actions"]._for_xml_id("sale.action_quotations_with_onboarding")
        action['views'] = [(self.env.ref('sale.view_order_form').id, 'form')]
        action['res_id'] = upsell_order.id
        return action

    def _get_renewal_start_date(self):
        """First day not billed by this contract (its next invoice date once
        it has been invoiced), else its end date."""
        self.ensure_one()
        if self.next_invoice_date and self.invoice_ids.filtered(lambda m: m.state != 'cancel'):
            return self.next_invoice_date
        return self.end_date or self.next_invoice_date or fields.Date.context_today(self)

    def _create_portal_renewal_quote(self, plan=None):
        """Renewal quotation requested by the customer from the portal,
        optionally on another plan (portal "Change Plan")."""
        self.ensure_one()
        plan = plan or self.plan_id
        # The renewal takes over where the parent's billing stops.
        start = self._get_renewal_start_date()
        renewal = self.copy({
            'origin_order_id': self.id,
            'is_renewal': True,
            'is_subscription': True,
            'subscription_state': 'draft',
            'plan_id': plan.id,
            'start_date': start,
            'next_invoice_date': start,
            'end_date': False,
        })
        if plan != self.plan_id:
            # Reprice the lines with the pricing of the new plan.
            renewal._onchange_plan_id()
        renewal._portal_ensure_token()
        return renewal

    def action_view_subscription_history(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('hudson_subscriptions.action_subscription_orders')
        action['domain'] = [('origin_order_id', '=', self.id)]
        action['context'] = {'default_origin_order_id': self.id, 'default_is_subscription': True}
        return action

    def action_view_invoice(self, invoices=False):
        if self.is_subscription and not invoices:
            child_orders = self.env['sale.order'].search([('origin_order_id', 'in', self.ids)])
            all_invoices = self.mapped('invoice_ids') | child_orders.mapped('invoice_ids')
            invoices = all_invoices
        return super(SaleOrder, self).action_view_invoice(invoices=invoices)

    # -------------------------------------------------------------------------
    # RECURRING INVOICING ENGINE
    # -------------------------------------------------------------------------

    def action_view_mrr_analysis(self):
        self.ensure_one()
        return {
            'name': _('MRR Analysis'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.subscription.report',
            'view_mode': 'graph,pivot',
            'domain': [('order_id', '=', self.id)],
            'context': {
                'graph_type': 'line',
                'graph_measure': 'mrr_change',
            }
        }

    def action_create_recurring_invoice(self):
        """Create recurring invoice manually for selected subscriptions."""
        invoices = self.env['account.move']
        for order in self:
            if not order.is_subscription:
                continue
            inv = order._create_subscription_invoice()
            if inv:
                invoices |= inv
        if len(invoices) == 1:
            return {
                'name': _('Customer Invoice'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'form',
                'res_id': invoices.id,
            }
        elif invoices:
            return {
                'name': _('Customer Invoices'),
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'view_mode': 'list,form',
                'domain': [('id', 'in', invoices.ids)],
            }
        raise UserError(_("No invoice could be generated. Check product lines and invoice settings."))

    def _get_subscription_invoice_qty(self, line):
        """Quantity of ``line`` to bill on the next subscription invoice.

        Recurring products are billed for the whole period, whatever their
        invoicing policy. A service set to "Delivered Quantities" has no
        delivery to wait for in a subscription: the period itself is what is
        delivered, so it is billed instead of raising "No items are available
        to invoice" like the standard flow does.
        One-time products (setup fees, hardware...) are billed only once.
        """
        if line.product_id.recurring_invoice:
            return line.product_uom_qty
        return max(line.product_uom_qty - line.qty_invoiced, 0.0)

    def _create_subscription_invoice(self, automatic=False):
        """Creates invoice for a subscription order and advances next_invoice_date."""
        self.ensure_one()
        prior_active_invoices = self.invoice_ids.filtered(lambda m: m.state != 'cancel')
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_invoice_id.id or self.partner_id.id,
            'partner_shipping_id': self.partner_shipping_id.id or self.partner_id.id,
            'currency_id': self.pricelist_id.currency_id.id if self.pricelist_id else self.currency_id.id,
            'invoice_user_id': self.user_id.id or self.env.user.id,
            'team_id': self.team_id.id,
            'company_id': self.company_id.id,
            'invoice_origin': self.name,
            'invoice_date': fields.Date.context_today(self),
            'invoice_line_ids': [],
        }

        for line in self.order_line:
            if line.display_type:
                continue
            qty = self._get_subscription_invoice_qty(line)
            if not qty:
                continue
            line_vals = {
                'name': f"{line.name} ({self.plan_id.name if self.plan_id else 'Recurring'})",
                'product_id': line.product_id.id,
                'quantity': qty,
                'product_uom_id': line.product_uom_id.id,
                'price_unit': line.price_unit,
                'discount': line.discount,
                'tax_ids': [(6, 0, line.tax_ids.ids)],
                'sale_line_ids': [(6, 0, [line.id])],
            }
            invoice_vals['invoice_line_ids'].append((0, 0, line_vals))

        if not invoice_vals['invoice_line_ids']:
            raise UserError(_(
                "There is nothing to invoice on %s. Add a product to the subscription first.",
                self.name,
            ))

        # Update next billing date. The first invoice covers the first period,
        # which action_confirm already accounted for (next date = start + 1
        # period), so it only moves the date when it is already due.
        previous_next_date = self.next_invoice_date
        if self.plan_id:
            today = fields.Date.context_today(self)
            curr_date = self.next_invoice_date or today
            # Renewals start billing on their start date (next date == start date).
            if prior_active_invoices or curr_date <= today or curr_date == self.start_date:
                self.next_invoice_date = self.plan_id.get_next_date(curr_date)
            else:
                self.next_invoice_date = curr_date

        invoice_vals.update({
            'subscription_order_id': self.id,
            'subscription_prev_next_date': previous_next_date,
            'subscription_new_next_date': self.next_invoice_date,
        })
        invoice = self.env['account.move'].create(invoice_vals)

        # Check end date
        if self.end_date and self.next_invoice_date and self.next_invoice_date > self.end_date:
            self.subscription_state = '5_renew'
            self.message_post(body=Markup(_("Subscription reached its end date (%(date)s) and has been marked as <b>To Renew</b>.") % {'date': self.end_date}))

        self.in_error = False
        self.message_post(
            body=Markup(_("Recurring invoice %s generated successfully.")) % invoice._get_html_link(title=invoice.name or _("Draft"))
        )
        return invoice

    @api.model
    def _cron_recurring_create_invoice(self):
        """Cron job to automatically create invoices for due subscriptions."""
        today = fields.Date.today()
        subscriptions = self.search([
            ('is_subscription', '=', True),
            ('subscription_state', '=', '3_progress'),
            ('auto_invoice', '=', True),
            ('next_invoice_date', '<=', today),
        ])
        _logger.info("Hudson Subscriptions: Processing %d recurring subscriptions for invoicing.", len(subscriptions))
        for sub in subscriptions:
            try:
                sub._create_subscription_invoice(automatic=True)
                sub.in_error = False
            except Exception as e:
                sub.in_error = True
                _logger.error("Failed to generate recurring invoice for subscription %s: %s", sub.name, str(e))
                sub.message_post(body=_("Automated recurring invoice generation failed: %s") % str(e))

    @api.model
    def get_retention_cohort_data(self, measure='count', interval='month', search_query=None):
        """
        Computes Retention Cohort Analysis matching Odoo Enterprise format:
        Rows: Cohorts by start date (first_contract_date or start_date)
        Columns: Initial measure, +0, +1, +2, ... period retention percentages.
        """
        # Renewals continue their parent contract: they are followed through
        # the parent below instead of counting as new subscriptions.
        domain = [('is_subscription', '=', True), ('state', '!=', 'cancel'), ('is_renewal', '=', False)]
        if search_query and search_query.strip():
            q = search_query.strip()
            domain += ['|', ('name', 'ilike', q), ('partner_id.name', 'ilike', q)]

        orders = self.search(domain, order='date_order asc, id asc')

        order_data = []
        today = fields.Date.today()

        def latest_renewal(order):
            seen = set()
            while order.subscription_state == '5_renewed' and order.id not in seen:
                seen.add(order.id)
                renewal = order.child_order_ids.filtered(lambda c: c.is_renewal and c.state == 'sale')[:1]
                if not renewal:
                    break
                order = renewal
            return order

        for o in orders:
            s_date = o.first_contract_date or o.start_date or (o.date_order and o.date_order.date()) or today
            last = latest_renewal(o)
            e_date = None
            if last.subscription_state == '6_churn':
                e_date = last.close_date or last.end_date or (last.write_date and last.write_date.date()) or today
            elif last.end_date:
                e_date = last.end_date

            val = 1.0
            if measure == 'recurring_monthly':
                val = float(o.recurring_monthly or 0.0)
            elif measure == 'recurring_total':
                val = float(o.recurring_total or o.amount_total or 0.0)

            order_data.append({
                'id': o.id,
                'name': o.name,
                'partner_name': o.partner_id.name or '',
                'start_date': s_date,
                'end_date': e_date,
                'state': last.subscription_state,
                'value': val,
            })

        if not order_data:
            return {
                'cohorts': [],
                'periods': [],
                'average': {'count': 0, 'cells': []},
                'measure': measure,
                'interval': interval,
            }

        def get_period_key(d):
            if interval == 'year':
                return (d.year, 1), str(d.year)
            elif interval == 'week':
                y, w, _ = d.isocalendar()
                return (y, w), f"W{w} {y}"
            elif interval == 'day':
                return (d.year, d.month, d.day), d.strftime('%d %b %Y')
            else:  # month default
                return (d.year, d.month), d.strftime('%B %Y')

        def diff_periods(d1, d2):
            if interval == 'year':
                return (d2.year - d1.year)
            elif interval == 'week':
                y1, w1, _ = d1.isocalendar()
                y2, w2, _ = d2.isocalendar()
                return (y2 - y1) * 52 + (w2 - w1)
            elif interval == 'day':
                return (d2 - d1).days
            else:  # month
                return (d2.year - d1.year) * 12 + (d2.month - d1.month)

        def add_periods(d, num):
            if interval == 'year':
                return d + relativedelta(years=num)
            elif interval == 'week':
                return d + relativedelta(weeks=num)
            elif interval == 'day':
                return d + relativedelta(days=num)
            else:
                return d + relativedelta(months=num)

        def period_bounds(d, p_idx):
            target = add_periods(d, p_idx)
            if interval == 'year':
                start = date(target.year, 1, 1)
                end = date(target.year, 12, 31)
            elif interval == 'week':
                start = target - relativedelta(days=target.weekday())
                end = start + relativedelta(days=6)
            elif interval == 'day':
                start = target
                end = target
            else:  # month
                start = date(target.year, target.month, 1)
                end = start + relativedelta(months=1, days=-1)
            return start, end

        cohort_groups = {}
        for item in order_data:
            key, label = get_period_key(item['start_date'])
            if key not in cohort_groups:
                cohort_groups[key] = {
                    'key': key,
                    'label': label,
                    'start_date': item['start_date'],
                    'items': [],
                }
            cohort_groups[key]['items'].append(item)

        sorted_keys = sorted(cohort_groups.keys())

        max_periods = 0
        for k in sorted_keys:
            c = cohort_groups[k]
            elapsed = diff_periods(c['start_date'], today)
            c['elapsed'] = max(0, elapsed)
            if c['elapsed'] > max_periods:
                max_periods = c['elapsed']

        max_periods = min(max_periods, 15)
        periods_header = [f"+{i}" for i in range(max_periods + 1)]

        result_cohorts = []
        for k in sorted_keys:
            c = cohort_groups[k]
            initial_orders = c['items']
            initial_order_ids = [it['id'] for it in initial_orders]
            initial_measure = sum(it['value'] for it in initial_orders)
            initial_count = len(initial_orders)

            cells = []
            for p in range(max_periods + 1):
                if p > c['elapsed']:
                    cells.append(None)
                    continue

                p_start, p_end = period_bounds(c['start_date'], p)
                retained_items = []
                for it in initial_orders:
                    if it['start_date'] <= p_end:
                        if not it['end_date'] or it['end_date'] >= p_start:
                            retained_items.append(it)

                retained_measure = sum(it['value'] for it in retained_items)
                retained_ids = [it['id'] for it in retained_items]
                percentage = (retained_measure / initial_measure * 100.0) if initial_measure > 0 else 0.0

                cells.append({
                    'period': p,
                    'percentage': round(percentage, 1),
                    'retained_count': len(retained_items),
                    'retained_measure': round(retained_measure, 2),
                    'order_ids': retained_ids,
                })

            display_count = initial_count if measure == 'count' else round(initial_measure, 2)

            result_cohorts.append({
                'label': c['label'],
                'count': display_count,
                'raw_count': initial_count,
                'initial_measure': initial_measure,
                'order_ids': initial_order_ids,
                'cells': cells,
            })

        avg_cells = []
        for p in range(max_periods + 1):
            eligible_cohorts = [co for co in result_cohorts if p < len(co['cells']) and co['cells'][p] is not None]
            if eligible_cohorts:
                total_retained = sum(co['cells'][p]['retained_measure'] for co in eligible_cohorts)
                total_initial = sum(co['initial_measure'] for co in eligible_cohorts)
                avg_pct = (total_retained / total_initial * 100.0) if total_initial > 0 else 0.0
                avg_cells.append({
                    'period': p,
                    'percentage': round(avg_pct, 1),
                    'is_average': True,
                })
            else:
                avg_cells.append(None)

        avg_initial_count = round(sum(co['count'] for co in result_cohorts) / len(result_cohorts), 1) if result_cohorts else 0

        retention_list_view = self.env.ref('hudson_subscriptions.view_subscription_retention_list', raise_if_not_found=False)
        list_view_id = retention_list_view.id if retention_list_view else False

        return {
            'cohorts': result_cohorts,
            'periods': periods_header,
            'average': {
                'label': 'Average',
                'count': avg_initial_count,
                'cells': avg_cells,
            },
            'measure': measure,
            'interval': interval,
            'list_view_id': list_view_id,
        }
