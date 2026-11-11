# -*- coding: utf-8 -*-
import logging
from odoo import models
from ..services.uae_pension_service import UAEPensionCalculationService

_logger = logging.getLogger(__name__)

# Module-level transient cache: key = (payslip_id, employee_id, date_to)
_PENSION_CACHE = {}


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _get_localization_context(self, localdict):
        """
        UAE payroll localization extension point.
        Injects centralized UAEPensionCalculationService into evaluation context.
        """
        localdict = super()._get_localization_context(localdict)
        localdict['uae_pension_service'] = UAEPensionCalculationService(self.env)
        localdict['localdict'] = localdict
        return localdict

    def _get_uae_pension_calculation(self, localdict=None):
        """
        Master calculation invocation with transient caching.
        Guarantees single execution per payslip run between SIEC and SICC.
        """
        emp = (localdict and localdict.get('employee')) or self.employee_id
        cache_key = (self.id or 0, emp.id if emp else 0, str(self.date_to or ''))

        # 1. Check transient module cache
        if cache_key in _PENSION_CACHE:
            cached = _PENSION_CACHE[cache_key]
            _logger.info(
                "[UAE_PENSION_TRACE] [CACHE HIT] Reusing cached calculation on payslip %s (Status: %s)",
                self.name or self.id, cached.get('status')
            )
            return cached

        # 2. Check localdict cache if passed
        if localdict and isinstance(localdict, dict) and 'uae_pension_result' in localdict:
            cached = localdict['uae_pension_result']
            if cached and isinstance(cached, dict):
                return cached

        service = (localdict and localdict.get('uae_pension_service')) or UAEPensionCalculationService(self.env)
        contract = (localdict and localdict.get('contract')) or self.contract_id

        res = service.calculate_pension(
            employee=emp,
            payslip=self,
            contract=contract,
            localdict=localdict,
            eval_date=self.date_to
        )
        if cache_key[0]:
            _PENSION_CACHE[cache_key] = res
        if localdict and isinstance(localdict, dict):
            localdict['uae_pension_result'] = res
        return res

    def hds_ae_compute_pension_siec(self, localdict=None):
        """
        Calculates and returns the UAE Social Insurance Employee Contribution (SIEC).
        Returns positive amount (salary rule will negate to form DED).
        """
        self.ensure_one()
        _logger.info(
            "[UAE_PENSION_TRACE] [RULE: SIEC] Evaluating Employee Contribution for payslip '%s'...",
            self.name or self.id
        )
        res = self._get_uae_pension_calculation(localdict=localdict)
        amount = float(res.get('employee_contribution', 0.0))
        _logger.info(
            "[UAE_PENSION_TRACE] [RULE: SIEC] Result: %.2f AED (Status: %s)",
            amount, res.get('status')
        )
        return amount

    def hds_ae_compute_pension_sicc(self, localdict=None):
        """
        Calculates and returns the UAE Social Insurance Company Contribution (SICC).
        Returns positive amount (employer cost in category COMP, does not reduce NET).
        """
        self.ensure_one()
        _logger.info(
            "[UAE_PENSION_TRACE] [RULE: SICC] Evaluating Employer Contribution for payslip '%s'...",
            self.name or self.id
        )
        res = self._get_uae_pension_calculation(localdict=localdict)
        amount = float(res.get('employer_contribution', 0.0))
        _logger.info(
            "[UAE_PENSION_TRACE] [RULE: SICC] Result: %.2f AED (Status: %s)",
            amount, res.get('status')
        )
        return amount

    def compute_sheet(self):
        """Standard alias for action_compute_sheet."""
        return self.action_compute_sheet()
