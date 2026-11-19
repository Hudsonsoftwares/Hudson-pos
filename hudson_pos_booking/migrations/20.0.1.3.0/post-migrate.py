# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Celebration types now assign tables automatically (no resource picker on
    the website) and are unpublished while no resource is configured."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['appointment.type'].sudo()._ensure_default_event_booking_setup()
    _logger.info("hudson_pos_booking 20.0.1.3.0 migration: resource configuration guard applied.")
