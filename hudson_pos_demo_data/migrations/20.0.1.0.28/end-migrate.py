# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    import odoo
    from odoo.addons.hudson_pos_demo_data.models.demo_autoloader import enqueue_suites

    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    # queued, loaded in the background by the scheduled action (never inside the upgrade request)
    _logger.info("Migrating hudson_pos_demo_data to 20.0.1.0.28: queueing marketing, events, blogs demo data...")
    enqueue_suites(env, ['marketing'])
