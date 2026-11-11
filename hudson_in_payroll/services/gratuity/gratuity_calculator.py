# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo.tools.float_utils import float_round
import logging

_logger = logging.getLogger(__name__)


class GratuityCalculationResult:
    """
    Structured container for Gratuity Calculation Results.
    Immutable output object produced by GratuityCalculator.
    """

    def __init__(
        self,
        raw_gratuity_amount=0.0,
        capped_gratuity_amount=0.0,
        final_gratuity_amount=0.0,
        is_ceiling_applied=False,
        statutory_ceiling_used=2000000.0,
        wage_base_used=0.0,
        daily_rate_used=0.0,
        completed_years_used=0,
        days_multiplier_used=15.0,
        month_divisor_used=26.0
    ):
        self.raw_gratuity_amount = raw_gratuity_amount
        self.capped_gratuity_amount = capped_gratuity_amount
        self.final_gratuity_amount = final_gratuity_amount
        self.is_ceiling_applied = is_ceiling_applied
        self.statutory_ceiling_used = statutory_ceiling_used
        self.wage_base_used = wage_base_used
        self.daily_rate_used = daily_rate_used
        self.completed_years_used = completed_years_used
        self.days_multiplier_used = days_multiplier_used
        self.month_divisor_used = month_divisor_used

    def to_dict(self):
        """Serialize calculation result into dictionary for audit trail / reporting."""
        return {
            'raw_gratuity_amount': float(self.raw_gratuity_amount),
            'capped_gratuity_amount': float(self.capped_gratuity_amount),
            'final_gratuity_amount': float(self.final_gratuity_amount),
            'is_ceiling_applied': self.is_ceiling_applied,
            'statutory_ceiling_used': float(self.statutory_ceiling_used),
            'wage_base_used': float(self.wage_base_used),
            'daily_rate_used': float(self.daily_rate_used),
            'completed_years_used': self.completed_years_used,
            'days_multiplier_used': float(self.days_multiplier_used),
            'month_divisor_used': float(self.month_divisor_used),
        }

    def __repr__(self):
        return (
            f"<GratuityCalculationResult final={self.final_gratuity_amount:.2f} "
            f"raw={self.raw_gratuity_amount:.2f} capped={self.is_ceiling_applied} "
            f"years={self.completed_years_used}>"
        )


class GratuityCalculator:
    """
    Pure Mathematical Calculation Engine for Gratuity.
    Single Responsibility: Compute statutory gratuity based on input data (DTO).
    Does NOT query database, perform ORM calls, check eligibility, or alter records.
    """

    def calculate(self, data_dto, precision_digits=2):
        """
        Computes gratuity based on prepared calculation data (DTO).

        :param data_dto: GratuityCalculationData object
        :param precision_digits: int (rounding precision, default 2)
        :return: GratuityCalculationResult
        """
        if not data_dto:
            return GratuityCalculationResult()

        wage_base = float(getattr(data_dto, 'wage_base', 0.0) or 0.0)
        completed_years = int(getattr(data_dto, 'completed_years', 0) or 0)
        days_multiplier = float(getattr(data_dto, 'days_multiplier', 15.0) or 15.0)
        month_divisor = float(getattr(data_dto, 'month_divisor', 26.0) or 26.0)
        statutory_ceiling = float(getattr(data_dto, 'statutory_ceiling', 2000000.0) or 2000000.0)

        # 1. Zero wage or zero completed service years returns 0.0 calculation
        if wage_base <= 0.0 or completed_years <= 0 or month_divisor <= 0.0:
            return GratuityCalculationResult(
                raw_gratuity_amount=0.0,
                capped_gratuity_amount=0.0,
                final_gratuity_amount=0.0,
                is_ceiling_applied=False,
                statutory_ceiling_used=statutory_ceiling,
                wage_base_used=wage_base,
                daily_rate_used=0.0,
                completed_years_used=completed_years,
                days_multiplier_used=days_multiplier,
                month_divisor_used=month_divisor
            )

        # 2. Compute Daily Wage Rate
        daily_rate = wage_base / month_divisor

        # 3. Compute Statutory Gratuity Formula: (Wage Base / Month Divisor) * Days Multiplier * Completed Years
        raw_gratuity_amount = daily_rate * days_multiplier * completed_years

        # 4. Apply Statutory Ceiling
        is_ceiling_applied = False
        if statutory_ceiling > 0.0 and raw_gratuity_amount > statutory_ceiling:
            capped_gratuity_amount = statutory_ceiling
            is_ceiling_applied = True
        else:
            capped_gratuity_amount = raw_gratuity_amount

        # 5. Apply Monetary Rounding
        final_gratuity_amount = float_round(capped_gratuity_amount, precision_digits=precision_digits)
        rounded_raw_amount = float_round(raw_gratuity_amount, precision_digits=precision_digits)

        # 6. Return Structured Result Object
        return GratuityCalculationResult(
            raw_gratuity_amount=rounded_raw_amount,
            capped_gratuity_amount=capped_gratuity_amount,
            final_gratuity_amount=final_gratuity_amount,
            is_ceiling_applied=is_ceiling_applied,
            statutory_ceiling_used=statutory_ceiling,
            wage_base_used=wage_base,
            daily_rate_used=daily_rate,
            completed_years_used=completed_years,
            days_multiplier_used=days_multiplier,
            month_divisor_used=month_divisor
        )
