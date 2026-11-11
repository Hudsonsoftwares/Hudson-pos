# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Mapping of standard UAE statutory pension parameter keys to hr.rule.parameter codes
UAE_PENSION_PARAMETER_MAPPING = {
    # GPSSA Authority Parameters
    'GPSSA_EE_RATE': 'hds_ae_gpssa_ee_rate',
    'GPSSA_ER_RATE': 'hds_ae_gpssa_er_rate',
    'GPSSA_SUBSIDY_RATE': 'hds_ae_gpssa_gov_subsidy_rate',
    'GPSSA_SUBSIDY_THRESHOLD': 'hds_ae_gpssa_subsidy_wage_threshold',
    'GPSSA_MAX_WAGE': 'hds_ae_gpssa_max_wage',
    'GPSSA_MIN_WAGE': 'hds_ae_gpssa_min_wage',

    # ADPF Authority Parameters
    'ADPF_EE_RATE': 'hds_ae_adpf_ee_rate',
    'ADPF_ER_RATE': 'hds_ae_adpf_er_rate',
    'ADPF_SUBSIDY_RATE': 'hds_ae_adpf_gov_subsidy_rate',
    'ADPF_SUBSIDY_THRESHOLD': 'hds_ae_adpf_gov_subsidy_rate',
    'ADPF_MAX_WAGE': 'hds_ae_adpf_max_wage',
    'ADPF_MIN_WAGE': 'hds_ae_adpf_min_wage',
}

# Mapping of (Authority, Scheme, ParamKey) to hr.rule.parameter codes for concurrent cohort resolution
UAE_SCHEME_PENSION_PARAMETER_MAPPING = {
    # GPSSA - Legacy Scheme (Federal Law No. 7 of 1999)
    ('GPSSA', 'legacy', 'EE_RATE'): 'hds_ae_gpssa_legacy_ee_rate',
    ('GPSSA', 'legacy', 'ER_RATE'): 'hds_ae_gpssa_legacy_er_rate',
    ('GPSSA', 'legacy', 'SUBSIDY_RATE'): 'hds_ae_gpssa_legacy_gov_subsidy_rate',
    ('GPSSA', 'legacy', 'SUBSIDY_THRESHOLD'): 'hds_ae_gpssa_legacy_subsidy_wage_threshold',
    ('GPSSA', 'legacy', 'MAX_WAGE'): 'hds_ae_gpssa_legacy_max_wage',
    ('GPSSA', 'legacy', 'MIN_WAGE'): 'hds_ae_gpssa_legacy_min_wage',

    # GPSSA - New Law Scheme (Federal Decree-Law No. 57 of 2023)
    ('GPSSA', 'new_law', 'EE_RATE'): 'hds_ae_gpssa_new_law_ee_rate',
    ('GPSSA', 'new_law', 'ER_RATE'): 'hds_ae_gpssa_new_law_er_rate',
    ('GPSSA', 'new_law', 'SUBSIDY_RATE'): 'hds_ae_gpssa_new_law_gov_subsidy_rate',
    ('GPSSA', 'new_law', 'SUBSIDY_THRESHOLD'): 'hds_ae_gpssa_new_law_subsidy_wage_threshold',
    ('GPSSA', 'new_law', 'MAX_WAGE'): 'hds_ae_gpssa_new_law_max_wage',
    ('GPSSA', 'new_law', 'MIN_WAGE'): 'hds_ae_gpssa_new_law_min_wage',

    # ADPF - Legacy Scheme (Law No. 2 of 2000)
    ('ADPF', 'legacy', 'EE_RATE'): 'hds_ae_adpf_legacy_ee_rate',
    ('ADPF', 'legacy', 'ER_RATE'): 'hds_ae_adpf_legacy_er_rate',
    ('ADPF', 'legacy', 'SUBSIDY_RATE'): 'hds_ae_adpf_legacy_gov_subsidy_rate',
    ('ADPF', 'legacy', 'MAX_WAGE'): 'hds_ae_adpf_legacy_max_wage',
    ('ADPF', 'legacy', 'MIN_WAGE'): 'hds_ae_adpf_legacy_min_wage',

    # ADPF - New Law Scheme (Law No. 22 of 2023)
    ('ADPF', 'new_law', 'EE_RATE'): 'hds_ae_adpf_new_law_ee_rate',
    ('ADPF', 'new_law', 'ER_RATE'): 'hds_ae_adpf_new_law_er_rate',
    ('ADPF', 'new_law', 'SUBSIDY_RATE'): 'hds_ae_adpf_new_law_gov_subsidy_rate',
    ('ADPF', 'new_law', 'MAX_WAGE'): 'hds_ae_adpf_new_law_max_wage',
    ('ADPF', 'new_law', 'MIN_WAGE'): 'hds_ae_adpf_new_law_min_wage',
}

