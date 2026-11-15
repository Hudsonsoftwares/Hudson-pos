# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Sales demo data (catering, banquets & corporate food supply).

Creates, idempotently (every record is bound to an xmlid of this module):
  * Catering & Events products (buffets per guest, live counters, staff, hall, decoration...),
    a lunch-box product with variants entered through the product grid, optional products
    and a downloadable banquet menu card (product document)
  * Quotation templates (wedding, corporate lunch, birthday, Onam Sadya, outdoor BBQ) with sections,
    notes, optional products, online signature and prepayment; plus a reusable section template
  * Quotation headers & footers (branded PDF cover, kitchen promise page, terms & payment page)
  * 14 quotations / sales orders linked to the Resto Cafe CRM customers and opportunities:
    draft, sent, expired, cancelled, confirmed, delivered, down payment, invoiced and paid
  * Promotions usable in Sales (automatic bulk discount, promo code, coupons, free product)
  * Corporate Catering pricelist and a catering-van delivery method
  * Follow-up activities and chatter notes on the quotations
"""
import base64
import io
import logging
from datetime import timedelta

from odoo import Command, fields
from odoo.tools import file_open
from odoo.tools.binary import BinaryBytes

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
GOLD = (0.788, 0.631, 0.365)
INK = (0.082, 0.067, 0.055)
CREAM = (0.992, 0.980, 0.961)


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
    return _bind(env, xid, env[model].sudo().create(vals))


def _image(path):
    try:
        with file_open(path, 'rb') as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return False


def _ago(days, hour=11):
    return fields.Datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days)


# --------------------------------------------------------------------------- branded PDFs
def _pdf(pages):
    """pages: list of dicts(title, kicker, lines[list of str], dark=bool). Returns the PDF as BinaryBytes."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    for page in pages:
        dark = page.get('dark')
        c.setFillColorRGB(*(INK if dark else CREAM))
        c.rect(0, 0, w, h, fill=1, stroke=0)
        # gold frame + band
        c.setStrokeColorRGB(*GOLD)
        c.setLineWidth(1.2)
        c.rect(28, 28, w - 56, h - 56, fill=0, stroke=1)
        c.setFillColorRGB(*GOLD)
        c.rect(28, h - 150, w - 56, 4, fill=1, stroke=0)
        c.setFont('Helvetica-Bold', 10)
        c.drawString(60, h - 90, page.get('kicker', 'RESTO CAFE SOLUTIONS').upper())
        c.setFillColorRGB(*((1, 1, 1) if dark else INK))
        c.setFont('Times-Bold', 30 if len(page['title']) < 30 else 24)
        c.drawString(60, h - 130, page['title'])
        y = h - 200
        for line in page.get('lines', []):
            if line.startswith('# '):
                y -= 10
                c.setFillColorRGB(*GOLD)
                c.setFont('Helvetica-Bold', 13)
                c.drawString(60, y, line[2:])
                y -= 24
                continue
            c.setFillColorRGB(*((0.92, 0.89, 0.84) if dark else (0.25, 0.22, 0.2)))
            c.setFont('Helvetica', 11.5)
            c.drawString(60, y, line)
            y -= 19
        c.setFillColorRGB(*GOLD)
        c.setFont('Helvetica', 9)
        c.drawString(60, 50, 'Resto Cafe Solutions  |  Marine Drive, Kochi, Kerala  |  +91 484 400 1234  |  events@restocafe.example')
        c.showPage()
    c.save()
    return BinaryBytes(buf.getvalue())


HEADER_COVER = [
    {'dark': True, 'kicker': 'Catering & Events Proposal', 'title': 'Food that makes the occasion', 'lines': [
        'Thank you for considering Resto Cafe Solutions for your event.',
        '',
        'Over the next pages you will find a menu and price proposal prepared',
        'specially for you by our events team and head chef.',
        '',
        '# What every booking includes',
        '-  A dedicated event coordinator from enquiry to clean-up',
        '-  Free menu tasting for weddings and events above 200 guests',
        '-  FSSAI-certified kitchen, uniformed and trained service staff',
        '-  Crockery, chafing dishes, buffet linen and live-counter setup',
        '',
        '# Our numbers',
        '-  1,200+ events catered across Kochi since 2014',
        '-  4.8 / 5 average rating from wedding and corporate clients',
    ]},
]
HEADER_KITCHEN = [
    {'kicker': 'Our Kitchen Promise', 'title': 'Fresh, safe and made to order', 'lines': [
        '# Sourcing',
        '-  Fish from Vypeen and Fort Kochi harbours every morning',
        '-  Spices from our partner farms in Idukki and Wayanad',
        '-  Cold-pressed coconut oil, no reused frying oil, ever',
        '',
        '# Food safety',
        '-  Every food handler holds our Food Safety & Hygiene certificate',
        '-  Temperature-logged transport in our insulated catering vans',
        '-  Hot food served above 63 C, desserts and salads below 5 C',
        '',
        '# Dietary care',
        '-  Separate preparation for Jain, vegan and gluten-free guests',
        '-  Allergen labels on every buffet dish',
    ]},
]
FOOTER_TERMS = [
    {'kicker': 'Terms, Payment & Contact', 'title': 'Booking terms', 'lines': [
        '# Confirmation',
        '-  Sign this quotation online to block your date.',
        '-  A 30% advance confirms weddings and events; balance 3 days before.',
        '-  Final guest count is due 72 hours before the event (minimum 90% billed).',
        '',
        '# Cancellation',
        '-  More than 30 days before: full refund of the advance.',
        '-  8 to 30 days before: 50% of the advance is retained.',
        '-  Less than 7 days before: the advance is non-refundable.',
        '',
        '# Pay by bank transfer',
        '-  Resto Cafe Solutions  |  Federal Bank, Marine Drive branch',
        '-  Use the quotation number as the payment reference.',
        '',
        '# Talk to us',
        '-  Events desk: +91 484 400 1234  |  events@restocafe.example',
    ]},
]
MENU_CARD = [
    {'kicker': 'Banquet Menu Card', 'title': 'Non-Veg Banquet Buffet', 'lines': [
        '# Welcome', '-  Tender coconut mojito, banana chips, chicken 65',
        '# Mains', '-  Malabar chicken biryani, Kerala fish curry, beef ularthiyathu',
        '-  Appam, Kerala parotta, ghee rice, vegetable stew, avial, thoran',
        '# Desserts', '-  Ada pradhaman, gulab jamun, seasonal fruit platter',
        '', 'Minimum order 50 guests. Menu can be customised with your event coordinator.',
    ]},
]


