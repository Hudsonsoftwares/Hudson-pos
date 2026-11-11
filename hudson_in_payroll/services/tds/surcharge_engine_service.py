# -*- coding: utf-8 -*-
import logging
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class SurchargeEngineResult:
    """
    Data Transfer Object (DTO) holding surcharge computation details,
    including statutory marginal relief breakdown.
    """
    def __init__(self, net_taxable_income, tax_after_rebate, surcharge_rate_pct,
                 surcharge_amount, tax_plus_surcharge,
                 surcharge_before_relief=0.0, marginal_relief=0.0,
                 is_applicable=False, threshold=0.0):
        self.net_taxable_income = net_taxable_income
        self.tax_after_rebate = tax_after_rebate
        self.surcharge_rate_pct = surcharge_rate_pct
        self.surcharge_before_relief = surcharge_before_relief
        self.marginal_relief = marginal_relief
        self.surcharge_amount = surcharge_amount  # Final surcharge after marginal relief
        self.tax_plus_surcharge = tax_plus_surcharge
        self.is_applicable = is_applicable
        self.threshold = threshold

    @property
    def surcharge(self):
        """Final surcharge amount after marginal relief."""
        return self.surcharge_amount

    @property
    def surcharge_rate(self):
        """Applicable surcharge rate percentage."""
        return self.surcharge_rate_pct

    def to_dict(self):
        return {
            'net_taxable_income': self.net_taxable_income,
            'tax_after_rebate': self.tax_after_rebate,
            'surcharge_rate_pct': self.surcharge_rate_pct,
            'surcharge_before_relief': self.surcharge_before_relief,
            'marginal_relief': self.marginal_relief,
            'surcharge': self.surcharge_amount,
            'surcharge_amount': self.surcharge_amount,
            'tax_plus_surcharge': self.tax_plus_surcharge,
            'is_applicable': self.is_applicable,
            'threshold': self.threshold,
        }


