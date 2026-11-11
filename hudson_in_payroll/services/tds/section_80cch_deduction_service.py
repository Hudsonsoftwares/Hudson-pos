# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import fields
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class Section80CCHTraceResult:
    """
    Data Transfer Object (DTO) holding Section 80CCH Agniveer Corpus Fund statutory trace & deduction details.
    """
    def __init__(self, is_eligible=False, declared_amount=0.0, eligible_amount=0.0, excess_amount=0.0,
                 approved_amount=0.0, usable_amount=0.0, source_type='HEADER_DECLARATION', regime='old',
                 parameter_code='HDS_IN_TDS_80CCH_ELIGIBILITY_PERCENT_OLD', configured_percentage=100.0,
                 calculation_phase='PRE-PROOF', eligibility_status='ELIGIBLE', remarks="", trace_log=""):
        self.is_eligible = is_eligible
        self.declared_amount = declared_amount
        self.eligible_amount = eligible_amount
        self.excess_amount = excess_amount
        self.approved_amount = approved_amount
        self.usable_amount = usable_amount
        self.source_type = source_type
        self.regime = regime
        self.parameter_code = parameter_code
        self.configured_percentage = configured_percentage
        self.calculation_phase = calculation_phase
        self.eligibility_status = eligibility_status
        self.remarks = remarks
        self.trace_log = trace_log

    @property
    def allowed_deduction(self):
        return self.eligible_amount