# Mapping of GCC country codes and parameter types to hr.rule.parameter codes
GCC_PENSION_PARAMETER_MAPPING = {
    # Saudi Arabia (GOSI)
    ('SA', 'EE_RATE'): 'hds_gcc_sa_ee_rate',
    ('SA', 'ER_RATE'): 'hds_gcc_sa_er_rate',
    ('SA', 'ER_CAP'): 'hds_gcc_sa_er_cap',
    ('SA', 'ABSORB_SHORTFALL'): 'hds_gcc_sa_absorb_shortfall',
    ('SA', 'MAX_WAGE'): 'hds_gcc_sa_max_wage',

    # Kuwait (PIFSS)
    ('KW', 'EE_RATE'): 'hds_gcc_kw_ee_rate',
    ('KW', 'ER_RATE'): 'hds_gcc_kw_er_rate',
    ('KW', 'ER_CAP'): 'hds_gcc_kw_er_cap',
    ('KW', 'ABSORB_SHORTFALL'): 'hds_gcc_kw_absorb_shortfall',
    ('KW', 'MAX_WAGE'): 'hds_gcc_kw_max_wage',

    # Bahrain (SIO)
    ('BH', 'EE_RATE'): 'hds_gcc_bh_ee_rate',
    ('BH', 'ER_RATE'): 'hds_gcc_bh_er_rate',
    ('BH', 'ER_CAP'): 'hds_gcc_bh_er_cap',
    ('BH', 'ABSORB_SHORTFALL'): 'hds_gcc_bh_absorb_shortfall',
    ('BH', 'MAX_WAGE'): 'hds_gcc_bh_max_wage',

    # Oman (SPF)
    ('OM', 'EE_RATE'): 'hds_gcc_om_ee_rate',
    ('OM', 'ER_RATE'): 'hds_gcc_om_er_rate',
    ('OM', 'ER_CAP'): 'hds_gcc_om_er_cap',
    ('OM', 'ABSORB_SHORTFALL'): 'hds_gcc_om_absorb_shortfall',
    ('OM', 'MAX_WAGE'): 'hds_gcc_om_max_wage',

    # Qatar (GRIA)
    ('QA', 'EE_RATE'): 'hds_gcc_qa_ee_rate',
    ('QA', 'ER_RATE'): 'hds_gcc_qa_er_rate',
    ('QA', 'ER_CAP'): 'hds_gcc_qa_er_cap',
    ('QA', 'ABSORB_SHORTFALL'): 'hds_gcc_qa_absorb_shortfall',
    ('QA', 'MAX_WAGE'): 'hds_gcc_qa_max_wage',
}


