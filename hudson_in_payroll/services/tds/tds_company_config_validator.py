# -*- coding: utf-8 -*-
import re


class TdsCompanyValidationResult:
    """
    Structured Result Container representing company TDS configuration validation.
    Decoupled from Odoo ORM models to allow pure Python testing and fast validation execution.
    """

    def __init__(self, is_valid, reason="", is_enabled=False, tan=None, default_tax_regime=None, default_tax_year=None):
        self.is_valid = is_valid
        self.reason = reason
        self.is_enabled = is_enabled
        self.tan = tan
        self.default_tax_regime = default_tax_regime
        self.default_tax_year = default_tax_year

    def to_dict(self):
        """Returns dictionary representation of validation result."""
        return {
            'is_valid': self.is_valid,
            'reason': self.reason,
            'is_enabled': self.is_enabled,
            'tan': self.tan,
            'default_tax_regime': self.default_tax_regime,
            'default_tax_year_id': self.default_tax_year.id if self.default_tax_year else False,
            'default_tax_year_name': self.default_tax_year.name if self.default_tax_year else False,
        }

    def __repr__(self):
        return (
            f"<TdsCompanyValidationResult valid={self.is_valid} "
            f"enabled={self.is_enabled} tan='{self.tan}' "
            f"regime='{self.default_tax_regime}' reason='{self.reason}'>"
        )


class TdsCompanyConfigValidator:
    """
    Validator for Company-level Tax Deducted at Source (TDS) Configuration.
    Single Responsibility: Validate company TDS status, TAN syntax, and regime settings.

    Business Rules:
    1. If TDS is disabled (hds_in_tds_applicable = False), return is_valid=True, is_enabled=False (calculations skipped).
    2. If TDS is enabled:
       - Require valid TAN (10 characters: 4 letters, 5 digits, 1 letter, e.g. ABCD12345E).
       - Require Default Tax Regime selection ('new' or 'old').
    """

    TAN_REGEX = re.compile(r'^[A-Z]{4}[0-9]{5}[A-Z]{1}$')

    def __init__(self, env=None):
        self.env = env

    def validate(self, company):
        """
        Validates company TDS configuration.

        :param company: res.company recordset or object with TDS attributes
        :return: TdsCompanyValidationResult
        """
        if not company:
            return TdsCompanyValidationResult(
                is_valid=False,
                reason="No company provided for TDS validation.",
                is_enabled=False
            )

        is_enabled = getattr(company, 'hds_in_tds_applicable', False)
        if not is_enabled:
            return TdsCompanyValidationResult(
                is_valid=True,
                reason=f"TDS is disabled for company '{company.name if hasattr(company, 'name') else 'Company'}'. Deductions skipped.",
                is_enabled=False
            )

        tan = (getattr(company, 'hds_in_tan', '') or '').strip().upper()
        if not tan:
            return TdsCompanyValidationResult(
                is_valid=False,
                reason=f"TAN is missing for company '{getattr(company, 'name', 'Company')}'.",
                is_enabled=True,
                tan=None
            )

        if not self.TAN_REGEX.match(tan):
            return TdsCompanyValidationResult(
                is_valid=False,
                reason=f"Invalid TAN format '{tan}' for company '{getattr(company, 'name', 'Company')}'. Must be 10 characters (e.g. ABCD12345E).",
                is_enabled=True,
                tan=tan
            )

        default_regime = getattr(company, 'hds_in_default_tax_regime', False)
        if not default_regime:
            return TdsCompanyValidationResult(
                is_valid=False,
                reason=f"Default Tax Regime is not configured for company '{getattr(company, 'name', 'Company')}'.",
                is_enabled=True,
                tan=tan,
                default_tax_regime=None
            )

        default_tax_year = getattr(company, 'hds_in_default_tax_year', None)

        return TdsCompanyValidationResult(
            is_valid=True,
            reason=f"TDS company configuration is valid for '{getattr(company, 'name', 'Company')}'.",
            is_enabled=True,
            tan=tan,
            default_tax_regime=default_regime,
            default_tax_year=default_tax_year
        )
