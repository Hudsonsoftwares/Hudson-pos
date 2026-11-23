# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
#
# 20.0.1.0.31: the floor plan vectors live only in hudson_pos_theme (the decor library shipped to clients);
# the duplicate copies in this demo module are removed. Floors still pointing at those copies get
# their image urls repointed to the theme, and demo floors on the plain old grid get the decorated plan.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        with cr.savepoint():
            from odoo.addons.hudson_pos_demo_data.models.demo_floor_plan import (
                repoint_floor_plan_images, upgrade_untouched_floor_plans,
            )
            fixed = repoint_floor_plan_images(env)
            upgraded = upgrade_untouched_floor_plans(env)
            env.flush_all()
        _logger.info("Hudson POS demo: floor plan images repointed on: %s; decorated plans applied to: %s",
                     ", ".join(fixed) or "none", ", ".join(upgraded) or "none")
    except Exception as e:
        _logger.exception("Hudson POS demo: floor plan image repair failed: %s", e)
