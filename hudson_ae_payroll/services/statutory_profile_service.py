# -*- coding: utf-8 -*-
from odoo import fields


class UAEStatutoryProfileService:
    """
    UAE Statutory Profile Resolution Service.

    Resolves the comprehensive statutory context for a given employer and employee
    in the UAE localization framework without performing financial calculations.

    Resolution Hierarchy:
    1. Company Level (Country, Sector, Jurisdiction, Emirate, Labour Authority)
    2. Employee Statutory Classification (Category, Registration Status, Numbers)
    3. Authority Context Resolution (Employee-specific override -> Company/Emirate defaults)
    4. Service & Statutory Verification Context
    """

    def __init__(self, env):
        self.env = env

    def get_statutory_profile(self, company, employee, evaluation_date=None):
        """
        Builds and returns the normalized UAE statutory profile context.

        :param company: res.company record
        :param employee: hr.employee record
        :param evaluation_date: date or string (optional, defaults to today)
        :return: dict representing the complete statutory context
        """
        if not evaluation_date:
            evaluation_date = fields.Date.today()
        elif isinstance(evaluation_date, str):
            evaluation_date = fields.Date.from_string(evaluation_date)

        # 1. Company Jurisdiction & Location Context
        country_code = company.country_id.code if company and company.country_id else None
        is_uae_company = bool(country_code == 'AE')

        jurisdiction = getattr(company, 'uae_jurisdiction_id', False)
        jurisdiction_type = getattr(company, 'uae_jurisdiction_type', False) or (
            jurisdiction.jurisdiction_type if jurisdiction else 'mainland'
        )

        emirate = getattr(employee, 'uae_emirate_id', False) or getattr(company, 'uae_emirate_id', False) or (
            jurisdiction.emirate_id if jurisdiction else False
        )

        labour_authority = getattr(company, 'uae_labour_authority_id', False) or (
            jurisdiction.labour_authority_id if jurisdiction else False
        )

        # 2. Employee Statutory Context
        emp_category = getattr(employee, 'uae_employee_category', False) or 'expatriate'
        pension_status = getattr(employee, 'uae_pension_registration_status', False) or (
            'not_applicable' if emp_category == 'expatriate' else 'pending_verification'
        )
        pension_reg_no = getattr(employee, 'uae_pension_registration_number', False) or None
        pension_scheme = getattr(employee, 'uae_pension_scheme_id', False)
        continuous_service_date = getattr(employee, 'uae_continuous_service_start_date', False) or (
            getattr(employee, 'create_date', False).date() if hasattr(employee, 'create_date') and employee.create_date else evaluation_date
        )
        overtime_eligibility = getattr(employee, 'uae_overtime_eligibility', False) or 'eligible'
        statutory_status = getattr(employee, 'uae_statutory_status', False) or 'draft'

        # 3. Pension Authority Resolution (Hierarchy: Employee Specific -> Default / Scheme)
        resolved_pension_authority = self._resolve_pension_authority(
            company=company,
            employee=employee,
            emp_category=emp_category,
            emirate=emirate
        )

        is_authority_enabled = bool(
            company and resolved_pension_authority and hasattr(company, 'is_pension_authority_enabled')
            and company.is_pension_authority_enabled(resolved_pension_authority)
        )

        profile = {
            'country': country_code or 'AE',
            'is_uae_company': is_uae_company,
            'employment_sector': getattr(company, 'uae_employment_sector', False) or 'private',
            'jurisdiction': {
                'id': jurisdiction.id if jurisdiction else None,
                'code': jurisdiction.code if jurisdiction else None,
                'name': jurisdiction.name if jurisdiction else (
                    'Mainland' if jurisdiction_type == 'mainland' else 'Free Zone'
                ),
                'type': jurisdiction_type or 'mainland',
            },
            'emirate': {
                'id': emirate.id if emirate else None,
                'code': emirate.code if emirate else None,
                'name': emirate.name if emirate else None,
            } if emirate else None,
            'labour_authority': {
                'id': labour_authority.id if labour_authority else None,
                'code': labour_authority.code if labour_authority else None,
                'name': labour_authority.name if labour_authority else None,
                'authority_type': labour_authority.authority_type if labour_authority else None,
            } if labour_authority else None,
            'employee_category': emp_category,
            'pension_registration_status': pension_status,
            'pension_authority': {
                'id': resolved_pension_authority.id,
                'code': resolved_pension_authority.code,
                'name': resolved_pension_authority.name,
                'authority_type': resolved_pension_authority.authority_type,
                'is_enabled_at_company': is_authority_enabled,
                'validation_status': 'VALID' if is_authority_enabled else 'AUTHORITY_NOT_ENABLED_AT_COMPANY',
            } if resolved_pension_authority else None,
            'pension_scheme': {
                'id': pension_scheme.id,
                'code': pension_scheme.code,
                'name': pension_scheme.name,
            } if pension_scheme else None,
            'pension_registration_number': pension_reg_no,
            'continuous_service_start_date': str(continuous_service_date) if continuous_service_date else None,
            'overtime_eligibility': overtime_eligibility,
            'statutory_status': statutory_status,
            'evaluation_date': str(evaluation_date),
        }

        return profile

    def _resolve_pension_authority(self, company, employee, emp_category, emirate):
        """
        Resolves governing pension authority dynamically from configured mapping:
        Applicable Emirate + Applicable Jurisdiction / Jurisdiction Type -> Pension Authority Resolver.
        """
        if emp_category not in ('uae_national', 'gcc_national'):
            return None

        # 1. Direct authority reference if already computed on employee
        if getattr(employee, 'uae_pension_authority_id', False):
            return employee.uae_pension_authority_id

        # 2. Employee jurisdiction mapping
        emp_jur = getattr(employee, 'uae_jurisdiction_id', False)
        if emp_jur and getattr(emp_jur, 'pension_authority_id', False):
            return emp_jur.pension_authority_id

        # 3. Company jurisdiction mapping
        comp_jur = getattr(company, 'uae_jurisdiction_id', False)
        if comp_jur and getattr(comp_jur, 'pension_authority_id', False):
            return comp_jur.pension_authority_id

        # 4. Employee's applicable Emirate or physical work location
        emp_emirate = getattr(employee, 'uae_emirate_id', False)
        if not emp_emirate and getattr(employee, 'work_location_id', False):
            emp_emirate = getattr(employee.work_location_id, 'uae_emirate_id', False)
        if emp_emirate and emp_emirate.pension_authority_id:
            return emp_emirate.pension_authority_id

        # 5. Company/jurisdiction Emirate mapping
        if emirate and emirate.pension_authority_id:
            return emirate.pension_authority_id

        return None


# Reusable alias for compatibility with eligibility engine naming
UAEEligibilityService = UAEStatutoryProfileService