# --------------------------------------------------------------------------- master data
CATERING_PRODUCTS = [
    # xid, name, type, price, cost, description, image
    ('rc_sp_sadya', 'Kerala Sadya Meal (per guest)', 'consu', 450, 210, '24-dish traditional Sadya served on banana leaf, with 2 payasams.', 'theme_bistro/static/src/img/backgrounds/15.webp'),
    ('rc_sp_veg_buffet', 'Veg Banquet Buffet (per guest)', 'consu', 650, 290, 'Welcome drink, 2 starters, 6 mains, breads, rice and 2 desserts.', 'theme_bistro/static/src/img/backgrounds/09.webp'),
    ('rc_sp_nonveg_buffet', 'Non-Veg Banquet Buffet (per guest)', 'consu', 850, 380, 'Chicken 65, Malabar biryani, fish curry, beef ularthiyathu, appam and desserts.', 'theme_bistro/static/src/img/backgrounds/03.webp'),
    ('rc_sp_premium_buffet', 'Premium Malabar Buffet (per guest)', 'consu', 1200, 540, 'Seafood grill, mutton biryani, karimeen pollichathu and a dessert bar.', 'theme_bistro/static/src/img/backgrounds/05.webp'),
    ('rc_sp_snack_box', 'Tea-time Snack Box', 'consu', 120, 48, 'Pazham pori, cutlet, cake slice and a cookie, packed for events and schools.', 'theme_bistro/static/src/img/content/media_list_01.webp'),
    ('rc_sp_kids_box', "Kids' Party Meal Box", 'consu', 250, 105, 'Mini burger, fries, juice and a cupcake.', 'theme_bistro/static/src/img/content/media_list_02.webp'),
    ('rc_sp_mocktail', 'Welcome Mocktail (per glass)', 'consu', 90, 28, 'Tender coconut mojito or passion fruit cooler.', 'theme_bistro/static/src/img/content/s_image_hexagonal_1.webp'),
    ('rc_sp_cake', 'Celebration Cake (per kg)', 'consu', 1100, 420, 'Chocolate truffle, red velvet or plum cake with custom message.', 'theme_bistro/static/src/img/backgrounds/11.webp'),
    ('rc_sp_coffee_station', 'Coffee & Pastry Station (per guest)', 'consu', 150, 55, 'Filter coffee, cardamom tea and assorted pastries, refilled through the event.', 'theme_bistro/static/src/img/backgrounds/06.webp'),
    ('rc_sp_pastry_tray', 'Pastry Supply Tray (24 pcs)', 'consu', 1800, 760, 'Croissants, puffs and muffins delivered fresh every morning.', 'theme_bistro/static/src/img/backgrounds/13.webp'),
    ('rc_sp_live_dosa', 'Live Dosa Counter (per event)', 'service', 6000, 2400, 'Chef-manned counter: ghee roast, masala and podi dosa with 3 chutneys.', None),
    ('rc_sp_live_appam', 'Live Appam & Stew Counter (per event)', 'service', 7500, 3000, 'Fresh appams with chicken or vegetable stew.', None),
    ('rc_sp_bbq', 'BBQ Grill Station (per event)', 'service', 9000, 3800, 'Charcoal grill with chef: chicken, fish and paneer tikka.', None),
    ('rc_sp_staff', 'Service Staff (per waiter, 6-hour shift)', 'service', 1200, 700, 'Uniformed, trained service staff.', None),
    ('rc_sp_hall', 'Banquet Hall Rental (4 hours)', 'service', 25000, 6000, 'Air-conditioned Party Hall for up to 150 guests, sound system included.', None),
    ('rc_sp_decor', 'Theme Decoration Package', 'service', 15000, 7000, 'Floral stage, entrance arch, table centrepieces and fairy lights.', None),
    ('rc_sp_setup', 'Delivery & Setup Charge', 'service', 1500, 600, 'Transport, buffet setup and clean-up at your venue.', None),
    ('rc_sp_coordinator', 'Event Coordinator', 'service', 5000, 2500, 'A dedicated coordinator on the day of the event.', None),
]
OPTIONAL_PRODUCTS = {
    'rc_sp_nonveg_buffet': ['rc_sp_mocktail', 'rc_sp_cake', 'rc_sp_live_dosa', 'rc_sp_decor'],
    'rc_sp_veg_buffet': ['rc_sp_mocktail', 'rc_sp_live_dosa', 'rc_sp_live_appam'],
    'rc_sp_premium_buffet': ['rc_sp_mocktail', 'rc_sp_live_appam', 'rc_sp_bbq', 'rc_sp_decor'],
    'rc_sp_sadya': ['rc_sp_staff', 'rc_sp_setup'],
}


