# -*- coding: utf-8 -*-
from odoo.tools.float_utils import float_round
import logging

_logger = logging.getLogger(__name__)


class LeaveEncashmentResult:
    """
    Structured container for Leave Encashment Calculation Results.
    Immutable output object produced by LeaveEncashmentCalculator.
    """

    def __init__(
        self,
        leave_days_used=0.0,
        daily_rate_used=0.0,
        raw_amount=0.0,
        capped_amount=0.0,
        final_amount=0.0,
        is_cap_applied=False,
        max_encashable_days_used=300.0,
        wage_base_used=0.0,
        month_divisor_used=26.0
    ):
        self.leave_days_used = leave_days_used
        self.daily_rate_used = daily_rate_used
        self.raw_amount = raw_amount
        self.capped_amount = capped_amount
        self.final_amount = final_amount
        self.is_cap_applied = is_cap_applied
        self.max_encashable_days_used = max_encashable_days_used
        self.wage_base_used = wage_base_used
        self.month_divisor_used = month_divisor_used

    def to_dict(self):
        """Serialize calculation result into dictionary for audit trail and reporting."""
        return {
            'leave_days_used': float(self.leave_days_used),
            'daily_rate_used': float(self.daily_rate_used),
            'raw_amount': float(self.raw_amount),
            'capped_amount': float(self.capped_amount),
            'final_amount': float(self.final_amount),
            'is_cap_applied': self.is_cap_applied,
            'max_encashable_days_used': float(self.max_encashable_days_used),
            'wage_base_used': float(self.wage_base_used),
            'month_divisor_used': float(self.month_divisor_used),
        }

    def __repr__(self):
        return (
            f"<LeaveEncashmentResult final={self.final_amount:.2f} "
            f"raw={self.raw_amount:.2f} days={self.leave_days_used} "
            f"daily_rate={self.daily_rate_used:.2f} capped={self.is_cap_applied}>"
        )


class LeaveEncashmentCalculator:
    """
    Pure Mathematical Calculation Engine for Leave Encashment.
    Single Responsibility: Compute Leave Encashment based purely on input data (DTO).
    Does NOT query database, perform ORM calls, check configuration/eligibility, or alter records.
    """

    def calculate(self, data_dto, precision_digits=2):
        """
        Computes Leave Encashment based on prepared calculation data (DTO).

        Formula:
        1. daily_rate = wage_base / month_divisor
        2. raw_amount = daily_rate * total_eligible_days
        3. capped_days = min(total_eligible_days, max_encashable_days) if max_encashable_days > 0 else total_eligible_days
        4. capped_amount = daily_rate * capped_days
        5. final_amount = float_round(capped_amount, precision_digits=2)

        :param data_dto: LeaveEncashmentCalculationData object
        :param precision_digits: int (rounding precision, default 2)
        :return: LeaveEncashmentResult
        """
        if not data_dto:
            return LeaveEncashmentResult()

        wage_base = float(getattr(data_dto, 'wage_base', 0.0) or 0.0)
        month_divisor = float(getattr(data_dto, 'month_divisor', 26.0) or 26.0)
        max_encashable_days = float(getattr(data_dto, 'max_encashable_days', 300.0) or 300.0)
        leave_days_used = float(getattr(data_dto, 'total_eligible_days', 0.0) or 0.0)

        # 1. Zero wage, zero days, or invalid month divisor returns 0.0 result
        if wage_base <= 0.0 or leave_days_used <= 0.0 or month_divisor <= 0.0:
            return LeaveEncashmentResult(
                leave_days_used=leave_days_used,
                daily_rate_used=0.0,
                raw_amount=0.0,
                capped_amount=0.0,
                final_amount=0.0,
                is_cap_applied=False,
                max_encashable_days_used=max_encashable_days,
                wage_base_used=wage_base,
                month_divisor_used=month_divisor
            )

        # 2. Calculate Daily Rate
        daily_rate_used = wage_base / month_divisor

        # 3. Calculate Raw Amount
        raw_amount = daily_rate_used * leave_days_used

        # 4. Apply Maximum Encashable Days Cap (0 = no cap)
        is_cap_applied = False
        if max_encashable_days > 0.0 and leave_days_used > max_encashable_days:
            capped_days = max_encashable_days
            is_cap_applied = True
        else:
            capped_days = leave_days_used

        capped_amount = daily_rate_used * capped_days

        # 5. Apply Monetary Rounding (Odoo float_round to 2 decimals)
        final_amount = float_round(capped_amount, precision_digits=precision_digits)

        # 6. Return Structured Result Object
        return LeaveEncashmentResult(
            leave_days_used=leave_days_used,
            daily_rate_used=daily_rate_used,
            raw_amount=raw_amount,
            capped_amount=capped_amount,
            final_amount=final_amount,
            is_cap_applied=is_cap_applied,
            max_encashable_days_used=max_encashable_days,
            wage_base_used=wage_base,
            month_divisor_used=month_divisor
        )
