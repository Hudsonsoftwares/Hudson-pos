# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
#
# 20.0.1.0.26: Multi-attribute product variants (Sizes, Flavours, Portions, Pack Sizes)
# across all restaurant, cafe, dessert, and packaged demo products.

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        with cr.savepoint():
            from odoo.addons.hudson_pos_demo_data.models.demo_data_loader import (
                _configure_product_variants,
                _configure_combos,
            )
            _configure_product_variants(env)
            _configure_combos(env)
            env.flush_all()
        _logger.info("Hudson POS demo: 20.0.1.0.26 all product variants and combos successfully migrated.")
    except Exception as e:
        _logger.exception("Hudson POS demo: product variant migration failed: %s", e)
