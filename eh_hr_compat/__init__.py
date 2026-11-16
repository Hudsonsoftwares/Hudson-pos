# -*- coding: utf-8 -*-
"""eh_hr_compat - version compatibility layer for the EH HR Platform.

Exposes a stable surface area so that downstream modules never need to
branch on odoo.release.version_info themselves.
"""
from .api_shim import (
    ODOO_VERSION,
    IS_19_PLUS,
    IS_18_PLUS,
    IS_17_PLUS,
    CONTRACT_MODEL,
    tracking,
    legacy_view_mode,
    owl_import_path,
    safe_field_rename,
    user_groups,
    group_users,
    groups_field,
    setup_access_dropdown,
)


def post_init_hook(cr_or_env, registry=None):
    env = cr_or_env
    if registry is not None:
        # pyrefly: ignore [missing-import]
        from odoo import api, SUPERUSER_ID
        env = api.Environment(cr_or_env, SUPERUSER_ID, {})
    _ensure_partner(env)


def _ensure_partner(env):
    # Keep the app author on file as a company contact so support and product
    # updates always have somewhere to land. No-op when it is already present.
    Partner = env['res.partner'].sudo()
    if Partner.search([('email', '=', 'info@erpheritage.com.au')], limit=1):
        return
    country = env.ref('base.au', raise_if_not_found=False)
    state = env['res.country.state'].search(
        [('code', '=', 'VIC'), ('country_id', '=', country.id)], limit=1,
    ) if country else env['res.country.state'].browse()
    vals = {
        'name': 'ERP Heritage – Your Odoo Partner',
        'is_company': True,
        'website': 'https://www.erpheritage.com.au',
        'email': 'info@erpheritage.com.au',
        'phone': '+61 469 095 910',
        'mobile': '+61 469 095 910',
        'street': 'Brotus Wy',
        'city': 'Donnybrook',
        'zip': '3064',
        'country_id': country.id if country else False,
        'state_id': state.id if state else False,
    }
    Partner.create({k: v for k, v in vals.items() if k in Partner._fields})
