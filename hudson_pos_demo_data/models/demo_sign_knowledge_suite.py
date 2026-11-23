# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Sign templates & Knowledge articles demo data.

Demo data only, through the standard models of the installed apps; idempotent (every record is
bound to an xmlid of this module, prefixes ``rc_sign_`` / ``rc_kb_``).

Sign (``hudson_sign``) - 4 reusable templates listed in Sign > Templates (favourites of the
administrator, shared with every user), each with its own 2-page agreement PDF generated at load
time, several signer roles in signing order (role sequence) and fields placed on the PDF's labelled
lines: Signature, Initials, Name, Date, Text, Checkbox, plus Company / Email / Selection / Multiline:
  * Employee Employment Agreement   - Employee -> HR Manager -> General Manager
  * Vendor Supply Agreement         - Vendor -> Purchase Manager -> Finance Head
  * Customer Catering Agreement     - Customer -> Events Manager
  * Recipe Confidentiality (NDA)    - Employee -> Head Chef

Knowledge (``hudson_knowledge``) - 4 workspace articles with nested sub-articles: Restaurant
Operations, Employee Onboarding, Food Safety & Hygiene, Kitchen SOP. They show headings, bullet /
numbered / check lists, tables, images, callout banners, two-column text, quotes, code blocks,
cover images and icons, article properties, and the embedded Item Kanban / Item List / Item
Calendar views with their item articles (stages, properties, dates).
"""
import io
import json
import logging
from datetime import timedelta

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'
IMG = '/hudson_pos_demo_data/static/src/img'


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


def _company_name(env):
    return env.company.name or 'Resto Cafe Solutions'


# =========================================================================== SIGN
# Page geometry (A4 in points). Field positions are ratios of the page, measured from the top-left.
PAGE_W, PAGE_H = 595.0, 842.0
MARGIN = 56.0

# xid, name, tags, validity days, message, roles [(name, auth by email, can delegate)],
# role field sets: role index -> list of (label, item type xmlid, placeholder, options),
# page 1 sections [(heading, text)]
SIGN_TEMPLATES = [
    ('rc_sign_tmpl_employee', 'Employee Employment Agreement', ['HR', 'Employment'], 30,
     'Please review your employment terms and sign. HR and the General Manager countersign after you.',
     [('Employee', True, False), ('HR Manager', False, True), ('General Manager', False, False)],
     {0: [('Full name', 'sign_item_type_name', 'Employee name', None),
          ('Position', 'sign_item_type_selection', 'Position',
           'Commis Chef\nChef de Partie\nBarista\nServer\nCashier\nDelivery Associate'),
          ('Emergency contact', 'sign_item_type_text', 'Name & phone', None),
          ('Date', 'sign_item_type_date', 'Date', None),
          ('Signature', 'sign_item_type_signature', 'Employee signature', None),
          ('I have read the staff handbook and accept these terms.', 'sign_item_type_checkbox', '', None)],
      1: [('Full name', 'sign_item_type_name', 'HR manager', None),
          ('Employee ID', 'sign_item_type_text', 'EMP-0000', None),
          ('Date', 'sign_item_type_date', 'Date', None),
          ('Signature', 'sign_item_type_signature', 'HR signature', None)],
      2: [('Full name', 'sign_item_type_name', 'General manager', None),
          ('Date', 'sign_item_type_date', 'Date', None),
          ('Signature', 'sign_item_type_signature', 'GM signature', None)]},
     [('1. Position and place of work', 'The Employee is appointed to the position stated on page 2 at the '
       'restaurant and central kitchen of {company} in Kochi, and may be scheduled across outlets as needed.'),
      ('2. Working hours and shifts', 'Standard working time is 48 hours per week over six days, on a rotating '
       'shift rota published one week in advance. Overtime is paid as per the Kerala Shops and Establishments Act.'),
      ('3. Probation', 'The first three months are a probation period with a notice period of seven days on either '
       'side. After confirmation, the notice period is thirty days.'),
      ('4. Food safety and hygiene', 'The Employee completes the FSSAI food-handler training within 30 days, '
       'follows the hygiene SOPs and reports any illness before the start of a shift.'),
      ('5. Uniform and conduct', 'Uniforms are provided and remain company property. The Employee follows the '
       'grooming standards and the code of conduct of the staff handbook.')]),
    ('rc_sign_tmpl_vendor', 'Vendor Supply Agreement', ['Purchase', 'Vendor'], 45,
     'Supply agreement for fresh produce and kitchen supplies. Signed by the vendor first, then by our '
     'Purchase Manager and Finance Head.',
     [('Vendor', True, True), ('Purchase Manager', False, False), ('Finance Head', False, False)],
     {0: [('Authorised signatory', 'sign_item_type_name', 'Signatory name', None),
          ('Company', 'sign_item_type_company', 'Vendor company', None),
          ('GSTIN', 'sign_item_type_text', '32ABCDE1234F1Z5', None),
          ('Email', 'sign_item_type_email', 'Email', None),
          ('Date', 'sign_item_type_date', 'Date', None),
          ('Signature', 'sign_item_type_signature', 'Vendor signature', None),
          ('We hold a valid FSSAI licence for the supplied goods.', 'sign_item_type_checkbox', '', None)],
      1: [('Full name', 'sign_item_type_name', 'Purchase manager', None),
          ('Payment terms', 'sign_item_type_selection', 'Payment terms', '15 days\n30 days\n45 days'),
          ('Date', 'sign_item_type_date', 'Date', None),
          ('Signature', 'sign_item_type_signature', 'Purchase signature', None)],
      2: [('Full name', 'sign_item_type_name', 'Finance head', None),
          ('Date', 'sign_item_type_date', 'Date', None),
          ('Signature', 'sign_item_type_signature', 'Finance signature', None)]},
     [('1. Scope of supply', 'The Vendor supplies the products listed in the purchase orders of {company} '
       '(fresh produce, dairy, dry stores and packaging) at the agreed vendor prices.'),
      ('2. Quality and food safety', 'Goods meet FSSAI standards, arrive within the agreed temperature range and '
       'carry batch and expiry information. Goods failing the receipt quality check are returned at the Vendor\'s cost.'),
      ('3. Delivery', 'Deliveries reach the central kitchen receiving bay between 6:00 and 9:00 a.m. within the '
       'lead time agreed per product. Late or partial deliveries are recorded on the purchase order.'),
      ('4. Prices and invoicing', 'Prices are fixed for the period of the purchase agreement. Invoices quote the '
       'purchase order reference and GSTIN and are paid as per the payment terms on page 2.'),
      ('5. Term and termination', 'This agreement is valid for twelve months and renews automatically unless '
       'either party gives thirty days\' written notice.')]),
    ('rc_sign_tmpl_customer', 'Customer Catering Agreement', ['Sales', 'Catering'], 15,
     'Thank you for choosing us for your event! Please confirm the catering terms; our Events Manager '
     'countersigns once you have signed.',
     [('Customer', True, False), ('Events Manager', False, False)],
     {0: [('Full name', 'sign_item_type_name', 'Customer name', None),
          ('Phone', 'sign_item_type_phone', 'Phone', None),
          ('Event date & venue', 'sign_item_type_text', 'Date, venue', None),
          ('Menu preference', 'sign_item_type_selection', 'Menu', 'Vegetarian\nNon-vegetarian\nMixed buffet'),
          ('Special requests', 'sign_item_type_multiline', 'Allergies, decor, timing...', None),
          ('Date', 'sign_item_type_date', 'Date', None),
          ('Signature', 'sign_item_type_signature', 'Customer signature', None),
          ('I accept the cancellation and advance-payment terms.', 'sign_item_type_checkbox', '', None)],
      1: [('Full name', 'sign_item_type_name', 'Events manager', None),
          ('Quotation reference', 'sign_item_type_text', 'S000xx', None),
          ('Date', 'sign_item_type_date', 'Date', None),
          ('Signature', 'sign_item_type_signature', 'Events signature', None)]},
     [('1. Services', '{company} provides the food, beverages, service staff and equipment described in the '
       'quotation referenced on page 2, for the event date, venue and guest count confirmed there.'),
      ('2. Guest count', 'The final guest count is confirmed 72 hours before the event. Up to 5% more guests are '
       'served at no extra cost; additional guests are invoiced per head.'),
      ('3. Payment', 'An advance of 30% confirms the booking; the balance is due on the event day. Prices include '
       'GST unless stated otherwise.'),
      ('4. Cancellation', 'Cancellations more than 14 days before the event are refunded in full, 7-14 days 50%, '
       'and less than 7 days are not refundable.'),
      ('5. Food safety', 'Food is prepared in our FSSAI-licensed kitchen and served within safe holding times. '
       'Leftovers are not packed for take-away after the safe holding time.')]),
    ('rc_sign_tmpl_nda', 'Recipe Confidentiality Agreement (NDA)', ['HR', 'Kitchen'], 30,
     'Our recipes are our signature. Please sign this confidentiality agreement before joining the kitchen.',
     [('Employee', False, False), ('Head Chef', False, False)],
     {0: [('Full name', 'sign_item_type_name', 'Employee name', None),
          ('Kitchen section', 'sign_item_type_text', 'e.g. Tandoor, Pastry', None),
          ('Date', 'sign_item_type_date', 'Date', None),
          ('Signature', 'sign_item_type_signature', 'Employee signature', None),
          ('I will not share recipes, supplier prices or photos of the kitchen.', 'sign_item_type_checkbox', '', None)],
      1: [('Full name', 'sign_item_type_name', 'Head chef', None),
          ('Date', 'sign_item_type_date', 'Date', None),
          ('Signature', 'sign_item_type_signature', 'Head chef signature', None)]},
     [('1. Confidential information', 'Recipes, spice blends, preparation methods, supplier lists and prices, '
       'menu plans and business figures of {company} are confidential information.'),
      ('2. Obligations', 'The Employee uses confidential information only to perform their work, does not copy or '
       'photograph recipes or kitchen documents, and returns all documents when leaving.'),
      ('3. Duration', 'These obligations apply during employment and for three years after it ends.'),
      ('4. Remedies', 'A breach may lead to disciplinary action, termination and a claim for damages.')]),
]

# role colour themes of hudson_sign (color, border, text)
ROLE_COLORS = [('#e2dcf3', '#a495d6', '#2e2252'), ('#d1fae5', '#10b981', '#065f46'),
               ('#fef3c7', '#f59e0b', '#92400e'), ('#e0e7ff', '#6366f1', '#3730a3')]


def _wrap(text, font, size, width):
    from reportlab.lib.utils import simpleSplit
    return simpleSplit(text, font, size, width)


def _agreement_pdf(env, name, sections, roles, role_fields):
    """2-page agreement: terms + initials boxes (page 1), one signature block per role (page 2).
    Returns (pdf bytes, [(role index, type xmlid, placeholder, options, page, x, y, w, h)])."""
    from reportlab.pdfgen import canvas
    company = _company_name(env)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(name)
    items = []

    def ratio_box(page, x, top, w, h):
        return page, x / PAGE_W, top / PAGE_H, w / PAGE_W, h / PAGE_H

    def header(subtitle):
        c.setFillColorRGB(0.13, 0.33, 0.30)
        c.rect(0, PAGE_H - 70, PAGE_W, 70, stroke=0, fill=1)
        c.setFillColorRGB(1, 1, 1)
        c.setFont('Helvetica-Bold', 17)
        c.drawString(MARGIN, PAGE_H - 38, name)
        c.setFont('Helvetica', 10)
        c.drawString(MARGIN, PAGE_H - 56, f'{company}  -  {subtitle}')
        c.setFillColorRGB(0, 0, 0)

    def footer(page):
        c.setFont('Helvetica', 8)
        c.setFillColorRGB(0.45, 0.45, 0.45)
        c.drawString(MARGIN, 28, f'{company} - {name}')
        c.drawRightString(PAGE_W - MARGIN, 28, f'Page {page} of 2')
        c.setFillColorRGB(0, 0, 0)

    # ---- page 1: terms
    header('Terms and conditions')
    top = 100.0
    width = PAGE_W - 2 * MARGIN
    for heading, text in sections:
        c.setFont('Helvetica-Bold', 11.5)
        c.drawString(MARGIN, PAGE_H - top, heading)
        top += 17
        c.setFont('Helvetica', 10)
        for line in _wrap(text.format(company=company), 'Helvetica', 10, width):
            c.drawString(MARGIN, PAGE_H - top, line)
            top += 14
        top += 10
    # initials of every signer at the bottom of page 1
    c.setFont('Helvetica-Bold', 10)
    c.drawString(MARGIN, 120, 'Initials of the parties:')
    box_w, box_h, gap = 110.0, 34.0, 18.0
    for i, (role_name, _a, _d) in enumerate(roles):
        x = MARGIN + i * (box_w + gap)
        c.setFont('Helvetica', 8.5)
        c.drawString(x, 104, role_name)
        c.setStrokeColorRGB(0.6, 0.6, 0.6)
        c.rect(x, 64, box_w, box_h, stroke=1, fill=0)
        items.append((i, 'sign_item_type_initial', 'Initials', None) + ratio_box(1, x + 4, PAGE_H - 64 - box_h + 2, box_w - 8, box_h - 4))
    footer(1)
    c.showPage()

    # ---- page 2: one signature block per role
    header('Signatures')
    top = 96.0
    label_w = 150.0
    field_x = MARGIN + label_w
    field_w = PAGE_W - MARGIN - field_x
    line_h = 22.0
    for i, (role_name, _a, _d) in enumerate(roles):
        c.setFillColorRGB(0.13, 0.33, 0.30)
        c.setFont('Helvetica-Bold', 12)
        c.drawString(MARGIN, PAGE_H - top - 12, f'{i + 1}. {role_name}')
        c.setFillColorRGB(0, 0, 0)
        top += 24
        for label, type_xid, placeholder, options in role_fields.get(i, []):
            if type_xid == 'sign_item_type_checkbox':
                c.setStrokeColorRGB(0.5, 0.5, 0.5)
                c.rect(MARGIN, PAGE_H - top - 13, 13, 13, stroke=1, fill=0)
                c.setFont('Helvetica', 9.5)
                c.drawString(MARGIN + 20, PAGE_H - top - 10, label)
                items.append((i, type_xid, placeholder, options) + ratio_box(2, MARGIN - 1, top - 1, 15, 15))
                top += line_h
                continue
            h = 40.0 if type_xid == 'sign_item_type_signature' else (36.0 if type_xid == 'sign_item_type_multiline' else 18.0)
            c.setFont('Helvetica', 10)
            c.drawString(MARGIN, PAGE_H - top - h + 5, f'{label}:')
            c.setStrokeColorRGB(0.7, 0.7, 0.7)
            c.line(field_x, PAGE_H - top - h, field_x + field_w, PAGE_H - top - h)
            w = field_w if type_xid in ('sign_item_type_signature', 'sign_item_type_multiline', 'sign_item_type_text',
                                        'sign_item_type_email', 'sign_item_type_company') else min(field_w, 200.0)
            items.append((i, type_xid, placeholder, options) + ratio_box(2, field_x, top, w, h - 2))
            top += h + 6
        top += 14
    footer(2)
    c.showPage()
    c.save()
    return buf.getvalue(), items


def _sign_templates(env):
    admin = env.ref('base.user_admin')
    tag_colors = {'HR': 4, 'Employment': 10, 'Purchase': 2, 'Vendor': 6, 'Sales': 3, 'Catering': 9, 'Kitchen': 1}
    tags = {}
    for name, color in tag_colors.items():
        tags[name] = (env['hudson.sign.template.tag'].sudo().search([('name', '=', name)], limit=1)
                      or _get_or_create(env, f'rc_sign_tag_{name.lower()}', 'hudson.sign.template.tag',
                                        {'name': name, 'color': color}))
    ItemType = env['hudson.sign.item.type']
    for xid, name, tag_names, validity, message, roles, role_fields, sections in SIGN_TEMPLATES:
        if _ref(env, xid):
            continue
        pdf, items = _agreement_pdf(env, name, sections, roles, role_fields)
        attachment = _bind(env, f'{xid}_pdf', env['ir.attachment'].sudo().create({
            'name': f'{name}.pdf', 'type': 'binary', 'mimetype': 'application/pdf', 'raw': pdf,
        }))
        template = _bind(env, xid, env['hudson.sign.template'].sudo().create({
            'name': name, 'attachment_id': attachment.id, 'active': True,
            'author_id': admin.id, 'authorized_ids': [Command.clear()],  # empty = every user can use it
            'favorited_ids': [Command.link(admin.id)],  # shown under "My Favorites" (default filter)
            'tag_ids': [Command.set([tags[t].id for t in tag_names])],
            'signature_request_validity': validity, 'message': f'<p>{message}</p>',
        }))
        role_recs = []
        for seq, (role_name, by_email, can_delegate) in enumerate(roles, start=1):
            color, border, text = ROLE_COLORS[(seq - 1) % len(ROLE_COLORS)]
            role_recs.append(env['hudson.sign.template.role'].sudo().create({
                'template_id': template.id, 'name': role_name, 'sequence': seq,  # sequence = signing order
                'color': color, 'border_color': border, 'text_color': text,
                'auth_method': 'email' if by_email else 'none', 'can_delegate': can_delegate,
            }))
        vals = []
        for role_idx, type_xid, placeholder, options, page, x, y, w, h in items:
            item_type = env.ref(f'hudson_sign.{type_xid}', raise_if_not_found=False)
            if not item_type:
                kind = type_xid.removeprefix('sign_item_type_')
                item_type = ItemType.search([('item_type', '=', kind)], limit=1)
            if not item_type:
                continue
            vals.append({
                'template_id': template.id, 'role_id': role_recs[role_idx].id, 'type_id': item_type.id,
                'page_number': page, 'pos_x': round(x, 4), 'pos_y': round(y, 4),
                'width': round(w, 4), 'height': round(h, 4),
                'placeholder': placeholder or False, 'options': options or False,
                'mandatory': type_xid not in ('sign_item_type_multiline',),
            })
        env['hudson.sign.template.item'].sudo().create(vals)


def load_sign_suite_demo_data(env):
    if 'hudson.sign.template' not in env:
        _logger.info("Hudson POS: Sign not installed, skipping Sign demo data.")
        return
    try:
        with env.cr.savepoint():
            _sign_templates(env)
        _logger.info("Hudson POS: Sign templates demo data loaded.")
    except Exception as e:
        _logger.exception("Hudson POS: Sign demo data failed: %s", e)


# =========================================================================== KNOWLEDGE
def _banner(kind, emoji, html):
    """Callout block, same markup as the editor's /banner command."""
    return (f'<div class="o_editor_banner user-select-none o-contenteditable-false lh-1 d-flex align-items-center '
            f'alert alert-{kind} pb-0 pt-3 ps-3 pe-3" role="status">'
            f'<i class="o_editor_banner_icon mb-3 fst-normal" data-oe-aria-label="{kind}">{emoji}</i>'
            f'<div class="o_editor_banner_content o-contenteditable-true w-100 px-3">{html}</div></div>')


