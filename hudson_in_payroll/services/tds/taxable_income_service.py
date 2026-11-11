# -*- coding: utf-8 -*-
import logging
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class TaxableIncomeResult:
    """
    Data Transfer Object (DTO) holding Net Taxable Income details.
    """
    def __init__(self, gross_total_income, total_approved_deductions, net_taxable_income,
                 taxable_income_before_rounding=None, rounding_factor=None):
        self.gross_total_income = gross_total_income
        self.total_approved_deductions = total_approved_deductions
        self.net_taxable_income_before_rounding = (
            float(taxable_income_before_rounding) if taxable_income_before_rounding is not None
            else float(net_taxable_income)
        )
        self.net_taxable_income = float(net_taxable_income)
        self.rounding_factor = (
            float(rounding_factor) if rounding_factor is not None
            else round(self.net_taxable_income - self.net_taxable_income_before_rounding, 2)
        )


class TaxableIncomeService(BaseStatutoryService):
    """
    Phase 4 Pipeline Service: Taxable Income Service.
    Calculates Net Taxable Income by subtracting total approved deductions from Gross Total Income (GTI).
    Applies statutory Section 516, Income-tax Act, 2025 rounding to the nearest multiple of Rs 10.
    Serves as the input provider to the Income Tax Slab Engine.
    """

    @staticmethod
    def round_to_nearest_10(amount):
        """
        Statutory Section 516, Income-tax Act, 2025 Rounding of Total Taxable Income:
        Rounds total income to the nearest multiple of ten rupees.
        - Any part of a rupee consisting of paise is ignored (truncated).
        - If the last digit of the rupee amount is 5 or more, the amount is
          increased to the next higher multiple of 10.
        - If the last digit of the rupee amount is less than 5, the amount is
          reduced to the next lower multiple of 10.
        """
        if amount is None or amount <= 0:
            return 0.0
        whole_rupees = int(float(amount))
        remainder = whole_rupees % 10
        if remainder >= 5:
            return float(whole_rupees + (10 - remainder))
        else:
            return float(whole_rupees - remainder)

    @staticmethod
    def round_tax_to_nearest_10(amount):
        """
        Statutory Section 288B Rounding of Tax, Surcharge, Cess, and Sums Payable/Refundable:
        - Any part of a rupee consisting of paise shall be ignored (truncated).
        - If the last figure in that amount is 5 or more, increased to next higher multiple of 10.
        - If the last figure is less than 5, reduced to next lower multiple of 10.
        """
        if amount is None or amount <= 0:
            return 0.0
        whole_rupees = int(float(amount))
        remainder = whole_rupees % 10
        if remainder >= 5:
            return float(whole_rupees + (10 - remainder))
        else:
            return float(whole_rupees - remainder)

    def calculate_taxable_income(self, gross_total_income, total_approved_deductions):
        """
        Calculates Net Taxable Income with Section 516, Income-tax Act, 2025 statutory rounding to nearest Rs. 10.

        :param gross_total_income: float (Gross Total Income projected in Phase 4)
        :param total_approved_deductions: float (Total approved statutory deductions)
        :return: TaxableIncomeResult
        """
        gti = float(gross_total_income or 0.0)
        deductions = float(total_approved_deductions or 0.0)
        unrounded_taxable = max(0.0, gti - deductions)
        net_taxable = self.round_to_nearest_10(unrounded_taxable)
        rounding_factor = round(net_taxable - unrounded_taxable, 2)

        summary_log = f"""
========================================================
TAXABLE INCOME SERVICE (WITH SECTION 516 ROUNDING)
========================================================
Gross Total Income              : INR {gti:,.2f}
- Total Deductions              : INR {deductions:,.2f}
= Unrounded Net Taxable Income  : INR {unrounded_taxable:,.2f}
Rounding Factor (Sec 516)       : INR {rounding_factor:+,.2f}
= Statutory Taxable Income (516): INR {net_taxable:,.2f}
========================================================
"""
        _logger.warning("""[FORENSIC_TDS_TRACE]
step=TAXABLE_INCOME
input=gross_total_income:INR %s, total_allowable_deductions:INR %s
output=net_taxable_income:INR %s (unrounded: INR %s, rounding_factor: INR %s)
source_method=TaxableIncomeService.calculate_taxable_income
branch_used=%s""",
            f"{gti:,.2f}",
            f"{deductions:,.2f}",
            f"{net_taxable:,.2f}",
            f"{unrounded_taxable:,.2f}",
            f"{rounding_factor:+,.2f}",
            f"SECTION_516_ROUNDED_TAXABLE_INCOME (Gross INR {gti:,.2f} - Deductions INR {deductions:,.2f})"
        )

        return TaxableIncomeResult(
            gross_total_income=gti,
            total_approved_deductions=deductions,
            net_taxable_income=net_taxable,
            taxable_income_before_rounding=unrounded_taxable,
            rounding_factor=rounding_factor
        )
