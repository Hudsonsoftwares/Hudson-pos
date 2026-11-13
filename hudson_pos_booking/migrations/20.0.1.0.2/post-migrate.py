# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Unlink orphaned default-floor tables from website booking and rescue trapped bookings onto active POS tables."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    res = env['restaurant.table'].sudo()._cleanup_orphaned_tables_and_rescue_bookings()
    _logger.info(
        "hudson_pos_booking 20.0.1.0.2 migration: cleaned up orphaned booking tables (rescued=%s).",
        res.get('rescued_bookings', 0),
    )

