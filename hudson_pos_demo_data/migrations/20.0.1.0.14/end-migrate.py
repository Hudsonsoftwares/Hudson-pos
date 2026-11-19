# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
# Superseded by migrations/20.0.1.0.16/end-migrate.py, which loads every demo suite once.


def migrate(cr, version):
    pass


# Added in 20.0.1.0.23: never modify or delete records that existed before this upgrade
# (data the user may have changed); only new demo records and newly added fields are written.
_hudson_unguarded_migrate = migrate


def migrate(cr, version):
    from odoo import api as _api, SUPERUSER_ID as _SUPERUSER_ID
    from odoo.addons.hudson_pos_demo_data.models.demo_guard import protect_existing
    with protect_existing(_api.Environment(cr, _SUPERUSER_ID, {})):
        _hudson_unguarded_migrate(cr, version)
