# -*- coding: utf-8 -*-
import logging
from odoo import fields
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class Section80DDTraceResult:
    """
    Data Transfer Object (DTO) holding Section 80DD statutory trace & deduction details.
    """
    def __init__(self, is_eligible=False, allowed_deduction=0.0, remarks="", trace_log="", is_severe=False):
        self.is_eligible = is_eligible
        self.allowed_deduction = allowed_deduction
        self.remarks = remarks
        self.trace_log = trace_log
        self.is_severe = is_severe


class Section80DDDeductionService(BaseStatutoryService):
    """
    Phase 5 Service: Section 80DD Statutory Trace & Eligibility Service.
    Generates detailed statutory audit traces for Section 80DD (Maintenance / Medical Treatment of Disabled Dependent).
    Single Source of Truth for Section 80DD statutory calculations.
    """

    def validate_and_trace(self, declaration_or_dict, eval_date=None, regime_code='old', employee=None, financial_year=None, **kwargs):
        """
        Evaluates Section 80DD statutory eligibility and produces standard ASCII statutory trace log.
        """
        regime = (regime_code or 'old').lower()

        # 1. Extract Declaration Inputs
        decl_state = 'draft'
        is_post_proof = False
        source_type = 'HEADER_DECLARATION'
        declared_amt = 0.0
        approved_amt_found = 0.0
        line_80dd = None

        if hasattr(declaration_or_dict, 'declaration_id') and getattr(declaration_or_dict, 'category', False) == '80dd':
            line_80dd = declaration_or_dict
            decl = line_80dd.declaration_id
            employee = employee or line_80dd.employee_id or (decl.employee_id if decl else None)
            financial_year = financial_year or line_80dd.financial_year_id or (decl.financial_year_id if decl else None)
            decl_state = getattr(decl, 'state', 'draft') if decl else getattr(line_80dd, 'validation_status', 'draft')
            is_post_proof = decl_state in ('proof_verified', 'approved')

            declared_amt = float(line_80dd.declared_amount or 0.0)
            line_approved = float(getattr(line_80dd, 'tax_firm_approved_amount', 0.0) or getattr(line_80dd, 'approved_amount', 0.0) or getattr(line_80dd, 'verified_amount', 0.0) or 0.0)
            approved_amt_found = line_approved
            source_type = 'DECLARATION_LINE'

            dep_name = getattr(decl, 'decl_80dd_dependent_name', 'N/A') if decl else 'N/A'
            relationship = getattr(decl, 'decl_80dd_relationship', 'child') if decl else 'child'
            dep_pan = getattr(decl, 'decl_80dd_dependent_pan', 'N/A') if decl else 'N/A'
            dep_dob = getattr(decl, 'decl_80dd_dependent_dob', False) if decl else False
            disability_exists = bool(getattr(decl, 'decl_80dd_disability_exists', False)) if decl else True
            has_certificate = bool(getattr(decl, 'decl_80dd_has_certificate', False)) if decl else True
            disability_percent = float(getattr(decl, 'decl_80dd_disability_percentage', 0.0) or 0.0) if decl else 0.0
            disability_cat = getattr(decl, 'decl_80dd_disability_category', 'autism') if decl else 'autism'
            cert_type = getattr(decl, 'decl_80dd_cert_type', 'permanent') if decl else 'permanent'
            cert_number = getattr(decl, 'decl_80dd_cert_number', False) if decl else False
            cert_issue_date = getattr(decl, 'decl_80dd_cert_issue_date', False) if decl else False
            cert_expiry_date = getattr(decl, 'decl_80dd_cert_expiry_date', False) if decl else False
            issuing_authority = getattr(decl, 'decl_80dd_issuing_authority', False) if decl else False
            has_maintenance = bool(getattr(decl, 'decl_80dd_has_maintenance_expenditure', False)) if decl else True
            has_insurance = bool(getattr(decl, 'decl_80dd_has_insurance_contribution', False)) if decl else False
            expenditure_amt = float(getattr(decl, 'decl_80dd_expenditure_amount', 0.0) or 0.0) if decl else declared_amt
            decl_id = decl.id if decl else 'N/A'

        elif hasattr(declaration_or_dict, 'decl_80dd_dependent_name'):
            decl = declaration_or_dict
            employee = employee or decl.employee_id
            financial_year = financial_year or decl.financial_year_id
            decl_state = getattr(decl, 'state', 'draft')
            is_post_proof = decl_state in ('proof_verified', 'approved')

            line_80dd = next((l for l in getattr(decl, 'declaration_line_ids', []) if l.category == '80dd' and getattr(l, 'active', True)), None)
            if line_80dd:
                declared_amt = float(line_80dd.declared_amount or 0.0)
                line_approved = float(getattr(line_80dd, 'tax_firm_approved_amount', 0.0) or getattr(line_80dd, 'approved_amount', 0.0) or getattr(line_80dd, 'verified_amount', 0.0) or 0.0)
                approved_amt_found = line_approved
                source_type = 'DECLARATION_LINE'
            else:
                declared_amt = float(getattr(decl, 'decl_80dd_expenditure_amount', 0.0) or 0.0)
                hdr_approved = float(getattr(decl, 'decl_80dd_approved_amount', 0.0) or getattr(decl, 'decl_80dd_amount', 0.0) or 0.0)
                approved_amt_found = hdr_approved
                source_type = 'HEADER_DECLARATION'

            dep_name = decl.decl_80dd_dependent_name or 'N/A'
            relationship = decl.decl_80dd_relationship or 'child'
            dep_pan = decl.decl_80dd_dependent_pan or 'N/A'
            dep_dob = decl.decl_80dd_dependent_dob
            disability_exists = bool(decl.decl_80dd_disability_exists)
            has_certificate = bool(getattr(decl, 'decl_80dd_has_certificate', False))
            disability_percent = float(decl.decl_80dd_disability_percentage or 0.0)
            disability_cat = decl.decl_80dd_disability_category or 'autism'
            cert_type = decl.decl_80dd_cert_type or 'permanent'
            cert_number = decl.decl_80dd_cert_number
            cert_issue_date = decl.decl_80dd_cert_issue_date
            cert_expiry_date = decl.decl_80dd_cert_expiry_date
            issuing_authority = decl.decl_80dd_issuing_authority
            has_maintenance = bool(decl.decl_80dd_has_maintenance_expenditure)
            has_insurance = bool(decl.decl_80dd_has_insurance_contribution)
            expenditure_amt = float(decl.decl_80dd_expenditure_amount or 0.0)
            decl_id = decl.id
        else:
            d = declaration_or_dict or {}
            decl = None
            decl_state = d.get('declaration_state', d.get('state', 'draft'))
            is_post_proof = decl_state in ('proof_verified', 'approved')
            declared_amt = float(d.get('declared_amount', d.get('decl_80dd_expenditure_amount', 0.0)))
            appr_val = float(d.get('tax_firm_approved_amount', d.get('approved_amount', 0.0)))
            approved_amt_found = appr_val
            source_type = d.get('source_type', 'DECLARATION_LINE')

            dep_name = d.get('decl_80dd_dependent_name', 'N/A')
            relationship = d.get('decl_80dd_relationship', 'child')
            dep_pan = d.get('decl_80dd_dependent_pan', 'N/A')
            dep_dob = d.get('decl_80dd_dependent_dob')
            disability_exists = bool(d.get('decl_80dd_disability_exists', True))
            has_certificate = bool(d.get('decl_80dd_has_certificate', True))
            disability_percent = float(d.get('decl_80dd_disability_percentage', 0.0))
            disability_cat = d.get('decl_80dd_disability_category', 'autism')
            cert_type = d.get('decl_80dd_cert_type', 'permanent')
            cert_number = d.get('decl_80dd_cert_number')
            cert_issue_date = d.get('decl_80dd_cert_issue_date')
            cert_expiry_date = d.get('decl_80dd_cert_expiry_date')
            issuing_authority = d.get('decl_80dd_issuing_authority')
            has_maintenance = bool(d.get('decl_80dd_has_maintenance_expenditure', True))
            has_insurance = bool(d.get('decl_80dd_has_insurance_contribution', False))
            expenditure_amt = float(d.get('decl_80dd_expenditure_amount', 0.0))
            decl_id = d.get('declaration_id', 'N/A')

        emp_name = employee.name if employee else kwargs.get('employee_name', 'N/A')
        emp_id = employee.id if employee else kwargs.get('employee_id', 'N/A')
        fy_name = financial_year.name if financial_year else 'N/A'
        
        # 1. Centralized Resident Validation
        from .resident_validation_service import ResidentValidationService
        res_svc = ResidentValidationService(self.env)
        res_res = res_svc.validate(employee or decl or kwargs, section_code="Section 80DD")
        is_resident = res_res.is_resident
        resident_status_str = res_res.status_label

        # Map Relationship & Category Labels
        rel_map = {
            'spouse': 'Spouse',
            'child': 'Child',
            'parent': 'Parent',
            'brother': 'Brother',
            'sister': 'Sister',
            'other': 'Other (Ineligible)'
        }
        rel_str = rel_map.get(relationship, 'Child')

        cat_map = {
            'blindness': 'Blindness',
            'low_vision': 'Low Vision',
            'leprosy_cured': 'Leprosy Cured',
            'hearing_impairment': 'Hearing Impairment',
            'locomotor_disability': 'Locomotor Disability',
            'mental_illness': 'Mental Illness',
            'autism': 'Autism Spectrum Disorder',
            'cerebral_palsy': 'Cerebral Palsy',
            'multiple_disabilities': 'Multiple Disabilities',
            'intellectual_disability': 'Intellectual Disability',
            'parkinsons': "Parkinson's Disease",
            'learning_disability': 'Specific Learning Disability',
            'acid_attack': 'Acid Attack Victim',
            'dwarfism': 'Dwarfism',
            'muscular_dystrophy': 'Muscular Dystrophy',
            'chronic_neurological_conditions': 'Chronic Neurological Conditions',
            'multiple_sclerosis': 'Multiple Sclerosis',
            'speech_and_language_disability': 'Speech and Language Disability',
            'thalassemia': 'Thalassemia',
            'hemophilia': 'Hemophilia',
            'sickle_cell_disease': 'Sickle Cell Disease',
            'other': 'Any Other Notified Disability'
        }
        cat_str = cat_map.get(disability_cat, 'Autism')

        # Resolve statutory rule parameters
        from .tds_parameter_service import TdsParameterService
        tds_param_svc = TdsParameterService(self.env)
        normal_deduction = tds_param_svc.get_80dd_normal_deduction(eval_date=eval_date)
        severe_deduction = tds_param_svc.get_80dd_severe_deduction(eval_date=eval_date)
        normal_disability_pct = tds_param_svc.get_80dd_normal_disability_percent(eval_date=eval_date)
        severe_disability_pct = tds_param_svc.get_80dd_severe_disability_percent(eval_date=eval_date)

        allow_only_resident = tds_param_svc.get_parameter('HDS_IN_TDS_80DD_ALLOW_ONLY_RESIDENT', eval_date=eval_date)
        if allow_only_resident is None:
            allow_only_resident = True

        eval_dt = eval_date or fields.Date.today()

        # Evaluate Statutory Conditions
        cond_regime = (regime == 'old')
        cond_resident = (not allow_only_resident or is_resident)
        cond_relationship = (relationship in ('spouse', 'child', 'parent', 'brother', 'sister'))
        cond_has_cert = bool(has_certificate)
        cond_cert_num = bool(cert_number and str(cert_number).strip() and str(cert_number).upper() != 'N/A')
        cond_cert_issue = bool(cert_issue_date)
        cond_cert_authority = bool(issuing_authority and str(issuing_authority).strip() and str(issuing_authority).upper() != 'N/A')

        if cert_type == 'permanent':
            cond_cert_expiry = True
            expiry_str = "Permanent"
        else:
            if not cert_expiry_date:
                cond_cert_expiry = False
                expiry_str = "N/A (Missing Expiry Date)"
            else:
                cond_cert_expiry = (cert_expiry_date >= eval_dt)
                expiry_str = cert_expiry_date.strftime('%d-%b-%Y') if hasattr(cert_expiry_date, 'strftime') else str(cert_expiry_date)

        cond_cert_valid = (cond_has_cert and cond_cert_num and cond_cert_issue and cond_cert_authority and cond_cert_expiry)
        line_is_severe = bool(getattr(line_80dd, 'is_severe_disability', False)) if line_80dd else False
        decl_is_severe = bool(getattr(decl, 'decl_80dd_is_severe_disability', False)) if decl else False
        is_severe = (disability_percent >= severe_disability_pct) or line_is_severe or decl_is_severe
        cond_disability_percent = (disability_percent >= normal_disability_pct) or is_severe

        is_eligible = False
        allowed_deduction = 0.0
        reason = ""

        if not cond_regime:
            reason = "Section 80DD Ineligible: Dependent disability deduction is available only under the Old Tax Regime (not permitted under New Tax Regime Income-tax Act, 2025 — Section 202(1))."
        elif not cond_resident:
            reason = res_res.failure_reason
        elif not cond_relationship:
            reason = f"Section 80DD Ineligible: Dependent relationship ({rel_str}) is not eligible under Section 80DD (Must be Spouse, Child, Parent, Brother, or Sister)."
        elif not cond_has_cert:
            reason = "Section 80DD Ineligible: No disability certificate has been provided."
        elif not cond_cert_num:
            reason = "Section 80DD Ineligible: Certificate Number is missing."
        elif not cond_cert_issue:
            reason = "Section 80DD Ineligible: Certificate Issue Date is missing."
        elif not cond_cert_authority:
            reason = "Section 80DD Ineligible: Issuing Medical Authority is missing."
        elif not cond_cert_expiry:
            reason = "Section 80DD Ineligible: Temporary disability certificate has expired." if cert_expiry_date else "Section 80DD Ineligible: Certificate Expiry Date is missing for temporary certificate."
        elif not cond_disability_percent:
            reason = f"Section 80DD Ineligible: Disability percentage ({disability_percent:.0f}%) is below the minimum statutory threshold of {normal_disability_pct:.0f}%."
        else:
            is_eligible = True
            if is_severe:
                allowed_deduction = severe_deduction
                reason = f"Dependent has severe disability ({disability_percent:.0f}% or more) supported by a valid medical certificate. Statutory flat deduction of INR {severe_deduction:,.0f} is allowable under Section 80DD."
            else:
                allowed_deduction = normal_deduction
                reason = f"Dependent has normal disability ({disability_percent:.0f}% to {severe_disability_pct - 1:.0f}%) supported by a valid medical certificate. Statutory flat deduction of INR {normal_deduction:,.0f} is allowable under Section 80DD."

        verified_amt = float(getattr(line_80dd, 'verified_amount', 0.0) or 0.0) if line_80dd else 0.0
        tax_firm_appr_amt = float(getattr(line_80dd, 'tax_firm_approved_amount', 0.0) or 0.0) if line_80dd else 0.0
        appr_amt = float(getattr(line_80dd, 'approved_amount', 0.0) or getattr(decl, 'decl_80dd_approved_amount', 0.0) or approved_amt_found or 0.0)
        statutory_flat_amount = (severe_deduction if is_severe else normal_deduction) if (disability_percent >= normal_disability_pct or is_severe) else 0.0
        eligible_ded = allowed_deduction if is_eligible else 0.0

        _logger.warning("""[80DD_FIELD_TRACE]
declared_amount=%s
approved_amount=%s
statutory_flat_amount=%s
eligible_deduction=%s
allowed_deduction=%s
declared_amount_source=%s""",
            declared_amt,
            appr_amt,
            statutory_flat_amount,
            eligible_ded,
            allowed_deduction,
            source_type
        )

        _logger.warning("""[80DD_AMOUNT_TRACE]
declared_amount=%s
verified_amount=%s
tax_firm_approved_amount=%s
approved_amount=%s
disability_percentage=%s
statutory_flat_amount=%s
eligible_deduction=%s
allowed_deduction=%s""",
            declared_amt,
            verified_amt,
            tax_firm_appr_amt,
            appr_amt,
            disability_percent,
            statutory_flat_amount,
            eligible_ded,
            allowed_deduction
        )

        _logger.warning("""[80DD_AUDIT]
disability_percentage=%s
declared_amount=%s
verified_amount=%s
approved_amount=%s
eligibility_result=%s
statutory_flat_amount=%s
final_allowed_80dd=%s""",
            disability_percent, declared_amt, verified_amt, appr_amt,
            is_eligible, statutory_flat_amount, allowed_deduction
        )

        _logger.warning("""[TDS_DEBUG_TRACE][SECTION_TRACE]
section=80DD
declaration_state=%s
declared_amount=%s
approved_amount=%s
eligible_amount=%s
usable_amount=%s
selected_amount=%s
final_chapter6a_amount=%s
source_type=%s""",
            decl_state, declared_amt, approved_amt_found, allowed_deduction, allowed_deduction, allowed_deduction, allowed_deduction, source_type
        )

        if not cond_has_cert:
            cert_type_str = "N/A"
            cert_num_str = "N/A"
            issue_date_str = "N/A"
            expiry_str = "N/A"
            authority_str = "N/A"

            check_num_str = "NOT APPLICABLE"
            check_issue_str = "NOT APPLICABLE"
            check_authority_str = "NOT APPLICABLE"
            check_expiry_str = "NOT APPLICABLE"
        else:
            cert_type_str = "Permanent" if cert_type == 'permanent' else "Temporary"
            cert_num_str = str(cert_number) if cert_number else 'N/A'
            issue_date_str = cert_issue_date.strftime('%d-%b-%Y') if hasattr(cert_issue_date, 'strftime') and cert_issue_date else (str(cert_issue_date) if cert_issue_date else 'N/A')
            authority_str = str(issuing_authority) if issuing_authority else 'N/A'

            check_num_str = "PASS" if cond_cert_num else "FAIL"
            check_issue_str = "PASS" if cond_cert_issue else "FAIL"
            check_authority_str = "PASS" if cond_cert_authority else "FAIL"
            check_expiry_str = "PASS" if cond_cert_expiry else "FAIL"

        if not is_eligible:
            ded_type_str = "Not Applicable"
            max_allowable_str = "INR 0"
        else:
            if is_severe:
                ded_type_str = "Severe Disability (80% or more)"
                max_allowable_str = f"INR {severe_deduction:,.0f}"
            else:
                ded_type_str = "Normal Disability (40% to 79%)"
                max_allowable_str = f"INR {normal_deduction:,.0f}"

        # 3. Generate Multi-Line Statutory Trace Log
        trace_log = f"""
=========================================================
SECTION 80DD STATUTORY TRACE
=========================================================

Employee                : {emp_name}
Employee ID             : {emp_id}
Financial Year          : {fy_name}
Declaration ID          : {decl_id}

---------------------------------------------------------
DECLARATION INPUTS
---------------------------------------------------------

Dependent Name          : {dep_name}
Relationship            : {rel_str}

Disability Percentage   : {disability_percent:.0f}%

Disability Category     : {cat_str}

Medical Certificate Available: {"YES" if cond_has_cert else "NO"}

Certificate Type        : {cert_type_str}

Certificate Number      : {cert_num_str}

Issue Date              : {issue_date_str}

Expiry Date             : {expiry_str}

Issuing Medical Authority: {authority_str}

Computed Certificate Valid: {"YES" if cond_cert_valid else "NO"}

Actual Expenditure      : INR {expenditure_amt:,.2f}

LIC / Approved Scheme   : {"YES" if has_insurance else "NO"}

Amount Paid             : INR {expenditure_amt:,.2f}

Income Tax Resident Status: {resident_status_str}

Tax Regime              : {"Old" if cond_regime else "New"}

---------------------------------------------------------
STATUTORY ELIGIBILITY CHECKS
---------------------------------------------------------

Old Regime

{"PASS" if cond_regime else "FAIL"}

---------------------------------------------------------

Income Tax Resident Status

{resident_status_str}

{"PASS" if cond_resident else "FAIL"}

---------------------------------------------------------

Eligible Relationship

{"PASS" if cond_relationship else "FAIL"}

---------------------------------------------------------

Medical Certificate Available

{"PASS" if cond_has_cert else "FAIL"}

---------------------------------------------------------

Certificate Number

{cert_num_str}

{check_num_str}

---------------------------------------------------------

Certificate Issue Date

{issue_date_str}

{check_issue_str}

---------------------------------------------------------

Issuing Medical Authority

{authority_str}

{check_authority_str}

---------------------------------------------------------

Certificate Expiry

{expiry_str}

{check_expiry_str}

---------------------------------------------------------

Computed Certificate Valid

{"YES" if cond_cert_valid else "NO"}

{"PASS" if cond_cert_valid else "FAIL"}

---------------------------------------------------------

Disability Percentage

{disability_percent:.0f}%

{"PASS" if cond_disability_percent else "FAIL"}

---------------------------------------------------------

Severe Disability

{"YES" if is_severe else "NO"}

---------------------------------------------------------
STATUTORY CALCULATION
---------------------------------------------------------

Statutory Deduction Type

{ded_type_str}

Maximum Allowable

{max_allowable_str}

Approved Section 80DD Deduction

INR {allowed_deduction:,.0f}

---------------------------------------------------------
FINAL RESULT
---------------------------------------------------------

Eligible

{"YES" if is_eligible else "NO"}

Approved Deduction

INR {allowed_deduction:,.0f}

Reason

{reason}

=========================================================
"""

        remarks = f"Section 80DD Status: {'ELIGIBLE' if is_eligible else 'INELIGIBLE'}. {reason}"
        _logger.warning(trace_log)

        return Section80DDTraceResult(
            is_eligible=is_eligible,
            allowed_deduction=allowed_deduction,
            remarks=remarks,
            trace_log=trace_log,
            is_severe=is_severe
        )
