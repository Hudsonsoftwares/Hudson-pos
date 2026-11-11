# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Constant Statutory Parameter Code Mapping to prevent cross-wiring
PF_PARAMETER_MAPPING = {
    'PF_WAGE_CEILING': 'hds_in_pf_wage_ceiling',
    'EPS_WAGE_CEILING': 'hds_in_eps_wage_ceiling',
    'EDLI_WAGE_CEILING': 'hds_in_edli_wage_ceiling',
    'EPF_RATE': 'hds_in_epf_rate',
    'EPS_RATE': 'hds_in_eps_rate',
    'EDLI_RATE': 'hds_in_edli_rate',
    'EPF_ADMIN_RATE': 'hds_in_epf_admin_charge_rate',
    'EDLI_ADMIN_RATE': 'hds_in_edli_admin_charge_rate',
    'EMPLOYER_EPF_RATE': 'hds_in_employer_epf_rate',
}

GRATUITY_PARAMETER_MAPPING = {
    'DAYS_MULTIPLIER': 'hds_in_gratuity_days_multiplier',
    'MONTH_DIVISOR': 'hds_in_gratuity_month_divisor',
    'MIN_SERVICE_YEARS': 'hds_in_gratuity_min_service_years',
    'STATUTORY_CEILING': 'hds_in_gratuity_statutory_ceiling',
}

LEAVE_ENCASHMENT_PARAMETER_MAPPING = {
    'MONTH_DIVISOR': 'hds_in_leave_encashment_month_divisor',
    'MAX_ENCASHABLE_DAYS': 'hds_in_max_encashable_days',
    'STATUTORY_CEILING': 'hds_in_leave_encashment_statutory_ceiling',
}


class HrRuleParameter(models.Model):
    _inherit = 'hr.rule.parameter'

    @api.model
    def get_pf_parameter(self, code_key_or_code, date=None, as_decimal=False):
        """
        Shared helper method to retrieve statutory PF parameters safely.
        - Accepts either a mapping key (e.g. 'EPF_RATE') or raw parameter code (e.g. 'hds_in_epf_rate').
        - Handles conversion to float.
        - If as_decimal=True and category in ('rate', 'admin'), divides value by 100.
        """
        code = PF_PARAMETER_MAPPING.get(code_key_or_code, code_key_or_code)
        return self.get_parameter(code, date=date, as_decimal=as_decimal)

    @api.model
    def get_gratuity_parameter(self, code_key_or_code, date=None, as_decimal=False):
        """
        Shared helper method to retrieve statutory Gratuity parameters safely.
        - Accepts either a mapping key (e.g. 'STATUTORY_CEILING') or raw parameter code.
        """
        code = GRATUITY_PARAMETER_MAPPING.get(code_key_or_code, code_key_or_code)
        return self.get_parameter(code, date=date, as_decimal=as_decimal)

    @api.model
    def get_leave_encashment_parameter(self, code_key_or_code, date=None, as_decimal=False):
        """
        Shared helper method to retrieve statutory Leave Encashment parameters safely.
        - Accepts either a mapping key (e.g. 'STATUTORY_CEILING') or raw parameter code.
        """
        code = LEAVE_ENCASHMENT_PARAMETER_MAPPING.get(code_key_or_code, code_key_or_code)
        return self.get_parameter(code, date=date, as_decimal=as_decimal)
