# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
#
# 20.0.1.0.25: decorated restaurant floor plans (models/demo_floor_plan.py). Existing databases get
# them only for demo floors that still have the plain table grid of the previous versions, i.e.
# floors nobody redrew; a floor plan edited by the user is never replaced.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        with cr.savepoint():
            from odoo.addons.hudson_pos_demo_data.models.demo_floor_plan import upgrade_untouched_floor_plans
            upgraded = upgrade_untouched_floor_plans(env)
            env.flush_all()
        _logger.info("Hudson POS demo: decorated floor plans applied to: %s", ", ".join(upgraded) or "none (floors were edited)")
    except Exception as e:
        _logger.exception("Hudson POS demo: decorated floor plan upgrade failed: %s", e)
