# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Delete the retired Birthday / Anniversary / Win appointment types; their
    bookings, tables and POS configs move to 'Celebrate Your Life Events'."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['appointment.type'].sudo()._ensure_default_event_booking_setup()
    _logger.info("hudson_pos_booking 20.0.1.3.1 migration: retired celebration types removed.")
