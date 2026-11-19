# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """The "Allow Website Booking" toggle is removed from the UI: every table is
    bookable online again, so none stays hidden without a way to switch it back."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    tables = env['restaurant.table'].sudo().with_context(active_test=False).search([
        ('allow_website_booking', '=', False),
    ])
    if tables:
        tables.write({'allow_website_booking': True})
    _logger.info("hudson_pos_booking 20.0.1.3.3 migration: website booking enabled on %s table(s).", len(tables))