def _enable_features(env):
    """Same as ticking the Sales settings: discounts, variants, pricelists, quotation templates."""
    user_group = env.ref('base.group_user')
    for xid in ('sale.group_discount_per_so_line', 'product.group_product_variant',
                'product.group_product_pricelist', 'sale_management.group_sale_order_template'):
        group = env.ref(xid, raise_if_not_found=False)
        if group and group not in user_group.implied_ids:
            user_group.sudo().write({'implied_ids': [Command.link(group.id)]})
    env.company.sudo().write({'portal_confirmation_sign': True, 'portal_confirmation_pay': True,
                              'prepayment_percent': 0.3})


def _products(env):
    categ = _get_or_create(env, 'rc_sale_categ_catering', 'product.category', {'name': 'Catering & Events'})
    tax = env.company.account_sale_tax_id
    res = {}
    for xid, name, ptype, price, cost, desc, img in CATERING_PRODUCTS:
        vals = {
            'name': name, 'type': ptype, 'list_price': price, 'standard_price': cost, 'categ_id': categ.id,
            'sale_ok': True, 'purchase_ok': False, 'invoice_policy': 'order', 'description_sale': desc,
            'available_in_pos': False, 'taxes_id': [Command.set(tax.ids)],
        }
        if ptype == 'service' and 'service_tracking' in env['product.template']._fields:
            vals['service_tracking'] = 'no'
        if img:
            vals['image_1920'] = _image(img)
        res[xid] = _get_or_create(env, xid, 'product.template', vals)
    for xid, opts in OPTIONAL_PRODUCTS.items():
        res[xid].optional_product_ids = [Command.set([res[o].id for o in opts])]

    # lunch box with variants, entered through the product grid (matrix)
    attr = env['product.attribute'].sudo().search([('name', '=', 'Lunch Menu')], limit=1) or _get_or_create(
        env, 'rc_sale_attr_menu', 'product.attribute', {'name': 'Lunch Menu', 'create_variant': 'always', 'display_type': 'pills'})
    values = {}
    for xid, name, seq in (('rc_sale_attr_veg', 'Veg', 1), ('rc_sale_attr_chicken', 'Chicken', 2), ('rc_sale_attr_fish', 'Fish', 3)):
        values[name] = attr.value_ids.filtered(lambda v: v.name == name)[:1] or _get_or_create(
            env, xid, 'product.attribute.value', {'name': name, 'attribute_id': attr.id, 'sequence': seq})
    if not _ref(env, 'rc_sp_lunch_box'):
        lunch = _get_or_create(env, 'rc_sp_lunch_box', 'product.template', {
            'name': 'Corporate Lunch Box', 'type': 'consu', 'list_price': 180, 'standard_price': 80, 'categ_id': categ.id,
            'invoice_policy': 'order', 'available_in_pos': False, 'taxes_id': [Command.set(tax.ids)],
            'description_sale': 'Rice, 2 curries, thoran, pickle and a sweet. Delivered by 12:30 PM.',
            'image_1920': _image('theme_bistro/static/src/img/backgrounds/17.webp'),
            'product_add_mode': 'matrix',
            'attribute_line_ids': [Command.create({'attribute_id': attr.id, 'value_ids': [Command.set([v.id for v in values.values()])]})],
        })
        for ptav in lunch.attribute_line_ids.product_template_value_ids:
            ptav.price_extra = {'Chicken': 40, 'Fish': 60}.get(ptav.name, 0)
    res['rc_sp_lunch_box'] = _ref(env, 'rc_sp_lunch_box')

    # downloadable menu card attached to the buffet (Product Documents on the quotation)
    if 'product.document' in env and not _ref(env, 'rc_sale_doc_menu_card'):
        doc = env['product.document'].sudo().with_context(disable_product_documents_creation=True).create({
            'name': 'Non-Veg Banquet Menu Card.pdf', 'raw': _pdf(MENU_CARD), 'mimetype': 'application/pdf',
            'res_model': 'product.template', 'res_id': res['rc_sp_nonveg_buffet'].id, 'attached_on_sale': 'quotation',
        })
        _bind(env, 'rc_sale_doc_menu_card', doc)
    return res


