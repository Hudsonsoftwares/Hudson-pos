# -*- coding: utf-8 -*-
import logging
from odoo import fields
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class Section80GGTraceResult:
    """
    Data Transfer Object (DTO) holding Section 80GG statutory trace & deduction details.
    """
    def __init__(self, is_eligible=False, allowed_deduction=0.0, remarks="", trace_log="",
                 declared_amount=0.0, approved_amount=0.0, eligible_amount=0.0,
                 ati=0.0, component_a=0.0, component_b=0.0, component_c=0.0,
                 rejection_reason="", selected_source='HEADER_DECLARATION', selected_amount=0.0,
                 declared_rent=0.0, verified_rent=0.0, approved_rent=0.0, effective_rent=0.0):
        self.is_eligible = is_eligible
        self.allowed_deduction = allowed_deduction
        self.remarks = remarks
        self.trace_log = trace_log
        self.declared_amount = declared_amount
        self.approved_amount = approved_amount
        self.eligible_amount = eligible_amount
        self.ati = ati
        self.component_a = component_a
        self.component_b = component_b
        self.component_c = component_c
        self.rejection_reason = rejection_reason
        self.selected_source = selected_source
        self.selected_amount = selected_amount
        self.declared_rent = declared_rent or declared_amount
        self.verified_rent = verified_rent
        self.approved_rent = approved_rent
        self.effective_rent = effective_rent
        self.allowed_80gg = allowed_deduction

    @property
    def usable_amount(self):
        return self.allowed_deduction


