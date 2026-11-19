# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
#
# 20.0.1.0.22: the module now depends only on `base` (auto_install) and loads the demo data of
# apps installed later automatically (models/demo_autoloader.py). On databases that already have
# the demo data, record the apps available now so that only apps installed from now on trigger
# a load. "end-" scripts run after ALL modules are loaded, so every app's models are available.

import logging

from odoo import api, SUPERUSER_ID
from odoo.addons.hudson_pos_demo_data.models.demo_autoloader import _get_state, available_probes, save_state

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    if _get_state(env) is None:
        probes = available_probes(env)
        save_state(env, probes)
        _logger.info("Hudson POS demo: auto-load state initialised with %s available apps/features", len(probes))
