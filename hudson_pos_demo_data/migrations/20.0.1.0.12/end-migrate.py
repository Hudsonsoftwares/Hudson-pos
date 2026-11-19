# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Load the Resto Cafe Solutions Sales demo data (catering quotations and orders) on existing installs."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        from odoo.addons.hudson_pos_demo_data.models.demo_sales_suite import (
            load_sales_suite_demo_data,
        )
        load_sales_suite_demo_data(env)
    except Exception as e:
        _logger.exception("Could not load Sales demo data during migration: %s", e)


# Added in 20.0.1.0.23: never modify or delete records that existed before this upgrade
# (data the user may have changed); only new demo records and newly added fields are written.
_hudson_unguarded_migrate = migrate


def migrate(cr, version):
    from odoo import api as _api, SUPERUSER_ID as _SUPERUSER_ID
    from odoo.addons.hudson_pos_demo_data.models.demo_guard import protect_existing
    with protect_existing(_api.Environment(cr, _SUPERUSER_ID, {})):
        _hudson_unguarded_migrate(cr, version)
