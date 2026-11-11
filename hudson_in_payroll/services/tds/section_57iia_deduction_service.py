# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import fields
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class Section57IIATraceResult:
    """
    Data Transfer Object (DTO) holding Section 57(iia) Family Pension statutory trace & deduction details.
    """
    def __init__(self, is_eligible=False, allowed_deduction=0.0, excess_amount=0.0,
                 one_third_amount=0.0, configured_limit=15000.0, cap_applied=False,
                 remarks="", trace_log=""):
        self.is_eligible = is_eligible
        self.allowed_deduction = allowed_deduction
        self.excess_amount = excess_amount
        self.one_third_amount = one_third_amount
        self.configured_limit = configured_limit
        self.cap_applied = cap_applied
        self.remarks = remarks
        self.trace_log = trace_log


class Section57IIADeductionService(BaseStatutoryService):
    """
    Phase 5 Service: Section 57(iia) Family Pension Statutory Trace & Eligibility Service.
    Generates detailed statutory audit traces for Section 57(iia) Family Pension Deductions.
    Single Source of Truth for Section 57(iia) statutory audit logging.
    """

    @classmethod
    def get_legal_reference_label(cls, financial_year=None, eval_date=None):
        """
        Returns statutory legal label:
        - Up to FY 2025-26: "Section 57(iia), Income-tax Act 1961"
        - From FY 2026-27 onwards: "Section 93(1)(d), Income-tax Act 2025"
        """
        is_ita_2025 = False
        if financial_year:
            if getattr(financial_year, 'start_date', False):
                is_ita_2025 = financial_year.start_date.year >= 2026
            elif getattr(financial_year, 'name', False):
                import re
                m = re.search(r'20(\d{2})', financial_year.name)
                if m and int(m.group(1)) >= 26:
                    is_ita_2025 = True
        elif eval_date:
            ref_year = eval_date.year if hasattr(eval_date, 'year') else int(str(eval_date)[:4])
            is_ita_2025 = (eval_date >= fields.Date.from_string('2026-04-01')) if hasattr(eval_date, 'year') else (ref_year >= 2026)
        else:
            is_ita_2025 = True
        
        return "Family Pension Section 93(1)(d), Income-tax Act 2025" if is_ita_2025 else "Section 57(iia), Income-tax Act 1961"

    @classmethod
    def get_statutory_section_code(cls, financial_year=None, eval_date=None):
        label = cls.get_legal_reference_label(financial_year=financial_year, eval_date=eval_date)
        return "93(1)(d)" if "93(1)(d)" in label else "57(iia)"

    def validate_and_trace(self, declaration_or_dict, eval_date=None, regime_code='old', employee=None, financial_year=None, **kwargs):
        """
        Evaluates Section 57(iia) / Section 93(1)(d) statutory eligibility and produces standard ASCII statutory trace log.
        """
        regime = (regime_code or 'old').lower()

        # 1. Extract Declaration Inputs
        family_pension_amt = 0.0
        decl = None
        source_type = 'HEADER_DECLARATION'
        decl_id = 'N/A'
        decl_state = 'draft'

        if hasattr(declaration_or_dict, 'decl_57iia_family_pension'):
            decl = declaration_or_dict
            employee = employee or decl.employee_id
            financial_year = financial_year or decl.financial_year_id
            decl_id = decl.id
            decl_state = getattr(decl, 'state', 'draft')
            is_post_proof = decl_state in ('proof_verified', 'approved')
            regime = (getattr(decl, 'regime_code', False) or regime).lower()

            # Check line vs header source
            line_57iia = next((l for l in getattr(decl, 'declaration_line_ids', []) if l.category == '57iia' and getattr(l, 'active', True)), None)
            if line_57iia:
                declared_amt = float(line_57iia.declared_amount or 0.0)
                line_approved = float(getattr(line_57iia, 'tax_firm_approved_amount', 0.0) or getattr(line_57iia, 'approved_amount', 0.0) or 0.0)
                approved_amt = line_approved
                family_pension_amt = line_approved if (is_post_proof and line_approved > 0.0) else declared_amt
                source_type = 'DECLARATION_LINE'
            else:
                declared_amt = float(getattr(decl, 'decl_57iia_family_pension', 0.0) or 0.0)
                hdr_approved = float(getattr(decl, 'decl_57iia_approved_amount', 0.0) or 0.0)
                approved_amt = hdr_approved
                family_pension_amt = hdr_approved if (is_post_proof and hdr_approved > 0.0) else declared_amt
                source_type = 'HEADER_DECLARATION'
        else:
            d = declaration_or_dict or {}
            decl = None
            decl_state = d.get('declaration_state', 'draft')
            is_post_proof = decl_state in ('proof_verified', 'approved')
            declared_amt = float(d.get('declared_amount', d.get('decl_57iia_family_pension', 0.0)))
            appr_val = float(d.get('tax_firm_approved_amount', d.get('approved_amount', 0.0)))
            approved_amt = appr_val
            family_pension_amt = appr_val if (is_post_proof and appr_val > 0.0) else declared_amt
            source_type = d.get('source_type', 'DECLARATION_LINE')
            decl_id = d.get('declaration_id', 'N/A')

        emp_name = employee.name if employee else kwargs.get('employee_name', 'N/A')
        emp_id = employee.id if employee else kwargs.get('employee_id', 'N/A')
        fy_name = financial_year.name if financial_year else 'N/A'
        emp_type = kwargs.get('employer_type') or (getattr(employee, 'hds_in_employer_category', getattr(employee, 'employer_type', 'private')) if employee else 'private') or 'private'

        # Legal Reference Labels
        legal_label = self.get_legal_reference_label(financial_year=financial_year, eval_date=eval_date)
        sec_code_label = self.get_statutory_section_code(financial_year=financial_year, eval_date=eval_date)

        # 2. Evaluate Eligibility via Single Source of Truth Engine
        from .eligibility_rule_engine_service import EligibilityRuleEngineService
        from .tds_parameter_service import TdsParameterService

        tds_param_svc = TdsParameterService(self.env)
        configured_limit = tds_param_svc.get_family_pension_limit(regime=regime, eval_date=eval_date)
        param_code = 'HDS_IN_TDS_FAMILY_PENSION_LIMIT_NEW' if regime == 'new' else 'HDS_IN_TDS_FAMILY_PENSION_LIMIT_OLD'

        engine = EligibilityRuleEngineService(self.env)
        engine_res = engine.evaluate_eligibility(
            '57iia',
            declared_amount=declared_amt,
            approved_amount=approved_amt,
            declaration_state=decl_state,
            regime_code=regime,
            eval_date=eval_date
        )

        allowed_deduction = engine_res.eligible_deduction
        excess_amount = engine_res.excess_amount
        one_third_amt = round((approved_amt if (is_post_proof and approved_amt > 0.0) else declared_amt) / 3.0, 2)
        cap_applied = family_pension_amt > 0 and (one_third_amt > configured_limit)
        cap_applied_str = "YES" if cap_applied else "NO"
        is_eligible = allowed_deduction > 0.0 or family_pension_amt == 0.0

        from .tds_declaration_lifecycle_logger import TdsDeclarationLifecycleLogger
        lifecycle_logger = TdsDeclarationLifecycleLogger(self.env)
        calc_phase = lifecycle_logger.get_calculation_phase(decl_state)
        amount_source = lifecycle_logger.get_amount_source(decl_state)

        verified_amt = float(getattr(decl, 'decl_57iia_verified_amount', 0.0) or 0.0) if decl else 0.0
        usable_amt = allowed_deduction

        _logger.warning("""[TDS_DEBUG_TRACE][SECTION_TRACE]
section=%s
declaration_state=%s
declared_amount=%s
approved_amount=%s
eligible_amount=%s
usable_amount=%s
selected_amount=%s
final_chapter6a_amount=%s
source_type=%s""",
            sec_code_label, decl_state, declared_amt, approved_amt, allowed_deduction, allowed_deduction, allowed_deduction, allowed_deduction, source_type
        )

        # 3. Generate Formatted Statutory Trace Log
        trace_log = f"""
============================================================
TDS {sec_code_label.upper()} FAMILY PENSION STATUTORY TRACE
============================================================

EMPLOYEE CONTEXT
------------------------------------------------------------
Employee                 : {emp_name}
Employee ID              : {emp_id}
Financial Year           : {fy_name}
Declaration ID           : {decl_id}
Declaration State        : {decl_state}

Section                  : {sec_code_label}
Statutory Reference      : {legal_label}
Source Type              : {source_type}

------------------------------------------------------------
DECLARATION
------------------------------------------------------------
Family Pension Declared  : INR {family_pension_amt:,.2f}

------------------------------------------------------------
RULE CONTEXT
------------------------------------------------------------
Tax Regime               : {regime}
Employer Type            : {emp_type}
Evaluation Date          : {eval_date or fields.Date.today()}

Parameter Code           : {param_code}
Configured Maximum       : INR {configured_limit:,.2f}

------------------------------------------------------------
CALCULATION
------------------------------------------------------------
Family Pension           : INR {family_pension_amt:,.2f}
One Third of Pension     : INR {one_third_amt:,.2f}
Configured Maximum       : INR {configured_limit:,.2f}
Statutory Eligible       : INR {allowed_deduction:,.2f}
Excess Amount            : INR {excess_amount:,.2f}
Cap Applied              : {cap_applied_str}

Calculation:
min(
    Family Pension / 3,
    Configured Maximum
)
min(
    INR {family_pension_amt:,.2f} / 3,
    INR {configured_limit:,.2f}
)
= min(
    INR {one_third_amt:,.2f},
    INR {configured_limit:,.2f}
)
= INR {allowed_deduction:,.2f}

------------------------------------------------------------
AMOUNT LIFECYCLE
------------------------------------------------------------
Declared / Projected     : INR {family_pension_amt:,.2f}
Eligible / Capped        : INR {allowed_deduction:,.2f}
Verified by HR           : INR {verified_amt:,.2f}
Approved by HR           : INR {approved_amt:,.2f}
Usable Amount            : INR {usable_amt:,.2f}

Amount Source            : {amount_source}
Calculation Phase        : {calc_phase}

------------------------------------------------------------
RECONCILIATION
------------------------------------------------------------
Projected Deduction      : INR {allowed_deduction:,.2f}
Approved Deduction       : INR {approved_amt:,.2f}
Difference               : INR {max(0.0, allowed_deduction - approved_amt):,.2f}
============================================================
"""
        _logger.warning(trace_log)

        return Section57IIATraceResult(
            is_eligible=is_eligible,
            allowed_deduction=allowed_deduction,
            excess_amount=excess_amount,
            one_third_amount=one_third_amt,
            configured_limit=configured_limit,
            cap_applied=cap_applied,
            remarks=f"Section 57(iia) Status: {'ELIGIBLE' if is_eligible else 'INELIGIBLE'}.",
            trace_log=trace_log
        )
