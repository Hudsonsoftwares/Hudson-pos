# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
#
# 20.0.1.0.32: new 'purchase_agreements' suite (Purchase Templates, Purchase Alternatives and a
# Blanket Order with releases). Databases where Purchase Agreements / Purchase Alternative are already
# installed would not pick it up (its probes are not new), so queue it once. Idempotent: the suite
# only creates missing records bound to rc_pa_ xmlids.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        with cr.savepoint():
            from odoo.addons.hudson_pos_demo_data.models.demo_autoloader import enqueue_suites
            if 'purchase.order' in env:
                enqueue_suites(env, ['purchase_agreements'])
            env.flush_all()
    except Exception as e:
        _logger.exception("Hudson POS demo: could not queue the purchase agreements suite: %s", e)
