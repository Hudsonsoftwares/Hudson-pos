# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import fields
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError
from ..base import BaseStatutoryService
from .standard_deduction_service import StandardDeductionService
from .professional_tax_deduction_service import ProfessionalTaxDeductionService
from .chapter6a_deduction_service import Chapter6aDeductionService
from .home_loan_deduction_service import HomeLoanDeductionService
from .section10_hra_exemption_service import Section10HraExemptionService
from .employee_tax_declaration_validation_service import EmployeeTaxDeclarationValidationService

_logger = logging.getLogger(__name__)


class DeductionSummary:
    """
    Data Transfer Object (DTO) holding the complete statutory deduction summary.
    """
    def __init__(self, employee_id, financial_year_id, regime_code, standard_deduction,
                 chapter_6a_deductions, hra_exemption, home_loan_interest_24b,
                 section_80eea_deduction, employer_nps_80ccd2, family_pension_57iia,
                 other_approved_deductions, total_allowable_deductions, lta_exemption=0.0,
                 professional_tax_16iii=0.0):
        self.employee_id = employee_id
        self.financial_year_id = financial_year_id
        self.regime_code = regime_code
        self.standard_deduction = standard_deduction
        self.professional_tax_16iii = float(professional_tax_16iii or 0.0)
        self.chapter_6a_deductions = chapter_6a_deductions
        self.hra_exemption = hra_exemption
        self.lta_exemption = lta_exemption
        self.home_loan_interest_24b = home_loan_interest_24b
        self.section_80eea_deduction = section_80eea_deduction
        self.employer_nps_80ccd2 = employer_nps_80ccd2
        self.family_pension_57iia = family_pension_57iia
        self.other_approved_deductions = other_approved_deductions
        self.total_allowable_deductions = total_allowable_deductions

    @property
    def total_approved_deductions(self):
        return self.total_allowable_deductions

    @property
    def total_chapter_6a(self):
        if hasattr(self.chapter_6a_deductions, 'total_chapter_6a'):
            return self.chapter_6a_deductions.total_chapter_6a
        if hasattr(self.chapter_6a_deductions, 'total_chapter_6a_deductions'):
            return self.chapter_6a_deductions.total_chapter_6a_deductions
        if isinstance(self.chapter_6a_deductions, (int, float)):
            return float(self.chapter_6a_deductions)
        return 0.0




