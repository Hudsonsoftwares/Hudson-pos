from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """ Delete the former "Fetch ECB Currency Rates" scheduled action: a noupdate record, never deleted by the update
    itself (see pre-currency_tools.py, which moved its schedule to om_currency_rate_update). """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    cron = env.ref('hudson_accounting_enhancements.ir_cron_fetch_ecb_currency_rates', raise_if_not_found=False)
    if cron:
        cron.unlink()
