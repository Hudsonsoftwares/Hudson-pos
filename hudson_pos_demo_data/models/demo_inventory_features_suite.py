# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Inventory feature showcase (the inventory feature checklist).

Idempotent (every record bound to an xmlid of this module, prefix rc_invf_). Runs after the
Purchase, MRP and Quality suites and reuses their vendors, products and quality teams.

  1. Products with shelf-life lots   lot-tracked dairy/frozen products, lots packed on different dates
                                     with best-before in the lot reference/notes (real expiration dates
                                     and the FEFO removal strategy are shown in demo_fefo_suite)
  2. Multiple locations              Cold Room, Freezer, Dry Store (Rack A/B), Bar Store, Bakery Store
                                     in the main warehouse and in a new Central Kitchen Warehouse (CKW)
  3. Packagings and packages         Crate of 12, Case of 24, Tray of 30, Dozen, Bag of 25 kg, Box of 10 kg,
                                     Can of 5 L; package types (crate, pallet, cool box) and packages holding stock
  4. Units of measure                kg, g, L, ml, Units; bought in bags/trays/cases, stocked in kg/units
  5. Removal strategies              FIFO / LIFO / Least Packages / Closest Location per location
  6. Reordering rules                min/max rules with multiples and a replenishment packaging; one run -> RFQ
  7. Multi-step routes               main WH stays 1-step; CKW receives in 3 steps and delivers in 3 steps
  8. Quality on purchase receipts    quality points on the CKW Quality Control step, checks passed/failed
  9. Returns to vendor               validated returns, a draft return and a vendor credit note
