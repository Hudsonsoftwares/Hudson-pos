# -*- coding: utf-8 -*-
import logging
from odoo import fields
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class Section80GTraceResult:
    """
    Data Transfer Object (DTO) holding Section 80G statutory trace & deduction details.
    """
    def __init__(self, is_eligible=False, allowed_deduction=0.0, remarks="", trace_log="", selected_source='HEADER_DECLARATION', selected_amount=0.0):
        self.is_eligible = is_eligible
        self.allowed_deduction = allowed_deduction
        self.remarks = remarks
        self.trace_log = trace_log
        self.selected_source = selected_source
        self.selected_amount = selected_amount


class Section80GDeductionService(BaseStatutoryService):
    """
    Phase 5 Service: Section 80G Statutory Trace & Eligibility Service.
    Generates detailed statutory audit traces for Section 80G Charitable Donations.
    """

    def validate_and_trace(self, declaration_or_dict, eval_date=None, regime_code='old', employee=None, financial_year=None, **kwargs):
        """
        Evaluates Section 80G statutory eligibility and produces standard ASCII statutory trace log.
        """
        regime = (regime_code or 'old').lower()

        # 1. Extract Declaration Inputs & Perform Explicit Source Selection
        declared_amt = 0.0
        approved_amt_found = 0.0
        header_amount = 0.0
        proof_line_found = False
        proof_line_id = 'N/A'
        proof_status = 'N/A'
        proof_approved_amount = 0.0
        proof_declared_amount = 0.0
        proof_category = 'N/A'
        selected_source = 'HEADER_DECLARATION'
        selected_amount = 0.0
        category = False
        donation_amt = 0.0
        decl_id = 'N/A'
        decl_state = 'draft'

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
            proof_category = getattr(line, 'decl_80g_category', False)

            header_declared = float(getattr(decl, 'decl_80g_donation', 0.0) or 0.0) if decl else 0.0
            header_approved = float(getattr(decl, 'decl_80g_approved_amount', 0.0) or getattr(decl, 'approved_80g', 0.0) or 0.0) if decl else 0.0
            header_amount = header_approved if (is_post_proof and header_approved > 0.0) else header_declared
            header_category = getattr(decl, 'decl_80g_category', False) if decl else False

            # Source selection for line record
            if (is_post_proof and proof_approved_amount > 0.0) or (not is_post_proof and proof_declared_amount > 0.0) or (header_amount == 0.0 and (proof_approved_amount > 0.0 or proof_declared_amount > 0.0)):
                selected_source = 'DECLARATION_LINE'
                selected_amount = proof_approved_amount if (is_post_proof and proof_approved_amount > 0.0) else proof_declared_amount
                category = proof_category or header_category
                declared_amt = proof_declared_amount
                approved_amt_found = proof_approved_amount
                donation_amt = selected_amount
            elif header_amount > 0.0:
                selected_source = 'HEADER_DECLARATION'
                selected_amount = header_amount
                category = header_category or proof_category
                declared_amt = header_declared
                approved_amt_found = header_approved
                donation_amt = selected_amount
            else:
                selected_source = 'DECLARATION_LINE'
                selected_amount = 0.0
                category = proof_category or header_category
                declared_amt = proof_declared_amount
                approved_amt_found = proof_approved_amount
                donation_amt = 0.0

            inst_name = getattr(decl, 'decl_80g_institution_name', 'N/A') if decl else 'N/A'
            is_approved = bool(getattr(decl, 'decl_80g_is_approved', True)) or (is_post_proof and approved_amt_found > 0.0)
            pay_mode = getattr(decl, 'decl_80g_mode', 'neft_rtgs') if decl else 'neft_rtgs'
            donation_date = getattr(decl, 'decl_80g_donation_date', None) if decl else None
            receipt_num = getattr(decl, 'decl_80g_receipt_number', 'N/A') if decl else 'N/A'
            donee_pan = getattr(decl, 'decl_80g_donee_pan', 'N/A') if decl else 'N/A'
            approval_num = getattr(decl, 'decl_80g_approval_number', 'N/A') if decl else 'N/A'

        elif hasattr(declaration_or_dict, 'decl_80g_donation'):
            decl = declaration_or_dict
            employee = employee or decl.employee_id
            financial_year = financial_year or decl.financial_year_id
            decl_id = decl.id
            decl_state = getattr(decl, 'state', 'draft')
            regime = (getattr(decl, 'regime_code', False) or regime).lower()
            is_post_proof = decl_state in ('proof_verified', 'approved')

            header_declared = float(getattr(decl, 'decl_80g_donation', 0.0) or 0.0)
            header_approved = float(getattr(decl, 'decl_80g_approved_amount', 0.0) or getattr(decl, 'approved_80g', 0.0) or 0.0)
            header_amount = header_approved if (is_post_proof and header_approved > 0.0) else header_declared
            header_category = getattr(decl, 'decl_80g_category', False)

            # Search active 80G declaration / proof lines for this declaration
            lines_80g = decl.declaration_line_ids.filtered(lambda l: l.category == '80g' and getattr(l, 'active', True))
            if not lines_80g and decl.id:
                lines_80g = self.env['tds.employee.declaration.line'].sudo().search([
                    ('declaration_id', '=', decl.id),
                    ('category', '=', '80g')
                ])

            # If multiple lines exist, prioritize line with approved amount > 0, then line with declared > 0, else first line
            approved_line = next((l for l in lines_80g if (float(getattr(l, 'tax_firm_approved_amount', 0.0) or getattr(l, 'approved_amount', 0.0) or getattr(l, 'verified_amount', 0.0) or 0.0) > 0.0)), None)
            target_line = approved_line or (lines_80g[0] if lines_80g else None)

            if target_line:
                proof_line_found = True
                proof_line_id = target_line.id
                proof_status = target_line.validation_status or decl_state
                proof_approved_amount = float(getattr(target_line, 'tax_firm_approved_amount', 0.0) or getattr(target_line, 'approved_amount', 0.0) or getattr(target_line, 'verified_amount', 0.0) or 0.0)
                proof_declared_amount = float(target_line.declared_amount or 0.0)
                proof_category = getattr(target_line, 'decl_80g_category', False)

            # Source Selection decision:
            # 1. If approved proof line exists with approved amount > 0 -> use line
            # 2. If post-proof and proof line exists with approved amount == 0 and header has approved > 0 -> use header
            # 3. If pre-proof and line has declared amount > 0 -> use line
            # 4. If line has 0 but header has declared > 0 -> use header
            # 5. If neither has > 0 -> remain 0
            if proof_line_found and is_post_proof and proof_approved_amount > 0.0:
                selected_source = 'DECLARATION_LINE'
                selected_amount = proof_approved_amount
                category = proof_category or header_category
                declared_amt = proof_declared_amount
                approved_amt_found = proof_approved_amount
                donation_amt = proof_approved_amount
            elif is_post_proof and header_approved > 0.0:
                selected_source = 'HEADER_DECLARATION'
                selected_amount = header_approved
                category = header_category or proof_category
                declared_amt = header_declared
                approved_amt_found = header_approved
                donation_amt = header_approved
            elif proof_line_found and not is_post_proof and proof_declared_amount > 0.0:
                selected_source = 'DECLARATION_LINE'
                selected_amount = proof_declared_amount
                category = proof_category or header_category
                declared_amt = proof_declared_amount
                approved_amt_found = proof_approved_amount
                donation_amt = proof_declared_amount
            elif header_declared > 0.0:
                selected_source = 'HEADER_DECLARATION'
                selected_amount = header_amount
                category = header_category or proof_category
                declared_amt = header_declared
                approved_amt_found = header_approved
                donation_amt = header_amount
            elif proof_line_found:
                selected_source = 'DECLARATION_LINE'
                selected_amount = 0.0
                category = proof_category or header_category
                declared_amt = proof_declared_amount
                approved_amt_found = proof_approved_amount
                donation_amt = 0.0
            else:
                selected_source = 'HEADER_DECLARATION'
                selected_amount = 0.0
                category = header_category
                declared_amt = header_declared
                approved_amt_found = header_approved
                donation_amt = 0.0

            inst_name = decl.decl_80g_institution_name or 'N/A'
            is_approved = bool(decl.decl_80g_is_approved) or (is_post_proof and approved_amt_found > 0.0)
            pay_mode = decl.decl_80g_mode or 'neft_rtgs'
            donation_date = decl.decl_80g_donation_date
            receipt_num = decl.decl_80g_receipt_number or 'N/A'
            donee_pan = decl.decl_80g_donee_pan or 'N/A'
            approval_num = decl.decl_80g_approval_number or 'N/A'

        else:
            d = declaration_or_dict or {}
            decl = None
            decl_state = d.get('declaration_state', d.get('state', 'draft'))
            is_post_proof = decl_state in ('proof_verified', 'approved')
            decl_id = d.get('declaration_id', 'N/A')

            header_amount = float(d.get('header_amount', d.get('decl_80g_donation', 0.0)))
            header_category = d.get('header_category', d.get('decl_80g_category'))

            proof_appr = float(d.get('tax_firm_approved_amount', d.get('approved_amount', 0.0)))
            proof_decl = float(d.get('declared_amount', d.get('decl_80g_donation', 0.0)))
            proof_cat = d.get('decl_80g_category') or d.get('category_80g') or d.get('category')
            proof_line_id = d.get('line_id', d.get('proof_line_id', 'N/A'))
            proof_status = d.get('validation_status', d.get('proof_status', decl_state))
            proof_line_found = d.get('proof_line_found', bool(d.get('source_type') == 'DECLARATION_LINE' or 'approved_amount' in d or 'tax_firm_approved_amount' in d or 'declared_amount' in d))

            proof_approved_amount = proof_appr
            proof_declared_amount = proof_decl
            proof_category = proof_cat

            # Source selection for dictionary payload
            explicit_source = d.get('source_type')
            if explicit_source:
                selected_source = explicit_source
                if selected_source == 'DECLARATION_LINE':
                    selected_amount = proof_appr if (is_post_proof and proof_appr > 0.0) else proof_decl
                    category = proof_cat or header_category
                else:
                    selected_amount = header_amount
                    category = header_category or proof_cat
            elif proof_line_found and is_post_proof and proof_appr > 0.0:
                selected_source = 'DECLARATION_LINE'
                selected_amount = proof_appr
                category = proof_cat or header_category
            elif is_post_proof and header_amount > 0.0:
                selected_source = 'HEADER_DECLARATION'
                selected_amount = header_amount
                category = header_category or proof_cat
            elif proof_line_found and not is_post_proof and proof_decl > 0.0:
                selected_source = 'DECLARATION_LINE'
                selected_amount = proof_decl
                category = proof_cat or header_category
            elif header_amount > 0.0:
                selected_source = 'HEADER_DECLARATION'
                selected_amount = header_amount
                category = header_category or proof_cat
            elif proof_line_found:
                selected_source = 'DECLARATION_LINE'
                selected_amount = 0.0
                category = proof_cat or header_category
            else:
                selected_source = 'HEADER_DECLARATION'
                selected_amount = 0.0
                category = header_category

            declared_amt = proof_decl if selected_source == 'DECLARATION_LINE' else header_amount
            approved_amt_found = proof_appr if selected_source == 'DECLARATION_LINE' else header_amount
            donation_amt = selected_amount

            inst_name = d.get('decl_80g_institution_name', 'N/A')
            is_approved = bool(d.get('decl_80g_is_approved', True)) or (is_post_proof and approved_amt_found > 0.0)
            pay_mode = d.get('decl_80g_mode', 'neft_rtgs')
            donation_date = d.get('decl_80g_donation_date')
            receipt_num = d.get('decl_80g_receipt_number', 'N/A')
            donee_pan = d.get('decl_80g_donee_pan', 'N/A')
            approval_num = d.get('decl_80g_approval_number', 'N/A')

        _logger.warning("""
=========================================================
80G_SOURCE_SELECTION
header_amount=%s
proof_line_found=%s
proof_line_id=%s
proof_status=%s
proof_approved_amount=%s
proof_category=%s
selected_source=%s
selected_amount=%s
=========================================================""",
            header_amount, proof_line_found, proof_line_id, proof_status,
            proof_approved_amount, proof_category, selected_source, selected_amount
        )

        if donation_amt > 0.0 and not category:
            from odoo.exceptions import ValidationError
            from odoo import _
            raise ValidationError(_(
                "Section 80G Deduction Category is missing for donation amount of ₹%s. "
                "Please select a valid 80G category (100%% No Limit, 50%% No Limit, 100%% With Limit, or 50%% With Limit)."
            ) % f"{donation_amt:,.2f}")

        emp_name = employee.name if employee else kwargs.get('employee_name', 'N/A')
        emp_id = employee.id if employee else kwargs.get('employee_id', 'N/A')
        fy_name = financial_year.name if financial_year else 'N/A'

        # 2. Map Category & Mode Labels
        cat_display_map = {
            '100_no_limit': '100% Deduction (Without Qualifying Limit)',
            '50_no_limit': '50% Deduction (Without Qualifying Limit)',
            '100_with_limit': '100% Deduction (Subject to Qualifying Limit)',
            '50_with_limit': '50% Deduction (Subject to Qualifying Limit)',
        }
        mode_display_map = {
            'cash': 'Cash',
            'cheque': 'Cheque',
            'dd': 'Demand Draft',
            'neft_rtgs': 'NEFT / RTGS / Banking Channel',
            'upi': 'UPI / BHIM',
            'other_digital': 'Other Digital Payment',
        }

        category_str = cat_display_map.get(category, 'N/A')
        mode_str = mode_display_map.get(pay_mode, 'NEFT / RTGS')

        # Resolve statutory rule parameters
        from .tds_parameter_service import TdsParameterService
        tds_param_svc = TdsParameterService(self.env)
        try:
            max_cash_allowed = tds_param_svc.get_parameter('HDS_IN_TDS_80G_MAX_CASH_DONATION', eval_date=eval_date)
        except (KeyError, ValueError, AttributeError):
            max_cash_allowed = 2000.0
        if not max_cash_allowed:
            max_cash_allowed = 2000.0

        try:
            qualifying_limit_pct = tds_param_svc.get_parameter('HDS_IN_TDS_80G_QUALIFYING_LIMIT_PERCENT', eval_date=eval_date)
        except (KeyError, ValueError, AttributeError):
            qualifying_limit_pct = 10.0
        if not qualifying_limit_pct or qualifying_limit_pct > 100.0:
            qualifying_limit_pct = 10.0

        _logger.debug(
            "\nLoaded Rule Parameters (Section 80G)\n"
            "-------------------------------------\n"
            "80G Maximum Cash Allowed      : INR %s\n"
            "80G Qualifying Limit Percent  : %s%%\n",
            f"{max_cash_allowed:,.2f}", f"{qualifying_limit_pct:.1f}"
        )

        # Percentage determination
        pct = 100.0 if category in ('100_no_limit', '100_with_limit') else 50.0
        has_qualifying_limit = category in ('100_with_limit', '50_with_limit')

        # Compute / Resolve Adjusted Gross Total Income (AGTI u/s 80G(10))
        agti = float(kwargs.get('agti', 0.0) or (d.get('agti', 0.0) if 'd' in locals() and d else 0.0))
        if agti <= 0.0 and employee:
            try:
                from .annual_income_projection_service import AnnualIncomeProjectionService
                from .standard_deduction_service import StandardDeductionService
                ann_svc = AnnualIncomeProjectionService(self.env)
                eval_date_to_use = eval_date
                if not eval_date_to_use and financial_year:
                    eval_date_to_use = getattr(financial_year, 'start_date', False) or getattr(financial_year, 'date_from', False)
                if not eval_date_to_use:
                    fy_rec = self.env['tds.financial.year'].search([('active', '=', True)], limit=1) or self.env['tds.financial.year'].search([], limit=1)
                    if fy_rec:
                        eval_date_to_use = getattr(fy_rec, 'start_date', False) or getattr(fy_rec, 'date_from', False)
                if not eval_date_to_use:
                    eval_date_to_use = fields.Date.today()

                proj = ann_svc.project_annual_income(employee, eval_date=eval_date_to_use)
                gti = float(getattr(proj, 'gross_total_income', 0.0) or getattr(proj, 'gross_annual_income', 0.0) or 0.0)

                std_svc = StandardDeductionService(self.env)
                std_res = std_svc.calculate_standard_deduction(regime_code=regime, gross_payroll_income=gti, eval_date=eval_date_to_use)
                std_ded = std_res if isinstance(std_res, (int, float)) else getattr(std_res, 'standard_deduction', 0.0)

                agti = max(0.0, gti - float(std_ded or 0.0))
            except Exception as e:
                _logger.warning("Failed to calculate AGTI for Section 80G for employee ID %s: %s", getattr(employee, 'id', 'N/A'), str(e), exc_info=True)
                agti = 0.0

        # Qualifying Limit Amount u/s 80G(10)
        qualifying_limit_amount = (agti * (qualifying_limit_pct / 100.0)) if (has_qualifying_limit and agti > 0.0) else 0.0

        # Eligible Donation Considered
        if has_qualifying_limit and agti > 0.0:
            eligible_donation = min(donation_amt, qualifying_limit_amount)
        else:
            eligible_donation = donation_amt

        # 3. Statutory Eligibility Checks
        cond_regime = (regime == 'old')
        cond_approved = is_approved or (is_post_proof and approved_amt_found > 0.0)
        cond_cash_limit = not (pay_mode == 'cash' and donation_amt > max_cash_allowed)

        is_eligible = False
        allowed_deduction = 0.0
        reason = ""

        if not cond_regime:
            reason = "Section 80G Ineligible: Charitable Donations are not permitted under the New Tax Regime Income-tax Act, 2025 — Section 202(1)."
            allowed_deduction = 0.0
        elif donation_amt <= 0.0:
            reason = "No Section 80G deduction allowable: Declared donation amount is zero."
            allowed_deduction = 0.0
        elif not cond_approved:
            reason = "Section 80G Ineligible: Donee institution does not hold valid Section 80G approval status."
            allowed_deduction = 0.0
        elif not cond_cash_limit:
            reason = f"Section 80G Ineligible: Cash donations exceeding INR {max_cash_allowed:,.2f} are statutorily disallowed under Section 80G(5D)."
            allowed_deduction = 0.0
        else:
            is_eligible = True
            allowed_deduction = eligible_donation * (pct / 100.0)

            cat_statutory_text = {
                '100_no_limit': 'eligible for 100% deduction without any qualifying limit',
                '50_no_limit': 'eligible for 50% deduction without any qualifying limit',
                '100_with_limit': 'eligible for 100% deduction subject to qualifying limit',
                '50_with_limit': 'eligible for 50% deduction subject to qualifying limit',
            }.get(category, 'eligible for 50% deduction subject to qualifying limit')

            if pct == 100.0 and not has_qualifying_limit:
                deduction_text = f"Accordingly, the entire declared donation of INR {donation_amt:,.2f} is allowable as a deduction."
            elif has_qualifying_limit and agti > 0.0 and donation_amt > qualifying_limit_amount:
                deduction_text = f"Declared donation of INR {donation_amt:,.2f} exceeds statutory qualifying limit ({qualifying_limit_pct:.0f}% of AGTI = INR {qualifying_limit_amount:,.2f}). Accordingly, {pct:.0f}% of eligible donation INR {eligible_donation:,.2f} (INR {allowed_deduction:,.2f}) is allowable as a deduction."
            else:
                deduction_text = f"Accordingly, {pct:.0f}% of the declared donation of INR {donation_amt:,.2f} (INR {allowed_deduction:,.2f}) is allowable as a deduction."

            reason = (
                f"Donation is made to an institution approved under Section 80G and {cat_statutory_text}.\n\n"
                f"{deduction_text}"
            )

        if not is_eligible:
            eligible_donation_considered = 0.0
            effective_pct = 0.0
            allowed_deduction = 0.0
        else:
            eligible_donation_considered = eligible_donation
            effective_pct = pct

        remarks = f"Section 80G Status: {'ELIGIBLE' if is_eligible else 'INELIGIBLE'}. {reason}"

        _logger.warning("""[TDS_DEBUG_TRACE][SECTION_TRACE]
section=80G
declaration_state=%s
declared_amount=%s
approved_amount=%s
eligible_amount=%s
usable_amount=%s
selected_amount=%s
final_chapter6a_amount=%s
source_type=%s""",
            decl_state, declared_amt, approved_amt_found, eligible_donation_considered, allowed_deduction, allowed_deduction, allowed_deduction, selected_source
        )
        _logger.warning("80G_FINAL_CHAPTER6A_AMOUNT=%s", allowed_deduction)

        donation_date_str = donation_date.strftime('%d-%b-%Y') if hasattr(donation_date, 'strftime') and donation_date else (str(donation_date) if donation_date else 'N/A')
        cash_amt_str = f"INR {donation_amt:,.2f}" if pay_mode == 'cash' else "INR 0.00"

        # 4. Generate Multi-Line Statutory Trace Log
        agti_str = f"INR {agti:,.2f}" if agti > 0.0 else "N/A (AGTI Context Not Provided)"
        qual_limit_str = f"INR {qualifying_limit_amount:,.2f}" if (has_qualifying_limit and agti > 0.0) else "N/A (Without Qualifying Limit)"

        trace_log = f"""
=========================================================
SECTION 80G STATUTORY TRACE
=========================================================

Employee                : {emp_name}
Employee ID             : {emp_id}
Financial Year          : {fy_name}
Declaration ID          : {decl_id}

---------------------------------------------------------
DECLARATION INPUTS
---------------------------------------------------------

Donation Amount         : INR {donation_amt:,.2f}
Institution Name        : {inst_name}
Institution Category    : {category_str}
Approved u/s 80G        : {"YES" if is_approved else "NO"}
Donation Mode           : {mode_str}
Donation Date           : {donation_date_str}
Receipt Number          : {receipt_num}
Donee PAN               : {donee_pan}

---------------------------------------------------------
STATUTORY ELIGIBILITY CHECKS
---------------------------------------------------------

Approved Institution
Result
{"PASS" if cond_approved else "FAIL"}

---------------------------------------------------------

Donation Mode

Cash Donation Amount
{cash_amt_str}

Maximum Cash Allowed
INR {max_cash_allowed:,.2f}

Result
{"PASS" if cond_cash_limit else "FAIL"}

---------------------------------------------------------

Deduction Category

{category_str}

---------------------------------------------------------

Qualifying Limit (Section 80G(10))

Applicable
{"YES" if has_qualifying_limit else "NO"}

Adjusted Gross Total Income (AGTI)
{agti_str}

Qualifying Limit Percentage
{qualifying_limit_pct:.0f}%

Qualifying Limit Amount
{qual_limit_str}

Eligible Donation Considered
INR {eligible_donation_considered:,.2f}

---------------------------------------------------------
STATUTORY CALCULATION
---------------------------------------------------------

Declared Donation
INR {donation_amt:,.2f}

Qualifying Limit Applicable
{"YES" if has_qualifying_limit else "NO"}

Eligible Donation Considered
INR {eligible_donation_considered:,.2f}

Eligible Percentage
{effective_pct:.0f}%

Approved Section 80G Deduction
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

        return Section80GTraceResult(
            is_eligible=is_eligible,
            allowed_deduction=allowed_deduction,
            remarks=remarks,
            trace_log=trace_log,
            selected_source=selected_source,
            selected_amount=selected_amount
        )
