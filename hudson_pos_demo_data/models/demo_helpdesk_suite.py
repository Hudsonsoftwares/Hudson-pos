# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Helpdesk demo data (custom module helpdesk_management_pro + bridges).

Creates, idempotently (every record bound to an xmlid of this module, prefix rc_hd_):
  * 4 teams (Customer Care, Catering & Events, Webshop Orders, IT & POS Support) with SLA, ratings,
    website form, refunds / coupons / gift cards / returns, timesheets and eLearning options
  * ticket types (categories), sources, tags (with dispatch users), an IT-only stage
  * SLA policies (assignment and reaching-stage targets, by priority / tag)
  * 25 tickets over the last 30 days in every stage, with customer e-mails and agent replies in the
    chatter, backdated SLA statuses (reached / failed / ongoing / paused), ratings and time logs
  * links through the bridges: CRM leads, project tasks, eLearning course + lesson, and the after-sales
    wizards (credit note, coupon, gift card)
No e-mail is sent: receipt / stage e-mails are switched off while loading and chatter messages are
written directly as mail.message records.
"""
import logging
from contextlib import contextmanager
from datetime import timedelta

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
TICKET = 'helpdesk.management.ticket'
CTX = {'tracking_disable': True, 'mail_auto_subscribe_no_notify': True, 'mail_notrack': True, 'loyalty_no_mail': True}


# --------------------------------------------------------------------------- helpers
def _ref(env, xid):
    if not xid:
        return None
    if '.' not in xid:
        xid = f'{MODULE}.{xid}'
    return env.ref(xid, raise_if_not_found=False)


def _bind(env, xid, record):
    env['ir.model.data'].sudo().create({
        'module': MODULE, 'name': xid, 'model': record._name, 'res_id': record.id, 'noupdate': True,
    })
    return record


def _get_or_create(env, xid, model, vals):
    rec = _ref(env, xid)
    if rec and rec.exists():
        return rec
    return _bind(env, xid, env[model].sudo().with_context(**CTX).create(vals))


def _now():
    return fields.Datetime.now().replace(microsecond=0)


@contextmanager
def _no_outgoing_mail(env):
    """Switch off ticket receipts and stage e-mails while loading, restore them afterwards."""
    teams = env['helpdesk.management.team'].sudo().search([('use_ticket_receipt', '=', True)])
    stages = env['helpdesk.management.stage'].sudo().search([('template_id', '!=', False)])
    stage_templates = {s.id: s.template_id.id for s in stages}
    teams.write({'use_ticket_receipt': False})
    stages.write({'template_id': False})
    try:
        yield
    finally:
        teams.exists().write({'use_ticket_receipt': True})
        for stage in stages.exists():
            stage.template_id = stage_templates[stage.id]


# --------------------------------------------------------------------------- master data
SOURCES = [('rc_hd_src_email', 'Email'), ('rc_hd_src_phone', 'Phone'), ('rc_hd_src_web', 'Website Form'),
           ('rc_hd_src_chat', 'Live Chat'), ('rc_hd_src_whatsapp', 'WhatsApp'), ('rc_hd_src_walkin', 'Walk-in / Front Desk'),
           ('rc_hd_src_internal', 'Internal')]
TAGS = [('rc_hd_tag_food', 'Food Quality', 1, None), ('rc_hd_tag_delay', 'Delivery Delay', 2, None),
        ('rc_hd_tag_wrong', 'Wrong Order', 3, None), ('rc_hd_tag_allergy', 'Allergy', 9, None),
        ('rc_hd_tag_billing', 'Billing & GST', 4, None), ('rc_hd_tag_vip', 'VIP / Corporate', 10, None),
        ('rc_hd_tag_aggregator', 'Swiggy / Zomato', 5, None), ('rc_hd_tag_catering', 'Catering', 6, None),
        ('rc_hd_tag_hardware', 'Hardware', 7, 'admin'), ('rc_hd_tag_network', 'Network & Wi-Fi', 8, 'arjun'),
        ('rc_hd_tag_course', 'eLearning', 11, None)]
TEAMS = [
    ('rc_hd_team_care', 'Customer Care – Dine-in & Delivery', 'admin', 'balanced', 1,
     'Guests of the restaurant, café and delivery: food quality, delays, bills, bookings and feedback.',
     {'use_rating': True, 'use_website_helpdesk_form': True, 'use_credit_notes': True, 'use_coupons': True,
      'use_gift_cards': True, 'use_auto_close': True, 'auto_close_ticket_days': 7, 'use_closure_by_customer': True,
      'use_website_helpdesk_elearning': True}),
    ('rc_hd_team_events', 'Catering & Events Support', 'arjun', 'random', 4,
     'Corporate catering, weddings and parties: guest-count changes, menus, delivery and invoices.',
     {'use_rating': True, 'use_credit_notes': True, 'use_coupons': True}),
    ('rc_hd_team_webshop', 'Webshop Orders', 'admin', 'balanced', 2,
     'Packaged food sold on the website: damaged parcels, wrong items, payments, returns and replacements.',
     {'use_rating': True, 'use_credit_notes': True, 'use_product_returns': True, 'use_product_replacements': True,
      'use_website_helpdesk_form': True}),
    ('rc_hd_team_it', 'IT & POS Support (internal)', 'admin', 'tags', 8,
     'Internal team: POS terminals, KDS screens, receipt printers, self-order QR and Wi-Fi.',
     {'use_helpdesk_timesheet': True, 'visibility_member_type': 'internal'}),
]
CATEGORIES = [('rc_hd_cat_complaint', 'Complaint', 'rc_hd_team_care'), ('rc_hd_cat_refund', 'Refund Request', 'rc_hd_team_care'),
              ('rc_hd_cat_order', 'Order Issue', 'rc_hd_team_webshop'), ('rc_hd_cat_feedback', 'Feedback', 'rc_hd_team_care'),
              ('rc_hd_cat_booking', 'Booking Change', 'rc_hd_team_events'), ('rc_hd_cat_billing', 'Billing & GST', 'rc_hd_team_care'),
              ('rc_hd_cat_pos', 'POS / KDS Issue', 'rc_hd_team_it'), ('rc_hd_cat_course', 'Course Support', 'rc_hd_team_care')]
# xid, team, name, priority, tags, target stage xmlid, target type, hours
SLAS = [
    ('rc_hd_sla_care_urgent', 'rc_hd_team_care', 'Urgent: assigned within 1 hour', '3', [], None, 'assign', 1),
    ('rc_hd_sla_care_resolve', 'rc_hd_team_care', 'Complaints solved within 8 working hours', False, [], 'helpdesk_management_pro.stage_solved', 'reaching_stage', 8),
    ('rc_hd_sla_care_allergy', 'rc_hd_team_care', 'Allergy cases in progress within 2 hours', False, ['rc_hd_tag_allergy'], 'helpdesk_management_pro.stage_in_progress', 'reaching_stage', 2),
    ('rc_hd_sla_events_urgent', 'rc_hd_team_events', 'Event-day issues in progress within 2 hours', '3', [], 'helpdesk_management_pro.stage_in_progress', 'reaching_stage', 2),
    ('rc_hd_sla_events_resolve', 'rc_hd_team_events', 'Booking changes confirmed within 24 working hours', False, [], 'helpdesk_management_pro.stage_solved', 'reaching_stage', 24),
    ('rc_hd_sla_webshop', 'rc_hd_team_webshop', 'Webshop issues solved within 16 working hours', False, [], 'helpdesk_management_pro.stage_solved', 'reaching_stage', 16),
    ('rc_hd_sla_it_down', 'rc_hd_team_it', 'POS / KDS down: in progress within 1 hour', '3', [], 'helpdesk_management_pro.stage_in_progress', 'reaching_stage', 1),
    ('rc_hd_sla_it_resolve', 'rc_hd_team_it', 'IT requests solved within 24 working hours', False, [], 'helpdesk_management_pro.stage_solved', 'reaching_stage', 24),
]
CUSTOMERS = [('rc_hd_cust_ravi', 'Ravi Menon', 'ravi.menon@example.com', '+91 98460 11223'),
             ('rc_hd_cust_annmary', 'Ann Mary George', 'annmary.george@example.com', '+91 94470 55120'),
             ('rc_hd_cust_fathima', 'Fathima Rahman', 'fathima.rahman@example.com', '+91 97450 33018'),
             ('rc_hd_cust_joseph', 'Joseph Varghese', 'joseph.varghese@example.com', '+91 98950 77441'),
             ('rc_hd_cust_nikhil', 'Nikhil Das', 'nikhil.das@example.com', '+91 90370 66290'),
             ('rc_hd_cust_meera', 'Meera Pillai', 'meera.pillai@example.com', '+91 94960 12876')]

STAGE = {'new': 'helpdesk_management_pro.stage_new', 'progress': 'helpdesk_management_pro.stage_in_progress',
         'hold': 'helpdesk_management_pro.stage_on_hold', 'solved': 'helpdesk_management_pro.stage_solved',
         'cancel': 'helpdesk_management_pro.stage_cancelled', 'vendor': f'{MODULE}.rc_hd_stage_it_vendor'}

# --------------------------------------------------------------------------- tickets
# xid: (team, category, source, subject, partner xid, priority, stage, created days ago (float),
#       assigned after hours (None = unassigned), stage reached after hours, user, tags, kanban_state,
#       messages [(from 'c'|'a', hours after creation, text)], rating (stars, feedback) | None, extras)
T = {
    'rc_hd_t01': ('rc_hd_team_care', 'rc_hd_cat_complaint', 'rc_hd_src_phone', 'Chicken biryani delivered cold and 50 minutes late',
                  'rc_hd_cust_ravi', '2', 'solved', 12.2, 0.3, 3, 'arjun', ['rc_hd_tag_delay', 'rc_hd_tag_food'], 'normal', [
                      ('c', 0, 'I ordered 2 chicken biryanis for delivery at 8 PM. They arrived at 8:50 and were cold. Very disappointed.'),
                      ('a', 0.4, 'We are really sorry, Mr. Menon. Our rider was stuck at the Vyttila block. We are sending a fresh hot replacement right now, and a coupon for your next order.'),
                      ('c', 2.5, 'Replacement came hot and quickly. Thank you for handling it.')],
                  (4, 'Late delivery, but the team fixed it fast and the replacement was excellent.'), {'coupon': True}),
    'rc_hd_t02': ('rc_hd_team_care', 'rc_hd_cat_complaint', 'rc_hd_src_walkin', 'Hair found in appam and stew at table 7',
                  'rc_hd_cust_annmary', '3', 'solved', 20.1, 0.1, 1.5, 'admin', ['rc_hd_tag_food'], 'normal', [
                      ('c', 0, 'We found a hair in the vegetable stew served with our appams. This is not acceptable.'),
                      ('a', 0.2, 'We sincerely apologise. The dish was removed from your bill and the kitchen hair-net check was repeated with the whole shift. Please accept a gift card for your next visit.')],
                  (3, 'Manager apologised and removed the dish, but this should not happen.'), {'giftcard': 500}),
    'rc_hd_t03': ('rc_hd_team_care', 'rc_hd_cat_complaint', 'rc_hd_src_whatsapp', 'Nut allergy: dessert contained cashew despite note',
                  'rc_hd_cust_fathima', '3', 'progress', 1.2, 0.5, 4, 'admin', ['rc_hd_tag_allergy', 'rc_hd_tag_food'], 'normal', [
                      ('c', 0, 'My son is allergic to nuts. I wrote it on the order but the payasam had cashews. Luckily he did not eat much.'),
                      ('a', 4.2, 'We are taking this very seriously. The allergen note did not print on the kitchen ticket. Our chef is reviewing the KDS settings today and we will call you this evening.')],
                  None, {}),
    'rc_hd_t04': ('rc_hd_team_care', 'rc_hd_cat_billing', 'rc_hd_src_email', 'Service charge added twice on dinner bill',
                  'rc_hd_cust_joseph', '1', 'solved', 6.3, 1, 5, 'arjun', ['rc_hd_tag_billing'], 'normal', [
                      ('c', 0, 'Bill no. 0042 from Saturday shows the 5% service charge twice. Please check.'),
                      ('a', 2, 'You are right, the cashier applied the service charge again after splitting the bill. We have refunded the extra amount to your card.')],
                  (5, 'Quick and honest response, refund received.'), {}),
    'rc_hd_t05': ('rc_hd_team_care', 'rc_hd_cat_refund', 'rc_hd_src_email', 'Birthday cake message misspelt – partial refund',
                  'rc_sale_partner_priya', '2', 'solved', 2.4, 0.5, 6, 'arjun', ['rc_hd_tag_catering'], 'normal', [
                      ('c', 0, "The cake for my daughter's party said 'Happy Brithday'. Everything else was lovely but this spoiled the photos."),
                      ('a', 1, 'We are so sorry, Ms. Raghavan. We have issued a credit note for the cake on your birthday package order.')],
                  (5, 'They refunded the cake without any argument. Will book again.'), {'refund': ('rc_so_birthday_priya', 'rc_sp_cake')}),
    'rc_hd_t06': ('rc_hd_team_care', 'rc_hd_cat_booking', 'rc_hd_src_web', 'Table booking confirmation e-mail not received',
                  'rc_hd_cust_nikhil', '1', 'new', 0.1, None, None, None, [], 'normal', [
                      ('c', 0, 'I booked a table for 6 on Friday at 8 PM on your website but did not get any confirmation. Is my booking done?')],
                  None, {}),
    'rc_hd_t07': ('rc_hd_team_care', 'rc_hd_cat_feedback', 'rc_hd_src_web', 'Compliments for the Onam Sadya',
                  'rc_hd_cust_meera', '0', 'solved', 29.5, 2, 3, 'arjun', [], 'normal', [
                      ('c', 0, 'Just wanted to say the Onam Sadya was the best we have had outside home. The ada pradhaman was perfect!'),
                      ('a', 2.5, 'Thank you so much, Ms. Pillai! We have shared your message with the kitchen team.')],
                  (5, 'Lovely food and very warm staff.'), {}),
    'rc_hd_t08': ('rc_hd_team_care', 'rc_hd_cat_order', 'rc_hd_src_chat', 'Zomato order missing raita and dessert',
                  'rc_hd_cust_ravi', '1', 'hold', 3.2, 0.5, 2, 'arjun', ['rc_hd_tag_aggregator', 'rc_hd_tag_wrong'], 'waiting_customer', [
                      ('c', 0, 'My Zomato order #ZM-88412 came without the raita and the gulab jamun.'),
                      ('a', 1, 'Sorry about that. Could you share a photo of the bill sticker on the bag so we can claim it with Zomato and refund you?')],
                  None, {}),
    'rc_hd_t09': ('rc_hd_team_care', 'rc_hd_cat_course', 'rc_hd_src_email', 'Food Safety certification exam does not load',
                  'rc_learner_anu', '2', 'progress', 1.1, 1, 2, 'admin', ['rc_hd_tag_course'], 'normal', [
                      ('c', 0, 'I completed the lessons of the Food Safety course but the Final Certification Exam page keeps loading.'),
                      ('a', 2, 'Thanks Anu. We reset your attempt; please clear the browser cache and try again. We will keep this ticket open until you pass.')],
                  None, {'course': ('slide_channel_food_safety', 'slide_safety_certification')}),
    'rc_hd_t10': ('rc_hd_team_care', 'rc_hd_cat_billing', 'rc_hd_src_phone', 'Wrong bill split for group of 12',
                  'rc_hd_cust_joseph', '0', 'cancel', 9.0, 0.5, 1, 'admin', ['rc_hd_tag_billing'], 'normal', [
                      ('c', 0, 'Our group bill was split wrongly.'),
                      ('a', 1, 'This is the same issue as your earlier ticket about the double service charge, so we are closing this duplicate.')],
                  None, {}),
    'rc_hd_t11': ('rc_hd_team_events', 'rc_hd_cat_booking', 'rc_hd_src_email', 'Wedding reception: increase guest count from 450 to 480',
                  'rc_partner_marina_events_contact', '2', 'progress', 2.1, 0.5, 3, 'arjun', ['rc_hd_tag_catering', 'rc_hd_tag_vip'], 'normal', [
                      ('c', 0, 'The families confirmed 30 more guests. Can you update the quotation to 480 and add one more live appam counter?'),
                      ('a', 3, 'Noted, Anjali. Our chef confirmed capacity for 480. A revised quotation will be sent today with the extra counter.')],
                  None, {'lead': 'Wedding Reception Catering & Live Counters (450 pax)'}),
    'rc_hd_t12': ('rc_hd_team_events', 'rc_hd_cat_complaint', 'rc_hd_src_phone', 'Corporate lunch boxes delivered 40 minutes late',
                  'rc_partner_harbour_park_contact', '3', 'solved', 5.2, 3, 30, 'admin', ['rc_hd_tag_delay', 'rc_hd_tag_vip'], 'normal', [
                      ('c', 0, '120 lunch boxes were due at 12:30, they reached at 1:10. Our staff had to wait. Please make sure this does not repeat.'),
                      ('a', 3.5, 'We apologise, Mr. Pillai. The van had a flat tyre. From tomorrow a second van leaves 20 minutes earlier for your campus.'),
                      ('c', 28, 'Today it was on time. Thanks.')],
                  (2, 'Food is good but the delay disrupted our lunch break.'), {'coupon': True}),
    'rc_hd_t13': ('rc_hd_team_events', 'rc_hd_cat_feedback', 'rc_hd_src_email', 'Request sugar-free pastry options for staff cafeteria',
                  'rc_partner_greenleaf_contact', '1', 'new', 1.0, None, None, None, ['rc_hd_tag_vip'], 'normal', [
                      ('c', 0, 'Many of our doctors and patients are diabetic. Could you add sugar-free options to the bakery supply?')],
                  None, {'lead': 'Hospital Staff Night-Shift Meal Plan'}),
    'rc_hd_t14': ('rc_hd_team_events', 'rc_hd_cat_booking', 'rc_hd_src_email', 'Annual Day: 50 extra Jain meal boxes',
                  'rc_partner_st_teresa_contact', '2', 'hold', 4.0, 1, 2, 'arjun', ['rc_hd_tag_catering'], 'waiting_customer', [
                      ('c', 0, 'We need 50 of the 600 boxes as Jain meals (no onion, no garlic).'),
                      ('a', 2, 'Certainly, Father. Please confirm the final count of Jain boxes by Friday so we can plan the separate preparation.')],
                  None, {'lead': 'School Annual Day Snacks (600 students)'}),
    'rc_hd_t15': ('rc_hd_team_events', 'rc_hd_cat_billing', 'rc_hd_src_email', 'GSTIN missing on catering invoice',
                  'rc_partner_film_society_contact', '1', 'solved', 15.0, 2, 7, 'admin', ['rc_hd_tag_billing'], 'normal', [
                      ('c', 0, 'Our GSTIN is not printed on the invoice, so we cannot claim input credit.'),
                      ('a', 6, 'Apologies, Meera. We updated your GSTIN on your customer record and re-issued the invoice.')],
                  (4, 'Sorted within the day.'), {}),
    'rc_hd_t16': ('rc_hd_team_events', 'rc_hd_cat_refund', 'rc_hd_src_phone', 'Marathon kiosks cancelled – advance refund',
                  'rc_partner_coastal_runners_contact', '1', 'solved', 25.0, 1, 20, 'arjun', ['rc_hd_tag_catering', 'rc_hd_tag_billing'], 'normal', [
                      ('c', 0, 'The run is now sponsor-catered. Please cancel our snack kiosk order and refund the advance.'),
                      ('a', 2, 'Understood, Divya. The order is cancelled and the advance will be refunded within 5 working days.')],
                  (3, 'Refund took a few days but was fine.'), {}),
    'rc_hd_t17': ('rc_hd_team_webshop', 'rc_hd_cat_order', 'rc_hd_src_web', 'Banana chips packs arrived crushed',
                  'rc_hd_cust_annmary', '1', 'progress', 1.3, 2, 3, 'admin', ['rc_hd_tag_wrong'], 'normal', [
                      ('c', 0, 'Three of the five banana chips packs arrived completely crushed.'),
                      ('a', 3, 'Sorry! We are shipping 3 replacement packs in a box with bubble wrap. No need to return the crushed ones.')],
                  None, {}),
    'rc_hd_t18': ('rc_hd_team_webshop', 'rc_hd_cat_order', 'rc_hd_src_email', 'Received mango pickle instead of lime pickle',
                  'rc_hd_cust_meera', '1', 'solved', 8.0, 1, 10, 'arjun', ['rc_hd_tag_wrong'], 'normal', [
                      ('c', 0, 'I ordered lime pickle 400 g but got mango pickle.'),
                      ('a', 2, 'Our mistake, sorry. The correct lime pickle is on its way; please keep the mango pickle with our compliments.')],
                  (5, 'Very generous, thank you!'), {}),
    'rc_hd_t19': ('rc_hd_team_webshop', 'rc_hd_cat_complaint', 'rc_hd_src_web', 'Coffee powder close to best-before date',
                  'rc_hd_cust_nikhil', '1', 'new', 0.2, None, None, None, ['rc_hd_tag_food'], 'normal', [
                      ('c', 0, 'The filter coffee powder I received expires in 3 weeks. I expected a fresher pack.')],
                  None, {}),
    'rc_hd_t20': ('rc_hd_team_webshop', 'rc_hd_cat_billing', 'rc_hd_src_chat', 'Payment debited but order not confirmed',
                  'rc_hd_cust_fathima', '3', 'progress', 4.0, 26, 27, 'arjun', ['rc_hd_tag_billing'], 'normal', [
                      ('c', 0, 'My UPI payment of ₹1,240 was debited but the website shows the order as pending.'),
                      ('a', 26.5, 'Sorry for the delay. The payment provider confirmed the amount; we are confirming your order manually now.')],
                  None, {}),
    'rc_hd_t21': ('rc_hd_team_webshop', 'rc_hd_cat_feedback', 'rc_hd_src_email', 'Bulk order: 50 Kerala snack hampers for tour groups',
                  'rc_partner_spice_route_contact', '1', 'new', 0.9, None, None, None, ['rc_hd_tag_vip'], 'normal', [
                      ('c', 0, 'We would like 50 snack hampers as welcome gifts for our tour groups. Is a bulk discount possible?')],
                  None, {'lead': 'Tourist Group Lunch Packages'}),
    'rc_hd_t22': ('rc_hd_team_it', 'rc_hd_cat_pos', 'rc_hd_src_internal', 'KDS screen on Hot Kitchen froze during dinner rush',
                  None, '3', 'solved', 3.1, 0.2, 0.5, 'admin', ['rc_hd_tag_hardware'], 'normal', [
                      ('c', 0, 'Hot Kitchen KDS stuck at 8:15 PM, orders not updating. Using printed tickets for now.'),
                      ('a', 0.5, 'Restarted the KDS box and cleared the browser cache. Vendor visit planned to replace the power adapter.')],
                  None, {'time': [(0.5, 'Remote restart and cache clear'), (1.5, 'On-site check with vendor, adapter replaced')],
                         'task': 'Replace KDS power adapter (Hot Kitchen)'}),
    'rc_hd_t23': ('rc_hd_team_it', 'rc_hd_cat_pos', 'rc_hd_src_internal', 'Receipt printer not printing the survey QR code',
                  None, '2', 'progress', 1.0, 0.3, 1, 'arjun', ['rc_hd_tag_hardware'], 'blocked', [
                      ('c', 0, 'Cafe counter printer prints the bill but the survey QR is blank.'),
                      ('a', 1, 'Printer firmware does not support the image size; waiting for the vendor firmware update.')],
                  None, {'time': [(0.75, 'Tested QR sizes and printer settings')]}),
    'rc_hd_t24': ('rc_hd_team_it', 'rc_hd_cat_pos', 'rc_hd_src_internal', 'Patio Wi-Fi drops – self-order QR menu fails',
                  None, '2', 'vendor', 2.0, 0.5, 4, 'arjun', ['rc_hd_tag_network'], 'normal', [
                      ('c', 0, 'Guests on the Patio cannot open the QR menu, Wi-Fi keeps dropping.'),
                      ('a', 4, 'Access point is faulty. Replacement ordered from the ISP; ticket parked in Waiting for Vendor.')],
                  None, {'time': [(1.0, 'Wi-Fi survey of patio')], 'task': 'Replace patio Wi-Fi access point'}),
    'rc_hd_t25': ('rc_hd_team_it', 'rc_hd_cat_pos', 'rc_hd_src_internal', 'New waiter needs POS login and PIN',
                  None, '0', 'new', 0.05, None, None, None, [], 'normal', [
                      ('c', 0, 'Kevin joins the floor team tomorrow and needs a POS user and PIN for the Restaurant shop.')],
                  None, {}),
}


# --------------------------------------------------------------------------- steps
def _users(env):
    return {'admin': env.ref('base.user_admin'), 'arjun': _ref(env, 'rc_user_arjun') or env.ref('base.user_admin')}


def _master_data(env):
    users = _users(env)
    for xid, name in SOURCES:
        _get_or_create(env, xid, 'helpdesk.management.source', {'name': name})
    for xid, name, color, user in TAGS:
        vals = {'name': name, 'color': color}
        if user:
            vals['user_ids'] = [Command.set(users[user].ids)]
        _get_or_create(env, xid, 'helpdesk.management.tag', vals)
    Team = env['helpdesk.management.team']
    courses = env['slide.channel'] if 'slide.channel' in env else None
    for xid, name, leader, method, color, desc, opts in TEAMS:
        vals = {'name': name, 'user_id': users[leader].id, 'member_ids': [Command.set((users['admin'] | users['arjun']).ids)],
                'assignment_method': method, 'color': color, 'description': desc, 'use_sla': True}
        vals.update({k: v for k, v in opts.items() if k in Team._fields})
        if vals.get('use_website_helpdesk_form') and 'website_id' in Team._fields:
            vals['website_id'] = env['website'].search([], limit=1).id
        if vals.get('use_website_helpdesk_elearning') and courses is not None:
            channels = env['slide.channel'].browse([c.id for c in (
                _ref(env, x) for x in ('slide_channel_food_safety', 'slide_channel_barista_coffee', 'slide_channel_kerala_cuisine')) if c])
            vals['website_slide_channel_ids'] = [Command.set(channels.ids)]
        _get_or_create(env, xid, 'helpdesk.management.team', vals)
    for team_xid in ('rc_hd_team_care',):
        team = _ref(env, team_xid)
        stage = _ref(env, 'helpdesk_management_pro.stage_solved')
        if team and stage and 'auto_close_stage_id' in team._fields and not team.auto_close_stage_id:
            team.write({'auto_close_stage_id': stage.id,
                        'auto_close_in_stage_ids': [Command.set(_ref(env, 'helpdesk_management_pro.stage_on_hold').ids)]})
    _get_or_create(env, 'rc_hd_stage_it_vendor', 'helpdesk.management.stage', {
        'name': 'Waiting for Vendor', 'sequence': 3, 'description': 'Parts or a vendor visit are needed.',
        'team_ids': [Command.set(_ref(env, 'rc_hd_team_it').ids)]})
    for xid, name, team_xid in CATEGORIES:
        _get_or_create(env, xid, 'helpdesk.management.category', {'name': name, 'team_id': _ref(env, team_xid).id})
    for xid, team_xid, name, prio, tags, stage_xid, ttype, hours in SLAS:
        vals = {'name': name, 'team_id': _ref(env, team_xid).id, 'priority': prio, 'target_type': ttype, 'target_hours': hours,
                'stage_id': (_ref(env, stage_xid) or _ref(env, 'helpdesk_management_pro.stage_solved')).id,
                'tag_ids': [Command.set([_ref(env, t).id for t in tags])]}
        if ttype == 'reaching_stage':
            vals['exclude_stage_ids'] = [Command.set(_ref(env, 'helpdesk_management_pro.stage_on_hold').ids)]
        _get_or_create(env, xid, 'helpdesk.management.sla', vals)
    for xid, name, email, phone in CUSTOMERS:
        _get_or_create(env, xid, 'res.partner', {'name': name, 'email': email, 'phone': phone, 'city': 'Kochi',
                                                 'country_id': env.ref('base.in').id})


def _project(env):
    if 'project.project' not in env:
        return None
    return _get_or_create(env, 'rc_hd_project', 'project.project', {
        'name': 'Service Recovery & IT Fixes', 'description': '<p>Interventions planned from Helpdesk tickets.</p>'})


def _post(env, ticket, author, when, body, from_customer):
    env['mail.message'].sudo().create({
        'model': TICKET, 'res_id': ticket.id, 'body': f'<p>{body}</p>', 'date': when,
        'message_type': 'email' if from_customer else 'comment',
        'subtype_id': env.ref('mail.mt_comment').id,
        'author_id': author.id, 'email_from': author.email_formatted or author.name,
    })


def _create_ticket(env, xid, spec, users, project):
    if _ref(env, xid):
        return
    (team_xid, cat_xid, src_xid, subject, partner_xid, prio, stage_key, days, assign_h, reach_h, user_key,
     tag_xids, kanban, messages, rating, extra) = spec
    team = _ref(env, team_xid)
    partner = _ref(env, partner_xid) if partner_xid else users['admin'].partner_id
    if not partner:
        partner = users['admin'].partner_id
    stage = _ref(env, STAGE[stage_key])
    user = users[user_key] if user_key else env['res.users']
    created = _now() - timedelta(days=days)
    if days >= 1 and created.weekday() >= 5:
        # the company works Mon-Fri: tickets of the past live on working days so SLA timers are meaningful
        created -= timedelta(days=created.weekday() - 4)
    Ticket = env[TICKET].sudo().with_context(**CTX)
    vals = {'subject': subject, 'team_id': team.id, 'category_id': _ref(env, cat_xid).id, 'source_id': _ref(env, src_xid).id,
            'partner_id': partner.id, 'priority': prio, 'tag_ids': [Command.set([_ref(env, t).id for t in tag_xids])],
            'description': f'<p>{messages[0][2]}</p>'}
    if user:
        vals['user_id'] = user.id
    ticket = _bind(env, xid, Ticket.create(vals))
    if not user and ticket.user_id:  # auto-assignment of the team: keep the demo ticket unassigned
        ticket.with_context(helpdesk_auto_assign=True).user_id = False
    if stage != ticket.stage_id:
        ticket.stage_id = stage
    if kanban != 'normal':
        ticket.kanban_state = kanban

    # backdate the ticket's life cycle
    assign_dt = created + timedelta(hours=assign_h) if assign_h is not None and ticket.user_id else None
    reach_dt = created + timedelta(hours=reach_h) if reach_h is not None else created
    close_dt = reach_dt if stage.is_close else None
    env.cr.execute(
        f"UPDATE {Ticket._table} SET create_date=%s, write_date=%s, assign_date=%s, close_date=%s, date_last_stage_update=%s WHERE id=%s",
        (created, reach_dt, assign_dt, close_dt, reach_dt, ticket.id))
    ticket.invalidate_recordset()
    _rebuild_sla(env, ticket, created, assign_dt, reach_dt)

    # chatter: customer e-mail and agent replies
    agent = (user or users['admin']).partner_id
    for who, hours, text in messages:
        _post(env, ticket, partner if who == 'c' else agent, created + timedelta(hours=hours), text, who == 'c')

    if rating:
        env['helpdesk.management.ticket.rating'].sudo().create({
            'ticket_id': ticket.id, 'rating': str(rating[0]), 'feedback': rating[1], 'date': (close_dt or reach_dt) + timedelta(hours=2)})
    for hours, desc in extra.get('time', []):
        env['helpdesk.management.ticket.time'].sudo().create({
            'ticket_id': ticket.id, 'user_id': (user or users['admin']).id, 'description': desc, 'duration': hours,
            'date': created.date()})
    if extra.get('lead') and 'lead_id' in ticket._fields:
        lead = env['crm.lead'].sudo().with_context(active_test=False).search([('name', '=', extra['lead'])], limit=1)
        if lead:
            ticket.lead_id = lead
            if 'helpdesk_ticket_id' in lead._fields and not lead.helpdesk_ticket_id:
                lead.with_context(**CTX).helpdesk_ticket_id = ticket
    if extra.get('course') and 'course_id' in ticket._fields:
        course, slide = (_ref(env, x) for x in extra['course'])
        if course:
            ticket.course_id = course
            if slide:
                ticket.slide_id = slide
    if extra.get('task') and project and 'task_id' in ticket._fields:
        task = _bind(env, f'{xid}_task', env['project.task'].sudo().with_context(**CTX).create({
            'name': extra['task'], 'project_id': project.id, 'helpdesk_ticket_id': ticket.id,
            'user_ids': [Command.set((user or users['admin']).ids)],
            'date_deadline': fields.Date.today() + timedelta(days=3),
            'description': f'<p>Planned from ticket {ticket.name}: {subject}</p>'}))
        ticket.task_id = task
        if stage.is_close and 'state' in task._fields:
            task.state = '1_done'
    if extra.get('refund') and 'helpdesk.ticket.refund' in env:
        so, product = (_ref(env, x) for x in extra['refund'])
        if so and product:
            res = env['helpdesk.ticket.refund'].sudo().create({
                'ticket_id': ticket.id, 'sale_order_id': so.id, 'product_id': product.product_variant_ids[:1].id,
                'reversal_date': (close_dt or reach_dt).date()}).action_reverse()
            move = env['account.move'].browse(res.get('res_id')) if isinstance(res, dict) else env['account.move']
            if move:
                move.action_post()
                _post(env, ticket, agent, close_dt or reach_dt, f'Credit note {move.name} posted for the cake on {so.name}.', False)
    if extra.get('coupon') and 'helpdesk.ticket.coupon' in env:
        program = _ref(env, 'rc_sale_promo_corporate_coupons') or env['loyalty.program'].search([('program_type', '=', 'coupons')], limit=1)
        if program:
            env['helpdesk.ticket.coupon'].sudo().with_context(**CTX).create({'ticket_id': ticket.id, 'program_id': program.id}).action_get_share_link()
    if extra.get('giftcard') and 'helpdesk.ticket.giftcard' in env:
        program = env['loyalty.program'].search([('program_type', '=', 'gift_card')], limit=1)
        if program:
            env['helpdesk.ticket.giftcard'].sudo().with_context(**CTX).create({
                'ticket_id': ticket.id, 'program_id': program.id, 'gift_card_value': extra['giftcard'],
                'description': 'Apology gift card'}).action_generate()


def _rebuild_sla(env, ticket, created, assign_dt, reach_dt):
    """Recompute the SLA statuses as if the ticket had lived through its backdated dates."""
    now = _now()
    calendar = ticket.team_id.resource_calendar_id or env.company.resource_calendar_id
    for status in ticket.sla_status_ids:
        sla = status.sla_id
        deadline = calendar.plan_hours(sla.target_hours, day_dt=created, compute_leaves=True) if calendar else \
            created + timedelta(hours=sla.target_hours)
        if sla.target_type == 'assign':
            done_dt = assign_dt
        else:
            done_dt = reach_dt if sla._is_stage_reached(ticket.stage_id) else None
        vals = {'start_datetime': created, 'deadline': deadline, 'reached_datetime': False, 'failed_datetime': False,
                'is_paused': False, 'pause_start_time': False}
        if done_dt:
            vals.update({'status': 'reached', 'reached_datetime': done_dt} if not deadline or done_dt <= deadline
                        else {'status': 'failed', 'failed_datetime': done_dt})
        elif ticket.stage_id.is_close:
            vals['status'] = 'cancelled'
        elif ticket.kanban_state in ('waiting_customer', 'blocked') or ticket.stage_id in sla.exclude_stage_ids:
            vals.update({'status': 'ongoing', 'is_paused': True, 'pause_start_time': reach_dt})
        elif deadline and deadline < now:
            vals.update({'status': 'failed', 'failed_datetime': deadline})
        else:
            vals['status'] = 'ongoing'
        status.write(vals)


# --------------------------------------------------------------------------- entry point
def load_helpdesk_suite_demo_data(env):
    if TICKET not in env:
        _logger.info("Hudson POS: Helpdesk Pro not installed, skipping Helpdesk demo data.")
        return
    try:
        with env.cr.savepoint():
            _master_data(env)
    except Exception as e:
        _logger.exception("Hudson POS: Helpdesk master data failed: %s", e)
        return
    project = None
    try:
        with env.cr.savepoint():
            project = _project(env)
    except Exception as e:
        _logger.exception("Hudson POS: Helpdesk project failed: %s", e)
    users = _users(env)
    with _no_outgoing_mail(env):
        for xid, spec in T.items():
            try:
                with env.cr.savepoint():
                    _create_ticket(env, xid, spec, users, project)
            except Exception as e:
                _logger.exception("Hudson POS: Helpdesk ticket %s failed: %s", xid, e)
    _logger.info("Hudson POS: Resto Cafe Helpdesk demo data loaded.")
