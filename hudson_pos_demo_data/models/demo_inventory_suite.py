# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.

import logging
from datetime import timedelta
from odoo import fields

_logger = logging.getLogger(__name__)

HINV_PREFIX = 'HINV-'


def _get_or_create_partner(env, ref, name, email, phone='+1 555-0100', street='100 Market St'):
    Partner = env['res.partner'].sudo().with_context(active_test=False)
    partner = Partner.search(['|', ('ref', '=', ref), ('name', '=', name)], limit=1)
    vals = {
        'name': name,
        'ref': ref,
        'is_company': True,
        'email': email,
        'phone': phone,
        'street': street,
    }
    if 'supplier_rank' in Partner._fields:
        vals['supplier_rank'] = 1
    if not partner:
        partner = env['res.partner'].sudo().create(vals)
    else:
        upd = {}
        if not partner.active:
            upd['active'] = True
        if not partner.ref:
            upd['ref'] = ref
        if upd:
            partner.write(upd)
    return partner


def _get_or_create_category(env, name, parent=None):
    Category = env['product.category'].sudo()
    domain = [('name', '=', name)]
    if parent:
        domain.append(('parent_id', '=', parent.id))
    else:
        domain.append(('parent_id', '=', False))
    cat = Category.search(domain, limit=1)
    if not cat:
        cat = Category.create({
            'name': name,
            'parent_id': parent.id if parent else False,
        })
    return cat


def _get_or_create_product(env, code, name, cost, uom, categ):
    ProductTmpl = env['product.template'].sudo()
    Product = env['product.product'].sudo().with_context(active_test=False)
    prod = Product.search([('default_code', '=', code)], limit=1)
    if not prod:
        prod = Product.search([('name', '=', name)], limit=1)
    if prod:
        if not prod.product_tmpl_id.active:
            prod.product_tmpl_id.write({'active': True})
        write_vals = {}
        if not prod.active:
            write_vals['active'] = True
        if not prod.default_code:
            write_vals['default_code'] = code
        if 'is_storable' in prod._fields and not prod.is_storable:
            write_vals['is_storable'] = True
        if prod.type != 'consu':
            write_vals['type'] = 'consu'
        if not prod.purchase_ok:
            write_vals['purchase_ok'] = True
        if prod.sale_ok:
            write_vals['sale_ok'] = False
        if 'available_in_pos' in prod._fields and prod.available_in_pos:
            write_vals['available_in_pos'] = False
        if write_vals:
            prod.write(write_vals)
        return prod

    tmpl_vals = {
        'name': name,
        'default_code': code,
        'type': 'consu',
        'is_storable': True,
        'purchase_ok': True,
        'sale_ok': False,
        'standard_price': cost,
        'list_price': round(cost * 1.25, 2),
        'categ_id': categ.id,
        'uom_id': uom.id,
    }
    if 'available_in_pos' in ProductTmpl._fields:
        tmpl_vals['available_in_pos'] = False
    tmpl = ProductTmpl.create(tmpl_vals)
    return tmpl.product_variant_id


def _ensure_supplierinfo(env, prod, partner, price, delay):
    if 'product.supplierinfo' not in env or not prod or not partner:
        return
    SupplierInfo = env['product.supplierinfo'].sudo()
    company = env.company
    existing = SupplierInfo.search([
        ('partner_id', '=', partner.id),
        ('product_tmpl_id', '=', prod.product_tmpl_id.id),
        ('company_id', 'in', [company.id, False]),
    ], limit=1)
    if not existing:
        SupplierInfo.create({
            'partner_id': partner.id,
            'product_tmpl_id': prod.product_tmpl_id.id,
            'min_qty': 1.0,
            'price': price,
            'delay': delay,
            'company_id': company.id,
            'currency_id': company.currency_id.id,
        })


def _get_or_create_location(env, barcode, name, parent_loc):
    Location = env['stock.location'].sudo().with_context(active_test=False)
    loc = Location.search([
        '|',
        ('barcode', '=', barcode),
        '&', ('name', '=', name), ('location_id', '=', parent_loc.id),
    ], limit=1)
    if not loc:
        vals = {
            'name': name,
            'usage': 'internal',
            'location_id': parent_loc.id,
            'barcode': barcode,
            'company_id': env.company.id,
        }
        loc = env['stock.location'].sudo().create(vals)
    else:
        upd = {}
        if not loc.active:
            upd['active'] = True
        if not loc.barcode:
            upd['barcode'] = barcode
        if upd:
            loc.write(upd)
    return loc


