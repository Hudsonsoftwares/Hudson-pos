# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.
"""
eCommerce Suite demo data for Resto Cafe Solutions: packaged food sold on the website.

- "Packaged Foods" shop category with 7 sub-categories (Snacks, Spices, Ready-to-Eat,
  Pickles, Sweets & Bakery, Coffee & Tea, Breakfast Mixes), each with an image
- 25 published products with packaging images, prices, strike-through sale prices,
  Sale / New ribbons, diet tags (Vegan, Gluten-Free...), e-commerce descriptions
  (net weight, shelf life, storage), weights and internal references
- "Pack Size" variants (100 g / 250 g / 500 g / 1 kg) priced per size for spices & beverages
- Alternative products and "frequently bought together" accessories
- Initial warehouse stock with availability shown on the website (one item sold out)

Loaded only when eCommerce (website_sale) is installed. Every record is owned by
hudson_pos_demo_data, so Odoo removes it when the module is uninstalled.
"""

import json
import logging

from odoo.tools import file_open
from .demo_xml import load_demo_xml as convert_file  # tolerant of apps not installed

_logger = logging.getLogger(__name__)

XML_FILE = 'demo/ecommerce/packaged_food_demo.xml'
SETTINGS_FILE = 'hudson_pos_demo_data/demo/ecommerce/packaged_food_settings.json'


def _ref(env, xid):
    return env.ref(f'hudson_pos_demo_data.{xid}', raise_if_not_found=False)


def load_ecommerce_suite_demo_data(env):
    """Load the packaged-food webshop demo data when eCommerce is installed."""
    if 'public_categ_ids' not in env['product.template']._fields:
        _logger.info("Hudson eCommerce Suite: skipped, eCommerce (website_sale) is not installed.")
        return False

    with env.cr.savepoint():
        _bind_existing_by_name(env)
        convert_file(env, 'hudson_pos_demo_data', XML_FILE, idref={}, mode='init', noupdate=True)

    with file_open(SETTINGS_FILE, 'r') as fh:
        settings = json.load(fh)

    with env.cr.savepoint():
        _set_pack_size_prices(env, settings['size_factors'])
        _set_accessories(env, settings['accessories'])
        _show_in_pos_shops(env)
    try:
        with env.cr.savepoint():
            _set_initial_stock(env, settings['stock'])
    except Exception:
        _logger.exception("Hudson eCommerce Suite: could not set initial stock")

    _logger.info("Hudson eCommerce Suite: packaged food webshop demo data loaded.")
    return True


# Records that may already exist with the same (unique) name, e.g. a "Vegetarian" tag from
# the POS demo: link them to our xmlid instead of creating a duplicate (which would fail).
_BIND_BY_NAME = {
    'product.tag': {
        'rc_ptag_veg': 'Vegetarian', 'rc_ptag_vegan': 'Vegan', 'rc_ptag_gf': 'Gluten-Free',
        'rc_ptag_best': 'Bestseller', 'rc_ptag_kerala': 'Kerala Special', 'rc_ptag_gift': 'Gift Pack',
    },
    'product.attribute': {'rc_attr_pack_size': 'Pack Size'},
}


def _bind_existing_by_name(env):
    IMD = env['ir.model.data'].sudo()
    for model, xids in _BIND_BY_NAME.items():
        for xid, name in xids.items():
            if _ref(env, xid):
                continue
            existing = env[model].sudo().search([('name', '=', name)], limit=1)
            if existing:
                IMD.create({
                    'module': 'hudson_pos_demo_data', 'name': xid, 'model': model,
                    'res_id': existing.id, 'noupdate': True,
                })


def _set_pack_size_prices(env, size_factors):
    """Bigger packs cost more: price extra = base price x (size factor - 1)."""
    PTAV = env['product.template.attribute.value'].sudo()
    for value_xid, factor in size_factors.items():
        value = _ref(env, value_xid)
        if not value:
            continue
        for ptav in PTAV.search([('product_attribute_value_id', '=', value.id)]):
            ptav.price_extra = round(ptav.product_tmpl_id.list_price * (factor - 1), 2)


def _set_accessories(env, accessories):
    for tmpl_xid, accessory_xids in accessories.items():
        tmpl = _ref(env, tmpl_xid)
        variants = env['product.product'].browse()
        for a_xid in accessory_xids:
            acc = _ref(env, a_xid)
            if acc:
                variants |= acc.product_variant_ids[:1]
        if tmpl and variants:
            tmpl.accessory_product_ids = [(6, 0, variants.ids)]


def _show_in_pos_shops(env):
    """POS shops that only show selected categories also get the "Packaged Foods" category."""
    category = _ref(env, 'rc_poscat_packaged')
    if not category or 'pos.config' not in env:
        return
    categories = category | category.child_ids
    for config in env['pos.config'].sudo().search([('limit_categories', '=', True)]):
        missing = categories - config.iface_available_categ_ids
        if missing:
            config.iface_available_categ_ids = [(4, c.id) for c in missing]


def _set_initial_stock(env, stock):
    """Put the demo quantities in the main warehouse, only for products that have no stock yet."""
    if 'stock.quant' not in env:
        return
    warehouse = env['stock.warehouse'].sudo().search([('company_id', '=', env.company.id)], limit=1)
    if not warehouse:
        return
    Quant = env['stock.quant'].sudo().with_context(inventory_mode=True)
    for tmpl_xid, qty in stock.items():
        tmpl = _ref(env, tmpl_xid)
        if not tmpl or not qty:
            continue
        variants = tmpl.product_variant_ids
        if any(v.qty_available for v in variants):
            continue  # already stocked (e.g. module upgraded again): never touch real quantities
        for i, variant in enumerate(variants):
            # bigger packs get fewer units
            Quant.create({
                'product_id': variant.id,
                'location_id': warehouse.lot_stock_id.id,
                'inventory_quantity': max(5, round(qty / (i + 1))),
            }).action_apply_inventory()
