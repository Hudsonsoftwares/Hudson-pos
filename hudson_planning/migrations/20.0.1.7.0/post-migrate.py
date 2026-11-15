# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Open shifts for the hours of the confirmed sales orders not assigned yet."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    lines = env['sale.order.line'].search([
        ('state', '=', 'sale'),
        ('product_id.planning_enabled', '=', True),
    ])
    lines._planning_slot_generation()