"""
import logging
from datetime import timedelta

from odoo import Command, fields

_logger = logging.getLogger(__name__)

MODULE = 'hudson_pos_demo_data'


# --------------------------------------------------------------------------- helpers
def _ref(env, xid):
    if not xid:
        return False
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


def _ago(days, hour=9):
    return fields.Datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=days)


def _uom(env, xmlid, name):
    return env.ref(xmlid, raise_if_not_found=False) or env['uom.uom'].sudo().search([('name', '=', name)], limit=1)


def _removal(env, method):
    return env['product.removal'].sudo().search([('method', '=', method)], limit=1)


def _vendor(env, xid, fallback_name=None):
    vendor = _ref(env, xid)
    if not vendor and fallback_name:
        vendor = env['res.partner'].sudo().search([('name', '=', fallback_name)], limit=1)
    return vendor or env['res.partner'].sudo().search([('supplier_rank', '>', 0)], limit=1)


def _html(*paras):
    return ''.join(f'<p>{p}</p>' for p in paras)


def _note(record, body):
    record.message_post(body=body, message_type='comment', subtype_xmlid='mail.mt_note')


# --------------------------------------------------------------------------- 0. settings
def _enable_features(env):
    """Same as ticking Inventory settings: locations, multi-warehouse, routes, lots, packages, units."""
    user_group = env.ref('base.group_user')
    for xid in ('stock.group_stock_multi_locations', 'stock.group_stock_multi_warehouses', 'stock.group_adv_location',
                'stock.group_production_lot', 'stock.group_tracking_lot', 'uom.group_uom',
                'product.group_stock_packaging'):
        group = env.ref(xid, raise_if_not_found=False)
        if group and group not in user_group.implied_ids:
            user_group.sudo().write({'implied_ids': [Command.link(group.id)]})


# --------------------------------------------------------------------------- 3. packagings & package types
PACKAGE_TYPES = [
    ('rc_invf_ptype_crate', 'Plastic Crate', 4.0, 30.0, 40, 30, 25),
    ('rc_invf_ptype_pallet', 'Euro Pallet', 25.0, 1000.0, 120, 80, 150),
    ('rc_invf_ptype_coolbox', 'Insulated Cool Box', 3.0, 40.0, 60, 40, 40),
]
# xid, name, factor, base uom (xmlid, name), package type xid
PACKAGINGS = [
    ('rc_invf_uom_crate12', 'Crate of 12', 12, ('uom.product_uom_unit', 'Units'), 'rc_invf_ptype_crate'),
    ('rc_invf_uom_case24', 'Case of 24', 24, ('uom.product_uom_unit', 'Units'), None),
    ('rc_invf_uom_tray30', 'Tray of 30', 30, ('uom.product_uom_unit', 'Units'), None),
    ('rc_invf_uom_dozen', 'Dozen', 12, ('uom.product_uom_unit', 'Units'), None),
    ('rc_invf_uom_bag25kg', 'Bag of 25 kg', 25, ('uom.product_uom_kgm', 'kg'), 'rc_invf_ptype_pallet'),
    ('rc_invf_uom_box10kg', 'Box of 10 kg', 10, ('uom.product_uom_kgm', 'kg'), 'rc_invf_ptype_coolbox'),
    ('rc_invf_uom_can5l', 'Can of 5 L', 5, ('uom.product_uom_litre', 'L'), None),
]


def _packagings(env):
    for xid, name, base_weight, max_weight, length, width, height in PACKAGE_TYPES:
        _get_or_create(env, xid, 'stock.package.type', {
            'name': name, 'base_weight': base_weight, 'max_weight': max_weight,
            'packaging_length': length, 'width': width, 'height': height})
    for xid, name, factor, (base_xid, base_name), ptype in PACKAGINGS:
        if _ref(env, xid):
            continue
        existing = env['uom.uom'].sudo().search([('name', '=', name)], limit=1)
        if existing:
            _bind(env, xid, existing)
            continue
        vals = {'name': name, 'relative_factor': factor, 'relative_uom_id': _uom(env, base_xid, base_name).id}
        if ptype and 'package_type_id' in env['uom.uom']._fields:
            vals['package_type_id'] = _ref(env, ptype).id
        _get_or_create(env, xid, 'uom.uom', vals)


# --------------------------------------------------------------------------- 2/5/7. locations & warehouses
def _main_warehouse(env):
    return env['stock.warehouse'].sudo().search([('company_id', '=', env.company.id)], order='id', limit=1)


def _location(env, xid, name, parent, removal=None):
    loc = _ref(env, xid)
    if not loc:
        loc = env['stock.location'].sudo().search([('name', '=', name), ('location_id', '=', parent.id)], limit=1)
        if loc:
            _bind(env, xid, loc)
        else:
            loc = _get_or_create(env, xid, 'stock.location', {'name': name, 'location_id': parent.id, 'usage': 'internal'})
    if removal and not loc.removal_strategy_id:
        loc.removal_strategy_id = removal
    return loc


def _locations(env):
    fifo, lifo = _removal(env, 'fifo'), _removal(env, 'lifo')
    closest, least = _removal(env, 'closest'), _removal(env, 'least_packages')
    main = _main_warehouse(env)
    stock = main.lot_stock_id
    locs = {
        'main_cold': _location(env, 'rc_invf_loc_main_cold', 'Cold Storage', stock, fifo),
        'main_dry': _location(env, 'rc_invf_loc_main_dry', 'Dry Store', stock, fifo),
        'main_freezer': _location(env, 'rc_invf_loc_main_freezer', 'Freezer', stock, least),
        'main_bar': _location(env, 'rc_invf_loc_main_bar', 'Bar Store', stock, lifo),
        'main_bakery': _location(env, 'rc_invf_loc_main_bakery', 'Bakery Store', stock, closest),
    }
    locs['main_rack_a'] = _location(env, 'rc_invf_loc_main_rack_a', 'Rack A', locs['main_dry'])
    locs['main_rack_b'] = _location(env, 'rc_invf_loc_main_rack_b', 'Rack B', locs['main_dry'])

    ckw = _ref(env, 'rc_invf_wh_ckw') or env['stock.warehouse'].sudo().search([('code', '=', 'CKW')], limit=1)
    if not ckw:
        ckw = env['stock.warehouse'].sudo().create({
            'name': 'Central Kitchen Warehouse', 'code': 'CKW', 'partner_id': env.company.partner_id.id,
            'reception_steps': 'three_steps', 'delivery_steps': 'pick_pack_ship',
        })
    if not _ref(env, 'rc_invf_wh_ckw'):
        _bind(env, 'rc_invf_wh_ckw', ckw)
    ckw_stock = ckw.lot_stock_id
    locs.update({
        'ckw_cold': _location(env, 'rc_invf_loc_ckw_cold', 'Cold Room', ckw_stock, fifo),
        'ckw_freezer': _location(env, 'rc_invf_loc_ckw_freezer', 'Freezer', ckw_stock, least),
        'ckw_dry': _location(env, 'rc_invf_loc_ckw_dry', 'Dry Store', ckw_stock, fifo),
    })
    return main, ckw, locs


# --------------------------------------------------------------------------- 1/4. products
CATEGORIES = [('rc_invf_categ_chilled', 'Dairy & Chilled'), ('rc_invf_categ_frozen', 'Frozen'),
              ('rc_invf_categ_dry', 'Dry Goods'), ('rc_invf_categ_bev', 'Beverages Stock')]

# xid, code, name, categ, uom (xmlid, name), packagings, tracking, cost, vendor xid/fallback,
# (purchase packaging xid or None, vendor price per purchase unit, lead days, min qty), shelf life days
PRODUCTS = [
    ('rc_invf_prod_milk', 'RC-CHL-MILK', 'Fresh Toned Milk', 'rc_invf_categ_chilled', ('uom.product_uom_litre', 'L'),
     ['rc_invf_uom_can5l'], 'lot', 1.35, ('rc_pur_vnd_dairy', None), ('rc_invf_uom_can5l', 6.5, 1, 4), 5),
    ('rc_invf_prod_yogurt', 'RC-CHL-YOGT', 'Greek Yogurt Cup 400 g', 'rc_invf_categ_chilled', ('uom.product_uom_unit', 'Units'),
     ['rc_invf_uom_crate12'], 'lot', 1.9, ('rc_pur_vnd_dairy', None), ('rc_invf_uom_crate12', 21.6, 1, 2), 21),
    ('rc_invf_prod_paneer', 'RC-CHL-PANR', 'Malabar Paneer', 'rc_invf_categ_chilled', ('uom.product_uom_kgm', 'kg'),
     ['rc_invf_uom_box10kg'], 'lot', 6.5, ('rc_pur_vnd_dairy', None), (None, 6.4, 1, 5), 7),
    ('rc_invf_prod_cream', 'RC-CHL-CREM', 'Fresh Cream 35%', 'rc_invf_categ_chilled', ('uom.product_uom_litre', 'L'),
     ['rc_invf_uom_can5l'], 'lot', 4.1, ('rc_pur_vnd_dairy', None), (None, 4.0, 1, 5), 10),
    ('rc_invf_prod_tikka', 'RC-FRZ-TIKK', 'Frozen Chicken Tikka (marinated)', 'rc_invf_categ_frozen', ('uom.product_uom_kgm', 'kg'),
     ['rc_invf_uom_box10kg'], 'lot', 8.2, ('rc_pur_vnd_fish', None), ('rc_invf_uom_box10kg', 80.0, 2, 1), 90),
    ('rc_invf_prod_rice', 'RC-DRY-RICE', 'Aged Basmati Rice', 'rc_invf_categ_dry', ('uom.product_uom_kgm', 'kg'),
     ['rc_invf_uom_bag25kg'], 'none', 1.6, ('rc_pur_vnd_spice', None), ('rc_invf_uom_bag25kg', 38.0, 3, 2), 0),
    ('rc_invf_prod_eggs', 'RC-CHL-EGGS', 'Free-Range Brown Eggs', 'rc_invf_categ_chilled', ('uom.product_uom_unit', 'Units'),
     ['rc_invf_uom_tray30', 'rc_invf_uom_dozen'], 'none', 0.25, ('rc_pur_vnd_dairy', None), ('rc_invf_uom_tray30', 7.2, 1, 2), 0),
    ('rc_invf_prod_saffron', 'RC-DRY-SAFF', 'Kashmiri Saffron', 'rc_invf_categ_dry', ('uom.product_uom_gram', 'g'),
     [], 'none', 0.9, ('rc_pur_vnd_spice', None), (None, 0.85, 7, 10), 0),
    ('rc_invf_prod_water', 'RC-BEV-WATR', 'Packaged Drinking Water 1 L', 'rc_invf_categ_bev', ('uom.product_uom_unit', 'Units'),
     ['rc_invf_uom_case24'], 'none', 0.22, (None, 'Roast & Sip Beverage Distributors'), ('rc_invf_uom_case24', 5.0, 2, 4), 0),
    ('rc_invf_prod_coco_water', 'RC-BEV-TCWT', 'Tender Coconut Water 200 ml', 'rc_invf_categ_bev', ('uom.product_uom_unit', 'Units'),
     ['rc_invf_uom_crate12'], 'none', 0.45, (None, 'Roast & Sip Beverage Distributors'), ('rc_invf_uom_crate12', 5.2, 2, 2), 0),
    ('rc_invf_prod_vanilla', 'RC-BAK-VANL', 'Pure Vanilla Extract', 'rc_invf_categ_dry', (None, 'ml'),
     [], 'none', 0.08, ('rc_pur_vnd_spice', None), (None, 0.075, 7, 250), 0),
]


def _products(env):
    root = env['product.category'].sudo().search([('complete_name', '=', 'Resto / Ingredients')], limit=1)
    for xid, name in CATEGORIES:
        existing = env['product.category'].sudo().search([('name', '=', name), ('parent_id', '=', root.id)], limit=1)
        if existing and not _ref(env, xid):
            _bind(env, xid, existing)
        _get_or_create(env, xid, 'product.category', {'name': name, 'parent_id': root.id or False})
    res = {}
    for (xid, code, name, categ, (uom_xid, uom_name), packs, tracking, cost, (vxid, vname),
         (buy_pack, vprice, delay, min_qty), shelf) in PRODUCTS:
        uom = _uom(env, uom_xid, uom_name) if uom_xid else env['uom.uom'].sudo().search([('name', '=', uom_name)], limit=1)
        vals = {
            'name': name, 'default_code': code, 'type': 'consu', 'is_storable': True, 'tracking': tracking if tracking != 'none' else False,
            'categ_id': _ref(env, categ).id, 'uom_id': uom.id, 'standard_price': cost, 'list_price': round(cost * 2.2, 2),
            'sale_ok': False, 'purchase_ok': True, 'available_in_pos': False,
            'uom_ids': [Command.set([_ref(env, p).id for p in packs if _ref(env, p)])],
            'description_pickingin': (f'Shelf life {shelf} days from packing date. Record the best-before date in the lot.'
                                      if shelf else False),
        }
        tmpl = _get_or_create(env, xid, 'product.template', vals)
        res[xid] = tmpl.product_variant_id
        vendor = _vendor(env, vxid, vname) if vxid else _vendor(env, 'rc_pur_vnd_pack', vname)
        if vendor and not tmpl.seller_ids:
            env['product.supplierinfo'].sudo().create({
                'partner_id': vendor.id, 'product_tmpl_id': tmpl.id, 'price': vprice, 'delay': delay, 'min_qty': min_qty,
                'uom_id': (_ref(env, buy_pack) or uom).id, 'product_code': f'V-{code}',
            })
    return res


# --------------------------------------------------------------------------- stock helpers
def _put_stock(env, product, location, qty, lot=None, package=None, days_ago=0, note='Opening stock'):
    """Inventory adjustment (creates valued stock moves), then backdate the quant's incoming date."""
    Quant = env['stock.quant'].sudo().with_context(inventory_mode=True)
    domain = [('product_id', '=', product.id), ('location_id', '=', location.id),
              ('lot_id', '=', lot.id if lot else False), ('package_id', '=', package.id if package else False)]
    quant = Quant.search(domain, limit=1)
    if quant:
        quant.inventory_quantity = quant.quantity + qty
    else:
        quant = Quant.create({'product_id': product.id, 'location_id': location.id, 'inventory_quantity': qty,
                              'lot_id': lot.id if lot else False, 'package_id': package.id if package else False})
    quant.with_context(inventory_name=note).action_apply_inventory()
    quant = env['stock.quant'].sudo().search(domain, limit=1)
    if quant and days_ago:
        quant.in_date = _ago(days_ago, 8)
    return quant