def _quotation_documents(env):
    if 'quotation.document' not in env:
        return {}
    docs = {}
    for xid, name, dtype, pages, default, seq in (
        ('rc_sale_qdoc_cover', 'Resto Cafe Proposal Cover.pdf', 'header', HEADER_COVER, True, 1),
        ('rc_sale_qdoc_kitchen', 'Our Kitchen Promise.pdf', 'header', HEADER_KITCHEN, False, 2),
        ('rc_sale_qdoc_terms', 'Booking Terms and Payment.pdf', 'footer', FOOTER_TERMS, True, 1),
    ):
        if _ref(env, xid):
            docs[xid] = _ref(env, xid)
            continue
        docs[xid] = _get_or_create(env, xid, 'quotation.document', {
            'name': name, 'raw': _pdf(pages), 'mimetype': 'application/pdf',
            'document_type': dtype, 'add_by_default': default, 'sequence': seq,
        })
    return docs



# template: xid, name, days, signature, prepayment, team xid, docs, lines
# line: ('section', name) | ('note', text) | (product xid, qty, optional)
TEMPLATES = [
    ('rc_sale_tmpl_wedding', 'Wedding Reception Package (per 100 guests)', 45, 0.3, 'rc_team_catering_events',
     ['rc_sale_qdoc_cover', 'rc_sale_qdoc_kitchen', 'rc_sale_qdoc_terms'], [
         ('section', 'Menu'),
         ('rc_sp_nonveg_buffet', 100, False), ('rc_sp_mocktail', 100, False),
         ('section', 'Live counters & services'),
         ('rc_sp_live_appam', 1, False), ('rc_sp_staff', 8, False), ('rc_sp_decor', 1, False), ('rc_sp_coordinator', 1, False),
         ('note', 'Free menu tasting for 4 people. Final guest count 72 hours before the event.'),
         ('rc_sp_cake', 5, True), ('rc_sp_live_dosa', 1, True), ('rc_sp_bbq', 1, True),
     ]),
    ('rc_sale_tmpl_corporate', 'Corporate Lunch Plan (monthly, 50 staff)', 30, 0.0, 'rc_team_catering_events',
     ['rc_sale_qdoc_cover', 'rc_sale_qdoc_terms'], [
         ('section', 'Daily lunch boxes (22 working days)'),
         ('rc_sp_lunch_box', 1100, False),
         ('section', 'Delivery'),
         ('rc_sp_setup', 22, False),
         ('note', 'Menu rotates weekly. Orders can be changed until 10 AM the same day.'),
         ('rc_sp_snack_box', 1100, True), ('rc_sp_coffee_station', 50, True),
     ]),
    ('rc_sale_tmpl_birthday', 'Birthday Party Package (40 guests)', 15, 1.0, 'sales_team.team_sales_department',
     ['rc_sale_qdoc_cover', 'rc_sale_qdoc_terms'], [
         ('section', 'Party menu'),
         ('rc_sp_veg_buffet', 25, False), ('rc_sp_kids_box', 15, False), ('rc_sp_cake', 3, False),
         ('section', 'Venue'),
         ('rc_sp_hall', 1, False), ('rc_sp_decor', 1, False),
         ('note', 'Rooftop or Party Hall, 4 hours. Balloon theme of your choice.'),
         ('rc_sp_mocktail', 40, True), ('rc_sp_live_dosa', 1, True),
     ]),
    ('rc_sale_tmpl_sadya', 'Onam Sadya Package (per 100 guests)', 30, 0.3, 'rc_team_catering_events',
     ['rc_sale_qdoc_cover', 'rc_sale_qdoc_kitchen', 'rc_sale_qdoc_terms'], [
         ('section', 'Sadya'),
         ('rc_sp_sadya', 100, False),
         ('section', 'Service'),
         ('rc_sp_staff', 6, False), ('rc_sp_setup', 1, False),
         ('note', 'Served on banana leaf in the traditional order. Pookalam on request.'),
         ('rc_sp_mocktail', 100, True),
     ]),
    ('rc_sale_tmpl_bbq', 'Outdoor BBQ & Retreat Catering', 20, 0.3, 'rc_team_catering_events',
     ['rc_sale_qdoc_cover', 'rc_sale_qdoc_terms'], [
         ('section', 'Food'),
         ('rc_sp_premium_buffet', 100, False), ('rc_sp_bbq', 1, False),
         ('section', 'Logistics'),
         ('rc_sp_staff', 10, False), ('rc_sp_coordinator', 1, False),
         ('rc_sp_coffee_station', 100, True), ('rc_sp_live_appam', 1, True),
     ]),
]


