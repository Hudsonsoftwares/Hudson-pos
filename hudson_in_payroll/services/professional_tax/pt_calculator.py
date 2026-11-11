# -*- coding: utf-8 -*-
import logging
from datetime import datetime, date
from odoo import fields
from odoo.tools import float_round

_logger = logging.getLogger(__name__)


class PTCalculationResult:
    """
    Structured Result Container representing a Professional Tax calculation output.
    Encapsulates final deduction amount, normal amount, override status, and calculation status.
    """

    def __init__(self, pt_amount, normal_amount, override_applied=False, override_month=None, override_amount=None, calculation_status="SUCCESS"):
        self.pt_amount = pt_amount
        self.normal_amount = normal_amount
        self.override_applied = override_applied
        self.override_month = override_month
        self.override_amount = override_amount
        self.calculation_status = calculation_status

    def to_dict(self):
        """Returns a structured dictionary representation of the calculation result."""
        return {
            'pt_amount': self.pt_amount,
            'normal_amount': self.normal_amount,
            'override_applied': self.override_applied,
            'override_month': self.override_month,
            'override_amount': self.override_amount,
            'calculation_status': self.calculation_status,
        }

    def __repr__(self):
        return (
            f"<PTCalculationResult pt_amount={self.pt_amount} normal={self.normal_amount} "
            f"override_applied={self.override_applied} status='{self.calculation_status}'>"
        )


class PTCalculator:
    """
    Pure Domain Calculation Engine for Professional Tax (PT) Statutory Deductions.
    Single Responsibility: Determine the Professional Tax amount based on a pre-resolved
    pt.state.slab or ProfessionalTaxSlabResult instance and payroll evaluation date/month.

    Features:
    - Pure calculation math with zero database access, ORM queries, or validation logic.
    - Evaluates standard monthly deduction amount vs special monthly override amount.
    - Applies statutory monetary rounding.
    """

    def __init__(self, env=None):
        self.env = env

    def round_statutory(self, amount, precision_digits=2):
        """Applies standard monetary rounding."""
        return float_round(amount or 0.0, precision_digits=precision_digits)

    def _extract_month(self, eval_date):
        """
        Extracts integer month (1-12) from eval_date.
        Supports int, str ('2' or '2026-02-15'), datetime.date, or None.
        """
        if eval_date is None:
            return fields.Date.today().month

        if isinstance(eval_date, int):
            if 1 <= eval_date <= 12:
                return eval_date
            return fields.Date.today().month

        if isinstance(eval_date, (date, datetime)):
            return eval_date.month

        if isinstance(eval_date, str):
            eval_date_str = eval_date.strip()
            if eval_date_str.isdigit():
                val = int(eval_date_str)
                if 1 <= val <= 12:
                    return val
            try:
                dt = fields.Date.from_string(eval_date_str)
                if dt:
                    return dt.month
            except (ValueError, TypeError) as e:
                _logger.debug("Failed parsing eval_date string '%s' in pt_calculator: %s", eval_date_str, e)

        return fields.Date.today().month

    def calculate(self, slab=None, eval_date=None):
        """
        Calculates the Professional Tax deduction amount based on slab configuration and evaluation date.

        :param slab: ProfessionalTaxSlabResult instance or pt.state.slab recordset or None
        :param eval_date: datetime.date, date str, month int, or None
        :return: PTCalculationResult instance
        """
        if not slab:
            return PTCalculationResult(
                pt_amount=0.0,
                normal_amount=0.0,
                override_applied=False,
                override_month=None,
                override_amount=None,
                calculation_status='NO_SLAB'
            )

        # Handle both ProfessionalTaxSlabResult objects and raw pt.state.slab recordsets
        normal_amount = getattr(slab, 'pt_amount', 0.0) or 0.0
        override_month_raw = getattr(slab, 'override_month', None)
        override_amount_raw = getattr(slab, 'override_amount', None)

        current_month = self._extract_month(eval_date)

        # Check if monthly override applies
        override_applied = False
        final_amount = normal_amount
        status = 'SUCCESS'

        periodicity = getattr(slab, 'periodicity', 'monthly') or 'monthly'
        if periodicity == 'monthly' and override_month_raw and override_amount_raw is not None and override_amount_raw is not False:
            try:
                override_m_int = int(str(override_month_raw).strip())
                if override_m_int == current_month:
                    final_amount = float(override_amount_raw)
                    override_applied = True
                    status = 'OVERRIDE_APPLIED'
            except (ValueError, TypeError):
                _logger.warning("PTCalculator: Invalid override_month value '%s'", override_month_raw)

        rounded_final = self.round_statutory(final_amount)
        rounded_normal = self.round_statutory(normal_amount)
        rounded_override = self.round_statutory(override_amount_raw) if (override_amount_raw is not None and override_amount_raw is not False) else None

        return PTCalculationResult(
            pt_amount=rounded_final,
            normal_amount=rounded_normal,
            override_applied=override_applied,
            override_month=override_month_raw,
            override_amount=rounded_override,
            calculation_status=status
        )