def _lot_info(packed_days_ago, shelf_days):
    packed = fields.Date.today() - timedelta(days=packed_days_ago)
    best_before = packed + timedelta(days=shelf_days)
    status = ('EXPIRED' if best_before < fields.Date.today()
              else 'expires within 2 days' if (best_before - fields.Date.today()).days <= 2 else 'fresh')
    return {'ref': f'BB {best_before:%d-%m-%Y}',
            'note': _html(f'Packed: {packed:%d %b %Y}', f'Best before: {best_before:%d %b %Y} ({status})')}


def _lot(env, xid, product, name, packed_days_ago, shelf_days):
    return _get_or_create(env, xid, 'stock.lot', {
        'name': name, 'product_id': product.id, 'company_id': env.company.id, **_lot_info(packed_days_ago, shelf_days)})


def _package(env, xid, name, ptype_xid, location=None):
    vals = {'name': name, 'package_type_id': _ref(env, ptype_xid).id}
    return _get_or_create(env, xid, 'stock.package', vals)


# lots: xid, product xid, lot name, packed days ago, location key, qty, package (xid, name, type) or None
LOTS = [
    ('rc_invf_lot_milk_1', 'rc_invf_prod_milk', 'MILK-A118', 7, 'ckw_cold', 10, None, 5),
    ('rc_invf_lot_milk_2', 'rc_invf_prod_milk', 'MILK-A122', 4, 'ckw_cold', 12, None, 5),
    ('rc_invf_lot_milk_3', 'rc_invf_prod_milk', 'MILK-A125', 1, 'ckw_cold', 8, None, 5),
    ('rc_invf_lot_yogurt_1', 'rc_invf_prod_yogurt', 'YOG-2611', 18, 'ckw_cold', 12, ('rc_invf_pkg_crate_1', 'CRATE-0001', 'rc_invf_ptype_crate'), 21),
    ('rc_invf_lot_yogurt_2', 'rc_invf_prod_yogurt', 'YOG-2618', 6, 'ckw_cold', 12, ('rc_invf_pkg_crate_2', 'CRATE-0002', 'rc_invf_ptype_crate'), 21),
    ('rc_invf_lot_paneer_1', 'rc_invf_prod_paneer', 'PNR-0907', 8, 'main_cold', 3, None, 7),
    ('rc_invf_lot_paneer_2', 'rc_invf_prod_paneer', 'PNR-0912', 3, 'main_cold', 5, None, 7),
    ('rc_invf_lot_cream_1', 'rc_invf_prod_cream', 'CRM-1102', 9, 'ckw_cold', 4, None, 10),
    ('rc_invf_lot_cream_2', 'rc_invf_prod_cream', 'CRM-1109', 2, 'ckw_cold', 6, None, 10),
    ('rc_invf_lot_tikka_1', 'rc_invf_prod_tikka', 'TIK-0817', 75, 'main_freezer', 10, ('rc_invf_pkg_coolbox_1', 'COOLBOX-0001', 'rc_invf_ptype_coolbox'), 90),
    ('rc_invf_lot_tikka_2', 'rc_invf_prod_tikka', 'TIK-1003', 30, 'main_freezer', 6, None, 90),
    ('rc_invf_lot_tikka_3', 'rc_invf_prod_tikka', 'TIK-1105', 8, 'ckw_freezer', 20, ('rc_invf_pkg_coolbox_2', 'COOLBOX-0002', 'rc_invf_ptype_coolbox'), 90),
]
# untracked stock: xid, product xid, location key, qty, days ago, package (xid, name, type) or None
STOCK = [
    ('rc_invf_stk_rice_a', 'rc_invf_prod_rice', 'main_rack_a', 50, 20, None),
    ('rc_invf_stk_rice_b', 'rc_invf_prod_rice', 'main_rack_b', 25, 3, None),
    ('rc_invf_stk_rice_ckw', 'rc_invf_prod_rice', 'ckw_dry', 150, 10, ('rc_invf_pkg_pallet_1', 'PALLET-0001', 'rc_invf_ptype_pallet')),
    ('rc_invf_stk_saffron', 'rc_invf_prod_saffron', 'main_rack_a', 40, 15, None),
    ('rc_invf_stk_water_old', 'rc_invf_prod_water', 'main_bar', 48, 25, ('rc_invf_pkg_pallet_3', 'PALLET-0003', 'rc_invf_ptype_pallet')),
    ('rc_invf_stk_water_new', 'rc_invf_prod_water', 'main_bar', 72, 2, ('rc_invf_pkg_pallet_4', 'PALLET-0004', 'rc_invf_ptype_pallet')),
    ('rc_invf_stk_water_ckw', 'rc_invf_prod_water', 'ckw_dry', 192, 6, ('rc_invf_pkg_pallet_2', 'PALLET-0002', 'rc_invf_ptype_pallet')),
    ('rc_invf_stk_coco_old', 'rc_invf_prod_coco_water', 'main_bar', 12, 12, ('rc_invf_pkg_crate_4', 'CRATE-0004', 'rc_invf_ptype_crate')),
    ('rc_invf_stk_coco_new', 'rc_invf_prod_coco_water', 'main_bar', 24, 1, ('rc_invf_pkg_crate_5', 'CRATE-0005', 'rc_invf_ptype_crate')),
    ('rc_invf_stk_vanilla', 'rc_invf_prod_vanilla', 'main_bakery', 750, 9, None),
    ('rc_invf_stk_eggs', 'rc_invf_prod_eggs', 'main_cold', 45, 2, None),
]


