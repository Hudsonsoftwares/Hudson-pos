# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Batch Transfers & fleet delivery demo data.

A batch transfer groups several delivery orders - of the same customer or of different customers -
into one trip, done by one vehicle and driver. Created idempotently (xmlids prefixed ``rc_bt_``) in
the main warehouse (WH) of the Resto Cafe company:

  * 9 dispatch products (lunch boxes, frozen parotta, bulk snacks, coffee, water cans, cold brew
    crates, gravy tubs, payasam) with weight and volume, and opening stock in WH/Stock
  * 13 Kochi customers (offices, supermarkets, a hotel, a hospital, a college, a cafe, home
    customers) with PIN codes, so the stops of a route are sorted by PIN code
  * 15 customer orders: confirmed sales orders when Sales is installed, otherwise delivery orders
  * 5 batch transfers, each a delivery route:
      - Done        Corporate lunch run, Infopark / Kakkanad - 4 orders of 3 customers (BlueWave
                    placed 2 separate orders that travel together), validated yesterday
      - In progress Supermarket restock - Edappally, Palarivattom, Kaloor - 3 customers, reserved
      - In progress Harbour Park Hotel - 3 orders of ONE customer consolidated into one trip
      - Draft       Water & beverages run tomorrow - hospital and college
      - Draft       EV express this evening - a cafe and 2 home deliveries by electric scooter
  * 2 delivery orders not yet in any batch, to try "Add to batch" from the Deliveries list

