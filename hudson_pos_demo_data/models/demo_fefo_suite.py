# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - FEFO (First Expiry First Out) showcase.

Needs the "Expiration Dates" feature (product_expiry); loaded automatically once it is installed.
Idempotent: every record is bound to an xmlid of this module (prefix rc_fefo_), so the
generic demo cleanup removes it on uninstall.

  1. Category "Perishables (FEFO)"   Force Removal Strategy = First Expiry First Out
  2. Location "Perishables Chiller"   removal strategy FEFO (the location-level way to set it)
  3. Products with expiration dates   expiration / best-before / removal / alert times per product
  4. Lots received out of expiry order  a batch received LATER expires EARLIER, plus an expired lot
                                        and lots inside their alert period
  5. Deliveries                       a validated delivery and a reserved one: Odoo reserved the
                                       lots expiring first (not the oldest received) and skipped
                                       the expired lot
  6. Purchases (with Purchase)        dairy vendor 'Kochi Fresh Dairy Farms' with vendor prices; Greek
                                       Yogurt, Fresh Cream and Paneer bought in several lots of the same
                                       product with different expiration dates: 2 received POs, a receipt
                                       ready to validate with lots pre-entered, a draft RFQ; the expired
                                       cream lot is scrapped (Spoilage / Expiry); a reserved delivery takes
                                       the purchased lots by expiry date; 'Alert Date Reached' activities