def load_inventory_suite_demo_data(env):
    """
    Populates comprehensive Inventory, Purchasing, Replenishment, BoM, and Stock Move
    demo data aligned with the Restaurant & Cafe POS menu (HINV- prefixed records).
    """
    _logger.info("Hudson Inventory Suite: Loading restaurant & cafe inventory demo data...")

    if 'product.product' not in env or 'stock.quant' not in env:
        _logger.warning("Hudson Inventory Suite: stock module unavailable, skipping.")
        return False

    company = env.company
    Product = env['product.product'].sudo()
    Quant = env['stock.quant'].sudo()
    Warehouse = env['stock.warehouse'].sudo()

    uom_unit = env.ref('uom.product_uom_unit', raise_if_not_found=False) or env['uom.uom'].sudo().search([], limit=1)
    uom_kg = env.ref('uom.product_uom_kgm', raise_if_not_found=False) or uom_unit
    uom_ltr = env.ref('uom.product_uom_litre', raise_if_not_found=False) or uom_unit

    # -------------------------------------------------------------------------
    # 1. Product Categories: Resto / Ingredients, Resto / Packaging
    # -------------------------------------------------------------------------
    cat_resto = _get_or_create_category(env, 'Resto')
    cat_ingredients = _get_or_create_category(env, 'Ingredients', parent=cat_resto)
    cat_packaging = _get_or_create_category(env, 'Packaging', parent=cat_resto)

    # -------------------------------------------------------------------------
    # 2. 6 Vendors
    # -------------------------------------------------------------------------
    v_produce = _get_or_create_partner(
        env, 'HINV-VND-PRODUCE', 'GreenLeaf Fresh Produce Co.',
        'orders@greenleafproduce.example.com', '+1 555-0101', '210 Orchard Ave'
    )
    v_meat = _get_or_create_partner(
        env, 'HINV-VND-MEAT', 'PrimeCut Meats & Poultry Ltd.',
        'supply@primecutmeats.example.com', '+1 555-0102', '48 Butcher Block Rd'
    )
    v_italian = _get_or_create_partner(
        env, 'HINV-VND-ITALIAN', 'BellaItalia Artisan Foods S.r.l.',
        'export@bellaitaliafoods.example.com', '+1 555-0103', '14 Via Napoli Plaza'
    )
    v_seafood = _get_or_create_partner(
        env, 'HINV-VND-SEAFOOD', 'NorthSea Catch & Sushi Supply',
        'desk@northseacatch.example.com', '+1 555-0104', '7 Harbour Pier Way'
    )
    v_beverage = _get_or_create_partner(
        env, 'HINV-VND-BEVERAGE', 'Roast & Sip Beverage Distributors',
        'wholesale@roastandsip.example.com', '+1 555-0105', '305 Roastery Lane'
    )
    v_bakery = _get_or_create_partner(
        env, 'HINV-VND-BAKERY', 'GoldenCrumb Bakery & Dairy Supplies',
        'sales@goldencrumbbakery.example.com', '+1 555-0106', '88 Flour Mill Blvd'
    )

    vendors_map = {
        'produce': v_produce,
        'meat': v_meat,
        'italian': v_italian,
        'seafood': v_seafood,
        'beverage': v_beverage,
        'bakery': v_bakery,
    }

    # -------------------------------------------------------------------------
    # 3. Stock Locations under Warehouse Stock Location
    # -------------------------------------------------------------------------
    warehouse = Warehouse.search([('company_id', '=', company.id)], limit=1)
    if not warehouse:
        warehouse = Warehouse.search([], limit=1)
    lot_stock = warehouse.lot_stock_id if warehouse else env['stock.location'].sudo().search(
        [('usage', '=', 'internal'), ('company_id', 'in', [company.id, False])], limit=1
    )

    loc_cold = _get_or_create_location(env, 'HINV-LOC-COLD', 'Cold Storage', lot_stock) if lot_stock else False
    loc_dry = _get_or_create_location(env, 'HINV-LOC-DRY', 'Dry Store', lot_stock) if lot_stock else False
    loc_kitchen = _get_or_create_location(env, 'HINV-LOC-KITCH', 'Kitchen', lot_stock) if lot_stock else False

    # -------------------------------------------------------------------------
    # 4. Ingredient & Packaging Products + Vendor Pricelists + Stock + Reordering
    # -------------------------------------------------------------------------
    # Tuple fields:
    # (code, name, cost, uom, categ, vendor_key, lead_days,
    #  main_store_type ('cold'|'dry'), main_qty, kitchen_qty, min_qty, max_qty)
    product_specs = [
        # Burgers & Sandwiches
        ('HINV-ING-PAT', 'Beef Patty', 2.80, uom_unit, cat_ingredients, 'meat', 1, 'cold', 60.0, 15.0, 20.0, 100.0),
        ('HINV-ING-BUN', 'Burger Bun', 0.75, uom_unit, cat_ingredients, 'bakery', 1, 'dry', 80.0, 20.0, 30.0, 140.0),
        ('HINV-ING-CHD', 'Cheddar Slice', 0.55, uom_unit, cat_ingredients, 'bakery', 2, 'cold', 90.0, 20.0, 25.0, 150.0),
        ('HINV-ING-BCN', 'Bacon', 14.00, uom_kg, cat_ingredients, 'meat', 2, 'cold', 8.0, 2.0, 3.0, 15.0),
        ('HINV-ING-LET', 'Lettuce', 3.20, uom_kg, cat_ingredients, 'produce', 1, 'cold', 6.0, 2.0, 3.0, 12.0),
        ('HINV-ING-TOM', 'Tomato', 2.90, uom_kg, cat_ingredients, 'produce', 1, 'cold', 8.0, 2.5, 3.0, 15.0),
        ('HINV-ING-BRD', 'Sandwich Bread', 0.65, uom_unit, cat_ingredients, 'bakery', 1, 'dry', 60.0, 18.0, 20.0, 100.0),
        ('HINV-ING-CHK', 'Chicken Breast', 9.50, uom_kg, cat_ingredients, 'meat', 1, 'cold', 12.0, 3.0, 4.0, 20.0),
        ('HINV-ING-TUN', 'Tuna', 13.50, uom_kg, cat_ingredients, 'seafood', 2, 'cold', 7.0, 2.0, 3.0, 14.0),

        # Pizza & Pasta
        ('HINV-ING-DGH', 'Pizza Dough Ball', 1.30, uom_unit, cat_ingredients, 'italian', 2, 'cold', 45.0, 12.0, 15.0, 80.0),
        # Intentionally kept low (3.5 < min 5.0) so Replenishment shows suggestion
        ('HINV-ING-MOZ', 'Mozzarella', 11.00, uom_kg, cat_ingredients, 'italian', 2, 'cold', 3.5, 1.5, 5.0, 18.0),
        ('HINV-ING-TSAU', 'Tomato Sauce', 4.20, uom_ltr, cat_ingredients, 'italian', 2, 'dry', 18.0, 4.0, 6.0, 30.0),
        ('HINV-ING-MSH', 'Mushrooms', 6.80, uom_kg, cat_ingredients, 'produce', 1, 'cold', 5.0, 1.5, 2.0, 10.0),
        ('HINV-ING-SPG', 'Spaghetti', 3.60, uom_kg, cat_ingredients, 'italian', 3, 'dry', 22.0, 5.0, 6.0, 35.0),
        ('HINV-ING-MBF', 'Minced Beef', 11.50, uom_kg, cat_ingredients, 'meat', 1, 'cold', 10.0, 2.5, 4.0, 18.0),
        ('HINV-ING-4CH', 'Four-Cheese Mix', 13.00, uom_kg, cat_ingredients, 'italian', 2, 'cold', 6.0, 1.5, 2.5, 12.0),

        # Sushi
        ('HINV-ING-SRIC', 'Sushi Rice', 4.50, uom_kg, cat_ingredients, 'seafood', 3, 'dry', 25.0, 5.0, 8.0, 40.0),
        ('HINV-ING-NORI', 'Nori Sheets', 0.35, uom_unit, cat_ingredients, 'seafood', 3, 'dry', 120.0, 30.0, 40.0, 200.0),
        # Start with 3.0 kg in Cold Storage; after 1.0 kg scrap -> 2.0 kg (< min 6.0) triggers replenishment
        ('HINV-ING-SALM', 'Fresh Salmon', 22.00, uom_kg, cat_ingredients, 'seafood', 1, 'cold', 3.0, 1.5, 6.0, 16.0),
        ('HINV-ING-AVOC', 'Avocado', 1.25, uom_unit, cat_ingredients, 'produce', 1, 'cold', 24.0, 6.0, 10.0, 40.0),

        # Cafe & Desserts
        # Low (4.0 < min 6.0) for Replenishment suggestion
        ('HINV-ING-COFF', 'Espresso Coffee Beans', 18.00, uom_kg, cat_ingredients, 'beverage', 2, 'dry', 4.0, 1.5, 6.0, 20.0),
        ('HINV-ING-MILK', 'Milk', 1.60, uom_ltr, cat_ingredients, 'bakery', 1, 'cold', 30.0, 8.0, 12.0, 50.0),
        # Low (3.5 < min 5.0) for Replenishment suggestion
        ('HINV-ING-CREM', 'Heavy Cream', 4.80, uom_ltr, cat_ingredients, 'bakery', 1, 'cold', 3.5, 1.5, 5.0, 16.0),
        ('HINV-ING-GTEA', 'Green Tea Leaves', 24.00, uom_kg, cat_ingredients, 'beverage', 3, 'dry', 4.5, 1.0, 1.5, 8.0),
        ('HINV-ING-FLOUR', 'Flour', 1.80, uom_kg, cat_ingredients, 'bakery', 3, 'dry', 35.0, 6.0, 10.0, 50.0),
        ('HINV-ING-SUGR', 'Sugar', 1.90, uom_kg, cat_ingredients, 'bakery', 3, 'dry', 28.0, 5.0, 8.0, 40.0),
        ('HINV-ING-EGGS', 'Eggs', 0.30, uom_unit, cat_ingredients, 'bakery', 1, 'cold', 96.0, 24.0, 36.0, 180.0),
        ('HINV-ING-BUTR', 'Butter', 8.50, uom_kg, cat_ingredients, 'bakery', 2, 'cold', 10.0, 2.5, 4.0, 18.0),
        ('HINV-ING-DCHOC', 'Dark Chocolate', 15.00, uom_kg, cat_ingredients, 'bakery', 3, 'dry', 8.0, 2.0, 3.0, 15.0),
        ('HINV-ING-MASC', 'Mascarpone', 12.50, uom_kg, cat_ingredients, 'italian', 2, 'cold', 5.5, 1.5, 2.0, 10.0),
        ('HINV-ING-CCHS', 'Cream Cheese', 9.80, uom_kg, cat_ingredients, 'bakery', 2, 'cold', 7.0, 2.0, 3.0, 14.0),
        ('HINV-ING-VICE', 'Vanilla Ice Cream', 6.40, uom_ltr, cat_ingredients, 'bakery', 2, 'cold', 12.0, 3.0, 5.0, 20.0),
        ('HINV-ING-APPL', 'Apples', 3.40, uom_kg, cat_ingredients, 'produce', 1, 'cold', 10.0, 2.0, 4.0, 16.0),
        ('HINV-ING-BANA', 'Bananas', 2.10, uom_kg, cat_ingredients, 'produce', 1, 'dry', 9.0, 2.5, 4.0, 16.0),

        # Packaging
        # Low (80 < min 120) for Replenishment suggestion
        ('HINV-PKG-CUP', 'Paper Cup', 0.18, uom_unit, cat_packaging, 'bakery', 4, 'dry', 80.0, 25.0, 120.0, 600.0),
        ('HINV-PKG-BOX', 'Takeaway Food Box', 0.35, uom_unit, cat_packaging, 'bakery', 4, 'dry', 250.0, 50.0, 100.0, 500.0),
        ('HINV-PKG-NAP', 'Paper Napkins', 0.04, uom_unit, cat_packaging, 'bakery', 4, 'dry', 500.0, 100.0, 150.0, 1000.0),
    ]

    products_by_code = {}
    Orderpoint = env['stock.warehouse.orderpoint'].sudo() if 'stock.warehouse.orderpoint' in env else None

    for (code, name, cost, uom, categ, vkey, delay, store_kind, main_qty, kitchen_qty, min_qty, max_qty) in product_specs:
        prod = _get_or_create_product(env, code, name, cost, uom, categ)
        products_by_code[code] = prod

        # Vendor price
        _ensure_supplierinfo(env, prod, vendors_map[vkey], round(cost * 0.92, 2), delay)

        # Opening stock split between main store (Cold Storage / Dry Store) and Kitchen
        main_loc = loc_cold if store_kind == 'cold' else loc_dry
        for loc, qty in ((main_loc, main_qty), (loc_kitchen, kitchen_qty)):
            if not loc or qty <= 0:
                continue
            try:
                existing_q = Quant.search([
                    ('product_id', '=', prod.id),
                    ('location_id', '=', loc.id),
                ], limit=1)
                if not existing_q:
                    Quant.with_context(inventory_mode=True).create({
                        'product_id': prod.id,
                        'location_id': loc.id,
                        'inventory_quantity': qty,
                    }).action_apply_inventory()
            except Exception as e:
                _logger.warning("Hudson Inventory Suite: Could not set stock for %s in %s: %s", name, loc.name, e)

        # Reordering rule on main storage location
        op_loc = main_loc or lot_stock
        if Orderpoint is not None and warehouse and op_loc:
            op_name = f"{HINV_PREFIX}OP-{code}"
            existing_op = Orderpoint.search([
                '|',
                ('name', '=', op_name),
                '&', ('product_id', '=', prod.id), ('location_id', '=', op_loc.id),
            ], limit=1)
            if not existing_op:
                try:
                    Orderpoint.create({
                        'name': op_name,
                        'trigger': 'auto',
                        'warehouse_id': warehouse.id,
                        'location_id': op_loc.id,
                        'product_id': prod.id,
                        'product_min_qty': min_qty,
                        'product_max_qty': max_qty,
                        'company_id': company.id,
                    })
                except Exception as e:
                    _logger.warning("Hudson Inventory Suite: Could not create orderpoint for %s: %s", name, e)

    # -------------------------------------------------------------------------
    # 5. Vendor prices + Reordering rules for Ready-Made POS Drinks & Key POS Menu
    # -------------------------------------------------------------------------
    drink_vendor_specs = [
        ('Coca-Cola', 1.15, 2, 30.0, 120.0),
        ('Fanta', 1.15, 2, 30.0, 120.0),
        ('Schweppes', 1.15, 2, 24.0, 100.0),
        ('Minute Maid', 1.20, 2, 24.0, 100.0),
        ('Water', 0.65, 2, 40.0, 180.0),
        ('Ice Tea', 1.10, 2, 24.0, 100.0),
    ]
    for drink_name, v_price, delay, min_q, max_q in drink_vendor_specs:
        drink_prod = Product.search([('name', '=', drink_name), ('available_in_pos', '=', True)], limit=1)
        if drink_prod:
            _ensure_supplierinfo(env, drink_prod, v_beverage, v_price, delay)
            if Orderpoint is not None and warehouse and lot_stock:
                op_name = f"{HINV_PREFIX}OP-POS-{drink_prod.id}"
                existing_op = Orderpoint.search([
                    '|',
                    ('name', '=', op_name),
                    '&', ('product_id', '=', drink_prod.id), ('location_id', '=', lot_stock.id),
                ], limit=1)
                if not existing_op:
                    try:
                        Orderpoint.create({
                            'name': op_name,
                            'trigger': 'auto',
                            'warehouse_id': warehouse.id,
                            'location_id': lot_stock.id,
                            'product_id': drink_prod.id,
                            'product_min_qty': min_q,
                            'product_max_qty': max_q,
                            'company_id': company.id,
                        })
                    except Exception as e:
                        _logger.warning("Hudson Inventory Suite: Orderpoint failed for POS drink %s: %s", drink_name, e)

    key_pos_items = [
        ('Cheese Burger', 20.0, 80.0),
        ('Bacon Burger', 20.0, 80.0),
        ('Pizza Margherita', 15.0, 60.0),
        ('Pasta Bolognese', 15.0, 60.0),
        ('Lunch Maki 18pc', 10.0, 40.0),
        ('Espresso', 30.0, 120.0),
        ('Tiramisu', 12.0, 50.0),
        ('New York Cheesecake', 12.0, 50.0),
        ('Artisan Chocolate Croissant', 20.0, 80.0),
        ('Luxury Chocolate Gift Box', 10.0, 40.0),
    ]
    if Orderpoint is not None and warehouse and lot_stock:
        for pos_name, min_q, max_q in key_pos_items:
            pos_prod = Product.search([('name', '=', pos_name), ('available_in_pos', '=', True)], limit=1)
            if not pos_prod:
                continue
            op_name = f"{HINV_PREFIX}OP-POS-{pos_prod.id}"
            existing_op = Orderpoint.search([
                '|',
                ('name', '=', op_name),
                '&', ('product_id', '=', pos_prod.id), ('location_id', '=', lot_stock.id),
            ], limit=1)
            if not existing_op:
                try:
                    Orderpoint.create({
                        'name': op_name,
                        'trigger': 'auto',
                        'warehouse_id': warehouse.id,
                        'location_id': lot_stock.id,
                        'product_id': pos_prod.id,
                        'product_min_qty': min_q,
                        'product_max_qty': max_q,
                        'company_id': company.id,
                    })
                except Exception as e:
                    _logger.warning("Hudson Inventory Suite: Orderpoint failed for POS item %s: %s", pos_name, e)

    # -------------------------------------------------------------------------
    # 6. Bills of Materials (BoMs) for 18 existing POS Products (if mrp.bom in env)
    # -------------------------------------------------------------------------
    if 'mrp.bom' in env:
        Bom = env['mrp.bom'].sudo()
        bom_specs = [
            ('Cheese Burger', [
                ('HINV-ING-PAT', 1.0),
                ('HINV-ING-BUN', 1.0),
                ('HINV-ING-CHD', 1.0),
                ('HINV-ING-LET', 0.03),
                ('HINV-ING-TOM', 0.04),
                ('HINV-PKG-BOX', 1.0),
                ('HINV-PKG-NAP', 2.0),
            ]),
            ('Bacon Burger', [
                ('HINV-ING-PAT', 1.0),
                ('HINV-ING-BUN', 1.0),
                ('HINV-ING-BCN', 0.06),
                ('HINV-ING-CHD', 1.0),
                ('HINV-ING-LET', 0.03),
                ('HINV-ING-TOM', 0.04),
                ('HINV-PKG-BOX', 1.0),
                ('HINV-PKG-NAP', 2.0),
            ]),
            ('Pizza Margherita', [
                ('HINV-ING-DGH', 1.0),
                ('HINV-ING-MOZ', 0.16),
                ('HINV-ING-TSAU', 0.12),
                ('HINV-PKG-BOX', 1.0),
            ]),
            ('Pizza Vegetarian', [
                ('HINV-ING-DGH', 1.0),
                ('HINV-ING-MOZ', 0.14),
                ('HINV-ING-TSAU', 0.12),
                ('HINV-ING-MSH', 0.08),
                ('HINV-ING-TOM', 0.06),
                ('HINV-PKG-BOX', 1.0),
            ]),
            ('Pasta Bolognese', [
                ('HINV-ING-SPG', 0.16),
                ('HINV-ING-MBF', 0.12),
                ('HINV-ING-TSAU', 0.15),
                ('HINV-ING-BUTR', 0.02),
            ]),
            ('Pasta 4 Formaggi', [
                ('HINV-ING-SPG', 0.16),
                ('HINV-ING-4CH', 0.14),
                ('HINV-ING-CREM', 0.08),
                ('HINV-ING-BUTR', 0.02),
            ]),
            ('Club Sandwich', [
                ('HINV-ING-BRD', 3.0),
                ('HINV-ING-CHK', 0.12),
                ('HINV-ING-BCN', 0.04),
                ('HINV-ING-LET', 0.04),
                ('HINV-ING-TOM', 0.05),
                ('HINV-ING-CHD', 1.0),
                ('HINV-PKG-NAP', 2.0),
            ]),
            ('Spicy Tuna Sandwich', [
                ('HINV-ING-BRD', 2.0),
                ('HINV-ING-TUN', 0.11),
                ('HINV-ING-LET', 0.03),
                ('HINV-ING-TOM', 0.04),
                ('HINV-PKG-NAP', 2.0),
            ]),
            ('Lunch Maki 18pc', [
                ('HINV-ING-SRIC', 0.28),
                ('HINV-ING-NORI', 3.0),
                ('HINV-ING-SALM', 0.14),
                ('HINV-ING-AVOC', 0.5),
                ('HINV-PKG-BOX', 1.0),
            ]),
            ('Salmon and Avocado', [
                ('HINV-ING-SRIC', 0.18),
                ('HINV-ING-NORI', 2.0),
                ('HINV-ING-SALM', 0.16),
                ('HINV-ING-AVOC', 1.0),
                ('HINV-PKG-BOX', 1.0),
            ]),
            ('Espresso', [
                ('HINV-ING-COFF', 0.02),
                ('HINV-PKG-CUP', 1.0),
            ]),
            ('Green Tea', [
                ('HINV-ING-GTEA', 0.01),
                ('HINV-PKG-CUP', 1.0),
            ]),
            ('Milkshake Banana', [
                ('HINV-ING-BANA', 0.15),
                ('HINV-ING-MILK', 0.22),
                ('HINV-ING-VICE', 0.10),
                ('HINV-PKG-CUP', 1.0),
            ]),
            ('Tiramisu', [
                ('HINV-ING-MASC', 0.10),
                ('HINV-ING-CREM', 0.06),
                ('HINV-ING-EGGS', 1.0),
                ('HINV-ING-SUGR', 0.03),
                ('HINV-ING-COFF', 0.01),
            ]),
            ('New York Cheesecake', [
                ('HINV-ING-CCHS', 0.14),
                ('HINV-ING-CREM', 0.06),
                ('HINV-ING-EGGS', 1.0),
                ('HINV-ING-SUGR', 0.04),
                ('HINV-ING-BUTR', 0.03),
            ]),
            ('Chocolate Lava Cake', [
                ('HINV-ING-DCHOC', 0.09),
                ('HINV-ING-BUTR', 0.06),
                ('HINV-ING-EGGS', 2.0),
                ('HINV-ING-FLOUR', 0.04),
                ('HINV-ING-SUGR', 0.04),
            ]),
            ('Warm Apple Pie', [
                ('HINV-ING-APPL', 0.18),
                ('HINV-ING-FLOUR', 0.08),
                ('HINV-ING-BUTR', 0.05),
                ('HINV-ING-SUGR', 0.04),
            ]),
            ('Vanilla Bean Ice Cream Sundae', [
                ('HINV-ING-VICE', 0.18),
                ('HINV-ING-CREM', 0.04),
                ('HINV-ING-DCHOC', 0.03),
            ]),
        ]

        for pos_name, comp_list in bom_specs:
            pos_prod = Product.search([('name', '=', pos_name), ('available_in_pos', '=', True)], limit=1)
            if not pos_prod:
                continue
            existing_bom = Bom.search([
                '|',
                ('product_tmpl_id', '=', pos_prod.product_tmpl_id.id),
                ('code', '=', f'{HINV_PREFIX}BOM-{pos_prod.id}'),
            ], limit=1)
            if existing_bom:
                continue

            bom_lines = []
            for comp_code, comp_qty in comp_list:
                comp_prod = products_by_code.get(comp_code)
                if comp_prod:
                    bom_lines.append((0, 0, {
                        'product_id': comp_prod.id,
                        'product_qty': comp_qty,
                        'uom_id': comp_prod.uom_id.id,
                    }))
            if bom_lines:
                try:
                    Bom.create({
                        'product_tmpl_id': pos_prod.product_tmpl_id.id,
                        'code': f'{HINV_PREFIX}BOM-{pos_prod.id}',
                        'product_qty': 1.0,
                        'uom_id': pos_prod.uom_id.id,
                        'type': 'normal',
                        'company_id': company.id,
                        'bom_line_ids': bom_lines,
                    })
                except Exception as e:
                    _logger.warning("Hudson Inventory Suite: Could not create BoM for %s: %s", pos_name, e)

    # -------------------------------------------------------------------------
    # 7. Stock Move History
    #    a) Confirmed & Received Purchase Order (Meat supplier)
    # -------------------------------------------------------------------------
    if 'purchase.order' in env:
        PurchaseOrder = env['purchase.order'].sudo()
        po_ref = 'HINV-PO-MEAT-001'
        po = PurchaseOrder.search([('partner_ref', '=', po_ref)], limit=1)
        if not po:
            po_lines_specs = [
                ('HINV-ING-PAT', 40.0, 2.55),
                ('HINV-ING-BCN', 10.0, 12.80),
                ('HINV-ING-CHK', 15.0, 8.70),
                ('HINV-ING-MBF', 12.0, 10.50),
            ]
            po_lines = []
            now_dt = fields.Datetime.now()
            for code, qty, price in po_lines_specs:
                comp_prod = products_by_code.get(code)
                if comp_prod:
                    po_lines.append((0, 0, {
                        'product_id': comp_prod.id,
                        'name': comp_prod.name,
                        'product_qty': qty,
                        'uom_id': comp_prod.uom_id.id,
                        'price_unit': price,
                        'date_planned': now_dt - timedelta(days=1),
                    }))
            if po_lines:
                try:
                    po = PurchaseOrder.create({
                        'partner_id': v_meat.id,
                        'partner_ref': po_ref,
                        'origin': po_ref,
                        'company_id': company.id,
                        'date_order': now_dt - timedelta(days=2),
                        'order_line': po_lines,
                    })
                    po.button_confirm()
                    for picking in po.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel')):
                        picking.origin = po_ref
                        for move in picking.move_ids:
                            move.origin = po_ref
                            move.quantity = move.product_uom_qty
                            move.picked = True
                        picking.with_context(skip_backorder=True).button_validate()
                except Exception as e:
                    _logger.warning("Hudson Inventory Suite: Could not complete demo PO receipt: %s", e)

    # -------------------------------------------------------------------------
    #    b) Internal Transfer (Dry Store -> Kitchen)
    # -------------------------------------------------------------------------
    if 'stock.picking' in env and loc_dry and loc_kitchen:
        Picking = env['stock.picking'].sudo()
        PickingType = env['stock.picking.type'].sudo()
        int_origin = 'HINV-INT-DRY-TO-KITCHEN'
        existing_int = Picking.search([('origin', '=', int_origin)], limit=1)
        if not existing_int:
            int_type = warehouse.int_type_id if (warehouse and warehouse.int_type_id) else PickingType.search([
                ('code', '=', 'internal'),
                ('company_id', '=', company.id),
            ], limit=1)
            if int_type:
                move_specs = [
                    ('HINV-ING-BUN', 15.0),
                    ('HINV-ING-SPG', 4.0),
                    ('HINV-ING-COFF', 1.0),
                    ('HINV-PKG-CUP', 20.0),
                    ('HINV-PKG-BOX', 25.0),
                ]
                moves_vals = []
                for code, qty in move_specs:
                    comp_prod = products_by_code.get(code)
                    if comp_prod:
                        moves_vals.append((0, 0, {
                            'product_id': comp_prod.id,
                            'uom_id': comp_prod.uom_id.id,
                            'product_uom_qty': qty,
                            'location_id': loc_dry.id,
                            'location_dest_id': loc_kitchen.id,
                            'origin': int_origin,
                            'company_id': company.id,
                        }))
                if moves_vals:
                    try:
                        int_pick = Picking.create({
                            'picking_type_id': int_type.id,
                            'location_id': loc_dry.id,
                            'location_dest_id': loc_kitchen.id,
                            'origin': int_origin,
                            'company_id': company.id,
                            'move_ids': moves_vals,
                        })
                        int_pick.action_confirm()
                        int_pick.action_assign()
                        for move in int_pick.move_ids:
                            move.quantity = move.product_uom_qty
                            move.picked = True
                        int_pick.with_context(skip_backorder=True).button_validate()
                    except Exception as e:
                        _logger.warning("Hudson Inventory Suite: Could not validate internal transfer: %s", e)

    # -------------------------------------------------------------------------
    #    c) Scrap record (Odoo 20 stock.move with is_scrap=True) - Fresh Salmon wastage
    # -------------------------------------------------------------------------
    if 'stock.move' in env and loc_cold:
        StockMove = env['stock.move'].sudo()
        scrap_origin = 'HINV-SCRAP-SALMON'
        salmon_prod = products_by_code.get('HINV-ING-SALM')
        if salmon_prod and not StockMove.search([('origin', '=', scrap_origin), ('is_scrap', '=', True)], limit=1):
            scrap_loc = company.scrap_location_id or env['stock.location'].sudo().search([
                ('usage', '=', 'inventory'),
                ('scrap_location', '=', True),
                ('company_id', 'in', [company.id, False]),
            ], limit=1)
            if scrap_loc:
                try:
                    scrap_vals = {
                        'product_id': salmon_prod.id,
                        'uom_id': salmon_prod.uom_id.id,
                        'product_uom_qty': 1.0,
                        'quantity': 1.0,
                        'location_id': loc_cold.id,
                        'location_dest_id': scrap_loc.id,
                        'is_scrap': True,
                        'origin': scrap_origin,
                        'company_id': company.id,
                    }
                    if 'stock.scrap.reason.tag' in env:
                        tag = env['stock.scrap.reason.tag'].sudo().search([('name', '=', 'Spoilage / Expiry')], limit=1)
                        if not tag:
                            tag = env['stock.scrap.reason.tag'].sudo().create({'name': 'Spoilage / Expiry'})
                        scrap_vals['scrap_reason_tag_ids'] = [(4, tag.id)]
                    scrap_move = StockMove.create(scrap_vals)
                    scrap_move.action_scrap()
                except Exception as e:
                    _logger.warning("Hudson Inventory Suite: Could not record Fresh Salmon scrap move: %s", e)

    _logger.info("Hudson Inventory Suite: Restaurant & cafe inventory demo data loaded successfully.")
    return True