With Stock Transport (stock_fleet) installed, every batch also gets its vehicle from the Fleet demo
(Tata Ace reefer van, Eeco van, Bolero pick-up, Ather scooter), the driver of that vehicle and
the payload weight/volume capacity of the vehicle category, so the batch shows its load %.
Installing Stock Transport later re-runs this suite, which then completes the existing batches.
"""
import logging
from datetime import timedelta

from markupsafe import Markup

from odoo import Command, fields

from .demo_inventory_features_suite import _ref, _bind, _get_or_create, _put_stock

_logger = logging.getLogger(__name__)

CTX = {'tracking_disable': True, 'mail_create_nolog': True, 'mail_create_nosubscribe': True,
       'mail_auto_subscribe_no_notify': True, 'mail_notify_noemail': True}

# xid, internal reference, name, weight (kg), volume (m3), cost, sale price, opening stock
PRODUCTS = [
    ('rc_bt_prod_lunch_veg', 'RC-DSP-LBV', 'Corporate Lunch Box - Kerala Veg Meals', 0.8, 0.002, 60, 120, 600),
    ('rc_bt_prod_lunch_nv', 'RC-DSP-LBN', 'Corporate Lunch Box - Chicken Biryani', 0.9, 0.002, 85, 160, 600),
    ('rc_bt_prod_parotta', 'RC-DSP-PAR10', 'Frozen Malabar Parotta (Pack of 10)', 0.95, 0.0018, 55, 95, 500),
    ('rc_bt_prod_chips', 'RC-DSP-CHP1K', 'Kerala Banana Chips 1 kg Bulk Pack', 1.05, 0.004, 210, 340, 300),
    ('rc_bt_prod_coffee', 'RC-DSP-COF1K', 'Filter Coffee Powder 1 kg', 1.02, 0.0015, 420, 620, 200),
    ('rc_bt_prod_water', 'RC-DSP-WAT20', 'Packaged Drinking Water 20 L Can', 20.6, 0.026, 45, 80, 300),
    ('rc_bt_prod_coldbrew', 'RC-DSP-CBC12', 'Cold Brew Coffee Crate (12 x 250 ml)', 3.6, 0.009, 540, 900, 150),
    ('rc_bt_prod_gravy', 'RC-DSP-GRV5', 'Kerala Curry Gravy Base 5 kg Tub', 5.3, 0.006, 650, 950, 120),
    ('rc_bt_prod_payasam', 'RC-DSP-PAY6', 'Palada Payasam Tub (6 servings)', 1.6, 0.0025, 180, 300, 200),
]

# xid, name, is company, street, area, PIN code, phone
CUSTOMERS = [
    ('rc_bt_cust_bluewave', 'BlueWave Technologies', True, 'Infopark Phase 1', 'Kakkanad', '682042', '+91 484 2415 100'),
    ('rc_bt_cust_infopark', 'Infopark Tech Solutions Pvt Ltd', True, 'Infopark Phase 2', 'Kakkanad', '682030', '+91 484 2416 220'),
    ('rc_bt_cust_smartcity', 'SmartCity Kochi - Food Court', True, 'SmartCity', 'Kakkanad', '682037', '+91 484 2418 300'),
    ('rc_bt_cust_lulu', 'Lulu Hypermarket Edappally', True, 'NH 66', 'Edappally', '682024', '+91 484 2727 777'),
    ('rc_bt_cust_nilgiris', 'Nilgiris Supermarket Kaloor', True, 'Stadium Link Road', 'Kaloor', '682017', '+91 484 2340 512'),
    ('rc_bt_cust_marginfree', 'Margin Free Market Palarivattom', True, 'Palarivattom Junction', 'Palarivattom', '682025', '+91 484 2338 640'),
    ('rc_bt_cust_harbour', 'Harbour Park Hotel', True, 'Willingdon Island', 'Kochi', '682003', '+91 484 2668 900'),
    ('rc_bt_cust_greenleaf', 'GreenLeaf Multispecialty Hospital', True, 'Edappally Bypass', 'Edappally', '682024', '+91 484 2802 000'),
    ('rc_bt_cust_teresa', "St. Teresa's College Canteen", True, 'Park Avenue', 'Ernakulam', '682011', '+91 484 2351 870'),
    ('rc_bt_cust_brewbloom', 'Brew & Bloom Cafe', True, '5th Cross Road, Panampilly Nagar', 'Kochi', '682036', '+91 98470 22015'),
    ('rc_bt_cust_anjali', 'Anjali Menon', False, 'Sahodaran Ayyappan Road, Kadavanthra', 'Kochi', '682020', '+91 94470 61234'),
    ('rc_bt_cust_rohit', 'Rohit Varghese', False, 'Janatha Road, Vyttila', 'Kochi', '682019', '+91 99610 40987'),
    ('rc_bt_cust_metro', 'Kochi Metro Staff Canteen - Muttom Yard', True, 'Muttom Yard', 'Aluva', '683106', '+91 484 2846 700'),
]

# Payload of the fleet demo vehicle categories (set when Stock Transport is installed)
CATEGORY_CAPACITY = {  # category name: (max weight kg, max volume m3)
    'Light Commercial': (750, 4.5),
    'MPV': (500, 2.5),
    'Electric Scooter': (40, 0.12),
}

# Orders: xid, customer xid, customer reference, lines [(product xid, qty)]
ORDERS = {
    # --- corporate lunch run (done yesterday)
    'rc_bt_ord_bluewave_veg': ('rc_bt_cust_bluewave', 'BW/CAF/1187 - Veg meals', [('rc_bt_prod_lunch_veg', 120)]),
    'rc_bt_ord_bluewave_nv': ('rc_bt_cust_bluewave', 'BW/CAF/1188 - Non-veg meals', [('rc_bt_prod_lunch_nv', 80)]),
    'rc_bt_ord_infopark': ('rc_bt_cust_infopark', 'ITS-PO-5521', [('rc_bt_prod_lunch_veg', 90), ('rc_bt_prod_lunch_nv', 60)]),
    'rc_bt_ord_smartcity': ('rc_bt_cust_smartcity', 'SCK-FC-0342', [('rc_bt_prod_lunch_nv', 40), ('rc_bt_prod_payasam', 20)]),
    # --- supermarket restock (in progress, today)
    'rc_bt_ord_lulu': ('rc_bt_cust_lulu', 'LULU/EDP/PO-77821',
                       [('rc_bt_prod_chips', 60), ('rc_bt_prod_coffee', 40), ('rc_bt_prod_parotta', 100)]),
    'rc_bt_ord_nilgiris': ('rc_bt_cust_nilgiris', 'NIL-KLR-2291',
                           [('rc_bt_prod_chips', 30), ('rc_bt_prod_parotta', 60), ('rc_bt_prod_coffee', 20)]),
    'rc_bt_ord_marginfree': ('rc_bt_cust_marginfree', 'MFM-PLV-1034', [('rc_bt_prod_chips', 25), ('rc_bt_prod_coffee', 15)]),
    # --- one customer, 3 orders, one trip (in progress, today)
    'rc_bt_ord_harbour_banquet': ('rc_bt_cust_harbour', 'HPH-BQT-0915 - Banquet',
                                  [('rc_bt_prod_gravy', 20), ('rc_bt_prod_payasam', 40)]),
    'rc_bt_ord_harbour_cafe': ('rc_bt_cust_harbour', 'HPH-CAF-0916 - Lobby coffee shop',
                               [('rc_bt_prod_coldbrew', 15), ('rc_bt_prod_coffee', 10)]),
    'rc_bt_ord_harbour_staff': ('rc_bt_cust_harbour', 'HPH-STF-0917 - Staff canteen',
                                [('rc_bt_prod_water', 12), ('rc_bt_prod_parotta', 50)]),
    # --- water & beverages run (draft, tomorrow)
    'rc_bt_ord_greenleaf': ('rc_bt_cust_greenleaf', 'GLH/PUR/4410', [('rc_bt_prod_water', 15), ('rc_bt_prod_coldbrew', 5)]),
    'rc_bt_ord_teresa': ('rc_bt_cust_teresa', 'STC-CNT-118', [('rc_bt_prod_water', 10), ('rc_bt_prod_coldbrew', 4)]),
    # --- EV express (draft, this evening)
    'rc_bt_ord_brewbloom': ('rc_bt_cust_brewbloom', 'BNB-0457', [('rc_bt_prod_coldbrew', 2), ('rc_bt_prod_payasam', 2)]),
    'rc_bt_ord_anjali': ('rc_bt_cust_anjali', 'Phone order', [('rc_bt_prod_payasam', 1), ('rc_bt_prod_lunch_nv', 2)]),
    'rc_bt_ord_rohit': ('rc_bt_cust_rohit', 'Website order', [('rc_bt_prod_chips', 1), ('rc_bt_prod_coffee', 1)]),
    # --- not batched yet
    'rc_bt_ord_metro': ('rc_bt_cust_metro', 'KMRL/CNT/PO-2026-311',
                        [('rc_bt_prod_lunch_veg', 150), ('rc_bt_prod_lunch_nv', 100)]),
    'rc_bt_ord_brewbloom_2': ('rc_bt_cust_brewbloom', 'BNB-0461', [('rc_bt_prod_parotta', 20), ('rc_bt_prod_gravy', 2)]),
}

# xid, description, state, day offset, hour, vehicle xid (fleet demo), orders, note
BATCHES = [
    ('rc_bt_batch_lunch_run', 'Corporate Lunch Run - Infopark / Kakkanad', 'done', -1, 11, 'rc_flt_van_1',
     ['rc_bt_ord_bluewave_veg', 'rc_bt_ord_bluewave_nv', 'rc_bt_ord_infopark', 'rc_bt_ord_smartcity'],
     ('<b>Multiple orders of the same and of different customers in one trip.</b>',
      'BlueWave Technologies placed two separate orders (veg and non-veg meals); they travel together with the '
      'Infopark and SmartCity orders in the refrigerated Tata Ace (KL-07-CX-4521).',
      'Validated from the batch: all 4 delivery orders were done in one click.')),
    ('rc_bt_batch_supermarket', 'Supermarket Restock - Edappally, Palarivattom & Kaloor', 'in_progress', 0, 14, 'rc_flt_van_2',
     ['rc_bt_ord_lulu', 'rc_bt_ord_nilgiris', 'rc_bt_ord_marginfree'],
     ('<b>Route of 3 customers, stock reserved and ready to load.</b>',
      'Stops are sorted by PIN code (Kaloor 682017, Edappally 682024, Palarivattom 682025). '
      'Print the batch / consignment notes, load the Eeco van, then <i>Validate</i> after the last drop.')),
    ('rc_bt_batch_harbour', 'Harbour Park Hotel - Consolidated Delivery (3 orders)', 'in_progress', 0, 16, 'rc_flt_pickup',
     ['rc_bt_ord_harbour_banquet', 'rc_bt_ord_harbour_cafe', 'rc_bt_ord_harbour_staff'],
     ('<b>One customer, three orders, one trip.</b>',
      'The banquet kitchen, the lobby coffee shop and the staff canteen of Harbour Park Hotel ordered separately '
      '(each with its own PO number and invoice); the orders are combined into a single delivery run by the '
      'Bolero pick-up to Willingdon Island.')),
    ('rc_bt_batch_water', 'Water & Beverages Run - Edappally / Ernakulam', 'draft', 1, 10, 'rc_flt_pickup',
     ['rc_bt_ord_greenleaf', 'rc_bt_ord_teresa'],
     ('<b>Draft route for tomorrow morning.</b>',
      '25 water cans (about 515 kg) - check the payload % against the vehicle before confirming. '
      'Add the open Kochi Metro canteen order if the Bolero still has capacity.')),
    ('rc_bt_batch_ev_express', 'EV Express - Panampilly Nagar, Kadavanthra & Vyttila', 'draft', 0, 18, 'rc_flt_scooter_1',
     ['rc_bt_ord_brewbloom', 'rc_bt_ord_anjali', 'rc_bt_ord_rohit'],
     ('<b>Last-mile route by electric scooter.</b>',
      'A cafe and two home customers, about 16 kg in total - within the 40 kg payload of the Ather 450X. '
      'Confirm the batch to send it to the rider.')),
]
UNBATCHED = [('rc_bt_ord_metro', 1, 11), ('rc_bt_ord_brewbloom_2', 1, 15)]  # order, day offset, hour

HOW_TO = ('<b>How to batch deliveries</b>',
          '1. Inventory &gt; Operations &gt; Deliveries: select several ready delivery orders (same or different '
          'customers) &gt; Actions &gt; <i>Add to batch</i>, or create one from Inventory &gt; Operations &gt; '
          '<i>Batch Transfers</i>.',
          '2. Set the vehicle (with Stock Transport the driver and the payload capacity follow), confirm the batch, '
          'print the picking list / consignment notes and validate all deliveries of the trip at once.')


def _html(paras):
    return Markup(''.join(f'<p>{p}</p>' for p in paras))


def _note(record, paras):
    record.sudo().with_context(**CTX).message_post(body=_html(paras), message_type='comment',
                                                   subtype_xmlid='mail.mt_note')


def _at(days, hour):
    """Naive UTC datetime of ``hour`` local time (Asia/Kolkata, UTC+5:30) ``days`` from today."""
    local = fields.Datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=days, hours=hour)
    return local - timedelta(hours=5, minutes=30)


# --------------------------------------------------------------------------- setup
def _enable_batches(env):
    group = env.ref('stock.group_stock_picking_batch', raise_if_not_found=False)
    user_group = env.ref('base.group_user')
    if group and group not in user_group.implied_ids:
        user_group.sudo().write({'implied_ids': [Command.link(group.id)]})


def _warehouse(env):
    return env['stock.warehouse'].sudo().search([('company_id', '=', env.company.id)], order='id', limit=1)


def _products(env, warehouse):
    categ = env['product.category'].sudo().search([('complete_name', '=', 'Resto')], limit=1)
    prods = {}
    for xid, code, name, weight, volume, cost, price, qty in PRODUCTS:
        vals = {'name': name, 'default_code': code, 'type': 'consu', 'is_storable': True,
                'weight': weight, 'volume': volume, 'standard_price': cost, 'list_price': price,
                'sale_ok': True, 'purchase_ok': False,
                'description_pickingout': 'Keep upright. Check the seal and the count with the customer at drop-off.'}
        if categ:
            vals['categ_id'] = categ.id
        if 'available_in_pos' in env['product.template']._fields:
            vals['available_in_pos'] = False
        prods[xid] = _get_or_create(env, xid, 'product.template', vals).product_variant_id
        if not _ref(env, f'{xid}_quant'):
            quant = _put_stock(env, prods[xid], warehouse.lot_stock_id, qty, days_ago=10,
                               note='Opening stock: dispatch products')
            if quant:
                _bind(env, f'{xid}_quant', quant)
    return prods


def _customers(env):
    Partner = env['res.partner'].sudo()
    india = env.ref('base.in')
    kerala = env['res.country.state'].sudo().search([('country_id', '=', india.id), ('code', '=', 'KL')], limit=1)
    custs = {}
    for xid, name, company, street, area, zip_code, phone in CUSTOMERS:
        rec = _ref(env, xid)
        if not rec:
            rec = Partner.search([('name', '=', name)], limit=1)
            if rec:
                _bind(env, xid, rec)
            else:
                rec = _get_or_create(env, xid, 'res.partner', {
                    'name': name, 'is_company': company, 'street': street, 'street2': area,
                    'city': 'Aluva' if zip_code.startswith('683') else 'Kochi', 'zip': zip_code,
                    'state_id': kerala.id or False, 'country_id': india.id, 'phone': phone,
                    'email': f"{''.join(c for c in name.lower() if c.isalnum() or c == ' ').replace(' ', '.')}@example.com",
                })
        custs[xid] = rec
    return custs


# --------------------------------------------------------------------------- orders
def _use_sales(env):
    return 'sale.order' in env and 'picking_ids' in env['sale.order']._fields


def _order_picking(env, xid, warehouse, custs, prods, when):
    """Delivery order of a customer order: a confirmed sales order (Sales) or a delivery order."""
    cust_xid, ref, lines = ORDERS[xid]
    partner = custs[cust_xid]
    out_type = warehouse.out_type_id
    if _use_sales(env):
        order = _ref(env, xid)
        if not order:
            order = env['sale.order'].sudo().with_context(**CTX).create({
                'partner_id': partner.id, 'client_order_ref': ref, 'warehouse_id': warehouse.id,
                'date_order': when - timedelta(days=1), 'commitment_date': when,
                'order_line': [Command.create({'product_id': prods[p].id, 'product_uom_qty': q}) for p, q in lines],
            })
            _bind(env, xid, order)
            order.with_context(send_email=False, **CTX).action_confirm()
            order.date_order = when - timedelta(days=1)
        return order.picking_ids.filtered(lambda p: p.picking_type_id == out_type)[:1]

    picking = _ref(env, xid)
    if picking:
        return picking
    src, dest = out_type.default_location_src_id, env.ref('stock.stock_location_customers')
    picking = env['stock.picking'].sudo().with_context(**CTX).create({
        'picking_type_id': out_type.id, 'partner_id': partner.id, 'origin': ref,
        'location_id': src.id, 'location_dest_id': dest.id, 'scheduled_date': when,
        'move_ids': [Command.create({
            'product_id': prods[p].id, 'product_uom_qty': q, 'uom_id': prods[p].uom_id.id,
            'location_id': src.id, 'location_dest_id': dest.id,
        }) for p, q in lines],
    })
    _bind(env, xid, picking)
    picking.action_confirm()
    return picking


# --------------------------------------------------------------------------- fleet
def _fleet_setup(env):
    """Payload capacity on the fleet demo vehicle categories (Stock Transport fields)."""
    Category = env['fleet.vehicle.model.category'].sudo()
    if 'weight_capacity' not in Category._fields:
        return
    for name, (weight, volume) in CATEGORY_CAPACITY.items():
        cat = Category.search([('name', '=', name)], limit=1)
        if cat and not cat.weight_capacity and not cat.volume_capacity:
            cat.write({'weight_capacity': weight, 'volume_capacity': volume})


def _vehicle(env, xid):
    if 'vehicle_id' not in env['stock.picking.batch']._fields:
        return None
    vehicle = _ref(env, xid)
    return vehicle if vehicle and vehicle._name == 'fleet.vehicle' else None


# --------------------------------------------------------------------------- batches
def _sort_by_zip(batch):
    for seq, picking in enumerate(batch.picking_ids.sorted(lambda p: p.partner_id.zip or '')):
        picking.batch_sequence = seq


def _validate(batch, when):
    pickings = batch.picking_ids
    pickings.action_assign()
    for move in pickings.move_ids.filtered(lambda m: m.state not in ('done', 'cancel')):
        move.quantity = move.product_uom_qty
        move.picked = True
    batch.with_context(skip_sms=True, skip_backorder=True, skip_immediate=True, cancel_backorder=False,
                       **CTX).action_done()
    done = pickings.filtered(lambda p: p.state == 'done')
    if done:
        done.write({'date_done': when})
        done.move_ids.write({'date': when})
        done.move_ids.move_line_ids.write({'date': when})
    if batch.state != 'done':
        _logger.warning("Hudson POS: batch '%s' could not be fully validated (state %s)", batch.description, batch.state)


def _batch(env, spec, warehouse, custs, prods, user):
    xid, description, state, days, hour, vehicle_xid, order_xids, note = spec
    when = _at(days, hour)
    vehicle = _vehicle(env, vehicle_xid)
    batch = _ref(env, xid)
    if batch:
        # e.g. Stock Transport installed after the batches were created: complete them with the vehicle
        if vehicle and not batch.vehicle_id:
            batch.vehicle_id = vehicle
        return batch

    pickings = env['stock.picking'].sudo()
    for order_xid in order_xids:
        pickings |= _order_picking(env, order_xid, warehouse, custs, prods, when)
    pickings = pickings.filtered(lambda p: p.state not in ('done', 'cancel'))
    if not pickings:
        return None
    pickings.action_assign()

    vals = {
        'description': description, 'picking_type_id': warehouse.out_type_id.id,
        'company_id': warehouse.company_id.id, 'user_id': user.id,
        'picking_ids': [Command.set(pickings.ids)],
    }
    if vehicle:
        vals['vehicle_id'] = vehicle.id
    batch = env['stock.picking.batch'].sudo().with_context(**CTX).create(vals)
    _bind(env, xid, batch)
    batch.scheduled_date = when
    _sort_by_zip(batch)
    if state in ('in_progress', 'done'):
        batch.action_confirm()
        batch.action_assign()
    if state == 'done':
        _validate(batch, when + timedelta(hours=2))
    _note(batch, note + HOW_TO)
    return batch


def _unbatched(env, warehouse, custs, prods):
    for order_xid, days, hour in UNBATCHED:
        picking = _order_picking(env, order_xid, warehouse, custs, prods, _at(days, hour))
        if picking and picking.state not in ('done', 'cancel'):
            picking.action_assign()


def load_batch_transfer_suite_demo_data(env):
    if 'stock.picking.batch' not in env or 'stock.warehouse' not in env:
        return
    warehouse = _warehouse(env)
    if not warehouse:
        _logger.info("Hudson POS: batch transfer demo skipped, no warehouse.")
        return
    user = env.ref('base.user_admin', raise_if_not_found=False) or env.user
    ctx = {}

    def setup():
        ctx['prods'] = _products(env, warehouse)
        ctx['custs'] = _customers(env)

    steps = [('batch feature', lambda: _enable_batches(env)),
             ('products, stock & customers', setup)]
    if 'fleet.vehicle' in env:
        steps.append(('vehicle capacities', lambda: _fleet_setup(env)))
    for spec in BATCHES:
        steps.append((f'batch {spec[1]}', lambda spec=spec: _batch(env, spec, warehouse, ctx['custs'], ctx['prods'], user)))
    steps.append(('orders to batch', lambda: _unbatched(env, warehouse, ctx['custs'], ctx['prods'])))

    for name, step in steps:
        try:
            with env.cr.savepoint():
                step()
        except Exception as e:  # noqa: BLE001
            _logger.exception("Hudson POS: batch transfer demo step '%s' failed: %s", name, e)
            if name == 'products, stock & customers':
                return
    _logger.info("Hudson POS: batch transfer & fleet delivery demo data loaded.")
