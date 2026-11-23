# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
"""Resto Cafe Solutions - Inventory Rules showcase: inter-warehouse replenishment DC -> Transit -> Stores.

Idempotent: every record is bound to an xmlid of this module (prefix rc_invr_), so the generic
demo cleanup removes it on uninstall. Needs Inventory; uses Purchase (Buy route) when installed.

  Network            Distribution Center (DC) supplies Store 1 - MG Road (S1) and Store 2 - Kakkanad (S2).
                     Each warehouse has its own address, so transfers to S1 and S2 are never merged.
  Transit locations  Inter-warehouse transit (Odoo standard, used by the warehouse supply routes) and a
                     Reefer Van fleet with one transit location per store: Van DC -> S1, Van DC -> S2
  1. Warehouse supply rules   S1 and S2 'Resupply From' = DC: Odoo generates the routes
                     'Store 1: Supply Product from Distribution Center' (DC/Stock -> Transit, MTS;
                     Transit -> S1/Stock, Pull & Push, MTO; return push Transit -> DC). They are set on the
                     'Dry & Packaging' product category.
  2. Custom pull route 'DC -> Stores: Cold-Chain Replenishment (Reefer Van)', set on the chilled products:
                     DC/Stock -> Van DC->S1 / Van DC->S2  (Cold-Chain Dispatch, Take From Stock, if unavailable
                     Trigger Another Rule -> the DC Buy route raises a vendor RFQ), then
                     Van DC->S1 -> S1/Stock and Van DC->S2 -> S2/Stock (store receipts, Trigger Another Rule)
  3. Push rules      route 'Store Cold-Room Put-away (Push)': S1/Stock -> S1/Walk-in Chiller and
                     S2/Stock -> S2/Walk-in Chiller, with Push Applicability = goods arriving from a transit
                     location only, so a validated store receipt automatically creates the chiller transfer
  4. Replenishment rules  min/max reordering rules at S1/Stock and S2/Stock, each with its route
                     (supply from DC or cold chain), and a Buy rule at the DC (with Purchase)
  5. Generated operations  the store rules are run like a buyer would from the Replenishment screen:
                     S1 cold chain - dispatched, received, push put-away to the chiller waiting
                     S1 dry goods  - shipped from DC, goods in transit, store receipt ready
                     S2 dry goods  - DC delivery ready to ship, store receipt waiting
                     S2 cold chain - dispatch reserved for milk, cheese waiting for the DC vendor RFQ
"""
import logging

from odoo import Command

from .demo_inventory_features_suite import _ref, _bind, _get_or_create, _ago, _uom, _note, _put_stock, _process, _next

_logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- 0. settings
def _enable_features(env):
    """Inventory settings: Storage Locations, Multi-Warehouses, Multi-Step Routes."""
    user_group = env.ref('base.group_user')
    for xid in ('stock.group_stock_multi_locations', 'stock.group_stock_multi_warehouses', 'stock.group_adv_location'):
        group = env.ref(xid, raise_if_not_found=False)
        if group and group not in user_group.implied_ids:
            user_group.sudo().write({'implied_ids': [Command.link(group.id)]})


# --------------------------------------------------------------------------- network: warehouses & transit
# xid, name, code, address xid, address name, street
WAREHOUSES = [
    ('dc', 'Resto Distribution Center', 'DC', 'Distribution Center (Kalamassery)', 'Plot 14, KINFRA Industrial Park, Kalamassery'),
    ('s1', 'Store 1 - MG Road', 'S1', 'Store 1 - MG Road', 'MG Road, near Jos Junction, Ernakulam'),
    ('s2', 'Store 2 - Kakkanad', 'S2', 'Store 2 - Kakkanad', 'Infopark Phase 1, Kakkanad'),
]


def _address(env, key, name, street):
    company_partner = env.company.partner_id
    xid = f'rc_invr_partner_{key}'
    partner = _ref(env, xid)
    if partner:
        return partner
    partner = env['res.partner'].sudo().search(
        [('name', '=', name), ('parent_id', '=', company_partner.id)], limit=1)
    if partner:
        return _bind(env, xid, partner)
    return _get_or_create(env, xid, 'res.partner', {
        'name': name, 'parent_id': company_partner.id, 'type': 'delivery', 'street': street,
        'city': 'Kochi', 'zip': '682030', 'country_id': company_partner.country_id.id,
        'state_id': company_partner.state_id.id})


