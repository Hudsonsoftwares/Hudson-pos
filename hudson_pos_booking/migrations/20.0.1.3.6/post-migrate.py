# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Keep the Pre-Order Food section visible on the website for appointment
    types that already showed it: enable 'Pre-Food Required' on every type
    used by a Point of Sale for Table Booking. Admins can untick it afterwards."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    types = env['pos.config'].sudo().with_context(active_test=False).search([
        ('use_booking', '=', True),
    ]).mapped('booking_appointment_type_id').filtered(lambda t: t.booking_target == 'resources')
    if types:
        types.write({'pre_food_required': True})
    _logger.info("hudson_pos_booking 20.0.1.3.6: enabled Pre-Food Required on %s Table Booking types.", len(types))
