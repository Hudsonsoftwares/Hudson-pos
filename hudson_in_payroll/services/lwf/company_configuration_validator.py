# -*- coding: utf-8 -*-


class CompanyValidationResult:
    """Data container for company LWF configuration validation results."""
    def __init__(self, is_valid, reason="", is_enabled=True, registration_no=None):
        self.is_valid = is_valid
        self.reason = reason
        self.is_enabled = is_enabled
        self.registration_no = registration_no


class CompanyConfigurationValidator:
    """
    Validator for Company-level Labour Welfare Fund (LWF) Configuration.
    Single Responsibility: Validate whether LWF is enabled for the company and
    whether company-level statutory requirements are satisfied.
    """

    def __init__(self, env):
        self.env = env

    def validate(self, company):
        """
        Validates company LWF configuration.

        :param company: res.company recordset or None
        :return: CompanyValidationResult
        """
        if not company:
            return CompanyValidationResult(
                is_valid=False,
                reason="No company provided in context.",
                is_enabled=False
            )

        is_enabled = getattr(company, 'hds_in_enable_lwf', True)
        if not is_enabled:
            return CompanyValidationResult(
                is_valid=False,
                reason=f"Labour Welfare Fund (LWF) is disabled for company '{company.name}'.",
                is_enabled=False
            )

        registration_no = getattr(company, 'hds_in_lwf_registration_no', False)

        return CompanyValidationResult(
            is_valid=True,
            reason=f"LWF is enabled for company '{company.name}'.",
            is_enabled=True,
            registration_no=registration_no
        )