def _warehouses(env):
    Warehouse = env['stock.warehouse'].sudo()
    whs = {}
    for key, name, code, addr_name, street in WAREHOUSES:
        xid = f'rc_invr_wh_{key}'
        wh = _ref(env, xid)
        if not wh:
            wh = Warehouse.search([('code', '=', code), ('company_id', '=', env.company.id)], limit=1)
            if wh:
                _bind(env, xid, wh)
            else:
                partner = _address(env, key, addr_name, street)
                wh = _bind(env, xid, Warehouse.create({
                    'name': name, 'code': code, 'partner_id': partner.id, 'company_id': env.company.id,
                    'reception_steps': 'one_step', 'delivery_steps': 'ship_only'}))
        whs[key] = wh
    return whs


def _transit_and_chillers(env, whs):
    company = env.company
    std_transit = company.internal_transit_location_id
    if std_transit and not std_transit.active:
        std_transit.active = True
    physical = env.ref('stock.stock_location_locations', raise_if_not_found=False) or std_transit.location_id
    fleet = _get_or_create(env, 'rc_invr_loc_reefer_fleet', 'stock.location', {
        'name': 'Reefer Van Fleet', 'usage': 'view', 'location_id': physical.id, 'company_id': company.id})
    locs = {'transit': std_transit, 'fleet': fleet}
    for key, label in (('s1', 'Van DC -> S1'), ('s2', 'Van DC -> S2')):
        locs[f'van_{key}'] = _get_or_create(env, f'rc_invr_loc_van_{key}', 'stock.location', {
            'name': label, 'usage': 'transit', 'location_id': fleet.id, 'company_id': company.id})
        locs[f'chiller_{key}'] = _get_or_create(env, f'rc_invr_loc_chiller_{key}', 'stock.location', {
            'name': 'Walk-in Chiller', 'usage': 'internal', 'location_id': whs[key].lot_stock_id.id,
            'company_id': company.id})
    return locs


# --------------------------------------------------------------------------- 1. warehouse supply rules
def _supply_routes(env, whs):
    """S1/S2 'Resupply From' DC: Odoo generates the inter-warehouse routes and their rules."""
    dc = whs['dc']
    routes = {}
    for key in ('s1', 's2'):
        wh = whs[key]
        if dc not in wh.resupply_wh_ids:
            wh.write({'resupply_wh_ids': [Command.link(dc.id)]})
        xid = f'rc_invr_route_supply_{key}'
        route = _ref(env, xid)
        if not route:
            route = env['stock.route'].sudo().search(
                [('supplied_wh_id', '=', wh.id), ('supplier_wh_id', '=', dc.id)], limit=1)
            if route:
                _bind(env, xid, route)
        routes[key] = route
    return routes


# --------------------------------------------------------------------------- 2/3. custom pull and push routes
def _rule(env, xid, vals):
    # location_dest_from_rule: moves go to the rule's location (Van DC -> S1 / S2), not the operation type default
    rule = _get_or_create(env, xid, 'stock.rule', {'company_id': env.company.id, 'location_dest_from_rule': True, **vals})
    if not rule.location_dest_from_rule:
        rule.location_dest_from_rule = True
    return rule


