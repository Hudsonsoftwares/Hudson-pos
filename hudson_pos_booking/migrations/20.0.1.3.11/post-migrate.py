# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Types that already have 'Event / Celebration Booking' switched on get the
    celebration questions (Event Type, Special Day Date) and a default emoji."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    types = env['appointment.type'].sudo().with_context(active_test=False).search([('is_event_booking', '=', True)])
    types._hudson_ensure_celebration_setup()
    _logger.info("hudson_pos_booking 20.0.1.3.11: celebration questions ensured on %s types.", len(types))