def _table(head, rows):
    th = ''.join(f'<th>{h}</th>' for h in head)
    body = ''.join('<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>' for row in rows)
    return (f'<table class="table table-bordered o_table"><thead><tr>{th}</tr></thead>'
            f'<tbody>{body}</tbody></table><p><br></p>')


def _checklist(items):
    """Check list (/checklist); items prefixed with '+' are checked."""
    lis = ''.join(f'<li class="o_checked">{t[1:]}</li>' if t.startswith('+') else f'<li>{t}</li>' for t in items)
    return f'<ul class="o_checklist">{lis}</ul>'


def _ul(items):
    return '<ul>' + ''.join(f'<li>{t}</li>' for t in items) + '</ul>'


def _ol(items):
    return '<ol>' + ''.join(f'<li>{t}</li>' for t in items) + '</ol>'


def _img(name, alt, width='100%'):
    return f'<p><img src="{IMG}/{name}" alt="{alt}" class="img-fluid rounded" style="width: {width};"></p>'


def _columns(*cols):
    """Text columns (/2 columns, /3 columns)."""
    size = 12 // len(cols)
    inner = ''.join(f'<div class="col-{size}">{c}</div>' for c in cols)
    return f'<div class="o_text_columns"><div class="row">{inner}</div></div>'


