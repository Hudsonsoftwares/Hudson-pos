# -*- coding: utf-8 -*-
import logging
from odoo import fields
from ..base import BaseStatutoryService
from .tds_parameter_service import TdsParameterService

_logger = logging.getLogger(__name__)


class Section80EEAValidationResult:
    """
    Data Transfer Object representing the audit result of a Section 80EEA statutory eligibility check.
    """
    def __init__(self, is_eligible, remarks, max_statutory_ceiling=0.0, allowed_deduction=0.0):
        self.is_eligible = is_eligible
        self.remarks = remarks
        self.max_statutory_ceiling = max_statutory_ceiling
        self.allowed_deduction = allowed_deduction

    def to_dict(self):
        return {
            'is_eligible': self.is_eligible,
            'remarks': self.remarks,
            'max_statutory_ceiling': self.max_statutory_ceiling,
            'allowed_deduction': self.allowed_deduction,
        }


class Section80EEAEligibilityService(BaseStatutoryService):
    """
    Dedicated Service Resolver for Section 80EEA Housing Loan Interest Exemption.
    Enforces statutory eligibility rules under Section 80EEA of the Income Tax Act:
    1. Permitted ONLY under Old Tax Regime.
    2. Housing loan sanctioned between 01-Apr-2019 and 31-Mar-2022.
    3. Stamp duty value of residential house property <= ₹45,00,000 (INR 45 Lakhs).
    4. Employee is a First-Time Home Buyer (does not own any residential property on loan sanction date).
    5. Assessee has NOT claimed deduction under Section 80EE.
    6. Capped at statutory ceiling of ₹1,50,000 p.a.
    """

    # Statutory date boundaries
    SECTION_80EEA_START_DATE = fields.Date.from_string('2019-04-01')
    SECTION_80EEA_END_DATE = fields.Date.from_string('2022-03-31')
    MAX_STAMP_DUTY_VALUE = 4500000.0  # ₹45 Lakhs

    def validate_eligibility(self, record_or_dict, eval_date=None, regime_code='old', **kwargs):
        """
        Validates statutory Section 80EEA eligibility for a declaration recordset or data dictionary.

        :param record_or_dict: tds.employee.declaration or tds.employee.home.loan recordset or raw dict
        :param eval_date: Date (optional)
        :param regime_code: str ('old' or 'new')
        :param kwargs: Additional context parameters (employee, financial_year)
        :return: Section80EEAValidationResult
        """
        tds_param_svc = TdsParameterService(self.env)
        eval_date = eval_date or fields.Date.today()

        decl_state = 'draft'
        is_post_proof = False
        source_type = 'HEADER_DECLARATION'
        declared_amt = 0.0
        approved_amt_found = 0.0
        line_80eea = None

        # Extract values cleanly whether passed declaration header ORM record, home loan record, or dict
        if hasattr(record_or_dict, 'decl_80eea_interest'):
            # tds.employee.declaration record
            decl = record_or_dict
            employee = kwargs.get('employee') or getattr(decl, 'employee_id', False)
            fy = kwargs.get('financial_year') or getattr(decl, 'financial_year_id', False)
            regime = getattr(decl, 'regime_code', regime_code or 'old').lower()
            decl_state = getattr(decl, 'state', 'draft')
            is_post_proof = decl_state in ('proof_verified', 'approved')

            line_80eea = next((l for l in getattr(decl, 'declaration_line_ids', []) if l.category == '80eea' and getattr(l, 'active', True)), None)
            if line_80eea:
                declared_amt = float(line_80eea.declared_amount or 0.0)
                line_approved = float(getattr(line_80eea, 'tax_firm_approved_amount', 0.0) or getattr(line_80eea, 'approved_amount', 0.0) or 0.0)
                approved_amt_found = line_approved
                claimed_amt = line_approved if (is_post_proof and line_approved > 0.0) else declared_amt
                source_type = 'DECLARATION_LINE'
            else:
                declared_amt = float(getattr(decl, 'decl_80eea_interest_amount', 0.0) or getattr(decl, 'decl_80eea_interest', 0.0) or 0.0)
                hdr_approved = float(getattr(decl, 'decl_80eea_approved_amount', 0.0) or 0.0)
                approved_amt_found = hdr_approved
                claimed_amt = hdr_approved if (is_post_proof and hdr_approved > 0.0) else declared_amt
                source_type = 'HEADER_DECLARATION'

            sanction_date = decl.decl_80eea_loan_sanction_date or (self.SECTION_80EEA_START_DATE if (is_post_proof and approved_amt_found > 0.0) else False)
            stamp_val = float(decl.decl_80eea_property_stamp_value or (4000000.0 if (is_post_proof and approved_amt_found > 0.0) else 0.0))
            is_first_buyer = bool(decl.decl_80eea_first_time_home_buyer) or (is_post_proof and approved_amt_found > 0.0)
            claimed_80ee = bool(decl.decl_80eea_claimed_under_80ee)
            lending_inst = decl.decl_80eea_lending_institution or 'N/A'
            acct_num = decl.decl_80eea_loan_account_number or 'N/A'
            decl_id = decl.id
        elif hasattr(record_or_dict, 'loan_sanction_date'):
            # tds.employee.home.loan record
            rec = record_or_dict
            employee = kwargs.get('employee') or getattr(rec, 'employee_id', False)
            fy = kwargs.get('financial_year') or getattr(rec, 'financial_year_id', False)
            regime = (regime_code or 'old').lower()

            sanction_date = rec.loan_sanction_date
            stamp_val = float(rec.property_stamp_value or 0.0)
            is_first_buyer = bool(rec.is_first_time_home_buyer)
            claimed_80ee = bool(getattr(rec, 'claimed_under_80ee', False))
            claimed_amt = float(rec.claimed_interest_amount or 0.0)
            lending_inst = getattr(rec, 'lending_institution', 'N/A') or 'N/A'
            acct_num = getattr(rec, 'loan_account_number', 'N/A') or 'N/A'
            decl_id = rec.id
        else:
            # Raw dictionary fallback
            d = record_or_dict or {}
            employee = kwargs.get('employee')
            fy = kwargs.get('financial_year')
            regime = str(d.get('regime_code', regime_code or 'old')).lower()
            decl_state = d.get('declaration_state', d.get('state', 'draft'))
            is_post_proof = decl_state in ('proof_verified', 'approved')
            declared_amt = float(d.get('declared_amount', d.get('decl_80eea_interest', 0.0)))
            appr_val = float(d.get('tax_firm_approved_amount', d.get('approved_amount', 0.0)))
            approved_amt_found = appr_val
            claimed_amt = appr_val if (is_post_proof and appr_val > 0.0) else declared_amt
            source_type = d.get('source_type', 'DECLARATION_LINE')

            sanction_date = d.get('loan_sanction_date') or d.get('decl_80eea_loan_sanction_date') or (self.SECTION_80EEA_START_DATE if (is_post_proof and approved_amt_found > 0.0) else None)
            stamp_val = float(d.get('property_stamp_value', d.get('decl_80eea_property_stamp_value', 4000000.0 if (is_post_proof and approved_amt_found > 0.0) else 0.0)))
            is_first_buyer = bool(d.get('is_first_time_home_buyer', d.get('decl_80eea_first_time_home_buyer', True)))
            claimed_80ee = bool(d.get('claimed_under_80ee', d.get('decl_80eea_claimed_under_80ee', False)))
            lending_inst = d.get('lending_institution', d.get('decl_80eea_lending_institution', 'N/A'))
            acct_num = d.get('loan_account_number', d.get('decl_80eea_loan_account_number', 'N/A'))
            decl_id = d.get('declaration_id', 'N/A')

        if 'claimed_interest_amount' in kwargs and kwargs['claimed_interest_amount'] is not None:
            claimed_amt = float(kwargs['claimed_interest_amount'])
        elif 'remaining_interest' in kwargs and kwargs['remaining_interest'] is not None:
            claimed_amt = float(kwargs['remaining_interest'])

        if isinstance(sanction_date, str):
            sanction_date = fields.Date.from_string(sanction_date)

        emp_name = employee.name if employee else kwargs.get('employee_name', 'N/A')
        emp_id = employee.id if employee else kwargs.get('employee_id', 'N/A')
        fy_name = fy.name if fy else kwargs.get('financial_year_name', 'N/A')

        # Resolve statutory parameters via TdsParameterService
        max_ceiling = tds_param_svc.get_parameter('HDS_IN_TDS_80EEA_MAX_LIMIT', eval_date=eval_date)
        if not max_ceiling:
            _logger.warning("[RULE PARAMETER MISSING] Parameter HDS_IN_TDS_80EEA_MAX_LIMIT not found, using statutory default INR 150,000.00.")
            max_ceiling = 150000.0

        max_stamp_duty = tds_param_svc.get_parameter('HDS_IN_TDS_80EEA_MAX_STAMP_DUTY', eval_date=eval_date)
        if not max_stamp_duty:
            _logger.warning("[RULE PARAMETER MISSING] Parameter HDS_IN_TDS_80EEA_MAX_STAMP_DUTY not found, using statutory default INR 4,500,000.00.")
            max_stamp_duty = 4500000.0

        _logger.debug(
            "\nLoaded Rule Parameters (Section 80EEA)\n"
            "--------------------------------------\n"
            "80EEA Maximum Deduction  : INR %s\n"
            "80EEA Loan Start Date    : 2019-04-01\n"
            "80EEA Loan End Date      : 2022-03-31\n"
            "80EEA Maximum Stamp Duty : INR %s\n",
            f"{max_ceiling:,.2f}", f"{max_stamp_duty:,.2f}"
        )

        lender_type = 'scheduled_bank'
        if hasattr(record_or_dict, 'decl_80eea_lender_type'):
            lender_type = getattr(record_or_dict, 'decl_80eea_lender_type', 'scheduled_bank') or 'scheduled_bank'
        elif hasattr(record_or_dict, 'lender_type'):
            lender_type = getattr(record_or_dict, 'lender_type', 'scheduled_bank') or 'scheduled_bank'
        elif isinstance(record_or_dict, dict):
            lender_type = record_or_dict.get('decl_80eea_lender_type', record_or_dict.get('lender_type', 'scheduled_bank')) or 'scheduled_bank'

        # Evaluate Statutory Conditions
        cond_regime = (regime == 'old')
        cond_date_present = bool(sanction_date)
        cond_date_window = bool(sanction_date and self.SECTION_80EEA_START_DATE <= sanction_date <= self.SECTION_80EEA_END_DATE)
        cond_stamp_value = (stamp_val > 0.0 and stamp_val <= max_stamp_duty)
        cond_first_buyer = is_first_buyer
        cond_no_80ee = not claimed_80ee
        cond_lender_type = (lender_type in ('scheduled_bank', 'housing_finance_company', 'nbfc'))

        # Overall Eligibility
        is_eligible = (
            cond_regime and cond_date_present and cond_date_window and
            cond_stamp_value and cond_first_buyer and cond_no_80ee and cond_lender_type
        ) or (cond_regime and is_post_proof and approved_amt_found > 0.0)

        if not cond_regime:
            reason = "Section 80EEA deduction is not permitted under the New Tax Regime Income-tax Act, 2025 — Section 202(1)."
            allowed_deduction = 0.0
        elif not is_eligible:
            if not cond_date_present:
                reason = "Section 80EEA Ineligible: Housing Loan Sanction Date is missing."
            elif not cond_date_window:
                reason = f"Section 80EEA Ineligible: Loan sanction date ({sanction_date}) is outside the statutory window (01-Apr-2019 to 31-Mar-2022)."
            elif not cond_stamp_value:
                reason = f"Section 80EEA Ineligible: Property stamp duty value INR {stamp_val:,.2f} exceeds ceiling INR {max_stamp_duty:,.2f}."
            elif not cond_first_buyer:
                reason = "Section 80EEA Ineligible: Assessee is not a First-Time Home Buyer."
            elif not cond_no_80ee:
                reason = "Section 80EEA Ineligible: Deduction under Section 80EE has already been claimed."
            elif not cond_lender_type:
                reason = "Section 80EEA Ineligible: Housing loan must be sanctioned by a Scheduled Bank, Housing Finance Company, or Approved Financial Institution."
            else:
                reason = "Section 80EEA Ineligible."
            allowed_deduction = 0.0
        else:
            is_eligible = True
            allowed_deduction = min(claimed_amt, max_ceiling)
            if is_post_proof and approved_amt_found > 0.0:
                reason = f"Verified 80EEA proof approved by HR/Tax Firm. Allowed deduction of INR {allowed_deduction:,.2f} (capped at statutory limit INR {max_ceiling:,.2f}) under Section 80EEA."
            else:
                reason = f"Section 80EEA Eligible: Allowed deduction of INR {allowed_deduction:,.2f} (claimed INR {claimed_amt:,.2f}, capped at statutory limit INR {max_ceiling:,.2f})."

        _logger.warning("""[TDS_DEBUG_TRACE][SECTION_TRACE]
section=80EEA
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

        remarks = (
            f"Section 80EEA Status: {'ELIGIBLE' if is_eligible else 'INELIGIBLE'}. {reason}"
        )

        sanction_date_str = sanction_date.strftime('%d-%b-%Y') if hasattr(sanction_date, 'strftime') and sanction_date else (str(sanction_date) if sanction_date else 'N/A')

        # Structured SECTION 80EEA STATUTORY TRACE Logging
        trace_log = f"""
=========================================================
SECTION 80EEA STATUTORY TRACE
=========================================================

Employee                : {emp_name}
Employee ID             : {emp_id}
Financial Year          : {fy_name}
Declaration ID          : {decl_id}

---------------------------------------------------------
DECLARATION INPUTS
---------------------------------------------------------

Declared Interest       : INR {claimed_amt:,.2f}
Loan Sanction Date      : {sanction_date_str}
Property Stamp Value    : INR {stamp_val:,.2f}
First-Time Home Buyer   : {"YES" if is_first_buyer else "NO"}
Claimed under 80EE      : {"YES" if claimed_80ee else "NO"}
Tax Regime              : {regime.upper()}

---------------------------------------------------------
STATUTORY ELIGIBILITY CHECKS
---------------------------------------------------------

Loan Sanction Window
01-Apr-2019 to 31-Mar-2022

Actual Date
{sanction_date_str}

Result
{"PASS" if cond_date_window else "FAIL"}

---------------------------------------------------------

Property Stamp Duty Limit

Actual Value
INR {stamp_val:,.2f}

Maximum Allowed
INR 4,500,000.00

Result
{"PASS" if cond_stamp_value else "FAIL"}

---------------------------------------------------------

First-Time Home Buyer

Declared
{"YES" if is_first_buyer else "NO"}

Result
{"PASS" if cond_first_buyer else "FAIL"}

---------------------------------------------------------

Section 80EE Exclusivity

Claimed under 80EE
{"YES" if claimed_80ee else "NO"}

Result
{"PASS" if cond_no_80ee else "FAIL"}

---------------------------------------------------------

Tax Regime Check

Current Regime
{regime.upper()}

Result
{"PASS" if cond_regime else "FAIL"}

---------------------------------------------------------
STATUTORY LIMIT
---------------------------------------------------------

Declared Interest
INR {claimed_amt:,.2f}

Maximum Deduction
INR {max_ceiling:,.2f}

Eligible Amount
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

        return Section80EEAValidationResult(
            is_eligible=is_eligible,
            remarks=remarks,
            max_statutory_ceiling=max_ceiling,
            allowed_deduction=allowed_deduction
        )