def _templates(env, prods, docs):
    res = {}
    for xid, name, days, prepay, team_xid, doc_xids, lines in TEMPLATES:
        if _ref(env, xid):
            res[xid] = _ref(env, xid)
            continue
        team = env.ref(team_xid if '.' in team_xid else f'{MODULE}.{team_xid}', raise_if_not_found=False)
        line_vals = []
        for seq, line in enumerate(lines, start=1):
            if line[0] == 'section':
                line_vals.append({'display_type': 'line_section', 'name': line[1], 'sequence': seq})
            elif line[0] == 'note':
                line_vals.append({'display_type': 'line_note', 'name': line[1], 'sequence': seq})
            else:
                tmpl = prods[line[0]]
                product = tmpl.product_variant_ids[:1]
                line_vals.append({'product_id': product.id, 'product_uom_qty': line[1], 'is_optional': line[2], 'sequence': seq})
        vals = {
            'name': name, 'number_of_days': days, 'require_signature': True, 'prepayment_percent': prepay,
            'sale_order_template_line_ids': [Command.create(v) for v in line_vals],
            'note': '<p>Prices per guest include GST. Rates valid for events in Kochi city limits.</p>',
        }
        if team:
            vals['team_ids'] = [Command.set(team.ids)]
        if docs:
            vals['quotation_document_ids'] = [Command.set([docs[d].id for d in doc_xids if d in docs])]
        res[xid] = _get_or_create(env, xid, 'sale.order.template', vals)
    # reusable section ("Add section" button on a quotation)
    if 'template_type' in env['sale.order.template']._fields and not _ref(env, 'rc_sale_tmpl_section_live'):
        try:
            with env.cr.savepoint():
                _get_or_create(env, 'rc_sale_tmpl_section_live', 'sale.order.template', {
                    'name': 'Live Counters Add-on', 'template_type': 'section',
                    'sale_order_template_line_ids': [
                        Command.create({'product_id': prods[x].product_variant_ids[:1].id, 'product_uom_qty': 1})
                        for x in ('rc_sp_live_dosa', 'rc_sp_live_appam', 'rc_sp_bbq')],
                })
        except Exception as e:
            _logger.info("Section template skipped: %s", e)
    return res


def _promotions(env, prods):
    if 'loyalty.program' not in env:
        return
    Program = env['loyalty.program'].sudo()
    categ = _ref(env, 'rc_sale_categ_catering')

    def program(xid, vals):
        if _ref(env, xid):
            return _ref(env, xid)
        flags = {k: v for k, v in (('sale_ok', True), ('pos_ok', False), ('ecommerce_ok', False)) if k in Program._fields}
        return _get_or_create(env, xid, 'loyalty.program', {**vals, **flags})

    program('rc_sale_promo_bulk', {
        'name': 'Bulk Catering: 10% off orders above 1,50,000', 'program_type': 'promotion', 'trigger': 'auto', 'applies_on': 'current',
        'rule_ids': [Command.create({'minimum_amount': 150000, 'reward_point_mode': 'order', 'reward_point_amount': 1})],
        'reward_ids': [Command.create({'reward_type': 'discount', 'discount': 10, 'discount_mode': 'percent',
                                       'discount_applicability': 'order', 'discount_max_amount': 25000, 'required_points': 1})],
    })
    program('rc_sale_promo_wedding_code', {
        'name': 'Wedding Season Code WEDDING26 (5% off catering)', 'program_type': 'promo_code', 'trigger': 'with_code', 'applies_on': 'current',
        'rule_ids': [Command.create({'mode': 'with_code', 'code': 'WEDDING26', 'reward_point_mode': 'order', 'reward_point_amount': 1})],
        'reward_ids': [Command.create({'reward_type': 'discount', 'discount': 5, 'discount_mode': 'percent', 'required_points': 1,
                                       'discount_applicability': 'specific', 'discount_product_category_id': categ.id})],
    })
    program('rc_sale_promo_free_cake', {
        'name': 'Free 2 kg Cake with Birthday Buffet (25+ guests)', 'program_type': 'promotion', 'trigger': 'auto', 'applies_on': 'current',
        'rule_ids': [Command.create({'product_ids': [Command.set(prods['rc_sp_veg_buffet'].product_variant_ids.ids)], 'minimum_qty': 25,
                                     'reward_point_mode': 'order', 'reward_point_amount': 1})],
        'reward_ids': [Command.create({'reward_type': 'product', 'reward_product_id': prods['rc_sp_cake'].product_variant_ids[:1].id,
                                       'reward_product_qty': 2, 'required_points': 1})],
    })
    coupons = program('rc_sale_promo_corporate_coupons', {
        'name': 'Corporate Welcome Coupon (2,000 off first order)', 'program_type': 'coupons', 'trigger': 'with_code', 'applies_on': 'current',
        'rule_ids': [Command.create({'reward_point_mode': 'order', 'reward_point_amount': 1})],
        'reward_ids': [Command.create({'reward_type': 'discount', 'discount': 2000, 'discount_mode': 'per_order',
                                       'discount_applicability': 'order', 'required_points': 1})],
    })
    if not coupons.coupon_ids and 'loyalty.generate.wizard' in env:
        try:
            with env.cr.savepoint():
                env['loyalty.generate.wizard'].sudo().with_context(active_id=coupons.id).create(
                    {'program_id': coupons.id, 'coupon_qty': 10, 'points_granted': 1}).generate_coupons()
        except Exception as e:
            _logger.info("Coupon generation skipped: %s", e)


