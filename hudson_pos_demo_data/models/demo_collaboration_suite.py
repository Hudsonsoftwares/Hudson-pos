# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - collaboration apps demo data.

Idempotent (every record bound to an xmlid of this module), one savepoint per app:
  * Documents (custom DMS): Licences & Compliance, Supplier Contracts, HR Documents, Recipes & SOPs and
    Marketing Assets folders with generated PDF files, tags, categories and licence expiry dates
  * Live Chat: canned responses and 5 past website conversations with ratings
  * Discuss: outlet / team channels with backdated posts
  * Calendar: tastings, supplier visits, trainings, FSSAI inspection and event set-ups
  * Surveys: Dine-in Feedback and Catering Event Feedback with ~20 completed responses
  * Gamification: Dessert Upsell Week, 5-Star Service Month and Zero Wastage Kitchen challenges with badges
"""
import base64
import logging
from datetime import timedelta

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
QUIET = {
    'tracking_disable': True, 'mail_create_nolog': True, 'mail_create_nosubscribe': True, 'mail_notrack': True,
    'no_mail_to_attendees': True, 'dont_notify': True, 'mail_auto_subscribe_no_notify': True,
}


# --------------------------------------------------------------------------- helpers
def _ref(env, xid):
    return env.ref(f'{MODULE}.{xid}', raise_if_not_found=False)


def _bind(env, xid, record):
    env['ir.model.data'].sudo().create({
        'module': MODULE, 'name': xid, 'model': record._name, 'res_id': record.id, 'noupdate': True,
    })
    return record


def _get_or_create(env, xid, model, vals):
    rec = _ref(env, xid)
    if rec and rec.exists():
        return rec
    return _bind(env, xid, env[model].sudo().with_context(**QUIET).create(vals))


def _now():
    return fields.Datetime.now().replace(second=0, microsecond=0)


def _ist(days, hour, minute=0):
    """Naive UTC datetime for `days` from today at hour:minute Kochi time (UTC+5:30)."""
    local = fields.Datetime.to_datetime(fields.Date.today()) + timedelta(days=days, hours=hour, minutes=minute)
    return local - timedelta(hours=5, minutes=30)


def _users(env):
    admin = env.ref('base.user_admin')
    arjun = _ref(env, 'rc_user_arjun') or admin
    return admin, arjun


def _message(env, record, body, date, author=None, guest=None):
    vals = {
        'model': record._name, 'res_id': record.id, 'body': body, 'date': date,
        'message_type': 'comment', 'subtype_id': env.ref('mail.mt_comment').id,
    }
    if guest:
        vals['author_guest_id'] = guest.id
        vals['author_id'] = False
    else:
        vals['author_id'] = (author or env.ref('base.user_admin')).partner_id.id
    return env['mail.message'].sudo().create(vals)


# --------------------------------------------------------------------------- Documents (DMS)
DMS_CATEGORIES = [('rc_dms_cat_compliance', 'Compliance'), ('rc_dms_cat_contracts', 'Contracts'),
                  ('rc_dms_cat_hr', 'HR'), ('rc_dms_cat_operations', 'Operations'), ('rc_dms_cat_marketing', 'Marketing')]
DMS_TAGS = [  # xid, name, category, color
    ('rc_dms_tag_licence', 'Licence', 'rc_dms_cat_compliance', 1), ('rc_dms_tag_renewal', 'Renewal Due', 'rc_dms_cat_compliance', 9),
    ('rc_dms_tag_supplier', 'Supplier', 'rc_dms_cat_contracts', 4), ('rc_dms_tag_signed', 'Signed', 'rc_dms_cat_contracts', 10),
    ('rc_dms_tag_policy', 'Policy', 'rc_dms_cat_hr', 3), ('rc_dms_tag_sop', 'SOP', 'rc_dms_cat_operations', 2),
    ('rc_dms_tag_recipe', 'Recipe', 'rc_dms_cat_operations', 5), ('rc_dms_tag_brand', 'Brand', 'rc_dms_cat_marketing', 6),
]
DMS_FOLDERS = [('rc_dms_dir_licences', 'Licences & Compliance'), ('rc_dms_dir_contracts', 'Supplier Contracts'),
               ('rc_dms_dir_hr', 'HR Documents'), ('rc_dms_dir_sops', 'Recipes & SOPs'), ('rc_dms_dir_marketing', 'Marketing Assets')]
# xid, folder, file name, category, tags, expiry (days from today or None), title, lines
DMS_FILES = [
    ('rc_dms_file_fssai', 'rc_dms_dir_licences', 'FSSAI Food Licence 2026-27.pdf', 'rc_dms_cat_compliance', ['rc_dms_tag_licence'], 138,
     'FSSAI State Licence', ['Licence No. 11326008000123 (State Licence, Kerala)', 'Food Business Operator: Resto Cafe Solutions',
                             'Premises: Marine Drive, Kochi 682031', 'Kind of business: Restaurant, Catering, Bakery',
                             'Valid till 31 March 2027']),
    ('rc_dms_file_trade', 'rc_dms_dir_licences', 'Kochi Corporation Trade Licence.pdf', 'rc_dms_cat_compliance',
     ['rc_dms_tag_licence', 'rc_dms_tag_renewal'], 21,
     'D&O Trade Licence', ['Issued by: Kochi Municipal Corporation, Ernakulam', 'Trade: Restaurant and Hotel (Category B)',
                           'Renewal due within 30 days. Fee: Rs 4,500']),
    ('rc_dms_file_fire', 'rc_dms_dir_licences', 'Fire NOC - Marine Drive Outlet.pdf', 'rc_dms_cat_compliance', ['rc_dms_tag_licence'], 290,
     'Fire Safety No Objection Certificate', ['Kerala Fire and Rescue Services, Ernakulam', 'Occupancy: Assembly (Restaurant), 140 persons',
                                              'Extinguishers: 8 (CO2 and ABC), hydrant point at kitchen entry']),
    ('rc_dms_file_gst', 'rc_dms_dir_licences', 'GST Registration Certificate (Form REG-06).pdf', 'rc_dms_cat_compliance',
     ['rc_dms_tag_licence'], None,
     'GST Registration Certificate', ['GSTIN: 32AABCR1234F1Z5 (Kerala)', 'Legal name: Resto Cafe Solutions',
                                      'Type: Regular, Restaurant services under 5% GST (no ITC)']),
    ('rc_dms_file_health', 'rc_dms_dir_licences', 'Health Inspection Report - Oct 2026.pdf', 'rc_dms_cat_compliance', [], None,
     'Health Inspection Report', ['Inspection date: 14 October 2026', 'Score: 92 / 100 (Grade A)',
                                  'Observation: label two sauce containers in the walk-in chiller']),
    ('rc_dms_file_vypeen', 'rc_dms_dir_contracts', 'Vypeen Harbour Fresh Catch - Supply Agreement.pdf', 'rc_dms_cat_contracts',
     ['rc_dms_tag_supplier', 'rc_dms_tag_signed'], 230,
     'Seafood Supply Agreement', ['Supplier: Vypeen Harbour Fresh Catch', 'Daily delivery before 7:00 AM at 0-4 C in insulated boxes',
                                  'Price review every quarter, payment 15 days', 'Rejection: above 5 C or off smell']),
    ('rc_dms_file_dairy', 'rc_dms_dir_contracts', 'Periyar Valley Dairy - Rate Contract.pdf', 'rc_dms_cat_contracts',
     ['rc_dms_tag_supplier', 'rc_dms_tag_signed'], 45,
     'Dairy Rate Contract', ['Supplier: Periyar Valley Dairy Co-operative', 'Toned milk Rs 52 / L, curd Rs 78 / kg, paneer Rs 380 / kg',
                             'Contract renewal in 45 days']),
    ('rc_dms_file_pest', 'rc_dms_dir_contracts', 'Pest Control AMC - CleanGuard Services.pdf', 'rc_dms_cat_contracts',
     ['rc_dms_tag_supplier'], 75,
     'Pest Control Annual Maintenance', ['Monthly gel and spray treatment, rodent stations checked fortnightly',
                                         'Service report to be filed in this folder after each visit']),
    ('rc_dms_file_handbook', 'rc_dms_dir_hr', 'Employee Handbook 2026.pdf', 'rc_dms_cat_hr', ['rc_dms_tag_policy'], None,
     'Employee Handbook', ['Working hours, shifts and weekly off', 'Uniform and grooming standards', 'Leave policy and festival holidays',
                           'Staff meals, discounts and code of conduct']),
    ('rc_dms_file_leave', 'rc_dms_dir_hr', 'Leave and Attendance Policy.pdf', 'rc_dms_cat_hr', ['rc_dms_tag_policy'], None,
     'Leave and Attendance Policy', ['12 casual, 12 sick and 15 earned leaves per year', 'Kiosk check-in within 10 minutes of shift start',
                                     'Festival leave on Onam, Vishu and Christmas by roster']),
    ('rc_dms_file_opening', 'rc_dms_dir_sops', 'Opening and Closing Checklist.pdf', 'rc_dms_cat_operations', ['rc_dms_tag_sop'], None,
     'Opening and Closing Checklist', ['Opening: chiller/freezer temperatures logged, gas leak check, POS session opened',
                                       'Closing: deep-clean fryers, cash count, KDS cleared, alarm set']),
    ('rc_dms_file_cleaning', 'rc_dms_dir_sops', 'Kitchen Cleaning Schedule.pdf', 'rc_dms_cat_operations', ['rc_dms_tag_sop'], None,
     'Kitchen Cleaning Schedule', ['After every service: boards, knives, prep tables', 'Daily: floors, drains, hoods filters',
                                   'Weekly: walk-in chiller, dry store shelves, exhaust ducts']),
    ('rc_dms_file_fishcurry', 'rc_dms_dir_sops', 'Recipe Card - Kerala Fish Curry.pdf', 'rc_dms_cat_operations', ['rc_dms_tag_recipe'], None,
     'Recipe Card: Kerala Fish Curry', ['Seer fish 1 kg, kudampuli 4 pieces, shallots 150 g, coconut oil 60 ml',
                                        'Simmer 10 minutes, rest 30 minutes before service', 'Plate: clay pot, curry leaves garnish']),
    ('rc_dms_file_brand', 'rc_dms_dir_marketing', 'Brand Guidelines.pdf', 'rc_dms_cat_marketing', ['rc_dms_tag_brand'], None,
     'Brand Guidelines', ['Colours: espresso #15110E, gold #C9A15D, cream #FDFAF5', 'Fonts: Playfair Display and Inter',
                          'Logo clear space: height of the R']),
    ('rc_dms_file_onam', 'rc_dms_dir_marketing', 'Onam Sadya Campaign Brief.pdf', 'rc_dms_cat_marketing', ['rc_dms_tag_brand'], None,
     'Onam Sadya Campaign Brief', ['Channels: website, email, Instagram, in-store posters', 'Offer: 26-dish Sadya at Rs 450, pre-book online',
                                   'Target: 1,200 covers over 3 days']),
]


def _pdf_b64(title, lines):
    from .demo_sales_suite import _pdf
    pages = [{'kicker': 'Resto Cafe Solutions', 'title': title, 'lines': ['-  ' + line for line in lines]}]
    return base64.b64encode(bytes(_pdf(pages))).decode()


def _documents(env):
    if 'dms.directory' not in env:
        return
    storage = env.ref('dms_enterprise_features.dms_storage_enterprise', raise_if_not_found=False) or env['dms.storage'].search([], limit=1)
    if not storage:
        return
    full_access = env['dms.access.group'].search([('name', '=', 'Enterprise Folders (Full Access)')], limit=1)
    for xid, name in DMS_CATEGORIES:
        _get_or_create(env, xid, 'dms.category', {'name': name})
    for xid, name, cat, color in DMS_TAGS:
        _get_or_create(env, xid, 'dms.tag', {'name': name, 'category_id': _ref(env, cat).id, 'color': color})
    for xid, name in DMS_FOLDERS:
        vals = {'name': name, 'is_root_directory': True, 'storage_id': storage.id}
        if full_access:
            vals['group_ids'] = [Command.set(full_access.ids)]
        _get_or_create(env, xid, 'dms.directory', vals)
    File = env['dms.file']
    for xid, folder, name, cat, tags, expiry, title, lines in DMS_FILES:
        if _ref(env, xid):
            continue
        vals = {
            'name': name, 'directory_id': _ref(env, folder).id, 'content': _pdf_b64(title, lines),
            'tag_ids': [Command.set([_ref(env, t).id for t in tags])],
        }
        if 'category_id' in File._fields:
            vals['category_id'] = _ref(env, cat).id
        if expiry is not None and 'expiry_date' in File._fields:
            vals['expiry_date'] = fields.Date.today() + timedelta(days=expiry)
        if 'mimetype' in File._fields:
            vals['mimetype'] = 'application/pdf'
        _get_or_create(env, xid, 'dms.file', vals)


# --------------------------------------------------------------------------- Live Chat
CANNED = [
    ('rc_chat_canned_allergen', 'allergen', 'Every dish on our menu lists its allergens. Tell us what to avoid (nuts, gluten, dairy, '
     'shellfish) and the chef will confirm a safe option before you order.'),
    ('rc_chat_canned_delivery', 'delivery', 'We deliver within 6 km of Marine Drive (Kadavanthra, Panampilly Nagar, MG Road, Fort Kochi) '
     'from 11:30 AM to 10:30 PM. Free delivery above Rs 499.'),
    ('rc_chat_canned_timings', 'timings', 'We are open every day 7:30 AM to 11:00 PM. Breakfast till 11 AM, lunch 12-3:30 PM, dinner from 7 PM.'),
    ('rc_chat_canned_booking', 'booking', 'You can reserve a table at restocafe.example/appointment. Choose date, time and party size; '
     'groups above 12 get the Party Hall.'),
    ('rc_chat_canned_refund', 'refund', 'Sorry about that! Please share your order number. Refunds go back to the original payment method '
     'within 5-7 working days.'),
]
# xid, visitor name, country code, days ago, hour, [(who, text)], rating (or None), feedback
CHATS = [
    ('rc_chat_conv_1', 'Visitor - Aditi', 'IN', 1, 12, [
        ('v', 'Hi! Does the paneer butter masala contain nuts?'),
        ('a', 'Hello Aditi! Yes, the gravy has cashew paste. The Kadai Paneer is nut-free if you prefer.'),
        ('v', 'Great, I will order the Kadai Paneer then. Thanks!'),
        ('a', 'Enjoy your meal! I have added a note for the kitchen as well.')], 5, 'Very quick answer, thank you'),
    ('rc_chat_conv_2', 'Visitor - Rohan', 'IN', 3, 19, [
        ('v', 'Do you deliver to Kakkanad?'),
        ('a', 'Sorry Rohan, Kakkanad is outside our 6 km delivery area. You can pre-order for pickup at Marine Drive.'),
        ('v', 'Okay, I will pick it up. Is parking available?'),
        ('a', 'Yes, we have 12 parking spaces next to the cafe.')], 4, 'Helpful, wish delivery covered Kakkanad'),
    ('rc_chat_conv_3', 'Visitor - Fathima', 'IN', 5, 15, [
        ('v', 'I want to book the Party Hall for 60 people next month for a birthday.'),
        ('a', 'Lovely! The Birthday Party Package covers buffet, cake and decoration. Shall I ask our events team to call you?'),
        ('v', 'Yes please, my number is +91 98470 55210.'),
        ('a', 'Done. Arjun from our Catering & Events team will call you today before 6 PM.')], 5, 'Super helpful'),
    ('rc_chat_conv_4', 'Visitor - George', 'AE', 8, 21, [
        ('v', 'My online order is 30 minutes late. Order WEB/0187.'),
        ('a', 'Really sorry George. The rider is 5 minutes away; I have added a free dessert and a 15% coupon to your account.'),
        ('v', 'Thanks for sorting it out.')], 3, 'Late delivery but good recovery'),
    ('rc_chat_conv_5', 'Visitor - Meenakshi', 'IN', 11, 10, [
        ('v', 'Is the Onam Sadya available on all three days?'),
        ('a', 'Yes, on Uthradam, Thiruvonam and Avittam from 11:30 AM. Pre-booking is recommended.'),
        ('v', 'Booked for 4 on Thiruvonam!')], None, ''),
]


def _livechat(env):
    if 'im_livechat.channel' not in env:
        return
    admin, arjun = _users(env)
    lc = env['im_livechat.channel'].search([('name', '=', 'Resto-Help')], limit=1) or env['im_livechat.channel'].search([], limit=1)
    if not lc:
        return
    lc.sudo().write({'user_ids': [Command.link(admin.id), Command.link(arjun.id)]})
    if 'mail.canned.response' in env:
        for xid, source, text in CANNED:
            _get_or_create(env, xid, 'mail.canned.response', {'source': source, 'substitution': text})
    Channel = env['discuss.channel'].sudo().with_context(**QUIET)
    for i, (xid, visitor, country, days, hour, lines, rating, feedback) in enumerate(CHATS):
        if _ref(env, xid):
            continue
        operator = arjun if i % 2 else admin
        guest = env['mail.guest'].sudo().create({'name': visitor, 'country_id': env.ref(f'base.{country.lower()}').id})
        start = _ist(-days, hour)
        vals = {
            'name': f'{visitor} {operator.name}', 'channel_type': 'livechat', 'livechat_channel_id': lc.id,
            'channel_member_ids': [
                Command.create({'partner_id': operator.partner_id.id, 'livechat_member_type': 'agent'}),
                Command.create({'guest_id': guest.id, 'livechat_member_type': 'visitor'}),
            ],
        }
        if 'country_id' in Channel._fields:
            vals['country_id'] = env.ref(f'base.{country.lower()}').id
        channel = _bind(env, xid, Channel.create(vals))
        for n, (who, text) in enumerate(lines):
            _message(env, channel, f'<p>{text}</p>', start + timedelta(minutes=2 * n),
                     author=operator if who == 'a' else None, guest=guest if who == 'v' else None)
        if 'livechat_end_dt' in Channel._fields:
            channel.livechat_end_dt = start + timedelta(minutes=2 * len(lines) + 3)
        if rating:
            env['rating.rating'].sudo().create({
                'res_model_id': env['ir.model']._get_id('discuss.channel'), 'res_id': channel.id,
                'rating': rating, 'feedback': feedback, 'consumed': True, 'rated_partner_id': operator.partner_id.id,
            })


# --------------------------------------------------------------------------- Discuss
CHANNELS = [  # xid, name, description, [(days ago, hour, author 'admin'|'arjun', text)]
    ('rc_disc_kitchen', 'kitchen', 'Hot kitchen, cold kitchen and bakery: prep lists, 86 items, temperature logs', [
        (2, 9, 'admin', 'Today 86: Karimeen Pollichathu (fish didn\'t meet temperature check). Push the Seer Fish Fry instead.'),
        (1, 8, 'arjun', 'Prep list for the BlueWave Onam lunch is pinned. 250 covers, Sadya leaves arrive at 9:30.'),
        (0, 8, 'admin', 'Walk-in chiller at 3.8 C, freezer at -19 C. All good for the morning check.')]),
    ('rc_disc_service', 'service-floor', 'Floor team: sections, reservations and guest feedback', [
        (2, 11, 'arjun', 'Saturday dinner: 46 reservations. Party Hall booked 7-10 PM (Priya, birthday, 40 guests).'),
        (1, 12, 'admin', 'Reminder: offer the Dessert of the Day with every main course. Upsell challenge is live!'),
        (0, 11, 'arjun', 'Table 7 asked for a Jain menu, please brief the kitchen before you send the order.')]),
    ('rc_disc_bar', 'bar-cafe', 'Coffee bar and mocktails', [
        (3, 10, 'admin', 'New beans from Wayanad Highland Estates: dial in at 18 g in / 36 g out, 27 seconds.'),
        (1, 16, 'arjun', 'Happy hour 4-6 PM: 20% off cold brew and mocktails on the POS (pricelist is set).')]),
    ('rc_disc_delivery', 'delivery', 'Riders and dispatch', [
        (2, 13, 'admin', 'Ather KL-07-DE-2214 battery swap done. Please charge scooters at the back lane socket only.'),
        (0, 12, 'arjun', 'Rain alert for the evening. Use the insulated bags and add 10 minutes to delivery estimates.')]),
    ('rc_disc_management', 'management', 'Owners and managers', [
        (4, 18, 'admin', 'October sales up 14% on September. Catering is now 31% of revenue.'),
        (2, 17, 'arjun', 'Marina Bay wedding quotation (450 guests) sent. Tasting planned for next week.'),
        (0, 10, 'admin', 'Trade licence renewal is due in 3 weeks, the document is in DMS > Licences & Compliance.')]),
    ('rc_disc_outlet', 'marine-drive-outlet', 'Everyone at the Marine Drive outlet', [
        (3, 9, 'admin', 'Welcome to our new baristas Sneha and Kevin!'),
        (1, 9, 'admin', 'Shift swap approved: Rahul takes Thursday evening, Vishnu takes Friday morning.'),
        (0, 9, 'arjun', 'FSSAI inspection expected this month. Keep the temperature logs and labels up to date.')]),
]


def _discuss(env):
    admin, arjun = _users(env)
    who = {'admin': admin, 'arjun': arjun}
    Channel = env['discuss.channel'].sudo().with_context(**QUIET)
    for xid, name, description, posts in CHANNELS:
        if _ref(env, xid):
            continue
        members = (admin | arjun).partner_id
        channel = _bind(env, xid, Channel.create({
            'name': name, 'channel_type': 'channel', 'description': description,
            'channel_member_ids': [Command.create({'partner_id': p.id}) for p in members],
        }))
        for days, hour, author, text in posts:
            _message(env, channel, f'<p>{text}</p>', _ist(-days, hour), author=who[author])


# --------------------------------------------------------------------------- Calendar
EVENTS = [  # xid, name, days, hour, duration h, category, partner xid, location, description
    ('rc_cal_tasting_marina', 'Menu tasting - Marina Bay wedding (450 pax)', 4, 15, 1.5, 'Tasting', 'rc_partner_marina_events',
     'Resto Cafe - Party Hall', 'Tasting of the wedding buffet with Anjali Thomas: 6 mains, 3 desserts, live appam counter.'),
    ('rc_cal_tasting_grand', 'Menu tasting - Grand Residency overflow catering', 9, 16, 1.0, 'Tasting', 'rc_partner_grand_residency',
     'Resto Cafe - Marine Drive', 'Banquet overflow menu, veg and non-veg options.'),
    ('rc_cal_tasting_film', 'Cocktail dinner tasting - Kochi Film Society', 13, 18, 1.5, 'Tasting', 'rc_partner_film_society',
     'Resto Cafe - Rooftop', 'Finger food and BBQ station for the festival opening night.'),
    ('rc_cal_supplier_vypeen', 'Supplier visit - Vypeen Harbour Fresh Catch', 2, 7, 1.0, 'Supplier', None,
     'Vypeen Harbour', 'Quarterly price review and cold-chain check at the harbour.'),
    ('rc_cal_supplier_wayanad', 'Coffee cupping - Wayanad Highland Estates', 11, 10, 2.0, 'Supplier', None,
     'Resto Cafe - Coffee Bar', 'Cupping of the new harvest lots for the house blend.'),
    ('rc_cal_training_safety', 'Staff training - Food Safety & Hygiene (eLearning + practical)', 6, 15, 2.0, 'Training', None,
     'Resto Cafe - Training Room', 'Complete the Food Safety course on eLearning before the session; practical on labelling and temperatures.'),
    ('rc_cal_training_barista', 'Barista workshop - latte art', 16, 9, 2.0, 'Training', None,
     'Resto Cafe - Coffee Bar', 'Hearts, tulips and rosettas. Bring your aprons!'),
    ('rc_cal_fssai', 'FSSAI inspection (expected)', 18, 11, 2.0, 'Compliance', None,
     'Resto Cafe - Marine Drive', 'Keep licence, temperature logs, pest-control reports and medical certificates ready (DMS > Licences & Compliance).'),
    ('rc_cal_owner', 'Monthly owners meeting - November review', 1, 18, 1.5, 'Management', None,
     'Resto Cafe - Office', 'Sales, food cost %, catering pipeline, Central Kitchen expansion.'),
    ('rc_cal_setup_welcome', 'Event set-up - Marina Bay welcome dinner (120 pax)', 12, 15, 3.0, 'Event', 'rc_partner_marina_events',
     'Bolgatty Palace lawn', 'Van loading at 2 PM, buffet set-up, live appam counter, 8 service staff.'),
    ('rc_cal_setup_retreat', 'Event set-up - Harbour Point corporate retreat BBQ', 20, 14, 4.0, 'Event', 'rc_partner_harbour_park',
     'Harbour Point lawns', 'BBQ grill station, 10 service staff, catering van.'),
    ('rc_cal_past_onam', 'BlueWave Onam Sadya (250 pax) - delivered', -9, 11, 4.0, 'Event', 'rc_partner_bluewave',
     'BlueWave Technologies, Infopark', 'Sadya service done, invoice paid.'),
    ('rc_cal_past_tasting', 'Menu tasting - Spice Route tour groups', -12, 15, 1.0, 'Tasting', 'rc_partner_spice_route',
     'Resto Cafe - Marine Drive', 'Sadya tasting for tour operators; order confirmed.'),
    ('rc_cal_past_supplier', 'Supplier visit - Periyar Valley Dairy', -5, 8, 1.0, 'Supplier', None,
     'Aluva', 'Milk quality audit after the cream temperature failure.'),
    ('rc_cal_past_training', 'New joiner induction', -7, 10, 2.0, 'Training', None,
     'Resto Cafe - Training Room', 'Handbook, uniforms, POS and KDS basics.'),
]


def _calendar(env):
    admin, arjun = _users(env)
    Event = env['calendar.event'].sudo().with_context(**QUIET)
    categs = {}
    for name in sorted({e[5] for e in EVENTS}):
        categs[name] = _get_or_create(env, f'rc_cal_type_{name.lower()}', 'calendar.event.type', {'name': name})
    for xid, name, days, hour, dur, categ, partner_xid, location, desc in EVENTS:
        if _ref(env, xid):
            continue
        partner = _ref(env, partner_xid) if partner_xid else None
        attendees = admin.partner_id | (arjun.partner_id if categ in ('Tasting', 'Event', 'Management', 'Training') else env['res.partner'])
        if partner:
            contact = partner.child_ids[:1] or partner
            attendees |= contact
        start = _ist(days, hour)
        vals = {
            'name': name, 'start': start, 'stop': start + timedelta(hours=dur), 'location': location,
            'description': f'<p>{desc}</p>', 'user_id': (arjun if categ in ('Tasting', 'Event') else admin).id,
            'partner_ids': [Command.set(attendees.ids)], 'alarm_ids': [Command.clear()],
            'categ_ids': [Command.set(categs[categ].ids)],
        }
        if partner and 'opportunity_id' in Event._fields:
            lead = env['crm.lead'].search([('partner_id', 'child_of', partner.commercial_partner_id.id)], limit=1) if 'crm.lead' in env else False
            if lead:
                vals['opportunity_id'] = lead.id
        _get_or_create(env, xid, 'calendar.event', vals)


# --------------------------------------------------------------------------- Surveys
RATING_CHOICES = ['Excellent', 'Good', 'Average', 'Poor']
SURVEYS = {
    'rc_srv_dinein': ('Dine-in Feedback', 'Thank you for dining with us at Resto Cafe! It takes 1 minute.', [
        ('food', 'How was the food?', 'choice'), ('service', 'How was the service?', 'choice'),
        ('speed', 'How quickly was your food served?', 'choice'), ('clean', 'How clean were the table and restrooms?', 'choice'),
        ('nps', 'How likely are you to recommend Resto Cafe to a friend?', 'nps'),
        ('comment', 'Anything we could do better?', 'text')]),
    'rc_srv_catering': ('Catering Event Feedback', 'Tell us how your event went. Your feedback goes straight to our events team.', [
        ('food', 'Food quality and taste', 'choice'), ('service', 'Service staff and coordination', 'choice'),
        ('setup', 'Set-up, punctuality and clean-up', 'choice'),
        ('nps', 'How likely are you to book Resto Cafe again?', 'nps'),
        ('comment', 'Comments for our events team', 'text')]),
}
# answers: (choice indexes for each choice question in order, nps, comment)
DINEIN_ANSWERS = [
    ((0, 0, 1, 0), 10, 'Fish curry was outstanding.'), ((0, 1, 1, 0), 9, ''), ((1, 1, 2, 1), 7, 'Waited 25 minutes for mains on Saturday.'),
    ((0, 0, 0, 0), 10, 'Best appam and stew in Kochi!'), ((1, 0, 1, 1), 8, ''), ((2, 1, 2, 1), 6, 'Biryani was a bit dry.'),
    ((0, 0, 1, 0), 9, 'Loved the cold brew.'), ((1, 2, 3, 1), 4, 'Our order was mixed up with another table.'),
    ((0, 1, 0, 0), 10, ''), ((0, 0, 1, 1), 9, 'Kids loved the party box.'), ((1, 1, 1, 0), 8, ''),
    ((0, 0, 0, 1), 10, 'Very friendly staff.'), ((1, 1, 2, 2), 6, 'Restroom needed attention.'), ((0, 0, 1, 0), 9, ''),
]
CATERING_ANSWERS = [
    ('rc_partner_bluewave', (0, 0, 1), 10, 'Sadya was perfect, everyone loved the payasam.'),
    ('rc_partner_spice_route', (0, 1, 0), 9, 'Great value for our tour groups.'),
    ('rc_sale_partner_priya', (0, 0, 0), 10, 'The birthday decoration was beautiful!'),
    ('rc_partner_nest_cowork', (1, 1, 1), 8, 'Pastries are good; coffee could be hotter on delivery.'),
    ('rc_partner_greenleaf', (1, 0, 2), 7, 'Morning delivery was late twice this month.'),
    ('rc_partner_marina_events', (0, 0, 1), 9, 'Smooth welcome dinner, will book the wedding.'),
]


def _surveys(env):
    if 'survey.survey' not in env:
        return
    Survey = env['survey.survey'].sudo().with_context(**QUIET)
    for xid, (title, desc, questions) in SURVEYS.items():
        if _ref(env, xid):
            continue
        survey = _bind(env, xid, Survey.create({
            'title': title, 'description': f'<p>{desc}</p>', 'survey_type': 'survey', 'access_mode': 'public',
            'questions_layout': 'one_page', 'users_login_required': False,
        }))
        for seq, (key, qtitle, kind) in enumerate(questions, start=1):
            vals = {'title': qtitle, 'survey_id': survey.id, 'sequence': seq, 'constr_mandatory': kind != 'text'}
            if kind == 'choice':
                vals.update({'question_type': 'simple_choice', 'suggested_answer_ids': [
                    Command.create({'value': v, 'sequence': i}) for i, v in enumerate(RATING_CHOICES)]})
            elif kind == 'nps':
                vals.update({'question_type': 'scale', 'scale_min': 0, 'scale_max': 10,
                             'scale_min_label': 'Not likely', 'scale_max_label': 'Very likely'})
            else:
                vals.update({'question_type': 'text_box'})
            q = env['survey.question'].sudo().create(vals)
            _bind(env, f'{xid}_q_{key}', q)
    _survey_answers(env, 'rc_srv_dinein', [(None, a, n, c) for a, n, c in DINEIN_ANSWERS], 30)
    _survey_answers(env, 'rc_srv_catering', CATERING_ANSWERS, 25)


def _survey_answers(env, survey_xid, answers, span_days):
    survey = _ref(env, survey_xid)
    if not survey:
        return
    questions = survey.question_ids.sorted('sequence')
    choice_qs = questions.filtered(lambda q: q.question_type == 'simple_choice')
    nps_q = questions.filtered(lambda q: q.question_type == 'scale')[:1]
    text_q = questions.filtered(lambda q: q.question_type == 'text_box')[:1]
    walkins = ['Ammu K', 'Rahul S', 'Deepa M', 'Joseph V', 'Nisha P', 'Arif K', 'Lakshmi R', 'Tom J', 'Sana F', 'Vivek N',
               'Mariam A', 'Hari P', 'Teena J', 'Gokul R']
    for i, (partner_xid, choices, nps, comment) in enumerate(answers):
        xid = f'{survey_xid}_resp_{i + 1}'
        if _ref(env, xid):
            continue
        start = _ist(-(span_days - i * span_days // max(len(answers), 1)), 13 + i % 8, 10)
        vals = {'survey_id': survey.id, 'state': 'done', 'start_datetime': start, 'end_datetime': start + timedelta(minutes=2)}
        partner = _ref(env, partner_xid) if partner_xid else None
        if partner:
            vals['partner_id'] = partner.id
        else:
            name = walkins[i % len(walkins)]
            vals.update({'nickname': name, 'email': f"{name.split()[0].lower()}{i}@example.com"})
        lines = []
        for q, idx in zip(choice_qs, choices):
            lines.append(Command.create({'question_id': q.id, 'answer_type': 'suggestion',
                                         'suggested_answer_id': q.suggested_answer_ids.sorted('sequence')[idx].id}))
        if nps_q:
            lines.append(Command.create({'question_id': nps_q.id, 'answer_type': 'scale', 'value_scale': nps}))
        if text_q:
            if comment:
                lines.append(Command.create({'question_id': text_q.id, 'answer_type': 'text_box', 'value_text_box': comment}))
            else:
                lines.append(Command.create({'question_id': text_q.id, 'skipped': True}))
        vals['user_input_line_ids'] = lines
        _get_or_create(env, xid, 'survey.user_input', vals)


# --------------------------------------------------------------------------- Gamification
BADGES = [  # xid, name, level, description
    ('rc_gam_badge_upsell', 'Upsell Star', 'gold', 'Top dessert and beverage seller of the week.'),
    ('rc_gam_badge_guest', 'Guest Favourite', 'silver', 'Named by guests in 5-star reviews and survey comments.'),
    ('rc_gam_badge_hygiene', 'Hygiene Hero', 'bronze', 'Perfect cleaning checklist and temperature logs for a whole month.'),
]
DEFINITIONS = [  # xid, name, suffix, condition, description
    ('rc_gam_def_desserts', 'Desserts sold', 'desserts', 'higher', 'Number of desserts added to dine-in orders.'),
    ('rc_gam_def_rating', 'Average guest rating', 'stars', 'higher', 'Average rating from dine-in feedback and live chat.'),
    ('rc_gam_def_waste', 'Food waste', 'kg', 'lower', 'Kitchen food waste logged on the wastage sheet.'),
]
CHALLENGES = [  # xid, name, period, days start, days end, definition, target, reward, {user: current}
    ('rc_gam_ch_dessert', 'Dessert Upsell Week', 'weekly', -3, 4, 'rc_gam_def_desserts', 60, 'rc_gam_badge_upsell',
     {'admin': 41, 'arjun': 63}, 'Offer the Dessert of the Day with every main course. Winner gets the Upsell Star badge.'),
    ('rc_gam_ch_service', '5-Star Service Month', 'monthly', -14, 16, 'rc_gam_def_rating', 4.7, 'rc_gam_badge_guest',
     {'admin': 4.6, 'arjun': 4.8}, 'Keep the average guest rating at 4.7 stars or more for the whole month.'),
    ('rc_gam_ch_waste', 'Zero Wastage Kitchen', 'monthly', -14, 16, 'rc_gam_def_waste', 25, 'rc_gam_badge_hygiene',
     {'admin': 18.5, 'arjun': 27.0}, 'Keep monthly food waste under 25 kg: smaller batches, FIFO and staff meals from surplus.'),
]


def _gamification(env):
    if 'gamification.challenge' not in env:
        return
    admin, arjun = _users(env)
    who = {'admin': admin, 'arjun': arjun}
    for xid, name, level, desc in BADGES:
        _get_or_create(env, xid, 'gamification.badge', {'name': name, 'level': level, 'description': desc, 'rule_auth': 'everyone'})
    for xid, name, suffix, condition, desc in DEFINITIONS:
        _get_or_create(env, xid, 'gamification.goal.definition', {
            'name': name, 'computation_mode': 'manually', 'display_mode': 'progress', 'suffix': suffix,
            'condition': condition, 'description': desc})
    Challenge = env['gamification.challenge'].sudo().with_context(**QUIET)
    for xid, name, period, d0, d1, dxid, target, badge, currents, desc in CHALLENGES:
        if _ref(env, xid):
            continue
        challenge = _bind(env, xid, Challenge.create({
            'name': name, 'description': desc, 'period': 'once', 'visibility_mode': 'ranking',
            'report_message_frequency': 'never', 'state': 'draft',
            'start_date': fields.Date.today() + timedelta(days=d0), 'end_date': fields.Date.today() + timedelta(days=d1),
            'user_ids': [Command.set((admin | arjun).ids)], 'reward_id': _ref(env, badge).id,
            'line_ids': [Command.create({'definition_id': _ref(env, dxid).id, 'target_goal': target})],
        }))
        challenge.write({'state': 'inprogress'})
        for goal in env['gamification.goal'].sudo().search([('challenge_id', '=', challenge.id)]):
            for key, user in who.items():
                if goal.user_id == user:
                    goal.with_context(**QUIET).write({'current': currents[key]})
    # badges already earned
    grants = [('rc_gam_grant_1', 'rc_gam_badge_upsell', 'arjun', 'Sold 71 desserts in the Christmas week!'),
              ('rc_gam_grant_2', 'rc_gam_badge_guest', 'admin', 'Mentioned in 6 five-star reviews this month.'),
              ('rc_gam_grant_3', 'rc_gam_badge_hygiene', 'arjun', 'Perfect October cleaning logs.'),
              ('rc_gam_grant_4', 'rc_gam_badge_guest', 'arjun', 'Fathima\'s birthday party feedback: "Arjun made it special".')]
    for xid, badge, user, comment in grants:
        _get_or_create(env, xid, 'gamification.badge.user', {
            'badge_id': _ref(env, badge).id, 'user_id': who[user].id, 'sender_id': admin.id, 'comment': comment})


# --------------------------------------------------------------------------- entry point
def load_collaboration_suite_demo_data(env):
    for name, step in (('documents', _documents), ('livechat', _livechat), ('discuss', _discuss),
                       ('calendar', _calendar), ('surveys', _surveys), ('gamification', _gamification)):
        try:
            with env.cr.savepoint():
                step(env)
                env.flush_all()
        except Exception as e:
            _logger.exception("Hudson POS: collaboration demo step '%s' failed: %s", name, e)
    _logger.info("Hudson POS: Resto Cafe collaboration demo data loaded.")
