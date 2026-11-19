# -*- coding: utf-8 -*-
import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """The "no resource configured" guard is removed: celebration types without a
    resource are no longer blocked (404) on the website. Re-publish the types the
    old guard unpublished automatically (recognised by its chatter message)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    messages = env['mail.message'].sudo().search([
        ('model', '=', 'appointment.type'),
        ('body', 'ilike', 'Unpublished from the website because no resource'),
    ])
    types = env['appointment.type'].sudo().with_context(active_test=False).browse(
        set(messages.mapped('res_id'))).exists().filtered(lambda t: t.active and not t.is_published)
    if types:
        types.write({'is_published': True})
    _logger.info("hudson_pos_booking 20.0.1.3.2 migration: re-published %s appointment type(s): %s",
                 len(types), ', '.join(types.mapped('name')))