def _item_view(view_type, name):
    """Embedded Item Kanban / List / Calendar (/item kanban...), rendering the article's items."""
    props = json.dumps({'viewType': view_type, 'name': name})
    return (f'<div class="o_knowledge_item_view_host" data-embedded="knowledgeItemView" data-oe-protected="true" '
            f'contenteditable="false" data-embedded-props=\'{props}\'></div><p><br></p>')


def _body(title, *parts):
    # the Knowledge editor reads the article title from the first <h1>
    return f'<h1>{title}</h1>' + ''.join(parts)


def _articles_spec(company):
    return [
        # xid, parent xid, name, icon, cover image, favourite, full width, body
        ('rc_kb_ops', None, 'Restaurant Operations', '🍽️', 'food_category.jpg', True, False, _body(
            'Restaurant Operations',
            f'<p>Everything the floor team of <b>{company}</b> needs for a smooth service, from opening the '
            'doors to cashing up. Sub-articles cover each part of the day in detail.</p>',
            _banner('info', '💡', '<p><b>New here?</b> Start with <i>Opening &amp; Closing</i>, then read '
                                 '<i>Cash &amp; POS Handling</i> before your first shift at the counter.</p>'),
            '<h2>Service hours</h2>',
            _table(['Service', 'Days', 'Hours', 'Floor lead'],
                   [['Breakfast', 'Mon - Sun', '7:00 - 10:30', 'Arjun'],
                    ['Lunch', 'Mon - Sun', '12:00 - 15:30', 'Priya'],
                    ['High tea', 'Sat - Sun', '16:00 - 18:00', 'Rahul'],
                    ['Dinner', 'Mon - Sun', '19:00 - 23:00', 'Arjun']]),
            '<h2>Our service promise</h2>',
            _columns('<h3>Welcome</h3>' + _ul(['Greet guests within 30 seconds', 'Offer water and the menu',
                                              'Mention the specials of the day']),
                     '<h3>Serve</h3>' + _ul(['Starters within 12 minutes', 'Mains within 20 minutes',
                                            'Check back two bites in']),
                     '<h3>Farewell</h3>' + _ul(['Bill on request, never rushed', 'Ask for feedback',
                                               'Invite them back'])),
            '<h2>Daily shift tasks</h2><p>Drag the cards between the stages as the shift goes on. Each card '
            'has a shift, an area and a priority (article properties).</p>',
            _item_view('kanban', 'Daily Shift Tasks'),
            '<blockquote>"Hospitality is making guests feel at home, even when you wish they were."</blockquote>',
        )),
        ('rc_kb_ops_open', 'rc_kb_ops', 'Opening & Closing Checklist', '🔑', None, False, False, _body(
            'Opening & Closing Checklist',
            '<p>Tick each item as you go. The shift lead signs off in the POS before opening the register.</p>',
            '<h2>Opening (by 6:45 a.m.)</h2>',
            _checklist(['+Disarm alarm, lights and exhaust fans on', '+Check fridge and freezer temperatures',
                        'Switch on the espresso machine (needs 20 minutes)', 'Set tables: cutlery, napkins, menus',
                        'Open the POS session and count the opening float', 'Check the reservations and waitlist']),
            '<h2>Closing</h2>',
            _ol(['Last orders 30 minutes before closing', 'Close the POS session and print the Z report',
                 'Count cash, record the difference and lock it in the safe', 'Clean and sanitise all surfaces',
                 'Fill the temperature log, switch off equipment', 'Arm the alarm and lock up']),
            _banner('warning', '⚠️', '<p>Never leave cash in the drawer overnight. A cash difference above '
                                    '₹200 must be reported to the manager the same evening.</p>'),
        )),
        ('rc_kb_ops_pos', 'rc_kb_ops', 'Cash & POS Handling', '💳', None, False, False, _body(
            'Cash & POS Handling',
            '<h2>Payment methods</h2>',
            _table(['Method', 'Accepted', 'Notes'],
                   [['Cash', '✅', 'Count change back to the guest'], ['Card', '✅', 'Visa, Mastercard, RuPay'],
                    ['UPI', '✅', 'Show the QR code on the customer display'], ['Cheque', '❌', 'Not accepted']]),
            '<h2>Refunds</h2>',
            _ol(['Open the order in the POS (Orders, search by receipt number)', 'Click Refund and pick the lines',
                 'Refund to the original payment method', 'Manager approval is needed above ₹1,000']),
            '<h2>Discount codes</h2><p>Enter promotion codes with <b>Enter Code</b> in the POS actions menu:</p>',
            '<pre>HAPPYHOUR20   20% off drinks, 16:00 - 18:00\nVIPMEMBER     15% off for VIP pricelist members</pre>',
        )),
        ('rc_kb_ops_events', 'rc_kb_ops', 'Specials & Events Calendar', '📅', 'drink_category.jpg', False, False, _body(
            'Specials & Events Calendar',
            '<p>Weekly specials, live music and private events. Click a day in the calendar to add an event.</p>',
            _item_view('calendar', 'Specials & Events'),
        )),

        ('rc_kb_onb', None, 'Employee Onboarding', '👋', 'th-espresso.png', True, False, _body(
            'Employee Onboarding',
            f'<p>Welcome to the team! This space guides every new joiner of <b>{company}</b> through their '
            'first two weeks.</p>',
            _banner('success', '🎉', '<p>Your buddy will meet you at reception at 9:00 a.m. on day one. '
                                    'Bring your ID proof, bank details and two passport photos.</p>'),
            '<h2>Your first two weeks</h2>',
            _table(['Day', 'What happens', 'With'],
                   [['Day 1', 'Welcome, tour, uniform, HR paperwork', 'HR + buddy'],
                    ['Day 2-3', 'Food safety training and hygiene test', 'Head chef'],
                    ['Day 4-7', 'Shadow shifts in your section', 'Buddy'],
                    ['Week 2', 'Supervised shifts, POS training', 'Shift lead'],
                    ['Day 14', 'Check-in with your manager', 'Manager']]),
            '<h2>Onboarding tracker</h2><p>One item per new joiner, with department, buddy, start date and '
            'whether the uniform was issued.</p>',
            _item_view('list', 'Onboarding Tracker'),
        )),
        ('rc_kb_onb_day1', 'rc_kb_onb', 'Day 1 Checklist', '✅', None, False, False, _body(
            'Day 1 Checklist',
            _checklist(['+Sign the employment agreement (Sign app)', '+Sign the recipe confidentiality agreement',
                        'Collect uniform, apron and name badge', 'Get your POS badge and Odoo login',
                        'Tour: kitchen, stores, staff room, fire exits', 'Read the staff handbook']),
            _banner('info', '📝', '<p>Agreements are sent from <b>Sign &gt; Templates</b>: '
                                 '<i>Employee Employment Agreement</i> and <i>Recipe Confidentiality Agreement</i>.</p>'),
        )),
        ('rc_kb_onb_uniform', 'rc_kb_onb', 'Uniform & Grooming Standards', '👔', None, False, False, _body(
            'Uniform & Grooming Standards',
            _columns('<h3>Kitchen</h3>' + _ul(['Chef jacket and black trousers', 'Hair net or cap at all times',
                                              'Non-slip closed shoes', 'No jewellery except a plain band']),
                     '<h3>Floor</h3>' + _ul(['Teal shirt with name badge', 'Black apron, ironed',
                                            'Hair tied back', 'Clean, short nails'])),
            _img('th-milkshake_banana.png', 'Presentation matters', '40%'),
            '<p><i>We present our food beautifully - and ourselves too.</i></p>',
        )),
        ('rc_kb_onb_roles', 'rc_kb_onb', 'Roles & Responsibilities', '🧑‍🍳', None, False, True, _body(
            'Roles & Responsibilities',
            _table(['Role', 'Reports to', 'Key responsibilities'],
                   [['Server', 'Floor lead', 'Take orders in the POS, serve, settle bills'],
                    ['Barista', 'Floor lead', 'Coffee and mocktail bar, bar hygiene'],
                    ['Commis chef', 'Chef de partie', 'Mise en place, prep, cleaning'],
                    ['Chef de partie', 'Head chef', 'Run a section, quality of every plate'],
                    ['Cashier', 'Manager', 'POS sessions, cash, refunds'],
                    ['Delivery associate', 'Manager', 'Deliveries on time, temperature boxes']]),
        )),

        ('rc_kb_safety', None, 'Food Safety & Hygiene', '🧼', 'th-salmon.png', True, False, _body(
            'Food Safety & Hygiene',
            '<p>Our kitchen follows FSSAI Schedule 4 and HACCP principles. Every team member is responsible '
            'for food safety.</p>',
            _banner('danger', '🚨', '<p><b>Stop and report</b>: vomiting, diarrhoea or fever means you do not '
                                   'handle food. Call your manager before your shift.</p>'),
            '<h2>Safe temperatures</h2>',
            _table(['Item', 'Target', 'Action if outside'],
                   [['Fridge', '1 - 4 °C', 'Move food, call maintenance'],
                    ['Freezer', '-18 °C or below', 'Check door seal, move stock'],
                    ['Hot holding', '63 °C or above', 'Reheat to 75 °C or discard'],
                    ['Cooked chicken (core)', '75 °C', 'Continue cooking'],
                    ['Cooling', '< 8 °C within 90 min', 'Use the blast chiller']]),
            '<h2>The 5 HACCP steps we check daily</h2>',
            _ol(['Receiving: temperature and expiry of every delivery', 'Storage: FEFO, labels, raw below cooked',
                 'Preparation: colour-coded boards, hand washing', 'Cooking: core temperature checks',
                 'Holding and service: time and temperature limits']),
            '<h2>Hygiene audit actions</h2>',
            _item_view('kanban', 'Hygiene Audit Actions'),
        )),
        ('rc_kb_safety_allergens', 'rc_kb_safety', 'Allergen Matrix', '🥜', None, False, True, _body(
            'Allergen Matrix',
            '<p>Always ask the guest about allergies and check this matrix with the chef.</p>',
            _table(['Dish', 'Gluten', 'Dairy', 'Nuts', 'Egg', 'Fish/Shellfish'],
                   [['Margherita Pizza', '✔', '✔', '', '', ''], ['Chicken Club Sandwich', '✔', '✔', '', '✔', ''],
                    ['Salmon Avocado Maki', '', '', '', '', '✔'], ['Tiramisu', '✔', '✔', '', '✔', ''],
                    ['Pecan Pie', '✔', '✔', '✔', '✔', ''], ['Banana Milkshake', '', '✔', '', '', '']]),
            _banner('warning', '⚠️', '<p>Cross-contact: nuts are used in the pastry section. Tell guests with a '
                                    'nut allergy that we cannot guarantee a nut-free dessert.</p>'),
        )),
        ('rc_kb_safety_temp', 'rc_kb_safety', 'Temperature Log', '🌡️', None, False, False, _body(
            'Temperature Log',
            '<p>One line per check: unit, reading and who checked it. Readings outside the safe range are '
            'flagged in red by the shift lead.</p>',
            _item_view('list', 'Temperature Checks'),
        )),
        ('rc_kb_safety_cleaning', 'rc_kb_safety', 'Cleaning Schedule', '🧽', None, False, False, _body(
            'Cleaning Schedule',
            _table(['Area', 'Daily', 'Weekly', 'Monthly'],
                   [['Work surfaces', 'After every task', '-', '-'], ['Fryers', 'Filter oil', 'Change oil', 'Deep clean'],
                    ['Walk-in chiller', 'Wipe handles', 'Shelves', 'Defrost & deep clean'],
                    ['Exhaust hood', '-', 'Filters', 'Professional service'], ['Floors', 'Mop each shift', 'Scrub', '-']]),
        )),

        ('rc_kb_sop', None, 'Kitchen SOP', '👨‍🍳', 'th-pasta-4f.png', True, False, _body(
            'Kitchen SOP',
            '<p>Standard operating procedures for the kitchen and bar: how we prepare, cook, plate and serve '
            'so that every dish tastes the same, every day.</p>',
            _columns(_img('th-pizza-fu.png', 'Pizza'), _img('th-burger.png', 'Burger'), _img('th-maki.png', 'Maki')),
            '<h2>SOP index</h2>',
            _ul(['<b>Mise en Place</b> - prepare before service', '<b>Recipe Standards</b> - portions and signature dishes',
                 '<b>Espresso Bar</b> - coffee recipes and machine care']),
        )),
        ('rc_kb_sop_mise', 'rc_kb_sop', 'Mise en Place', '🔪', None, False, False, _body(
            'Mise en Place',
            _ol(['Read the prep list printed from the kitchen display', 'Collect ingredients (FEFO: oldest first)',
                 'Wash, peel and cut; label every container with name, date and initials',
                 'Store at the right temperature until service', 'Clean as you go']),
            _checklist(['+Sauces portioned', '+Garnish tray ready', 'Proteins marinated', 'Bread proofed']),
        )),
        ('rc_kb_sop_recipes', 'rc_kb_sop', 'Recipe Standards', '📖', None, False, False, _body(
            'Recipe Standards',
            '<h2>Portion sizes</h2>',
            _table(['Dish', 'Portion', 'Plate', 'Garnish'],
                   [['Pasta Quattro Formaggi', '250 g', 'Pasta bowl', 'Parmesan, basil'],
                    ['Cheeseburger', '180 g patty', 'Wooden board', 'Pickles, fries 120 g'],
                    ['Salmon Avocado Maki', '8 pieces', 'Slate', 'Pickled ginger, wasabi']]),
            '<p>Signature desserts have their own recipe cards in the sub-articles.</p>',
        )),
        ('rc_kb_sop_tiramisu', 'rc_kb_sop_recipes', 'Signature Dish: Tiramisu', '🍰', None, False, False, _body(
            'Signature Dish: Tiramisu',
            _columns(_img('product_tiramisu.png', 'Tiramisu'),
                     '<h3>Ingredients (12 portions)</h3>' + _ul(['500 g mascarpone', '4 eggs, separated', '100 g sugar',
                                                                 '300 ml strong espresso, cooled', '24 savoiardi biscuits',
                                                                 'Cocoa powder to dust'])),
            '<h3>Method</h3>',
            _ol(['Whisk yolks and sugar until pale, fold in mascarpone', 'Whip whites to soft peaks and fold in',
                 'Dip biscuits in espresso (1 second each side)', 'Layer biscuits and cream twice',
                 'Chill at least 6 hours, dust with cocoa before serving']),
            _banner('info', '🥚', '<p>Use pasteurised eggs only. Shelf life: 48 hours, labelled.</p>'),
        )),
        ('rc_kb_sop_espresso', 'rc_kb_sop', 'Espresso Bar', '☕', None, False, False, _body(
            'Espresso Bar',
            _columns(_img('th-espresso.png', 'Espresso', '80%'),
                     '<h3>Espresso recipe</h3>' + _table(['Dose', 'Yield', 'Time', 'Temp'],
                                                         [['18 g', '36 g', '25 - 30 s', '93 °C']])),
            '<h3>Machine care</h3>',
            _checklist(['+Purge the group head after every shot', '+Wipe the steam wand after every milk',
                        'Backflush with detergent at closing', 'Descale weekly (Monday)']),
        )),
    ]


