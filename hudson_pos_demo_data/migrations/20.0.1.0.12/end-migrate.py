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
