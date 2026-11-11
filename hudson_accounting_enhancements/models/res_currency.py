import logging

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Free, reliable exchange rate API (no API key required) based on ECB data
RATES_URL = 'https://open.er-api.com/v6/latest/EUR'

class ResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.model
    def _fetch_ecb_rates_data(self):
        """
        Fetch ExchangeRate-API JSON feed and return a dict {currency_code: rate_vs_eur}.
        Provides: 1 EUR = rate[currency_code]
        """
        # TLS certificates are verified: these rates feed every multi-currency posting
        try:
            response = requests.get(RATES_URL, headers={'User-Agent': 'Odoo'}, timeout=15)
            response.raise_for_status()
        except requests.RequestException as e:
            raise UserError(
                _('Failed to connect to Exchange Rate server: %s\n'
                  'Please check your internet connection.') % str(e)
            )

        try:
            data = response.json()
        except ValueError as e:
            raise UserError(_('Failed to parse JSON response: %s') % str(e))

        if data.get('result') != 'success':
            raise UserError(_('API returned an error or unsuccessful response.'))

        rates = {code: rate for code, rate in (data.get('rates') or {}).items()
                 if isinstance(rate, (int, float)) and rate > 0}
        if not rates:
            raise UserError(_('Could not find rate data in API feed.'))

        # Ensure EUR is 1.0
        rates['EUR'] = 1.0
        return rates

    @api.model
    def _update_currency_rates(self, company=None):
        """
        Fetch ECB rates and update res.currency.rate for active currencies.

        Odoo rate convention (v16+):
          res.currency.rate.rate = amount of this currency per 1 company currency
          i.e. if company_currency = USD and EUR rate = 0.93, then 1 USD = 0.93 EUR

        ECB gives: 1 EUR = ecb_rate[foreign]
        Conversion formula:
          company_rate_vs_eur = ecb_rate[company_currency]  (or 1.0 if company_currency = EUR)
          odoo_rate[foreign] = ecb_rate[foreign] / company_rate_vs_eur
          (= amount of foreign currency per 1 company_currency)
        """
        if not company:
            # Scheduled action: update every root company; one failure must neither stop
            # the others nor make the cron fail on every run.
            updated = 0
            for root_company in self.env['res.company'].search([('parent_id', '=', False)]):
                try:
                    with self.env.cr.savepoint():
                        updated += self._update_currency_rates(company=root_company)
                except UserError as e:
                    _logger.warning("Currency rate update failed for %s: %s", root_company.name, e)
            return updated

        ecb_rates = self._fetch_ecb_rates_data()

        company_currency = company.currency_id
        company_currency_code = company_currency.name

        # Rate of company currency vs EUR
        if company_currency_code == 'EUR':
            company_vs_eur = 1.0
        elif company_currency_code in ecb_rates:
            company_vs_eur = ecb_rates[company_currency_code]
        else:
            raise UserError(
                _('Your company currency (%s) is not available in the ECB feed. '
                  'ECB provides EUR-based rates. Please set your base currency to EUR '
                  'or a currency listed by ECB.') % company_currency_code
            )

        today = fields.Date.today()
        active_currencies = self.search([('active', '=', True)])
        CurrencyRate = self.env['res.currency.rate']
        updated_count = 0
        skipped = []

        for currency in active_currencies:
            if currency.name not in ecb_rates:
                skipped.append(currency.name)
                continue

            # 1 EUR = ecb_rates[currency.name] units of foreign
            # 1 company_currency = company_vs_eur units of EUR
            #                    = company_vs_eur * ecb_rates[foreign] units of foreign
            # → odoo_rate = ecb_rates[foreign] / company_vs_eur
            odoo_rate = ecb_rates[currency.name] / company_vs_eur

            # Find or create today's rate record
            existing = CurrencyRate.search([
                ('currency_id', '=', currency.id),
                ('name', '=', today),
                ('company_id', '=', company.id),
            ], limit=1)

            rate_vals = {
                'currency_id': currency.id,
                'name': today,
                'rate': odoo_rate,
                'company_id': company.id,
            }

            if existing:
                existing.write({'rate': odoo_rate})
            else:
                CurrencyRate.create(rate_vals)

            updated_count += 1

        if skipped:
            _logger.info(
                'ECB rate update: skipped currencies not in ECB feed: %s',
                ', '.join(skipped)
            )
        _logger.info(
            'ECB rate update complete: %d currencies updated for %s',
            updated_count, today
        )
        return updated_count

    def action_fetch_ecb_rates(self):
        """Button action: manually fetch ECB rates for current company."""
        updated = self._update_currency_rates(company=self.env.company.root_id)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Currency Rates Updated'),
                'message': _(
                    '%d currency rates have been successfully fetched '
                    'from the European Central Bank (ECB) for today.'
                ) % updated,
                'type': 'success',
                'sticky': False,
            },
        }
