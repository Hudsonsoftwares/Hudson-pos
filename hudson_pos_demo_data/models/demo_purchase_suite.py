# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Purchase & Inventory demo data (Kerala suppliers, Kochi kitchen).

Builds on the Inventory suite (HINV- ingredients, vendors, locations, reordering rules) and adds,
idempotently (every record bound to an xmlid of this module, prefixes rc_pur_ / rc_inv_):
  * 6 Kerala suppliers (fish, dairy, spices, coffee, vegetables, packaging) with contacts
  * Kerala ingredients (seer fish, karimeen, pepper, cardamom, coconut oil, shallots...)
  * Vendor pricelists (product.supplierinfo) with price, lead time and minimum quantity,
    including alternative vendors on existing ingredients so the vendor comparison is meaningful
  * 13 purchase orders across every state: RFQ, RFQ sent, confirmed (on time and late),
    partially received with backorder, received, billed, billed & paid, cancelled
  * Physical inventory: applied stock counts (spoilage / recount) and counts still to apply
"""
import logging
from datetime import timedelta

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'


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


def _ago(days, hour=10):
    return fields.Datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days)


def _product(env, code_or_name):
    Product = env['product.product'].sudo().with_context(active_test=False)
    return (Product.search([('default_code', '=', code_or_name)], limit=1)
            or Product.search([('name', '=', code_or_name)], limit=1))


# --------------------------------------------------------------------------- master data
VENDORS = [
    # xid, name, street, city, phone, email, contact
    ('rc_pur_vnd_fish', 'Vypeen Harbour Fresh Catch', 'Fishing Harbour Road, Vypeen', 'Kochi', '+91 484 250 1188',
     'orders@vypeencatch.example', 'Joseph Antony'),
    ('rc_pur_vnd_dairy', 'Periyar Valley Dairy Co-operative', 'Edappally Industrial Estate', 'Kochi', '+91 484 280 4410',
     'supply@periyardairy.example', 'Lissy Varghese'),
    ('rc_pur_vnd_spice', 'Idukki Spice Growers Collective', 'Spice Park, Kumily', 'Idukki', '+91 486 922 2150',
     'trade@idukkispice.example', 'Biju Kurian'),
    ('rc_pur_vnd_coffee', 'Wayanad Highland Coffee Estates', 'Meppadi Estate Road', 'Wayanad', '+91 493 628 1777',
     'beans@wayanadcoffee.example', 'Sameer Ali'),
    ('rc_pur_vnd_veg', 'Aluva Farm Fresh Vegetables', 'Aluva Market Junction', 'Aluva', '+91 484 262 9003',
     'fresh@aluvafarm.example', 'Ramesh Babu'),
    ('rc_pur_vnd_pack', 'Kochi PackRight Supplies', 'Kalamassery Industrial Area', 'Kochi', '+91 484 254 7700',
     'sales@packright.example', 'Sneha Pillai'),
]

# xid, code, name, uom xmlid, cost, category ('ing'|'pkg')
NEW_PRODUCTS = [
    ('rc_pur_prod_seer', 'RC-ING-SEER', 'Seer Fish (Neymeen)', 'uom.product_uom_kgm', 9.5, 'ing'),
    ('rc_pur_prod_karimeen', 'RC-ING-KARI', 'Pearl Spot (Karimeen)', 'uom.product_uom_kgm', 11.0, 'ing'),
    ('rc_pur_prod_prawns', 'RC-ING-PRWN', 'Tiger Prawns', 'uom.product_uom_kgm', 14.0, 'ing'),
    ('rc_pur_prod_pepper', 'RC-ING-PEPR', 'Malabar Black Pepper', 'uom.product_uom_kgm', 7.2, 'ing'),
    ('rc_pur_prod_cardamom', 'RC-ING-CARD', 'Green Cardamom (8 mm bold)', 'uom.product_uom_kgm', 28.0, 'ing'),
    ('rc_pur_prod_coconut_oil', 'RC-ING-COIL', 'Cold-Pressed Coconut Oil', 'uom.product_uom_litre', 3.8, 'ing'),
    ('rc_pur_prod_coconut', 'RC-ING-COCO', 'Grated Coconut', 'uom.product_uom_kgm', 1.6, 'ing'),
    ('rc_pur_prod_shallots', 'RC-ING-SHAL', 'Shallots (Kunjulli)', 'uom.product_uom_kgm', 1.4, 'ing'),
    ('rc_pur_prod_curry_leaves', 'RC-ING-CURL', 'Curry Leaves', 'uom.product_uom_kgm', 2.0, 'ing'),
    ('rc_pur_prod_arabica', 'RC-ING-ARAB', 'Wayanad Arabica Beans (medium roast)', 'uom.product_uom_kgm', 15.5, 'ing'),
    ('rc_pur_prod_kraft_bag', 'RC-PKG-KBAG', 'Kraft Paper Carry Bag', 'uom.product_uom_unit', 0.12, 'pkg'),
    ('rc_pur_prod_banana_leaf', 'RC-PKG-BLEF', 'Banana Leaf (cut, for Sadya)', 'uom.product_uom_unit', 0.06, 'pkg'),
]

# vendor xid -> [(product code or name, price, delay days, min qty)]
PRICELISTS = {
    'rc_pur_vnd_fish': [('RC-ING-SEER', 9.1, 1, 5), ('RC-ING-KARI', 10.6, 1, 5), ('RC-ING-PRWN', 13.4, 1, 5),
                        ('HINV-ING-TUN', 12.1, 1, 10), ('HINV-ING-SALM', 21.0, 2, 5)],
    'rc_pur_vnd_dairy': [('HINV-ING-MILK', 1.42, 1, 50), ('HINV-ING-BUTR', 7.6, 2, 5), ('HINV-ING-CREM', 4.3, 1, 10),
                         ('HINV-ING-CCHS', 9.2, 3, 5), ('HINV-ING-EGGS', 0.27, 1, 120)],
    'rc_pur_vnd_spice': [('RC-ING-PEPR', 6.9, 4, 10), ('RC-ING-CARD', 27.0, 5, 2), ('RC-ING-COIL', 3.6, 3, 20)],
    'rc_pur_vnd_coffee': [('RC-ING-ARAB', 14.8, 5, 20), ('HINV-ING-COFF', 16.2, 5, 10), ('HINV-ING-GTEA', 21.5, 7, 5)],
    'rc_pur_vnd_veg': [('RC-ING-SHAL', 1.3, 1, 10), ('RC-ING-CURL', 1.9, 1, 2), ('RC-ING-COCO', 1.5, 1, 10),
                       ('HINV-ING-TOM', 2.6, 1, 10), ('HINV-ING-LET', 2.8, 1, 5), ('HINV-ING-BANA', 1.8, 1, 10)],
    'rc_pur_vnd_pack': [('RC-PKG-KBAG', 0.11, 3, 1000), ('RC-PKG-BLEF', 0.05, 1, 500), ('HINV-PKG-BOX', 0.31, 4, 500),
                        ('HINV-PKG-CUP', 0.16, 4, 1000), ('HINV-PKG-NAP', 0.035, 4, 2000)],
}

# xid, vendor (xid or existing vendor name), state, days ago, planned in days (from order date),
# buyer ('admin'|'arjun'), vendor ref, lines [(product, qty)], extras
ORDERS = [
    ('rc_pur_po_spice_rfq', 'rc_pur_vnd_spice', 'draft', 1, 5, 'admin', '',
     [('RC-ING-PEPR', 25), ('RC-ING-CARD', 4), ('RC-ING-COIL', 40)], {}),
    ('rc_pur_po_pack_rfq', 'rc_pur_vnd_pack', 'draft', 0, 4, 'arjun', '',
     [('RC-PKG-KBAG', 3000), ('HINV-PKG-BOX', 1500), ('RC-PKG-BLEF', 1000)], {'priority': True}),
    ('rc_pur_po_coffee_sent', 'rc_pur_vnd_coffee', 'sent', 4, 6, 'admin', 'WHC-QT-2231',
     [('RC-ING-ARAB', 40), ('HINV-ING-GTEA', 6)], {}),
    ('rc_pur_po_fish_sent', 'rc_pur_vnd_fish', 'sent', 1, 1, 'arjun', 'VHC-Q-0912',
     [('RC-ING-SEER', 30), ('RC-ING-KARI', 20), ('RC-ING-PRWN', 15)], {'note': 'Christmas Eve feast: deliver on ice before 7 AM.'}),
    ('rc_pur_po_dairy_open', 'rc_pur_vnd_dairy', 'purchase', 1, 2, 'admin', 'PVD-SO-7781',
     [('HINV-ING-MILK', 120), ('HINV-ING-BUTR', 10), ('HINV-ING-CREM', 15)], {}),
    ('rc_pur_po_veg_late', 'rc_pur_vnd_veg', 'purchase', 6, 2, 'arjun', 'AFF-5520',
     [('RC-ING-SHAL', 40), ('HINV-ING-TOM', 30), ('RC-ING-CURL', 5), ('RC-ING-COCO', 25)], {'priority': True}),
    ('rc_pur_po_coffee_partial', 'rc_pur_vnd_coffee', 'partial', 10, 5, 'admin', 'WHC-SO-2190',
     [('RC-ING-ARAB', 60), ('HINV-ING-COFF', 20)], {'receive_ratio': 0.6}),
    ('rc_pur_po_fish_received', 'rc_pur_vnd_fish', 'received', 3, 1, 'arjun', 'VHC-INV-0907',
     [('RC-ING-SEER', 25), ('HINV-ING-TUN', 12)], {}),
    ('rc_pur_po_spice_billed', 'rc_pur_vnd_spice', 'billed', 18, 4, 'admin', 'ISGC-1184',
     [('RC-ING-PEPR', 30), ('RC-ING-CARD', 5), ('RC-ING-COIL', 60)], {}),
    ('rc_pur_po_dairy_paid', 'rc_pur_vnd_dairy', 'paid', 40, 1, 'admin', 'PVD-SO-7432',
     [('HINV-ING-MILK', 150), ('HINV-ING-BUTR', 12), ('HINV-ING-EGGS', 360), ('HINV-ING-CCHS', 6)], {}),
    ('rc_pur_po_bev_paid', 'Roast & Sip Beverage Distributors', 'paid', 55, 2, 'arjun', 'RSB-88213',
     [('Coca-Cola', 240), ('Fanta', 120), ('Water', 480), ('HINV-ING-COFF', 15)], {}),
    ('rc_pur_po_bakery_paid', 'GoldenCrumb Bakery & Dairy Supplies', 'paid', 28, 3, 'admin', 'GCB-4471',
     [('HINV-ING-FLOUR', 100), ('HINV-ING-SUGR', 60), ('HINV-ING-DCHOC', 15), ('HINV-ING-BUN', 400)], {}),
    ('rc_pur_po_pack_cancel', 'rc_pur_vnd_pack', 'cancel', 22, 4, 'arjun', 'KPR-Q-0331',
     [('HINV-PKG-CUP', 5000)], {'reason': 'Cancelled: cups were 8 oz instead of the 12 oz we use for cold brew.'}),
]

# product code, location complete name, counted qty delta (applied) or None for pending count
COUNTS = [
    ('rc_inv_count_salmon', 'HINV-ING-SALM', -0.5, True, 'Spoilage: 0.5 kg salmon past use-by date discarded.'),
    ('rc_inv_count_milk', 'HINV-ING-MILK', -4, True, 'Weekly count: 4 L milk short (spillage).'),
    ('rc_inv_count_cups', 'HINV-PKG-CUP', 25, True, 'Recount found an unopened sleeve of 25 cups.'),
    ('rc_inv_count_eggs', 'HINV-ING-EGGS', -12, False, 'Count to verify: one tray reported broken.'),
    ('rc_inv_count_coffee', 'HINV-ING-COFF', -0.5, False, 'Monthly coffee count, waiting for manager approval.'),
]


def _vendors(env):
    india = env.ref('base.in', raise_if_not_found=False)
    res = {}
    for xid, name, street, city, phone, email, contact in VENDORS:
        existing = env['res.partner'].sudo().search([('name', '=', name), ('is_company', '=', True)], limit=1)
        if existing and not _ref(env, xid):
            _bind(env, xid, existing)
        vendor = _get_or_create(env, xid, 'res.partner', {
            'name': name, 'is_company': True, 'street': street, 'city': city, 'phone': phone, 'email': email,
            'country_id': india.id if india else False, 'supplier_rank': 1,
        })
        _get_or_create(env, f'{xid}_contact', 'res.partner', {
            'name': contact, 'parent_id': vendor.id, 'function': 'Sales Manager', 'email': email, 'phone': phone})
        res[xid] = vendor
    return res


def _products(env):
    Categ = env['product.category'].sudo()
    ing = Categ.search([('complete_name', '=', 'Resto / Ingredients')], limit=1) or Categ.search([('parent_id', '=', False)], limit=1)
    pkg = Categ.search([('complete_name', '=', 'Resto / Packaging')], limit=1) or ing
    tax = env.company.account_purchase_tax_id
    for xid, code, name, uom_xid, cost, cat in NEW_PRODUCTS:
        existing = _product(env, code)
        if existing and not _ref(env, xid):
            _bind(env, xid, existing.product_tmpl_id)
            continue
        uom = env.ref(uom_xid, raise_if_not_found=False) or env.ref('uom.product_uom_unit')
        _get_or_create(env, xid, 'product.template', {
            'name': name, 'default_code': code, 'type': 'consu', 'is_storable': True, 'uom_id': uom.id,
            'standard_price': cost, 'list_price': 0, 'sale_ok': False, 'purchase_ok': True,
            'available_in_pos': False, 'categ_id': (ing if cat == 'ing' else pkg).id,
            'supplier_taxes_id': [Command.set(tax.ids)],
        })


def _pricelists(env, vendors):
    for vxid, rows in PRICELISTS.items():
        vendor = vendors[vxid]
        for code, price, delay, min_qty in rows:
            product = _product(env, code)
            if not product:
                continue
            xid = f'rc_pur_si_{vxid[11:]}_{code.replace("-", "_").lower()}'
            _get_or_create(env, xid, 'product.supplierinfo', {
                'partner_id': vendor.id, 'product_tmpl_id': product.product_tmpl_id.id, 'price': price,
                'delay': delay, 'min_qty': min_qty, 'product_code': f'{vendor.name[:3].upper()}-{code[-4:]}',
            })


def _vendor(env, vendors, key):
    if key in vendors:
        return vendors[key]
    return env['res.partner'].sudo().search([('name', '=', key)], limit=1)


def _buyer(env, key):
    return (_ref(env, 'rc_user_arjun') if key == 'arjun' else None) or env.ref('base.user_admin')


def _receive(po, ratio=1.0, when=None):
    for picking in po.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')):
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty * ratio
            move.picked = True
        picking.with_context(skip_sms=True)._action_done()
        if when:
            picking.date_done = when
            picking.move_ids.filtered(lambda m: m.state == 'done').write({'date': when})
            picking.move_ids.move_line_ids.write({'date': when})


def _bill(env, po, when):
    po.action_create_invoice()
    bill = po.invoice_ids.filtered(lambda m: m.state == 'draft')[:1]
    if not bill:
        return False
    bill.write({'invoice_date': when.date(), 'ref': po.partner_ref or po.name})
    bill.action_post()
    return bill


def _pay(env, bill, when):
    env['account.payment.register'].sudo().with_context(active_model='account.move', active_ids=bill.ids).create(
        {'payment_date': when.date()})._create_payments()


def _create_po(env, vendors, spec):
    xid, vkey, state, days, planned_in, buyer_key, vref, lines, extra = spec
    if _ref(env, xid):
        return
    vendor = _vendor(env, vendors, vkey)
    if not vendor:
        return
    buyer = _buyer(env, buyer_key)
    date_order = _ago(days)
    date_planned = date_order + timedelta(days=planned_in)
    line_vals = []
    for code, qty in lines:
        product = _product(env, code)
        if not product:
            continue
        seller = env['product.supplierinfo'].sudo().search([
            ('partner_id', '=', vendor.id), ('product_tmpl_id', '=', product.product_tmpl_id.id),
            ('min_qty', '<=', qty)], order='min_qty desc, price', limit=1)
        line_vals.append(Command.create({
            'product_id': product.id, 'product_qty': qty, 'date_planned': date_planned,
            'price_unit': seller.price if seller else product.standard_price,
        }))
    if not line_vals:
        return
    po = env['purchase.order'].sudo().with_context(mail_create_nosubscribe=True, tracking_disable=True).create({
        'partner_id': vendor.id, 'user_id': buyer.id, 'date_order': date_order, 'date_planned': date_planned,
        'partner_ref': vref or False, 'priority': '1' if extra.get('priority') else '0',
        'note': extra.get('note') or False, 'order_line': line_vals,
    })
    _bind(env, xid, po)

    if state == 'sent':
        po.write({'state': 'sent'})
        po.message_post(body=f"Request for quotation sent to {vendor.name}.", message_type='comment',
                        subtype_xmlid='mail.mt_note')
    elif state == 'cancel':
        po.write({'state': 'sent'})
        po.button_cancel()
        po.message_post(body=extra.get('reason', 'Cancelled.'), message_type='comment', subtype_xmlid='mail.mt_note')
    elif state in ('purchase', 'partial', 'received', 'billed', 'paid'):
        po.button_confirm()
        po.write({'date_approve': date_order + timedelta(hours=2), 'date_order': date_order})
        po.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')).write({'scheduled_date': date_planned})
        received_on = min(date_planned, fields.Datetime.now())
        if state == 'partial':
            _receive(po, extra.get('receive_ratio', 0.5), received_on)
            backorder = po.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel'))
            backorder.write({'scheduled_date': fields.Datetime.now() + timedelta(days=3)})
            po.message_post(body="Partial delivery: the estate shipped the rest with the next roast batch.",
                            message_type='comment', subtype_xmlid='mail.mt_note')
        elif state in ('received', 'billed', 'paid'):
            _receive(po, 1.0, received_on)
            if state in ('billed', 'paid'):
                bill = _bill(env, po, received_on + timedelta(days=1))
                if bill and state == 'paid':
                    _pay(env, bill, received_on + timedelta(days=10))


def _counts(env):
    Quant = env['stock.quant'].sudo()
    warehouse = env['stock.warehouse'].sudo().search([('company_id', '=', env.company.id)], limit=1)
    stock = warehouse.lot_stock_id
    for xid, code, delta, apply, note in COUNTS:
        if _ref(env, xid):
            continue
        product = _product(env, code)
        if not product:
            continue
        quant = Quant.search([('product_id', '=', product.id), ('location_id', 'child_of', stock.id),
                              ('quantity', '>', abs(delta) if delta < 0 else 0)], order='quantity desc', limit=1)
        if not quant:
            continue
        quant.with_context(inventory_mode=True).write({
            'inventory_quantity': quant.quantity + delta, 'user_id': env.ref('base.user_admin').id,
            'inventory_date': fields.Date.today(),
        })
        _bind(env, xid, quant)
        if apply:
            quant.with_context(inventory_name=note, inventory_mode=True).action_apply_inventory()


# --------------------------------------------------------------------------- entry point
def load_purchase_suite_demo_data(env):
    if 'purchase.order' not in env:
        _logger.info("Hudson POS: Purchase not installed, skipping Purchase demo data.")
        return
    ctx = {}
    steps = [
        ('vendors', lambda: ctx.update(vendors=_vendors(env))),
        ('products', lambda: _products(env)),
        ('vendor pricelists', lambda: _pricelists(env, ctx['vendors'])),
    ]
    for name, step in steps:
        try:
            with env.cr.savepoint():
                step()
        except Exception as e:
            _logger.exception("Hudson POS: Purchase demo step '%s' failed: %s", name, e)
            if name == 'vendors':
                return
    for spec in ORDERS:
        try:
            with env.cr.savepoint():
                _create_po(env, ctx['vendors'], spec)
        except Exception as e:
            _logger.exception("Hudson POS: Purchase demo order %s failed: %s", spec[0], e)
    try:
        with env.cr.savepoint():
            _counts(env)
    except Exception as e:
        _logger.exception("Hudson POS: Inventory count demo data failed: %s", e)
    _logger.info("Hudson POS: Resto Cafe Purchase & Inventory demo data loaded.")
