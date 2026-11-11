# -*- coding: utf-8 -*-
import logging
from odoo import fields
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class Section80ETraceResult:
    """
    Data Transfer Object (DTO) holding Section 80E statutory trace & deduction details.
    """
    def __init__(self, is_eligible=False, allowed_deduction=0.0, remarks="", trace_log="", current_claim_year=1, is_within_8_years=True, declared_amount=0.0, approved_amount=0.0, eligible_amount=0.0, selected_source='HEADER_DECLARATION', selected_amount=0.0):
        self.is_eligible = is_eligible
        self.allowed_deduction = allowed_deduction
        self.remarks = remarks
        self.trace_log = trace_log
        self.current_claim_year = current_claim_year
        self.is_within_8_years = is_within_8_years
        self.declared_amount = declared_amount
        self.approved_amount = approved_amount
        self.eligible_amount = eligible_amount
        self.selected_source = selected_source
        self.selected_amount = selected_amount


class Section80EDeductionService(BaseStatutoryService):
    """
    Phase 5 Service: Section 80E Statutory Trace & Eligibility Service.
    Generates detailed statutory audit traces for Section 80E Education Loan Interest Deductions.
    Single Source of Truth for Section 80E statutory calculations.
    """

    def validate_and_trace(self, declaration_or_dict, eval_date=None, regime_code='old', employee=None, financial_year=None, **kwargs):
        """
        Evaluates Section 80E statutory eligibility and produces standard ASCII statutory trace log.
        """
        regime = (regime_code or 'old').lower()

        decl_state = 'draft'
        is_post_proof = False
        source_type = 'HEADER_DECLARATION'
        declared_amt = 0.0
        approved_amt_found = 0.0
        header_amount = 0.0
        proof_line_found = False
        proof_line_id = 'N/A'
        proof_status = 'N/A'
        proof_approved_amount = 0.0
        proof_declared_amount = 0.0
        selected_source = 'HEADER_DECLARATION'
        selected_amount = 0.0
        interest_amt = 0.0
        line_80e = None

        if getattr(declaration_or_dict, '_name', '') == 'tds.employee.declaration.line':
            line = declaration_or_dict
            decl = line.declaration_id
            employee = employee or line.employee_id or (decl.employee_id if decl else None)
            financial_year = financial_year or line.financial_year_id or (decl.financial_year_id if decl else None)
            decl_id = decl.id if decl else 'N/A'
            decl_state = getattr(line, 'declaration_state', False) or (getattr(decl, 'state', 'draft') if decl else 'draft')
            regime = (getattr(line, 'regime_code', False) or (getattr(decl, 'regime_code', False) if decl else False) or regime).lower()
            is_post_proof = decl_state in ('proof_verified', 'approved')

            proof_line_found = True
            proof_line_id = line.id
            proof_status = line.validation_status or decl_state
            proof_approved_amount = float(getattr(line, 'tax_firm_approved_amount', 0.0) or getattr(line, 'approved_amount', 0.0) or getattr(line, 'verified_amount', 0.0) or 0.0)
            proof_declared_amount = float(line.declared_amount or 0.0)

            header_declared = float(getattr(decl, 'decl_80e_interest', 0.0) or 0.0) if decl else 0.0
            header_approved = float(getattr(decl, 'decl_80e_approved_amount', 0.0) or 0.0) if decl else 0.0
            header_amount = header_approved if (is_post_proof and header_approved > 0.0) else header_declared

            if (is_post_proof and proof_approved_amount > 0.0) or (not is_post_proof and proof_declared_amount > 0.0) or (header_amount == 0.0 and (proof_approved_amount > 0.0 or proof_declared_amount > 0.0)):
                selected_source = 'DECLARATION_LINE'
                selected_amount = proof_approved_amount if (is_post_proof and proof_approved_amount > 0.0) else proof_declared_amount
                declared_amt = proof_declared_amount
                approved_amt_found = proof_approved_amount
                interest_amt = selected_amount
            elif header_amount > 0.0:
                selected_source = 'HEADER_DECLARATION'
                selected_amount = header_amount
                declared_amt = header_declared
                approved_amt_found = header_approved
                interest_amt = selected_amount
            else:
                selected_source = 'DECLARATION_LINE'
                selected_amount = 0.0
                declared_amt = proof_declared_amount
                approved_amt_found = proof_approved_amount
                interest_amt = 0.0

            account_num = getattr(decl, 'decl_80e_loan_account_number', 'N/A') if decl else 'N/A'
            sanction_date = getattr(decl, 'decl_80e_loan_sanction_date', None) if decl else None
            interest_start_date = getattr(decl, 'decl_80e_interest_start_date', None) if decl else None
            lender_name = getattr(decl, 'decl_80e_lender_name', 'N/A') if decl else 'N/A'
            lender_type = getattr(decl, 'decl_80e_lender_type', 'scheduled_bank') if decl else 'scheduled_bank'
            is_higher_education = bool(getattr(decl, 'decl_80e_is_higher_education', True))
            loan_taken_for = getattr(decl, 'decl_80e_loan_taken_for', 'self') if decl else 'self'
            first_claim_fy = getattr(decl, 'decl_80e_first_claim_fy_id', False) if decl else False
            current_claim_year = int(getattr(decl, 'decl_80e_current_claim_year', 1) or 1) if decl else 1
            is_within_8_years = bool(getattr(decl, 'decl_80e_is_within_8_years', True))

        elif hasattr(declaration_or_dict, 'decl_80e_interest'):
            decl = declaration_or_dict
            employee = employee or decl.employee_id
            financial_year = financial_year or decl.financial_year_id
            decl_state = getattr(decl, 'state', 'draft')
            is_post_proof = decl_state in ('proof_verified', 'approved')

            header_declared = float(decl.decl_80e_interest or 0.0)
            header_approved = float(getattr(decl, 'decl_80e_approved_amount', 0.0) or 0.0)
            header_amount = header_approved if (is_post_proof and header_approved > 0.0) else header_declared

            lines_80e = decl.declaration_line_ids.filtered(lambda l: l.category == '80e' and getattr(l, 'active', True))
            if not lines_80e and decl.id:
                lines_80e = self.env['tds.employee.declaration.line'].sudo().search([
                    ('declaration_id', '=', decl.id),
                    ('category', '=', '80e')
                ])

            approved_line = next((l for l in lines_80e if (float(getattr(l, 'tax_firm_approved_amount', 0.0) or getattr(l, 'approved_amount', 0.0) or getattr(l, 'verified_amount', 0.0) or 0.0) > 0.0)), None)
            target_line = approved_line or (lines_80e[0] if lines_80e else None)

            if target_line:
                proof_line_found = True
                proof_line_id = target_line.id
                proof_status = target_line.validation_status or decl_state
                proof_approved_amount = float(getattr(target_line, 'tax_firm_approved_amount', 0.0) or getattr(target_line, 'approved_amount', 0.0) or getattr(target_line, 'verified_amount', 0.0) or 0.0)
                proof_declared_amount = float(target_line.declared_amount or 0.0)

            if proof_line_found and is_post_proof and proof_approved_amount > 0.0:
                selected_source = 'DECLARATION_LINE'
                selected_amount = proof_approved_amount
                declared_amt = proof_declared_amount
                approved_amt_found = proof_approved_amount
                interest_amt = proof_approved_amount
            elif is_post_proof and header_approved > 0.0:
                selected_source = 'HEADER_DECLARATION'
                selected_amount = header_approved
                declared_amt = header_declared
                approved_amt_found = header_approved
                interest_amt = header_approved
            elif proof_line_found and not is_post_proof and proof_declared_amount > 0.0:
                selected_source = 'DECLARATION_LINE'
                selected_amount = proof_declared_amount
                declared_amt = proof_declared_amount
                approved_amt_found = proof_approved_amount
                interest_amt = proof_declared_amount
            elif header_declared > 0.0:
                selected_source = 'HEADER_DECLARATION'
                selected_amount = header_amount
                declared_amt = header_declared
                approved_amt_found = header_approved
                interest_amt = header_amount
            elif proof_line_found:
                selected_source = 'DECLARATION_LINE'
                selected_amount = 0.0
                declared_amt = proof_declared_amount
                approved_amt_found = proof_approved_amount
                interest_amt = 0.0
            else:
                selected_source = 'HEADER_DECLARATION'
                selected_amount = 0.0
                declared_amt = header_declared
                approved_amt_found = header_approved
                interest_amt = 0.0

            account_num = decl.decl_80e_loan_account_number or 'N/A'
            sanction_date = decl.decl_80e_loan_sanction_date
            interest_start_date = getattr(decl, 'decl_80e_interest_start_date', None)
            lender_name = decl.decl_80e_lender_name or 'N/A'
            lender_type = decl.decl_80e_lender_type or 'scheduled_bank'
            is_higher_education = bool(decl.decl_80e_is_higher_education)
            loan_taken_for = decl.decl_80e_loan_taken_for or 'self'
            first_claim_fy = getattr(decl, 'decl_80e_first_claim_fy_id', False)
            current_claim_year = int(getattr(decl, 'decl_80e_current_claim_year', 1) or 1)
            is_within_8_years = bool(getattr(decl, 'decl_80e_is_within_8_years', True))
            decl_id = decl.id
        else:
            d = declaration_or_dict or {}
            decl = None
            decl_state = d.get('declaration_state', d.get('state', 'draft'))
            is_post_proof = decl_state in ('proof_verified', 'approved')

            header_amount = float(d.get('header_amount', d.get('decl_80e_interest', 0.0)))
            proof_appr = float(d.get('tax_firm_approved_amount', d.get('approved_amount', 0.0)))
            proof_decl = float(d.get('declared_amount', d.get('decl_80e_interest', 0.0)))
            proof_line_id = d.get('line_id', d.get('proof_line_id', 'N/A'))
            proof_status = d.get('validation_status', d.get('proof_status', decl_state))
            proof_line_found = d.get('proof_line_found', bool(d.get('source_type') == 'DECLARATION_LINE' or 'approved_amount' in d or 'tax_firm_approved_amount' in d or 'declared_amount' in d))

            proof_approved_amount = proof_appr
            proof_declared_amount = proof_decl

            explicit_source = d.get('source_type')
            if explicit_source:
                selected_source = explicit_source
                selected_amount = proof_appr if (is_post_proof and proof_appr > 0.0) else proof_decl if selected_source == 'DECLARATION_LINE' else header_amount
            elif proof_line_found and is_post_proof and proof_appr > 0.0:
                selected_source = 'DECLARATION_LINE'
                selected_amount = proof_appr
            elif is_post_proof and header_amount > 0.0:
                selected_source = 'HEADER_DECLARATION'
                selected_amount = header_amount
            elif proof_line_found and not is_post_proof and proof_decl > 0.0:
                selected_source = 'DECLARATION_LINE'
                selected_amount = proof_decl
            elif header_amount > 0.0:
                selected_source = 'HEADER_DECLARATION'
                selected_amount = header_amount
            elif proof_line_found:
                selected_source = 'DECLARATION_LINE'
                selected_amount = 0.0
            else:
                selected_source = 'HEADER_DECLARATION'
                selected_amount = 0.0

            declared_amt = proof_decl if selected_source == 'DECLARATION_LINE' else header_amount
            approved_amt_found = proof_appr if selected_source == 'DECLARATION_LINE' else header_amount
            interest_amt = selected_amount

            account_num = d.get('decl_80e_loan_account_number', 'N/A')
            sanction_date = d.get('decl_80e_loan_sanction_date')
            interest_start_date = d.get('decl_80e_interest_start_date')
            lender_name = d.get('decl_80e_lender_name', 'N/A')
            lender_type = d.get('decl_80e_lender_type', 'scheduled_bank')
            is_higher_education = bool(d.get('decl_80e_is_higher_education', True))
            loan_taken_for = d.get('decl_80e_loan_taken_for', 'self')
            first_claim_fy = d.get('decl_80e_first_claim_fy_id')
            current_claim_year = int(d.get('decl_80e_current_claim_year', 1) or 1)
            is_within_8_years = bool(d.get('decl_80e_is_within_8_years', True))
            decl_id = d.get('declaration_id', 'N/A')

        _logger.warning("""
=========================================================
80E_SOURCE_SELECTION
header_amount=%s
proof_line_found=%s
proof_line_id=%s
proof_status=%s
proof_approved_amount=%s
selected_source=%s
selected_amount=%s
=========================================================""",
            header_amount, proof_line_found, proof_line_id, proof_status,
            proof_approved_amount, selected_source, selected_amount
        )

        emp_name = employee.name if employee else kwargs.get('employee_name', 'N/A')
        emp_id = employee.id if employee else kwargs.get('employee_id', 'N/A')
        fy_name = financial_year.name if financial_year else 'N/A'

        # Calculate claim year count if first_claim_fy or interest_start_date provided
        if (first_claim_fy or interest_start_date) and financial_year:
            first_start = False
            if interest_start_date:
                try:
                    s_d = fields.Date.from_string(interest_start_date) if isinstance(interest_start_date, str) else interest_start_date
                    s_yr = s_d.year if s_d.month >= 4 else s_d.year - 1
                    first_start = fields.Date.from_string(f"{s_yr}-04-01")
                except Exception:
                    pass
            elif first_claim_fy:
                first_start = getattr(first_claim_fy, 'start_date', False) or getattr(first_claim_fy, 'date_from', False)

            curr_start = getattr(financial_year, 'start_date', False) or getattr(financial_year, 'date_from', False)
            if first_start and curr_start:
                try:
                    f_year = first_start.year if hasattr(first_start, 'year') else int(str(first_start)[:4])
                    c_year = curr_start.year if hasattr(curr_start, 'year') else int(str(curr_start)[:4])
                    current_claim_year = max(1, (c_year - f_year) + 1)
                except Exception:
                    pass

        # 2. Map Category & Mode Labels
        lender_type_map = {
            'scheduled_bank': 'Scheduled Bank',
            'financial_institution': 'Financial Institution',
            'approved_charitable': 'Approved Charitable Institution',
            'private_individual': 'Private Individual',
            'employer': 'Employer',
            'friend_relative': 'Friend / Relative',
            'cooperative_society': 'Cooperative Society (Non-approved)',
            'foreign_individual': 'Foreign Individual',
            'money_lender': 'Money Lender',
            'unregistered_nbfc': 'Unregistered NBFC',
            'other': 'Other (Non-Eligible)',
        }
        taken_for_map = {
            'self': 'Self',
            'spouse': 'Spouse',
            'child': 'Child',
            'legal_guardian': 'Student for whom employee is legal guardian',
        }

        lender_type_str = lender_type_map.get(lender_type, str(lender_type).title() if lender_type else 'Scheduled Bank')
        taken_for_str = taken_for_map.get(loan_taken_for, 'Self')

        # Resolve statutory rule parameters
        from .tds_parameter_service import TdsParameterService
        tds_param_svc = TdsParameterService(self.env)
        max_deduction_years = tds_param_svc.get_80e_max_years(eval_date=eval_date)
        allowed_lender_types = tds_param_svc.get_80e_allowed_lenders(eval_date=eval_date)

        # 3. Statutory Eligibility Checks (Proof approval must not bypass expired window or statutory ineligibility)
        cond_regime = (regime == 'old')
        cond_interest = (interest_amt > 0.0)
        cond_higher_edu = is_higher_education
        cond_lender = bool(lender_type and lender_type.upper() in [x.upper() for x in allowed_lender_types])
        cond_window = bool(current_claim_year <= max_deduction_years)

        is_eligible = False
        allowed_deduction = 0.0
        reason = ""

        if not cond_regime:
            reason = "Section 80E Ineligible: Education Loan Interest deduction is available only under the Old Tax Regime (not permitted under New Tax Regime Income-tax Act, 2025 — Section 202(1))."
        elif not cond_interest:
            reason = "No Section 80E deduction allowable: Declared education loan interest amount is zero."
        elif not cond_higher_edu:
            reason = "Section 80E Ineligible: Education loan was not taken for higher education as statutorily required under Section 80E."
        elif not cond_lender:
            reason = "Section 80E Ineligible: Loan is not obtained from a Scheduled Bank, Financial Institution, or Approved Charitable Institution as required under Section 80E."
        elif not cond_window:
            reason = f"Section 80E Ineligible: Maximum deduction period of {max_deduction_years} assessment years permitted under Section 80E has expired (Current Claim Year: {current_claim_year})."
        else:
            is_eligible = True
            allowed_deduction = interest_amt
            if is_post_proof and approved_amt_found > 0.0:
                reason = f"Verified education loan interest proof approved by HR/Tax Firm. Allowed deduction of INR {allowed_deduction:,.2f} under Section 80E."
            else:
                reason = f"Full declared interest of INR {interest_amt:,.2f} is allowable as deduction under Section 80E without any statutory ceiling."

        if not is_eligible:
            eligible_interest_considered = 0.0
            allowed_deduction = 0.0
        else:
            eligible_interest_considered = interest_amt

        _logger.warning("""[TDS_DEBUG_TRACE][SECTION_TRACE]
section=80E
declaration_state=%s
declared_amount=%s
approved_amount=%s
eligible_amount=%s
usable_amount=%s
selected_amount=%s
final_chapter6a_amount=%s
source_type=%s""",
            decl_state, declared_amt, approved_amt_found, eligible_interest_considered, allowed_deduction, allowed_deduction, allowed_deduction, selected_source
        )
        _logger.warning("80E_FINAL_CHAPTER6A_AMOUNT=%s", allowed_deduction)
        _logger.warning("80E_SELECTED_AMOUNT=%s", allowed_deduction)
        _logger.warning("80E_INCLUDED_IN_CHAPTER6A=%s", allowed_deduction)

        _logger.warning("""[80E_AUDIT] SECTION_80E
declared_80e=%s
approved_80e=%s
eligible_80e=%s
allowed_80e=%s
final_80e_deduction=%s""",
            declared_amt, approved_amt_found, allowed_deduction, allowed_deduction, allowed_deduction
        )

        remarks = f"Section 80E Status: {'ELIGIBLE' if is_eligible else 'INELIGIBLE'}. {reason}"
        sanction_date_str = sanction_date.strftime('%d-%b-%Y') if hasattr(sanction_date, 'strftime') and sanction_date else (str(sanction_date) if sanction_date else 'N/A')
        interest_start_date_str = interest_start_date.strftime('%d-%b-%Y') if hasattr(interest_start_date, 'strftime') and interest_start_date else (str(interest_start_date) if interest_start_date else 'N/A')

        # Resolve AY strings
        def get_ay_string(fy_obj_or_record):
            if not fy_obj_or_record:
                return 'N/A'
            start_val = getattr(fy_obj_or_record, 'start_date', False) or getattr(fy_obj_or_record, 'date_from', False)
            name_val = getattr(fy_obj_or_record, 'name', '')
            if start_val:
                try:
                    yr = start_val.year if hasattr(start_val, 'year') else int(str(start_val)[:4])
                    return f"AY {yr + 1}-{str(yr + 2)[-2:]}"
                except Exception:
                    pass
            if name_val and 'AY' in str(name_val):
                return str(name_val)
            elif name_val and 'FY' in str(name_val):
                try:
                    parts = str(name_val).split(' ')[1].split('-')
                    y1 = int(parts[0])
                    return f"AY {y1 + 1}-{str(y1 + 2)[-2:]}"
                except Exception:
                    pass
            return str(name_val) if name_val else 'N/A'

        if interest_start_date:
            try:
                s_d = fields.Date.from_string(interest_start_date) if isinstance(interest_start_date, str) else interest_start_date
                s_yr = s_d.year if s_d.month >= 4 else s_d.year - 1
                first_ay_str = f"AY {s_yr + 1}-{str(s_yr + 2)[-2:]}"
            except Exception:
                first_ay_str = get_ay_string(first_claim_fy) if first_claim_fy else get_ay_string(financial_year)
        else:
            first_ay_str = get_ay_string(first_claim_fy) if first_claim_fy else get_ay_string(financial_year)
        curr_ay_str = get_ay_string(financial_year)

        _logger.warning("""[80E_WINDOW_AUDIT]
interest_start_date=%s
first_claim_fy=%s
current_fy=%s
current_claim_year=%s
max_deduction_years=%s
is_within_8_years=%s
allowed_deduction=%s""",
            interest_start_date, first_ay_str, curr_ay_str, current_claim_year,
            max_deduction_years, cond_window, allowed_deduction
        )

        # 4. Generate Multi-Line Statutory Trace Log
        trace_log = f"""
=========================================================
SECTION 80E STATUTORY TRACE
=========================================================

Employee                : {emp_name}
Employee ID             : {emp_id}
Financial Year          : {fy_name}
Declaration ID          : {decl_id}

---------------------------------------------------------
DECLARATION INPUTS
---------------------------------------------------------

Interest Paid           : INR {interest_amt:,.2f}
Loan Account Number     : {account_num}
Loan Sanction Date      : {sanction_date_str}
Interest Start Date     : {interest_start_date_str}
Lending Institution     : {lender_name}
Lending Institution Type: {lender_type_str}
Higher Education        : {"YES" if is_higher_education else "NO"}
Loan Taken For          : {taken_for_str}

---------------------------------------------------------
STATUTORY ELIGIBILITY CHECKS
---------------------------------------------------------

Tax Regime (Old Regime)
Result
{"PASS" if cond_regime else "FAIL"}

---------------------------------------------------------

Higher Education Purpose
Result
{"PASS" if cond_higher_edu else "FAIL"}

---------------------------------------------------------

Approved Lender Category
Lender Type
{lender_type_str}
Allowed Categories
Scheduled Bank, Financial Institution, Approved Charitable Institution
Result
{"PASS" if cond_lender else "FAIL"}

---------------------------------------------------------

Eight-Year Window

First Assessment Year of Claim
{first_ay_str}

Current Assessment Year
{curr_ay_str}

Current Claim Number
Year {current_claim_year} of {max_deduction_years}

Maximum Deduction Window
{max_deduction_years} Assessment Years

Result
{"PASS" if cond_window else "FAIL"}

---------------------------------------------------------
STATUTORY CALCULATION
---------------------------------------------------------

Declared Interest Amount
INR {interest_amt:,.2f}

Eligible Interest Amount
INR {eligible_interest_considered:,.2f}

Approved Section 80E Deduction
INR {allowed_deduction:,.2f}

---------------------------------------------------------
FINAL RESULT
---------------------------------------------------------

Eligible
{"YES" if is_eligible else "NO"}

Approved Deduction
INR {allowed_deduction:,.2f}

Reason

{reason}

=========================================================
"""

        _logger.warning(trace_log)

        return Section80ETraceResult(
            is_eligible=is_eligible,
            allowed_deduction=allowed_deduction,
            remarks=remarks,
            trace_log=trace_log,
            current_claim_year=current_claim_year,
            is_within_8_years=cond_window,
            declared_amount=declared_amt,
            approved_amount=approved_amt_found,
            eligible_amount=eligible_interest_considered,
            selected_source=selected_source,
            selected_amount=allowed_deduction
        )
