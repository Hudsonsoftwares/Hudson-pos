# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Planned jobs without technician are now an open shift of the schedule
    (they had none): create it."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env['field.service.order'].search([
        ('employee_id', '=', False),
        ('extra_employee_ids', '=', False),
        ('date_planned', '!=', False),
        ('state', '!=', 'cancelled'),
    ])
    orders._sync_planning_slots()
