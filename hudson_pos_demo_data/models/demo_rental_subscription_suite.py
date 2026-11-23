# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Rental (event equipment hire) and Subscriptions demo data.

Rental (hudson_rental): rentable event equipment with hour/day/week pricing, late fees and deposits,
and rental orders in every status: quotation, sent, reserved (future, today, late pickup),
picked-up (on time and late return), returned (on time + invoiced/paid, late with delay fee), cancelled.

Subscriptions (hudson_subscriptions): recurring products (office coffee & pastry box, corporate lunch
plan, coffee bean club, cafe membership, bakery supply) on the module's weekly/monthly/quarterly/yearly
plans, with subscriptions in progress (with past recurring invoices, some paid), to renew, renewal quote,
upsell quote, paused, churned with reason, quotation and quotation sent.

Idempotent: every record is bound to an xmlid of this module (rc_rent_* / rc_sub_*).
"""
import logging
from datetime import timedelta

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'


def _ref(env, xid):
    return env.ref(xid if '.' in xid else f'{MODULE}.{xid}', raise_if_not_found=False)


def _bind(env, xid, record):
    env['ir.model.data'].sudo().create({
        'module': MODULE, 'name': xid, 'model': record._name, 'res_id': record.id, 'noupdate': True,
    })
    return record


def _get_or_create(env, xid, model, vals):
    rec = _ref(env, xid)
    if rec and rec.exists():
        return rec
    return _bind(env, xid, env[model].sudo().create(vals))


def _partner(env, xid):
    partner = _ref(env, xid)
    if partner:
        return partner
    if xid == 'rc_sale_partner_priya':
        return _get_or_create(env, xid, 'res.partner', {
            'name': 'Priya Raghavan', 'email': 'priya.raghavan@example.com', 'phone': '+91 98470 22110',
            'street': 'Panampilly Nagar', 'city': 'Kochi', 'country_id': env.ref('base.in').id})
    return env['res.partner']


def _user(env, key):
    return (_ref(env, 'rc_user_arjun') if key == 'arjun' else None) or env.ref('base.user_admin')


def _at(days, hour=10):
    """Naive UTC datetime `days` from now at `hour`:00 UTC."""
    return fields.Datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days)


def _invoice_and_pay(env, order, date, pay=False):
    try:
        invoice = order._create_invoices()
        invoice.invoice_date = date
        invoice.action_post()
        if pay:
            _pay(env, invoice, date + timedelta(days=3))
        return invoice
    except Exception as e:
        _logger.info("Invoice for %s skipped: %s", order.name, e)
        return False


def _pay(env, invoice, date):
    try:
        env['account.payment.register'].sudo().with_context(active_model='account.move', active_ids=invoice.ids).create(
            {'payment_date': date})._create_payments()
    except Exception as e:
        _logger.info("Payment for %s skipped: %s", invoice.name, e)


# =========================================================================== RENTAL
RENTAL_PRODUCTS = [
    # xid, name, periodicity, list price (per period), pricing [(duration, unit, price)], late fee/day, deposit, description
    ('rc_rent_chafing', 'Chafing Dish (Stainless, 8 L)', 'day', 350, [(1, 'day', 350), (1, 'week', 1800)], 150, 1000,
     'Roll-top chafing dish with fuel holders, ideal for buffets.'),
    ('rc_rent_chairs', 'Banquet Chair with Cover', 'day', 45, [(1, 'day', 45), (1, 'week', 220)], 20, 0,
     'Cushioned banquet chair with white or ivory cover and sash.'),
    ('rc_rent_table', 'Round Table (8 seater) with Linen', 'day', 300, [(1, 'day', 300), (1, 'week', 1500)], 100, 500,
     '5 ft round table with ironed linen and skirting.'),
    ('rc_rent_tent', 'Garden Canopy Tent (20 x 20 ft)', 'day', 6500, [(1, 'day', 6500), (1, 'week', 32000)], 2500, 10000,
     'Waterproof white canopy with side curtains, installed by our crew.'),
    ('rc_rent_urn', 'Coffee Urn (100 cups)', 'day', 900, [(4, 'hour', 450), (1, 'day', 900), (1, 'week', 4500)], 300, 2000,
     'Electric coffee & tea urn with tap, keeps drinks hot for 6 hours.'),
    ('rc_rent_cart', 'Live Counter Cart with Induction', 'day', 3500, [(6, 'hour', 2200), (1, 'day', 3500)], 1200, 5000,
     'Mobile live-cooking counter with 2 induction tops and branding panel.'),
    ('rc_rent_sound', 'PA Sound System with 2 Mics', 'hour', 1200, [(1, 'hour', 1200), (1, 'day', 7500)], 2000, 8000,
     '2 x 1000 W speakers, mixer and 2 wireless microphones.'),
    ('rc_rent_lights', 'Fairy Light Set (20 m)', 'day', 400, [(1, 'day', 400), (1, 'week', 2000)], 100, 500,
     'Warm-white LED fairy lights for stages, trees and entrances.'),
]

# xid, partner xid, salesperson, status, start (days from now), duration (days), lines [(product xid, qty)], note
RENTAL_ORDERS = [
    ('rc_rent_so_film_society', 'rc_partner_film_society', 'arjun', 'draft', 20, 1,
     [('rc_rent_chairs', 150), ('rc_rent_table', 15), ('rc_rent_lights', 10)], 'Open-air screening night at Durbar Hall grounds.'),
    ('rc_rent_so_school_sports', 'rc_partner_st_teresa', 'admin', 'sent', 15, 1,
     [('rc_rent_tent', 2), ('rc_rent_sound', 1), ('rc_rent_chairs', 300)], 'Sports day pavilion and announcements.'),
    ('rc_rent_so_marina_wedding', 'rc_partner_marina_events', 'arjun', 'reserved', 5, 2,
     [('rc_rent_chafing', 20), ('rc_rent_chairs', 200), ('rc_rent_table', 25), ('rc_rent_lights', 12)], 'Beach wedding at Cherai, setup the day before.'),
    ('rc_rent_so_nest_launch', 'rc_partner_nest_cowork', 'admin', 'today', 0, 1,
     [('rc_rent_urn', 2), ('rc_rent_cart', 1)], 'Members\' launch party, pickup this afternoon.'),
    ('rc_rent_so_runners_late_pickup', 'rc_partner_coastal_runners', 'arjun', 'reserved', -1, 2,
     [('rc_rent_tent', 2), ('rc_rent_urn', 2)], 'Hydration point, customer has not collected yet.'),
    ('rc_rent_so_bluewave_offsite', 'rc_partner_bluewave', 'admin', 'picked', -2, 3,
     [('rc_rent_sound', 1), ('rc_rent_chairs', 120)], 'Quarterly town hall at their campus.'),
    ('rc_rent_so_grand_late_return', 'rc_partner_grand_residency', 'admin', 'picked', -6, 4,
     [('rc_rent_chafing', 30)], 'Overflow buffet equipment for the hotel, return overdue.'),
    ('rc_rent_so_harbour_retreat', 'rc_partner_harbour_park', 'arjun', 'returned_paid', -20, 2,
     [('rc_rent_tent', 1), ('rc_rent_chairs', 100), ('rc_rent_table', 12)], 'Annual retreat, returned in good condition.'),
    ('rc_rent_so_spice_late', 'rc_partner_spice_route', 'arjun', 'returned_late', -10, 2,
     [('rc_rent_tent', 1), ('rc_rent_lights', 6)], 'Tourist group camp, returned 6 days late.'),
    ('rc_rent_so_priya_cancel', 'rc_sale_partner_priya', 'arjun', 'cancel', 8, 1,
     [('rc_rent_lights', 4)], 'Birthday moved indoors, lights not needed.'),
]


def _rental_products(env):
    categ = _get_or_create(env, 'rc_rent_categ', 'product.category', {'name': 'Event Equipment Rental'})
    tax = env.company.account_sale_tax_id
    res = {}
    for xid, name, periodicity, price, pricing, late_fee, deposit, desc in RENTAL_PRODUCTS:
        if _ref(env, xid):
            res[xid] = _ref(env, xid)
            continue
        vals = {
            'name': name, 'type': 'consu', 'list_price': price, 'categ_id': categ.id, 'sale_ok': True,
            'purchase_ok': False, 'invoice_policy': 'order', 'description_sale': desc,
            'rental_periodicity': periodicity, 'late_fee_per_day': late_fee, 'security_deposit': deposit,
            'taxes_id': [Command.set(tax.ids)],
            'rental_pricing_ids': [Command.create({'duration': d, 'duration_unit': u, 'price': p}) for d, u, p in pricing],
        }
        if 'available_in_pos' in env['product.template']._fields:
            vals['available_in_pos'] = False
        res[xid] = _get_or_create(env, xid, 'product.template', vals)
    return res


def _rental_wizard(env, order, status):
    Wizard = env['rental.order.wizard'].sudo().with_context(default_order_id=order.id, default_status=status)
    # same lines the wizard proposes when opened from the order (everything left to pick up / return)
    vals = Wizard.default_get(['order_id', 'status', 'line_ids'])
    Wizard.create(vals).action_apply()


def _create_rental_order(env, spec, prods):
    xid, partner_xid, sp, status, start_in, duration, lines, note = spec
    if _ref(env, xid):
        return
    partner = _partner(env, partner_xid)
    if not partner:
        return
    user = _user(env, sp)
    if status == 'today':
        start = (fields.Datetime.now() + timedelta(hours=3)).replace(minute=0, second=0, microsecond=0)
    else:
        start = _at(start_in, 4)  # 09:30 IST
    end = start + timedelta(days=duration)
    order = env['sale.order'].sudo().create({
        'partner_id': partner.id, 'user_id': user.id, 'client_order_ref': note[:40],
        'rental_start_date': start, 'rental_end_date': end,
        'date_order': min(fields.Datetime.now(), start - timedelta(days=3)),
        'note': f'<p>{note}</p>',
        'order_line': [Command.create({'product_id': prods[p].product_variant_ids[:1].id, 'product_uom_qty': q})
                       for p, q in lines],
    })
    _bind(env, xid, order)

    if status == 'sent':
        order.action_quotation_sent()
    elif status == 'cancel':
        order.action_quotation_sent()
        order._action_cancel()
        order.message_post(body=note, message_type='comment', subtype_xmlid='mail.mt_note')
    elif status != 'draft':
        order.action_confirm()
        if status in ('picked', 'returned_paid', 'returned_late'):
            _rental_wizard(env, order, 'pickup')
        if status == 'returned_paid':
            if order.company_id.rental_use_transfers:
                _rental_wizard(env, order, 'return')
            else:
                # Returned on its (past) return date: record it like the Return wizard does, without the
                # delay fee the wizard would compute against today's date.
                for line in order.order_line.filtered('is_rental'):
                    line.qty_returned = line.qty_delivered
                order.message_post(body="Returned: all equipment back on time, checked and cleaned.")
            _invoice_and_pay(env, order, end.date(), pay=True)
        elif status == 'returned_late':
            _rental_wizard(env, order, 'return')  # returned now: adds the delay-cost line
    if status in ('reserved', 'picked') and order.is_late:
        order.activity_schedule('mail.mail_activity_data_call', date_deadline=fields.Date.today(),
                                summary='Call customer about late pickup/return', user_id=user.id)


def load_rental_demo_data(env):
    if 'rental.pricing' not in env or 'is_rental_order' not in env['sale.order']._fields:
        _logger.info("Hudson POS: hudson_rental not installed, skipping Rental demo data.")
        return
    # delay fees on late returns (keeps the company's own settings if already configured)
    company = env.company.sudo()
    if 'rental_extra_day' in company._fields and not company.rental_extra_day:
        company.write({'rental_extra_day': 1.0, 'rental_extra_hour': 0.1})
    prods = _rental_products(env)
    for spec in RENTAL_ORDERS:
        try:
            with env.cr.savepoint():
                _create_rental_order(env, spec, prods)
        except Exception as e:
            _logger.exception("Hudson POS: Rental demo order %s failed: %s", spec[0], e)
    try:
        with env.cr.savepoint():
            _refresh_rental_dashboard_dates(env)
    except Exception as e:
        _logger.exception("Hudson POS: Failed to refresh rental dashboard dates: %s", e)


def _refresh_rental_dashboard_dates(env):
    """Keep demo rental order dates fresh relative to now so all dashboard tiles stay populated."""
    now = fields.Datetime.now()

    # 1. Today pickup (rc_rent_so_nest_launch) -> is_today=True, rental_status='pickup'
    nest = _ref(env, 'rc_rent_so_nest_launch')
    if nest and nest.exists():
        nest.write({
            'rental_start_date': now + timedelta(hours=2),
            'rental_end_date': now + timedelta(days=2),
        })

    # 2. Late pickup (rc_rent_so_runners_late_pickup) -> is_late=True, rental_status='pickup'
    runners = _ref(env, 'rc_rent_so_runners_late_pickup')
    if runners and runners.exists():
        runners.write({
            'rental_start_date': now - timedelta(days=1, hours=3),
            'rental_end_date': now + timedelta(days=1),
        })

    # 3. Today return (rc_rent_so_bluewave_offsite) -> is_today=True, rental_status='return'
    blue = _ref(env, 'rc_rent_so_bluewave_offsite')
    if blue and blue.exists():
        blue.write({
            'rental_start_date': now - timedelta(days=2),
            'rental_end_date': now + timedelta(hours=3),
        })

    # 4. Late return (rc_rent_so_grand_late_return) -> is_late=True, rental_status='return'
    grand = _ref(env, 'rc_rent_so_grand_late_return')
    if grand and grand.exists():
        grand.write({
            'rental_start_date': now - timedelta(days=5),
            'rental_end_date': now - timedelta(days=1, hours=2),
        })

    # 5. Future pickup (rc_rent_so_marina_wedding)
    marina = _ref(env, 'rc_rent_so_marina_wedding')
    if marina and marina.exists():
        marina.write({
            'rental_start_date': now + timedelta(days=4),
            'rental_end_date': now + timedelta(days=6),
        })


# =========================================================================== SUBSCRIPTIONS
PLANS = {  # key -> (module xmlid, fallback vals)
    'weekly': ('hudson_subscriptions.subscription_plan_weekly', {'name': 'Weekly', 'billing_period_value': 1, 'billing_period_unit': 'weeks'}),
    'monthly': ('hudson_subscriptions.subscription_plan_monthly', {'name': 'Monthly', 'billing_period_value': 1, 'billing_period_unit': 'months'}),
    'quarterly': ('hudson_subscriptions.subscription_plan_quarterly', {'name': 'Quarterly', 'billing_period_value': 3, 'billing_period_unit': 'months'}),
    'yearly': ('hudson_subscriptions.subscription_plan_yearly', {'name': 'Yearly', 'billing_period_value': 1, 'billing_period_unit': 'years'}),
}

SUB_PRODUCTS = [
    # xid, name, default plan, list price, description
    ('rc_sub_prod_coffee_box', 'Office Coffee & Pastry Box', 'weekly', 3500,
     'Weekly delivery of 2 kg house-roast coffee, 40 pastries and filter coffee decoction for your office.'),
    ('rc_sub_prod_lunch_plan', 'Corporate Lunch Plan (per staff)', 'monthly', 3800,
     'Working-day lunch box per employee: rice, 2 curries, thoran, pickle and a sweet.'),
    ('rc_sub_prod_bean_club', 'Coffee Bean Club (1 kg)', 'monthly', 1200,
     'A different single-estate Kerala or Coorg coffee every month, roasted to order.'),
    ('rc_sub_prod_membership', 'Resto Cafe Membership', 'monthly', 499,
     '10% off every bill, a free dessert on your birthday and priority table booking.'),
    ('rc_sub_prod_bakery', 'Daily Bakery Supply', 'monthly', 45000,
     'Fresh bread, buns and pastries delivered to your cafeteria every morning.'),
]
# price per plan when different from list price
PLAN_PRICES = {
    ('rc_sub_prod_bean_club', 'quarterly'): 3300, ('rc_sub_prod_bean_club', 'yearly'): 12000,
    ('rc_sub_prod_membership', 'yearly'): 4999, ('rc_sub_prod_coffee_box', 'monthly'): 13000,
    ('rc_sub_prod_bakery', 'quarterly'): 130000,
}

# xid, partner, salesperson, plan, start (days ago), lines [(product, qty)], scenario, extra
SUBSCRIPTIONS = [
    ('rc_sub_nest_coffee', 'rc_partner_nest_cowork', 'admin', 'weekly', 45, [('rc_sub_prod_coffee_box', 2)], 'progress', {'pay': True}),
    ('rc_sub_bluewave_lunch', 'rc_partner_bluewave', 'admin', 'monthly', 120, [('rc_sub_prod_lunch_plan', 120)], 'progress', {'pay': True}),
    ('rc_sub_harbour_coffee', 'rc_partner_harbour_park', 'arjun', 'monthly', 75, [('rc_sub_prod_coffee_box', 1)], 'upsell', {'pay': True, 'upsell_qty': 3}),
    ('rc_sub_greenleaf_bakery', 'rc_partner_greenleaf', 'admin', 'quarterly', 200, [('rc_sub_prod_bakery', 1)], 'progress', {'pay': False}),
    ('rc_sub_grand_beans', 'rc_partner_grand_residency', 'admin', 'yearly', 350, [('rc_sub_prod_bean_club', 5)], 'to_renew', {'pay': True}),
    ('rc_sub_marina_beans', 'rc_partner_marina_events', 'arjun', 'quarterly', 85, [('rc_sub_prod_bean_club', 2)], 'renewal_quote', {'pay': True}),
    ('rc_sub_priya_member', 'rc_sale_partner_priya', 'arjun', 'monthly', 95, [('rc_sub_prod_membership', 1)], 'paused', {'pay': True}),
    ('rc_sub_film_member', 'rc_partner_film_society', 'arjun', 'yearly', 400, [('rc_sub_prod_membership', 6)], 'churn',
     {'pay': True, 'reason': 'rc_sub_reason_moved', 'notes': 'Society now meets at a venue across town.'}),
    ('rc_sub_runners_beans', 'rc_partner_coastal_runners', 'arjun', 'monthly', 150, [('rc_sub_prod_bean_club', 3)], 'churn',
     {'pay': True, 'reason': 'hudson_subscriptions.close_reason_too_expensive', 'notes': 'Club budget cut for the off-season.'}),
    ('rc_sub_spice_lunch', 'rc_partner_spice_route', 'arjun', 'monthly', 0, [('rc_sub_prod_lunch_plan', 25)], 'sent', {}),
    ('rc_sub_school_bakery', 'rc_partner_st_teresa', 'admin', 'monthly', 0, [('rc_sub_prod_bakery', 1)], 'draft', {}),
]


def _plans(env):
    res = {}
    for key, (xmlid, vals) in PLANS.items():
        res[key] = env.ref(xmlid, raise_if_not_found=False) or _get_or_create(env, f'rc_sub_plan_{key}', 'sale.subscription.plan', vals)
    return res


def _sub_products(env, plans):
    categ = _get_or_create(env, 'rc_sub_categ', 'product.category', {'name': 'Subscriptions & Memberships'})
    tax = env.company.account_sale_tax_id
    res = {}
    for xid, name, plan_key, price, desc in SUB_PRODUCTS:
        vals = {
            'name': name, 'type': 'service', 'list_price': price, 'categ_id': categ.id, 'sale_ok': True,
            'purchase_ok': False, 'invoice_policy': 'order', 'description_sale': desc,
            'recurring_invoice': True, 'subscription_plan_id': plans[plan_key].id,
            'taxes_id': [Command.set(tax.ids)],
        }
        if 'available_in_pos' in env['product.template']._fields:
            vals['available_in_pos'] = False
        if 'service_tracking' in env['product.template']._fields:
            vals['service_tracking'] = 'no'
        res[xid] = _get_or_create(env, xid, 'product.template', vals)
    # plan prices on the default pricelist (used by the website plan selector)
    pricelist = env['product.pricelist'].sudo().search([('company_id', 'in', (False, env.company.id))], limit=1)
    if pricelist and 'subscription_plan_id' in env['product.pricelist.item']._fields:
        for xid, _name, plan_key, price, _desc in SUB_PRODUCTS:
            for key in ('weekly', 'monthly', 'quarterly', 'yearly'):
                p = PLAN_PRICES.get((xid, key), price if key == plan_key else None)
                if p is None:
                    continue
                _get_or_create(env, f'{xid}_price_{key}', 'product.pricelist.item', {
                    'pricelist_id': pricelist.id, 'applied_on': '1_product', 'product_tmpl_id': res[xid].id,
                    'compute_price': 'fixed', 'fixed_price': p, 'subscription_plan_id': plans[key].id})
    return res


def _sub_invoices(env, order, plan, start, pay):
    """Recurring invoices for every period started up to today, dated at each period start."""
    today = fields.Date.context_today(order)
    period_start = start
    count = 0
    while period_start <= today and count < 13:
        invoice = order._create_subscription_invoice()
        invoice.invoice_date = period_start
        invoice.action_post()
        # pay all but the latest period, so some invoices stay open like in real life
        nxt = plan.get_next_date(period_start)
        if pay and nxt <= today:
            _pay(env, invoice, period_start + timedelta(days=5))
        period_start = nxt
        count += 1
    order.next_invoice_date = period_start


def _create_subscription(env, spec, plans, prods):
    xid, partner_xid, sp, plan_key, days_ago, lines, scenario, extra = spec
    if _ref(env, xid):
        return
    partner = _partner(env, partner_xid)
    if not partner:
        return
    user = _user(env, sp)
    plan = plans[plan_key]
    today = fields.Date.context_today(env['sale.order'])
    start = today - timedelta(days=days_ago) if days_ago else today + timedelta(days=7)
    order = env['sale.order'].sudo().create({
        'partner_id': partner.id, 'user_id': user.id, 'is_subscription': True, 'plan_id': plan.id,
        'start_date': start, 'next_invoice_date': plan.get_next_date(start),
        'date_order': fields.Datetime.now() - timedelta(days=days_ago + 3),
        'order_line': [Command.create({'product_id': prods[p].product_variant_ids[:1].id, 'product_uom_qty': q})
                       for p, q in lines],
    })
    _bind(env, xid, order)
    for line in order.order_line:
        tmpl_xid = next(x for x, *_ in SUB_PRODUCTS if prods[x] == line.product_id.product_tmpl_id)
        price = PLAN_PRICES.get((tmpl_xid, plan_key), line.product_id.list_price)
        line.price_unit = price

    if scenario == 'draft':
        return
    if scenario == 'sent':
        order.action_quotation_sent()
        order.subscription_state = 'sent'
        return

    order.action_confirm()
    order.write({'start_date': start, 'date_order': fields.Datetime.now() - timedelta(days=days_ago)})
    if 'first_contract_date' in order._fields:
        order.first_contract_date = start
    _sub_invoices(env, order, plan, start, extra.get('pay'))

    if scenario == 'to_renew':
        order.end_date = plan.get_next_date(start) - timedelta(days=1)
        order.action_set_to_renew()
        order.activity_schedule('mail.mail_activity_data_call', date_deadline=today + timedelta(days=3),
                                summary='Renewal call: offer the new estate coffees', user_id=user.id)
    elif scenario == 'renewal_quote':
        order.end_date = order.next_invoice_date
        wizard = env['sale.subscription.renew.wizard'].sudo().create({
            'subscription_id': order.id, 'plan_id': plans['yearly'].id, 'renewal_type': 'new_quote',
            'start_date': order.next_invoice_date, 'end_date': plans['yearly'].get_next_date(order.next_invoice_date)})
        wizard.action_apply_renewal()
        renewal = order.renewal_order_ids[:1] if 'renewal_order_ids' in order._fields else False
        if renewal:
            _bind(env, f'{xid}_renewal', renewal)
            for line in renewal.order_line:
                line.price_unit = PLAN_PRICES.get(('rc_sub_prod_bean_club', 'yearly'), line.price_unit)
            renewal.action_quotation_sent()
    elif scenario == 'upsell':
        order.action_upsell_subscription()
        upsell = order.upsell_order_ids[:1] if 'upsell_order_ids' in order._fields else False
        if upsell:
            _bind(env, f'{xid}_upsell', upsell)
            upsell.order_line[:1].product_uom_qty = extra.get('upsell_qty', 1)
            upsell.write({'order_line': [Command.create({
                'product_id': prods['rc_sub_prod_bean_club'].product_variant_ids[:1].id, 'product_uom_qty': 2,
                'price_unit': prods['rc_sub_prod_bean_club'].list_price})]})
            upsell.message_post(body="Customer asked for 2 more boxes for the new floor and a monthly bean club.",
                                message_type='comment', subtype_xmlid='mail.mt_note')
    elif scenario == 'paused':
        order.action_pause_subscription()
        order.message_post(body="Paused for 2 months while the member is travelling.", message_type='comment',
                           subtype_xmlid='mail.mt_note')
    elif scenario == 'churn':
        reason = _ref(env, extra['reason'])
        if reason:
            env['sale.subscription.close.wizard'].sudo().create({
                'subscription_id': order.id, 'close_reason_id': reason.id,
                'close_date': today - timedelta(days=10), 'notes': extra.get('notes')}).action_close()
            order.end_date = today - timedelta(days=10)


def load_subscription_demo_data(env):
    if 'sale.subscription.plan' not in env or 'is_subscription' not in env['sale.order']._fields:
        _logger.info("Hudson POS: hudson_subscriptions not installed, skipping Subscriptions demo data.")
        return
    plans = _plans(env)
    _get_or_create(env, 'rc_sub_reason_moved', 'sale.subscription.close.reason',
                   {'name': 'Moved location / no longer in delivery area', 'sequence': 50})
    prods = _sub_products(env, plans)
    for spec in SUBSCRIPTIONS:
        try:
            with env.cr.savepoint():
                _create_subscription(env, spec, plans, prods)
        except Exception as e:
            _logger.exception("Hudson POS: Subscription demo %s failed: %s", spec[0], e)


# =========================================================================== entry point
def load_rental_subscription_suite_demo_data(env):
    for name, loader in (('Rental', load_rental_demo_data), ('Subscriptions', load_subscription_demo_data)):
        try:
            with env.cr.savepoint():
                loader(env)
        except Exception as e:
            _logger.exception("Hudson POS: %s demo data failed: %s", name, e)
    _logger.info("Hudson POS: Resto Cafe Rental & Subscriptions demo data loaded.")
