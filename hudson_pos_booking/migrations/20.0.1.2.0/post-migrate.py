# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Merge the Birthday / Anniversary / Win / Other celebration types into the
    single 'Celebrate Your Life Events' type (Event Type, Special Day Date and
    Special Requests questions). Old types are unpublished, not deleted."""
    cr.execute("""
        UPDATE ir_model_data
           SET noupdate = TRUE
         WHERE module = 'hudson_pos_booking'
           AND name IN ('email_template_celebration_advance', 'email_template_celebration_day')
    """)
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['appointment.type'].sudo()._ensure_default_event_booking_setup()
    _logger.info("hudson_pos_booking 20.0.1.2.0 migration: 'Celebrate Your Life Events' type applied.")
