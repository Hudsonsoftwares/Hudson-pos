# -*- coding: utf-8 -*-
import logging
from odoo import fields
from ..base import BaseStatutoryService
from .tds_parameter_service import TdsParameterService
from .section_80eea_eligibility_service import Section80EEAEligibilityService

_logger = logging.getLogger(__name__)


class HomeLoanDeductionResult:
    """
    Data Transfer Object (DTO) holding housing loan deduction calculation details.
    """
    def __init__(self, section_24b_self_interest=0.0, section_80eea_interest=0.0, total_home_loan_deduction=0.0):
        self.section_24b_self_interest = section_24b_self_interest
        self.section_80eea_interest = section_80eea_interest
        self.total_home_loan_deduction = total_home_loan_deduction


class HomeLoanDeductionService(BaseStatutoryService):
    """
    Phase 5 Service: Home Loan Deduction Service.
    Evaluates housing loan deductions:
    1. Section 24(b) Self-Occupied Home Loan Interest (capped at ₹2,00,000 via TdsParameterService).
    2. Section 80EEA First-Time Home Buyer additional interest (capped at ₹1,50,000 after invoking Section80EEAEligibilityService).
    Strictly returns 0.0 under New Tax Regime (Section 115BAC prohibits 24(b) self-occupied and 80EEA).
    """

    def calculate_home_loan_deductions(self, employee, financial_year, regime_code, eval_date=None, **kwargs):
        """
        Calculates housing loan deductions.

        :param employee: hr.employee record
        :param financial_year: tds.financial.year record
        :param regime_code: str ('old' or 'new')
        :param eval_date: Date (optional)
        :return: HomeLoanDeductionResult
        """
        regime_code = (regime_code or 'new').lower()

        if regime_code == 'new':
            return HomeLoanDeductionResult()

        tds_param_svc = TdsParameterService(self.env)

        # 1. Section 24(b) Self-Occupied Interest from declaration
        decl = self.env['tds.employee.declaration'].sudo().search([
            ('employee_id', '=', employee.id),
            ('financial_year_id', '=', financial_year.id)
        ], limit=1)

        home_loans = self.env['tds.employee.home.loan'].sudo().search([
            ('employee_id', '=', employee.id),
            ('financial_year_id', '=', financial_year.id)
        ])

        sec_24b_amt = 0.0
        total_home_loan_interest = 0.0
        source_type = 'HEADER_DECLARATION'
        decl_state = 'draft'
        is_post_proof = False
        declared_24b = 0.0
        approved_24b = 0.0

        loan_purpose = 'purchase'
        borrowing_date = None
        completion_date = None

        if decl:
            decl_state = getattr(decl, 'state', 'draft')
            is_post_proof = decl_state in ('proof_verified', 'approved')
            loan_purpose = getattr(decl, 'decl_24b_loan_purpose', 'purchase') or 'purchase'
            borrowing_date = getattr(decl, 'decl_24b_borrowing_date', None)
            completion_date = getattr(decl, 'decl_24b_completion_date', None)

            line_24b = next((l for l in decl.declaration_line_ids if l.category == '24b' and getattr(l, 'active', True)), None)
            if line_24b:
                declared_24b = float(line_24b.declared_amount or 0.0)
                line_appr = float(getattr(line_24b, 'tax_firm_approved_amount', 0.0) or getattr(line_24b, 'approved_amount', 0.0) or 0.0)
                approved_24b = line_appr
                total_home_loan_interest = declared_24b or float(getattr(decl, 'decl_24b_self_interest', 0.0) or 0.0)
                sec_24b_amt = line_appr if (is_post_proof and line_appr > 0.0) else (declared_24b or line_24b.usable_amount)
                source_type = 'DECLARATION_LINE'
            elif is_post_proof and (getattr(decl, 'decl_24b_approved_amount', 0.0) or 0.0) > 0:
                declared_24b = float(decl.decl_24b_self_interest or 0.0)
                approved_24b = float(decl.decl_24b_approved_amount or 0.0)
                total_home_loan_interest = declared_24b
                sec_24b_amt = approved_24b
                source_type = 'HEADER_DECLARATION'
            elif decl.decl_24b_self_interest > 0:
                declared_24b = float(decl.decl_24b_self_interest or 0.0)
                total_home_loan_interest = declared_24b
                sec_24b_amt = declared_24b
                source_type = 'HEADER_DECLARATION'
            else:
                for line in decl.declaration_line_ids:
                    if line.category == '24b' and line.is_regime_permitted:
                        declared_24b += float(line.declared_amount or 0.0)
                        line_appr = float(getattr(line, 'tax_firm_approved_amount', 0.0) or getattr(line, 'approved_amount', 0.0) or 0.0)
                        approved_24b += line_appr
                        sec_24b_amt += line_appr if (is_post_proof and line_appr > 0.0) else float(line.declared_amount or line.usable_amount or 0.0)
                        source_type = 'DECLARATION_LINE'
                total_home_loan_interest = declared_24b

        if home_loans:
            if not total_home_loan_interest:
                total_home_loan_interest = float(home_loans.claimed_interest_amount or 0.0)
            if not sec_24b_amt and not decl:
                sec_24b_amt = float(home_loans.claimed_interest_amount or 0.0)
            if not borrowing_date:
                borrowing_date = getattr(home_loans, 'borrowing_date', None)
            if not completion_date:
                completion_date = home_loans.completion_date
            if loan_purpose == 'purchase' and getattr(home_loans, 'loan_purpose', None):
                loan_purpose = home_loans.loan_purpose

        # Section 24(b) Statutory Parameters & Caps
        completion_period_years = tds_param_svc.get_24b_completion_period_years(eval_date=eval_date)
        borrowing_start_threshold = tds_param_svc.get_24b_borrowing_start_date(eval_date=eval_date)
        REPAIR_RENOVATION_LIMIT = tds_param_svc.get_24b_repair_renovation_limit(eval_date=eval_date)
        PURCHASE_CONSTRUCTION_LIMIT = tds_param_svc.get_home_loan_interest_limit(eval_date=eval_date) or 200000.0

        borrowing_fy_name = "N/A"
        borrowing_fy_end_str = "N/A"
        deadline = None
        deadline_str = "N/A"
        completion_date_str = completion_date.strftime('%Y-%m-%d') if hasattr(completion_date, 'strftime') and completion_date else (str(completion_date) if completion_date else "N/A")
        borrowing_date_str = borrowing_date.strftime('%Y-%m-%d') if hasattr(borrowing_date, 'strftime') and borrowing_date else (str(borrowing_date) if borrowing_date else "N/A")

        if borrowing_date:
            b_year = borrowing_date.year
            b_month = borrowing_date.month
            fy_end_year = b_year + 1 if b_month >= 4 else b_year
            borrowing_fy_name = f"FY {fy_end_year-1}-{str(fy_end_year)[-2:]}"
            borrowing_fy_end_str = f"{fy_end_year}-03-31"
            deadline = fields.Date.from_string(f"{fy_end_year + completion_period_years}-03-31")
            deadline_str = deadline.strftime('%Y-%m-%d')

        if loan_purpose == 'repair_renovation':
            selected_cap = REPAIR_RENOVATION_LIMIT
            completion_check_result = "N/A (Repair / Renovation)"
            cap_reason = "Statutory limit restricted to ₹30,000 for repair, renovation, renewal or reconstruction under Section 24(b)."
        elif borrowing_date and borrowing_date < borrowing_start_threshold:
            selected_cap = REPAIR_RENOVATION_LIMIT
            completion_check_result = "FAIL (Borrowed prior to 01-Apr-1999)"
            cap_reason = f"Capital borrowed on {borrowing_date_str} is prior to statutory threshold (01-Apr-1999). Restricted to ₹30,000 ceiling under Section 24(b)."
        elif loan_purpose in ('purchase', 'construction'):
            if completion_date and deadline:
                if completion_date <= deadline:
                    selected_cap = PURCHASE_CONSTRUCTION_LIMIT
                    completion_check_result = "PASS"
                    cap_reason = f"Completed on {completion_date_str}, within statutory {completion_period_years}-year deadline ({deadline_str}) from end of borrowing FY ({borrowing_fy_name}). Full ₹2,00,000 limit allowed."
                else:
                    selected_cap = REPAIR_RENOVATION_LIMIT
                    completion_check_result = "FAIL"
                    cap_reason = f"Completed on {completion_date_str}, exceeding statutory {completion_period_years}-year deadline ({deadline_str}) from end of borrowing FY ({borrowing_fy_name}). Restricted to ₹30,000 cap under Section 24(b)."
            elif deadline and eval_date and eval_date > deadline:
                selected_cap = REPAIR_RENOVATION_LIMIT
                completion_check_result = "FAIL"
                cap_reason = f"Construction/Purchase not completed within {completion_period_years} years of loan borrowing FY ({borrowing_fy_name}, deadline: {deadline_str}). Restricted to ₹30,000 cap."
            else:
                selected_cap = PURCHASE_CONSTRUCTION_LIMIT
                completion_check_result = "PASS"
                cap_reason = "Purchase/Construction loan with valid completion status. Full ₹2,00,000 limit allowed."
        else:
            selected_cap = PURCHASE_CONSTRUCTION_LIMIT
            completion_check_result = "PASS"
            cap_reason = "Standard purchase/construction limit."

        # Apply system parameter limit if configured and lower
        configured_max = tds_param_svc.get_home_loan_interest_limit(eval_date=eval_date)
        if configured_max and configured_max < selected_cap:
            selected_cap = configured_max

        sec_24b_approved = min(sec_24b_amt, selected_cap)
        base_interest_for_residual = total_home_loan_interest if total_home_loan_interest > 0.0 else sec_24b_amt
        remaining_interest = max(base_interest_for_residual - sec_24b_approved, 0.0)

        _logger.warning("""[SECTION_24B_STATUTORY_AUDIT]
loan_purpose=%s
borrowing_date=%s
borrowing_fy=%s
completion_date=%s
five_year_deadline=%s
completion_check_result=%s
selected_cap=%s
interest_considered=%s
final_24b_deduction=%s
remaining_interest_for_80eea=%s
decision_reason=%s""",
            loan_purpose,
            borrowing_date_str,
            borrowing_fy_name,
            completion_date_str,
            deadline_str,
            completion_check_result,
            f"INR {selected_cap:,.2f}",
            f"INR {sec_24b_amt:,.2f}",
            f"INR {sec_24b_approved:,.2f}",
            f"INR {remaining_interest:,.2f}",
            cap_reason
        )

        _logger.warning("""[TDS_DEBUG_TRACE][SECTION_TRACE]
section=24B
declaration_state=%s
declared_amount=%s
approved_amount=%s
eligible_amount=%s
usable_amount=%s
selected_amount=%s
final_chapter6a_amount=%s
source_type=%s""",
            decl_state, declared_24b, approved_24b, sec_24b_approved, sec_24b_approved, sec_24b_approved, sec_24b_approved, source_type
        )

        # 2. Section 80EEA Eligibility Service Invocation (Applied ON RESIDUAL INTEREST ONLY)
        sec_80eea_approved = 0.0
        eea_svc = Section80EEAEligibilityService(self.env)
        eea_res = None

        has_decl_80eea_claim = False
        eea_decl_amt = 0.0
        eea_appr_amt = 0.0
        if decl:
            line_80eea = next((l for l in getattr(decl, 'declaration_line_ids', []) if l.category == '80eea' and getattr(l, 'active', True)), None)
            if line_80eea:
                eea_decl_amt = float(line_80eea.declared_amount or 0.0)
                eea_appr_amt = float(getattr(line_80eea, 'tax_firm_approved_amount', 0.0) or getattr(line_80eea, 'approved_amount', 0.0) or 0.0)
            else:
                eea_decl_amt = float(getattr(decl, 'decl_80eea_interest_amount', 0.0) or 0.0)
                eea_appr_amt = float(getattr(decl, 'decl_80eea_approved_amount', 0.0) or 0.0)
            has_decl_80eea_claim = (eea_decl_amt > 0.0 or eea_appr_amt > 0.0 or bool(getattr(decl, 'decl_80eea_loan_sanction_date', False)))

        eea_claimed_amount = eea_appr_amt if (is_post_proof and eea_appr_amt > 0.0) else eea_decl_amt
        eea_interest_to_check = 0.0

        if has_decl_80eea_claim:
            if base_interest_for_residual > 0.0:
                eea_interest_to_check = min(eea_claimed_amount, remaining_interest) if eea_claimed_amount > 0.0 else remaining_interest
            else:
                eea_interest_to_check = eea_claimed_amount
            eea_res = eea_svc.validate_eligibility(
                decl,
                eval_date=eval_date,
                regime_code=regime_code,
                employee=employee,
                financial_year=financial_year,
                claimed_interest_amount=eea_interest_to_check
            )
            sec_80eea_approved = eea_res.allowed_deduction
        else:
            home_loans = self.env['tds.employee.home.loan'].search([
                ('employee_id', '=', employee.id),
                ('financial_year_id', '=', financial_year.id),
                ('claimed_interest_amount', '>', 0)
            ], limit=1)
            if home_loans:
                hl_claimed = float(home_loans.claimed_interest_amount or 0.0)
                if base_interest_for_residual > 0.0:
                    eea_interest_to_check = min(remaining_interest, hl_claimed) if hl_claimed > 0.0 else remaining_interest
                else:
                    eea_interest_to_check = hl_claimed
                eea_res = eea_svc.validate_eligibility(
                    home_loans,
                    eval_date=eval_date,
                    regime_code=regime_code,
                    employee=employee,
                    financial_year=financial_year,
                    claimed_interest_amount=eea_interest_to_check
                )
                sec_80eea_approved = eea_res.allowed_deduction

        total_home_loan = sec_24b_approved + sec_80eea_approved

        sec80eea_is_eligible = eea_res.is_eligible if eea_res else False
        eea_reason = eea_res.remarks if eea_res else ("Section 80EEA not claimed." if not has_decl_80eea_claim else "Section 80EEA not evaluated.")

        # Dedicated SECTION 24(b) STATUTORY TRACE
        emp_name = employee.name if employee else 'N/A'
        emp_id = employee.id if employee else 'N/A'
        decl_id = decl.id if decl else (home_loans.id if home_loans else 'N/A')
        fy_name = financial_year.name if financial_year else 'N/A'
        eval_date_str = eval_date.strftime('%Y-%m-%d') if hasattr(eval_date, 'strftime') and eval_date else (str(eval_date) if eval_date else fields.Date.today().strftime('%Y-%m-%d'))
        calc_run_id = kwargs.get('calculation_run_id') or kwargs.get('run_id') or getattr(decl, 'run_id', 'N/A') or 'N/A'
        payslip_id = kwargs.get('payslip_id') or (kwargs.get('payslip').id if kwargs.get('payslip') else 'N/A')

        purpose_cap_val = REPAIR_RENOVATION_LIMIT if loan_purpose == 'repair_renovation' else PURCHASE_CONSTRUCTION_LIMIT
        rejected_24b_amt = max(sec_24b_amt - sec_24b_approved, 0.0)

        five_year_applicable = "YES" if (loan_purpose in ('purchase', 'construction') and borrowing_date) else ("NO (Repair/Renovation)" if loan_purpose == 'repair_renovation' else "NO")
        comp_status = "COMPLETED" if completion_date else "PENDING / FUTURE"
        if completion_date and deadline:
            comp_within_5yr = "YES" if completion_date <= deadline else "NO"
        elif deadline:
            comp_within_5yr = "PENDING (Within allowed window)"
        else:
            comp_within_5yr = "N/A"

        trace_24b_log = f"""
=========================================================
[SECTION_24B_STATUTORY_TRACE]
=========================================================
employee                            : {emp_name}
employee_id                         : {emp_id}
declaration_id                      : {decl_id}
financial_year                      : {fy_name}
evaluation_date                     : {eval_date_str}
calculation_run_id                  : {calc_run_id}
payslip_id                          : {payslip_id}


---------------- INPUT ----------------
tax_regime                          : {regime_code.upper()}
property_occupation_status          : Self-Occupied
loan_purpose                        : {loan_purpose}
capital_borrowing_date              : {borrowing_date_str}
borrowing_financial_year            : {borrowing_fy_name}
borrowing_fy_end                    : {borrowing_fy_end_str}
five_year_deadline                  : {deadline_str}
completion_date                     : {completion_date_str}


---------------- INTEREST ----------------
declared_interest                   : INR {declared_24b:,.2f}
eligible_interest                   : INR {sec_24b_amt:,.2f}
approved_interest                   : INR {approved_24b:,.2f}
usable_interest                     : INR {sec_24b_amt:,.2f}
source_type                         : {source_type}


---------------- 5-YEAR RULE ----------------
five_year_rule_applicable           : {five_year_applicable}
completion_status                   : {comp_status}
completion_within_5_years           : {comp_within_5yr}
five_year_rule_result               : {completion_check_result}


---------------- CAP RESOLUTION ----------------
statutory_cap_before_rule           : INR {PURCHASE_CONSTRUCTION_LIMIT:,.2f}
purpose_based_cap                   : INR {purpose_cap_val:,.2f}
completion_based_cap                : INR {selected_cap:,.2f}
final_applicable_cap                : INR {selected_cap:,.2f}
cap_reason                          : {cap_reason}


---------------- FINAL 24(b) ----------------
interest_considered                 : INR {sec_24b_amt:,.2f}
section_24b_allowed                 : INR {sec_24b_approved:,.2f}
section_24b_rejected_amount         : INR {rejected_24b_amt:,.2f}
section_24b_final_deduction         : INR {sec_24b_approved:,.2f}


---------------- DOWNSTREAM ----------------
section_24b_passed_to_taxable_income: INR {sec_24b_approved:,.2f}
section_80eea_amount                : INR {sec_80eea_approved:,.2f}
remaining_interest_for_80eea        : INR {remaining_interest:,.2f}


=========================================================
"""
        _logger.warning(trace_24b_log)

        # Dedicated SECTION 80EEA CALCULATION FLOW TRACE
        eea_line = next((l for l in getattr(decl, 'declaration_line_ids', []) if l.category == '80eea'), None) if decl else None
        eea_verified_amt = float(getattr(eea_line, 'verified_amount', 0.0) or 0.0) if eea_line else 0.0
        eea_approved_amt = float(getattr(eea_line, 'tax_firm_approved_amount', 0.0) or getattr(eea_line, 'approved_amount', 0.0) or 0.0) if eea_line else (float(getattr(decl, 'decl_80eea_approved_amount', 0.0) or 0.0) if decl else 0.0)
        eea_sanction_date = decl.decl_80eea_loan_sanction_date if decl and decl.decl_80eea_loan_sanction_date else (home_loans.loan_sanction_date if home_loans else False)
        eea_stamp_val = float(decl.decl_80eea_property_stamp_value or 0.0) if decl and decl.decl_80eea_property_stamp_value else (float(home_loans.property_stamp_value or 0.0) if home_loans else 0.0)
        eea_first_buyer = bool(decl.decl_80eea_first_time_home_buyer) if decl and hasattr(decl, 'decl_80eea_first_time_home_buyer') else (bool(home_loans.is_first_time_home_buyer) if home_loans else False)
        eea_claimed_80ee = bool(decl.decl_80eea_claimed_under_80ee) if decl and hasattr(decl, 'decl_80eea_claimed_under_80ee') else (bool(home_loans.claimed_under_80ee) if home_loans else False)
        eea_lender_type = (decl.decl_80eea_lender_type or 'scheduled_bank') if decl else (home_loans.lender_type or 'scheduled_bank' if home_loans else 'scheduled_bank')
        eea_lending_inst = (decl.decl_80eea_lending_institution or 'N/A') if decl else (getattr(home_loans, 'lending_institution', 'N/A') or 'N/A' if home_loans else 'N/A')
        eea_loan_acct = (decl.decl_80eea_loan_account_number or 'N/A') if decl else (getattr(home_loans, 'loan_account_number', 'N/A') or 'N/A' if home_loans else 'N/A')
        eea_sanction_date_str = eea_sanction_date.strftime('%Y-%m-%d') if hasattr(eea_sanction_date, 'strftime') and eea_sanction_date else (str(eea_sanction_date) if eea_sanction_date else 'N/A')

        eea_s_date_obj = fields.Date.from_string(str(eea_sanction_date)) if eea_sanction_date else None
        eea_cond_date_window = bool(eea_s_date_obj and fields.Date.from_string("2019-04-01") <= eea_s_date_obj <= fields.Date.from_string("2022-03-31"))
        eea_cond_stamp = bool(eea_stamp_val > 0.0 and eea_stamp_val <= 4500000.0)
        eea_cond_lender = bool(eea_lender_type in ('scheduled_bank', 'housing_finance_company', 'nbfc'))

        trace_80eea_flow_log = f"""
=========================================================
[SECTION_80EEA_CALCULATION_FLOW_TRACE]
=========================================================
Source: HomeLoanDeductionService.calculate_home_loan_deductions() -> Section80EEAEligibilityService.validate_eligibility()

---------------- 1. DECLARATION INPUT ----------------
employee_id                         : {emp_id}
employee_name                       : {emp_name}
declaration_id                      : {decl_id}
financial_year                      : {fy_name}
declaration_state                   : {decl_state}
explicit_80eea_claim                : {"YES" if has_decl_80eea_claim else "NO"}
declared_80eea_amount               : INR {eea_decl_amt:,.2f}
loan_sanction_date                  : {eea_sanction_date_str}
property_stamp_value                : INR {eea_stamp_val:,.2f}
first_time_home_buyer               : {"YES" if eea_first_buyer else "NO"}
claimed_under_80ee                  : {"YES" if eea_claimed_80ee else "NO"}
lender_type                         : {eea_lender_type}
lending_institution                 : {eea_lending_inst}
loan_account_number                 : {eea_loan_acct}


---------------- 2. HOME LOAN / 24(b) ----------------
original_home_loan_interest_declared: INR {total_home_loan_interest:,.2f}
section_24b_eligible_amount         : INR {sec_24b_amt:,.2f}
section_24b_allowed_amount          : INR {sec_24b_approved:,.2f}
exact_amount_deducted_under_24b     : INR {sec_24b_approved:,.2f}


---------------- 3. 80EEA RESIDUAL CALCULATION ----------------
Formula                             : residual_interest = original_home_loan_interest - allowed_24b_interest
original_interest                   : INR {total_home_loan_interest:,.2f}
allowed_24b                         : INR {sec_24b_approved:,.2f}
residual_interest                   : INR {remaining_interest:,.2f}
declared_80eea_amount               : INR {eea_decl_amt:,.2f}
eligible_base_used                  : INR {eea_interest_to_check:,.2f} ({'Residual interest after Section 24(b)' if remaining_interest > 0.0 else 'Declared 80EEA Amount'})


---------------- 4. 80EEA STATUTORY ELIGIBILITY ----------------
Tax Regime (Old Regime)             : {"PASS (OLD)" if (regime_code == 'old') else "FAIL (NEW - Not permitted under New Tax Regime Section 202(1))"}
First-Time Home Buyer Condition     : {"PASS" if eea_first_buyer else "FAIL (Assessee is not a first-time buyer)"}
Loan Sanction Date                  : {eea_sanction_date_str}
Sanction-Date Window (2019-2022)    : {"PASS (Between 01-Apr-2019 and 31-Mar-2022)" if eea_cond_date_window else "FAIL (Outside statutory window)"}
Property Stamp Duty Value (<= 45L)  : {"PASS (INR " + f"{eea_stamp_val:,.2f} <= INR 4,500,000.00)" if eea_cond_stamp else "FAIL (Exceeds INR 4,500,000.00)"}
Lender Institution Condition        : {"PASS (Approved Financial Institution/Bank)" if eea_cond_lender else "FAIL"}
Section 80EE Exclusivity            : {"PASS (No Section 80EE claimed)" if not eea_claimed_80ee else "FAIL (Already claimed u/s 80EE)"}
Final Eligibility Result            : {"PASS (ELIGIBLE)" if sec80eea_is_eligible else "FAIL (INELIGIBLE)"}
Rejection Reason                    : {eea_reason if not sec80eea_is_eligible else "None (Conditions Met)"}


---------------- 5. 80EEA AMOUNT LIFECYCLE ----------------
declared_amount                     : INR {eea_decl_amt:,.2f}
projected_amount                    : INR {eea_decl_amt:,.2f}
residual_eligible_amount            : INR {remaining_interest:,.2f}
statutory_80eea_cap                 : INR 150,000.00
capped_eligible_amount              : INR {sec_80eea_approved:,.2f}
verified_amount                     : INR {eea_verified_amt:,.2f}
hr_approved_amount                  : INR {eea_approved_amt:,.2f}
usable_amount                       : INR {sec_80eea_approved:,.2f}
final_selected_amount               : INR {sec_80eea_approved:,.2f}
final_Chapter_VIA_amount            : INR {sec_80eea_approved:,.2f}

---------------- CALCULATION SEQUENCE ----------------
Sequence: Total Interest (INR {total_home_loan_interest:,.2f}) → 24(b) (INR {sec_24b_approved:,.2f}) → Residual Interest (INR {remaining_interest:,.2f}) → 80EEA Cap (INR 150,000.00) → Final 80EEA (INR {sec_80eea_approved:,.2f})

=========================================================

[80EEA_END_TO_END_TRACE]
explicit_80eea_claim = {"YES" if has_decl_80eea_claim else "NO"}
sanction_date = {eea_sanction_date_str}
first_time_buyer = {"YES" if eea_first_buyer else "NO"}
property_value = INR {eea_stamp_val:,.2f}
lender_type = {eea_lender_type}
section_24b_original_interest = INR {total_home_loan_interest:,.2f}
section_24b_final_amount = INR {sec_24b_approved:,.2f}
section_80eea_residual_interest = INR {remaining_interest:,.2f}
section_80eea_declared_amount = INR {eea_decl_amt:,.2f}
section_80eea_statutory_cap = INR 150,000.00
eligible_amount = INR {eea_interest_to_check:,.2f}
approved_amount = INR {sec_80eea_approved:,.2f}
final_80eea_amount = INR {sec_80eea_approved:,.2f}
final_chapter6a_amount = INR {sec_80eea_approved:,.2f}
calculation_sequence = Total Interest (INR {total_home_loan_interest:,.2f}) → 24(b) (INR {sec_24b_approved:,.2f}) → Residual Interest (INR {remaining_interest:,.2f}) → 80EEA Cap (INR 150,000.00) → Final 80EEA (INR {sec_80eea_approved:,.2f})
=========================================================
"""
        _logger.warning(trace_80eea_flow_log)

        _logger.warning("""[TDS_DEBUG_TRACE][80EEA_CALCULATION_AUDIT]
TOTAL_INTEREST=%s
FINAL_24B_AMOUNT=%s
RESIDUAL_INTEREST_FOR_80EEA=%s
80EEA_DECLARED_AMOUNT=%s
80EEA_STATUTORY_CAP=150000.00
80EEA_ELIGIBILITY_RESULT=%s
FINAL_80EEA_AMOUNT=%s
FINAL_CHAPTER_VIA_80EEA=%s""",
            f"INR {total_home_loan_interest:,.2f}",
            f"INR {sec_24b_approved:,.2f}",
            f"INR {remaining_interest:,.2f}",
            f"INR {eea_decl_amt:,.2f}",
            "ELIGIBLE" if sec80eea_is_eligible else "INELIGIBLE",
            f"INR {sec_80eea_approved:,.2f}",
            f"INR {sec_80eea_approved:,.2f}"
        )

        trace_log = f"""
===========================================================
HOME LOAN DEDUCTION SUMMARY
===========================================================

Declared Home Loan Interest    : INR {sec_24b_amt:,.2f}
Section 24(b) Allowed          : INR {sec_24b_approved:,.2f}
Remaining Interest after 24(b) : INR {remaining_interest:,.2f}
Section 80EEA Eligible         : {"YES" if sec80eea_is_eligible else "NO"}
Section 80EEA Allowed          : INR {sec_80eea_approved:,.2f}

-----------------------------------------------------------
TOTAL HOME LOAN DEDUCTION
-----------------------------------------------------------

Section 24(b) Allowed          : INR {sec_24b_approved:,.2f}
Section 80EEA Allowed          : INR {sec_80eea_approved:,.2f}
Total Home Loan Deduction      : INR {total_home_loan:,.2f}

Reason

{eea_reason}

===========================================================
"""
        _logger.warning(trace_log)

        return HomeLoanDeductionResult(
            section_24b_self_interest=sec_24b_approved,
            section_80eea_interest=sec_80eea_approved,
            total_home_loan_deduction=total_home_loan
        )