def clear_inventory_suite_demo_data(env):
    """
    Safely removes or archives ONLY records created with the HINV- marker.
    Existing Restaurant & Cafe POS products are strictly preserved.
    """
    _logger.info("Hudson Inventory Suite: Cleaning up HINV- demo records...")

    # 1. Remove HINV- BoMs (before products)
    if 'mrp.bom' in env:
        try:
            with env.cr.savepoint():
                boms = env['mrp.bom'].sudo().with_context(active_test=False).search([
                    ('code', 'like', f'{HINV_PREFIX}BOM-%')
                ])
                if boms:
                    if 'mrp.production' in env:
                        mos = env['mrp.production'].sudo().search([('bom_id', 'in', boms.ids)])
                        for mo in mos.filtered(lambda m: m.state not in ('done', 'cancel')):
                            try:
                                mo.action_cancel()
                            except Exception:
                                pass
                        try:
                            mos.filtered(lambda m: m.state in ('draft', 'cancel')).unlink()
                        except Exception:
                            pass
                    try:
                        boms.unlink()
                    except Exception:
                        boms.write({'active': False})
        except Exception as e:
            _logger.warning("Hudson Inventory Suite: Could not clear HINV BoMs: %s", e)

    # 2. Remove HINV- reordering rules
    if 'stock.warehouse.orderpoint' in env:
        try:
            with env.cr.savepoint():
                ops = env['stock.warehouse.orderpoint'].sudo().with_context(active_test=False).search([
                    ('name', 'like', f'{HINV_PREFIX}OP-%')
                ])
                if ops:
                    try:
                        ops.unlink()
                    except Exception:
                        ops.write({'active': False})
        except Exception as e:
            _logger.warning("Hudson Inventory Suite: Could not clear HINV orderpoints: %s", e)

    # 3. Clean up HINV- POs and Pickings / draft moves
    if 'purchase.order' in env:
        try:
            with env.cr.savepoint():
                pos = env['purchase.order'].sudo().search([('partner_ref', 'like', f'{HINV_PREFIX}PO-%')])
                for po in pos:
                    try:
                        if po.state in ('draft', 'sent', 'to approve'):
                            po.button_cancel()
                            po.unlink()
                    except Exception:
                        pass
        except Exception as e:
            _logger.warning("Hudson Inventory Suite: Could not clear HINV purchase orders: %s", e)

    if 'stock.picking' in env:
        try:
            with env.cr.savepoint():
                picks = env['stock.picking'].sudo().search([('origin', 'like', f'{HINV_PREFIX}%')])
                for pick in picks:
                    if pick.state not in ('done', 'cancel'):
                        try:
                            pick.action_cancel()
                            pick.unlink()
                        except Exception:
                            pass
        except Exception as e:
            _logger.warning("Hudson Inventory Suite: Could not clear HINV pickings: %s", e)

    # 4. Identify HINV- products strictly by HINV- default_code
    hinv_products = env['product.product'].sudo().with_context(active_test=False).search([
        ('default_code', 'like', f'{HINV_PREFIX}%')
    ]) if 'product.product' in env else False
    hinv_tmpls = env['product.template'].sudo().with_context(active_test=False).search([
        ('default_code', 'like', f'{HINV_PREFIX}%')
    ]) if 'product.template' in env else False
    if hinv_products:
        hinv_tmpls |= hinv_products.mapped('product_tmpl_id')

    # Clear supplierinfo created for HINV- vendors (covers ingredients, packaging & POS drinks)
    if 'product.supplierinfo' in env:
        try:
            with env.cr.savepoint():
                hinv_vendors = env['res.partner'].sudo().with_context(active_test=False).search([
                    ('ref', 'like', f'{HINV_PREFIX}VND-%')
                ])
                if hinv_vendors:
                    env['product.supplierinfo'].sudo().search([('partner_id', 'in', hinv_vendors.ids)]).unlink()
        except Exception as e:
            _logger.warning("Hudson Inventory Suite: Could not clear HINV supplierinfo: %s", e)

    # Clear quants ONLY for HINV- products (never touch POS products)
    if hinv_products and 'stock.quant' in env:
        try:
            with env.cr.savepoint():
                quants = env['stock.quant'].sudo().search([('product_id', 'in', hinv_products.ids)])
                if quants:
                    quants.unlink()
        except Exception as e:
            _logger.warning("Hudson Inventory Suite: Could not clear HINV quants: %s", e)

    # Unlink HINV- product templates individually, archive if referenced by done moves/PO lines
    if hinv_tmpls:
        Move = env['stock.move'].sudo() if 'stock.move' in env else None
        POLine = env['purchase.order.line'].sudo() if 'purchase.order.line' in env else None
        for tmpl in hinv_tmpls:
            var_ids = tmpl.with_context(active_test=False).product_variant_ids.ids
            has_history = bool(
                (Move is not None and var_ids and Move.search_count([('product_id', 'in', var_ids)], limit=1))
                or (POLine is not None and var_ids and POLine.search_count([('product_id', 'in', var_ids)], limit=1))
            )
            if has_history:
                try:
                    with env.cr.savepoint():
                        tmpl.write({'active': False, 'purchase_ok': False})
                except Exception:
                    pass
                continue
            try:
                with env.cr.savepoint():
                    tmpl.unlink()
            except Exception:
                try:
                    with env.cr.savepoint():
                        tmpl.write({'active': False, 'purchase_ok': False})
                except Exception:
                    pass

    # 5. Remove or archive HINV- locations
    if 'stock.location' in env:
        locs = env['stock.location'].sudo().with_context(active_test=False).search([
            ('barcode', 'like', f'{HINV_PREFIX}LOC-%')
        ])
        Move = env['stock.move'].sudo() if 'stock.move' in env else None
        Picking = env['stock.picking'].sudo() if 'stock.picking' in env else None
        for loc in locs:
            has_history = bool(
                (Move is not None and Move.search_count(['|', ('location_id', '=', loc.id), ('location_dest_id', '=', loc.id)], limit=1))
                or (Picking is not None and Picking.search_count(['|', ('location_id', '=', loc.id), ('location_dest_id', '=', loc.id)], limit=1))
            )
            if has_history:
                try:
                    with env.cr.savepoint():
                        loc.write({'active': False})
                except Exception:
                    pass
                continue
            try:
                with env.cr.savepoint():
                    loc.unlink()
            except Exception:
                try:
                    with env.cr.savepoint():
                        loc.write({'active': False})
                except Exception:
                    pass

    # 6. Remove or archive HINV- vendors
    vendors = env['res.partner'].sudo().with_context(active_test=False).search([
        ('ref', 'like', f'{HINV_PREFIX}VND-%')
    ])
    PO = env['purchase.order'].sudo() if 'purchase.order' in env else None
    for vendor in vendors:
        has_history = bool(PO is not None and PO.search_count([('partner_id', '=', vendor.id)], limit=1))
        if has_history:
            try:
                with env.cr.savepoint():
                    vendor.write({'active': False})
            except Exception:
                pass
            continue
        try:
            with env.cr.savepoint():
                vendor.unlink()
        except Exception:
            try:
                with env.cr.savepoint():
                    vendor.write({'active': False})
            except Exception:
                pass

    # 7. Clean up empty Resto / Ingredients & Resto / Packaging categories
    if 'product.category' in env:
        cat_resto = env['product.category'].sudo().search([('name', '=', 'Resto'), ('parent_id', '=', False)], limit=1)
        if cat_resto:
            for sub_name in ('Ingredients', 'Packaging'):
                sub_cat = env['product.category'].sudo().search([
                    ('name', '=', sub_name), ('parent_id', '=', cat_resto.id)
                ], limit=1)
                if sub_cat:
                    try:
                        with env.cr.savepoint():
                            sub_cat.unlink()
                    except Exception:
                        pass
            if not cat_resto.child_id:
                try:
                    with env.cr.savepoint():
                        cat_resto.unlink()
                except Exception:
                    pass

    _logger.info("Hudson Inventory Suite: Cleanup complete.")
    return True

