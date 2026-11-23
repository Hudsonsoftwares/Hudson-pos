# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Purchase Templates, Alternatives and Blanket Orders demo data.

Only standard Odoo 20 models are used; nothing is added to the Purchase functionality:
  * Purchase Templates (``purchase.requisition``, type ``purchase_template``, module Purchase Agreements):
      - Café Food Supplies
      - Restaurant Kitchen Supplies
      - Beverage & Packaging Supplies
    plus one RFQ created from the Café Food Supplies template.
  * Purchase Alternatives (``purchase.order.group``, module Purchase Alternative), built ONLY from the
    existing Purchase/Inventory demo vendors and products (nothing new is created): 4 calls for tender
    (café dairy, espresso beans & tea, sushi/grill fish, salad produce), each a main RFQ plus an
    alternative RFQ with the same products and quantities; prices and expected arrival come from each
    vendor's existing price and lead time, so Alternatives -> Compare Product Lines -> Choose shows
    real differences (cheaper vs faster, and a group where each vendor wins a different line).
  * Blanket Order (``purchase.requisition``, type ``blanket_order``): Kerala Food Suppliers,
    100 kg Basmati Rice at ₹120/kg, confirmed, with two releases: 40 kg confirmed, 30 kg left as RFQ,
    30 kg still open on the agreement.

The Kerala vendors are billed in Indian Rupees (standard vendor purchase currency). When the company
currency is USD, INR is activated and given an exchange rate if it has none.