def _opening_stock(env, prods, locs):
    for xid, pxid, lot_name, packed, loc_key, qty, pkg, shelf in LOTS:
        if _ref(env, f'{xid}_quant'):
            continue
        lot = _lot(env, xid, prods[pxid], lot_name, packed, shelf)
        package = _package(env, *pkg) if pkg else None
        quant = _put_stock(env, prods[pxid], locs[loc_key], qty, lot, package, packed,
                           note=f'Opening stock: lot {lot_name}')
        _bind(env, f'{xid}_quant', quant)
    for xid, pxid, loc_key, qty, days, pkg in STOCK:
        if _ref(env, xid):
            continue
        package = _package(env, *pkg) if pkg else None
        quant = _put_stock(env, prods[pxid], locs[loc_key], qty, None, package, days)
        _bind(env, xid, quant)


# --------------------------------------------------------------------------- 2. putaway rules
def _putaway(env, main, ckw, locs):
    rules = [
        ('rc_invf_put_ckw_chilled', ckw.lot_stock_id, locs['ckw_cold'], 'rc_invf_categ_chilled'),
        ('rc_invf_put_ckw_frozen', ckw.lot_stock_id, locs['ckw_freezer'], 'rc_invf_categ_frozen'),
        ('rc_invf_put_ckw_dry', ckw.lot_stock_id, locs['ckw_dry'], 'rc_invf_categ_dry'),
        ('rc_invf_put_ckw_bev', ckw.lot_stock_id, locs['ckw_dry'], 'rc_invf_categ_bev'),
        ('rc_invf_put_main_frozen', main.lot_stock_id, locs['main_freezer'], 'rc_invf_categ_frozen'),
        ('rc_invf_put_main_bev', main.lot_stock_id, locs['main_bar'], 'rc_invf_categ_bev'),
    ]
    for xid, loc_in, loc_out, categ in rules:
        _get_or_create(env, xid, 'stock.putaway.rule', {
            'location_in_id': loc_in.id, 'location_out_id': loc_out.id, 'category_id': _ref(env, categ).id})