class Section80CCHDeductionService(BaseStatutoryService):
    """
    Phase 5 Service: Section 80CCH Agniveer Corpus Fund Statutory Trace & Eligibility Service.
    Generates statutory audit traces for Section 80CCH Employee Contributions to Agniveer Corpus Fund.
    Single Source of Truth for Section 80CCH statutory calculations.
    """

    def validate_and_trace(self, declaration_or_dict, eval_date=None, regime_code='old', employee=None, financial_year=None, **kwargs):
        """
        Evaluates Section 80CCH statutory eligibility and returns Section80CCHTraceResult DTO.
        """
        regime = (regime_code or 'old').lower()

        # 1. Extract Declaration Inputs (Supporting Header Field & Declaration Line)
        declared_amt = 0.0
        decl = None
        source_type = 'HEADER_DECLARATION'
        decl_id = 'N/A'
        decl_state = 'draft'

        if hasattr(declaration_or_dict, 'decl_80cch_agniveer'):
            decl = declaration_or_dict
            employee = employee or decl.employee_id
            financial_year = financial_year or decl.financial_year_id
            decl_id = decl.id
            decl_state = getattr(decl, 'state', 'draft')
            regime = (getattr(decl, 'regime_code', False) or regime).lower()

            is_post_proof = decl_state in ('proof_verified', 'approved')
            line_80cch = next((l for l in getattr(decl, 'declaration_line_ids', []) if l.category == '80cch' and getattr(l, 'active', True)), None)
            if line_80cch:
                declared_amt = float(line_80cch.declared_amount or 0.0)
                line_approved = float(getattr(line_80cch, 'tax_firm_approved_amount', 0.0) or getattr(line_80cch, 'approved_amount', 0.0) or 0.0)
                source_amt = line_approved if (is_post_proof and line_approved > 0.0) else declared_amt
                source_type = 'DECLARATION_LINE'
            else:
                declared_amt = float(getattr(decl, 'decl_80cch_agniveer', 0.0) or 0.0)
                hdr_approved = float(getattr(decl, 'decl_80cch_approved_amount', 0.0) or 0.0)
                source_amt = hdr_approved if (is_post_proof and hdr_approved > 0.0) else declared_amt
                source_type = 'HEADER_DECLARATION'
        else:
            d = declaration_or_dict or {}
            decl = None
            decl_state = d.get('declaration_state', 'draft')
            is_post_proof = decl_state in ('proof_verified', 'approved')
            declared_amt = float(d.get('decl_80cch_agniveer', d.get('declared_amount', 0.0)))
            appr_val = float(d.get('approved_amount', 0.0))
            source_amt = appr_val if (is_post_proof and appr_val > 0.0) else declared_amt
            source_type = d.get('source_type', 'DECLARATION_LINE')
            decl_id = d.get('declaration_id', 'N/A')

        emp_name = employee.name if employee else kwargs.get('employee_name', 'N/A')
        emp_id = employee.id if employee else kwargs.get('employee_id', 'N/A')
        fy_name = financial_year.name if financial_year else 'N/A'

        # 2. Resolve Statutory Parameter via TdsParameterService
        from .tds_parameter_service import TdsParameterService
        tds_param_svc = TdsParameterService(self.env)
        configured_pct = tds_param_svc.get_80cch_eligibility_percent(regime=regime, eval_date=eval_date)
        param_code = 'HDS_IN_TDS_80CCH_ELIGIBILITY_PERCENT_NEW' if regime == 'new' else 'HDS_IN_TDS_80CCH_ELIGIBILITY_PERCENT_OLD'

        verified_amt = float(getattr(decl, 'decl_80cch_verified_amount', 0.0) or 0.0) if decl else 0.0
        approved_amt = source_amt if is_post_proof else 0.0
        amount_source_label = "APPROVED/POST-PROOF" if (is_post_proof and source_amt > 0.0) else "PROJECTED"
        calc_phase = "POST-PROOF" if is_post_proof else "PRE-PROOF"

        # Check Agnipath Scheme eligibility if employee is identified
        is_agnipath = getattr(employee, 'hds_in_is_agnipath', False) if employee else kwargs.get('is_agnipath', True)
        if employee and not is_agnipath:
            eligible_amount = 0.0
            excess_amount = source_amt
            usable_amount = 0.0
            is_eligible = False
            status_str = 'INELIGIBLE (Not enrolled under Agnipath Scheme)'
            remarks = (
                f"Section 80CCH Status: INELIGIBLE. Employee is not enrolled under the Agnipath Scheme. "
                f"Agniveer Corpus Fund deduction is not allowable."
            )
        else:
            # 3. Perform Eligibility & Deduction Calculation
            eligible_amount = round(source_amt * (configured_pct / 100.0), 2)
            excess_amount = max(0.0, source_amt - eligible_amount)
            usable_amount = eligible_amount
            is_eligible = (eligible_amount > 0.0 or source_amt == 0.0)
            status_str = 'ELIGIBLE' if is_eligible else 'INELIGIBLE'
            remarks = (
                f"Section 80CCH Status: ELIGIBLE. Agniveer Corpus Fund contribution "
                f"of INR {source_amt:,.2f} is allowable as deduction under Section 80CCH ({configured_pct:.0f}% rate)."
            )

        # 4. Generate Formatted Statutory Audit Trace Log
        trace_log = f"""
============================================================
80CCH AGNIVEER CORPUS FUND STATUTORY TRACE
============================================================

EMPLOYEE CONTEXT
------------------------------------------------------------
Employee                 : {emp_name}
Employee ID              : {emp_id}
Financial Year           : {fy_name}
Declaration ID           : {decl_id}
Declaration State        : {decl_state}
Section                  : Sec 80CCH
Source Type              : {source_type}

------------------------------------------------------------
EMPLOYEE CONTRIBUTION
------------------------------------------------------------
Employee Contribution    : INR {declared_amt:,.2f}

------------------------------------------------------------
RULE CONTEXT
------------------------------------------------------------
Tax Regime               : {regime}
Evaluation Date          : {eval_date or fields.Date.today()}
Rule Parameter           : {param_code}
Configured Eligibility % : {configured_pct:.2f}%

------------------------------------------------------------
ELIGIBILITY CALCULATION
------------------------------------------------------------
Calculation Source Amount: INR {source_amt:,.2f}
Eligibility Percentage   : {configured_pct:.2f}%

Calculation:
INR {source_amt:,.2f} x {configured_pct:.2f}%
= INR {eligible_amount:,.2f}

Eligible Amount          : INR {eligible_amount:,.2f}
Excess Amount            : INR {excess_amount:,.2f}
Cap Applied              : NO

------------------------------------------------------------
AMOUNT LIFECYCLE
------------------------------------------------------------
Declared / Projected     : INR {declared_amt:,.2f}
Approved by HR           : INR {approved_amt:,.2f}
Source Amount            : INR {source_amt:,.2f}
Eligible / Capped        : INR {eligible_amount:,.2f}
Verified by HR           : INR {verified_amt:,.2f}
Usable Amount            : INR {usable_amount:,.2f}

Amount Source            : {amount_source_label}
Calculation Phase        : {calc_phase}

------------------------------------------------------------
STATUTORY CONCLUSION
------------------------------------------------------------
80CCH Eligibility        : {status_str}

Reason:
Employee contribution is eligible according to the configured
80CCH eligibility percentage.
============================================================
"""
        _logger.warning(trace_log)

        return Section80CCHTraceResult(
            is_eligible=is_eligible,
            declared_amount=declared_amt,
            eligible_amount=eligible_amount,
            excess_amount=excess_amount,
            approved_amount=approved_amt,
            usable_amount=usable_amount,
            source_type=source_type,
            regime=regime,
            parameter_code=param_code,
            configured_percentage=configured_pct,
            calculation_phase=calc_phase,
            eligibility_status=status_str,
            remarks=remarks,
            trace_log=trace_log
        )
