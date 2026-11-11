# -*- coding: utf-8 -*-
import logging
from ..base import BaseStatutoryService
from .employee_tax_declaration_validation_service import EmployeeTaxDeclarationValidationService

_logger = logging.getLogger(__name__)


class Chapter6aDeductionResult:
    """
    Data Transfer Object (DTO) holding Chapter VI-A approved deductions breakdown.
    """
    def __init__(self, section_80c=0.0, section_80ccd1b=0.0, section_80d=0.0,
                 section_80dd=0.0, section_80tta_80ttb=0.0, section_80eea=0.0,
                 section_80g=0.0, section_80e=0.0, section_80u=0.0, section_80cch=0.0,
                 section_80gg=0.0, other_80_deductions=0.0, total_chapter_6a=0.0):
        self.section_80c = section_80c
        self.section_80ccd1b = section_80ccd1b
        self.section_80d = section_80d
        self.section_80dd = section_80dd
        self.section_80tta_80ttb = section_80tta_80ttb
        self.section_80eea = section_80eea
        self.section_80g = section_80g
        self.section_80e = section_80e
        self.section_80u = section_80u
        self.section_80cch = section_80cch
        self.section_80gg = section_80gg
        self.other_80_deductions = other_80_deductions
        self.total_chapter_6a = total_chapter_6a

    @property
    def sec_80gg(self):
        return self.section_80gg

    @property
    def sec_80c(self):
        return self.section_80c

    @property
    def sec_80ccd1b(self):
        return self.section_80ccd1b

    @property
    def sec_80d(self):
        return self.section_80d

    @property
    def sec_80dd(self):
        return self.section_80dd

    @property
    def sec_80tta(self):
        return self.section_80tta_80ttb

    @property
    def sec_80eea(self):
        return self.section_80eea

    @property
    def sec_80g(self):
        return self.section_80g

    @property
    def sec_80e(self):
        return self.section_80e

    @property
    def sec_80u(self):
        return self.section_80u

    @property
    def sec_80cch(self):
        return self.section_80cch

    @property
    def total_chapter_6a_deductions(self):
        return self.total_chapter_6a

    @property
    def other_80(self):
        return self.other_80_deductions


