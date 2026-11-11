# -*- coding: utf-8 -*-
"""
HUDSON PAYROLL ENGINE - SECTION 80U DEDUCTION SERVICE
Statutory calculation and verification engine for Section 80U (Deduction for Person with Disability - Employee Own Disability).
"""

import logging
import datetime
from odoo import fields

_logger = logging.getLogger(__name__)


class Section80UTraceResult:
    """DTO for Section 80U Statutory Verification and Audit Trace."""
    def __init__(self, is_eligible, allowed_deduction, remarks, trace_log, is_severe=False):
        self.is_eligible = is_eligible
        self.allowed_deduction = allowed_deduction
        self.remarks = remarks
        self.trace_log = trace_log
        self.is_severe = is_severe


class Section80UDeductionService:
    """
    Statutory Section 80U Deduction Engine (Employee's Own Disability).

    Statutory Rules:
    - Applies to Old Tax Regime only.
    - Resident Individual taxpayers only.
    - Medical Certificate issued by prescribed authority is mandatory.
    - Minimum disability percentage is 40%.
    - Normal disability (40% - 79%) -> Fixed deduction ₹75,000.
    - Severe disability (>= 80%) -> Fixed deduction ₹1,25,000.
    - Strictly for Employee's own disability (No dependent fields).
    """

    def __init__(self, env=None):
        self.env = env

    def validate_and_trace(self, declaration_or_dict, regime_code=None, employee=None, financial_year=None, eval_date=None, **kwargs):
        d = declaration_or_dict
        decl_state = 'draft'
        is_post_proof = False
        source_type = 'HEADER_DECLARATION'
        declared_amt = 0.0
        approved_amt_found = 0.0
        line_80u = None

        if hasattr(d, 'decl_80u_disability_percentage'):
            decl = d
            employee = employee or getattr(decl, 'employee_id', False)
            financial_year = financial_year or getattr(decl, 'financial_year_id', False)
            decl_state = getattr(decl, 'state', 'draft')
            is_post_proof = decl_state in ('proof_verified', 'approved')

            lines_80u = [l for l in getattr(decl, 'declaration_line_ids', []) if l.category == '80u' and getattr(l, 'active', True)]
            if lines_80u:
                declared_amt = max(float(l.declared_amount or 0.0) for l in lines_80u)
                approved_amt_found = max(float(getattr(l, 'tax_firm_approved_amount', 0.0) or getattr(l, 'approved_amount', 0.0) or 0.0) for l in lines_80u)
                source_type = 'DECLARATION_LINE'
            else:
                declared_amt = float(getattr(decl, 'decl_80u_amount', 0.0) or 0.0)
                hdr_approved = float(getattr(decl, 'decl_80u_approved_amount', 0.0) or 0.0)
                approved_amt_found = hdr_approved
                source_type = 'HEADER_DECLARATION'

            disability_percent = float(getattr(d, 'decl_80u_disability_percentage', 0.0) or 0.0)
            disability_cat = getattr(d, 'decl_80u_disability_category', 'autism') or 'autism'
            has_certificate = getattr(d, 'decl_80u_has_certificate', False) or (is_post_proof and approved_amt_found > 0.0)
            cert_type = getattr(d, 'decl_80u_cert_type', 'permanent') or 'permanent'
            cert_number = getattr(d, 'decl_80u_cert_number', False) or ('VERIFIED-PROOF' if is_post_proof and approved_amt_found > 0.0 else False)
            cert_issue_date = getattr(d, 'decl_80u_cert_issue_date', False) or (fields.Date.today() if is_post_proof and approved_amt_found > 0.0 else False)
            cert_expiry_date = getattr(d, 'decl_80u_cert_expiry_date', False)
            issuing_authority = getattr(d, 'decl_80u_issuing_authority', False) or ('Medical Authority' if is_post_proof and approved_amt_found > 0.0 else False)

            reassessment_pending = bool(getattr(d, 'decl_80u_reassessment_pending', False))
            renewal_cert_number = getattr(d, 'decl_80u_renewal_cert_number', False)
            renewal_issue_date = getattr(d, 'decl_80u_renewal_issue_date', False)
            renewal_expiry_date = getattr(d, 'decl_80u_renewal_expiry_date', False)
            renewal_disability_percent = float(getattr(d, 'decl_80u_renewal_disability_percentage', 0.0) or 0.0)

            regime = regime_code or getattr(d, 'regime_code', 'old')
            decl_id = getattr(d, 'id', 'N/A')
        elif isinstance(d, dict):
            decl_state = d.get('declaration_state', d.get('state', 'draft'))
            is_post_proof = decl_state in ('proof_verified', 'approved')
            declared_amt = float(d.get('declared_amount', d.get('decl_80u_amount', 0.0)))
            appr_val = float(d.get('tax_firm_approved_amount', d.get('approved_amount', 0.0)))
            approved_amt_found = appr_val
            source_type = d.get('source_type', 'DECLARATION_LINE')

            disability_percent = float(d.get('decl_80u_disability_percentage', 0.0))
            disability_cat = d.get('decl_80u_disability_category', 'autism')
            has_certificate = d.get('decl_80u_has_certificate', False) or (is_post_proof and approved_amt_found > 0.0)
            cert_type = d.get('decl_80u_cert_type', 'permanent')
            cert_number = d.get('decl_80u_cert_number', 'VERIFIED-PROOF' if is_post_proof and approved_amt_found > 0.0 else False)
            cert_issue_date = d.get('decl_80u_cert_issue_date', fields.Date.today() if is_post_proof and approved_amt_found > 0.0 else False)
            cert_expiry_date = d.get('decl_80u_cert_expiry_date', False)
            issuing_authority = d.get('decl_80u_issuing_authority', 'Medical Authority' if is_post_proof and approved_amt_found > 0.0 else False)

            reassessment_pending = bool(d.get('decl_80u_reassessment_pending', d.get('reassessment_pending', False)))
            renewal_cert_number = d.get('decl_80u_renewal_cert_number', d.get('renewal_cert_number', False))
            renewal_issue_date = d.get('decl_80u_renewal_issue_date', d.get('renewal_issue_date', False))
            renewal_expiry_date = d.get('decl_80u_renewal_expiry_date', d.get('renewal_expiry_date', False))
            renewal_disability_percent = float(d.get('decl_80u_renewal_disability_percentage', d.get('renewal_disability_percentage', 0.0)))

            regime = regime_code or d.get('regime_code', 'old')
            decl_id = d.get('declaration_id', 'N/A')
        else:
            decl_state = kwargs.get('declaration_state', 'draft')
            is_post_proof = decl_state in ('proof_verified', 'approved')
            declared_amt = float(kwargs.get('declared_amount', kwargs.get('decl_80u_amount', 0.0)))
            appr_val = float(kwargs.get('tax_firm_approved_amount', kwargs.get('approved_amount', 0.0)))
            approved_amt_found = appr_val
            source_type = kwargs.get('source_type', 'DECLARATION_LINE')

            disability_percent = float(kwargs.get('decl_80u_disability_percentage', 0.0))
            disability_cat = kwargs.get('decl_80u_disability_category', 'autism')
            has_certificate = kwargs.get('decl_80u_has_certificate', False) or (is_post_proof and approved_amt_found > 0.0)
            cert_type = kwargs.get('decl_80u_cert_type', 'permanent')
            cert_number = kwargs.get('decl_80u_cert_number', 'VERIFIED-PROOF' if is_post_proof and approved_amt_found > 0.0 else False)
            cert_issue_date = kwargs.get('decl_80u_cert_issue_date', fields.Date.today() if is_post_proof and approved_amt_found > 0.0 else False)
            cert_expiry_date = kwargs.get('decl_80u_cert_expiry_date', False)
            issuing_authority = kwargs.get('decl_80u_issuing_authority', 'Medical Authority' if is_post_proof and approved_amt_found > 0.0 else False)

            reassessment_pending = bool(kwargs.get('decl_80u_reassessment_pending', kwargs.get('reassessment_pending', False)))
            renewal_cert_number = kwargs.get('decl_80u_renewal_cert_number', kwargs.get('renewal_cert_number', False))
            renewal_issue_date = kwargs.get('decl_80u_renewal_issue_date', kwargs.get('renewal_issue_date', False))
            renewal_expiry_date = kwargs.get('decl_80u_renewal_expiry_date', kwargs.get('renewal_expiry_date', False))
            renewal_disability_percent = float(kwargs.get('decl_80u_renewal_disability_percentage', kwargs.get('renewal_disability_percentage', 0.0)))

            regime = regime_code or kwargs.get('regime_code', 'old')
            decl_id = 'N/A'

        emp_name = employee.name if employee else kwargs.get('employee_name', 'N/A')
        emp_id = employee.id if employee else kwargs.get('employee_id', 'N/A')
        fy_name = financial_year.name if financial_year else 'N/A'

        # 1. Centralized Resident Validation
        from .resident_validation_service import ResidentValidationService
        res_svc = ResidentValidationService(self.env)
        res_res = res_svc.validate(employee or d or kwargs, section_code="Section 80U")
        is_resident = res_res.is_resident
        resident_status_str = res_res.status_label

        # Disability Category Display Label Mapping
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
        }
        cat_str = cat_map.get(disability_cat, 'Autism Spectrum Disorder')

        # Resolve statutory rule parameters
        from .tds_parameter_service import TdsParameterService
        tds_param_svc = TdsParameterService(self.env)
        normal_deduction = tds_param_svc.get_80u_normal_deduction(eval_date=eval_date)
        severe_deduction = tds_param_svc.get_80u_severe_deduction(eval_date=eval_date)
        normal_disability_pct = tds_param_svc.get_80u_normal_disability_percent(eval_date=eval_date)
        severe_disability_pct = tds_param_svc.get_80u_severe_disability_percent(eval_date=eval_date)
        allow_only_resident = tds_param_svc.get_80u_allow_only_resident(eval_date=eval_date)

        # FY Period Determination for Timeline Verification
        eval_dt = eval_date or fields.Date.today()
        eval_date_obj = eval_dt if hasattr(eval_dt, 'year') else fields.Date.from_string(str(eval_dt))

        fy_start = False
        fy_end = False
        if financial_year:
            fy_start = getattr(financial_year, 'start_date', False) or getattr(financial_year, 'date_from', False)
            fy_end = getattr(financial_year, 'end_date', False) or getattr(financial_year, 'date_to', False)

        if not fy_start or not fy_end:
            yr = eval_date_obj.year if eval_date_obj.month >= 4 else eval_date_obj.year - 1
            fy_start = fields.Date.from_string(f"{yr}-04-01")
            fy_end = fields.Date.from_string(f"{yr + 1}-03-31")

        # Convert string dates to Date objects if needed
        c_issue = fields.Date.from_string(cert_issue_date) if isinstance(cert_issue_date, str) else cert_issue_date
        c_expiry = fields.Date.from_string(cert_expiry_date) if isinstance(cert_expiry_date, str) else cert_expiry_date
        r_issue = fields.Date.from_string(renewal_issue_date) if isinstance(renewal_issue_date, str) else renewal_issue_date
        r_expiry = fields.Date.from_string(renewal_expiry_date) if isinstance(renewal_expiry_date, str) else renewal_expiry_date

        active_disability_pct = disability_percent
        prev_cert_info = "N/A"
        curr_cert_info = f"Cert #{cert_number or 'N/A'} (Issued: {c_issue or 'N/A'}, Expiry: {c_expiry or 'N/A'})"
        reassessment_status_str = "NOT REQUIRED"
        overlap_status = "FULL_FY_COVERAGE"

        cond_regime = (regime == 'old')
        cond_resident = (is_resident if allow_only_resident else True)
        cond_has_cert = bool(has_certificate)
        cond_cert_num = bool(cert_number and str(cert_number).strip() and str(cert_number).upper() != 'N/A')
        cond_cert_issue = bool(c_issue)
        cond_cert_authority = bool(issuing_authority and str(issuing_authority).strip() and str(issuing_authority).upper() != 'N/A')

        if cert_type == 'permanent':
            cond_cert_expiry = True
            expiry_str = "Permanent"
            overlap_status = "FULL_FY_COVERAGE (Permanent)"
        else:
            # Temporary Certificate Validity Timeline Evaluation (Scenarios A through G)
            if not c_expiry:
                cond_cert_expiry = False
                expiry_str = "N/A (Missing Expiry Date)"
                overlap_status = "MISSING_EXPIRY_DATE"
            else:
                expiry_str = c_expiry.strftime('%d-%b-%Y') if hasattr(c_expiry, 'strftime') else str(c_expiry)

                # Check 1: Primary cert covers full FY or extends to/past FY end
                if c_expiry >= fy_end:
                    cond_cert_expiry = True
                    if c_issue and c_issue > fy_start:
                        overlap_status = "STARTS_DURING_FY (Full FY Granted)"  # Scenario B
                    else:
                        overlap_status = "FULL_FY_COVERAGE"  # Scenario A

                # Check 2: Primary cert expires DURING the FY (fy_start <= c_expiry < fy_end)
                elif fy_start <= c_expiry < fy_end:
                    overlap_status = "EXPIRES_DURING_FY"
                    if renewal_cert_number or r_issue:
                        # Scenario C / G: Renewed within FY
                        cond_cert_expiry = True
                        reassessment_status_str = f"RENEWED (New Cert #{renewal_cert_number or 'N/A'}, Issued: {r_issue or 'N/A'})"
                        prev_cert_info = f"Primary Cert #{cert_number} (Expired: {c_expiry})"
                        curr_cert_info = f"Renewed Cert #{renewal_cert_number} (Issued: {r_issue}, Expiry: {r_expiry or 'Permanent'})"
                        if renewal_disability_percent > 0.0:
                            active_disability_pct = renewal_disability_percent  # Scenario G
                    elif reassessment_pending:
                        # Scenario D: Reassessment Pending
                        cond_cert_expiry = True
                        reassessment_status_str = "PENDING (Reassessment Application Documented)"
                    else:
                        # Scenario E: Expired without Renewal / Reassessment
                        cond_cert_expiry = False
                        reassessment_status_str = "NONE (Expired without Renewal/Reassessment)"

                # Check 3: Primary cert expired BEFORE FY starts (c_expiry < fy_start)
                elif c_expiry < fy_start:
                    if renewal_cert_number and (not r_expiry or r_expiry >= fy_start):
                        cond_cert_expiry = True
                        overlap_status = "RENEWED_FOR_FY"
                        reassessment_status_str = f"RENEWED (New Cert #{renewal_cert_number}, Issued: {r_issue})"
                        prev_cert_info = f"Old Cert #{cert_number} (Expired: {c_expiry})"
                        curr_cert_info = f"Renewed Cert #{renewal_cert_number} (Issued: {r_issue}, Expiry: {r_expiry or 'Permanent'})"
                        if renewal_disability_percent > 0.0:
                            active_disability_pct = renewal_disability_percent
                    else:
                        # Scenario F: Expired Pre-FY
                        cond_cert_expiry = False
                        overlap_status = "EXPIRED_BEFORE_FY_START"
                        reassessment_status_str = "NONE (Expired Before FY Start)"

        # Effective Disability Percentage & Certificate Selection
        if renewal_disability_percent > 0.0:
            active_disability_pct = renewal_disability_percent
            effective_cert_str = "Renewed"
        else:
            active_disability_pct = disability_percent
            effective_cert_str = "Primary"

        cond_cert_valid = (cond_has_cert and cond_cert_num and cond_cert_issue and cond_cert_authority and cond_cert_expiry)

        # Strictly derive severe disability status from active disability percentage threshold
        is_severe = (active_disability_pct >= severe_disability_pct)
        cond_disability_percent = (active_disability_pct >= normal_disability_pct)

        is_eligible = False
        allowed_deduction = 0.0
        reasons = []

        if not cond_regime:
            reasons.append("Section 80U Ineligible: Employee disability deduction is available only under the Old Tax Regime (not permitted under New Tax Regime Income-tax Act, 2025 — Section 202(1)).")
        if not cond_resident:
            reasons.append(res_res.failure_reason if hasattr(res_res, 'failure_reason') and res_res.failure_reason else "Section 80U Ineligible: Employee is a Non-Resident.")
        if not cond_has_cert:
            reasons.append("Section 80U Ineligible: Medical certificate not available.")
        if cond_has_cert and not cond_cert_num:
            reasons.append("Section 80U Ineligible: Certificate Number is missing.")
        if cond_has_cert and not cond_cert_issue:
            reasons.append("Section 80U Ineligible: Certificate Issue Date is missing.")
        if cond_has_cert and not cond_cert_authority:
            reasons.append("Section 80U Ineligible: Issuing Medical Authority is missing.")
        if cond_has_cert and not cond_cert_expiry:
            if not c_expiry:
                reasons.append("Section 80U Ineligible: Certificate Expiry Date is missing for temporary certificate.")
            elif c_expiry < fy_start and not renewal_cert_number and not r_issue:
                reasons.append("Section 80U Ineligible: Disability certificate expired before financial year start.")
            else:
                reasons.append("Section 80U Ineligible: Temporary disability certificate has expired without renewal or pending reassessment.")
        if not cond_disability_percent:
            reasons.append(f"Section 80U Ineligible: Disability percentage ({active_disability_pct:.2f}%) is below the statutory minimum of {normal_disability_pct:.0f}% prescribed under Section 80U.")

        if not reasons:
            is_eligible = True
            statutory_entitlement = severe_deduction if is_severe else normal_deduction
            allowed_deduction = statutory_entitlement
            declared_amt = statutory_entitlement
            if is_post_proof and approved_amt_found > 0.0:
                reason = f"Verified employee disability proof approved by HR/Tax Firm. Allowed statutory deduction of INR {allowed_deduction:,.0f} under Section 80U."
            elif is_severe:
                reason = f"Employee has severe disability ({active_disability_pct:.2f}% >= {severe_disability_pct:.0f}%) supported by a valid medical certificate. Statutory deduction of INR {severe_deduction:,.0f} is allowable under Section 80U."
            else:
                reason = f"Employee has normal disability ({active_disability_pct:.2f}% in {normal_disability_pct:.0f}%–{severe_disability_pct - 1:.0f}%) supported by a valid medical certificate. Statutory deduction of INR {normal_deduction:,.0f} is allowable under Section 80U."
        else:
            is_eligible = False
            allowed_deduction = 0.0
            declared_amt = 0.0
            reason = " | ".join(reasons)

        _logger.warning("""[TDS_DEBUG_TRACE][SECTION_TRACE]
section=80U
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

        cert_type_str = "Permanent" if cert_type == 'permanent' else "Temporary"
        cert_num_str = str(cert_number) if cert_number else 'N/A'
        issue_date_str = c_issue.strftime('%d-%b-%Y') if hasattr(c_issue, 'strftime') and c_issue else (str(c_issue) if c_issue else 'N/A')
        r_issue_str = r_issue.strftime('%d-%b-%Y') if hasattr(r_issue, 'strftime') and r_issue else (str(r_issue) if r_issue else 'N/A')
        r_expiry_str = r_expiry.strftime('%d-%b-%Y') if hasattr(r_expiry, 'strftime') and r_expiry else (str(r_expiry) if r_expiry else 'N/A')
        fy_start_str = fy_start.strftime('%d-%b-%Y') if hasattr(fy_start, 'strftime') and fy_start else str(fy_start)
        fy_end_str = fy_end.strftime('%d-%b-%Y') if hasattr(fy_end, 'strftime') and fy_end else str(fy_end)
        authority_str = str(issuing_authority) if issuing_authority else 'N/A'

        if not is_eligible:
            ded_type_str = "Ineligible"
            final_class_str = "Ineligible"
            max_allowable_str = "INR 0"
        else:
            if is_severe:
                ded_type_str = "Severe Disability (80% or more)"
                final_class_str = "Severe"
                max_allowable_str = f"INR {severe_deduction:,.0f}"
            else:
                ded_type_str = "Normal Disability (40% to 79%)"
                final_class_str = "Normal"
                max_allowable_str = f"INR {normal_deduction:,.0f}"

        # 3. Generate Multi-Line Detailed Audit Log Trace
        trace_log = f"""
=========================================================
SECTION 80U STATUTORY AUDIT TRACE
=========================================================

Employee                    : {emp_name}
Employee ID                 : {emp_id}
Financial Year              : {fy_name} (Period: {fy_start_str} to {fy_end_str})
Declaration ID              : {decl_id}

---------------------------------------------------------
CERTIFICATE & TIMELINE DETAILS
---------------------------------------------------------

Certificate Type            : {cert_type_str}
Certificate Start Date      : {issue_date_str}
Old Certificate Expiry Date : {expiry_str}
Renewal / Reassessment Date : {r_issue_str}
New Certificate Expiry Date : {r_expiry_str}
FY Coverage Overlap Status  : {overlap_status}
Renewal / Reassessment Status: {reassessment_status_str}
Previous Certificate Info   : {prev_cert_info}
Current Certificate Info    : {curr_cert_info}

---------------------------------------------------------
DISABILITY & ELIGIBILITY DETAILS
---------------------------------------------------------

Old Certificate Percentage  : {disability_percent:.0f}%
Renewed Percentage          : {renewal_disability_percent:.0f}%
Effective Certificate       : {effective_cert_str}
Active Disability Percentage: {active_disability_pct:.2f}%
Disability Classification   : {ded_type_str}
Final Classification        : {final_class_str}
Income Tax Resident Status  : {resident_status_str}
Tax Regime                  : {"Old" if cond_regime else "New"}
Final Eligibility           : {"YES" if is_eligible else "NO"}
Final Approved 80U Amount   : INR {allowed_deduction:,.0f}
Eligibility / Rejection Reason: {reason}
=========================================================
"""
        _logger.warning(trace_log)

        return Section80UTraceResult(
            is_eligible=is_eligible,
            allowed_deduction=allowed_deduction,
            remarks=reason,
            trace_log=trace_log,
            is_severe=is_severe
        )