def _custom_routes(env, whs, locs):
    dc, s1, s2 = whs['dc'], whs['s1'], whs['s2']
    dispatch_type = _get_or_create(env, 'rc_invr_ptype_cc_dispatch', 'stock.picking.type', {
        'name': 'Cold-Chain Dispatch', 'code': 'internal', 'sequence_code': 'CCD', 'warehouse_id': dc.id,
        'company_id': env.company.id, 'default_location_src_id': dc.lot_stock_id.id,
        'default_location_dest_id': locs['van_s1'].id})

    # supplier_wh_id = DC: moves leaving the vans (no warehouse) look for the next rule in the DC
    cold = _get_or_create(env, 'rc_invr_route_coldchain', 'stock.route', {
        'name': 'DC -> Stores: Cold-Chain Replenishment (Reefer Van)', 'sequence': 3, 'company_id': env.company.id,
        'product_selectable': True, 'product_categ_selectable': True, 'warehouse_selectable': False,
        'supplier_wh_id': dc.id})
    for key, wh in (('s1', s1), ('s2', s2)):
        van = locs[f'van_{key}']
        _rule(env, f'rc_invr_rule_cc_dispatch_{key}', {
            'name': f'DC: Stock -> {van.name} (cold-chain dispatch)', 'route_id': cold.id, 'action': 'pull',
            'location_src_id': dc.lot_stock_id.id, 'location_dest_id': van.id, 'picking_type_id': dispatch_type.id,
            'procure_method': 'mts_else_mto', 'warehouse_id': dc.id, 'delay': 1, 'sequence': 10,
            'partner_address_id': wh.partner_id.id, 'propagate_cancel': True})
        _rule(env, f'rc_invr_rule_cc_receive_{key}', {
            'name': f'{wh.code}: {van.name} -> Stock (cold-chain receipt)', 'route_id': cold.id, 'action': 'pull',
            'location_src_id': van.id, 'location_dest_id': wh.lot_stock_id.id, 'picking_type_id': wh.in_type_id.id,
            'procure_method': 'make_to_order', 'warehouse_id': wh.id, 'delay': 0, 'sequence': 20,
            'partner_address_id': dc.partner_id.id})

    push = _get_or_create(env, 'rc_invr_route_push_coldroom', 'stock.route', {
        'name': 'Store Cold-Room Put-away (Push)', 'sequence': 4, 'company_id': env.company.id,
        'product_selectable': True, 'product_categ_selectable': True, 'warehouse_selectable': False})
    for key, wh in (('s1', s1), ('s2', s2)):
        _rule(env, f'rc_invr_rule_push_chiller_{key}', {
            'name': f'{wh.code}: Stock -> Walk-in Chiller (push on arrival from transit)', 'route_id': push.id,
            'action': 'push', 'location_src_id': wh.lot_stock_id.id, 'location_dest_id': locs[f'chiller_{key}'].id,
            'picking_type_id': wh.int_type_id.id, 'auto': 'manual', 'warehouse_id': wh.id, 'delay': 0,
            # only goods coming off a van / the transit location: the chiller transfer itself never re-pushes
            'push_domain': '[("location_id.usage", "=", "transit")]'})
    return cold, push


# --------------------------------------------------------------------------- products
CATEGORIES = [('rc_invr_categ_chilled', 'Chilled (Cold Chain)'), ('rc_invr_categ_dry', 'Dry & Packaging')]

# xid, code, name, category, uom (xmlid, name), cost, DC opening qty, S1 qty, S2 qty
PRODUCTS = [
    ('rc_invr_prod_milk', 'RC-REP-MILK', 'Barista Whole Milk 1 L', 'rc_invr_categ_chilled',
     ('uom.product_uom_unit', 'Units'), 0.95, 300, 8, 5),
    ('rc_invr_prod_butter', 'RC-REP-BUTR', 'Unsalted Butter 500 g', 'rc_invr_categ_chilled',
     ('uom.product_uom_unit', 'Units'), 2.6, 80, 2, 10),
    ('rc_invr_prod_cheese', 'RC-REP-CHED', 'Mature Cheddar Block 1 kg', 'rc_invr_categ_chilled',
     ('uom.product_uom_unit', 'Units'), 7.4, 0, 6, 1),   # no DC stock: the cold chain triggers a DC purchase
    ('rc_invr_prod_beans', 'RC-REP-BEAN', 'House Espresso Beans 1 kg', 'rc_invr_categ_dry',
     ('uom.product_uom_unit', 'Units'), 11.5, 120, 3, 4),
    ('rc_invr_prod_cups', 'RC-REP-CUP12', 'Paper Cup 12 oz (sleeve of 50)', 'rc_invr_categ_dry',
     ('uom.product_uom_unit', 'Units'), 2.1, 400, 15, 30),
    ('rc_invr_prod_syrup', 'RC-REP-SYRV', 'Vanilla Syrup 750 ml', 'rc_invr_categ_dry',
     ('uom.product_uom_unit', 'Units'), 4.8, 60, 9, 2),
    ('rc_invr_prod_sugar', 'RC-REP-SUGR', 'Brown Sugar Sachets (box of 500)', 'rc_invr_categ_dry',
     ('uom.product_uom_unit', 'Units'), 6.2, 40, 6, 1),
]