# Items of the embedded views: parent xid -> (stages, properties definition, items)
# item: (name, stage, properties dict, start offset days|None, duration hours)
ITEM_SPECS = {
    'rc_kb_ops': (
        ['To Do', 'In Progress', 'Done'],
        [{'name': 'shift', 'type': 'selection', 'string': 'Shift',
          'selection': [['morning', 'Morning'], ['afternoon', 'Afternoon'], ['evening', 'Evening']]},
         {'name': 'area', 'type': 'char', 'string': 'Area'},
         {'name': 'priority', 'type': 'selection', 'string': 'Priority',
          'selection': [['low', 'Low'], ['normal', 'Normal'], ['high', 'High']]}],
        [('Restock napkins and condiments', 'To Do', {'shift': 'morning', 'area': 'Floor', 'priority': 'normal'}, None, 0),
         ('Polish cutlery and glasses', 'In Progress', {'shift': 'afternoon', 'area': 'Floor', 'priority': 'low'}, None, 0),
         ('Brief team on dinner specials', 'To Do', {'shift': 'evening', 'area': 'Floor', 'priority': 'high'}, None, 0),
         ('Update specials board', 'Done', {'shift': 'morning', 'area': 'Entrance', 'priority': 'normal'}, None, 0),
         ('Check reservations for large parties', 'In Progress', {'shift': 'afternoon', 'area': 'Reception', 'priority': 'high'}, None, 0),
         ('Clean coffee machine', 'Done', {'shift': 'evening', 'area': 'Bar', 'priority': 'normal'}, None, 0)]),
    'rc_kb_ops_events': (
        ['Planned', 'Confirmed'],
        [{'name': 'kind', 'type': 'selection', 'string': 'Type',
          'selection': [['special', 'Special'], ['music', 'Live music'], ['private', 'Private event']]}],
        [('Monsoon Kappa & Karimeen special', 'Confirmed', {'kind': 'special'}, 1, 4),
         ('Live acoustic night', 'Confirmed', {'kind': 'music'}, 3, 3),
         ('Birthday party - rooftop (40 pax)', 'Confirmed', {'kind': 'private'}, 5, 4),
         ('Weekend high-tea menu', 'Planned', {'kind': 'special'}, 6, 2),
         ('Corporate lunch - IT Park', 'Planned', {'kind': 'private'}, 9, 3),
         ('Jazz brunch', 'Planned', {'kind': 'music'}, 13, 3)]),
    'rc_kb_onb': (
        ['Starting', 'Training', 'Completed'],
        [{'name': 'department', 'type': 'selection', 'string': 'Department',
          'selection': [['kitchen', 'Kitchen'], ['floor', 'Floor'], ['bar', 'Bar'], ['delivery', 'Delivery']]},
         {'name': 'buddy', 'type': 'char', 'string': 'Buddy'},
         {'name': 'start_date', 'type': 'date', 'string': 'Start Date'},
         {'name': 'uniform', 'type': 'boolean', 'string': 'Uniform Issued'}],
        [('Anjali Das - Server', 'Training', {'department': 'floor', 'buddy': 'Priya Menon', 'start_date': -6, 'uniform': True}, None, 0),
         ('Gokul Krishna - Commis Chef', 'Training', {'department': 'kitchen', 'buddy': 'Rahul Nair', 'start_date': -4, 'uniform': True}, None, 0),
         ('Faisal Ahmed - Barista', 'Starting', {'department': 'bar', 'buddy': 'Vishnu Kumar', 'start_date': 2, 'uniform': False}, None, 0),
         ('Lakshmi Iyer - Delivery Associate', 'Starting', {'department': 'delivery', 'buddy': 'Arun Varma', 'start_date': 5, 'uniform': False}, None, 0),
         ('Nikhil Raj - Chef de Partie', 'Completed', {'department': 'kitchen', 'buddy': 'Rahul Nair', 'start_date': -20, 'uniform': True}, None, 0)]),
    'rc_kb_safety': (
        ['Open', 'In Progress', 'Closed'],
        [{'name': 'area', 'type': 'char', 'string': 'Area'},
         {'name': 'severity', 'type': 'selection', 'string': 'Severity',
          'selection': [['minor', 'Minor'], ['major', 'Major'], ['critical', 'Critical']]}],
        [('Replace cracked chopping board (raw meat)', 'Open', {'area': 'Butchery', 'severity': 'major'}, None, 0),
         ('Fix walk-in chiller door seal', 'In Progress', {'area': 'Stores', 'severity': 'critical'}, None, 0),
         ('Label sauces in the pass fridge', 'Closed', {'area': 'Pass', 'severity': 'minor'}, None, 0),
         ('Refill hand-wash soap at bar sink', 'Closed', {'area': 'Bar', 'severity': 'minor'}, None, 0),
         ('Pest control visit report', 'Open', {'area': 'Whole site', 'severity': 'major'}, None, 0)]),
    'rc_kb_safety_temp': (
        ['To Review', 'OK'],
        [{'name': 'unit', 'type': 'char', 'string': 'Unit'},
         {'name': 'reading', 'type': 'float', 'string': 'Reading (°C)'},
         {'name': 'checked_by', 'type': 'char', 'string': 'Checked By'},
         {'name': 'in_range', 'type': 'boolean', 'string': 'In Safe Range'}],
        [('Walk-in chiller - morning', 'OK', {'unit': 'Walk-in chiller', 'reading': 3.2, 'checked_by': 'Rahul', 'in_range': True}, None, 0),
         ('Freezer 1 - morning', 'OK', {'unit': 'Freezer 1', 'reading': -19.5, 'checked_by': 'Rahul', 'in_range': True}, None, 0),
         ('Pass fridge - lunch', 'To Review', {'unit': 'Pass fridge', 'reading': 6.1, 'checked_by': 'Gokul', 'in_range': False}, None, 0),
         ('Bain-marie - lunch', 'OK', {'unit': 'Bain-marie', 'reading': 68.0, 'checked_by': 'Gokul', 'in_range': True}, None, 0),
         ('Dessert display - evening', 'OK', {'unit': 'Dessert display', 'reading': 4.0, 'checked_by': 'Anjali', 'in_range': True}, None, 0)]),
}


