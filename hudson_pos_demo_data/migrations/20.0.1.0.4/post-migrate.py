# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Load and configure all 6 Loyalty & Discount program types for existing installs."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        with env.cr.savepoint():
            from odoo.addons.hudson_pos_demo_data.models.demo_data_loader import (
                load_pos_demo_data,
            )
            load_pos_demo_data(env)
            _logger.info("Hudson POS: Successfully migrated and loaded all 6 Loyalty & Discount program types.")
    except Exception as e:
        _logger.warning("Could not load Loyalty & Discount demo data during migration: %s", e)



# Added in 20.0.1.0.23: never modify or delete records that existed before this upgrade
# (data the user may have changed); only new demo records and newly added fields are written.
_hudson_unguarded_migrate = migrate


def migrate(cr, version):
    from odoo import api as _api, SUPERUSER_ID as _SUPERUSER_ID
    from odoo.addons.hudson_pos_demo_data.models.demo_guard import protect_existing
    with protect_existing(_api.Environment(cr, _SUPERUSER_ID, {})):
        _hudson_unguarded_migrate(cr, version)