def _buy_route(env):
    return env.ref('purchase_stock.route_warehouse0_buy', raise_if_not_found=False)


def _products(env, supply_routes, cold, push):
    parent = _ref(env, 'rc_invr_categ_root')
    if not parent:
        parent = env['product.category'].sudo().search([('name', '=', 'Store Replenishment'), ('parent_id', '=', False)], limit=1)
        parent = _bind(env, 'rc_invr_categ_root', parent) if parent else _get_or_create(
            env, 'rc_invr_categ_root', 'product.category', {'name': 'Store Replenishment'})
    for xid, name in CATEGORIES:
        if not _ref(env, xid):
            existing = env['product.category'].sudo().search([('name', '=', name), ('parent_id', '=', parent.id)], limit=1)
            if existing:
                _bind(env, xid, existing)
        _get_or_create(env, xid, 'product.category', {'name': name, 'parent_id': parent.id})
    # category routes: dry goods are supplied by the warehouse supply routes
    dry = _ref(env, 'rc_invr_categ_dry')
    supply = [r.id for r in supply_routes.values() if r]
    if supply and not set(supply) <= set(dry.route_ids.ids):
        dry.route_ids = [Command.link(rid) for rid in supply]

    buy = _buy_route(env)
    vendor = (_ref(env, 'rc_pur_vnd_dairy') or env['res.partner'].sudo().search([('supplier_rank', '>', 0)], limit=1)) \
        if buy else env['res.partner']
    res = {}
    for xid, code, name, categ, (uom_xid, uom_name), cost, *_qty in PRODUCTS:
        chilled = categ == 'rc_invr_categ_chilled'
        # Buy is not product-selectable in Odoo 20: it applies through the warehouse when a vendor is set
        routes = [cold.id, push.id] if chilled else []
        tmpl = _ref(env, xid)
        if not tmpl:
            tmpl = env['product.template'].sudo().search([('default_code', '=', code)], limit=1)
            if tmpl:
                _bind(env, xid, tmpl)
        if not tmpl:
            uom = _uom(env, uom_xid, uom_name)
            tmpl = _get_or_create(env, xid, 'product.template', {
                'name': name, 'default_code': code, 'type': 'consu', 'is_storable': True,
                'categ_id': _ref(env, categ).id, 'uom_id': uom.id, 'standard_price': cost,
                'list_price': round(cost * 1.8, 2), 'sale_ok': False, 'purchase_ok': True,
                'available_in_pos': False, 'route_ids': [Command.set(routes)],
                'description_pickingout': 'Keep at 0-4 °C: load into the reefer van only.' if chilled else False})
        if vendor and not tmpl.seller_ids:
            env['product.supplierinfo'].sudo().create({
                'partner_id': vendor.id, 'product_tmpl_id': tmpl.id, 'price': cost, 'delay': 2, 'min_qty': 1})
        res[xid] = tmpl.product_variant_id
    return res


def _opening_stock(env, whs, prods):
    for xid, _code, _name, _categ, _uom_t, _cost, dc_qty, s1_qty, s2_qty in PRODUCTS:
        for key, qty in (('dc', dc_qty), ('s1', s1_qty), ('s2', s2_qty)):
            if xid == 'rc_invr_prod_cheese' and key == 'dc' and not _buy_route(env):
                qty = 30   # no Purchase app: the DC has stock instead of a vendor order
            mark = f'{xid}_stock_{key}'
            if not qty or _ref(env, mark):
                continue
            quant = _put_stock(env, prods[xid], whs[key].lot_stock_id, qty, days_ago=6,
                               note=f'Opening stock {whs[key].code}')
            _bind(env, mark, quant)