class DeductionCalculationService(BaseStatutoryService):
    """
    Phase 5 Master Orchestration Service: Deduction Calculation Service.
    Determines total allowable statutory deductions based on employee tax regime.
    - Old Regime: Standard Deduction (₹50k) + Chapter VI-A (80C, 80CCD1B, 80D, 80DD, 80TTA/TTB) + HRA Exemption + LTA Exemption + Home Loan 24(b) + 80EEA.
    - New Regime: Standard Deduction (₹75k for FY 2025-26 under Finance Act 2025) + Employer NPS 80CCD(2) + Family Pension 57(iia). Prohibits Old Regime deductions.
    """

    def calculate_deductions(self, employee, financial_year, regime_context=None, eval_date=None, gross_salary_income=None, payslip=None, annual_projection=None):
        """
        Master method for calculating statutory deductions.

        :param employee: hr.employee record
        :param financial_year: tds.financial.year record
        :param regime_context: RegimeCalculationContext DTO (optional)
        :param eval_date: Date (optional)
        :param gross_salary_income: float (Gross Salary Income projected in Phase 4)
        :param payslip: hr.payslip record (optional)
        :param annual_projection: AnnualIncomeProjectionResult (optional)
        :return: DeductionSummary
        """
        if not employee:
            raise ValidationError("Deduction Calculation Error: Employee record is required.")
        if not financial_year:
            raise ValidationError("Deduction Calculation Error: Financial Year record is required.")

        eval_date = eval_date or fields.Date.today()
        regime_code = (regime_context.regime_code if regime_context else 'new').lower()

        # Resolve salary income for Section 16(ia) standard deduction cap.
        # Section 16(ia) standard deduction is strictly deductible from income under the head 'Salaries',
        # and CANNOT be set off against other heads of income (e.g. interest, house property).
        if gross_salary_income is not None:
            gross_payroll = float(gross_salary_income)
        elif regime_context and hasattr(regime_context, 'gross_salary_income') and regime_context.gross_salary_income is not None:
            gross_payroll = float(regime_context.gross_salary_income)
        else:
            gross_payroll = float(regime_context.gross_total_income) if regime_context else 0.0

        # 1. Calculate Standard Deduction via StandardDeductionService
        std_svc = StandardDeductionService(self.env)
        standard_deduction = std_svc.calculate_standard_deduction(
            regime_code=regime_code,
            gross_payroll_income=gross_payroll,
            eval_date=eval_date
        )

        # 1b. Calculate Section 16(iii) Professional Tax Deduction via ProfessionalTaxDeductionService
        pt_ded_svc = ProfessionalTaxDeductionService(self.env)
        pt_ded_res = pt_ded_svc.calculate_pt_deduction(
            employee=employee,
            financial_year=financial_year,
            regime_code=regime_code,
            eval_date=eval_date,
            gross_payroll_income=gross_payroll,
            payslip=payslip,
            annual_projection=annual_projection
        )
        raw_pt_16iii = pt_ded_res.allowed_pt_deduction

        # 2. Calculate Chapter VI-A Deductions via Chapter6aDeductionService
        c6a_svc = Chapter6aDeductionService(self.env)
        c6a_res = c6a_svc.calculate_chapter_6a_deductions(
            employee=employee,
            financial_year=financial_year,
            regime_code=regime_code,
            eval_date=eval_date
        )
        total_chapter_6a = c6a_res.total_chapter_6a

        # 3. Calculate Home Loan Deductions via HomeLoanDeductionService
        hl_svc = HomeLoanDeductionService(self.env)
        hl_res = hl_svc.calculate_home_loan_deductions(
            employee=employee,
            financial_year=financial_year,
            regime_code=regime_code,
            eval_date=eval_date
        )
        home_loan_24b = hl_res.section_24b_self_interest
        section_80eea = hl_res.section_80eea_interest

        # 4. Section 10 Exemptions (HRA, LTA) and Employer NPS / Family Pension resolution from declaration
        hra_exemption = 0.0
        lta_exemption = 0.0
        employer_nps_80ccd2 = 0.0
        family_pension_57iia = 0.0
        other_approved_deductions = 0.0

        decl = self.env['tds.employee.declaration'].sudo().search([
            ('employee_id', '=', employee.id),
            ('financial_year_id', '=', financial_year.id)
        ], limit=1)

        if decl:
            val_svc = EmployeeTaxDeclarationValidationService(self.env)
            val_svc.validate_declaration(decl, eval_date=eval_date)

            for line in decl.declaration_line_ids:
                if not line.is_regime_permitted:
                    continue
                cat = line.category
                amt = line.usable_amount

                if regime_code == 'old':
                    if cat == 'hra':
                        # Section 10(13A) HRA Exemption least-of-three calculation
                        from .salary_projection_service import SalaryProjectionService
                        sal_proj_svc = SalaryProjectionService(self.env)
                        sal_res = sal_proj_svc.project_salary(employee, financial_year, eval_date=eval_date)

                        annual_basic_salary = (sal_res.total_basic or 0.0) + (sal_res.total_da or 0.0)
                        actual_hra_received = sal_res.total_hra or 0.0
                        annual_rent_paid = float(
                            line.usable_amount if line and line.usable_amount > 0.0
                            else (decl.decl_hra_annual_rent or 0.0)
                        )
                        is_metro = bool(decl.decl_hra_is_metro)

                        # Mandatory input availability checks
                        missing_inputs = []
                        if annual_basic_salary <= 0.0: missing_inputs.append("Annual Basic Salary (+ DA)")
                        if actual_hra_received <= 0.0: missing_inputs.append("Actual HRA Received")
                        if annual_rent_paid <= 0.0: missing_inputs.append("Annual Rent Paid")

                        if missing_inputs:
                            _logger.warning(
                                "[HRA EXEMPTION WARNING] Mandatory HRA calculation input(s) unavailable or zero: %s for Employee '%s'. HRA Exemption evaluated as ₹0.00.",
                                ", ".join(missing_inputs), employee.name if employee else "N/A"
                            )

                        contract = sal_proj_svc._get_employee_contract(employee)
                        c_hra = float(getattr(contract, 'hra', 0.0) or getattr(contract, 'hra_amount', 0.0) or 0.0)
                        
                        _logger.warning("""[10_13A_HRA_SOURCE_TRACE]
monthly_hra=%s
projection_month=%s
months_elapsed=%s
months_remaining=%s
annual_projected_hra=%s
hra_value_passed_to_10_13A=%s
source_method=SalaryProjectionService.project_salary -> DeductionCalculationService""",
                            f"INR {c_hra:,.2f}",
                            sal_res.months_remaining if hasattr(sal_res, 'months_remaining') else 12,
                            sal_res.months_elapsed if hasattr(sal_res, 'months_elapsed') else 1,
                            sal_res.months_remaining if hasattr(sal_res, 'months_remaining') else 12,
                            f"INR {sal_res.total_hra:,.2f}",
                            f"INR {actual_hra_received:,.2f}"
                        )

                        hra_svc = Section10HraExemptionService(self.env)
                        hra_res = hra_svc.calculate_exemption(
                            annual_rent_paid=annual_rent_paid,
                            actual_hra_received=actual_hra_received,
                            annual_basic_salary=annual_basic_salary,
                            is_metro=is_metro,
                            eval_date=eval_date,
                            employee=employee,
                            financial_year=financial_year,
                            declaration=decl,
                            declaration_line=line,
                            regime_code=regime_code,
                            annual_basic_component=sal_res.total_basic,
                            annual_da_component=sal_res.total_da
                        )
                        hra_exemption += hra_res.exempt_amount

                        decl_rent = float(getattr(decl, 'decl_hra_annual_rent', 0.0) or (line.declared_amount if line else 0.0) or 0.0)
                        ver_rent = float(getattr(line, 'verified_amount', 0.0) or 0.0) if line else 0.0
                        appr_rent = float(getattr(line, 'tax_firm_approved_amount', 0.0) or getattr(line, 'approved_amount', 0.0) or 0.0) if line else 0.0
                        usable_rent = float(line.usable_amount if line else 0.0)
                        rent_source = "DECLARATION_LINE" if (line and line.usable_amount > 0.0) else "HEADER_DECLARATION"

                        _logger.warning("""[HRA_SOURCE_SELECTION]
declared_rent=%s
verified_rent=%s
approved_rent=%s
usable_amount=%s
selected_rent=%s
selected_source=%s""",
                            f"INR {decl_rent:,.2f}",
                            f"INR {ver_rent:,.2f}",
                            f"INR {appr_rent:,.2f}",
                            f"INR {usable_rent:,.2f}",
                            f"INR {annual_rent_paid:,.2f}",
                            rent_source
                        )

                        _logger.warning("""[SECTION_10_13A_TRACE]
actual_hra=%s
basic_plus_da=%s
formula_1=%s
formula_2=%s
formula_3=%s
final_hra_exemption=%s""",
                            f"INR {actual_hra_received:,.2f}",
                            f"INR {annual_basic_salary:,.2f}",
                            f"INR {hra_res.actual_hra_received:,.2f}",
                            f"INR {hra_res.rent_excess_basic:,.2f}",
                            f"INR {hra_res.basic_pct_limit:,.2f}",
                            f"INR {hra_res.exempt_amount:,.2f}"
                        )
                    elif cat == 'lta':
                        # Section 10(5) LTA Exemption calculation
                        from .salary_projection_service import SalaryProjectionService
                        from .section10_lta_exemption_service import Section10LtaExemptionService
                        sal_proj_svc = SalaryProjectionService(self.env)
                        sal_res = sal_proj_svc.project_salary(employee, financial_year, eval_date=eval_date)
                        actual_lta_received = getattr(sal_res, 'total_lta', 0.0) or 0.0
                        declared_fare = float(line.usable_amount if (line and line.usable_amount > 0.0) else (line.declared_amount if line else 0.0))
                        if declared_fare == 0.0 and decl:
                            declared_fare = float(getattr(decl, 'decl_lta_declared_fare', 0.0) or 0.0)

                        lta_svc = Section10LtaExemptionService(self.env)
                        lta_res = lta_svc.validate_and_calculate(
                            employee=employee,
                            declared_fare=declared_fare,
                            actual_lta_received=actual_lta_received,
                            regime_code=regime_code,
                            declaration=decl,
                            eval_date=eval_date
                        )
                        lta_exemption += lta_res.exempt_amount
                        _logger.warning("""[SECTION_10_5_LTA_TRACE]
employee=%s
declared_fare=%s
actual_lta_received=%s
eligible_travel_fare=%s
statutory_fare_ceiling=%s
final_lta_exemption=%s
eligibility_status=%s
block_period=%s
remarks=%s""",
                            employee.name if employee else 'N/A',
                            f"INR {declared_fare:,.2f}",
                            f"INR {actual_lta_received:,.2f}",
                            f"INR {lta_res.eligible_travel_fare:,.2f}",
                            f"INR {lta_res.statutory_fare_ceiling:,.2f}",
                            f"INR {lta_res.exempt_amount:,.2f}",
                            lta_res.eligibility_status,
                            lta_res.block_period,
                            lta_res.remarks
                        )
                    elif cat == '80ccd2':
                        employer_nps_80ccd2 += amt
                    elif cat == '57iia':
                        family_pension_57iia = max(family_pension_57iia, amt)
                    elif cat not in ('80c', 'nps_employee', '80ccd1b', '80d_self', '80d_parents', '80d_preventive', '80tta', '80ttb', '80dd', '80u', '80g', '80e', '80gg', '24b', '80eea', '80cch', 'lta', 'hra'):
                        other_approved_deductions += amt
                else:
                    # New Regime
                    if cat == '80ccd2':
                        employer_nps_80ccd2 += amt
                    elif cat == '57iia':
                        family_pension_57iia = max(family_pension_57iia, amt)
                    elif cat == '80cch':
                        is_agnipath = bool(getattr(decl, 'hds_in_is_agnipath', False) or getattr(employee, 'hds_in_is_agnipath', False))
                        if is_agnipath:
                            other_approved_deductions += amt
                            if c6a_res and hasattr(c6a_res, 'section_80cch'):
                                c6a_res.section_80cch = amt

            # Safe Fallback for Section 10(5) LTA Exemption if child line was absent in declaration_line_ids
            if regime_code == 'old' and lta_exemption == 0.0 and decl and getattr(decl, 'decl_lta_declared_fare', 0.0) > 0.0:
                from .salary_projection_service import SalaryProjectionService
                from .section10_lta_exemption_service import Section10LtaExemptionService
                sal_proj_svc = SalaryProjectionService(self.env)
                sal_res = sal_proj_svc.project_salary(employee, financial_year, eval_date=eval_date)
                actual_lta_received = getattr(sal_res, 'total_lta', 0.0) or 0.0
                declared_fare = float(getattr(decl, 'decl_lta_declared_fare', 0.0) or 0.0)

                lta_svc = Section10LtaExemptionService(self.env)
                lta_res = lta_svc.validate_and_calculate(
                    employee=employee,
                    declared_fare=declared_fare,
                    actual_lta_received=actual_lta_received,
                    regime_code=regime_code,
                    declaration=decl,
                    eval_date=eval_date
                )
                lta_exemption = lta_res.exempt_amount
                _logger.warning("""[SECTION_10_5_LTA_TRACE] (HEADER_FALLBACK)
employee=%s
declared_fare=%s
actual_lta_received=%s
eligible_travel_fare=%s
statutory_fare_ceiling=%s
final_lta_exemption=%s
eligibility_status=%s
block_period=%s
remarks=%s""",
                    employee.name if employee else 'N/A',
                    f"INR {declared_fare:,.2f}",
                    f"INR {actual_lta_received:,.2f}",
                    f"INR {lta_res.eligible_travel_fare:,.2f}",
                    f"INR {lta_res.statutory_fare_ceiling:,.2f}",
                    f"INR {lta_res.exempt_amount:,.2f}",
                    lta_res.eligibility_status,
                    lta_res.block_period,
                    lta_res.remarks
                )

            # Safe Fallback for Section 80CCH Agniveer Corpus Fund under New Regime if child line was absent in declaration_line_ids
            if regime_code == 'new' and decl:
                cch_line_amt = sum(l.usable_amount for l in decl.declaration_line_ids if l.category == '80cch' and getattr(l, 'active', True))
                is_agnipath = bool(getattr(decl, 'hds_in_is_agnipath', False) or getattr(employee, 'hds_in_is_agnipath', False))
                header_cch_decl = float(getattr(decl, 'decl_80cch_agniveer', 0.0) or 0.0)
                header_cch_appr = float(getattr(decl, 'decl_80cch_approved_amount', 0.0) or 0.0)
                if cch_line_amt == 0.0 and is_agnipath and (header_cch_decl > 0.0 or header_cch_appr > 0.0):
                    from .section_80cch_deduction_service import Section80CCHDeductionService
                    cch_svc = Section80CCHDeductionService(self.env)
                    cch_res = cch_svc.validate_and_trace(
                        decl,
                        eval_date=eval_date,
                        regime_code=regime_code,
                        employee=employee,
                        financial_year=financial_year
                    )
                    if cch_res and cch_res.usable_amount > 0.0:
                        other_approved_deductions += cch_res.usable_amount
                        if c6a_res and hasattr(c6a_res, 'section_80cch'):
                            c6a_res.section_80cch = cch_res.usable_amount
                        _logger.warning("""[SECTION_80CCH_NEW_REGIME_TRACE] (HEADER_FALLBACK)
employee=%s
declared_80cch=%s
approved_80cch=%s
usable_amount=%s
status=%s
remarks=%s""",
                            employee.name if employee else 'N/A',
                            f"INR {header_cch_decl:,.2f}",
                            f"INR {header_cch_appr:,.2f}",
                            f"INR {cch_res.usable_amount:,.2f}",
                            cch_res.eligibility_status if hasattr(cch_res, 'eligibility_status') else getattr(cch_res, 'status', 'N/A'),
                            cch_res.remarks
                        )

        # Section 80CCD(2) Employer NPS statutory ceiling enforcement (14% new regime / 10% or 14% old regime)
        claimed_nps = float(decl.decl_80ccd2_employer_nps or 0.0) if (decl and getattr(decl, 'decl_80ccd2_employer_nps', 0.0)) else employer_nps_80ccd2

        if claimed_nps > 0.0:
            from .tds_parameter_service import TdsParameterService
            tds_param_svc = TdsParameterService(self.env)
            emp_type = getattr(employee, 'hds_in_employer_category', getattr(employee, 'employer_type', 'private')) or 'private'
            nps_pct = tds_param_svc.get_employer_nps_limit(regime=regime_code, employer_type=emp_type, eval_date=eval_date, as_decimal=False) or (14.0 if regime_code == 'new' else 10.0)
            from .salary_projection_service import SalaryProjectionService
            sal_proj_svc = SalaryProjectionService(self.env)
            sal_res = sal_proj_svc.project_salary(employee, financial_year, eval_date=eval_date)
            salary_base = (sal_res.total_basic or 0.0) + (sal_res.total_da or 0.0)
            nps_cap = round(salary_base * (nps_pct / 100.0), 2)
            employer_nps_80ccd2 = min(claimed_nps, nps_cap)
            _logger.warning("""[SECTION_80CCD2_STATUTORY_CAP]
employee=%s
declared_nps=%s
salary_base=%s
nps_percentage=%s
calculated_cap=%s
eligible_80ccd2=%s""",
                employee.name if employee else 'N/A',
                f"INR {claimed_nps:,.2f}",
                f"INR {salary_base:,.2f}",
                f"{nps_pct}%",
                f"INR {nps_cap:,.2f}",
                f"INR {employer_nps_80ccd2:,.2f}"
            )
        else:
            employer_nps_80ccd2 = 0.0

        # Statutory Section 16 Rules:
        # Standard deduction Section 16(ia) and Professional Tax Section 16(iii) apply strictly
        # against salary chargeable under 'Salaries' (gross salary minus Section 10 exemptions like HRA and LTA).
        net_salary_available = max(0.0, gross_payroll - hra_exemption - lta_exemption)
        standard_deduction = min(standard_deduction, net_salary_available)
        net_salary_after_std = max(0.0, net_salary_available - standard_deduction)
        professional_tax_16iii = min(raw_pt_16iii, net_salary_after_std) if regime_code == 'old' else 0.0

        if regime_code == 'old':
            total_allowable_deductions = (
                standard_deduction + professional_tax_16iii + total_chapter_6a + hra_exemption + lta_exemption +
                home_loan_24b + employer_nps_80ccd2 +
                other_approved_deductions
            )
        else:
            total_allowable_deductions = (
                standard_deduction + employer_nps_80ccd2 +
                other_approved_deductions
            )

        _logger.info(
            "[TDS TRACE] Phase: Deduction Calculation | Service: DeductionCalculationService | Record ID: %s | Employee: %s | FY: %s | Field: total_allowable_deductions | Old Value: N/A | New Value: ₹%s | Target Model: hr.payslip.line | DB Read: True | Calculation Result: StdDeduction=₹%s, PT_16iii=₹%s, Chapter6A=₹%s, HRAExemption=₹%s, LTAExemption=₹%s, HomeLoan24b=₹%s, Total=₹%s (Decl State: %s)",
            decl.id if decl else 'N/A', employee.name if employee else 'N/A', financial_year.name if financial_year else 'N/A',
            total_allowable_deductions, standard_deduction, professional_tax_16iii, total_chapter_6a, hra_exemption, lta_exemption, home_loan_24b, total_allowable_deductions,
            decl.state if decl else 'no_declaration'
        )

        other_deductions_total = hra_exemption + lta_exemption + home_loan_24b + employer_nps_80ccd2 + other_approved_deductions + professional_tax_16iii

        _logger.warning("""[TDS_DEBUG_TRACE] TOTAL_DEDUCTION_AGGREGATION
standard_deduction=%s
professional_tax_16iii=%s
chapter_via_total=%s
other_deductions=%s
total_deductions=%s""",
            standard_deduction, professional_tax_16iii, total_chapter_6a, other_deductions_total, total_allowable_deductions
        )

        _logger.warning("""[80E_AUDIT] DEDUCTION_AGGREGATION
standard_deduction=%s
professional_tax_16iii=%s
section_80c=%s
section_80ccd1b=%s
section_80d=%s
section_80e=%s
section_80g=%s
section_80dd=%s
section_80u=%s
section_80tta=%s
section_80ttb=%s
section_80gg=%s
hra_exemption=%s
lta_exemption=%s
home_loan_24b=%s
section_80eea=%s
employer_nps_80ccd2=%s
family_pension_57iia=%s
other_approved_deductions=%s
total_chapter_6a=%s
total_deductions=%s""",
            standard_deduction,
            professional_tax_16iii,
            getattr(c6a_res, 'section_80c', 0.0),
            getattr(c6a_res, 'section_80ccd1b', 0.0),
            getattr(c6a_res, 'section_80d', 0.0),
            getattr(c6a_res, 'section_80e', 0.0),
            getattr(c6a_res, 'section_80g', 0.0),
            getattr(c6a_res, 'section_80dd', 0.0),
            getattr(c6a_res, 'section_80u', 0.0),
            getattr(c6a_res, 'section_80tta', 0.0),
            getattr(c6a_res, 'section_80ttb', 0.0),
            getattr(c6a_res, 'section_80gg', 0.0),
            hra_exemption,
            lta_exemption,
            home_loan_24b,
            section_80eea,
            employer_nps_80ccd2,
            family_pension_57iia,
            other_approved_deductions,
            total_chapter_6a,
            total_allowable_deductions
        )

        summary_log = f"""
========================================================
DEDUCTION CALCULATION SERVICE
========================================================
Tax Regime              : {regime_code.upper()}
Standard Deduction      : ₹{standard_deduction:,.2f}
Professional Tax 16(iii): ₹{professional_tax_16iii:,.2f}
80C                     : ₹{getattr(c6a_res, 'section_80c', 0.0):,.2f}
80CCD(1B)               : ₹{getattr(c6a_res, 'section_80ccd1b', 0.0):,.2f}
80D                     : ₹{getattr(c6a_res, 'section_80d', 0.0):,.2f}
HRA Exemption          : ₹{hra_exemption:,.2f}
LTA Exemption          : ₹{lta_exemption:,.2f}
Home Loan Interest     : ₹{home_loan_24b:,.2f}
Total Deductions        : ₹{total_allowable_deductions:,.2f}

Formula:
Total = Sum of all eligible deductions
========================================================
"""
        _logger.warning("""[FORENSIC_TDS_TRACE]
step=TOTAL_DEDUCTIONS
eval_date=%s
eval_month=%s
input=employee_id:%s, regime:%s, std_deduction:INR %s, pt_16iii:INR %s, chapter_6a:INR %s, hra_exemption:INR %s, lta_exemption:INR %s, home_loan_24b:INR %s
output=total_allowable_deductions:INR %s
source_method=DeductionCalculationService.calculate_deductions
branch_used=%s""",
            eval_date,
            eval_date.strftime('%B') if hasattr(eval_date, 'strftime') else 'N/A',
            employee.id if employee else 'N/A',
            regime_code.upper(),
            f"{standard_deduction:,.2f}",
            f"{professional_tax_16iii:,.2f}",
            f"{total_chapter_6a:,.2f}",
            f"{hra_exemption:,.2f}",
            f"{lta_exemption:,.2f}",
            f"{home_loan_24b:,.2f}",
            f"{total_allowable_deductions:,.2f}",
            f"{'OLD_REGIME_TOTAL_DEDUCTIONS_AGGREGATION' if regime_code == 'old' else 'NEW_REGIME_TOTAL_DEDUCTIONS_AGGREGATION'}"
        )

        return DeductionSummary(
            employee_id=employee.id,
            financial_year_id=financial_year.id,
            regime_code=regime_code,
            standard_deduction=standard_deduction,
            chapter_6a_deductions=c6a_res,
            hra_exemption=hra_exemption,
            lta_exemption=lta_exemption,
            home_loan_interest_24b=home_loan_24b,
            section_80eea_deduction=section_80eea,
            employer_nps_80ccd2=employer_nps_80ccd2,
            family_pension_57iia=family_pension_57iia,
            other_approved_deductions=other_approved_deductions,
            total_allowable_deductions=total_allowable_deductions,
            professional_tax_16iii=professional_tax_16iii
        )
