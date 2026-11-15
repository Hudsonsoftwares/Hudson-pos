from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Sign setting "Manage template access" starts off, as in a new database:
    every internal user sees every template."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['res.config.settings']._hudson_sign_open_template_access()
