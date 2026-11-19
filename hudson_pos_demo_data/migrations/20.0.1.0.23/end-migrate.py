# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
#
# 20.0.1.0.23: lot-wise expiration dates on purchases (FEFO suite section 6). Re-run the FEFO suite
# on databases that already have it; it is idempotent, so existing FEFO records are kept.
# "end-" scripts run after ALL modules are loaded, so Purchase's models are available.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    cr.execute("SELECT COALESCE(MAX(id), 0) FROM mail_mail")
    last_mail_id = cr.fetchone()[0]
    try:
        from odoo.addons.hudson_pos_demo_data.models.demo_guard import protect_existing
        with cr.savepoint(), protect_existing(env):
            from odoo.addons.hudson_pos_demo_data.models.demo_fefo_suite import load_fefo_suite_demo_data
            load_fefo_suite_demo_data(env)
            env.flush_all()
    except Exception as e:
        _logger.exception("Hudson POS: FEFO purchase demo failed during migration: %s", e)
    # demo records trigger notifications; never e-mail them to real users
    try:
        with cr.savepoint():
            env['mail.mail'].sudo().search([
                ('id', '>', last_mail_id), ('state', 'in', ('outgoing', 'exception'))]).unlink()
    except Exception as e:
        _logger.exception("Hudson POS: could not clean demo e-mail queue: %s", e)