# --------------------------------------------------------------------------- 4. replenishment (reordering) rules
# xid, product, warehouse key, route ('supply' = warehouse supply route, 'cold' = cold chain, 'buy'), min, max, trigger
ORDERPOINTS = [
    ('rc_invr_op_s1_milk', 'rc_invr_prod_milk', 's1', 'cold', 24, 60, 'manual'),
    ('rc_invr_op_s1_butter', 'rc_invr_prod_butter', 's1', 'cold', 6, 18, 'manual'),
    ('rc_invr_op_s1_beans', 'rc_invr_prod_beans', 's1', 'supply', 10, 30, 'manual'),
    ('rc_invr_op_s1_cups', 'rc_invr_prod_cups', 's1', 'supply', 20, 60, 'manual'),
    ('rc_invr_op_s2_milk', 'rc_invr_prod_milk', 's2', 'cold', 18, 48, 'manual'),
    ('rc_invr_op_s2_cheese', 'rc_invr_prod_cheese', 's2', 'cold', 4, 12, 'manual'),
    ('rc_invr_op_s2_beans', 'rc_invr_prod_beans', 's2', 'supply', 8, 24, 'manual'),
    ('rc_invr_op_s2_syrup', 'rc_invr_prod_syrup', 's2', 'supply', 6, 18, 'manual'),
    ('rc_invr_op_s2_sugar', 'rc_invr_prod_sugar', 's2', 'supply', 4, 12, 'auto'),
    # the DC itself is replenished from the vendor (only with Purchase)
    ('rc_invr_op_dc_beans', 'rc_invr_prod_beans', 'dc', 'buy', 50, 150, 'manual'),
    ('rc_invr_op_dc_cups', 'rc_invr_prod_cups', 'dc', 'buy', 200, 600, 'manual'),
]


def _orderpoints(env, whs, prods, supply_routes, cold):
    # created as the admin user: Odoo deletes superuser-created manual rules once nothing is left to order
    Orderpoint = env['stock.warehouse.orderpoint'].with_user(env.ref('base.user_admin')).sudo()
    buy = _buy_route(env)
    created = Orderpoint.browse()
    for xid, pxid, key, route_key, mn, mx, trigger in ORDERPOINTS:
        if _ref(env, xid):
            continue
        route = {'cold': cold, 'supply': supply_routes.get(key), 'buy': buy}.get(route_key)
        if not route:
            continue
        wh, product = whs[key], prods[pxid]
        vals = {'product_id': product.id, 'warehouse_id': wh.id, 'location_id': wh.lot_stock_id.id,
                'product_min_qty': mn, 'product_max_qty': mx, 'trigger': trigger, 'route_id': route.id}
        existing = Orderpoint.search([('product_id', '=', product.id), ('location_id', '=', wh.lot_stock_id.id)], limit=1)
        if existing:
            existing.write(vals)
            op = _bind(env, xid, existing)
        else:
            op = _bind(env, xid, Orderpoint.create(vals))
        if key != 'dc':
            created |= op
    return created


