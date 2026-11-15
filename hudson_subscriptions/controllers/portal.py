# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from markupsafe import Markup

from odoo import fields, http, _
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager

PORTAL_SUBSCRIPTION_STATES = ['3_progress', '4_paused', '5_renew', '5_renewed', '6_churn']


class SubscriptionCustomerPortal(CustomerPortal):

    # ------------------------------------------------------------------
    # Home card counter (Odoo 20: portal.entry + _prepare_portal_counter_values)
    # ------------------------------------------------------------------

    def _prepare_subscriptions_domain(self, partner):
        return [
            ('is_subscription', '=', True),
            ('partner_id', 'child_of', [partner.commercial_partner_id.id]),
            ('state', '=', 'sale'),
            ('subscription_state', 'in', PORTAL_SUBSCRIPTION_STATES),
        ]

    def _prepare_portal_counter_values(self, counter):
        if counter == 'subscription_count':
            partner = request.env.user.partner_id
            return 'sale.order', self._prepare_subscriptions_domain(partner), 'read'
        return super()._prepare_portal_counter_values(counter)

    def _get_portal_subscription(self, order_id, access_token=None):
        """Return the subscription as sudo if the visitor may access it, else None."""
        try:
            order_sudo = self._document_check_access('sale.order', order_id, access_token=access_token)
        except (AccessError, MissingError):
            return None
        if not order_sudo.is_subscription:
            return None
        return order_sudo

    def _redirect_to_subscription(self, order_sudo):
        return request.redirect(order_sudo.get_portal_url())

    # ------------------------------------------------------------------
    # List & detail
    # ------------------------------------------------------------------

    @http.route(['/my/subscriptions', '/my/subscriptions/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_subscriptions(self, page=1, **kw):
        values = self._prepare_portal_layout_values()
        SaleOrder = request.env['sale.order']
        domain = self._prepare_subscriptions_domain(request.env.user.partner_id)

        subscription_count = SaleOrder.search_count(domain)
        pager = portal_pager(
            url="/my/subscriptions",
            total=subscription_count,
            page=page,
            step=10,
        )
        # Records are filtered by the access rules above; sudo only for rendering
        # related records (plan, ...) that portal users cannot read directly.
        subscriptions = SaleOrder.search(domain, limit=10, offset=pager['offset'], order='id desc').sudo()

        values.update({
            'subscriptions': subscriptions,
            'page_name': 'subscription',
            'pager': pager,
            'default_url': '/my/subscriptions',
        })
        return request.render("hudson_subscriptions.portal_my_subscriptions", values)

    @http.route(['/my/subscriptions/<int:subscription_id>'], type='http', auth="public", website=True)
    def portal_my_subscription_detail(self, subscription_id=None, access_token=None, **kw):
        # Like Odoo Online, a subscription is managed from its order page,
        # which carries the subscription sidebar (billing, renew, pause, close...).
        order_sudo = self._get_portal_subscription(subscription_id, access_token)
        if not order_sudo:
            return request.redirect('/my')
        return self._redirect_to_subscription(order_sudo)

    # ------------------------------------------------------------------
    # Self-service actions (each one gated by the recurring plan options)
    # ------------------------------------------------------------------

    @http.route(['/my/subscriptions/<int:order_id>/renew'], type='http', auth="public", methods=['POST'], website=True)
    def portal_my_subscription_renew(self, order_id=None, access_token=None, **kw):
        order = self._get_portal_subscription(order_id, access_token)
        if not order:
            return request.redirect('/my')
        if not order.plan_id.user_renew or order.subscription_state not in ('3_progress', '5_renew'):
            return self._redirect_to_subscription(order)

        pending = order.renewal_order_ids.filtered(lambda r: r.state in ('draft', 'sent'))
        if pending:
            return request.redirect(pending[0].get_portal_url())

        renewal_order = order._create_portal_renewal_quote()
        order.message_post(body=Markup(_("Renewal quotation %s created by the customer from the portal.")) % renewal_order._get_html_link())
        return request.redirect(renewal_order.get_portal_url())

    @http.route(['/my/subscriptions/<int:order_id>/change_plan'], type='http', auth="public", methods=['POST'], website=True)
    def portal_my_subscription_change_plan(self, order_id=None, plan_id=None, access_token=None, **kw):
        order = self._get_portal_subscription(order_id, access_token)
        if not order:
            return request.redirect('/my')

        new_plan = order.plan_id.optional_plan_ids.filtered(lambda p: str(p.id) == str(plan_id))
        if not new_plan:
            return self._redirect_to_subscription(order)

        if order.state in ('draft', 'sent'):
            # Still a quotation: simply switch the plan and reprice it.
            order.plan_id = new_plan
            order._onchange_plan_id()
            order.message_post(body=Markup(_("Recurring plan changed to <b>%s</b> by the customer from the portal.")) % new_plan.name)
            return self._redirect_to_subscription(order)

        # Running subscription: the new plan starts with a renewal quotation the
        # customer has to accept, prices being recomputed for that plan.
        renewal_order = order._create_portal_renewal_quote(plan=new_plan)
        order.message_post(body=Markup(_("The customer asked to switch to the <b>%(plan)s</b> plan: %(quote)s.")) % {
            'plan': new_plan.name,
            'quote': renewal_order._get_html_link(),
        })
        return request.redirect(renewal_order.get_portal_url())

    @http.route(['/my/subscriptions/<int:order_id>/pause'], type='http', auth="public", methods=['POST'], website=True)
    def portal_my_subscription_pause(self, order_id=None, access_token=None, **kw):
        order = self._get_portal_subscription(order_id, access_token)
        if not order:
            return request.redirect('/my')
        if order.plan_id.user_pausable and order.subscription_state == '3_progress':
            order.subscription_state = '4_paused'
            order.message_post(body=Markup(_("Subscription <b>Paused</b> by the customer from the portal.")))
        return self._redirect_to_subscription(order)

    @http.route(['/my/subscriptions/<int:order_id>/resume'], type='http', auth="public", methods=['POST'], website=True)
    def portal_my_subscription_resume(self, order_id=None, access_token=None, **kw):
        order = self._get_portal_subscription(order_id, access_token)
        if not order:
            return request.redirect('/my')
        if order.plan_id.user_pausable and order.subscription_state == '4_paused':
            order.subscription_state = '3_progress'
            order.message_post(body=Markup(_("Subscription <b>Resumed</b> by the customer from the portal.")))
        return self._redirect_to_subscription(order)

    @http.route(['/my/subscriptions/<int:order_id>/close'], type='http', auth="public", methods=['POST'], website=True)
    def portal_my_subscription_close(self, order_id=None, close_reason_id=None, access_token=None, **kw):
        order = self._get_portal_subscription(order_id, access_token)
        if not order:
            return request.redirect('/my')
        if not order.plan_id.user_closable or order.subscription_state in ('5_renewed', '6_churn', 'draft', 'sent'):
            return self._redirect_to_subscription(order)

        reason = request.env['sale.subscription.close.reason'].sudo().browse(int(close_reason_id or 0)).exists()
        if reason:
            order.write({
                'subscription_state': '6_churn',
                'close_reason_id': reason.id,
                'close_date': fields.Date.context_today(order),
            })
            order.message_post(body=Markup(_("Subscription has been <b>Closed</b> by the customer from the portal.<br/>Reason: %s")) % reason.name)
        return self._redirect_to_subscription(order)
