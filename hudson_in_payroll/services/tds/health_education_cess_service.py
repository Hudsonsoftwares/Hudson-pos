# -*- coding: utf-8 -*-
import logging
from ..base import BaseStatutoryService
from .tds_parameter_service import TdsParameterService

_logger = logging.getLogger(__name__)


class HealthEducationCessResult:
    """
    Data Transfer Object (DTO) holding Health & Education Cess and Total Annual Tax Liability details,
    statutorily rounded to the nearest multiple of ten rupees under Section 288B of the Income-tax Act, 1961.
    """
    def __init__(self, tax_plus_surcharge, cess_rate_pct, cess_amount, total_annual_tax_liability,
                 unrounded_annual_tax=None, rounding_factor_288b=0.0):
        self.tax_plus_surcharge = tax_plus_surcharge
        self.cess_rate_pct = cess_rate_pct
        self.cess_amount = cess_amount
        self.total_annual_tax_liability = total_annual_tax_liability
        self.unrounded_annual_tax = unrounded_annual_tax if unrounded_annual_tax is not None else total_annual_tax_liability
        self.rounding_factor_288b = rounding_factor_288b

    @property
    def cess_rate(self):
        """Statutory cess percentage rate."""
        return self.cess_rate_pct

    def to_dict(self):
        return {
            'tax_plus_surcharge': self.tax_plus_surcharge,
            'cess_rate_pct': self.cess_rate_pct,
            'cess_rate': self.cess_rate_pct,
            'cess_amount': self.cess_amount,
            'unrounded_annual_tax': self.unrounded_annual_tax,
            'rounding_factor_288b': self.rounding_factor_288b,
            'total_annual_tax_liability': self.total_annual_tax_liability,
        }


class HealthEducationCessService(BaseStatutoryService):
    """
    Phase 4 Pipeline Service: Health & Education Cess Engine Service.
    Resolves the statutory Health & Education Cess percentage (4.0%) via TdsParameterService (HEALTH_CESS).
    Applies Cess to (Tax + Surcharge - Rebate) and computes final Total Annual Income Tax Liability,
    statutorily rounded to the nearest multiple of ten rupees under Section 288B of the Income-tax Act, 1961.
    """

    @staticmethod
    def round_tax_to_nearest_10(amount):
        """
        Statutory Section 288B, Income-tax Act, 1961:
        Rounds total tax liability (including surcharge, cess, sums payable/refundable)
        to the nearest multiple of ten rupees:
        - Any part of a rupee consisting of paise shall be ignored (truncated).
        - If the last figure in that amount is 5 or more, the amount shall be
          increased to the next higher amount which is a multiple of ten.
        - If the last figure is less than 5, the amount shall be reduced to the
          next lower amount which is a multiple of ten.
        """
        if amount is None or amount <= 0:
            return 0.0
        whole_rupees = int(float(amount))
        remainder = whole_rupees % 10
        if remainder >= 5:
            return float(whole_rupees + (10 - remainder))
        else:
            return float(whole_rupees - remainder)

    def calculate_cess(self, tax_plus_surcharge, eval_date=None):
        """
        Calculates Health & Education Cess and total annual tax liability with Section 288B rounding.

        :param tax_plus_surcharge: float (Income tax after rebate + surcharge)
        :param eval_date: Date (optional)
        :return: HealthEducationCessResult
        """
        if tax_plus_surcharge <= 0:
            return HealthEducationCessResult(
                tax_plus_surcharge=0.0,
                cess_rate_pct=4.0,
                cess_amount=0.0,
                total_annual_tax_liability=0.0,
                unrounded_annual_tax=0.0,
                rounding_factor_288b=0.0
            )

        tds_param_svc = TdsParameterService(self.env)
        # Resolve Health & Education Cess rate (4%) via TdsParameterService
        cess_rate = tds_param_svc.get_parameter('HEALTH_CESS', eval_date=eval_date) or 4.0

        cess_amount = round(tax_plus_surcharge * (cess_rate / 100.0), 2)
        unrounded_annual_tax = round(tax_plus_surcharge + cess_amount, 2)
        total_annual_tax_liability = self.round_tax_to_nearest_10(unrounded_annual_tax)
        rounding_factor = round(total_annual_tax_liability - unrounded_annual_tax, 2)

        summary_log = f"""
========================================================
HEALTH & EDUCATION CESS SERVICE (SEC 288B COMPLIANT)
========================================================
Tax After Rebate / Surcharge : ₹{tax_plus_surcharge:,.2f}
Cess Rate                    : {cess_rate}%
Cess Amount                  : ₹{cess_amount:,.2f}
Unrounded Annual Tax         : ₹{unrounded_annual_tax:,.2f}
Sec 288B Rounding Adjustment : ₹{rounding_factor:,.2f}
Final Annual Tax (Sec 288B)  : ₹{total_annual_tax_liability:,.2f}
========================================================
"""
        _logger.warning(summary_log)

        return HealthEducationCessResult(
            tax_plus_surcharge=tax_plus_surcharge,
            cess_rate_pct=cess_rate,
            cess_amount=cess_amount,
            total_annual_tax_liability=total_annual_tax_liability,
            unrounded_annual_tax=unrounded_annual_tax,
            rounding_factor_288b=rounding_factor
        )
