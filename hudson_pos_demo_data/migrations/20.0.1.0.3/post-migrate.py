# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Populate Restaurant & Cafe Inventory Suite demo data for existing installs."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        with env.cr.savepoint():
            from odoo.addons.hudson_pos_demo_data.models.demo_inventory_suite import (
                load_inventory_suite_demo_data,
            )
            load_inventory_suite_demo_data(env)
    except Exception as e:
        _logger.warning("Could not load Inventory suite demo data during migration: %s", e)

