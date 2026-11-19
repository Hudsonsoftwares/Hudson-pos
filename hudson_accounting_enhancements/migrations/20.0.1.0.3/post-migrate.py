from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Backfill codes on accounts created codeless by Odoo 20 charts (e.g. l10n_in)."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    for company in env['res.company'].search([('parent_id', '=', False), ('chart_template', '!=', False)]):
        env['account.chart.template']._hudson_assign_missing_account_codes(company)