class Section80GGDeductionService(BaseStatutoryService):
    """
    Phase 5 Service: Section 80GG Statutory Deduction Service.
    Evaluates Section 80GG eligibility (Form 10BA, No HRA, No House at Duty/Residence, No Self-Occupied House Elsewhere).
    Calculates statutory deduction: Min( ₹5,000/month, 25% of ATI, Rent Paid - 10% of ATI ).
    Single Source of Truth for Section 80GG.
    """

    def validate_and_trace(self, declaration_or_dict, eval_date=None, regime_code='old', employee=None, financial_year=None, **kwargs):
        """
        Evaluates Section 80GG statutory eligibility, calculates allowed deduction, logs structured audit,
        and returns Section80GGTraceResult.
        """
        regime = (regime_code or 'old').lower()
        eval_dt = eval_date or fields.Date.today()

        decl = None
        line_80gg = None
        decl_state = 'draft'
        source_type = 'HEADER_DECLARATION'
        declared_rent = 0.0
        verified_rent = 0.0
        approved_rent = 0.0

        if hasattr(declaration_or_dict, 'declaration_id') and getattr(declaration_or_dict, 'category', False) == '80gg':
            line_80gg = declaration_or_dict
            decl = line_80gg.declaration_id
            employee = employee or line_80gg.employee_id or (decl.employee_id if decl else None)
            financial_year = financial_year or line_80gg.financial_year_id or (decl.financial_year_id if decl else None)
            decl_state = getattr(decl, 'state', 'draft') if decl else getattr(line_80gg, 'validation_status', 'draft')
            source_type = 'DECLARATION_LINE'

            owns_house_work_place = bool(getattr(decl, 'decl_80gg_owns_house_work_place', False)) if decl else False
            owns_house_elsewhere = bool(getattr(decl, 'decl_80gg_owns_house_elsewhere', False)) if decl else False
            hra_received = bool(getattr(decl, 'decl_80gg_hra_received', False)) if decl else False
            form_10ba_filed = bool(getattr(decl, 'decl_80gg_form_10ba_filed', False)) if decl else False

        elif hasattr(declaration_or_dict, 'decl_80gg_rent') or hasattr(declaration_or_dict, 'decl_80gg_form_10ba_filed'):
            decl = declaration_or_dict
            employee = employee or decl.employee_id
            financial_year = financial_year or decl.financial_year_id
            decl_state = getattr(decl, 'state', 'draft')
            line_80gg = next((l for l in getattr(decl, 'declaration_line_ids', []) if l.category == '80gg' and getattr(l, 'active', True)), None)
            source_type = 'DECLARATION_LINE' if line_80gg else 'HEADER_DECLARATION'

            owns_house_work_place = bool(getattr(decl, 'decl_80gg_owns_house_work_place', False))
            owns_house_elsewhere = bool(getattr(decl, 'decl_80gg_owns_house_elsewhere', False))
            hra_received = bool(getattr(decl, 'decl_80gg_hra_received', False))
            form_10ba_filed = bool(getattr(decl, 'decl_80gg_form_10ba_filed', False))

        elif isinstance(declaration_or_dict, dict):
            d = declaration_or_dict
            owns_house_work_place = bool(d.get('owns_house_work_place', False) or d.get('decl_80gg_owns_house_work_place', False))
            owns_house_elsewhere = bool(d.get('owns_house_elsewhere', False) or d.get('decl_80gg_owns_house_elsewhere', False))
            hra_received = bool(d.get('hra_received', False) or d.get('decl_80gg_hra_received', False))
            form_10ba_filed = bool(d.get('form_10ba_filed', False) or d.get('decl_80gg_form_10ba_filed', False))
            regime = d.get('regime_code', regime).lower()
            decl_state = d.get('state', 'draft')
        else:
            owns_house_work_place = False
            owns_house_elsewhere = False
            hra_received = False
            form_10ba_filed = False

        if decl and getattr(decl, 'regime_code', False):
            regime = decl.regime_code.lower()

        # Resolve actual payroll HRA received for the relevant period
        payslip = kwargs.get('payslip') or kwargs.get('payslip_id')
        payslip_hra = 0.0
        if payslip:
            hra_lines = getattr(payslip, 'line_ids', None)
            if hra_lines:
                matching_hra = hra_lines.filtered(lambda l: l.code in ('HRA', 'HOUSE_RENT_ALLOWANCE') or 'HRA' in str(l.code).upper())
                payslip_hra = sum(matching_hra.mapped('total'))
            if payslip_hra <= 0.0 and hasattr(payslip, 'hds_in_hra'):
                payslip_hra = float(payslip.hds_in_hra or 0.0)

        payroll_annual_hra = float(kwargs.get('hra_amount', 0.0) or (d.get('hra_amount', 0.0) if 'd' in locals() and d else 0.0))
        if payroll_annual_hra <= 0.0 and employee:
            try:
                from .salary_projection_service import SalaryProjectionService
                sal_svc = SalaryProjectionService(self.env)
                eval_date_to_use = eval_date or (getattr(financial_year, 'start_date', False) if financial_year else False) or fields.Date.today()
                sal_res = sal_svc.project_salary(employee, financial_year, eval_date=eval_date_to_use)
                payroll_annual_hra = float(getattr(sal_res, 'total_hra', 0.0) or 0.0)
            except (AttributeError, ValueError, KeyError) as e:
                _logger.warning("Parameter/Salary resolution fallback for Section 80GG HRA check: %s", str(e))
                payroll_annual_hra = 0.0
            except Exception as e:
                _logger.error("Unexpected error projecting salary for Section 80GG: %s", str(e), exc_info=True)
                payroll_annual_hra = 0.0

        effective_hra_amount = max(payslip_hra, payroll_annual_hra)
        if effective_hra_amount > 0.0:
            hra_received = True

        is_80gg_hra_eligible = (effective_hra_amount <= 0.0 and not hra_received)

        # ── Separate declared_rent, verified_rent, approved_rent, effective_rent ──
        is_post_proof = decl_state in ('proof_verified', 'approved')

        if line_80gg:
            declared_rent = float(line_80gg.declared_amount or 0.0)
            verified_rent = float(getattr(line_80gg, 'verified_amount', 0.0) or 0.0)
            tax_firm_appr = float(getattr(line_80gg, 'tax_firm_approved_amount', 0.0) or getattr(line_80gg, 'approved_amount', 0.0) or 0.0)
            approved_rent = tax_firm_appr
            if is_post_proof:
                # Post-proof: use tax_firm_approved_amount (or verified_rent if tax firm approved not set).
                # If approved rent is explicitly 0.0, effective_rent is 0.0 (do NOT fall back to declared rent).
                effective_rent = tax_firm_appr if tax_firm_appr > 0.0 else (verified_rent if verified_rent > 0.0 else 0.0)
                selected_amount = effective_rent
            else:
                effective_rent = declared_rent
                selected_amount = declared_rent
        elif decl:
            declared_rent = float(getattr(decl, 'decl_80gg_rent', 0.0) or 0.0)
            approved_rent = float(getattr(decl, 'decl_80gg_approved_rent', 0.0) or getattr(decl, 'decl_80gg_approved_amount', 0.0) or 0.0)
            if is_post_proof:
                effective_rent = approved_rent
                selected_amount = effective_rent
            else:
                effective_rent = declared_rent
                selected_amount = declared_rent
        elif isinstance(declaration_or_dict, dict):
            declared_rent = float(d.get('rent_amount', 0.0) or d.get('declared_amount', 0.0) or d.get('decl_80gg_rent', 0.0) or 0.0)
            verified_rent = float(d.get('verified_amount', 0.0) or 0.0)
            approved_rent = float(d.get('tax_firm_approved_amount', 0.0) or d.get('approved_amount', 0.0) or 0.0)
            if is_post_proof:
                effective_rent = approved_rent if approved_rent > 0.0 else (verified_rent if verified_rent > 0.0 else 0.0)
                selected_amount = effective_rent
            else:
                effective_rent = declared_rent
                selected_amount = declared_rent
        else:
            effective_rent = 0.0
            selected_amount = 0.0

        # Eligibility Checks
        is_eligible = False
        rejection_reason = ""

        if regime != 'old':
            rejection_reason = "Section 80GG not eligible under the New Tax Regime."
        elif not is_80gg_hra_eligible:
            rejection_reason = "Section 80GG not eligible: HRA is received during the relevant period."
        elif owns_house_work_place:
            rejection_reason = "Section 80GG not eligible: Employee owns a residential house at the place of residence/work."
        elif owns_house_elsewhere:
            rejection_reason = "Section 80GG not eligible: Residential property elsewhere is treated as self-occupied."
        elif not form_10ba_filed:
            rejection_reason = "Section 80GG not eligible: Form 10BA has not been filed."
        elif effective_rent <= 0.0:
            rejection_reason = "Section 80GG not eligible: Rent paid / approved rent is zero."
        else:
            is_eligible = True

        # Resolve Adjusted Total Income (ATI)
        dict_ati = (declaration_or_dict.get('adjusted_total_income', 0.0) or declaration_or_dict.get('ati', 0.0)) if isinstance(declaration_or_dict, dict) else 0.0
        ati = float(kwargs.get('ati', 0.0) or kwargs.get('adjusted_total_income', 0.0) or dict_ati or 0.0)
        if ati <= 0.0 and employee:
            try:
                from .annual_income_projection_service import AnnualIncomeProjectionService
                from .standard_deduction_service import StandardDeductionService
                ann_svc = AnnualIncomeProjectionService(self.env)
                eval_date_to_use = eval_date or (getattr(financial_year, 'start_date', False) if financial_year else False) or fields.Date.today()
                proj = ann_svc.project_annual_income(employee, eval_date=eval_date_to_use)
                gti = float(getattr(proj, 'gross_total_income', 0.0) or getattr(proj, 'gross_annual_income', 0.0) or 0.0)

                std_svc = StandardDeductionService(self.env)
                std_res = std_svc.calculate_standard_deduction(regime_code=regime, gross_payroll_income=gti, eval_date=eval_date_to_use)
                std_ded = std_res if isinstance(std_res, (int, float)) else getattr(std_res, 'standard_deduction', 0.0)

                other_c6a = float(kwargs.get('other_chapter_6a', 0.0) or 0.0)
                ati = max(0.0, gti - float(std_ded or 0.0) - other_c6a)
            except (AttributeError, ValueError, KeyError) as e:
                _logger.warning("ATI resolution fallback for Section 80GG: %s", str(e))
                ati = 0.0
            except Exception as e:
                _logger.error("Unexpected error calculating ATI for Section 80GG for employee ID %s: %s", getattr(employee, 'id', 'N/A'), str(e), exc_info=True)
                ati = 0.0

        from .tds_parameter_service import TdsParameterService
        tds_param_svc = TdsParameterService(self.env)
        monthly_limit = tds_param_svc.get_parameter('80GG_MAX_MONTHLY_LIMIT', eval_date=eval_dt) or 5000.0

        # Component A: ₹5,000 / month * 12 months = ₹60,000
        component_a = monthly_limit * 12.0
        # Component B: 25% of Adjusted Total Income
        component_b = 0.25 * ati
        # Component C: Rent Paid − 10% of Adjusted Total Income
        component_c = max(0.0, effective_rent - (0.10 * ati))

        allowed_80gg = 0.0
        if is_eligible:
            allowed_80gg = max(0.0, min(component_a, component_b, component_c))
            remarks = (
                f"Section 80GG Status: ELIGIBLE. Statutory deduction of INR {allowed_80gg:,.2f} is allowable "
                f"(Min of ₹5,000/mo: ₹{component_a:,.2f}, 25% ATI: ₹{component_b:,.2f}, Rent - 10% ATI: ₹{component_c:,.2f})."
            )
        else:
            remarks = rejection_reason

        emp_name = getattr(employee, 'name', 'N/A') if employee else 'N/A'
        payslip_str = getattr(payslip, 'number', getattr(payslip, 'name', 'N/A')) if payslip else 'N/A'

        # Structured [80GG_HRA_TRACE] Log
        _logger.warning("""[80GG_HRA_TRACE]
employee=%s
payslip=%s
hra_amount=%s
hra_received_flag=%s
80gg_hra_eligible=%s
decision=%s
allowed_deduction=%s
rejection_reason=%s""",
            emp_name,
            payslip_str,
            effective_hra_amount,
            hra_received,
            is_80gg_hra_eligible,
            "ELIGIBLE" if is_eligible else "NOT_ELIGIBLE",
            allowed_80gg,
            rejection_reason if not is_eligible else "N/A"
        )

        # Structured [80GG_AUDIT] Log
        _logger.warning("""[80GG_AUDIT]
regime=%s
owns_house_work_place=%s
owns_house_elsewhere=%s
hra_received=%s
form_10ba_filed=%s
rent_paid=%s
adjusted_total_income=%s
component_a_fixed=%s
component_b_25pct_ati=%s
component_c_rent_minus_10pct_ati=%s
is_eligible=%s
allowed_80gg=%s
rejection_reason=%s""",
            regime,
            owns_house_work_place,
            owns_house_elsewhere,
            hra_received,
            form_10ba_filed,
            effective_rent,
            ati,
            component_a,
            component_b,
            component_c,
            is_eligible,
            allowed_80gg,
            rejection_reason if not is_eligible else "N/A"
        )

        trace_log = (
            f"=========================================================\n"
            f"SECTION 80GG STATUTORY TRACE\n"
            f"=========================================================\n"
            f"Employee                : {getattr(employee, 'name', 'N/A')}\n"
            f"Financial Year          : {getattr(financial_year, 'name', 'N/A')}\n"
            f"Tax Regime              : {regime.upper()}\n"
            f"Own House at Work/Duty  : {'YES' if owns_house_work_place else 'NO'}\n"
            f"Own House Elsewhere     : {'YES' if owns_house_elsewhere else 'NO'}\n"
            f"HRA Received in Period  : {'YES' if hra_received else 'NO'}\n"
            f"Form 10BA Filed         : {'YES' if form_10ba_filed else 'NO'}\n"
            f"Annual Rent Paid        : INR {effective_rent:,.2f}\n"
            f"Adjusted Total Income   : INR {ati:,.2f}\n"
            f"---------------------------------------------------------\n"
            f"STATUTORY COMPONENTS:\n"
            f"Component A (₹5k/month) : INR {component_a:,.2f}\n"
            f"Component B (25% ATI)   : INR {component_b:,.2f}\n"
            f"Component C (Rent-10%ATI): INR {component_c:,.2f}\n"
            f"---------------------------------------------------------\n"
            f"Eligibility Status      : {'ELIGIBLE' if is_eligible else 'NOT ELIGIBLE'}\n"
            f"Allowed 80GG Deduction  : INR {allowed_80gg:,.2f}\n"
            f"Remarks                 : {remarks}\n"
            f"=========================================================\n"
        )

        # Structured [80GG_POST_PROOF_TRACE] Log
        _logger.warning("""[80GG_POST_PROOF_TRACE]
declared_rent=%s
verified_rent=%s
tax_firm_approved_rent=%s
is_eligible=%s
allowed_80gg=%s""",
            int(declared_rent) if declared_rent == int(declared_rent) else declared_rent,
            int(verified_rent) if verified_rent == int(verified_rent) else verified_rent,
            int(approved_rent) if approved_rent == int(approved_rent) else approved_rent,
            is_eligible,
            int(allowed_80gg) if allowed_80gg == int(allowed_80gg) else allowed_80gg
        )

        return Section80GGTraceResult(
            is_eligible=is_eligible,
            allowed_deduction=allowed_80gg,
            remarks=remarks,
            trace_log=trace_log,
            declared_amount=declared_rent,
            approved_amount=approved_rent if is_post_proof else 0.0,
            eligible_amount=allowed_80gg if is_eligible else 0.0,
            ati=ati,
            component_a=component_a if is_eligible else 0.0,
            component_b=component_b if is_eligible else 0.0,
            component_c=component_c if is_eligible else 0.0,
            rejection_reason=rejection_reason,
            selected_source=source_type,
            selected_amount=allowed_80gg,
            declared_rent=declared_rent,
            verified_rent=verified_rent,
            approved_rent=approved_rent,
            effective_rent=effective_rent
        )
