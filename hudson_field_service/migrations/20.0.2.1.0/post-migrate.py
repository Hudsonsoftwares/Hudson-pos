# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    """Create the planning slots of existing field service orders."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['field.service.order']._resync_all_planning_slots()