# --------------------------------------------------------------------------- 5. generated operations
def _replenish(env, whs, locs, orderpoints):
    """Run the store rules (Replenishment > Order) store by store and move the S1 flows along.

    S1 runs and ships first: Odoo's supply route would otherwise put S1 and S2 goods in one DC delivery.
    """
    if not orderpoints or _ref(env, 'rc_invr_pick_s1_cold_dispatch'):
        return
    Picking = env['stock.picking'].sudo()
    dc = whs['dc']
    has_po = 'purchase.order' in env
    po_before = env['purchase.order'].sudo().search([]).ids if has_po else []
    picks = {}

    def dispatch(rcpt):
        # the DC operation feeding the store receipt (chained by the rules)
        return rcpt.move_ids.move_orig_ids.picking_id.filtered(lambda p: p.picking_type_id.warehouse_id == dc)[:1]

    def run(key):
        wh = whs[key]
        before = Picking.search([]).ids
        orderpoints.filtered(lambda o: o.warehouse_id == wh).action_replenish()
        new = Picking.search([('id', 'not in', before)])
        for kind, src in (('cold', locs[f'van_{key}']), ('dry', locs['transit'])):
            rcpt = new.filtered(lambda p: p.location_id == src and p.location_dest_id == wh.lot_stock_id)[:1]
            for name, pick in ((f'{key}_{kind}_receipt', rcpt), (f'{key}_{kind}_dispatch', dispatch(rcpt))):
                picks[name] = pick
                if pick:
                    _bind(env, f'rc_invr_pick_{name}', pick)
        new.filtered(lambda p: p.state in ('confirmed', 'waiting')).action_assign()

    def ready(pick):
        return pick and pick.move_ids and all(m.state == 'assigned' for m in pick.move_ids)

    run('s1')
    # S1 cold chain: dispatched yesterday, received this morning -> push rule creates the chiller put-away
    disp, rcpt = picks['s1_cold_dispatch'], picks['s1_cold_receipt']
    if ready(disp):
        _process(disp, when=_ago(1, 6))
        _note(disp, 'Reefer van KL-07-CR-2210 left the DC at 06:00, van temperature 3 °C.')
        if rcpt:
            rcpt.action_assign()
            _process(rcpt, when=_ago(0, 8))
            _note(rcpt, 'Received at MG Road at 08:10, probe 3.5 °C. Goods staged on the receiving bay.')
            putaway = _next(rcpt)
            if putaway:
                putaway.action_assign()
                _bind(env, 'rc_invr_pick_s1_chiller_putaway', putaway[:1])
                _note(putaway[:1], 'Created by the push rule S1: Stock -> Walk-in Chiller when the van receipt was validated.')

    # S1 dry goods: shipped from the DC this morning, still on the road (store receipt ready)
    disp = picks['s1_dry_dispatch']
    if ready(disp):
        _process(disp, when=_ago(0, 7))
        _note(disp, 'Shipped on the 07:00 shuttle to MG Road; expected at the store by 11:00.')
        if picks['s1_dry_receipt']:
            picks['s1_dry_receipt'].action_assign()

    # S2: DC delivery ready to ship; cold chain: cheese has no DC stock ->
    # 'Take From Stock, if unavailable, Trigger Another Rule' asked the vendor (DC Buy route)
    run('s2')
    if has_po:
        rfq = env['purchase.order'].sudo().search([('id', 'not in', po_before)], limit=1)
        if rfq:
            _bind(env, 'rc_invr_po_dc_cheese', rfq)
    if picks['s2_dry_dispatch']:
        _note(picks['s2_dry_dispatch'], 'Picked and staged for the afternoon shuttle to Kakkanad.')
    if picks['s2_cold_dispatch']:
        _note(picks['s2_cold_dispatch'], 'Milk reserved. Cheddar is not in stock at the DC: the rule raised a purchase '
                                         'order to the vendor; dispatch goes out when it is received.')


# --------------------------------------------------------------------------- entry point
def load_inventory_rules_suite_demo_data(env):
    if 'stock.warehouse' not in env:
        return
    ctx = {}

    def network():
        ctx['whs'] = _warehouses(env)
        ctx['locs'] = _transit_and_chillers(env, ctx['whs'])

    def routes():
        ctx['supply'] = _supply_routes(env, ctx['whs'])
        ctx['cold'], ctx['push'] = _custom_routes(env, ctx['whs'], ctx['locs'])

    steps = [
        ('settings', lambda: _enable_features(env)),
        ('warehouses & transit locations', network),
        ('routes & rules', routes),
        ('products', lambda: ctx.update(prods=_products(env, ctx['supply'], ctx['cold'], ctx['push']))),
        ('opening stock', lambda: _opening_stock(env, ctx['whs'], ctx['prods'])),
        ('reordering rules', lambda: ctx.update(ops=_orderpoints(env, ctx['whs'], ctx['prods'], ctx['supply'], ctx['cold']))),
        ('replenishment transfers', lambda: _replenish(env, ctx['whs'], ctx['locs'], ctx.get('ops'))),
    ]
    for name, step in steps:
        try:
            with env.cr.savepoint():
                step()
        except Exception as e:
            _logger.exception("Hudson POS: Inventory rules step '%s' failed: %s", name, e)
            if name in ('warehouses & transit locations', 'routes & rules', 'products'):
                return
    _logger.info("Hudson POS: Resto Cafe Inventory rules (DC -> Transit -> Stores) demo data loaded.")
