# -*- encoding: utf-8 -*-
from . import models
from . import controllers


def post_init_hook(env_or_cr, registry=None):
    """Assign the attendance-suite groups to a single access-level dropdown.

    The grouping field differs by version (res.groups.privilege on Odoo 19,
    res.groups.category_id on 16 to 18), so it cannot be set in XML portably.
    The compat helper branches on the running version. The hook itself accepts
    both signatures: (cr, registry) on Odoo 16, (env) on 17+.
    """
    # pyrefly: ignore [missing-import]
    from odoo import api, SUPERUSER_ID
    # pyrefly: ignore [missing-import]
    from odoo.addons.eh_hr_compat import setup_access_dropdown
    env = env_or_cr if registry is None \
        else api.Environment(env_or_cr, SUPERUSER_ID, {})
    setup_access_dropdown(
        env, 'ERP Heritage Attendance Suite', 95,
        ['eh_hr_attendance_base.group_eh_hr_user',
         'eh_hr_attendance_base.group_eh_hr_manager',
         'eh_hr_attendance_base.group_eh_hr_admin',
         'eh_hr_attendance_base.group_eh_hr_auditor'])
