# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Create 4 Event appointment types, reusable event questions, share tables, and unpublish legacy Table Booking."""
    cr.execute("""
        SELECT table_name, column_name
          FROM information_schema.columns
         WHERE (table_name = 'appointment_question' AND column_name = 'question_role')
            OR (table_name = 'appointment_type' AND column_name = 'is_event_booking')
            OR (table_name = 'appointment_booking' AND column_name = 'celebrant_name')
    """)
    found = set(cr.fetchall())
    required = {
        ('appointment_question', 'question_role'),
        ('appointment_type', 'is_event_booking'),
        ('appointment_booking', 'celebrant_name'),
    }
    if not required.issubset(found):
        raise UserError(_(
            "Please upgrade the 'Appointments' (appointment) module FIRST from Apps, "
            "then upgrade 'POS Table Booking Bridge' (hudson_pos_booking) — "
            "or upgrade both together with '-u appointment,hudson_pos_booking'."
        ))

    env = api.Environment(cr, SUPERUSER_ID, {})
    env['appointment.type'].sudo()._ensure_default_event_booking_setup()
    res = env['restaurant.table'].sudo()._cleanup_orphaned_tables_and_rescue_bookings()
    _logger.info(
        "hudson_pos_booking 20.0.1.0.3 migration: event setup applied (rescued=%s).",
        res.get('rescued_bookings', 0),
    )

