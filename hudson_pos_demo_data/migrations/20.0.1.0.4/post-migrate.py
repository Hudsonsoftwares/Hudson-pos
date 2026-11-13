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

