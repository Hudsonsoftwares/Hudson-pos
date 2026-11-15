# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Load the Resto Cafe Solutions CRM demo dataset (CRM Suite) on existing installs."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        from odoo.addons.hudson_pos_demo_data.models.demo_crm_suite import (
            load_crm_suite_demo_data,
        )
        load_crm_suite_demo_data(env)
    except Exception as e:
        _logger.exception("Could not load CRM suite demo data during migration: %s", e)