# --------------------------------------------------------------------------- 8. quality on the CKW QC step
QC_POINTS = [
    ('rc_invf_qc_chilled_temp', 'CKW Chilled Goods Temperature (QC step)', 'measure', 'rc_invf_categ_chilled',
     {'norm': 4.0, 'norm_unit': '°C', 'tolerance_min': 0.0, 'tolerance_max': 5.0,
      'instructions': _html('Probe one unit per crate before the goods move from Quality Control to the Cold Room.'),
      'failure_message': _html('Above 5 °C: keep the goods in Quality Control and raise a quality alert.')}),
    ('rc_invf_qc_shelf_life', 'CKW Shelf-life & Lot Label Check (QC step)', 'passfail', 'rc_invf_categ_chilled',
     {'instructions': _html('Lot number and best-before date printed on every unit; at least 70% shelf life left.')}),
    ('rc_invf_qc_dry_goods', 'CKW Dry Goods Moisture & Pest Check (QC step)', 'passfail', 'rc_invf_categ_dry',
     {'instructions': _html('Bags sealed and dry, no weevils or damp patches, pallet wrap intact.')}),
]


def _quality_points(env, ckw):
    if 'quality.point' not in env or not ckw.qc_type_id:
        return
    team = _ref(env, 'rc_qc_team_receiving') or env['quality.team'].sudo().search([], limit=1)
    for xid, title, ttype, categ, extra in QC_POINTS:
        _get_or_create(env, xid, 'quality.point', {
            'title': title, 'test_type': ttype, 'team_id': team.id, 'user_id': env.ref('base.user_admin').id,
            'picking_type_ids': [Command.set(ckw.qc_type_id.ids)], 'apply_to': 'categories',
            'product_category_id': _ref(env, categ).id, 'control_per': 'product', **extra})


# --------------------------------------------------------------------------- picking helpers
def _process(picking, lots=None, packages=None, ratio=1.0, when=None):
    """Set done quantities (with lot names / destination packages) and validate the transfer."""
    lots, packages = lots or {}, packages or {}
    picking.action_assign()
    for move in picking.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
        qty = move.product_uom_qty * ratio
        lines = move.move_line_ids
        if not lines:
            lines = move.env['stock.move.line'].create({
                'move_id': move.id, 'picking_id': picking.id, 'product_id': move.product_id.id,
                'location_id': move.location_id.id, 'location_dest_id': move.location_dest_id.id,
                'uom_id': move.uom_id.id, 'quantity': qty})
        lines[1:].unlink()
        vals = {'quantity': qty, 'picked': True}
        if move.product_id in lots and picking.picking_type_code == 'incoming':
            vals['lot_name'] = lots[move.product_id]
        if move.product_id in packages:
            vals['result_package_id'] = packages[move.product_id].id
        lines[:1].write(vals)
        move.picked = True
    picking.with_context(skip_sms=True, skip_backorder=True, cancel_backorder=False)._action_done()
    if when:
        picking.date_done = when
        picking.move_ids.filtered(lambda m: m.state == 'done').write({'date': when})
    return picking


