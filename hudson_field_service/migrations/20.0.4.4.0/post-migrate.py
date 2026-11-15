# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Technicians already assigned to jobs get Field Service / User rights,
    to start their jobs from their shifts (see _grant_technician_access)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env['field.service.order'].search([
        ('state', 'not in', ('done', 'cancelled')),
        '|', ('employee_id', '!=', False), ('extra_employee_ids', '!=', False),
    ])
    orders._grant_technician_access()
