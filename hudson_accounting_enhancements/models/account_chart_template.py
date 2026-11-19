import logging
import re

from odoo import api, models

_logger = logging.getLogger(__name__)

# Template account xmlids carry the account number: ``p10031``, ``p213201``, ``2012``.
_TEMPLATE_CODE_RE = re.compile(r'p?(\d+)')
# Start point for accounts whose xmlid holds no number (or whose number is taken).
_FALLBACK_START_CODE = '999100'


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    def _post_load_data(self, template_code, company, template_data):
        super()._post_load_data(template_code, company, template_data)
        self._hudson_assign_missing_account_codes(company, template_data)

    @api.model
    def _hudson_assign_missing_account_codes(self, company, template_data=None):
        """Give every account of ``company`` that has no code a unique one.

        Odoo 20 ships some charts (e.g. ``l10n_in``) without a ``code`` column,
        so their accounts are created codeless. The number is still in the
        template xmlid (``account.<company>_p10031``); it is normalized the way
        the chart loader normalizes template codes: right-padded with zeros to
        ``code_digits`` (default 6), so ``p10031`` -> ``100310``. A taken or
        missing number falls back to the next free code. Codes are stored on
        the root company, which branches share.
        """
        company = company.root_id
        code_digits = int((template_data or {}).get('code_digits') or 6)
        Account = self.env['account.account'].sudo().with_company(company).with_context(active_test=False)
        company_domain = [('company_ids', 'child_of', company.id)]
        accounts = Account.search([*company_domain, ('code', '=', False)], order='id')
        if not accounts:
            return Account
        used = set(Account.search([*company_domain, ('code', '!=', False)]).mapped('code'))
        prefix = f'{company.id}_'
        xmlids = accounts._get_external_ids()
        for account in accounts:
            code = False
            for xmlid in xmlids.get(account.id, []):
                name = xmlid.split('.', 1)[-1].removeprefix(prefix)
                if match := _TEMPLATE_CODE_RE.fullmatch(name):
                    code = match.group(1).ljust(code_digits, '0')
                    break
            if not code or code in used:
                code = Account._search_new_account_code(code or _FALLBACK_START_CODE, cache=used)
            account.code = code
            used.add(code)
        _logger.info("Assigned default codes to %s codeless accounts of company %s", len(accounts), company.name)
        return accounts