def _next(pickings):
    return pickings.move_ids.move_dest_ids.picking_id.filtered(lambda p: p.state not in ('done', 'cancel'))


def _po(env, xid, vendor, picking_type, lines, days, ref):
    po = _ref(env, xid)
    if po:
        return po, False
    line_vals = []
    for product, qty, uom in lines:
        seller = product.seller_ids[:1]
        price = seller.price if seller and (seller.uom_id == uom) else product.standard_price * uom.factor / product.uom_id.factor
        line_vals.append(Command.create({'product_id': product.id, 'product_qty': qty, 'uom_id': uom.id,
                                         'price_unit': price, 'date_planned': _ago(days - 1)}))
    po = env['purchase.order'].sudo().with_context(tracking_disable=True).create({
        'partner_id': vendor.id, 'picking_type_id': picking_type.id, 'partner_ref': ref,
        'date_order': _ago(days), 'order_line': line_vals})
    _bind(env, xid, po)
    po.button_confirm()
    po.write({'date_order': _ago(days), 'date_approve': _ago(days)})
    return po, True


# --------------------------------------------------------------------------- 7/8. multi-step receipts with QC
def _multistep_receipts(env, ckw, prods):
    dairy = _vendor(env, 'rc_pur_vnd_dairy')
    spice = _vendor(env, 'rc_pur_vnd_spice')
    unit = lambda p: p.uom_id
    # A: dairy delivery - received into Input, Quality Control step has checks (one failed), not yet stored
    po, new = _po(env, 'rc_invf_po_ckw_dairy', dairy, ckw.in_type_id, [
        (prods['rc_invf_prod_milk'], 40, unit(prods['rc_invf_prod_milk'])),
        (prods['rc_invf_prod_yogurt'], 2, _ref(env, 'rc_invf_uom_crate12')),
        (prods['rc_invf_prod_cream'], 10, unit(prods['rc_invf_prod_cream'])),
    ], 1, 'PVD-CKW-1201')
    if new:
        receipt = po.picking_ids[:1]
        crate = _package(env, 'rc_invf_pkg_crate_3', 'CRATE-0003', 'rc_invf_ptype_crate')
        _process(receipt, lots={prods['rc_invf_prod_milk']: 'MILK-A127', prods['rc_invf_prod_yogurt']: 'YOG-2625',
                                prods['rc_invf_prod_cream']: 'CRM-1114'},
                 packages={prods['rc_invf_prod_yogurt']: crate}, when=_ago(0, 7))
        shelf = {'rc_invf_prod_milk': 5, 'rc_invf_prod_yogurt': 21, 'rc_invf_prod_cream': 10}
        for lot in receipt.move_line_ids.lot_id:
            days = next((d for x, d in shelf.items() if prods[x] == lot.product_id), 7)
            lot.write(_lot_info(0, days))
        qc = _next(receipt)
        for check in qc.quality_check_ids:
            if check.test_type == 'measure':
                bad = check.product_id == prods['rc_invf_prod_cream']
                check.write({'measure': 7.8 if bad else 3.6})
                if bad:
                    check.write({'quality_state': 'fail', 'date_done': fields.Datetime.now(),
                                 'additional_note': 'Cream cans at 7.8 °C: van chiller off for 40 minutes.'})
                else:
                    check.do_measure()
            elif check.product_id == prods['rc_invf_prod_milk']:
                check.do_pass()
        _note(qc, 'Cream failed the temperature check. Goods held in Quality Control; supplier informed.')
    # B: dry goods - all three steps done (Receipt -> Quality Control -> Stock, put away by category)
    po, new = _po(env, 'rc_invf_po_ckw_dry', spice, ckw.in_type_id, [
        (prods['rc_invf_prod_rice'], 4, _ref(env, 'rc_invf_uom_bag25kg')),
        (prods['rc_invf_prod_saffron'], 50, unit(prods['rc_invf_prod_saffron'])),
    ], 6, 'ISGC-CKW-1188')
    if new:
        receipt = _process(po.picking_ids[:1], when=_ago(4, 8))
        qc = _next(receipt)
        for check in qc.quality_check_ids:
            check.do_pass()
        qc = _process(qc, when=_ago(4, 10))
        store = _next(qc)
        if store:
            _process(store, when=_ago(4, 12))
    # C: eggs bought in trays of 30 - receipt waiting at the dock
    _po(env, 'rc_invf_po_ckw_eggs', dairy, ckw.in_type_id, [
        (prods['rc_invf_prod_eggs'], 8, _ref(env, 'rc_invf_uom_tray30')),
    ], 0, 'PVD-CKW-1205')