class HrRuleParameter(models.Model):
    _inherit = 'hr.rule.parameter'

    category = fields.Selection(
        selection_add=[
            ('uae_gpssa', 'UAE Pension (GPSSA)'),
            ('uae_adpf', 'UAE Pension (ADPF)'),
            ('gcc_pension', 'GCC Pension (Unified Extension)'),
        ],
        ondelete={
            'uae_gpssa': 'set default',
            'uae_adpf': 'set default',
            'gcc_pension': 'set default',
        }
    )

    pension_authority_id = fields.Many2one(
        'uae.pension.authority',
        string='Pension Authority',
        index=True,
        help="Governing UAE Pension Authority for statutory parameter filtering."
    )

    pension_scheme_id = fields.Many2one(
        'uae.pension.scheme',
        string='Pension Scheme',
        index=True,
        help="Applicable UAE Pension Scheme (Legacy Scheme vs New Law Scheme)."
    )

    @api.model
    def get_parameter(self, code, date=None, as_decimal=False):
        """
        Extends core get_parameter to handle:
        1. String dates converted safely to datetime.date.
        2. Boolean parameter values (e.g. 'True' / 'False' for absorb_shortfall).
        3. Decimal division (as_decimal=True) for statutory rate and cap parameters.
        """
        param = self.search([('code', '=', code)], limit=1)
        if not param:
            raise ValidationError(f"Statutory parameter '{code}' is not defined in the system.")

        if isinstance(date, str):
            date = fields.Date.from_string(date)
        elif not date:
            date = fields.Date.today()

        val_str = param._get_parameter_value(date=date)
        if val_str is False:
            raise ValidationError(f"No effective statutory parameter version found for '{code}' on date {date}.")

        val_str_clean = str(val_str).strip()

        # Support Boolean statutory parameters
        if val_str_clean.lower() in ('true', 'false'):
            return val_str_clean.lower() == 'true'

        try:
            val_float = float(val_str_clean)
        except (ValueError, TypeError):
            raise ValidationError(f"Invalid non-numeric value '{val_str}' for parameter '{code}'.")

        if as_decimal:
            if param.category in ('rate', 'admin') or (
                param.category in ('uae_gpssa', 'uae_adpf', 'gcc_pension') and
                any(s in (param.code or '') for s in ('_rate', '_cap'))
            ):
                return val_float / 100.0

        return val_float

    @api.model
    def get_uae_pension_parameter(self, code_key_or_code, scheme_code=None, date=None, as_decimal=False):
        """
        Retrieve UAE statutory pension parameters by key or exact code on a given calculation date.
        Supports dynamic resolution across concurrent schemes (Legacy vs New Law):
            Authority + Scheme + Date -> Effective Parameter
        """
        code = None
        if scheme_code:
            # Handle if uae.pension.scheme record was passed
            if hasattr(scheme_code, 'code'):
                scheme_code = scheme_code.code
            scheme_code = str(scheme_code).strip().lower()

            # Extract authority prefix and parameter key if code_key_or_code is like 'GPSSA_EE_RATE'
            parts = code_key_or_code.split('_', 1) if '_' in code_key_or_code else (code_key_or_code, '')
            authority_prefix = parts[0].upper()
            param_key = parts[1].upper() if len(parts) > 1 else ''
            code = UAE_SCHEME_PENSION_PARAMETER_MAPPING.get((authority_prefix, scheme_code, param_key))

        if not code:
            code = UAE_PENSION_PARAMETER_MAPPING.get(code_key_or_code, code_key_or_code)

        return self.get_parameter(code, date=date, as_decimal=as_decimal)

    @api.model
    def get_gcc_pension_parameter(self, country_code, param_type, date=None, as_decimal=False):
        """
        Retrieve GCC National home-country pension parameters by country code and type.
        Examples:
            get_gcc_pension_parameter('SA', 'EE_RATE', as_decimal=True) -> 0.09
            get_gcc_pension_parameter('SA', 'ER_CAP', as_decimal=True) -> 0.125
            get_gcc_pension_parameter('SA', 'ABSORB_SHORTFALL') -> True
        """
        country_code = country_code.upper() if country_code else ''
        param_type = param_type.upper() if param_type else ''
        code = GCC_PENSION_PARAMETER_MAPPING.get((country_code, param_type))
        if not code:
            raise ValidationError(
                f"No statutory GCC pension parameter mapped for country '{country_code}' and parameter '{param_type}'."
            )
        return self.get_parameter(code, date=date, as_decimal=as_decimal)

    @api.model
    def resolve_uae_pension_rates(self, authority_code='gpssa', scheme_code=None, date=None, as_decimal=False):
        """
        Pure parameter-driven UAE pension rate resolution supporting concurrent cohorts.
        Resolves applicable scheme parameters using:
            Authority + Pension Scheme + Effective Payslip Date -> Applicable Rule Parameter
        Enables Legacy and New Law rates to coexist simultaneously for different employees.
        Zero hardcoded rates or scheme cutover dates in Python.
        """
        authority_lower = (authority_code or '').lower()
        if 'adpf' in authority_lower or authority_lower == 'abu_dhabi':
            prefix = 'ADPF'
        else:
            prefix = 'GPSSA'

        # Normalize scheme code if a recordset or string was passed
        if hasattr(scheme_code, 'code'):
            norm_scheme = scheme_code.code
        elif scheme_code:
            norm_scheme = str(scheme_code).strip().lower()
        else:
            norm_scheme = None

        ee_rate = self.get_uae_pension_parameter(f'{prefix}_EE_RATE', scheme_code=norm_scheme, date=date, as_decimal=as_decimal)
        er_rate = self.get_uae_pension_parameter(f'{prefix}_ER_RATE', scheme_code=norm_scheme, date=date, as_decimal=as_decimal)
        subsidy_rate = self.get_uae_pension_parameter(f'{prefix}_SUBSIDY_RATE', scheme_code=norm_scheme, date=date, as_decimal=as_decimal)

        if prefix == 'GPSSA':
            subsidy_threshold = self.get_uae_pension_parameter('GPSSA_SUBSIDY_THRESHOLD', scheme_code=norm_scheme, date=date)
        else:
            subsidy_threshold = 0.0

        max_wage = self.get_uae_pension_parameter(f'{prefix}_MAX_WAGE', scheme_code=norm_scheme, date=date)
        min_wage = self.get_uae_pension_parameter(f'{prefix}_MIN_WAGE', scheme_code=norm_scheme, date=date)

        return {
            'authority': prefix,
            'scheme': norm_scheme,
            'employee_rate': ee_rate,
            'employer_rate': er_rate,
            'subsidy_rate': subsidy_rate,
            'subsidy_wage_threshold': subsidy_threshold,
            'total_rate': ee_rate + er_rate + subsidy_rate,
            'min_wage_limit': min_wage,
            'max_wage_limit': max_wage,
        }

    @api.model
    def resolve_gcc_pension_rates(self, country_code, date=None, as_decimal=False):
        """
        Resolves configurable, effective-dated parameters for GCC National home-country scheme.
        Returns:
            {
                'country_code': str,
                'employee_rate': float,
                'employer_rate': float,
                'employer_cap': float,
                'absorb_shortfall': bool,
                'max_wage_limit': float,
                'total_rate': float,
            }
        """
        ee_rate = self.get_gcc_pension_parameter(country_code, 'EE_RATE', date=date, as_decimal=as_decimal)
        er_rate = self.get_gcc_pension_parameter(country_code, 'ER_RATE', date=date, as_decimal=as_decimal)
        er_cap = self.get_gcc_pension_parameter(country_code, 'ER_CAP', date=date, as_decimal=as_decimal)
        absorb_shortfall = self.get_gcc_pension_parameter(country_code, 'ABSORB_SHORTFALL', date=date)
        max_wage = self.get_gcc_pension_parameter(country_code, 'MAX_WAGE', date=date)

        return {
            'country_code': (country_code or '').upper(),
            'employee_rate': ee_rate,
            'employer_rate': er_rate,
            'employer_cap': er_cap,
            'absorb_shortfall': bool(absorb_shortfall),
            'total_rate': ee_rate + er_rate,
            'max_wage_limit': max_wage,
        }