class SurchargeEngineService(BaseStatutoryService):
    """
    Phase 4 Pipeline Service: Surcharge Engine Service.
    Resolves range-based surcharge percentage bands from tds.surcharge for the Financial Year & Tax Regime.
    Applies surcharge to total income tax after Section 87A rebate and evaluates statutory marginal relief.
    """

    def calculate_surcharge(self, net_taxable_income, tax_after_rebate, financial_year, regime_code, age_category='general'):
        """
        Calculates income tax surcharge with statutory marginal relief.

        :param net_taxable_income: float (Net Taxable Income)
        :param tax_after_rebate: float (Tax liability after Section 87A rebate)
        :param financial_year: tds.financial.year record
        :param regime_code: str ('old' or 'new')
        :param age_category: str ('general', 'senior', or 'super_senior') for consistent slab resolution
        :return: SurchargeEngineResult
        """
        net_taxable_income = float(net_taxable_income or 0.0)
        tax_after_rebate = float(tax_after_rebate or 0.0)

        if tax_after_rebate <= 0 or net_taxable_income <= 0:
            return SurchargeEngineResult(
                net_taxable_income=net_taxable_income,
                tax_after_rebate=0.0,
                surcharge_rate_pct=0.0,
                surcharge_amount=0.0,
                tax_plus_surcharge=0.0,
                surcharge_before_relief=0.0,
                marginal_relief=0.0,
                is_applicable=False,
                threshold=0.0
            )

        regime_code = (regime_code or 'new').lower()

        # Query surcharge slabs from master ordered by income_from asc
        surcharges = self.env['tds.surcharge'].search([
            ('financial_year_id', '=', financial_year.id),
            ('regime_code', '=', regime_code)
        ], order='income_from asc, sequence asc') if (financial_year and hasattr(self.env, 'get')) or hasattr(self.env, '__getitem__') else []

        if not surcharges:
            try:
                surcharges = self.env['tds.surcharge'].search([
                    ('financial_year_id', '=', financial_year.id),
                    ('regime_code', '=', regime_code)
                ], order='income_from asc, sequence asc')
            except Exception:
                surcharges = []

        if not surcharges:
            surcharges = self._get_fallback_surcharges(financial_year, regime_code)

        applicable_slab = None
        prev_slab = None

        for idx, s in enumerate(surcharges):
            inc_from = float(s.income_from or 0.0)
            inc_to = float(s.income_to or 0.0) if float(s.income_to or 0.0) > 0.0 else float('inf')

            # Boundary rules:
            # Surcharge applies when taxable income EXCEEDS threshold (inc_from < net_taxable_income <= inc_to).
            # The base 0% tier applies for 0 <= net_taxable_income <= inc_to.
            if inc_from == 0.0:
                if 0.0 <= net_taxable_income <= inc_to:
                    applicable_slab = s
                    break
            else:
                if inc_from < net_taxable_income <= inc_to:
                    applicable_slab = s
                    if idx > 0:
                        prev_slab = surcharges[idx - 1]
                    break

        if applicable_slab is None and net_taxable_income > 0 and surcharges:
            # Income exceeds highest slab upper bound
            applicable_slab = surcharges[-1]
            if len(surcharges) > 1:
                prev_slab = surcharges[-2]

        surcharge_rate = float(applicable_slab.surcharge_rate or 0.0) if applicable_slab else 0.0

        if not applicable_slab or surcharge_rate <= 0.0:
            return SurchargeEngineResult(
                net_taxable_income=net_taxable_income,
                tax_after_rebate=tax_after_rebate,
                surcharge_rate_pct=0.0,
                surcharge_amount=0.0,
                tax_plus_surcharge=tax_after_rebate,
                surcharge_before_relief=0.0,
                marginal_relief=0.0,
                is_applicable=False,
                threshold=0.0
            )

        # ── Step 1: Calculate Surcharge Before Marginal Relief ────────────────
        surcharge_before_relief = round(tax_after_rebate * (surcharge_rate / 100.0), 2)
        tax_plus_surcharge_before_relief = round(tax_after_rebate + surcharge_before_relief, 2)

        # ── Step 2: Marginal Relief Calculation ───────────────────────────────
        threshold = float(applicable_slab.income_from or 0.0)
        excess_income = max(0.0, round(net_taxable_income - threshold, 2))

        # Calculate base tax at threshold using IncomeTaxSlabService
        from .income_tax_slab_service import IncomeTaxSlabService
        slab_svc = IncomeTaxSlabService(self.env)
        tax_at_threshold_calc = slab_svc.calculate_base_tax(threshold, financial_year, regime_code, age_category=age_category)
        tax_at_threshold = float(tax_at_threshold_calc.base_tax_liability or 0.0)

        # Surcharge rate applicable at threshold is derived from the preceding slab
        prev_surcharge_rate = float(prev_slab.surcharge_rate or 0.0) if prev_slab else 0.0
        surcharge_at_threshold = round(tax_at_threshold * (prev_surcharge_rate / 100.0), 2)
        total_tax_at_threshold = round(tax_at_threshold + surcharge_at_threshold, 2)

        # Statutory ceiling: Tax + Surcharge cannot exceed (Total Tax at Threshold + Excess Income)
        max_tax_plus_surcharge = round(total_tax_at_threshold + excess_income, 2)

        if tax_plus_surcharge_before_relief > max_tax_plus_surcharge:
            marginal_relief = round(tax_plus_surcharge_before_relief - max_tax_plus_surcharge, 2)
        else:
            marginal_relief = 0.0

        # Cap marginal relief so final surcharge never becomes negative
        marginal_relief = min(marginal_relief, surcharge_before_relief)
        final_surcharge = max(0.0, round(surcharge_before_relief - marginal_relief, 2))
        tax_plus_surcharge = round(tax_after_rebate + final_surcharge, 2)

        summary_log = f"""
========================================================
SURCHARGE ENGINE SERVICE (WITH MARGINAL RELIEF)
========================================================
Net Taxable Income          : ₹{net_taxable_income:,.2f}
Tax Before Surcharge        : ₹{tax_after_rebate:,.2f}
Applicable Surcharge Tier   : {surcharge_rate}% (Threshold: ₹{threshold:,.2f})
Surcharge Before Relief     : ₹{surcharge_before_relief:,.2f}
--------------------------------------------------------
Tax at Threshold            : ₹{tax_at_threshold:,.2f}
Surcharge at Threshold      : ₹{surcharge_at_threshold:,.2f} ({prev_surcharge_rate}%)
Excess Income Over Slab     : ₹{excess_income:,.2f}
Maximum Allowable Tax + Sur : ₹{max_tax_plus_surcharge:,.2f}
Tax + Sur Before Relief     : ₹{tax_plus_surcharge_before_relief:,.2f}
Marginal Relief Amount      : ₹{marginal_relief:,.2f}
--------------------------------------------------------
Final Surcharge Amount      : ₹{final_surcharge:,.2f}
Tax Plus Final Surcharge    : ₹{tax_plus_surcharge:,.2f}
========================================================
"""
        _logger.warning(summary_log)

        return SurchargeEngineResult(
            net_taxable_income=net_taxable_income,
            tax_after_rebate=tax_after_rebate,
            surcharge_rate_pct=surcharge_rate,
            surcharge_amount=final_surcharge,
            tax_plus_surcharge=tax_plus_surcharge,
            surcharge_before_relief=surcharge_before_relief,
            marginal_relief=marginal_relief,
            is_applicable=True,
            threshold=threshold
        )

    def _get_fallback_surcharges(self, financial_year, regime_code):
        """Standard statutory fallback surcharge slabs if unseeded."""
        class DummySurcharge:
            def __init__(self, income_from, income_to, surcharge_rate, regime_code):
                self.income_from = income_from
                self.income_to = income_to
                self.surcharge_rate = surcharge_rate
                self.regime_code = regime_code

        regime_code = (regime_code or 'new').lower()
        if regime_code == 'new':
            return [
                DummySurcharge(0.0, 5000000.0, 0.0, 'new'),
                DummySurcharge(5000000.0, 10000000.0, 10.0, 'new'),
                DummySurcharge(10000000.0, 20000000.0, 15.0, 'new'),
                DummySurcharge(20000000.0, 0.0, 25.0, 'new'),
            ]
        else:
            return [
                DummySurcharge(0.0, 5000000.0, 0.0, 'old'),
                DummySurcharge(5000000.0, 10000000.0, 10.0, 'old'),
                DummySurcharge(10000000.0, 20000000.0, 15.0, 'old'),
                DummySurcharge(20000000.0, 50000000.0, 25.0, 'old'),
                DummySurcharge(50000000.0, 0.0, 37.0, 'old'),
            ]
        class DummySurcharge:
            def __init__(self, income_from, income_to, surcharge_rate, regime_code):
                self.income_from = income_from
                self.income_to = income_to
                self.surcharge_rate = surcharge_rate
                self.regime_code = regime_code

        regime_code = (regime_code or 'new').lower()
        if regime_code == 'new':
            return [
                DummySurcharge(0.0, 5000000.0, 0.0, 'new'),
                DummySurcharge(5000000.0, 10000000.0, 10.0, 'new'),
                DummySurcharge(10000000.0, 20000000.0, 15.0, 'new'),
                DummySurcharge(20000000.0, 0.0, 25.0, 'new'),
            ]
        else:
            return [
                DummySurcharge(0.0, 5000000.0, 0.0, 'old'),
                DummySurcharge(5000000.0, 10000000.0, 10.0, 'old'),
                DummySurcharge(10000000.0, 20000000.0, 15.0, 'old'),
                DummySurcharge(20000000.0, 50000000.0, 25.0, 'old'),
                DummySurcharge(50000000.0, 0.0, 37.0, 'old'),
            ]