# --------------------------------------------------------------------------- 7. 3-step deliveries from CKW
def _multistep_deliveries(env, ckw, prods):
    customers = env.ref('stock.stock_location_customers')
    Procurement = env['stock.rule'].Procurement
    specs = [
        ('rc_invf_dlv_grand_residency', 'rc_partner_grand_residency', 'CKW banquet supply - Grand Residency',
         [(prods['rc_invf_prod_rice'], 50), (prods['rc_invf_prod_water'], 48)], True),
        ('rc_invf_dlv_marina', 'rc_partner_marina_events', 'CKW event supply - Marina Bay',
         [(prods['rc_invf_prod_water'], 96), (prods['rc_invf_prod_rice'], 25)], False),
    ]
    for xid, partner_xid, origin, lines, pick_done in specs:
        if _ref(env, xid):
            continue
        partner = _ref(env, partner_xid) or env.company.partner_id
        before = env['stock.picking'].sudo().search([('picking_type_id', '=', ckw.pick_type_id.id)]).ids
        env['stock.rule'].sudo().run([
            Procurement(product, qty, product.uom_id, customers, origin, origin, env.company,
                        {'warehouse_id': ckw, 'partner_id': partner.id, 'date_planned': fields.Datetime.now() + timedelta(days=1)})
            for product, qty in lines])
        pick = env['stock.picking'].sudo().search([('picking_type_id', '=', ckw.pick_type_id.id), ('id', 'not in', before)], limit=1)
        if not pick:
            continue
        _bind(env, xid, pick)
        pick.action_assign()
        if pick_done and pick.state == 'assigned':
            _process(pick)


# --------------------------------------------------------------------------- 6. reordering rules
ORDERPOINTS = [
    # xid, product, location key ('ckw' stock or loc key), min, max, multiple, replenishment packaging, trigger
    ('rc_invf_op_milk', 'rc_invf_prod_milk', 'ckw', 100, 200, 5, 'rc_invf_uom_can5l', 'manual'),
    ('rc_invf_op_yogurt', 'rc_invf_prod_yogurt', 'ckw', 72, 144, 12, 'rc_invf_uom_crate12', 'manual'),
    ('rc_invf_op_rice', 'rc_invf_prod_rice', 'ckw', 200, 400, 25, 'rc_invf_uom_bag25kg', 'manual'),
    ('rc_invf_op_tikka', 'rc_invf_prod_tikka', 'ckw', 30, 80, 10, 'rc_invf_uom_box10kg', 'manual'),
    ('rc_invf_op_water', 'rc_invf_prod_water', 'main', 144, 288, 24, 'rc_invf_uom_case24', 'manual'),
    ('rc_invf_op_eggs', 'rc_invf_prod_eggs', 'main', 90, 240, 30, 'rc_invf_uom_tray30', 'auto'),
    ('rc_invf_op_saffron', 'rc_invf_prod_saffron', 'main', 25, 100, 10, None, 'manual'),
]


def _orderpoints(env, main, ckw, prods):
    buy = env.ref('purchase_stock.route_warehouse0_buy', raise_if_not_found=False)
    # created as the admin user: Odoo deletes superuser-created manual rules once nothing is left to order
    Orderpoint = env['stock.warehouse.orderpoint'].with_user(env.ref('base.user_admin')).sudo()
    created = []
    for xid, pxid, where, mn, mx, multiple, pack_xid, trigger in ORDERPOINTS:
        if _ref(env, xid):
            continue
        wh = ckw if where == 'ckw' else main
        product = prods[pxid]
        existing = Orderpoint.search([('product_id', '=', product.id), ('location_id', '=', wh.lot_stock_id.id)], limit=1)
        vals = {'product_id': product.id, 'warehouse_id': wh.id, 'location_id': wh.lot_stock_id.id,
                'product_min_qty': mn, 'product_max_qty': mx, 'trigger': trigger}
        if buy:
            vals['route_id'] = buy.id
        pack = _ref(env, pack_xid) if pack_xid else False
        if pack and 'replenishment_uom_id' in Orderpoint._fields:
            vals['replenishment_uom_id'] = pack.id
        if 'qty_multiple' in Orderpoint._fields:
            vals['qty_multiple'] = multiple
        if existing:
            existing.write(vals)
            op = _bind(env, xid, existing)
        else:
            op = _bind(env, xid, Orderpoint.create(vals))
        created.append((xid, op))
    # order the rice now from the Replenishment screen, like a buyer would
    for xid, op in created:
        if xid == 'rc_invf_op_rice':
            before = env['purchase.order'].sudo().search([]).ids
            op.action_replenish()
            rfq = env['purchase.order'].sudo().search([('id', 'not in', before)], limit=1)
            if rfq:
                _bind(env, 'rc_invf_po_replenish_rice', rfq)


# --------------------------------------------------------------------------- 9. returns to vendor
def _return(env, xid, picking, product_qty, validate, note):
    if _ref(env, xid) or not picking or picking.state != 'done':
        return False
    ret = picking._create_return()
    _bind(env, xid, ret)
    keep = {p.id: q for p, q in product_qty}
    for move in ret.move_ids:
        if move.product_id.id in keep:
            move.product_uom_qty = keep[move.product_id.id]
        else:
            move.unlink()
    ret.action_confirm()
    ret.action_assign()
    _note(ret, note)
    if validate:
        _process(ret, when=_ago(0, 11))
    return ret


