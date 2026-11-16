# -*- coding: utf-8 -*-
# Part of Hudson POS. See LICENSE file for full copyright and licensing details.
#
# "end-" scripts run after ALL modules are loaded, so every app's models are available.
# Every suite is idempotent (records bound to xmlids), so re-running is safe.

import importlib
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

SUITES = [  # 20.0.1.0.18: Visitor Management, Employee Referral and Appraisals
    ('demo_visitor_suite', 'load_visitor_suite_demo_data'),
    ('demo_referral_suite', 'load_referral_suite_demo_data'),
    ('demo_appraisal_suite', 'load_appraisal_suite_demo_data'),
]


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # demo records trigger assignment/approval notifications; never e-mail them to real users
    cr.execute("SELECT COALESCE(MAX(id), 0) FROM mail_mail")
    last_mail_id = cr.fetchone()[0]
    for module_name, func_name in SUITES:
        try:
            with cr.savepoint():
                module = importlib.import_module(f'odoo.addons.hudson_pos_demo_data.models.{module_name}')
                getattr(module, func_name)(env)
                env.flush_all()
            _logger.info("Hudson POS: %s loaded", module_name)
        except Exception as e:
            _logger.exception("Hudson POS: %s failed during migration: %s", module_name, e)
    try:
        with cr.savepoint():
            queued = env['mail.mail'].sudo().search([('id', '>', last_mail_id), ('state', 'in', ('outgoing', 'exception'))])
            _logger.info("Hudson POS: removing %s e-mails queued by the demo data load", len(queued))
            queued.unlink()
    except Exception as e:
        _logger.exception("Hudson POS: could not clean demo e-mail queue: %s", e)