Each part only loads when its Odoo module is installed; installing Purchase Agreements or Purchase
Alternative later reloads this suite (see demo_autoloader). All records are bound to xmlids
(prefix rc_pa_), so loading again never creates duplicates.
"""
import logging
from datetime import date, timedelta

from odoo import Command, fields

from .demo_guard import unguarded
from .demo_purchase_suite import _ago, _bind, _buyer, _get_or_create, _product, _ref

_logger = logging.getLogger(__name__)

INR_PER_USD = 84.0

# xid, name, street, city, phone, email, contact
VENDORS = [
    ('rc_pa_vnd_cafe', 'Kochi Café Wholesale Mart', 'Broadway, Ernakulam', 'Kochi', '+91 484 236 4410',
     'orders@kochicafemart.example', 'Anitha Menon'),
    ('rc_pa_vnd_provisions', 'Ernakulam Wholesale Provisions', 'Market Road, Ernakulam', 'Kochi',
     '+91 484 237 1290', 'sales@ekmprovisions.example', 'Shaji Thomas'),
    ('rc_pa_vnd_bev', 'Cochin Beverage & Pack Distributors', 'Kakkanad Industrial Area', 'Kochi',
     '+91 484 242 8800', 'supply@cochinbevpack.example', 'Faisal Rahman'),
    ('rc_pa_vnd_kfs', 'Kerala Food Suppliers', 'Shakthan Nagar', 'Thrissur', '+91 487 244 7020',
     'orders@keralafoods.example', 'Priya Nair'),
]

# xid, code, name, uom xmlid, cost (INR), category ('ing'|'pkg'), existing product code reused when present
PRODUCTS = [
    ('rc_pa_prod_coffee', 'RC-PA-COFB', 'Premium Coffee Beans – 1 KG', 'uom.product_uom_kgm', 780, 'ing', None),
    ('rc_pa_prod_rice', 'RC-PA-BASM', 'Basmati Rice', 'uom.product_uom_kgm', 120, 'ing', None),
    ('rc_pa_prod_milk', 'RC-PA-MILK', 'Fresh Toned Milk', 'uom.product_uom_litre', 56, 'ing', 'HINV-ING-MILK'),
    ('rc_pa_prod_cream', 'RC-PA-CREM', 'Whipping Cream', 'uom.product_uom_litre', 340, 'ing', 'HINV-ING-CREM'),
    ('rc_pa_prod_sugar', 'RC-PA-BSUG', 'Brown Sugar', 'uom.product_uom_kgm', 62, 'ing', None),
    ('rc_pa_prod_choc_syrup', 'RC-PA-CHSY', 'Chocolate Syrup – 1 L Bottle', 'uom.product_uom_unit', 450, 'ing', None),
    ('rc_pa_prod_van_syrup', 'RC-PA-VNSY', 'Vanilla Syrup – 1 L Bottle', 'uom.product_uom_unit', 420, 'ing', None),
    ('rc_pa_prod_sun_oil', 'RC-PA-SOIL', 'Refined Sunflower Oil – 15 L Tin', 'uom.product_uom_unit', 2150, 'ing', None),
    ('rc_pa_prod_dal', 'RC-PA-TDAL', 'Toor Dal', 'uom.product_uom_kgm', 145, 'ing', None),
    ('rc_pa_prod_onion', 'RC-PA-ONIO', 'Onions', 'uom.product_uom_kgm', 38, 'ing', None),
    ('rc_pa_prod_chicken', 'RC-PA-CHKN', 'Chicken – Curry Cut', 'uom.product_uom_kgm', 240, 'ing', None),
    ('rc_pa_prod_garam', 'RC-PA-GRMS', 'Garam Masala', 'uom.product_uom_kgm', 680, 'ing', None),
    ('rc_pa_prod_water', 'RC-PA-WATR', 'Packaged Drinking Water 1 L – Case of 12', 'uom.product_uom_unit', 216, 'pkg', None),
    ('rc_pa_prod_soda', 'RC-PA-SODA', 'Soda 300 ml – Crate of 24', 'uom.product_uom_unit', 480, 'pkg', None),
    ('rc_pa_prod_juice', 'RC-PA-OJUI', 'Orange Juice 1 L Tetra Pack', 'uom.product_uom_unit', 110, 'pkg', None),
    ('rc_pa_prod_cup', 'RC-PA-CUP', 'Paper Cup 250 ml', 'uom.product_uom_unit', 1.6, 'pkg', 'HINV-PKG-CUP'),
    ('rc_pa_prod_box', 'RC-PA-BOX', 'Takeaway Food Box', 'uom.product_uom_unit', 6.5, 'pkg', 'HINV-PKG-BOX'),
    ('rc_pa_prod_straw', 'RC-PA-STRW', 'Paper Straws', 'uom.product_uom_unit', 0.9, 'pkg', None),
]

# vendor xid -> [(product xid, price INR, lead time days, min qty)]
PRICELISTS = {
    'rc_pa_vnd_cafe': [('rc_pa_prod_coffee', 790, 3, 5), ('rc_pa_prod_milk', 56, 1, 50), ('rc_pa_prod_cream', 340, 1, 5),
                       ('rc_pa_prod_sugar', 62, 2, 10), ('rc_pa_prod_choc_syrup', 450, 3, 3),
                       ('rc_pa_prod_van_syrup', 420, 3, 3)],
    'rc_pa_vnd_provisions': [('rc_pa_prod_rice', 125, 2, 25), ('rc_pa_prod_sun_oil', 2150, 2, 2),
                             ('rc_pa_prod_dal', 145, 2, 10), ('rc_pa_prod_onion', 38, 1, 20),
                             ('rc_pa_prod_chicken', 240, 1, 10), ('rc_pa_prod_garam', 680, 3, 1)],
    'rc_pa_vnd_bev': [('rc_pa_prod_water', 216, 2, 10), ('rc_pa_prod_soda', 480, 2, 5), ('rc_pa_prod_juice', 110, 3, 12),
                      ('rc_pa_prod_cup', 1.6, 4, 1000), ('rc_pa_prod_box', 6.5, 4, 500),
                      ('rc_pa_prod_straw', 0.9, 4, 1000)],
}

# xid, template name, vendor xid, reference, description, lines [(product xid, qty, price INR)]
TEMPLATES = [
    ('rc_pa_tmpl_cafe', 'Café Food Supplies', 'rc_pa_vnd_cafe', 'Café Food Supplies',
     '<p>Weekly café counter replenishment: coffee beans, dairy, sugar and syrups for the espresso bar.</p>',
     [('rc_pa_prod_coffee', 10, 790), ('rc_pa_prod_milk', 100, 56), ('rc_pa_prod_cream', 10, 340),
      ('rc_pa_prod_sugar', 20, 62), ('rc_pa_prod_choc_syrup', 6, 450), ('rc_pa_prod_van_syrup', 6, 420)]),
    ('rc_pa_tmpl_kitchen', 'Restaurant Kitchen Supplies', 'rc_pa_vnd_provisions', 'Restaurant Kitchen Supplies',
     '<p>Weekly main-kitchen staples: rice, oil, dal, onions, chicken and spices for the lunch &amp; dinner menu.</p>',
     [('rc_pa_prod_rice', 50, 125), ('rc_pa_prod_sun_oil', 4, 2150), ('rc_pa_prod_dal', 25, 145),
      ('rc_pa_prod_onion', 60, 38), ('rc_pa_prod_chicken', 30, 240), ('rc_pa_prod_garam', 2, 680)]),
    ('rc_pa_tmpl_bev_pack', 'Beverage & Packaging Supplies', 'rc_pa_vnd_bev', 'Beverage & Packaging Supplies',
     '<p>Fortnightly cold beverages and takeaway packaging for dine-in, takeaway and delivery orders.</p>',
     [('rc_pa_prod_water', 40, 216), ('rc_pa_prod_soda', 10, 480), ('rc_pa_prod_juice', 24, 110),
      ('rc_pa_prod_cup', 2000, 1.6), ('rc_pa_prod_box', 1000, 6.5), ('rc_pa_prod_straw', 2000, 0.9)]),
]


# --------------------------------------------------------------------------- master data
def _inr(env):
    """INR when the vendors can be billed in rupees with a correct conversion, else False."""
    company = env.company
    inr = env.ref('base.INR', raise_if_not_found=False)
    if not inr:
        return False
    if company.currency_id == inr:
        return inr
    if company.currency_id.name != 'USD':
        return False  # no reliable rate to company currency: keep the company currency
    if not inr.active:
        # enabling a currency changes no user data: done outside the demo guard (demo_guard.py),
        # which would otherwise skip the write because base.INR exists before the demo run
        with unguarded():
            inr.sudo().write({'active': True})
    Rate = env['res.currency.rate'].sudo()
    if not Rate.search_count([('currency_id', '=', inr.id), ('company_id', 'in', (company.id, False))]):
        _get_or_create(env, 'rc_pa_rate_inr', 'res.currency.rate', {
            'currency_id': inr.id, 'company_id': company.id, 'name': date(2025, 1, 1), 'rate': INR_PER_USD})
    return inr


def _vendors(env, currency):
    india = env.ref('base.in', raise_if_not_found=False)
    res = {}
    for xid, name, street, city, phone, email, contact in VENDORS:
        existing = env['res.partner'].sudo().search([('name', '=', name), ('is_company', '=', True)], limit=1)
        if existing and not _ref(env, xid):
            _bind(env, xid, existing)
        vals = {
            'name': name, 'is_company': True, 'street': street, 'city': city, 'phone': phone, 'email': email,
            'country_id': india.id if india else False, 'supplier_rank': 1,
        }
        if currency and currency != env.company.currency_id:
            vals['property_purchase_currency_id'] = currency.id  # standard vendor purchase currency
        vendor = _get_or_create(env, xid, 'res.partner', vals)
        _get_or_create(env, f'{xid}_contact', 'res.partner', {
            'name': contact, 'parent_id': vendor.id, 'function': 'Sales Manager', 'email': email, 'phone': phone})
        res[xid] = vendor
    return res


def _products(env, currency):
    """product xid -> product.product (existing restaurant ingredients are reused, never duplicated)."""
    Categ = env['product.category'].sudo()
    ing = (Categ.search([('complete_name', '=', 'Resto / Ingredients')], limit=1)
           or Categ.search([('parent_id', '=', False)], limit=1))
    pkg = Categ.search([('complete_name', '=', 'Resto / Packaging')], limit=1) or ing
    Tmpl = env['product.template']
    tax = env.company.account_purchase_tax_id
    company_cur = env.company.currency_id
    res = {}
    for xid, code, name, uom_xid, cost, cat, reuse in PRODUCTS:
        tmpl = _ref(env, xid)
        if not (tmpl and tmpl.exists()):
            existing = (_product(env, reuse) if reuse else False) or _product(env, code)
            if existing:
                tmpl = _bind(env, xid, existing.product_tmpl_id)
            else:
                uom = env.ref(uom_xid, raise_if_not_found=False) or env.ref('uom.product_uom_unit')
                vals = {
                    'name': name, 'default_code': code, 'type': 'consu', 'uom_id': uom.id,
                    'standard_price': currency._convert(cost, company_cur, env.company, fields.Date.today())
                    if currency and currency != company_cur else cost,
                    'list_price': 0, 'sale_ok': False, 'purchase_ok': True, 'categ_id': (ing if cat == 'ing' else pkg).id,
                    'supplier_taxes_id': [Command.set(tax.ids)],
                }
                if 'is_storable' in Tmpl._fields:
                    vals['is_storable'] = True
                if 'available_in_pos' in Tmpl._fields:
                    vals['available_in_pos'] = False
                tmpl = _bind(env, xid, Tmpl.sudo().create(vals))
        res[xid] = tmpl.product_variant_id
    return res


def _pricelists(env, vendors, products, currency):
    for vxid, rows in PRICELISTS.items():
        vendor = vendors[vxid]
        for pxid, price, delay, min_qty in rows:
            product = products.get(pxid)
            if not product:
                continue
            vals = {
                'partner_id': vendor.id, 'product_tmpl_id': product.product_tmpl_id.id, 'price': price,
                'delay': delay, 'min_qty': min_qty,
                'product_code': f'{vendor.name[:3].upper()}-{(product.default_code or "")[-4:]}',
            }
            if currency:
                vals['currency_id'] = currency.id
            _get_or_create(env, f'rc_pa_si_{vxid[9:]}_{pxid[11:]}', 'product.supplierinfo', vals)


# --------------------------------------------------------------------------- orders
def _po_lines_from_agreement(agreement, qty_by_product=None, date_planned=None):
    """Purchase order lines prepared by the agreement lines exactly as Odoo does (_prepare_purchase_order_line)."""
    lines = []
    for line in agreement.line_ids.filtered(lambda l: not l.display_type):
        qty = qty_by_product.get(line.product_id.id, 0) if qty_by_product is not None else line.product_qty
        if not qty:
            continue
        vals = line._prepare_purchase_order_line(
            name=line.product_id.display_name, product_qty=qty, price_unit=line.price_unit,
            taxes_ids=line.product_id.supplier_taxes_id.filtered(
                lambda t: t.company_id in agreement.company_id.parent_ids).ids)
        if date_planned:
            vals['date_planned'] = date_planned
        lines.append(Command.create(vals))
    return lines


def _create_po(env, xid, vals, state='draft', days=0):
    po = _ref(env, xid)
    if po and po.exists():
        return po
    date_order = _ago(days)
    po = env['purchase.order'].sudo().with_context(mail_create_nosubscribe=True).create(
        dict(vals, date_order=date_order))
    _bind(env, xid, po)
    if state == 'sent':
        po.write({'state': 'sent'})
        po.message_post(body=f"Request for quotation sent to {po.partner_id.name}.", message_type='comment',
                        subtype_xmlid='mail.mt_note')
    elif state == 'purchase':
        po.with_context(skip_alternative_check=True).button_confirm()
        po.write({'date_approve': date_order + timedelta(hours=2), 'date_order': date_order})
    return po


def _templates(env, vendors, products):
    agreements = {}
    for xid, name, vxid, reference, description, lines in TEMPLATES:
        agreement = _ref(env, xid)
        if not (agreement and agreement.exists()):
            line_vals = [Command.create({'product_id': products[p].id, 'product_qty': qty, 'price_unit': price})
                         for p, qty, price in lines if products.get(p)]
            agreement = env['purchase.requisition'].sudo().create({
                'requisition_type': 'purchase_template', 'vendor_id': vendors[vxid].id, 'reference': reference,
                'description': description, 'user_id': _buyer(env, 'admin').id, 'line_ids': line_vals,
            })
            _bind(env, xid, agreement)
            agreement.action_confirm()
        agreements[xid] = agreement

    # one RFQ created from the Café Food Supplies template
    cafe = agreements['rc_pa_tmpl_cafe']
    _create_po(env, 'rc_pa_po_from_tmpl_cafe', {
        'partner_id': cafe.vendor_id.id, 'requisition_id': cafe.id, 'origin': cafe.name,
        'user_id': _buyer(env, 'arjun').id, 'note': cafe.description,
        'order_line': _po_lines_from_agreement(cafe, date_planned=_ago(-3)),
    }, state='draft', days=0)


# Alternative RFQs built ONLY from the existing Purchase / Inventory demo data: the vendors and products
# below come from demo_purchase_suite (rc_pur_vnd_*) and demo_inventory_suite (HINV-VND-* vendors,
# HINV-ING-* products), and every product already has a vendor price (product.supplierinfo) for each
# vendor of its group. Price and expected arrival are therefore not hard-coded: Odoo fills them from
# each vendor's existing price and lead time, exactly as when a buyer creates the RFQ.
#   group xid, purpose, [(RFQ xid, vendor xmlid or HINV vendor reference, state, vendor ref)], [(product code, qty)]
# The first RFQ of each group is the main RFQ; the others are its alternatives (purchase.order.group).
ALTERNATIVE_GROUPS = [
    ('rc_pa_alt_dairy', 'Weekly café dairy: milk, butter, cream, cream cheese and eggs for the espresso bar and bakery.',
     [('rc_pa_po_alt_dairy_main', 'rc_pur_vnd_dairy', 'sent', 'PVD-QT-7810'),
      ('rc_pa_po_alt_dairy_alt', 'HINV-VND-BAKERY', 'draft', 'GCB-Q-4502')],
     [('HINV-ING-MILK', 100), ('HINV-ING-BUTR', 10), ('HINV-ING-CREM', 15), ('HINV-ING-CCHS', 6), ('HINV-ING-EGGS', 240)]),
    ('rc_pa_alt_coffee', 'Espresso bar restock: espresso beans and green tea - cheaper estate supply vs faster distributor.',
     [('rc_pa_po_alt_coffee_main', 'rc_pur_vnd_coffee', 'sent', 'WHC-QT-2240'),
      ('rc_pa_po_alt_coffee_alt', 'HINV-VND-BEVERAGE', 'draft', 'RSB-Q-8830')],
     [('HINV-ING-COFF', 20), ('HINV-ING-GTEA', 5)]),
    ('rc_pa_alt_seafood', 'Sushi & grill fish: each vendor is cheaper on a different line - choose line by line.',
     [('rc_pa_po_alt_seafood_main', 'rc_pur_vnd_fish', 'draft', ''),
      ('rc_pa_po_alt_seafood_alt', 'HINV-VND-SEAFOOD', 'draft', 'NSC-Q-1290')],
     [('HINV-ING-TUN', 12), ('HINV-ING-SALM', 6)]),
    ('rc_pa_alt_produce', 'Salad & dessert produce for the weekend menu.',
     [('rc_pa_po_alt_produce_main', 'rc_pur_vnd_veg', 'draft', ''),
      ('rc_pa_po_alt_produce_alt', 'HINV-VND-PRODUCE', 'draft', 'GLP-Q-0715')],
     [('HINV-ING-TOM', 20), ('HINV-ING-LET', 10), ('HINV-ING-BANA', 20)]),
]


def _existing_vendor(env, key):
    """Existing demo vendor: xmlid of the Purchase suite, or reference of an Inventory suite vendor."""
    vendor = _ref(env, key)
    if vendor:
        return vendor
    return env['res.partner'].sudo().with_context(active_test=False).search([('ref', '=', key)], limit=1)


def _alternatives(env, *_args):
    """Main RFQ + alternative RFQs per group, reusing existing vendors/products only (nothing created)."""
    for gxid, purpose, rfqs, lines in ALTERNATIVE_GROUPS:
        vendors = [_existing_vendor(env, vkey) for _x, vkey, _s, _r in rfqs]
        products = [(_product(env, code), qty) for code, qty in lines]
        if not all(vendors) or not all(p for p, _q in products):
            _logger.info("Hudson POS: purchase alternatives '%s' skipped: its existing vendors/products are missing.", gxid)
            continue
        # only when every vendor of the group already sells every product (existing vendor prices)
        if not all(p.seller_ids.filtered(lambda s: s.partner_id == v) for v in vendors for p, _q in products):
            _logger.info("Hudson POS: purchase alternatives '%s' skipped: a vendor has no price for a product.", gxid)
            continue
        orders = env['purchase.order']
        for n, ((xid, _vkey, state, ref), vendor) in enumerate(zip(rfqs, vendors)):
            order = _create_po(env, xid, {
                'partner_id': vendor.id, 'partner_ref': ref or False, 'user_id': _buyer(env, 'admin').id,
                'origin': 'Call for tender' if n == 0 else 'Alternative RFQ',
                'note': purpose,
                # price_unit and date_planned are computed from the vendor's existing price & lead time
                'order_line': [Command.create({'product_id': p.id, 'product_qty': qty}) for p, qty in products],
            }, state=state, days=0)  # dated today: expected arrivals = today + each vendor's lead time
            orders |= order
        groups = orders.purchase_group_id
        if not groups:
            env['purchase.order.group'].sudo().create({'order_ids': [Command.set(orders.ids)]})
        elif len(groups) == 1 and orders - groups.order_ids:
            groups.sudo().order_ids |= orders


def _blanket_order(env, vendors, products):
    rice = products['rc_pa_prod_rice']
    vendor = vendors['rc_pa_vnd_kfs']
    blanket = _ref(env, 'rc_pa_blanket_rice')
    if not (blanket and blanket.exists()):
        blanket = env['purchase.requisition'].sudo().create({
            'requisition_type': 'blanket_order', 'vendor_id': vendor.id, 'reference': 'KFS-BO-2026-11',
            'date_start': fields.Date.today() - timedelta(days=15), 'date_end': fields.Date.today() + timedelta(days=75),
            'user_id': _buyer(env, 'admin').id,
            'description': '<p>Quarterly agreement: 100 kg Basmati Rice at ₹120/kg, released in batches '
                           'as the kitchen needs it.</p>',
            'line_ids': [Command.create({'product_id': rice.id, 'product_qty': 100, 'price_unit': 120})],
        })
        _bind(env, 'rc_pa_blanket_rice', blanket)
        blanket.action_confirm()

    # Release 1: 40 kg, confirmed - Release 2: 30 kg, still an RFQ - 30 kg remain on the agreement
    # (xid, qty, state, ordered days ago, delivery in days from today, vendor reference)
    for xid, qty, state, days, deliver_in, ref in (
            ('rc_pa_po_blanket_rel1', 40, 'purchase', 5, 2, 'KFS-SO-5521'),
            ('rc_pa_po_blanket_rel2', 30, 'draft', 1, 10, False)):
        _create_po(env, xid, {
            'partner_id': vendor.id, 'requisition_id': blanket.id, 'origin': blanket.name, 'partner_ref': ref,
            'user_id': _buyer(env, 'admin').id,
            'order_line': _po_lines_from_agreement(blanket, {rice.id: qty}, date_planned=_ago(-deliver_in)),
        }, state=state, days=days)


# --------------------------------------------------------------------------- entry point
def load_purchase_agreements_suite_demo_data(env):
    has_agreements = 'purchase.requisition' in env and 'requisition_type' in env['purchase.requisition']._fields
    has_alternatives = 'purchase.order.group' in env
    if 'purchase.order' not in env or not (has_agreements or has_alternatives):
        _logger.info("Hudson POS: Purchase Agreements / Alternative not installed, skipping their demo data.")
        return
    ctx = {'vendors': {}, 'products': {}}
    # Vendors/products of the Purchase Templates & Blanket Order: only with Purchase Agreements.
    # The alternatives reuse the existing Purchase/Inventory demo vendors and products instead.
    if has_agreements:
        try:
            with env.cr.savepoint():
                currency = _inr(env)
                ctx['vendors'] = _vendors(env, currency)
                ctx['products'] = _products(env, currency)
                _pricelists(env, ctx['vendors'], ctx['products'], currency)
        except Exception as e:
            _logger.exception("Hudson POS: Purchase agreements master data failed: %s", e)
            has_agreements = False
    steps = []
    if has_agreements:
        steps += [('purchase templates', _templates), ('blanket order', _blanket_order)]
    if has_alternatives:
        steps.append(('purchase alternatives', _alternatives))
    for name, step in steps:
        try:
            with env.cr.savepoint():
                step(env, ctx['vendors'], ctx['products'])
        except Exception as e:
            _logger.exception("Hudson POS: Purchase agreements demo step '%s' failed: %s", name, e)
    _logger.info("Hudson POS: Purchase templates, alternatives and blanket order demo data loaded.")
