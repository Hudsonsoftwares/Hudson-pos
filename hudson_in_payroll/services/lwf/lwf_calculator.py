# -*- coding: utf-8 -*-
from odoo.tools import float_round


class LWFCalculator:
    """
    Pure Domain Calculator for Labour Welfare Fund (LWF) contributions.
    Single Responsibility: Compute employee deduction and employer contribution
    amounts and apply statutory rounding rules.
    """

    def __init__(self, env=None):
        self.env = env

    def round_statutory(self, amount, precision_digits=2):
        """Standard monetary rounding."""
        return float_round(amount or 0.0, precision_digits=precision_digits)

    def calculate_employee_contribution(self, rate_config):
        """
        Calculates employee LWF contribution amount.

        :param rate_config: lwf.state.rate recordset
        :return: float
        """
        if not rate_config:
            return 0.0
        raw_amount = getattr(rate_config, 'emp_contribution', 0.0) or 0.0
        return self.round_statutory(raw_amount)

    def calculate_employer_contribution(self, rate_config):
        """
        Calculates employer LWF contribution amount.

        :param rate_config: lwf.state.rate recordset
        :return: float
        """
        if not rate_config:
            return 0.0
        raw_amount = getattr(rate_config, 'empl_contribution', 0.0) or 0.0
        return self.round_statutory(raw_amount)
