# -*- coding: utf-8 -*-
"""
HUDSON PAYROLL ENGINE - RESIDENT VALIDATION SERVICE
Centralized service for Income Tax Resident Status verification across all TDS deduction/exemption modules.
"""

import logging
_logger = logging.getLogger(__name__)


class ResidentValidationResult:
    """DTO for Resident Validation Result."""
    def __init__(self, is_resident, status_code, status_label, failure_reason=""):
        self.is_resident = is_resident
        self.status_code = status_code
        self.status_label = status_label
        self.failure_reason = failure_reason

    def __bool__(self):
        return self.is_resident


class ResidentValidationService:
    """
    Centralized validation service for verifying employee Income Tax Resident Status.
    Derives residency from hr.employee.resident_status (or legacy hds_in_residential_status / residency_status).
    """

    def __init__(self, env=None):
        self.env = env

    def get_resident_status(self, employee_or_decl):
        """
        Extracts standardized resident status code ('resident' or 'non_resident')
        and human-readable label ('Resident' or 'Non-Resident').
        """
        if not employee_or_decl:
            return 'resident', 'Resident'

        emp = employee_or_decl
        if hasattr(employee_or_decl, 'employee_id') and getattr(employee_or_decl, 'employee_id', False):
            emp = employee_or_decl.employee_id

        res_val = getattr(emp, 'hds_in_residential_status', False) or getattr(emp, 'resident_status', False) or getattr(emp, 'residency_status', False) or 'resident'
        
        if hasattr(res_val, 'lower'):
            res_val = res_val.lower()

        if res_val in ('ror', 'resident'):
            return 'resident', 'Resident (ROR)'
        elif res_val == 'rnor':
            return 'resident', 'Resident (RNOR)'
        elif res_val in ('nre', 'non_resident'):
            return 'non_resident', 'Non-Resident'
        
        return 'resident', 'Resident'

    def is_resident(self, employee_or_decl):
        """Returns True if employee has Resident status, False otherwise."""
        status_code, _ = self.get_resident_status(employee_or_decl)
        return status_code == 'resident'

    def validate(self, employee_or_decl, section_code="Section"):
        """
        Validates Resident status for a specific tax section.
        Returns ResidentValidationResult DTO.
        """
        status_code, status_label = self.get_resident_status(employee_or_decl)
        is_res = (status_code == 'resident')

        failure_reason = ""
        if not is_res:
            failure_reason = f"{section_code} Ineligible: Deduction under {section_code} is available only to a Resident Individual."

        return ResidentValidationResult(
            is_resident=is_res,
            status_code=status_code,
            status_label=status_label,
            failure_reason=failure_reason
        )
