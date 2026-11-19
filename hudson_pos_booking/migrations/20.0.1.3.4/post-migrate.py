# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Ensure celebration appointment types have company_id = False so they can be
    read and selected across multiple companies without triggering AccessError."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    if 'appointment.type' in env:
        AppType = env['appointment.type'].sudo().with_context(active_test=False)
        types = AppType.search([
            ('is_event_booking', '=', True),
            ('company_id', '!=', False),
        ])
        if types:
            types.write({'company_id': False})
            _logger.info("hudson_pos_booking 20.0.1.3.4 migration: set company_id=False on %s celebration appointment types.", len(types))

        other = env.ref('hudson_pos_booking.appointment_type_event_other', raise_if_not_found=False)
        if other:
            other = other.sudo()
            if other.company_id:
                other.write({'company_id': False})
                _logger.info("hudson_pos_booking 20.0.1.3.4 migration: released appointment_type_event_other to company_id=False.")
