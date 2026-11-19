# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
#
# 20.0.1.0.24: fixes demo data that did not load on new databases:
#   * the POS demo needed POS Restaurant + Loyalty (no longer forced as dependencies) -> it now needs
#     only Point of Sale; floors / loyalty programs are added when those apps are installed;
#   * suites creating products with fields of apps not installed (e.g. 'available_in_pos' without
#     Point of Sale) failed as a whole -> such values are now skipped (Sales: quotation templates,
#     headers & footers; FEFO; Purchase; Project; BoMs of the Inventory suite...).
# Those suites were already recorded as loaded, so load everything available once more. This runs
# under demo_guard: records that already exist are never modified or deleted, only missing demo
# records are created.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        with cr.savepoint():
            from odoo.addons.hudson_pos_demo_data.models.demo_autoloader import run_autoload
            loaded = run_autoload(env, force=True)
            env.flush_all()
        _logger.info("Hudson POS demo: reloaded suites after fix: %s", ", ".join(loaded) or "none")
    except Exception as e:
        _logger.exception("Hudson POS demo: reload after fix failed: %s", e)