"""
import logging
from datetime import timedelta

from odoo import Command, fields

from .demo_inventory_features_suite import _ref, _bind, _get_or_create, _ago, _uom, _html, _note, _put_stock

_logger = logging.getLogger(__name__)

# xid, code, name, uom (xmlid, name), cost, sale price,
# (expiration_time, use_time, removal_time, alert_time) in days
FEFO_PRODUCTS = [
    ('rc_fefo_prod_mozzarella', 'RC-FEFO-MOZZ', 'Buffalo Mozzarella 250 g', ('uom.product_uom_unit', 'Units'),
     2.4, 4.5, (14, 4, 2, 5)),
    ('rc_fefo_prod_orange_juice', 'RC-FEFO-OJ1L', 'Cold-Pressed Orange Juice 1 L', ('uom.product_uom_unit', 'Units'),
     1.8, 3.9, (7, 2, 1, 2)),
    ('rc_fefo_prod_butter', 'RC-FEFO-BUTR', 'Salted Butter 500 g', ('uom.product_uom_unit', 'Units'),
     3.1, 5.2, (60, 10, 5, 14)),
    ('rc_fefo_prod_salmon', 'RC-FEFO-SALM', 'Smoked Salmon Slices 200 g', ('uom.product_uom_unit', 'Units'),
     6.8, 11.5, (21, 3, 2, 5)),
    ('rc_fefo_prod_mousse', 'RC-FEFO-MOUS', 'Chocolate Mousse Cup', ('uom.product_uom_unit', 'Units'),
     0.9, 2.5, (5, 1, 1, 2)),
    ('rc_fefo_prod_bread', 'RC-FEFO-BRED', 'Multigrain Sourdough Loaf', ('uom.product_uom_unit', 'Units'),
     1.2, 3.0, (4, 1, 1, 1)),
    # bought from the dairy vendor: every lot comes in through a purchase receipt (section 6)
    ('rc_fefo_prod_yogurt', 'RC-FEFO-YOGT', 'Greek Yogurt 500 g', ('uom.product_uom_unit', 'Units'),
     1.6, 3.2, (21, 5, 3, 7)),
    ('rc_fefo_prod_cream', 'RC-FEFO-CREM', 'Fresh Dairy Cream 1 L', ('uom.product_uom_unit', 'Units'),
     2.2, 4.0, (10, 3, 2, 3)),
    ('rc_fefo_prod_paneer', 'RC-FEFO-PANR', 'Fresh Paneer 1 kg', ('uom.product_uom_unit', 'Units'),
     3.5, 6.5, (7, 2, 1, 2)),
]

PURCHASED_PRODUCTS = ('rc_fefo_prod_yogurt', 'rc_fefo_prod_cream', 'rc_fefo_prod_paneer')

DAIRY_VENDOR = ('rc_fefo_vendor_dairy', 'Kochi Fresh Dairy Farms')

# Purchase orders of the dairy vendor. Each receipt line is split into lots carrying the
# expiration date printed by the vendor, so one product holds several lots with different dates.
# xid, partner ref, ordered days ago, state ('done' = received, 'ready' = receipt to validate,
# 'draft' = RFQ), lines: (product xid, qty, [(lot name, qty, expires in days)])
# (expires in days is counted from today; a 'ready' line without lots is left for the user)
FEFO_PURCHASES = [
    ('rc_fefo_po_dairy_1', 'KFD/INV/2611', 12, 'done', [
        ('rc_fefo_prod_yogurt', 60, [('YOG-2501', 20, 6), ('YOG-2502', 20, 14), ('YOG-2503', 20, 20)]),
        ('rc_fefo_prod_cream', 30, [('CRM-1101', 10, -2), ('CRM-1102', 20, 5)]),
    ]),
    ('rc_fefo_po_dairy_2', 'KFD/INV/2654', 3, 'done', [
        # YOG-2510 arrived 9 days after YOG-2502 but expires earlier -> FEFO picks it first
        ('rc_fefo_prod_yogurt', 40, [('YOG-2510', 15, 9), ('YOG-2511', 25, 25)]),
        ('rc_fefo_prod_paneer', 25, [('PAN-0301', 10, 2), ('PAN-0302', 15, 5)]),
    ]),
    ('rc_fefo_po_dairy_3', 'KFD/INV/2690', 0, 'ready', [
        ('rc_fefo_prod_yogurt', 50, [('YOG-2520', 30, 18), ('YOG-2521', 20, 27)]),
        ('rc_fefo_prod_paneer', 20, [('PAN-0310', 20, 6)]),
        ('rc_fefo_prod_cream', 24, []),
    ]),
    ('rc_fefo_po_dairy_4', False, 0, 'draft', [
        ('rc_fefo_prod_cream', 40, []),
    ]),
]

# xid, product xid, lot name, received days ago, expires in days (negative = already expired), qty
FEFO_LOTS = [
    # Mozzarella: MOZ-2409 arrived after MOZ-2401 but is short-dated -> FEFO takes it first
    ('rc_fefo_lot_moz_2388', 'rc_fefo_prod_mozzarella', 'MOZ-2388', 15, -1, 4),
    ('rc_fefo_lot_moz_2401', 'rc_fefo_prod_mozzarella', 'MOZ-2401', 10, 8, 12),
    ('rc_fefo_lot_moz_2409', 'rc_fefo_prod_mozzarella', 'MOZ-2409', 2, 3, 6),
    ('rc_fefo_lot_moz_2412', 'rc_fefo_prod_mozzarella', 'MOZ-2412', 1, 13, 20),
    # Orange juice
    ('rc_fefo_lot_oj_1120', 'rc_fefo_prod_orange_juice', 'OJ-1120', 4, 4, 10),
    ('rc_fefo_lot_oj_1123', 'rc_fefo_prod_orange_juice', 'OJ-1123', 1, 2, 6),
    ('rc_fefo_lot_oj_1124', 'rc_fefo_prod_orange_juice', 'OJ-1124', 0, 7, 18),
    # Butter: the newer delivery is the short-dated one (inside its alert period)
    ('rc_fefo_lot_but_0815', 'rc_fefo_prod_butter', 'BUT-0815', 30, 40, 24),
    ('rc_fefo_lot_but_0902', 'rc_fefo_prod_butter', 'BUT-0902', 5, 12, 8),
    # Smoked salmon
    ('rc_fefo_lot_sal_0771', 'rc_fefo_prod_salmon', 'SAL-0771', 12, 9, 8),
    ('rc_fefo_lot_sal_0779', 'rc_fefo_prod_salmon', 'SAL-0779', 3, 18, 10),
    # Chocolate mousse: one lot already expired
    ('rc_fefo_lot_mou_0309', 'rc_fefo_prod_mousse', 'MOU-0309', 5, -1, 6),
    ('rc_fefo_lot_mou_0311', 'rc_fefo_prod_mousse', 'MOU-0311', 3, 2, 10),
    ('rc_fefo_lot_mou_0313', 'rc_fefo_prod_mousse', 'MOU-0313', 1, 4, 24),
    # Bread
    ('rc_fefo_lot_brd_1117', 'rc_fefo_prod_bread', 'BRD-1117', 2, 2, 8),
    ('rc_fefo_lot_brd_1118', 'rc_fefo_prod_bread', 'BRD-1118', 0, 4, 15),
]

HOW_TO = _html(
    '<b>How FEFO is set up in this demo</b>',
    '1. Inventory &gt; Configuration &gt; Settings &gt; Traceability: <i>Lots &amp; Serial Numbers</i> and '
    '<i>Expiration Dates</i> enabled.',
    '2. Product &gt; Inventory tab: Tracking = <i>By Lots</i>, <i>Expiration Date</i> ticked, with the expiration, '
    'best-before, removal and alert times (days).',
    '3. Inventory &gt; Configuration &gt; Product Categories &gt; <i>Perishables (FEFO)</i>: '
    'Force Removal Strategy = <i>First Expiry First Out (FEFO)</i>. '
    '(It can also be set per location: Inventory &gt; Configuration &gt; Locations &gt; <i>Perishables Chiller</i>.)',
    '4. Deliveries now reserve the lot with the earliest <i>removal date</i> first, whatever its receipt date, '
    'and never reserve lots whose removal date has passed.',
)


def _fefo_removal(env):
    return env['product.removal'].sudo().search([('method', '=', 'fefo')], limit=1)


def _enable_expiry_settings(env):
    user_group = env.ref('base.group_user')
    for xid in ('stock.group_production_lot', 'stock.group_stock_multi_locations',
                'product_expiry.group_expiry_date_on_delivery_slip'):
        group = env.ref(xid, raise_if_not_found=False)
        if group and group not in user_group.implied_ids:
            user_group.sudo().write({'implied_ids': [Command.link(group.id)]})


def _category_and_location(env, fefo):
    root = env['product.category'].sudo().search([('complete_name', '=', 'Resto / Ingredients')], limit=1)
    categ = _ref(env, 'rc_fefo_categ_perishables')
    if not categ:
        categ = _get_or_create(env, 'rc_fefo_categ_perishables', 'product.category', {
            'name': 'Perishables (FEFO)', 'parent_id': root.id or False})
        _note(categ, HOW_TO)
    if categ.removal_strategy_id != fefo:
        categ.removal_strategy_id = fefo

    warehouse = env['stock.warehouse'].sudo().search([('company_id', '=', env.company.id)], order='id', limit=1)
    loc = _ref(env, 'rc_fefo_loc_chiller')
    if not loc:
        loc = env['stock.location'].sudo().search([
            ('name', '=', 'Perishables Chiller'), ('location_id', '=', warehouse.lot_stock_id.id)], limit=1)
        if loc:
            _bind(env, 'rc_fefo_loc_chiller', loc)
        else:
            loc = _get_or_create(env, 'rc_fefo_loc_chiller', 'stock.location', {
                'name': 'Perishables Chiller', 'location_id': warehouse.lot_stock_id.id, 'usage': 'internal'})
    if loc.removal_strategy_id != fefo:
        loc.removal_strategy_id = fefo
    return warehouse, categ, loc


def _products(env, categ):
    prods = {}
    for xid, code, name, (uom_xid, uom_name), cost, price, (exp, use, removal, alert) in FEFO_PRODUCTS:
        tmpl = _get_or_create(env, xid, 'product.template', {
            'name': name, 'default_code': code, 'type': 'consu', 'is_storable': True, 'tracking': 'lot',
            'categ_id': categ.id, 'uom_id': _uom(env, uom_xid, uom_name).id,
            'standard_price': cost, 'list_price': price,
            'sale_ok': True, 'purchase_ok': True, 'available_in_pos': False,
            'use_expiration_date': True, 'expiration_time': exp, 'use_time': use,
            'removal_time': removal, 'alert_time': alert,
            'description_pickingin': 'Check the expiration date printed on each batch and enter it on the lot.',
        })
        prods[xid] = tmpl.product_variant_id
    return prods


def _expiry(days):
    return fields.Datetime.now().replace(hour=23, minute=0, second=0, microsecond=0) + timedelta(days=days)


def _lots_and_stock(env, prods, loc):
    for xid, pxid, lot_name, received, expires_in, qty in FEFO_LOTS:
        if _ref(env, f'{xid}_quant'):
            continue
        lot = _get_or_create(env, xid, 'stock.lot', {
            'name': lot_name, 'product_id': prods[pxid].id, 'company_id': env.company.id,
            'expiration_date': _expiry(expires_in),
        })
        quant = _put_stock(env, prods[pxid], loc, qty, lot, None, received,
                           note=f'Opening stock: lot {lot_name}')
        if quant and not received:
            quant.in_date = _ago(0, 7)
        _bind(env, f'{xid}_quant', quant)


def _delivery(env, xid, warehouse, loc, partner, lines, origin, validate, note):
    picking = _ref(env, xid)
    if picking:
        return picking
    picking_type = warehouse.out_type_id
    customers = env.ref('stock.stock_location_customers')
    picking = env['stock.picking'].sudo().create({
        'picking_type_id': picking_type.id, 'partner_id': partner.id, 'origin': origin,
        'location_id': loc.id, 'location_dest_id': customers.id,
        'move_ids': [Command.create({
            'product_id': product.id, 'product_uom_qty': qty, 'uom_id': product.uom_id.id,
            'location_id': loc.id, 'location_dest_id': customers.id,
        }) for product, qty in lines],
    })
    _bind(env, xid, picking)
    picking.action_confirm()
    picking.action_assign()
    if validate:
        for move in picking.move_ids:
            move.move_line_ids.write({'picked': True})
            move.picked = True
        picking.with_context(skip_sms=True, skip_backorder=True, cancel_backorder=False,
                             skip_expired=True)._action_done()
    _note(picking, note)
    return picking


def _partner(env, name):
    Partner = env['res.partner'].sudo()
    return Partner.search([('name', '=', name)], limit=1) or Partner.create({
        'name': name, 'is_company': True, 'city': 'Kochi', 'email': f"{name.lower().replace(' ', '.')}@example.com"})


def _deliveries(env, warehouse, loc, prods):
    p = prods
    _delivery(
        env, 'rc_fefo_out_done', warehouse, loc, _partner(env, 'Malabar Corporate Club'),
        [(p['rc_fefo_prod_salmon'], 4), (p['rc_fefo_prod_bread'], 5)],
        'FEFO demo - canapé order', True,
        _html('Validated with FEFO: the salmon came from lot SAL-0771 (expires first) and the bread from '
              'BRD-1117, although newer lots were on the shelf.'))
    _delivery(
        env, 'rc_fefo_out_ready', warehouse, loc, _partner(env, 'Royal Orchid Hospitality Ltd'),
        [(p['rc_fefo_prod_mozzarella'], 10), (p['rc_fefo_prod_orange_juice'], 8),
         (p['rc_fefo_prod_butter'], 6), (p['rc_fefo_prod_mousse'], 12)],
        'FEFO demo - brunch buffet', False,
        _html('<b>Open the Detailed Operations to see FEFO at work:</b>',
              'Mozzarella: 6 from MOZ-2409 (received 2 days ago, expires in 3 days) + 4 from MOZ-2401. '
              'FIFO would have started with the older MOZ-2401. Expired lot MOZ-2388 is never reserved.',
              'Orange juice: OJ-1123 (received yesterday, expires in 2 days) before OJ-1120.',
              'Butter: BUT-0902 (received 5 days ago, short-dated) before BUT-0815 (received 30 days ago).',
              'Chocolate mousse: expired lot MOU-0309 is skipped; MOU-0311 is used first.') + HOW_TO)


# --------------------------------------------------------------------------- 6. purchases with lots
PURCHASE_HOW_TO = _html(
    '<b>Lot-wise expiration dates on purchases</b>',
    '1. Confirm the purchase order; the receipt is created in <i>WH/Stock/Perishables Chiller</i>.',
    '2. On the receipt open the <i>Detailed Operations</i> of a product: add one line per lot, with the '
    '<i>Lot/Serial Number</i>, the quantity and the <i>Expiration Date</i> printed by the vendor '
    '(Odoo proposes receipt date + the product\'s expiration time).',
    '3. Validate: each lot is created with its own expiration, best-before, removal and alert dates.',
    '4. Inventory &gt; Products &gt; Lots/Serial Numbers (group by product) and Inventory &gt; Reporting &gt; '
    'Stock (group by lot) show the quantity and expiry of every lot; lots past their alert date get an '
    '<i>Alert Date Reached</i> activity, expired lots are flagged and never reserved by FEFO.',
)


def _dairy_vendor(env, prods):
    xid, name = DAIRY_VENDOR
    vendor = _ref(env, xid)
    if not vendor:
        vendor = env['res.partner'].sudo().search([('name', '=', name)], limit=1)
        if vendor:
            _bind(env, xid, vendor)
        else:
            vendor = _get_or_create(env, xid, 'res.partner', {
                'name': name, 'is_company': True, 'supplier_rank': 1, 'city': 'Kochi',
                'street': 'Edappally Industrial Estate', 'zip': '682024',
                'email': 'orders@kochifreshdairy.example.com', 'phone': '+91 98470 55120'})
    if 'product.supplierinfo' in env:
        for pxid in PURCHASED_PRODUCTS:
            tmpl = prods[pxid].product_tmpl_id
            if vendor not in tmpl.seller_ids.partner_id:
                env['product.supplierinfo'].sudo().create({
                    'partner_id': vendor.id, 'product_tmpl_id': tmpl.id, 'min_qty': 10,
                    'price': tmpl.standard_price, 'delay': 1,
                    'product_code': f'KFD-{tmpl.default_code[-4:]}'})
    return vendor


def _receive_lots(picking, loc, lines, prods, when):
    """Fill the receipt with one move line per vendor lot (name, qty, expiration date)."""
    MoveLine = picking.env['stock.move.line'].sudo()
    for pxid, _qty, lots in lines:
        move = picking.move_ids.filtered(lambda m: m.product_id == prods[pxid])[:1]
        if not move or not lots:
            continue
        move.move_line_ids.unlink()
        for lot_name, lot_qty, expires_in in lots:
            MoveLine.create({
                'move_id': move.id, 'picking_id': picking.id, 'product_id': move.product_id.id,
                'location_id': move.location_id.id, 'location_dest_id': loc.id,
                'uom_id': move.uom_id.id, 'quantity': lot_qty,
                'lot_name': lot_name, 'expiration_date': _expiry(expires_in),
            })
        if when:
            move.picked = True


def _purchase(env, vendor, warehouse, loc, prods, xid, ref, days, state, lines):
    po = _ref(env, xid)
    if po:
        return po
    po = env['purchase.order'].sudo().with_context(tracking_disable=True).create({
        'partner_id': vendor.id, 'partner_ref': ref or False, 'picking_type_id': warehouse.in_type_id.id,
        'date_order': _ago(days),
        'order_line': [Command.create({
            'product_id': prods[pxid].id, 'product_qty': qty, 'uom_id': prods[pxid].uom_id.id,
            'price_unit': prods[pxid].standard_price, 'date_planned': _ago(max(days - 1, 0), 10),
        }) for pxid, qty, _lots in lines],
    })
    _bind(env, xid, po)
    if state == 'draft':
        _note(po, _html('RFQ to replace the expired cream lot CRM-1101 that was scrapped.') + PURCHASE_HOW_TO)
        return po
    po.button_confirm()
    po.write({'date_order': _ago(days), 'date_approve': _ago(days)})
    for picking in po.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')):
        picking.write({'location_dest_id': loc.id})
        picking.move_ids.write({'location_dest_id': loc.id})
        picking.action_assign()
        done = state == 'done'
        _receive_lots(picking, loc, lines, prods, done)
        if done:
            picking.with_context(skip_sms=True, skip_backorder=True, cancel_backorder=False,
                                 skip_expired=True)._action_done()
            when = _ago(max(days - 1, 0), 11)
            picking.date_done = when
            picking.move_ids.write({'date': when})
            picking.move_line_ids.write({'date': when})
            quants = env['stock.quant'].sudo().search([
                ('location_id', '=', loc.id), ('lot_id', 'in', picking.move_line_ids.lot_id.ids)])
            quants.write({'in_date': when})
            _note(picking, _html('Received in lots with the vendor\'s expiration dates: ' + ', '.join(
                f'{lot} ({qty} units, expires {_expiry(exp):%d %b %Y})'
                for _p, _q, lots in lines for lot, qty, exp in lots) + '.'))
        else:
            _note(picking, _html(
                '<b>Ready to validate:</b> the yogurt and paneer lots are already entered with their '
                'expiration dates (open the Detailed Operations). For the cream, add the lot number and '
                'expiration date from the vendor\'s label yourself, then validate.') + PURCHASE_HOW_TO)
    _note(po, PURCHASE_HOW_TO)
    return po


def _scrap_expired_lot(env, loc, prods):
    """Scrap the expired cream lot CRM-1101 received on the first purchase."""
    if _ref(env, 'rc_fefo_scrap_crm_1101'):
        return
    lot = env['stock.lot'].sudo().search([
        ('name', '=', 'CRM-1101'), ('product_id', '=', prods['rc_fefo_prod_cream'].id)], limit=1)
    quant = env['stock.quant'].sudo().search([
        ('lot_id', '=', lot.id), ('location_id', '=', loc.id), ('quantity', '>', 0)], limit=1) if lot else False
    if not quant:
        return
    company = env.company
    scrap_loc = company.scrap_location_id if 'scrap_location_id' in company._fields else False
    scrap_loc = scrap_loc or env['stock.location'].sudo().search([
        ('usage', '=', 'inventory'), ('scrap_location', '=', True),
        ('company_id', 'in', [company.id, False])], limit=1)
    if not scrap_loc:
        return
    product = prods['rc_fefo_prod_cream']
    vals = {
        'product_id': product.id, 'uom_id': product.uom_id.id, 'product_uom_qty': quant.quantity,
        'location_id': loc.id, 'location_dest_id': scrap_loc.id, 'origin': 'FEFO demo - expired lot CRM-1101',
        'company_id': company.id,
    }
    if 'stock.scrap.reason.tag' in env:
        tag = env['stock.scrap.reason.tag'].sudo().search([('name', '=', 'Spoilage / Expiry')], limit=1) \
            or env['stock.scrap.reason.tag'].sudo().create({'name': 'Spoilage / Expiry'})
        vals['scrap_reason_tag_ids'] = [Command.link(tag.id)]
    move = env['stock.move'].sudo().create(vals)
    env['stock.move.line'].sudo().create({
        'move_id': move.id, 'product_id': product.id, 'lot_id': lot.id, 'quantity': quant.quantity,
        'uom_id': product.uom_id.id, 'location_id': loc.id, 'location_dest_id': scrap_loc.id})
    move.with_context(skip_expired=True)._action_scrap()
    _bind(env, 'rc_fefo_scrap_crm_1101', move)


def _purchases(env, warehouse, loc, prods):
    if 'purchase.order' not in env:
        _logger.info("Hudson POS: FEFO purchase demo skipped (Purchase not installed).")
        return
    vendor = _dairy_vendor(env, prods)
    for xid, ref, days, state, lines in FEFO_PURCHASES:
        try:
            with env.cr.savepoint():
                _purchase(env, vendor, warehouse, loc, prods, xid, ref, days, state, lines)
        except Exception as e:
            _logger.exception("Hudson POS: FEFO purchase %s failed: %s", xid, e)
    try:
        with env.cr.savepoint():
            _scrap_expired_lot(env, loc, prods)
    except Exception as e:
        _logger.exception("Hudson POS: FEFO scrap of expired lot failed: %s", e)
    # a delivery across the purchased lots: YOG-2501 (expires in 6 days) then YOG-2510 (bought 9 days
    # later, expires in 9 days) are reserved before the older YOG-2502 (14 days)
    if _ref(env, 'rc_fefo_po_dairy_2'):
        _delivery(
            env, 'rc_fefo_out_yogurt', warehouse, loc, _partner(env, 'Infopark Tech Solutions Pvt Ltd'),
            [(prods['rc_fefo_prod_yogurt'], 30), (prods['rc_fefo_prod_paneer'], 12)],
            'FEFO demo - corporate lunch (purchased lots)', False,
            _html('<b>FEFO across purchased lots</b> (Detailed Operations):',
                  'Greek Yogurt: 20 from YOG-2501 (expires in 6 days) + 10 from YOG-2510 (expires in 9 days), '
                  'although YOG-2502 and YOG-2503 were bought earlier than YOG-2510.',
                  'Paneer: 10 from PAN-0301 (expires in 2 days) + 2 from PAN-0302.') + PURCHASE_HOW_TO)
    # what the daily scheduler does: an "Alert Date Reached" activity on lots in stock past their alert date
    try:
        with env.cr.savepoint():
            env['stock.lot'].sudo()._alert_date_exceeded()
    except Exception as e:
        _logger.warning("Hudson POS: could not raise FEFO lot expiry alerts: %s", e)


def load_fefo_suite_demo_data(env):
    if 'stock.warehouse' not in env or 'expiration_date' not in env['stock.lot']._fields:
        _logger.info("Hudson POS: FEFO demo skipped (Expiration Dates / product_expiry not installed).")
        return
    fefo = _fefo_removal(env)
    if not fefo:
        _logger.warning("Hudson POS: FEFO removal strategy not found; FEFO demo skipped.")
        return
    ctx = {}

    def setup():
        ctx['warehouse'], ctx['categ'], ctx['loc'] = _category_and_location(env, fefo)
        ctx['prods'] = _products(env, ctx['categ'])

    steps = [
        ('expiry settings', lambda: _enable_expiry_settings(env)),
        ('category, location & products', setup),
        ('lots & stock', lambda: _lots_and_stock(env, ctx['prods'], ctx['loc'])),
        ('deliveries', lambda: _deliveries(env, ctx['warehouse'], ctx['loc'], ctx['prods'])),
        ('purchases with lots', lambda: _purchases(env, ctx['warehouse'], ctx['loc'], ctx['prods'])),
    ]
    for name, step in steps:
        try:
            with env.cr.savepoint():
                step()
        except Exception as e:
            _logger.exception("Hudson POS: FEFO demo step '%s' failed: %s", name, e)
            if name == 'category, location & products':
                return
    _logger.info("Hudson POS: FEFO (First Expiry First Out) demo data loaded.")