class Chapter6aDeductionService(BaseStatutoryService):
    """
    Phase 5 Service: Chapter VI-A Deduction Service.
    Calculates approved Chapter VI-A deductions for the employee:
    Section 80C, Section 80CCD(1B), Section 80D, Section 80DD, Section 80TTA / 80TTB.
    Strictly enforces regime restrictions (returns 0.0 for all Chapter VI-A under New Tax Regime).
    """

    def calculate_chapter_6a_deductions(self, employee, financial_year, regime_code, eval_date=None, declaration_id=None):
        """
        Calculates approved Chapter VI-A deductions.

        :param employee: hr.employee record
        :param financial_year: tds.financial.year record
        :param regime_code: str ('old' or 'new')
        :param eval_date: Date (optional)
        :param declaration_id: tds.employee.declaration record (optional)
        :return: Chapter6aDeductionResult
        """
        regime_code = (regime_code or 'new').lower()

        # Under New Tax Regime (Section 115BAC), Chapter VI-A deductions are strictly prohibited
        if regime_code == 'new':
            return Chapter6aDeductionResult()

        decl = declaration_id if declaration_id else self.env['tds.employee.declaration'].sudo().search([
            ('employee_id', '=', employee.id),
            ('financial_year_id', '=', financial_year.id)
        ], limit=1)

        reg_rec = self.env['tds.employee.tax.regime'].sudo().search([
            ('employee_id', '=', employee.id),
            ('financial_year_id', '=', financial_year.id)
        ], limit=1)

        _logger.info(
            "\n======================================\n"
            "REGIME TRACE\n"
            "======================================\n"
            "Employee                     : %s (ID: %s)\n"
            "Financial Year               : %s (ID: %s)\n"
            "Employee Tax Regime Record ID: %s\n"
            "Selected Regime in Database  : %s\n"
            "Resolved Regime Code         : %s\n"
            "Resolved Regime Name         : %s\n"
            "======================================",
            employee.name if employee else 'N/A', employee.id if employee else 'N/A',
            financial_year.name if financial_year else 'N/A', financial_year.id if financial_year else 'N/A',
            reg_rec.id if reg_rec else 'None',
            reg_rec.regime_id.code if (reg_rec and reg_rec.regime_id) else 'None',
            regime_code.upper(),
            reg_rec.regime_id.name if (reg_rec and reg_rec.regime_id) else 'N/A'
        )

        if not decl:
            return Chapter6aDeductionResult()

        val_svc = EmployeeTaxDeclarationValidationService(self.env)
        val_svc.validate_declaration(decl, regime_code=regime_code, eval_date=eval_date)

        from .tds_parameter_service import TdsParameterService
        tds_param_svc = TdsParameterService(self.env)
        max_80c = tds_param_svc.get_80c_limit(eval_date=eval_date) or 150000.0
        max_80ccd1b = tds_param_svc.get_80ccd1b_limit(eval_date=eval_date) or 50000.0

        raw_80c = 0.0
        raw_80ccd1b = 0.0
        section_80d = 0.0
        section_80dd = 0.0
        section_80tta_80ttb = 0.0
        section_80eea = 0.0
        other_80 = 0.0

        # Section 80G Statutory Deduction via Section80GDeductionService (Single Source of Truth)
        section_80g = 0.0
        if decl:
            from .section_80g_deduction_service import Section80GDeductionService
            g_svc = Section80GDeductionService(self.env)
            g_res = g_svc.validate_and_trace(
                decl,
                eval_date=eval_date,
                regime_code=regime_code,
                employee=employee,
                financial_year=financial_year
            )
            section_80g = g_res.allowed_deduction if regime_code == 'old' else 0.0

        # Section 80E Statutory Deduction via Section80EDeductionService (Single Source of Truth)
        section_80e = 0.0
        if decl:
            from .section_80e_deduction_service import Section80EDeductionService
            e_svc = Section80EDeductionService(self.env)
            e_res = e_svc.validate_and_trace(
                decl,
                eval_date=eval_date,
                regime_code=regime_code,
                employee=employee,
                financial_year=financial_year
            )
            section_80e = e_res.allowed_deduction if regime_code == 'old' else 0.0
        # Section 80DD Statutory Deduction via Section80DDDeductionService (Single Source of Truth)
        section_80dd = 0.0
        has_80dd_decl = False
        if decl:
            has_80dd_header = (bool(getattr(decl, 'decl_80dd_disability_exists', False)) or bool(getattr(decl, 'decl_80dd_dependent_name', False)))
            has_80dd_line = any(l.category == '80dd' for l in decl.declaration_line_ids)
            has_80dd_decl = has_80dd_header or has_80dd_line

        if decl and has_80dd_decl:
            from .section_80dd_deduction_service import Section80DDDeductionService
            dd_svc = Section80DDDeductionService(self.env)
            dd_res = dd_svc.validate_and_trace(
                decl,
                eval_date=eval_date,
                regime_code=regime_code,
                employee=employee,
                financial_year=financial_year
            )
            section_80dd = dd_res.allowed_deduction if regime_code == 'old' else 0.0

        # Section 80U Statutory Deduction via Section80UDeductionService (Single Source of Truth)
        section_80u = 0.0
        has_80u_decl = False
        if decl:
            has_80u_header = (float(getattr(decl, 'decl_80u_disability_percentage', 0.0) or 0.0) > 0.0 or float(getattr(decl, 'decl_80u_renewal_disability_percentage', 0.0) or 0.0) > 0.0 or bool(getattr(decl, 'decl_80u_has_certificate', False)))
            has_80u_line = any(l.category == '80u' for l in decl.declaration_line_ids)
            has_80u_decl = has_80u_header or has_80u_line

        if decl and has_80u_decl:
            from .section_80u_deduction_service import Section80UDeductionService
            u_svc = Section80UDeductionService(self.env)
            u_res = u_svc.validate_and_trace(
                decl,
                eval_date=eval_date,
                regime_code=regime_code,
                employee=employee,
                financial_year=financial_year
            )
            section_80u = u_res.allowed_deduction if regime_code == 'old' else 0.0

        # Section 80GG Statutory Deduction via Section80GGDeductionService (Single Source of Truth)
        section_80gg = 0.0
        has_80gg_decl = False
        if decl:
            has_80gg_header = (float(getattr(decl, 'decl_80gg_rent', 0.0) or 0.0) > 0.0 or bool(getattr(decl, 'decl_80gg_form_10ba_filed', False)))
            has_80gg_line = any(l.category == '80gg' for l in decl.declaration_line_ids)
            has_80gg_decl = has_80gg_header or has_80gg_line

        if decl and has_80gg_decl:
            from .section_80gg_deduction_service import Section80GGDeductionService
            gg_svc = Section80GGDeductionService(self.env)
            gg_res = gg_svc.validate_and_trace(
                decl,
                eval_date=eval_date,
                regime_code=regime_code,
                employee=employee,
                financial_year=financial_year
            )
            section_80gg = gg_res.allowed_deduction if regime_code == 'old' else 0.0

        # Section 57(iia) Statutory Deduction via Section57IIADeductionService (Single Source of Truth)
        section_57iia = 0.0
        has_57iia_decl = False
        if decl:
            has_57iia_header = (float(getattr(decl, 'decl_57iia_family_pension', 0.0) or 0.0) > 0.0)
            has_57iia_line = any(l.category == '57iia' for l in decl.declaration_line_ids)
            has_57iia_decl = has_57iia_header or has_57iia_line

        if decl and has_57iia_decl:
            from .section_57iia_deduction_service import Section57IIADeductionService
            p_svc = Section57IIADeductionService(self.env)
            p_res = p_svc.validate_and_trace(
                decl,
                eval_date=eval_date,
                regime_code=regime_code,
                employee=employee,
                financial_year=financial_year
            )
            section_57iia = p_res.allowed_deduction

        # Section 80CCH Statutory Deduction via Section80CCHDeductionService (Single Source of Truth)
        section_80cch = 0.0
        has_80cch_decl = False
        if decl:
            has_80cch_header = (float(getattr(decl, 'decl_80cch_agniveer', 0.0) or 0.0) > 0.0)
            has_80cch_line = any(l.category == '80cch' for l in decl.declaration_line_ids)
            has_80cch_decl = has_80cch_header or has_80cch_line

        if decl and has_80cch_decl:
            from .section_80cch_deduction_service import Section80CCHDeductionService
            cch_svc = Section80CCHDeductionService(self.env)
            cch_res = cch_svc.validate_and_trace(
                decl,
                eval_date=eval_date,
                regime_code=regime_code,
                employee=employee,
                financial_year=financial_year
            )
            section_80cch = cch_res.usable_amount

        # Section 80EEA Statutory Deduction via HomeLoanDeductionService (Single Source of Truth)
        section_80eea = 0.0
        final_24b = 0.0
        has_80eea_decl = False
        if decl:
            has_80eea_header = (float(getattr(decl, 'decl_80eea_interest_amount', 0.0) or 0.0) > 0.0 or bool(getattr(decl, 'decl_80eea_loan_sanction_date', False)))
            has_80eea_line = any(l.category == '80eea' for l in decl.declaration_line_ids)
            has_80eea_decl = has_80eea_header or has_80eea_line

        if decl:
            from .home_loan_deduction_service import HomeLoanDeductionService
            hl_svc = HomeLoanDeductionService(self.env)
            hl_res = hl_svc.calculate_home_loan_deductions(
                employee=employee,
                financial_year=financial_year,
                regime_code=regime_code,
                eval_date=eval_date
            )
            final_24b = hl_res.section_24b_self_interest if regime_code == 'old' else 0.0
            section_80eea = hl_res.section_80eea_interest if (regime_code == 'old' and has_80eea_decl) else 0.0

        running_total = 0.0
        has_80d_line = False
        has_80g_line = False
        has_80e_line = False
        has_80dd_line = False
        has_80u_line = False
        has_80ccd2_line = False
        has_57iia_line = False
        has_80cch_line = False
        has_80eea_line = False

        from .tds_declaration_lifecycle_logger import TdsDeclarationLifecycleLogger
        lifecycle_logger = TdsDeclarationLifecycleLogger(self.env)

        from .tds_parameter_service import TdsParameterService
        tds_param_svc = TdsParameterService(self.env)

        for line in decl.declaration_line_ids:
            cat = line.category
            amt = line.usable_amount
            is_permitted = line.is_regime_permitted
            is_act = getattr(line, 'active', True)

            reason = "Included in deduction calculation"
            selected_amt = 0.0

            lifecycle_logger.log_amount_reconciliation_trace(
                employee_name=employee.name if employee else 'N/A',
                employee_id=employee.id if employee else 'N/A',
                financial_year_name=financial_year.name if financial_year else 'N/A',
                declaration_id=decl.id if decl else 'N/A',
                declaration_state=decl.state if decl else 'draft',
                section_code=line.section_code or line.category,
                source_type="DECLARATION_LINE",
                declared_amount=line.declared_amount,
                eligible_amount=line.eligible_amount,
                verified_amount=line.verified_amount,
                approved_amount=line.approved_amount,
                usable_amount=line.usable_amount,
                service_method="Chapter6aDeductionService.calculate_chapter_6a_deductions"
            )

            if not is_permitted:
                reason = "Skipped: Category prohibited under active tax regime (is_regime_permitted = False)"
            elif not is_act:
                reason = "Skipped: Declaration line item inactive (active = False)"
            else:
                if cat == '80c':
                    raw_80c += amt
                    selected_amt = amt
                elif cat == '80ccd1b':
                    raw_80ccd1b += amt
                    selected_amt = amt
                    lifecycle_logger.log_80ccd1b_statutory_trace(
                        employee_name=employee.name if employee else 'N/A',
                        employee_id=employee.id if employee else 'N/A',
                        financial_year_name=financial_year.name if financial_year else 'N/A',
                        declaration_id=decl.id if decl else 'N/A',
                        declaration_state=decl.state if decl else 'draft',
                        declared_amount=line.declared_amount,
                        eligible_amount=line.eligible_amount,
                        verified_amount=line.verified_amount,
                        approved_amount=line.approved_amount,
                        usable_amount=line.usable_amount,
                        statutory_cap=max_80ccd1b
                    )
                elif cat in ('80d_self', '80d_parents', '80d_preventive'):
                    has_80d_line = True
                    section_80d += amt
                    selected_amt = amt

                    if cat == '80d_parents':
                        sr_status = (line.is_senior_citizen or bool(getattr(decl, 'decl_80d_parents_is_senior', False)) or (employee and bool(getattr(employee, 'hds_in_decl_80d_parents_is_senior', False))))
                        stat_lim = tds_param_svc.get_80d_limit(is_senior=sr_status, is_parents=True, eval_date=eval_date) or 25000.0
                    elif cat == '80d_preventive':
                        sr_status = bool(getattr(decl, 'decl_80d_self_is_senior', False) or (employee and (bool(getattr(employee, 'is_senior_citizen', False)) or bool(getattr(employee, 'hds_in_decl_80d_self_is_senior', False)))))
                        stat_lim = tds_param_svc.get_parameter('80D_PREVENTIVE_CHECKUP_LIMIT', eval_date=eval_date) or 5000.0
                    else: # 80d_self
                        sr_status = (line.is_senior_citizen or bool(getattr(decl, 'decl_80d_self_is_senior', False)) or (employee and (bool(getattr(employee, 'is_senior_citizen', False)) or bool(getattr(employee, 'hds_in_decl_80d_self_is_senior', False)))))
                        stat_lim = tds_param_svc.get_80d_limit(is_senior=sr_status, is_parents=False, eval_date=eval_date) or 25000.0

                    _logger.warning("""[TDS_DEBUG_TRACE][80D]
category=%s
declared=%s
eligible=%s
approved=%s
usable=%s
senior_status=%s
statutory_limit=%s
permitted_status=%s""",
                        cat, line.declared_amount, line.eligible_amount, line.approved_amount, line.usable_amount, sr_status, stat_lim, is_permitted)
                elif cat == '80ccd2':
                    has_80ccd2_line = True
                    selected_amt = amt
                    from .salary_projection_service import SalaryProjectionService
                    from .tds_parameter_service import TdsParameterService
                    sal_svc = SalaryProjectionService(self.env)
                    sal_res = sal_svc.project_salary(employee, financial_year, eval_date=eval_date)
                    annual_b = sal_res.total_basic or 0.0
                    annual_d = sal_res.total_da or 0.0
                    sal_b = annual_b + annual_d
                    
                    emp_type = getattr(employee, 'hds_in_employer_category', getattr(employee, 'employer_type', 'private')) or 'private'
                    tds_param_svc = TdsParameterService(self.env)
                    nps_pct = tds_param_svc.get_employer_nps_limit(regime=regime_code, employer_type=emp_type, eval_date=eval_date)
                    param_code = 'HDS_IN_TDS_NPS_LIMIT_NEW' if regime_code == 'new' else ('HDS_IN_TDS_NPS_LIMIT_OLD_GOVT' if 'govt' in str(emp_type).lower() else 'HDS_IN_TDS_NPS_LIMIT_OLD_PRIVATE')
                    calc_ceiling = sal_b * (nps_pct / 100.0)
                    selected_amt = min(amt, round(calc_ceiling, 2))
                    reason = f"Section 80CCD(2) statutory approved deduction (capped at ₹{calc_ceiling:,.2f}): ₹{selected_amt:,.2f}"

                    contract_obj = sal_svc._get_employee_contract(employee) if hasattr(sal_svc, '_get_employee_contract') else False
                    c_id = getattr(contract_obj, 'id', 'N/A') if contract_obj else 'N/A'
                    from .payroll_period_service import PayrollPeriodService
                    _period_svc = PayrollPeriodService(self.env)
                    _emp_periods = _period_svc.calculate_total_periods_in_fy(employee, financial_year, eval_date=eval_date) if (employee and financial_year) else 12.0
                    m_b = float(getattr(contract_obj, 'basic_salary', 0.0) or 0.0) if contract_obj else (annual_b / float(_emp_periods or 12))
                    m_d = float(getattr(contract_obj, 'da', 0.0) or getattr(contract_obj, 'da_amount', 0.0) or 0.0) if contract_obj else (annual_d / float(_emp_periods or 12))

                    # Note: 80CCD(2) dedicated statutory trace is logged by declaration-level trigger in tds.employee.declaration._compute_totals()
                    pass
                elif cat == '57iia':
                    has_57iia_line = True
                    selected_amt = 0.0
                    reason = "Netted under Income from Other Sources"
                elif cat in ('80d_self', '80d_parents', '80d_preventive'):
                    section_80d += amt
                    selected_amt = amt
                elif cat == '80dd':
                    has_80dd_line = True
                    selected_amt = section_80dd
                    reason = f"Section 80DD statutory approved deduction: ₹{section_80dd:,.2f}"
                elif cat == '80u':
                    has_80u_line = True
                    selected_amt = section_80u
                    other_80 += section_80u
                    reason = f"Section 80U statutory approved deduction: ₹{section_80u:,.2f}"
                elif cat in ('80tta', '80ttb'):
                    section_80tta_80ttb += amt
                    selected_amt = amt
                elif cat == '80eea':
                    has_80eea_line = True
                    selected_amt = section_80eea
                    reason = f"Section 80EEA statutory approved deduction: ₹{section_80eea:,.2f}"
                elif cat == '80g':
                    # Section 80G is calculated by Section80GDeductionService (Single Source of Truth)
                    has_80g_line = True
                    selected_amt = section_80g
                    other_80 += section_80g
                    reason = f"Section 80G statutory approved deduction: ₹{section_80g:,.2f}"
                    _logger.warning("""[TDS_DEBUG_TRACE][80G_AGGREGATION]
80G_FINAL_CHAPTER6A_AMOUNT=%s
80G_SELECTED_AMOUNT=%s
80G_INCLUDED_IN_CHAPTER6A=%s
TOTAL_CHAPTER6A_DEDUCTIONS_SO_FAR=%s""",
                        section_80g, selected_amt, other_80, running_total + selected_amt
                    )
                elif cat == '80e':
                    # Section 80E is calculated by Section80EDeductionService (Single Source of Truth)
                    has_80e_line = True
                    selected_amt = section_80e
                    other_80 += section_80e
                    reason = f"Section 80E statutory approved deduction: ₹{section_80e:,.2f}"
                    _logger.warning("""[TDS_DEBUG_TRACE][80E_AGGREGATION]
80E_FINAL_CHAPTER6A_AMOUNT=%s
80E_SELECTED_AMOUNT=%s
80E_INCLUDED_IN_CHAPTER6A=%s
TOTAL_CHAPTER6A_DEDUCTIONS_SO_FAR=%s""",
                        section_80e, selected_amt, other_80, running_total + selected_amt
                    )
                elif cat == '80cch':
                    # Section 80CCH is calculated by Section80CCHDeductionService (Single Source of Truth)
                    has_80cch_line = True
                    selected_amt = section_80cch
                    other_80 += section_80cch
                    reason = f"Section 80CCH statutory approved deduction: ₹{section_80cch:,.2f}"
                    lifecycle_logger.log_80cch_statutory_trace(
                        employee_name=employee.name if employee else 'N/A',
                        employee_id=employee.id if employee else 'N/A',
                        financial_year_name=financial_year.name if financial_year else 'N/A',
                        declaration_id=decl.id if decl else 'N/A',
                        declaration_state=decl.state if decl else 'draft',
                        regime_code=regime_code,
                        declared_amount=line.declared_amount,
                        eligible_amount=line.eligible_amount,
                        verified_amount=line.verified_amount,
                        approved_amount=line.approved_amount,
                        usable_amount=line.usable_amount,
                        excess_amount=line.excess_amount,
                        source_type='DECLARATION_LINE'
                    )
                elif cat == '80gg':
                    has_80gg_line = True
                    selected_amt = section_80gg
                    other_80 += section_80gg
                    reason = f"Section 80GG statutory approved deduction: ₹{section_80gg:,.2f}"
                    _logger.warning("""[TDS_DEBUG_TRACE][80GG_AGGREGATION]
80GG_FINAL_CHAPTER6A_AMOUNT=%s
80GG_SELECTED_AMOUNT=%s
80GG_INCLUDED_IN_CHAPTER6A=%s
TOTAL_CHAPTER6A_DEDUCTIONS_SO_FAR=%s""",
                        section_80gg, selected_amt, other_80, running_total + selected_amt
                    )
                running_total += selected_amt

            _logger.info(
                "--------------------------------------\n"
                "Category               : %s\n"
                "Description            : %s\n"
                "Declared Amount        : ₹%s\n"
                "Approved Amount        : ₹%s\n"
                "Usable Amount          : ₹%s\n"
                "is_regime_permitted    : %s\n"
                "is_active              : %s\n"
                "Selected Amount        : ₹%s\n"
                "Reason Included/Skipped: %s\n"
                "Running Total Chapter VI-A: ₹%s",
                cat, line.description, line.declared_amount, line.approved_amount,
                line.usable_amount, is_permitted, is_act, selected_amt, reason, running_total
            )

        if not has_80d_line and decl and regime_code == 'old':
            hdr_self = float(getattr(decl, 'decl_80d_self', 0.0) or 0.0)
            hdr_par = float(getattr(decl, 'decl_80d_parents', 0.0) or 0.0)
            hdr_prev = float(getattr(decl, 'decl_80d_preventive', 0.0) or 0.0)
            if hdr_self + hdr_par + hdr_prev > 0.0:
                self_sr = bool(getattr(decl, 'decl_80d_self_is_senior', False) or (employee and (getattr(employee, 'is_senior_citizen', False) or getattr(employee, 'hds_in_decl_80d_self_is_senior', False))))
                par_sr = bool(getattr(decl, 'decl_80d_parents_is_senior', False) or (employee and getattr(employee, 'hds_in_decl_80d_parents_is_senior', False)))
                cap_s = tds_param_svc.get_80d_limit(is_senior=self_sr, is_parents=False, eval_date=eval_date) or 25000.0
                cap_p = tds_param_svc.get_80d_limit(is_senior=par_sr, is_parents=True, eval_date=eval_date) or 25000.0
                prev_sub = tds_param_svc.get_parameter('80D_PREVENTIVE_CHECKUP_LIMIT', eval_date=eval_date) or 5000.0
                elig_s = min(hdr_self + min(hdr_prev, prev_sub), cap_s)
                elig_p = min(hdr_par, cap_p)
                section_80d = elig_s + elig_p
                running_total += section_80d


        if not has_80g_line and section_80g > 0.0:
            other_80 += section_80g
            running_total += section_80g

        if not has_80e_line and section_80e > 0.0:
            other_80 += section_80e
            running_total += section_80e

        if not has_80cch_line and section_80cch > 0.0:
            other_80 += section_80cch
            running_total += section_80cch

        if not has_80dd_line and section_80dd > 0.0:
            running_total += section_80dd

        if not has_80gg_line and section_80gg > 0.0:
            other_80 += section_80gg
            running_total += section_80gg

        if not has_80u_line and section_80u > 0.0:
            other_80 += section_80u
            running_total += section_80u

        hdr_80ccd2 = float(getattr(decl, 'decl_80ccd2_employer_nps', 0.0) or 0.0) if decl else 0.0
        if not has_80ccd2_line and hdr_80ccd2 > 0.0:
            from .salary_projection_service import SalaryProjectionService
            from .tds_parameter_service import TdsParameterService
            from .eligibility_rule_engine_service import EligibilityRuleEngineService
            
            sal_svc = SalaryProjectionService(self.env)
            sal_res = sal_svc.project_salary(employee, financial_year, eval_date=eval_date)
            annual_b = sal_res.total_basic or 0.0
            annual_d = sal_res.total_da or 0.0
            sal_b = annual_b + annual_d
            
            emp_type = getattr(employee, 'hds_in_employer_category', getattr(employee, 'employer_type', 'private')) or 'private'
            tds_param_svc = TdsParameterService(self.env)
            nps_pct = tds_param_svc.get_employer_nps_limit(regime=regime_code, employer_type=emp_type, eval_date=eval_date)
            param_code = 'HDS_IN_TDS_NPS_LIMIT_NEW' if regime_code == 'new' else ('HDS_IN_TDS_NPS_LIMIT_OLD_GOVT' if 'govt' in str(emp_type).lower() else 'HDS_IN_TDS_NPS_LIMIT_OLD_PRIVATE')
            calc_ceiling = sal_b * (nps_pct / 100.0)
            
            elig_svc = EligibilityRuleEngineService(self.env)
            elig_res = elig_svc.evaluate_eligibility(
                '80ccd2',
                declared_amount=hdr_80ccd2,
                regime_code=regime_code,
                employer_type=emp_type,
                salary_base=sal_b,
                eval_date=eval_date
            )
            hdr_elig = elig_res.eligible_deduction
            hdr_excess = elig_res.excess_amount

            contract_obj = sal_svc._get_employee_contract(employee) if hasattr(sal_svc, '_get_employee_contract') else False
            c_id = getattr(contract_obj, 'id', 'N/A') if contract_obj else 'N/A'
            from .payroll_period_service import PayrollPeriodService
            _period_svc = PayrollPeriodService(self.env)
            _emp_periods = _period_svc.calculate_total_periods_in_fy(employee, financial_year, eval_date=eval_date) if (employee and financial_year) else 12.0
            m_b = float(getattr(contract_obj, 'basic_salary', 0.0) or 0.0) if contract_obj else (annual_b / float(_emp_periods or 12))
            m_d = float(getattr(contract_obj, 'da', 0.0) or getattr(contract_obj, 'da_amount', 0.0) or 0.0) if contract_obj else (annual_d / float(_emp_periods or 12))
            
            # Note: 80CCD(2) dedicated statutory trace is logged by declaration-level trigger in tds.employee.declaration._compute_totals()
            pass

        # Deduplicate 80C components across scalar header fields and declaration lines
        comp_vals = {
            'VPF': 0.0, 'LIC': 0.0, 'ELSS': 0.0, 'PPF': 0.0, 'NSC': 0.0,
            'SSY': 0.0, 'FD': 0.0, 'Tuition': 0.0, 'Housing Principal': 0.0, 'Other 80C': 0.0
        }

        if decl:
            is_post_proof = decl.state in ('proof_verified', 'approved')
            has_80c_lines = any(l.category == '80c' and getattr(l, 'active', True) for l in decl.declaration_line_ids)

            # Initialize comp_vals from header scalar fields only if NOT post-proof with line items
            if not (is_post_proof and has_80c_lines):
                comp_vals['PPF'] = float(getattr(decl, 'decl_80c_ppf', 0.0) or 0.0)
                comp_vals['VPF'] = float(getattr(decl, 'decl_80c_epf', 0.0) or 0.0)
                comp_vals['LIC'] = float(getattr(decl, 'decl_80c_lic', 0.0) or 0.0)
                comp_vals['ELSS'] = float(getattr(decl, 'decl_80c_elss', 0.0) or 0.0)
                comp_vals['NSC'] = float(getattr(decl, 'decl_80c_nsc', 0.0) or 0.0)
                comp_vals['SSY'] = float(getattr(decl, 'decl_80c_ssy', 0.0) or 0.0)
                comp_vals['FD'] = float(getattr(decl, 'decl_80c_fd', 0.0) or 0.0)
                comp_vals['Tuition'] = float(getattr(decl, 'decl_80c_tuition', 0.0) or 0.0)
                comp_vals['Housing Principal'] = float(getattr(decl, 'decl_80c_housing_principal', 0.0) or 0.0)
                comp_vals['Other 80C'] = float(getattr(decl, 'decl_80c_other', 0.0) or 0.0)

            for line in decl.declaration_line_ids:
                if line.category == '80c' and getattr(line, 'active', True):
                    amt_line = float(line.usable_amount or line.declared_amount or 0.0)
                    desc_l = (line.description or '').lower()

                    if is_post_proof and has_80c_lines:
                        # Post-proof adjustment phase: consume canonical line approved_amount directly
                        amt_line = float(line.approved_amount or 0.0)
                        if 'ppf' in desc_l or 'public provident' in desc_l:
                            comp_vals['PPF'] += amt_line
                        elif 'vpf' in desc_l or 'epf' in desc_l or 'provident' in desc_l:
                            comp_vals['VPF'] += amt_line
                        elif 'lic' in desc_l or 'life insurance' in desc_l:
                            comp_vals['LIC'] += amt_line
                        elif 'elss' in desc_l or 'mutual fund' in desc_l:
                            comp_vals['ELSS'] += amt_line
                        elif 'nsc' in desc_l or 'national savings' in desc_l:
                            comp_vals['NSC'] += amt_line
                        elif 'ssy' in desc_l or 'sukanya' in desc_l:
                            comp_vals['SSY'] += amt_line
                        elif 'fd' in desc_l or 'fixed deposit' in desc_l:
                            comp_vals['FD'] += amt_line
                        elif 'tuition' in desc_l or 'school' in desc_l or 'fee' in desc_l:
                            comp_vals['Tuition'] += amt_line
                        elif 'housing' in desc_l or 'principal' in desc_l or 'home loan' in desc_l:
                            comp_vals['Housing Principal'] += amt_line
                        else:
                            comp_vals['Other 80C'] += amt_line
                    else:
                        # Planning phase: deduplicate using max between header scalar and line items
                        if 'ppf' in desc_l or 'public provident' in desc_l:
                            comp_vals['PPF'] = max(comp_vals['PPF'], amt_line)
                        elif 'vpf' in desc_l or 'epf' in desc_l or 'provident' in desc_l:
                            comp_vals['VPF'] = max(comp_vals['VPF'], amt_line)
                        elif 'lic' in desc_l or 'life insurance' in desc_l:
                            comp_vals['LIC'] = max(comp_vals['LIC'], amt_line)
                        elif 'elss' in desc_l or 'mutual fund' in desc_l:
                            comp_vals['ELSS'] = max(comp_vals['ELSS'], amt_line)
                        elif 'nsc' in desc_l or 'national savings' in desc_l:
                            comp_vals['NSC'] = max(comp_vals['NSC'], amt_line)
                        elif 'ssy' in desc_l or 'sukanya' in desc_l:
                            comp_vals['SSY'] = max(comp_vals['SSY'], amt_line)
                        elif 'fd' in desc_l or 'fixed deposit' in desc_l:
                            comp_vals['FD'] = max(comp_vals['FD'], amt_line)
                        elif 'tuition' in desc_l or 'school' in desc_l or 'fee' in desc_l:
                            comp_vals['Tuition'] = max(comp_vals['Tuition'], amt_line)
                        elif 'housing' in desc_l or 'principal' in desc_l or 'home loan' in desc_l:
                            comp_vals['Housing Principal'] = max(comp_vals['Housing Principal'], amt_line)
                        else:
                            comp_vals['Other 80C'] = max(comp_vals['Other 80C'], amt_line)

        unique_80c_aggregate = sum(comp_vals.values())

        _logger.warning("""[TDS_DEBUG_TRACE][80C_AGGREGATION_TRACE]
stage=POST_80C_AGGREGATION
employee_id=%s
declaration_state=%s
is_post_proof=%s
has_80c_lines=%s
components_aggregated=%s
unique_80c_aggregate=%s""",
            employee.id if employee else 'N/A',
            decl.state if decl else 'N/A',
            is_post_proof if decl else False,
            has_80c_lines if decl else False,
            comp_vals,
            unique_80c_aggregate
        )

        raw_80c = unique_80c_aggregate
        section_80c = min(raw_80c, max_80c)
        section_80ccd1b = min(raw_80ccd1b, max_80ccd1b)

        components_dict = {k: v for k, v in comp_vals.items() if v > 0}

        lifecycle_logger.log_80c_statutory_trace(
            employee_name=employee.name if employee else 'N/A',
            employee_id=employee.id if employee else 'N/A',
            financial_year_name=financial_year.name if financial_year else 'N/A',
            declaration_id=decl.id if decl else 'N/A',
            declaration_state=decl.state if decl else 'draft',
            components_dict=components_dict,
            statutory_cap=max_80c,
            approved_amount=decl.total_approved_amount if decl else 0.0,
            usable_amount=section_80c
        )

        declared_80eea = float(getattr(decl, 'decl_80eea_interest_amount', 0.0) or 0.0) if decl else 0.0
        total_home_loan_interest = float(getattr(decl, 'decl_24b_self_interest', 0.0) or 0.0) if decl else 0.0
        residual_after_24b = max(total_home_loan_interest - final_24b, 0.0)

        total_chapter_6a = (
            section_80c + section_80ccd1b + section_80d +
            section_80dd + section_80tta_80ttb + section_80eea + other_80
        )

        _logger.warning("""[TDS_DEBUG_TRACE][80EEA_PRE_CHAPTER6A_AGGREGATION]
TOTAL_INTEREST=%s
FINAL_24B_AMOUNT=%s
RESIDUAL_INTEREST_FOR_80EEA=%s
80EEA_DECLARED_AMOUNT=%s
80EEA_STATUTORY_CAP=150000.00
80EEA_ELIGIBILITY_RESULT=%s
FINAL_80EEA_AMOUNT=%s
FINAL_CHAPTER_VIA_80EEA=%s
declared_80eea=%s
final_24b=%s
total_home_loan_interest=%s
residual_after_24b=%s
calculated_80eea=%s
final_80eea=%s
chapter_via_total=%s""",
            f"INR {total_home_loan_interest:,.2f}",
            f"INR {final_24b:,.2f}",
            f"INR {residual_after_24b:,.2f}",
            f"INR {declared_80eea:,.2f}",
            "ELIGIBLE" if section_80eea > 0 else ("INELIGIBLE" if not has_80eea_decl else "ZERO_RESIDUAL"),
            f"INR {section_80eea:,.2f}",
            f"INR {section_80eea:,.2f}",
            declared_80eea,
            final_24b,
            total_home_loan_interest,
            residual_after_24b,
            section_80eea,
            section_80eea,
            total_chapter_6a
        )

        std_ded_val = 50000.0 if regime_code == 'old' else 75000.0
        tot_allowable_ded = std_ded_val + total_chapter_6a
        # Taxable income projection for debug log
        from .salary_projection_service import SalaryProjectionService
        sal_proj = SalaryProjectionService(self.env)
        sal_r = sal_proj.project_salary(employee, financial_year, eval_date=eval_date)
        gti_val = (getattr(sal_r, 'total_projected_current_salary', 0.0) or 0.0) if sal_r else 0.0
        taxable_inc_val = max(0.0, gti_val - tot_allowable_ded)

        debug_80c_trace = f"""
========================================================
80C DEBUG
========================================================
Employee                 : {employee.name if employee else 'N/A'} (ID: {employee.id if employee else 'N/A'})
Declaration              : {decl.id if decl else 'None'}
State                    : {decl.state if decl else 'no_declaration'}

VPF                      : ₹{comp_vals['VPF']:,.2f}
LIC                      : ₹{comp_vals['LIC']:,.2f}
ELSS                     : ₹{comp_vals['ELSS']:,.2f}
PPF                      : ₹{comp_vals['PPF']:,.2f}
NSC                      : ₹{comp_vals['NSC']:,.2f}
SSY                      : ₹{comp_vals['SSY']:,.2f}
FD                       : ₹{comp_vals['FD']:,.2f}
Tuition                  : ₹{comp_vals['Tuition']:,.2f}
Housing Principal        : ₹{comp_vals['Housing Principal']:,.2f}
Other 80C                : ₹{comp_vals['Other 80C']:,.2f}

Unique 80C Aggregate     : ₹{unique_80c_aggregate:,.2f}
80C Statutory Cap        : ₹{max_80c:,.2f}
Final 80C Eligible       : ₹{section_80c:,.2f}
Final 80C Usable         : ₹{section_80c:,.2f}

Chapter VI-A Total       : ₹{total_chapter_6a:,.2f}
Total Allowable Deductions: ₹{tot_allowable_ded:,.2f}
Taxable Income           : ₹{taxable_inc_val:,.2f}
========================================================
"""
        _logger.warning(debug_80c_trace)

        # ── 80C DIAGNOSTIC TRACE STAGES ───────────────────────────────────
        decl_id = decl.id if decl else 'N/A'
        emp_id = employee.id if employee else 'N/A'

        epf_val = float(getattr(decl, 'decl_80c_epf', 0.0) or 0.0) if decl else 0.0
        lic_val = float(getattr(decl, 'decl_80c_lic', 0.0) or 0.0) if decl else 0.0
        elss_val = float(getattr(decl, 'decl_80c_elss', 0.0) or 0.0) if decl else 0.0
        tuition_val = float(getattr(decl, 'decl_80c_tuition', 0.0) or 0.0) if decl else 0.0
        ppf_val = float(getattr(decl, 'decl_80c_ppf', 0.0) or 0.0) if decl else 0.0
        ssy_val = float(getattr(decl, 'decl_80c_ssy', 0.0) or 0.0) if decl else 0.0
        fd_val = float(getattr(decl, 'decl_80c_fd', 0.0) or 0.0) if decl else 0.0
        nsc_val = float(getattr(decl, 'decl_80c_nsc', 0.0) or 0.0) if decl else 0.0
        housing_val = float(getattr(decl, 'decl_80c_housing_principal', 0.0) or 0.0) if decl else 0.0
        other_val = float(getattr(decl, 'decl_80c_other', 0.0) or 0.0) if decl else 0.0
        total_decl_val = float(getattr(decl, 'total_80c_declared', 0.0) or unique_80c_aggregate) if decl else unique_80c_aggregate

        _logger.warning("""[TDS_DEBUG_TRACE][80C_SOURCE]
declaration_id=%s
employee_id=%s
decl_80c_epf=%s
decl_80c_lic=%s
decl_80c_elss=%s
decl_80c_tuition=%s
decl_80c_ppf=%s
decl_80c_ssy=%s
decl_80c_fd=%s
decl_80c_nsc=%s
decl_80c_housing_principal=%s
decl_80c_other=%s
total_80c_declared=%s""",
            decl_id, emp_id, epf_val, lic_val, elss_val, tuition_val,
            ppf_val, ssy_val, fd_val, nsc_val, housing_val, other_val, total_decl_val
        )

        if decl and hasattr(decl, 'declaration_line_ids') and decl.declaration_line_ids:
            for l in decl.declaration_line_ids:
                if l.category == '80c':
                    _logger.warning("""[TDS_DEBUG_TRACE][80C_LINES]
line_id=%s
description=%s
declared_amount=%s
eligible_amount=%s
approved_amount=%s
usable_amount=%s""",
                        l.id, l.description or 'N/A', l.declared_amount,
                        l.eligible_amount, l.approved_amount, l.usable_amount
                    )
        else:
            _logger.warning("""[TDS_DEBUG_TRACE][80C_LINES]
line_id=N/A
description=No 80C line items
declared_amount=0.0
eligible_amount=0.0
approved_amount=0.0
usable_amount=0.0""")

        _logger.warning("""[TDS_DEBUG_TRACE][80C_ENGINE_INPUT]
claimed_amount=%s
source_field=unique_80c_aggregate
source_value=%s""",
            unique_80c_aggregate, unique_80c_aggregate
        )

        _logger.warning("""[TDS_DEBUG_TRACE][80C_ENGINE_RESULT]
claimed=%s
eligible=%s
allowed=%s""",
            unique_80c_aggregate, section_80c, section_80c
        )

        _logger.warning("""[TDS_DEBUG_TRACE] 80C_RESULT
claimed=%s
eligible=%s
allowed=%s""", unique_80c_aggregate, section_80c, section_80c)

        _logger.warning("""[TDS_DEBUG_TRACE] CHAPTER_VIA_AGGREGATION
80C=%s
80CCD_1B=%s
80CCD_2=0.0
80D=%s
80E=%s
80G=%s
80DD=%s
80U=%s
80CCH=%s
80TTA=%s
80TTB=0.0
other_80=%s
chapter_via_total=%s""",
            section_80c, section_80ccd1b, section_80d, section_80e, section_80g, section_80dd,
            section_80u, section_80cch, section_80tta_80ttb, other_80, total_chapter_6a
        )

        _logger.warning("""[TDS_RECALC_TRACE][CHAPTER_6A]
80C=%s
80CCD1B=%s
80D=%s
80DD=%s
80E=%s
80G=%s
80GG=%s
80TTA_TTB=%s
80EEA=%s
other_80=%s
total_chapter_6a=%s""",
            int(section_80c) if section_80c == int(section_80c) else section_80c,
            int(section_80ccd1b) if section_80ccd1b == int(section_80ccd1b) else section_80ccd1b,
            int(section_80d) if section_80d == int(section_80d) else section_80d,
            int(section_80dd) if section_80dd == int(section_80dd) else section_80dd,
            int(section_80e) if section_80e == int(section_80e) else section_80e,
            int(section_80g) if section_80g == int(section_80g) else section_80g,
            int(section_80gg) if section_80gg == int(section_80gg) else section_80gg,
            int(section_80tta_80ttb) if section_80tta_80ttb == int(section_80tta_80ttb) else section_80tta_80ttb,
            int(section_80eea) if section_80eea == int(section_80eea) else section_80eea,
            int(other_80) if other_80 == int(other_80) else other_80,
            int(total_chapter_6a) if total_chapter_6a == int(total_chapter_6a) else total_chapter_6a
        )

        _logger.warning("""[FORENSIC_TDS_TRACE]
step=CHAPTER_6A_DEDUCTIONS
eval_date=%s
eval_month=%s
input=employee_id:%s, regime:%s, decl_state:%s
output=section_80c:INR %s, section_80ccd1b:INR %s, section_80d:INR %s, section_80e:INR %s, section_80g:INR %s, total_chapter_6a:INR %s
source_method=Chapter6ADeductionService.calculate_chapter_6a_deductions
branch_used=%s""",
            eval_date,
            eval_date.strftime('%B') if hasattr(eval_date, 'strftime') else 'N/A',
            employee.id if employee else 'N/A',
            regime_code.upper(),
            decl.state if decl else 'no_declaration',
            f"{section_80c:,.2f}",
            f"{section_80ccd1b:,.2f}",
            f"{section_80d:,.2f}",
            f"{section_80e:,.2f}",
            f"{section_80g:,.2f}",
            f"{total_chapter_6a:,.2f}",
            f"{'OLD_REGIME_CHAPTER_6A' if regime_code == 'old' else 'NEW_REGIME_CHAPTER_6A_PROHIBITED'} (Decl State: {decl.state if decl else 'N/A'})"
        )

        return Chapter6aDeductionResult(
            section_80c=section_80c,
            section_80ccd1b=section_80ccd1b,
            section_80d=section_80d,
            section_80dd=section_80dd,
            section_80tta_80ttb=section_80tta_80ttb,
            section_80eea=section_80eea,
            section_80g=section_80g,
            section_80e=section_80e,
            section_80u=section_80u,
            section_80cch=section_80cch,
            section_80gg=section_80gg,
            other_80_deductions=other_80,
            total_chapter_6a=total_chapter_6a
        )
