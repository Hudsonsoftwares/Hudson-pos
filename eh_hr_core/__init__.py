# -*- coding: utf-8 -*-
from . import models
from . import services


def post_init_hook(cr_or_env, registry=None):
    """Grant the base administrator the HR Platform admin group on install.

    Odoo 19 dropped res.groups.category_id, so the legacy "admin gets the top
    group of each category" auto-grant no longer fires, and a fresh database
    would leave even the administrator unable to open any platform record. We
    wire it explicitly here.

    Signature is version-agnostic: Odoo 16 calls post_init_hook(cr, registry)
    while Odoo 17+ calls post_init_hook(env). The groups relation was also
    renamed in 19 (res.users.groups_id -> group_ids), so the field name is
    resolved through the compat helper. Portable across Odoo 16 to 19.
    """
    if registry is not None:
        from odoo import api, SUPERUSER_ID
        env = api.Environment(cr_or_env, SUPERUSER_ID, {})
    else:
        env = cr_or_env
    admin = env.ref('base.user_admin', raise_if_not_found=False)
    group = env.ref('eh_hr_core.group_hr_admin', raise_if_not_found=False)
    if admin and group:
        from odoo.addons.eh_hr_compat import groups_field
        admin.sudo().write({groups_field(env): [(4, group.id)]})

    # Present the four platform access levels as a single dropdown on the user
    # form (Employee / Manager / Officer / Admin) rather than four checkboxes.
    from odoo.addons.eh_hr_compat import setup_access_dropdown
    setup_access_dropdown(env, 'HR Platform Access', 5, [
        'eh_hr_core.group_hr_employee_self',
        'eh_hr_core.group_hr_manager',
        'eh_hr_core.group_hr_officer',
        'eh_hr_core.group_hr_admin',
    ])