def _knowledge(env):
    Article = env['knowledge.management.article'].sudo()
    admin = env.ref('base.user_admin')
    today = fields.Date.context_today(Article)
    now = fields.Datetime.now().replace(minute=0, second=0, microsecond=0)
    articles = {}
    for seq, (xid, parent_xid, name, icon, cover, favorite, full_width, body) in enumerate(
            _articles_spec(_company_name(env)), start=1):
        rec = _ref(env, xid)
        if not rec:
            vals = {
                'name': name, 'icon': icon, 'body_html': body, 'sequence': seq, 'visibility': 'workspace',
                'full_width': full_width,
            }
            if parent_xid:
                vals['parent_id'] = articles[parent_xid].id
            if cover:
                vals['cover_image_url'] = f'{IMG}/{cover}'
            if favorite:
                vals['favorite_user_ids'] = [Command.link(admin.id)]
            spec = ITEM_SPECS.get(xid)
            if spec:
                vals['article_properties_definition'] = spec[1]
            rec = _bind(env, xid, Article.create(vals))
        articles[xid] = rec

    for parent_xid, (stage_names, _definition, items) in ITEM_SPECS.items():
        parent = articles[parent_xid]
        stages = {}
        for i, sname in enumerate(stage_names, start=1):
            stages[sname] = _get_or_create(env, f'{parent_xid}_stage_{i}', 'knowledge.management.item.stage', {
                'name': sname, 'article_id': parent.id, 'sequence': i * 10, 'fold': i == len(stage_names) and i > 2,
            })
        for i, (name, sname, props, start, hours) in enumerate(items, start=1):
            xid = f'{parent_xid}_item_{i}'
            if _ref(env, xid):
                continue
            props = dict(props)
            if 'start_date' in props:
                props['start_date'] = fields.Date.to_string(today + timedelta(days=props['start_date']))
            vals = {
                'name': name, 'parent_id': parent.id, 'is_article_item': True, 'stage_id': stages[sname].id,
                'article_properties': props, 'sequence': i, 'visibility': parent.visibility,
            }
            if start is not None:
                begin = now.replace(hour=12) + timedelta(days=start)
                vals.update(item_date_start=begin, item_date_end=begin + timedelta(hours=hours))
            _bind(env, xid, Article.create(vals))


def load_knowledge_suite_demo_data(env):
    if 'knowledge.management.article' not in env:
        _logger.info("Hudson POS: Knowledge not installed, skipping Knowledge demo data.")
        return
    try:
        with env.cr.savepoint():
            _knowledge(env)
        _logger.info("Hudson POS: Knowledge articles demo data loaded.")
    except Exception as e:
        _logger.exception("Hudson POS: Knowledge demo data failed: %s", e)