def _returns_po(env, main, prods):
    """Main warehouse (1-step) purchase: received, billed, then partly returned with a vendor credit note."""
    spice = _vendor(env, 'rc_pur_vnd_spice')
    po, new = _po(env, 'rc_invf_po_main_returns', spice, main.in_type_id, [
        (prods['rc_invf_prod_rice'], 4, _ref(env, 'rc_invf_uom_bag25kg')),
        (prods['rc_invf_prod_saffron'], 60, prods['rc_invf_prod_saffron'].uom_id),
    ], 9, 'ISGC-WH-1172')
    if not new:
        return
    tax_field = 'tax_ids' if 'tax_ids' in po.order_line._fields else 'taxes_id'
    po.order_line.write({tax_field: [Command.clear()]})
    receipt = _process(po.picking_ids[:1], when=_ago(8, 10))
    po.action_create_invoice()
    bill = po.invoice_ids.filtered(lambda m: m.state == 'draft')[:1]
    if bill:
        bill.write({'invoice_date': _ago(7).date(), 'ref': 'ISGC-INV-1172'})
        bill.action_post()
    ret = _return(env, 'rc_invf_ret_rice', receipt, [(prods['rc_invf_prod_rice'], 25)], True,
                  'Returned 1 bag (25 kg) basmati rice: torn bag and weevils found during put-away.')
    if ret and bill and bill.state == 'posted':
        # vendor credit note for the returned bag (qty to invoice is now negative on the PO line)
        lines = []
        for pol in po.order_line.filtered(lambda l: l.qty_to_invoice < 0):
            vals = pol._prepare_account_move_line()
            vals['quantity'] = abs(pol.qty_to_invoice)
            lines.append(Command.create(vals))
        if lines:
            refund = env['account.move'].sudo().create({
                'move_type': 'in_refund', 'partner_id': po.partner_id.id, 'invoice_date': fields.Date.today(),
                'ref': 'ISGC-CN-1172', 'invoice_origin': po.name, 'invoice_line_ids': lines})
            refund.action_post()
            _bind(env, 'rc_invf_refund_rice', refund)
    _return(env, 'rc_invf_ret_saffron_draft', receipt, [(prods['rc_invf_prod_saffron'], 10)], False,
            'Draft return: 10 g saffron failed the colour test. Waiting for the supplier to collect.')


def _returns(env, prods):
    product = lambda code: env['product.product'].sudo().search([('default_code', '=', code)], limit=1)
    fish = _ref(env, 'rc_pur_po_fish_received')
    if fish:
        _return(env, 'rc_invf_ret_fish', fish.picking_ids.filtered(lambda p: p.state == 'done')[:1],
                [(product('RC-ING-SEER'), 3)], True, 'Returned 3 kg seer fish: dull eyes and soft flesh on arrival.')
    spice = _ref(env, 'rc_pur_po_spice_billed')
    if spice:
        ret = _return(env, 'rc_invf_ret_pepper', spice.picking_ids.filtered(lambda p: p.state == 'done' and not p.return_id)[:1],
                      [(product('RC-ING-PEPR'), 5)], True, 'Returned 5 kg pepper: moisture above 12%, mould spots in 2 bags.')
        if ret and not _ref(env, 'rc_invf_refund_pepper'):
            before = spice.invoice_ids.ids
            spice.action_create_invoice()
            refund = spice.invoice_ids.filtered(lambda m: m.id not in before and m.move_type == 'in_refund')[:1]
            if refund:
                refund.write({'invoice_date': fields.Date.today(), 'ref': 'ISGC-CN-0042'})
                refund.action_post()
                _bind(env, 'rc_invf_refund_pepper', refund)
    dairy = _ref(env, 'rc_pur_po_dairy_paid')
    if dairy:
        _return(env, 'rc_invf_ret_milk_draft', dairy.picking_ids.filtered(lambda p: p.state == 'done')[:1],
                [(product('HINV-ING-MILK'), 10)], False, 'Draft return: 10 L milk soured before the use-by date. Waiting for vendor pickup.')


# --------------------------------------------------------------------------- entry point
def load_inventory_features_suite_demo_data(env):
    if 'stock.warehouse' not in env:
        return
    ctx = {}

    def locations():
        ctx['main'], ctx['ckw'], ctx['locs'] = _locations(env)

    steps = [
        ('settings', lambda: _enable_features(env)),
        ('packagings', lambda: _packagings(env)),
        ('locations & warehouses', locations),
        ('products & units', lambda: ctx.update(prods=_products(env))),
        ('putaway rules', lambda: _putaway(env, ctx['main'], ctx['ckw'], ctx['locs'])),
        ('lots & opening stock', lambda: _opening_stock(env, ctx['prods'], ctx['locs'])),
        ('quality points', lambda: _quality_points(env, ctx['ckw'])),
        ('multi-step receipts', lambda: 'purchase.order' in env and _multistep_receipts(env, ctx['ckw'], ctx['prods'])),
        ('multi-step deliveries', lambda: _multistep_deliveries(env, ctx['ckw'], ctx['prods'])),
        ('reordering rules', lambda: _orderpoints(env, ctx['main'], ctx['ckw'], ctx['prods'])),
        ('returns (main warehouse purchase)', lambda: 'purchase.order' in env and _returns_po(env, ctx['main'], ctx['prods'])),
        ('returns (purchase demo orders)', lambda: 'purchase.order' in env and _returns(env, ctx['prods'])),
    ]
    for name, step in steps:
        try:
            with env.cr.savepoint():
                step()
        except Exception as e:
            _logger.exception("Hudson POS: Inventory features step '%s' failed: %s", name, e)
            if name in ('locations & warehouses', 'products & units'):
                return
    _logger.info("Hudson POS: Resto Cafe Inventory features demo data loaded.")