def _pricelist_and_carrier(env):
    categ = _ref(env, 'rc_sale_categ_catering')
    pricelist = _get_or_create(env, 'rc_sale_pricelist_corporate', 'product.pricelist', {
        'name': 'Corporate Catering (5% off)', 'currency_id': env.company.currency_id.id,
        'item_ids': [Command.create({'applied_on': '2_product_category', 'categ_id': categ.id,
                                     'compute_price': 'discount', 'price_discount': 5})],
    })
    for xid in ('rc_partner_harbour_park', 'rc_partner_bluewave', 'rc_partner_greenleaf'):
        partner = _ref(env, xid)
        if partner:
            partner.sudo().property_product_pricelist = pricelist
    carrier = False
    if 'delivery.carrier' in env:
        van = _get_or_create(env, 'rc_sale_prod_van', 'product.product', {
            'name': 'Catering Van Delivery', 'type': 'service', 'list_price': 750, 'sale_ok': False,
            'purchase_ok': False, 'available_in_pos': False, 'categ_id': categ.id})
        carrier = _get_or_create(env, 'rc_sale_carrier_van', 'delivery.carrier', {
            'name': 'Resto Cafe Catering Van (Kochi)', 'delivery_type': 'fixed', 'fixed_price': 750, 'product_id': van.id,
            'free_over': True, 'amount': 200000})
    return pricelist, carrier


# --------------------------------------------------------------------------- quotations & orders
# xid, partner xid, template xid, guests (scales per-guest lines; None = template qty), state, days ago,
# opportunity xid, salesperson ('admin'|'arjun'), client ref, extras
ORDERS = [
    ('rc_so_wedding_marina', 'rc_partner_marina_events', 'rc_sale_tmpl_wedding', 450, 'sent', 6,
     'Wedding Reception Catering & Live Counters (450 pax)', 'arjun', 'MARINA-WED-450', {'activity': 'Call to confirm menu tasting date', 'event_in': 40}),
    ('rc_so_wedding_welcome', 'rc_partner_marina_events', 'rc_sale_tmpl_wedding', 120, 'downpayment', 34,
     'Destination Wedding Welcome Dinner (120 pax)', 'arjun', 'MARINA-WELCOME-120', {'event_in': 12, 'signed': 'Anjali Thomas'}),
    ('rc_so_onam_bluewave', 'rc_partner_bluewave', 'rc_sale_tmpl_sadya', 250, 'paid', 58,
     'IT Park Onam Celebration Sadya (250 pax)', 'admin', 'BW-ONAM-250', {'event_in': -50, 'signed': 'Neha Kurian'}),
    ('rc_so_onam_spice_route', 'rc_partner_spice_route', 'rc_sale_tmpl_sadya', 300, 'delivered', 21,
     'Onam Sadya for Tour Groups (300 guests)', 'arjun', 'SRT-SADYA-300', {'event_in': -14}),
    ('rc_so_corporate_harbour', 'rc_partner_harbour_park', 'rc_sale_tmpl_corporate', None, 'draft', 2,
     'Corporate Daily Lunch Subscription (120 staff)', 'admin', 'HPCP-LUNCH-DEC', {'lunch_mix': {'Veg': 900, 'Chicken': 1000, 'Fish': 740},
                                                                                   'activity': 'Send revised quote with Jain option'}),
    ('rc_so_hotel_overflow', 'rc_partner_grand_residency', 'rc_sale_tmpl_wedding', 200, 'sent', 9,
     'Hotel Banquet Overflow Catering Contract', 'admin', 'GRH-OVERFLOW-Q1', {'discount': 7.5, 'event_in': 25}),
    ('rc_so_school_annual_day', 'rc_partner_st_teresa', None, None, 'sent', 4,
     'Annual Day Lunch & Snack Boxes (600 students)', 'admin', 'STPS-ANNUAL-DAY', {
         'lines': [('rc_sp_kids_box', 600), ('rc_sp_snack_box', 650), ('rc_sp_setup', 2)], 'event_in': 18,
         'activity': 'Principal to approve the quotation'}),
    ('rc_so_film_society', 'rc_partner_film_society', 'rc_sale_tmpl_bbq', 180, 'draft', 1,
     'Film Festival Opening Night Cocktail Dinner', 'arjun', 'KFS-OPENING', {}),
    ('rc_so_greenleaf_bakery', 'rc_partner_greenleaf', None, None, 'invoiced', 40,
     'Hospital Cafeteria Bakery Supply – 12 months', 'admin', 'GLH-BAKERY-M1', {
         'lines': [('rc_sp_pastry_tray', 30), ('rc_sp_coffee_station', 400), ('rc_sp_setup', 30)], 'event_in': -35}),
    ('rc_so_nest_cowork', 'rc_partner_nest_cowork', None, None, 'delivered', 12,
     'Co-working Café Corner – Coffee & Pastry Supply', 'admin', 'NEST-CAFE-NOV', {
         'lines': [('rc_sp_pastry_tray', 20), ('rc_sp_coffee_station', 300)], 'event_in': -8}),
    ('rc_so_birthday_priya', 'rc_sale_partner_priya', 'rc_sale_tmpl_birthday', None, 'paid', 16,
     'Birthday Party Package – Rooftop (40 pax)', 'arjun', 'BDAY-PRIYA', {'event_in': -3, 'signed': 'Priya Raghavan'}),
    ('rc_so_marathon', 'rc_partner_coastal_runners', None, None, 'cancel', 27,
     'Marathon Hydration & Energy Snack Kiosks', 'arjun', 'CRC-MARATHON', {
         'lines': [('rc_sp_snack_box', 800), ('rc_sp_staff', 6)], 'reason': 'Customer moved the run to a sponsor-catered venue.'}),
    ('rc_so_christmas_bluewave', 'rc_partner_bluewave', None, None, 'expired', 50,
     'Christmas Eve Family Feast – Private Dining (25 pax)', 'admin', 'BW-XMAS', {
         'lines': [('rc_sp_premium_buffet', 25), ('rc_sp_cake', 3), ('rc_sp_hall', 1)]}),
    ('rc_so_retreat_bbq', 'rc_partner_harbour_park', 'rc_sale_tmpl_bbq', 200, 'sent', 3,
     'Corporate Retreat Outdoor BBQ (200 pax)', 'arjun', 'HPCP-RETREAT', {'carrier': True, 'event_in': 30}),
]


