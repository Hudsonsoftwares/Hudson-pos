# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
#
# 20.0.1.0.36: Repair POS combos left without any combo item (combo selection in QR ordering
# opened nothing and priced the combo wrongly). Re-syncs the combo choices only, one item per
# active product variant; nothing else is reloaded.

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    try:
        with cr.savepoint():
            from odoo.addons.hudson_pos_demo_data.models.demo_data_loader import _configure_combos
            _configure_combos(env)
            env.flush_all()
        _logger.info("Hudson POS demo 20.0.1.0.36: POS combo items re-synced.")
    except Exception as e:
        _logger.exception("Hudson POS demo 20.0.1.0.36: combo repair warning: %s", e)
