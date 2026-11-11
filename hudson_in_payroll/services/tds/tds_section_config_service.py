# -*- coding: utf-8 -*-
from odoo import fields
from ..base import BaseStatutoryService

class TdsSectionConfigService(BaseStatutoryService):
    """
    Centralized Resolution Service for Tax Declaration Section & Sub-Component Configurations.
    Determines UI visibility and regime/date applicability dynamically.
    Does NOT calculate statutory deduction eligibility or monetary caps.
    """

    def get_active_sections(self, regime_code='old', eval_date=None):
        """
        Retrieves active tds.tax.section.config records applicable for the given regime and evaluation date.

        :param regime_code: str ('old' or 'new')
        :param eval_date: date or str (defaults to today)
        :return: recordset of tds.tax.section.config
        """
        if not eval_date:
            eval_date = fields.Date.today()
        elif isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)

        regime_code = (regime_code or 'old').lower()
        regime_domain = [('old_regime_allowed', '=', True)] if regime_code == 'old' else [('new_regime_allowed', '=', True)]

        domain = [
            ('active', '=', True),
            ('effective_from', '<=', eval_date),
            '|',
            ('effective_to', '=', False),
            ('effective_to', '>=', eval_date),
        ] + regime_domain

        return self.env['tds.tax.section.config'].sudo().search(domain, order='sequence, id')

    def get_active_components(self, section_code=None, regime_code='old', eval_date=None):
        """
        Retrieves active tds.tax.component.config records applicable for the given section, regime, and evaluation date.

        :param section_code: str (optional section code filter, e.g. '80C')
        :param regime_code: str ('old' or 'new')
        :param eval_date: date or str
        :return: recordset of tds.tax.component.config
        """
        if not eval_date:
            eval_date = fields.Date.today()
        elif isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)

        regime_code = (regime_code or 'old').lower()
        regime_domain = [('old_regime_allowed', '=', True)] if regime_code == 'old' else [('new_regime_allowed', '=', True)]

        domain = [
            ('active', '=', True),
            ('effective_from', '<=', eval_date),
            '|',
            ('effective_to', '=', False),
            ('effective_to', '>=', eval_date),
        ] + regime_domain

        if section_code:
            domain.append(('section_id.code', '=', section_code))

        return self.env['tds.tax.component.config'].sudo().search(domain, order='sequence, id')

    def is_category_permitted(self, category_code, regime_code='old', eval_date=None):
        """
        Evaluates whether a given declaration category/component code is active and permitted under the specified regime and evaluation date.

        :param category_code: str (e.g. '80c_ppf', '80ccd2')
        :param regime_code: str ('old' or 'new')
        :param eval_date: date or str
        :return: bool
        """
        if not category_code:
            return True

        active_comps = self.get_active_components(regime_code=regime_code, eval_date=eval_date)
        permitted_codes = active_comps.mapped('code')
        
        # Fallback to true if master configuration data is not loaded yet
        if not permitted_codes:
            if (regime_code or 'old').lower() == 'new':
                return category_code.lower() in ('80ccd2', '57iia', '80cch')
            return True

        return category_code.lower() in [c.lower() for c in permitted_codes]
