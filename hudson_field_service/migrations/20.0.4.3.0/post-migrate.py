# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """The primary technician of a job is not also one of its extra technicians."""
    cr.execute("""
        SELECT DISTINCT o.id
          FROM field_service_order o
          JOIN field_service_order_extra_employees_rel r
            ON r.order_id = o.id AND r.employee_id = o.employee_id
    """)
    order_ids = [row[0] for row in cr.fetchall()]
    if order_ids:
        env = api.Environment(cr, SUPERUSER_ID, {})
        orders = env['field.service.order'].browse(order_ids)
        orders._remove_primary_from_extra_technicians()
        orders._sync_planning_slots()
