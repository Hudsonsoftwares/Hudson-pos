# -*- coding: utf-8 -*-
import math
from odoo.exceptions import ValidationError, UserError


class BaseStatutoryService:
    """
    Abstract Pure Python Base Service for all Indian Statutory Services.
    Decoupled from Odoo Model Registry for clean testing and zero ORM overhead.
    """
    def __init__(self, env):
        self.env = env

    def get_parameter(self, code, date=None, as_decimal=False):
        """Delegates parameter lookup to hr.rule.parameter with date effective rules."""
        return self.env['hr.rule.parameter'].get_parameter(code, date=date, as_decimal=as_decimal)

    def get_pf_parameter(self, code_key_or_code, date=None, as_decimal=False):
        """Delegates PF parameter lookup to hr.rule.parameter."""
        return self.env['hr.rule.parameter'].get_pf_parameter(code_key_or_code, date=date, as_decimal=as_decimal)

    @staticmethod
    def round_statutory(amount):
        """Statutory nearest rupee rounding (Rule 4 of EPF Scheme). Half values round up."""
        if amount is False or amount is None:
            return 0.0
        return float(math.floor(amount + 0.5))

    @staticmethod
    def calculate_age(dob, target_date):
        """Calculates exact age on target_date (usually payslip.date_to)."""
        if not dob or not target_date:
            return 0
        return target_date.year - dob.year - ((target_date.month, target_date.day) < (dob.month, dob.day))