def _salesperson(env, key):
    return (_ref(env, 'rc_user_arjun') if key == 'arjun' else None) or env.ref('base.user_admin')


def _order_lines_from_template(order, template, guests, prods):
    t_lines = template.sale_order_template_line_ids
    per_guest = t_lines.filtered(lambda l: '(per guest)' in (l.product_id.name or ''))
    base = per_guest[:1].product_uom_qty or 0
    lines = []
    for t_line in t_lines:
        vals = t_line._prepare_order_line_values(order.fiscal_position_id, order.currency_id)
        name = t_line.product_id.name or ''
        if guests and base and ('(per guest)' in name or '(per glass)' in name):
            vals['product_uom_qty'] = round(t_line.product_uom_qty * guests / base)
        elif guests and name.startswith('Service Staff'):
            vals['product_uom_qty'] = max(4, round(guests / 15))
        lines.append(Command.create(vals))
    return lines


def _create_order(env, spec, prods, pricelist, carrier, docs):
    xid, partner_xid, tmpl_xid, guests, state, days, opp_name, sp, ref, extra = spec
    if _ref(env, xid):
        return
    partner = _ref(env, partner_xid)
    if not partner:
        return
    user = _salesperson(env, sp)
    opp = env['crm.lead'].sudo().search([('name', '=', opp_name)], limit=1) if 'crm.lead' in env else False
    team = _ref(env, 'rc_team_catering_events') or env.ref('sales_team.team_sales_department')
    date_order = _ago(days)
    vals = {
        'partner_id': partner.id, 'user_id': user.id, 'team_id': team.id, 'client_order_ref': ref,
        'date_order': date_order, 'origin': opp_name,
        'validity_date': (date_order + timedelta(days=30)).date(),
    }
    if opp:
        vals['opportunity_id'] = opp.id
        if opp.tag_ids:
            vals['tag_ids'] = [Command.set(opp.tag_ids.ids)]
        for f in ('campaign_id', 'medium_id', 'source_id'):
            if opp[f]:
                vals[f] = opp[f].id
    if extra.get('event_in') is not None:
        vals['commitment_date'] = fields.Datetime.now().replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=extra['event_in'])
    order = env['sale.order'].sudo().with_user(user).with_context(mail_create_nosubscribe=True, tracking_disable=True).create(vals)
    order = order.sudo()
    _bind(env, xid, order)

    if tmpl_xid:
        template = _ref(env, tmpl_xid)
        order.write({'sale_order_template_id': template.id, 'require_signature': template.require_signature,
                     'prepayment_percent': template.prepayment_percent or order.prepayment_percent})
        order.write({'order_line': _order_lines_from_template(order, template, guests, prods)})
        if docs and 'quotation_document_ids' in order._fields:
            order.quotation_document_ids = [Command.set(template.quotation_document_ids.filtered('add_by_default').ids)]
    for pxid, qty in extra.get('lines', []):
        order.write({'order_line': [Command.create({'product_id': prods[pxid].product_variant_ids[:1].id, 'product_uom_qty': qty})]})
    if extra.get('lunch_mix'):
        box_lines = order.order_line.filtered(lambda l: l.product_id.product_tmpl_id == prods['rc_sp_lunch_box'])
        variants = prods['rc_sp_lunch_box'].product_variant_ids
        seq = box_lines[:1].sequence
        box_lines.unlink()
        order.write({'order_line': [Command.create({
            'product_id': v.id, 'product_uom_qty': extra['lunch_mix'].get(v.product_template_attribute_value_ids[:1].name, 0), 'sequence': seq})
            for v in variants]})
    if extra.get('discount'):
        order.order_line.filtered(lambda l: l.product_id and not l.is_optional).write({'discount': extra['discount']})
    if extra.get('carrier') and carrier:
        order.set_delivery_line(carrier, carrier.fixed_price)
    if partner_xid in ('rc_partner_harbour_park', 'rc_partner_bluewave', 'rc_partner_greenleaf') and pricelist:
        order.pricelist_id = pricelist
        order._recompute_prices()

    if extra.get('activity'):
        order.activity_schedule('mail.mail_activity_data_call' if 'Call' in extra['activity'] else 'mail.mail_activity_data_todo',
                                date_deadline=fields.Date.today() + timedelta(days=2), summary=extra['activity'], user_id=user.id)

    if state in ('sent',):
        order.action_quotation_sent()
        order.message_post(body=f"Quotation sent to {partner.name} with the proposal cover and booking terms.",
                           message_type='comment', subtype_xmlid='mail.mt_note')
    elif state == 'expired':
        order.action_quotation_sent()
        order.validity_date = (date_order + timedelta(days=15)).date()
    elif state == 'cancel':
        order.action_quotation_sent()
        order._action_cancel()
        order.message_post(body=extra.get('reason', 'Cancelled.'), message_type='comment', subtype_xmlid='mail.mt_note')
    elif state in ('downpayment', 'delivered', 'invoiced', 'paid'):
        if extra.get('signed'):
            order.write({'signed_by': extra['signed'], 'signed_on': date_order + timedelta(days=1)})
        order.with_context(send_email=False).action_confirm()
        order.date_order = date_order + timedelta(days=1)
        if state in ('delivered', 'invoiced', 'paid'):
            _deliver(order)
        if state == 'downpayment':
            _invoice(env, order, date_order + timedelta(days=2), downpayment=30)
        elif state in ('invoiced', 'paid'):
            invoice = _invoice(env, order, date_order + timedelta(days=3))
            if state == 'paid' and invoice:
                _pay(env, invoice, date_order + timedelta(days=8))


