from odoo import api, models


class ResCurrency(models.Model):
    """ The exchange rates are updated by om_currency_rate_update only (sources, currencies, interval and maximum
    change of Settings > Accounting > Automatic Currency Rates): these buttons of the currencies run that same
    update. The former ECB / open.er-api.com updater of this module and its scheduled action are removed. """
    _inherit = 'res.currency'

    def action_update_currency_rates(self):
        """ Button of the currencies: update the rates of the current company now """
        return self.env.company.action_update_currency_rates()

    def action_force_update_currency_rates(self):
        """ Button of the currencies: update the rates even when they changed more than the maximum change """
        return self.env.company.action_update_currency_rates(force=True)

    def action_fetch_ecb_rates(self):
        """ Former name of the button, kept for the views and clients not reloaded yet """
        return self.action_update_currency_rates()

    @api.model
    def _update_currency_rates(self, company=None):
        """ Former scheduled action of this module, kept in case it still runs on a database not upgraded yet:
        it runs the scheduled update of om_currency_rate_update, which follows the interval of each company. """
        return self.env['res.company']._cron_update_currency_rates()