def _deliver(order):
    for picking in order.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')):
        try:
            picking.action_assign()
            for move in picking.move_ids:
                move.quantity = move.product_uom_qty
                move.picked = True
            picking.with_context(skip_backorder=True, skip_sms=True, skip_immediate=True).button_validate()
        except Exception as e:
            _logger.info("Delivery of %s skipped: %s", order.name, e)


def _invoice(env, order, date, downpayment=None):
    try:
        if downpayment:
            wizard = env['sale.advance.payment.inv'].sudo().with_context(active_model='sale.order', active_ids=order.ids).create(
                {'advance_payment_method': 'percentage', 'amount': downpayment})
            wizard._create_invoices(order)
            invoice = order.invoice_ids.filtered(lambda m: m.state == 'draft')[:1]
        else:
            invoice = order._create_invoices()
        invoice.write({'invoice_date': date.date() if hasattr(date, 'date') else date})
        invoice.action_post()
        return invoice
    except Exception as e:
        _logger.info("Invoice for %s skipped: %s", order.name, e)
        return False


def _pay(env, invoice, date):
    try:
        env['account.payment.register'].sudo().with_context(active_model='account.move', active_ids=invoice.ids).create(
            {'payment_date': date.date()})._create_payments()
    except Exception as e:
        _logger.info("Payment for %s skipped: %s", invoice.name, e)


# --------------------------------------------------------------------------- entry point
def load_sales_suite_demo_data(env):
    if 'sale.order' not in env:
        _logger.info("Hudson POS: Sales not installed, skipping Sales demo data.")
        return
    steps = [('features', lambda: _enable_features(env))]
    ctx = {}
    steps += [
        ('products', lambda: ctx.update(prods=_products(env))),
        ('quotation documents', lambda: ctx.update(docs=_quotation_documents(env))),
        ('templates', lambda: _templates(env, ctx['prods'], ctx.get('docs', {}))),
        ('pricelist & carrier', lambda: ctx.update(zip(('pricelist', 'carrier'), _pricelist_and_carrier(env)))),
        ('promotions', lambda: _promotions(env, ctx['prods'])),
        ('customer', lambda: _get_or_create(env, 'rc_sale_partner_priya', 'res.partner', {
            'name': 'Priya Raghavan', 'email': 'priya.raghavan@example.com', 'phone': '+91 98470 22110',
            'street': 'Panampilly Nagar', 'city': 'Kochi', 'country_id': env.ref('base.in').id})),
    ]
    for name, step in steps:
        try:
            with env.cr.savepoint():
                step()
        except Exception as e:
            _logger.exception("Hudson POS: Sales demo step '%s' failed: %s", name, e)
            if name in ('products',):
                return
    for spec in ORDERS:
        try:
            with env.cr.savepoint():
                _create_order(env, spec, ctx['prods'], ctx.get('pricelist'), ctx.get('carrier'), ctx.get('docs'))
        except Exception as e:
            _logger.exception("Hudson POS: Sales demo order %s failed: %s", spec[0], e)
    _logger.info("Hudson POS: Resto Cafe Sales demo data loaded.")
