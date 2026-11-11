# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import fields
from ..base import BaseStatutoryService
from .annual_income_projection_service import AnnualIncomeProjectionService
from .deduction_calculation_service import DeductionCalculationService
from .taxable_income_service import TaxableIncomeService
from .income_tax_slab_service import IncomeTaxSlabService
from .rebate_engine_service import RebateEngineService
from .surcharge_engine_service import SurchargeEngineService
from .health_education_cess_service import HealthEducationCessService
from .monthly_tds_distribution_service import MonthlyTDSDistributionService

_logger = logging.getLogger(__name__)


class TdsComputationResult:
    """
    Data Transfer Object (DTO) holding the complete end-to-end statutory audit trace
    produced by the Master TDS Orchestration Engine.
    """
    def __init__(self, employee_id, financial_year_id, regime_code, regime_name,
                 annual_income_projection, deduction_calculation, taxable_income,
                 income_tax_slab, rebate_engine, surcharge_engine, health_education_cess,
                 monthly_tds_distribution, calculation_run_id=None, previous_annual_tax=None):
        self.employee_id = employee_id
        self.financial_year_id = financial_year_id
        self.regime_code = regime_code
        self.regime_name = regime_name
        self.annual_income_projection = annual_income_projection
        self.deduction_calculation = deduction_calculation
        self.taxable_income = taxable_income
        self.income_tax_slab = income_tax_slab
        self.rebate_engine = rebate_engine
        self.surcharge_engine = surcharge_engine
        self.health_education_cess = health_education_cess
        self.monthly_tds_distribution = monthly_tds_distribution
        self.calculation_run_id = calculation_run_id
        self.previous_annual_tax = previous_annual_tax

    @property
    def current_month_tds(self):
        """Current month TDS withholding amount."""
        return self.monthly_tds_distribution.current_month_tds

    @property
    def total_annual_tax_liability(self):
        """Total projected annual tax liability after cess."""
        return self.health_education_cess.total_annual_tax_liability

    @property
    def total_tds_paid_so_far(self):
        """Total TDS paid so far (YTD + previous employer)."""
        return getattr(self.monthly_tds_distribution, 'total_tds_paid_so_far', 0.0)

    @property
    def ytd_tds_deducted(self):
        """Current employer YTD TDS deducted."""
        return getattr(self.monthly_tds_distribution, 'ytd_tds_deducted', 0.0)

    @property
    def prev_employer_tds(self):
        """Previous employer TDS deducted from Form 12B."""
        return getattr(self.monthly_tds_distribution, 'prev_employer_tds', 0.0)

    @property
    def remaining_annual_tax_liability(self):
        """Remaining annual tax liability to be distributed."""
        return getattr(self.monthly_tds_distribution, 'remaining_annual_tax_liability', 0.0)

    @property
    def remaining_payroll_periods(self):
        """Remaining payroll periods in FY."""
        return getattr(self.monthly_tds_distribution, 'remaining_payroll_periods', 1)

    @property
    def surcharge_before_relief(self):
        """Surcharge before marginal relief."""
        return getattr(self.surcharge_engine, 'surcharge_before_relief', getattr(self.surcharge_engine, 'surcharge_amount', 0.0))

    @property
    def marginal_relief(self):
        """Statutory marginal relief amount."""
        return getattr(self.surcharge_engine, 'marginal_relief', 0.0)

    @property
    def surcharge_amount(self):
        """Final surcharge amount after marginal relief."""
        return getattr(self.surcharge_engine, 'surcharge_amount', 0.0)

    @property
    def tax_plus_surcharge(self):
        """Tax liability plus final surcharge."""
        return getattr(self.surcharge_engine, 'tax_plus_surcharge', 0.0)

    def get_tax_summary_breakdown(self):
        """Returns the statutory TDS liability breakdown dictionary."""
        return {
            'income_tax': float(getattr(self.rebate_engine, 'tax_after_rebate', 0.0) or 0.0),
            'base_tax': float(getattr(self.income_tax_slab, 'base_tax_liability', 0.0) or 0.0),
            'rebate': float(getattr(self.rebate_engine, 'rebate_applied', 0.0) or 0.0),
            'surcharge_rate': float(getattr(self.surcharge_engine, 'surcharge_rate_pct', getattr(self.surcharge_engine, 'surcharge_rate', 0.0)) or 0.0),
            'surcharge_before_relief': self.surcharge_before_relief,
            'marginal_relief': self.marginal_relief,
            'surcharge': self.surcharge_amount,
            'surcharge_amount': self.surcharge_amount,
            'tax_plus_surcharge': self.tax_plus_surcharge,
            'cess': float(getattr(self.health_education_cess, 'cess_amount', 0.0) or 0.0),
            'total_tax_liability': float(self.total_annual_tax_liability or 0.0),
            'current_month_tds': float(self.current_month_tds or 0.0),
        }


class TdsOrchestrationEngine(BaseStatutoryService):
    """
    Phase 11 Master Orchestration Service: Master TDS Orchestration Engine.
    Executes the end-to-end statutory TDS calculation pipeline.
    """
    _hds_call_counter = 0

    def hds_in_compute_tds(self, employee, eval_date=None, payslip=None):
        """
        Master Entry Point for Payslip Statutory TDS Calculation.

        :param employee: hr.employee record
        :param eval_date: Date (optional payslip evaluation date)
        :return: TdsComputationResult
        """
        TdsOrchestrationEngine._hds_call_counter += 1
        call_idx = TdsOrchestrationEngine._hds_call_counter
        eval_date = eval_date or fields.Date.today()
        eval_month_str = eval_date.strftime('%Y%m') if hasattr(eval_date, 'strftime') else str(eval_date)[:7]
        calc_run_id = f"RUN-EMP{employee.id}-{eval_month_str}-{call_idx}"
        self.env = self.env(context=dict(self.env.context, tds_calc_run_id=calc_run_id))
        icp = self.env['ir.config_parameter'].sudo()
        get_param_fn = getattr(icp, 'get_param', None) or getattr(icp, 'get_str', None)
        debug_enabled = (get_param_fn('hudson_in_payroll.tds_debug_logging', 'False') == 'True') if get_param_fn else False
        if debug_enabled:
            import inspect
            import os
            caller_stack = inspect.stack()
            caller_func = "unknown"
            if len(caller_stack) > 1:
                caller_func = f"{caller_stack[1].function}:{caller_stack[1].lineno} ({os.path.basename(caller_stack[1].filename)})"

            _logger.warning("""[80E_BUG_TRACE] CALCULATION_START
calculation_run_id=%s
employee=%s
payslip=%s
month=%s""",
                calc_run_id,
                getattr(employee, 'name', 'N/A'),
                payslip.name if payslip else 'N/A',
                eval_date.strftime('%B %Y') if hasattr(eval_date, 'strftime') else str(eval_date)
            )

            _logger.warning("Entering TdsOrchestrationEngine for employee '%s' (Eval Date: %s, Run: %s)", getattr(employee, 'name', 'Unknown'), eval_date, calc_run_id)


        # Step 1 to 3: Annual Income Projection & Tax Regime Resolution (Phase 4 Master Service)
        if debug_enabled:
            _logger.warning("Before AnnualIncomeProjectionService")
        projection_svc = AnnualIncomeProjectionService(self.env)
        annual_projection = projection_svc.project_annual_income(employee, eval_date=eval_date, payslip=payslip)
        if debug_enabled:
            _logger.warning(
                "After AnnualIncomeProjectionService | Current Employer Salary: %s, Previous Employer Income: %s, Other Income: %s, Gross Total Income: %s",
                annual_projection.current_employer_salary,
                annual_projection.previous_employer_income.taxable_salary,
                annual_projection.other_income_aggregation.total_other_income,
                annual_projection.gross_total_income
            )

        financial_year_id = annual_projection.financial_year_id
        financial_year = self.env['tds.financial.year'].browse(financial_year_id)
        regime_code = annual_projection.regime_code
        regime_name = annual_projection.regime_name
        regime_context = annual_projection.regime_context
        gti = annual_projection.gross_total_income

        # Step 4: Regime Routing & Deduction Calculation
        if debug_enabled:
            _logger.warning("Before DeductionCalculationService")
        gross_salary_income = getattr(annual_projection, 'projected_annual_salary', None)
        if gross_salary_income is None and regime_context and hasattr(regime_context, 'gross_salary_income'):
            gross_salary_income = regime_context.gross_salary_income

        deduction_svc = DeductionCalculationService(self.env)
        deduction_calc = deduction_svc.calculate_deductions(
            employee=employee,
            financial_year=financial_year,
            regime_context=regime_context,
            eval_date=eval_date,
            gross_salary_income=gross_salary_income,
            payslip=payslip,
            annual_projection=annual_projection
        )
        if debug_enabled:
            _logger.warning(
                "After DeductionCalculationService | Standard Deduction: %s, PT 16(iii): %s, Chapter VI-A Deductions: %s, HRA Exemption: %s, Home Loan Deduction: %s, Total Deductions: %s",
                deduction_calc.standard_deduction,
                getattr(deduction_calc, 'professional_tax_16iii', 0.0),
                deduction_calc.total_chapter_6a,
                deduction_calc.hra_exemption,
                deduction_calc.home_loan_interest_24b,
                deduction_calc.total_approved_deductions
            )

        _logger.warning("""[SECTION_16III_PT_DEDUCTION_AUDIT]
calculation_run_id=%s
employee=%s
financial_year=%s
regime=%s
annual_salary=%s
standard_deduction=%s
professional_tax_16iii=%s
taxable_salary_before_chapter_6a=%s""",
            calc_run_id,
            employee.name if employee else 'N/A',
            financial_year.name if financial_year else 'N/A',
            regime_code.upper(),
            f"INR {gross_salary_income:,.2f}",
            f"INR {float(deduction_calc.standard_deduction or 0.0):,.2f}",
            f"INR {float(getattr(deduction_calc, 'professional_tax_16iii', 0.0) or 0.0):,.2f}",
            f"INR {max(0.0, gross_salary_income - (deduction_calc.standard_deduction or 0.0) - (getattr(deduction_calc, 'professional_tax_16iii', 0.0) or 0.0)):,.2f}"
        )

        _logger.warning("""[HRA_EXEMPTION_AT_ANNUAL_TAX_CALCULATION_POINT]
calculation_run_id=%s
employee_id=%s
payslip_id=%s
evaluation_date=%s
financial_year=%s
hra_exemption_received=%s
total_approved_deductions=%s
gross_total_income=%s""",
            calc_run_id,
            employee.id,
            payslip.id if payslip else 'N/A',
            eval_date.strftime('%Y-%m-%d') if hasattr(eval_date, 'strftime') else str(eval_date),
            financial_year.name if financial_year else 'N/A',
            f"INR {float(deduction_calc.hra_exemption or 0.0):,.2f}",
            f"INR {float(deduction_calc.total_approved_deductions or 0.0):,.2f}",
            f"INR {float(gti or 0.0):,.2f}"
        )

        # ── Step 4b: Section 71(3A) Aggregate House-Property Loss Cap ──────────────
        # Under Section 71(3A) (applicable to Old Regime only), the TOTAL house
        # property loss that may be set off against salary / other income in any
        # assessment year is capped at ₹2,00,000.  The engine currently applies:
        #   • Let-out property loss  → subtracted from GTI in OtherIncomeAggregationService
        #   • Self-occupied interest → subtracted as a deduction in HomeLoanDeductionService
        # Both reductions are each capped at ₹2L individually, but their COMBINED
        # impact can reach ₹4L, which is statutorily impermissible.
        # Fix: measure both components together; trim the self-occupied 24(b) deduction
        # so that (let_out_loss_absorbed + self_occ_interest_allowed) ≤ ₹2L cap.
        if regime_code == 'old':
            from .tds_parameter_service import TdsParameterService as _TdsParamSvc
            _tds_param_svc_71 = _TdsParamSvc(self.env)
            _sec_71_3a_cap = _tds_param_svc_71.get_house_property_loss_limit(eval_date=eval_date) or 200000.0

            # Let-out loss already absorbed in GTI (effective_hp_gti_impact is negative when a loss)
            _other_inc_agg = annual_projection.other_income_aggregation
            _letout_loss_absorbed = abs(min(0.0, float(getattr(_other_inc_agg, 'effective_hp_gti_impact', 0.0) or 0.0)))

            # Self-occupied interest allowed as a deduction
            _self_occ_24b = float(deduction_calc.home_loan_interest_24b or 0.0)

            _combined_hp_relief = _letout_loss_absorbed + _self_occ_24b

            if _combined_hp_relief > _sec_71_3a_cap:
                # Remaining room for self-occupied 24(b) after the let-out loss has used its share
                _allowed_self_occ_24b = max(0.0, _sec_71_3a_cap - _letout_loss_absorbed)
                _trimmed_24b = _self_occ_24b - _allowed_self_occ_24b  # amount being removed

                _logger.warning(
                    """[SECTION_71_3A_AGGREGATE_CAP_ENFORCEMENT]
regime                      : OLD
sec_71_3a_statutory_cap     : INR %s
letout_loss_absorbed_in_gti : INR %s  (already reduced GTI via OtherIncomeAggregationService)
self_occ_24b_deduction      : INR %s  (computed by HomeLoanDeductionService)
combined_hp_relief_pre_cap  : INR %s
combined_hp_relief_post_cap : INR %s
trimmed_self_occ_24b        : INR %s  (excess removed to honour aggregate cap)
final_allowed_self_occ_24b  : INR %s
decision                    : self-occupied 24(b) capped to leave room within ₹2L aggregate limit""",
                    f"{_sec_71_3a_cap:,.2f}",
                    f"{_letout_loss_absorbed:,.2f}",
                    f"{_self_occ_24b:,.2f}",
                    f"{_combined_hp_relief:,.2f}",
                    f"{_sec_71_3a_cap:,.2f}",
                    f"{_trimmed_24b:,.2f}",
                    f"{_allowed_self_occ_24b:,.2f}",
                )

                # Adjust the deduction summary in-place before it is consumed by TaxableIncomeService
                deduction_calc.home_loan_interest_24b = _allowed_self_occ_24b
                deduction_calc.total_allowable_deductions = (
                    deduction_calc.total_allowable_deductions - _trimmed_24b
                )
            else:
                _logger.warning(
                    """[SECTION_71_3A_AGGREGATE_CAP_ENFORCEMENT]
regime                      : OLD
sec_71_3a_statutory_cap     : INR %s
letout_loss_absorbed_in_gti : INR %s
self_occ_24b_deduction      : INR %s
combined_hp_relief          : INR %s
decision                    : combined HP relief is within ₹2L cap — no adjustment required""",
                    f"{_sec_71_3a_cap:,.2f}",
                    f"{_letout_loss_absorbed:,.2f}",
                    f"{_self_occ_24b:,.2f}",
                    f"{_combined_hp_relief:,.2f}",
                )

        # Step 5: Net Taxable Income Computation
        if debug_enabled:
            _logger.warning("Before TaxableIncomeService")
        taxable_svc = TaxableIncomeService(self.env)
        taxable_inc = taxable_svc.calculate_taxable_income(
            gross_total_income=gti,
            total_approved_deductions=deduction_calc.total_approved_deductions
        )
        if debug_enabled:
            _logger.warning(
                "After TaxableIncomeService | Taxable Income: %s",
                taxable_inc.net_taxable_income
            )

        # Step 6: Income Tax Slab Engine Computation
        _logger.warning("""[TAX_SLAB_INPUT_AUDIT]
gross_annual_income=%s
standard_deduction=%s
professional_tax_16iii=%s
hra_exemption_received=%s
chapter_6a_deductions=%s
total_deductions=%s
taxable_income_passed_to_tax_calculator=%s""",
            f"INR {float(gti or 0.0):,.2f}",
            f"INR {float(deduction_calc.standard_deduction or 0.0):,.2f}",
            f"INR {float(getattr(deduction_calc, 'professional_tax_16iii', 0.0) or 0.0):,.2f}",
            f"INR {float(deduction_calc.hra_exemption or 0.0):,.2f}",
            f"INR {float(deduction_calc.total_chapter_6a or 0.0):,.2f}",
            f"INR {float(deduction_calc.total_approved_deductions or 0.0):,.2f}",
            f"INR {float(taxable_inc.net_taxable_income or 0.0):,.2f}"
        )

        # Step 6a: Resolve employee age category for Old Regime slab selection
        # Per CBDT Circular No. 19/2015: age determined as of March 31 of the Financial Year
        age_category = IncomeTaxSlabService.resolve_age_category(employee, financial_year, eval_date)

        if debug_enabled:
            _logger.warning("Before IncomeTaxSlabService | Age Category: %s", age_category)
        slab_svc = IncomeTaxSlabService(self.env)
        slab_calc = slab_svc.calculate_base_tax(
            net_taxable_income=taxable_inc.net_taxable_income,
            financial_year=financial_year,
            regime_code=regime_code,
            age_category=age_category
        )
        if debug_enabled:
            _logger.warning(
                "After IncomeTaxSlabService | Base Tax: %s | Age Category: %s",
                slab_calc.base_tax_liability,
                slab_calc.age_category
            )

        # Step 7: Section 87A Rebate Engine Application
        if debug_enabled:
            _logger.warning("Before RebateEngineService")
        rebate_svc = RebateEngineService(self.env)
        rebate_calc = rebate_svc.apply_rebate(
            net_taxable_income=taxable_inc.net_taxable_income,
            base_tax_liability=slab_calc.base_tax_liability,
            regime_code=regime_code,
            eval_date=eval_date
        )
        if debug_enabled:
            _logger.warning(
                "After RebateEngineService | 87A Rebate: %s, Tax After Rebate: %s",
                rebate_calc.rebate_applied,
                rebate_calc.tax_after_rebate
            )

        # Step 8: Range-Based Surcharge Engine Application
        if debug_enabled:
            _logger.warning("Before SurchargeEngineService")
        surcharge_svc = SurchargeEngineService(self.env)
        surcharge_calc = surcharge_svc.calculate_surcharge(
            net_taxable_income=taxable_inc.net_taxable_income,
            tax_after_rebate=rebate_calc.tax_after_rebate,
            financial_year=financial_year,
            regime_code=regime_code,
            age_category=age_category
        )
        if debug_enabled:
            _logger.warning(
                "After SurchargeEngineService | Surcharge Before Relief: %s, Marginal Relief: %s, Final Surcharge: %s",
                getattr(surcharge_calc, 'surcharge_before_relief', surcharge_calc.surcharge_amount),
                getattr(surcharge_calc, 'marginal_relief', 0.0),
                surcharge_calc.surcharge_amount
            )

        # Step 9 & 10: Health & Education Cess Engine & Annual Tax Liability
        if debug_enabled:
            _logger.warning("Before HealthEducationCessService")
        cess_svc = HealthEducationCessService(self.env)
        cess_calc = cess_svc.calculate_cess(
            tax_plus_surcharge=surcharge_calc.tax_plus_surcharge,
            eval_date=eval_date
        )
        if debug_enabled:
            _logger.warning(
                "After HealthEducationCessService | Cess Amount: %s, Final Annual Tax: %s",
                cess_calc.cess_amount,
                cess_calc.total_annual_tax_liability
            )

        _logger.warning("""[TAX_SLAB_OUTPUT_AUDIT]
fresh_annual_tax_returned=%s""",
            f"INR {float(cess_calc.total_annual_tax_liability or 0.0):,.2f}"
        )

        gross_income = float(annual_projection.gross_total_income or 0.0)
        total_exemptions = float(deduction_calc.hra_exemption or 0.0) + float(deduction_calc.standard_deduction or 0.0)
        chapter_via = float(deduction_calc.total_chapter_6a or 0.0)
        taxable_income = float(taxable_inc.net_taxable_income or 0.0)
        tax_after_recalc = float(cess_calc.total_annual_tax_liability or 0.0)

        stored_sched = self.env['tds.recalculation.schedule'].sudo().search([
            ('employee_id', '=', employee.id),
            ('financial_year_id', '=', financial_year.id)
        ], order='id desc', limit=1)
        tax_before_proof = float(stored_sched.recalculated_annual_tax or 0.0) if stored_sched else tax_after_recalc
        tax_difference = tax_after_recalc - tax_before_proof

        _logger.warning("""[ANNUAL_TAX_TRACE]
gross_projected_income=%s
total_exemptions=%s
chapter_via_deductions=%s
taxable_income=%s
tax_before_proof=%s
tax_after_recalculation=%s
tax_difference=%s""",
            f"INR {gross_income:,.2f}",
            f"INR {total_exemptions:,.2f}",
            f"INR {chapter_via:,.2f}",
            f"INR {taxable_income:,.2f}",
            f"INR {tax_before_proof:,.2f}",
            f"INR {tax_after_recalc:,.2f}",
            f"INR {tax_difference:,.2f}"
        )

        # Step 11: Monthly TDS Distribution Engine Computation
        if debug_enabled:
            import inspect
            _logger.warning("Before MonthlyTDSDistributionService | Source File: %s", inspect.getfile(MonthlyTDSDistributionService))
        monthly_svc = MonthlyTDSDistributionService(self.env)
        monthly_tds = monthly_svc.calculate_monthly_tds(
            employee=employee,
            financial_year=financial_year,
            total_annual_tax_liability=cess_calc.total_annual_tax_liability,
            eval_date=eval_date,
            payslip=payslip
        )

        decl_rec = self.env['tds.employee.declaration'].sudo().search([
            ('employee_id', '=', employee.id),
            ('financial_year_id', '=', financial_year.id)
        ], limit=1)
        hra_line = decl_rec.declaration_line_ids.filtered(lambda l: l.category == 'hra') if decl_rec else None
        decl_rent_val = float(getattr(decl_rec, 'decl_hra_annual_rent', 0.0) or (hra_line[0].declared_amount if hra_line else 0.0) or 0.0)
        appr_rent_val = float(getattr(hra_line[0], 'tax_firm_approved_amount', 0.0) or getattr(hra_line[0], 'approved_amount', 0.0) or 0.0) if hra_line else 0.0
        usable_rent_val = float(hra_line[0].usable_amount if hra_line else 0.0)
        sel_rent_val = usable_rent_val if usable_rent_val > 0.0 else decl_rent_val
        sel_src_val = "DECLARATION_LINE" if usable_rent_val > 0.0 else "HEADER_DECLARATION"

        c6a_obj = getattr(deduction_calc, 'chapter_6a_deductions', None)
        std_ded_val = float(deduction_calc.standard_deduction or 0.0)
        pt_16iii_val = float(getattr(deduction_calc, 'professional_tax_16iii', 0.0) or 0.0)
        hra_ex_val = float(deduction_calc.hra_exemption or 0.0)
        lta_ex_val = float(deduction_calc.lta_exemption or 0.0)
        s80c_val = float(getattr(c6a_obj, 'section_80c', 0.0) or 0.0) if c6a_obj else 0.0
        s80ccd1b_val = float(getattr(c6a_obj, 'section_80ccd1b', 0.0) or 0.0) if c6a_obj else 0.0
        s80ccd2_val = float(getattr(deduction_calc, 'employer_nps_80ccd2', 0.0) or 0.0)
        s80d_val = float(getattr(c6a_obj, 'section_80d', 0.0) or 0.0) if c6a_obj else 0.0
        s80e_val = float(getattr(c6a_obj, 'section_80e', 0.0) or 0.0) if c6a_obj else 0.0
        s80g_val = float(getattr(c6a_obj, 'section_80g', 0.0) or 0.0) if c6a_obj else 0.0
        s80gg_val = float(getattr(c6a_obj, 'section_80gg', 0.0) or 0.0) if c6a_obj else 0.0
        s80dd_val = float(getattr(c6a_obj, 'section_80dd', 0.0) or 0.0) if c6a_obj else 0.0
        s80u_val = float(getattr(c6a_obj, 'section_80u', 0.0) or 0.0) if c6a_obj else 0.0
        s80tta_val = float(getattr(c6a_obj, 'section_80tta', 0.0) or 0.0) if c6a_obj else 0.0
        s80ttb_val = float(getattr(c6a_obj, 'section_80ttb', 0.0) or 0.0) if c6a_obj else 0.0
        s24b_val = float(getattr(deduction_calc, 'home_loan_interest_24b', 0.0) or 0.0)
        s80eea_val = float(getattr(c6a_obj, 'section_80eea', 0.0) or 0.0) if c6a_obj else 0.0
        s80cch_val = float(getattr(c6a_obj, 'section_80cch', 0.0) or 0.0) if c6a_obj else 0.0
        s57iia_val = float(getattr(deduction_calc, 'family_pension_57iia', 0.0) or 0.0)
        total_c6a_val = float(deduction_calc.total_chapter_6a or 0.0)
        total_ded_val = float(deduction_calc.total_allowable_deductions or 0.0)

        _logger.warning("""[TDS_ANNUAL_RECALC_AUDIT]
calculation_run_id=%s
payslip_id=%s
evaluation_date=%s
financial_year=%s
previous_annual_tax=%s
fresh_annual_tax=%s
tax_difference=%s
ytd_tds=%s
remaining_tax=%s
months_remaining=%s
calculated_monthly_tds=%s
final_tds=%s
annual_taxable_income=%s
standard_deduction=%s
hra_exemption=%s
lta_exemption=%s
section_80c=%s
section_80ccd1b=%s
section_80ccd2=%s
section_80d=%s
section_80e=%s
section_80g=%s
section_80gg=%s
section_80dd=%s
section_80u=%s
section_80tta=%s
section_80ttb=%s
section_24b=%s
section_80eea=%s
section_80cch=%s
section_57iia=%s
total_chapter_6a=%s
total_deductions=%s""",
            calc_run_id,
            payslip.id if payslip else 'N/A',
            eval_date.strftime('%Y-%m-%d') if hasattr(eval_date, 'strftime') else str(eval_date),
            financial_year.name if financial_year else 'N/A',
            f"INR {tax_before_proof:,.2f}",
            f"INR {tax_after_recalc:,.2f}",
            f"INR {tax_difference:,.2f}",
            f"INR {float(monthly_tds.total_tds_paid_so_far or monthly_tds.ytd_tds_deducted or 0.0):,.2f}",
            f"INR {float(monthly_tds.remaining_annual_tax_liability or 0.0):,.2f}",
            monthly_tds.remaining_payroll_periods,
            f"INR {float(monthly_tds.current_month_tds or 0.0):,.2f}",
            f"INR {float(monthly_tds.current_month_tds or 0.0):,.2f}",
            f"INR {taxable_income:,.2f}",
            f"INR {std_ded_val:,.2f}",
            f"INR {hra_ex_val:,.2f}",
            f"INR {lta_ex_val:,.2f}",
            f"INR {s80c_val:,.2f}",
            f"INR {s80ccd1b_val:,.2f}",
            f"INR {s80ccd2_val:,.2f}",
            f"INR {s80d_val:,.2f}",
            f"INR {s80e_val:,.2f}",
            f"INR {s80g_val:,.2f}",
            f"INR {s80gg_val:,.2f}",
            f"INR {s80dd_val:,.2f}",
            f"INR {s80u_val:,.2f}",
            f"INR {s80tta_val:,.2f}",
            f"INR {s80ttb_val:,.2f}",
            f"INR {s24b_val:,.2f}",
            f"INR {s80eea_val:,.2f}",
            f"INR {s80cch_val:,.2f}",
            f"INR {s57iia_val:,.2f}",
            f"INR {total_c6a_val:,.2f}",
            f"INR {total_ded_val:,.2f}"
        )

        _logger.warning("""[JANUARY_END_TO_END_TDS_RECALC_TRACE]
calculation_run_id=%s
employee=%s (ID: %s)
payslip=%s (ID: %s)
declaration_id=%s
financial_year=%s
payroll_month=%s
hra_selected_amount=%s
hra_selected_source=%s
hra_exemption=%s
annual_tax_before_recalculation=%s
annual_tax_after_recalculation=%s
tax_difference=%s
ytd_tds=%s
remaining_tax=%s
remaining_months=%s
new_monthly_tds=%s
final_HDS_IN_TDS=%s""",
            calc_run_id,
            employee.name, employee.id,
            payslip.name if payslip else 'N/A', payslip.id if payslip else 'N/A',
            decl_rec.id if decl_rec else 'N/A',
            financial_year.name if financial_year else 'N/A',
            eval_date.strftime('%B %Y') if hasattr(eval_date, 'strftime') else str(eval_date),
            f"INR {sel_rent_val:,.2f}",
            sel_src_val,
            f"INR {float(deduction_calc.hra_exemption or 0.0):,.2f}",
            f"INR {tax_before_proof:,.2f}",
            f"INR {tax_after_recalc:,.2f}",
            f"INR {tax_difference:,.2f}",
            f"INR {float(monthly_tds.total_tds_paid_so_far or monthly_tds.ytd_tds_deducted or 0.0):,.2f}",
            f"INR {float(monthly_tds.remaining_annual_tax_liability or 0.0):,.2f}",
            monthly_tds.remaining_payroll_periods,
            f"INR {float(monthly_tds.current_month_tds or 0.0):,.2f}",
            f"INR {float(monthly_tds.current_month_tds or 0.0):,.2f}"
        )

        # ══════════════════════════════════════════════════════════════════════
        # COMPREHENSIVE TDS CALCULATION TRACE  (diagnostic logging only)
        # ══════════════════════════════════════════════════════════════════════
        if debug_enabled:
            decl_for_log = self.env['tds.employee.declaration'].sudo().search([
                ('employee_id', '=', employee.id),
                ('financial_year_id', '=', financial_year_id)
            ], limit=1)
            c6a_obj        = getattr(deduction_calc, 'chapter_6a_deductions', None)
            sal_proj       = annual_projection.salary_projection
            prev_emp       = annual_projection.previous_employer_income
            oth_inc        = annual_projection.other_income_aggregation

            # ── Chapter VI-A component extraction ─────────────────────────────────
            sec_80c_val      = getattr(c6a_obj, 'section_80c',          0.0) if c6a_obj else 0.0
            sec_80ccd1b_val  = getattr(c6a_obj, 'section_80ccd1b',      0.0) if c6a_obj else 0.0
            sec_80d_val      = getattr(c6a_obj, 'section_80d',          0.0) if c6a_obj else 0.0
            sec_80dd_val     = getattr(c6a_obj, 'section_80dd',         0.0) if c6a_obj else 0.0
            sec_80tta_val    = getattr(c6a_obj, 'section_80tta_80ttb',  0.0) if c6a_obj else 0.0
            sec_80eea_val    = getattr(c6a_obj, 'section_80eea',        0.0) if c6a_obj else 0.0
            sec_80g_val      = getattr(c6a_obj, 'section_80g',          0.0) if c6a_obj else 0.0
            sec_80e_val      = getattr(c6a_obj, 'section_80e',          0.0) if c6a_obj else 0.0
            sec_80u_val      = getattr(c6a_obj, 'section_80u',          0.0) if c6a_obj else 0.0
            sec_80gg_val     = getattr(c6a_obj, 'section_80gg',         0.0) if c6a_obj else 0.0
            sec_other80_val  = getattr(c6a_obj, 'other_80_deductions',  0.0) if c6a_obj else 0.0
            total_c6a_val    = deduction_calc.total_chapter_6a if hasattr(deduction_calc, 'total_chapter_6a') else 0.0

            _logger.warning("""[TDS_DEBUG_TRACE][BOUNDARY_TRACE]
80E_FINAL_CHAPTER6A_AMOUNT=%s
80E_SELECTED_AMOUNT=%s
80E_INCLUDED_IN_CHAPTER6A=%s
80G_FINAL_CHAPTER6A_AMOUNT=%s
80G_SELECTED_AMOUNT=%s
80G_INCLUDED_IN_CHAPTER6A=%s
TOTAL_CHAPTER6A_DEDUCTIONS=%s
TOTAL_ALLOWABLE_DEDUCTIONS=%s
TAXABLE_INCOME=%s
ANNUAL_TAX_LIABILITY=%s
PREVIOUS_TDS=%s
BALANCE_TAX=%s
CURRENT_MONTH_TDS=%s""",
                sec_80e_val, sec_80e_val, sec_80e_val,
                sec_80g_val, sec_80g_val, sec_80g_val,
                total_c6a_val,
                deduction_calc.total_allowable_deductions,
                taxable_inc.net_taxable_income,
                cess_calc.total_annual_tax_liability,
                monthly_tds.ytd_tds_deducted,
                monthly_tds.remaining_annual_tax_liability,
                monthly_tds.current_month_tds
            )

            # ── Employer NPS 80CCD(2), family pension, and 80CCH ──────────────────
            emp_nps_80ccd2   = float(getattr(deduction_calc, 'employer_nps_80ccd2',   0.0) or 0.0)
            fam_pension_57   = float(getattr(deduction_calc, 'family_pension_57iia',  0.0) or 0.0)
            sec_80eea_ded    = float(getattr(deduction_calc, 'section_80eea_deduction', 0.0) or 0.0)
            from .section_57iia_deduction_service import Section57IIADeductionService
            from .tds_parameter_service import TdsParameterService
            tds_param_svc_inst = TdsParameterService(self.env)
            fp_limit = tds_param_svc_inst.get_family_pension_limit(regime=regime_code, eval_date=eval_date)
            fp_sec_code = Section57IIADeductionService.get_statutory_section_code(financial_year, eval_date=eval_date)
            fp_label = Section57IIADeductionService.get_legal_reference_label(financial_year, eval_date=eval_date)
            fam_pension_gross = float(getattr(oth_inc, 'family_pension_gross', 0.0) or 0.0)
            fam_pension_ded = float(getattr(oth_inc, 'family_pension_deduction', fam_pension_57) or 0.0)
            fam_pension_net = float(getattr(oth_inc, 'family_pension_net', 0.0) or 0.0)
            sec_80cch_val    = 0.0
            decl_80cch_claimed = 0.0
            if decl_for_log:
                has_cch_hdr = (float(getattr(decl_for_log, 'decl_80cch_agniveer', 0.0) or 0.0) > 0.0)
                has_cch_ln = any(l.category == '80cch' for l in decl_for_log.declaration_line_ids)
                if has_cch_hdr or has_cch_ln:
                    from .section_80cch_deduction_service import Section80CCHDeductionService
                    cch_svc = Section80CCHDeductionService(self.env)
                    sec_80cch_val = cch_svc.validate_and_trace(
                        decl_for_log,
                        eval_date=eval_date,
                        regime_code=regime_code,
                        employee=employee,
                        financial_year=financial_year
                    ).usable_amount
                    cch_ln = next((l for l in decl_for_log.declaration_line_ids if l.category == '80cch'), None)
                    is_post_proof_log = getattr(decl_for_log, 'state', 'draft') in ('proof_verified', 'approved')
                    if cch_ln:
                        ln_appr = float(getattr(cch_ln, 'tax_firm_approved_amount', 0.0) or getattr(cch_ln, 'approved_amount', 0.0) or 0.0)
                        decl_80cch_claimed = ln_appr if (is_post_proof_log and ln_appr > 0.0) else float(cch_ln.declared_amount or 0.0)
                    else:
                        hdr_appr = float(getattr(decl_for_log, 'decl_80cch_approved_amount', 0.0) or 0.0)
                        decl_80cch_claimed = hdr_appr if (is_post_proof_log and hdr_appr > 0.0) else float(getattr(decl_for_log, 'decl_80cch_agniveer', 0.0) or 0.0)

            # ── Tax slab detail ───────────────────────────────────────────────────
            slab_breakdown   = getattr(slab_calc, 'slab_breakdown', [])
            slab_lines       = '\n'.join(
                f"   {sb.get('range','?'):30s}  Rate: {sb.get('rate',0)*100:.0f}%  "
                f"Tax: ₹{sb.get('tax',0.0):,.2f}"
                for sb in slab_breakdown
            ) if slab_breakdown else "   (no slab breakdown available)"

            # ── Rebate detail ─────────────────────────────────────────────────────
            rebate_limit_val  = float(getattr(rebate_calc, 'rebate_limit',  0.0) or 0.0)
            rebate_applicable = getattr(rebate_calc, 'is_applicable', rebate_calc.rebate_applied > 0)

            # ── Surcharge detail ──────────────────────────────────────────────────
            surcharge_rate_val = float(getattr(surcharge_calc, 'surcharge_rate_pct', getattr(surcharge_calc, 'surcharge_rate', 0.0)) or 0.0)
            tax_plus_surcharge = float(getattr(surcharge_calc, 'tax_plus_surcharge', 0.0) or 0.0)

            # ── Cess detail ───────────────────────────────────────────────────────
            cess_rate_val      = float(getattr(cess_calc, 'cess_rate_pct', getattr(cess_calc, 'cess_rate', 0.04)) or 0.04)

            # ── Payslip context (if available) ────────────────────────────────────
            payslip_ref  = getattr(payslip, 'name', 'N/A') if payslip else 'N/A'
            payroll_mth  = (payslip.date_to.strftime('%B %Y')
                            if payslip and getattr(payslip, 'date_to', None)
                            else (eval_date.strftime('%B %Y') if hasattr(eval_date, 'strftime') else str(eval_date)))
            eval_date_s  = eval_date.strftime('%d-%b-%Y') if hasattr(eval_date, 'strftime') else str(eval_date)
            fy_name      = financial_year.name if financial_year else 'N/A'
            emp_name     = getattr(employee, 'name', 'Unknown')

            decl_id_str = str(decl_for_log.id) if decl_for_log else 'N/A'
            payslip_id_str = str(payslip.id) if payslip else 'N/A'

            detailed_trace = f"""[TDS_DEBUG_TRACE]
Employee: {emp_name}
Payslip ID: {payslip_id_str}
Payroll Month: {payroll_mth}
Financial Year: {fy_name}
Declaration ID: {decl_id_str}

================================================================================
TDS CALCULATION TRACE
================================================================================
Employee        : {emp_name} (ID: {getattr(employee, 'id', 'N/A')})
Payslip         : {payslip_ref}
Payroll Month   : {payroll_mth}
Financial Year  : {fy_name}
Tax Regime      : {regime_code.upper()} ({regime_name})
Eval Date       : {eval_date_s}
================================================================================

[STAGE 1 — SALARY PROJECTION]
Input          : Contract/Payslip history for FY {fy_name}
Months Elapsed : {sal_proj.months_elapsed}
Paid Payslips  : {getattr(sal_proj, 'months_remaining', 0) + getattr(sal_proj, 'months_elapsed', 0) - getattr(sal_proj, 'months_remaining', 0)}
Projection Mths: {sal_proj.months_remaining}
Formula        : YTD Basic + YTD DA + YTD HRA + YTD Allowances
                 + (Monthly Gross × Projection Months)
  YTD Basic    : ₹{sal_proj.ytd_basic:,.2f}
  YTD DA       : ₹{sal_proj.ytd_da:,.2f}
  YTD HRA      : ₹{sal_proj.ytd_hra:,.2f}
  YTD Bonus    : ₹{sal_proj.ytd_bonus:,.2f}
  YTD Allows   : ₹{sal_proj.ytd_allowances:,.2f}
  Proj Basic   : ₹{sal_proj.projected_basic:,.2f}
  Proj DA      : ₹{sal_proj.projected_da:,.2f}
  Proj HRA     : ₹{sal_proj.projected_hra:,.2f}
  Proj Allows  : ₹{sal_proj.projected_allowances:,.2f}
Result         : ₹{sal_proj.total_projected_current_salary:,.2f}

[STAGE 2 — PREVIOUS EMPLOYER INCOME]
Input          : Form 12B declaration
  Taxable Sal  : ₹{float(getattr(prev_emp, 'taxable_salary', 0.0) or 0.0):,.2f}
  Prev TDS     : ₹{float(getattr(prev_emp, 'tds_deducted', 0.0) or 0.0):,.2f}
Formula        : Prev Employer Gross - Prev Employer Exemptions
Result         : ₹{float(getattr(prev_emp, 'taxable_salary', 0.0) or 0.0):,.2f}

[STAGE 3 — OTHER INCOME]
Input          : Employer/Employee declaration
  Savings Int  : ₹{float(getattr(oth_inc, 'savings_interest', 0.0) or 0.0):,.2f}
  FD Interest  : ₹{float(getattr(oth_inc, 'fd_interest', 0.0) or 0.0):,.2f}
  Dividend     : ₹{float(getattr(oth_inc, 'dividend_income', 0.0) or 0.0):,.2f}
  Misc Income  : ₹{float(getattr(oth_inc, 'other_sources_misc', 0.0) or 0.0):,.2f}
  Fam Pension  : Gross ₹{fam_pension_gross:,.2f} - Ded ₹{fam_pension_ded:,.2f} = Net ₹{fam_pension_net:,.2f}
  Net HseProperty: ₹{float(getattr(oth_inc, 'net_house_property_income_loss', 0.0) or 0.0):,.2f}
Formula        : Sum of all other-source income items
Result (Total Other Income): ₹{float(getattr(oth_inc, 'total_other_income', 0.0) or 0.0):,.2f}

[STAGE 4 — GROSS TOTAL INCOME (GTI)]
Input          :
  Current Employer Salary : ₹{sal_proj.total_projected_current_salary:,.2f}
  Prev Employer Income    : ₹{float(getattr(prev_emp, 'taxable_salary', 0.0) or 0.0):,.2f}
  Other Income            : ₹{float(getattr(oth_inc, 'total_other_income', 0.0) or 0.0):,.2f}
Formula        : Current Salary + Previous Employer + Other Income
Result (GTI)   : ₹{annual_projection.gross_total_income:,.2f}

[STAGE 5 — STANDARD DEDUCTION]
Input          : Regime={regime_code.upper()}
Formula        : ₹50,000 (Old) | ₹75,000 (New, FY 2025-26+)
Result         : ₹{deduction_calc.standard_deduction:,.2f}

[STAGE 6 — CHAPTER VI-A DEDUCTIONS]
Input          : Declaration approved/usable amounts
  6A-1  Sec 80C  Investments          : ₹{sec_80c_val:,.2f}   (cap ₹1,50,000)
  6A-2  Sec 80CCD(1B) NPS             : ₹{sec_80ccd1b_val:,.2f}   (cap ₹50,000)
  6A-3  Employer NPS (Sec 124)        : ₹{emp_nps_80ccd2:,.2f}   (% of Basic+DA)
  6A-4  Sec 80D Medical Insurance     : ₹{sec_80d_val:,.2f}
  6A-5  Sec 80DD Disability Dependent : ₹{sec_80dd_val:,.2f}
  6A-6  Sec 80TTA/80TTB Savings Int   : ₹{sec_80tta_val:,.2f}
  6A-7  Sec 80EEA Additional Interest : ₹{sec_80eea_val:,.2f}
  6A-8  Sec 80G Charitable Donations  : ₹{sec_80g_val:,.2f}
  6A-9  Sec 80E Education Loan Int    : ₹{sec_80e_val:,.2f}
  6A-10 Sec 80U Employee Disability   : ₹{sec_80u_val:,.2f}
  6A-11 Sec 80CCH Agniveer Corpus     : ₹{sec_80cch_val:,.2f}
  6A-12 Other (80GG/Misc)             : ₹{sec_other80_val:,.2f}
Formula        : Sum of all permitted Chapter VI-A sections (0 if New Regime)
Result (Total Chapter VI-A): ₹{total_c6a_val:,.2f}

[STAGE 7 — {fp_label.upper()} FAMILY PENSION DEDUCTION]
Input          : Gross Family Pension declared = ₹{fam_pension_gross:,.2f}
Formula        : min(1/3 of family pension, ₹{fp_limit:,.0f}) (Netted under Income from Other Sources)
Deduction      : ₹{fam_pension_ded:,.2f}
Net Pension    : ₹{fam_pension_net:,.2f} (Included in Stage 3 Other Income)

[STAGE 8 — HRA EXEMPTION (Sec 10(13A))]
Input          : Actual HRA, Annual Rent, Basic+DA, Metro flag
Formula        : min(Actual HRA, Rent-10%Basic, 50%/40% of Basic) [Old Regime only]
Result         : ₹{deduction_calc.hra_exemption:,.2f}

[STAGE 9 — SECTION 24(b) SELF-OCCUPIED HOME LOAN INTEREST]
Input          : Self-Occupied Home Loan Interest Declared (Field: decl_24b_self_interest via HomeLoanDeductionService)
Formula        : min(Declared, ₹2,00,000) [Old Regime only]
Result         : ₹{deduction_calc.home_loan_interest_24b:,.2f}

[STAGE 10 — SEC 80EEA FIRST-TIME HOME BUYER]
Input          : Residual interest after 24(b) cap, eligibility conditions
Formula        : min(Eligible Residual, ₹1,50,000) [Old Regime only]
Result         : ₹{sec_80eea_ded:,.2f}

[STAGE 11 — TOTAL ALLOWABLE DEDUCTIONS]
Input          :
  Standard Deduction   : ₹{deduction_calc.standard_deduction:,.2f}
  Professional Tax 16(iii): ₹{pt_16iii_val:,.2f}
  Chapter VI-A Total   : ₹{total_c6a_val:,.2f}
  Employer NPS (Sec 124): ₹{emp_nps_80ccd2:,.2f}
  HRA Exemption        : ₹{deduction_calc.hra_exemption:,.2f}
  Sec 24(b) Self-Occupied: ₹{deduction_calc.home_loan_interest_24b:,.2f}
  80EEA                : ₹{sec_80eea_ded:,.2f}
Formula        : Sum of all approved salary & Ch.VI-A deductions
Result         : ₹{deduction_calc.total_allowable_deductions:,.2f}

[STAGE 12 — TAXABLE INCOME]
Input          : GTI={annual_projection.gross_total_income:,.2f}  Total Deductions={deduction_calc.total_allowable_deductions:,.2f}
Formula        : max(0, GTI - Total Allowable Deductions)
Result         : ₹{taxable_inc.net_taxable_income:,.2f}

[STAGE 13 — TAX SLAB CALCULATION]
Input          : Taxable Income=₹{taxable_inc.net_taxable_income:,.2f}  Regime={regime_code.upper()}
Slab Breakdown :
{slab_lines}
Formula        : Progressive slab-rate computation
Result (Base Tax): ₹{slab_calc.base_tax_liability:,.2f}

[STAGE 14 — SECTION 87A REBATE]
Input          : Taxable Income=₹{taxable_inc.net_taxable_income:,.2f}  Base Tax=₹{slab_calc.base_tax_liability:,.2f}
Rebate Limit   : ₹{rebate_limit_val:,.2f}
Applicable     : {rebate_applicable}
Formula        : if Taxable Income <= threshold → Rebate = min(BaseTax, RebateLimit)
Result (Rebate Applied): ₹{rebate_calc.rebate_applied:,.2f}
Tax After Rebate       : ₹{rebate_calc.tax_after_rebate:,.2f}

[STAGE 15 — SURCHARGE]
Input          : Taxable Income=₹{taxable_inc.net_taxable_income:,.2f}  Tax After Rebate=₹{rebate_calc.tax_after_rebate:,.2f}
Surcharge Rate : {surcharge_rate_val * 100:.0f}%
Formula        : (Tax After Rebate × Surcharge Rate) - Marginal Relief
Surcharge Pre-Relief : ₹{getattr(surcharge_calc, 'surcharge_before_relief', surcharge_calc.surcharge_amount):,.2f}
Marginal Relief      : ₹{getattr(surcharge_calc, 'marginal_relief', 0.0):,.2f}
Result (Final Surcharge): ₹{surcharge_calc.surcharge_amount:,.2f}
Tax + Surcharge      : ₹{tax_plus_surcharge:,.2f}

[STAGE 16 — HEALTH & EDUCATION CESS]
Input          : Tax + Surcharge=₹{tax_plus_surcharge:,.2f}
Cess Rate      : {cess_rate_val * 100:.0f}%
Formula        : (Tax + Surcharge) × 4%
Result (Cess)  : ₹{cess_calc.cess_amount:,.2f}

[STAGE 17 — FINAL ANNUAL TAX LIABILITY]
Input          : Tax+Surcharge=₹{tax_plus_surcharge:,.2f}  Cess=₹{cess_calc.cess_amount:,.2f}
Formula        : Tax + Surcharge + Cess
Result         : ₹{cess_calc.total_annual_tax_liability:,.2f}

[STAGE 18 — YTD TDS]
Input          : Confirmed payslips for FY {fy_name}
  Prev Employer TDS : ₹{monthly_tds.prev_employer_tds:,.2f}
  Current FY YTD    : ₹{monthly_tds.ytd_tds_deducted:,.2f}
Formula        : Sum of TDS from all paid payslips + Prev Employer TDS
Result (Total TDS Paid So Far): ₹{monthly_tds.total_tds_paid_so_far:,.2f}

[STAGE 19 — REMAINING TAX LIABILITY]
Input          : Annual Tax=₹{cess_calc.total_annual_tax_liability:,.2f}  Paid So Far=₹{monthly_tds.total_tds_paid_so_far:,.2f}
Formula        : max(0, Annual Tax - Total TDS Paid So Far)
Result         : ₹{monthly_tds.remaining_annual_tax_liability:,.2f}

[STAGE 20 — REMAINING MONTHS / DISTRIBUTION]
Input          : Eval Date={eval_date_s}  FY End={fy_name}
Remaining Payroll Periods : {monthly_tds.remaining_payroll_periods}
Formula        : Determined by PayrollPeriodService based on confirmed payslips remaining in FY

[STAGE 21 — FINAL CURRENT MONTH TDS]
Input          : Remaining Liability=₹{monthly_tds.remaining_annual_tax_liability:,.2f}
                 Distribution Periods={monthly_tds.remaining_payroll_periods}
Formula        : Remaining Liability / Remaining Payroll Periods
Result         : ₹{monthly_tds.current_month_tds:,.2f}

================================================================================
FINAL SUMMARY
================================================================================
Gross Total Income         : ₹{annual_projection.gross_total_income:,.2f}
Standard Deduction         : ₹{deduction_calc.standard_deduction:,.2f}
Professional Tax 16(iii)   : ₹{pt_16iii_val:,.2f}
Chapter VI-A Total         : ₹{total_c6a_val:,.2f}
Section 57(iia)            : ₹{fam_pension_57:,.2f}
HRA Exemption              : ₹{deduction_calc.hra_exemption:,.2f}
Sec 24(b) Self-Occupied    : ₹{deduction_calc.home_loan_interest_24b:,.2f}
80EEA                      : ₹{sec_80eea_ded:,.2f}
Employer NPS (Sec 124)        : ₹{emp_nps_80ccd2:,.2f}
Other Deductions           : ₹{float(getattr(deduction_calc, 'other_approved_deductions', 0.0) or 0.0):,.2f}
Total Allowable Deductions : ₹{deduction_calc.total_allowable_deductions:,.2f}
Taxable Income             : ₹{taxable_inc.net_taxable_income:,.2f}
Gross Tax                  : ₹{slab_calc.base_tax_liability:,.2f}
87A Rebate                 : ₹{rebate_calc.rebate_applied:,.2f}
Surcharge Before Relief    : ₹{getattr(surcharge_calc, 'surcharge_before_relief', surcharge_calc.surcharge_amount):,.2f}
Marginal Relief            : ₹{getattr(surcharge_calc, 'marginal_relief', 0.0):,.2f}
Final Surcharge            : ₹{surcharge_calc.surcharge_amount:,.2f}
Cess (4%)                  : ₹{cess_calc.cess_amount:,.2f}
Annual Tax Liability        : ₹{cess_calc.total_annual_tax_liability:,.2f}
YTD TDS                    : ₹{monthly_tds.ytd_tds_deducted:,.2f}
Prev Employer TDS          : ₹{monthly_tds.prev_employer_tds:,.2f}
Remaining Liability        : ₹{monthly_tds.remaining_annual_tax_liability:,.2f}
Distribution Months        : {monthly_tds.remaining_payroll_periods}
Current Month TDS          : ₹{monthly_tds.current_month_tds:,.2f}
================================================================================
"""
            _logger.warning(detailed_trace)

            sec_80e_val = float(getattr(getattr(deduction_calc, 'chapter_6a_deductions', None), 'section_80e', 0.0) or 0.0)
            _logger.warning("""[80E_AUDIT] MASTER_FLOW_TRACE
final_80e_deduction=%s
total_deductions=%s
taxable_income=%s
tax_before_rebate=%s
rebate=%s
cess=%s
annual_tax_liability=%s
previous_tds=%s
balance_tax=%s
distribution_months=%s
current_month_tds=%s""",
                sec_80e_val,
                deduction_calc.total_allowable_deductions,
                taxable_inc.net_taxable_income,
                slab_calc.base_tax_liability,
                rebate_calc.rebate_applied,
                cess_calc.cess_amount,
                cess_calc.total_annual_tax_liability,
                monthly_tds.total_tds_paid_so_far,
                monthly_tds.remaining_annual_tax_liability,
                monthly_tds.remaining_payroll_periods,
                monthly_tds.current_month_tds
            )

            _logger.warning("""[80E_BUG_TRACE] 80E_STATE
declared_80e=%s
approved_80e=%s
eligible_80e=%s
final_80e_deduction=%s""",
                float(getattr(decl_for_log, 'decl_80e_interest', 0.0) or 0.0) if decl_for_log else 0.0,
                sec_80e_val,
                sec_80e_val,
                sec_80e_val
            )

            _logger.warning("""[80E_BUG_TRACE] TAX_RESULT
total_deductions=%s
taxable_income=%s
annual_tax=%s""",
                deduction_calc.total_allowable_deductions,
                taxable_inc.net_taxable_income,
                cess_calc.total_annual_tax_liability
            )

            _logger.warning("""[80E_BUG_TRACE] HDS_IN_COMPUTE_TDS_CALL
call_number=%s
caller/method=%s
80e_deduction=%s
total_deductions=%s
taxable_income=%s
annual_tax=%s
current_month_tds=%s""",
                call_idx,
                caller_func,
                sec_80e_val,
                deduction_calc.total_allowable_deductions,
                taxable_inc.net_taxable_income,
                cess_calc.total_annual_tax_liability,
                monthly_tds.current_month_tds
            )

            case_name = "80E: Declared = ₹1,00,000, Approved = ₹70,000" if (sec_80e_val > 0 or (decl_for_log and float(getattr(decl_for_log, 'decl_80e_interest', 0.0) or 0.0) > 0)) else "NO DEDUCTION"
            declared_80e_val = float(getattr(decl_for_log, 'decl_80e_interest', 0.0) or 0.0) if decl_for_log else 0.0
            prev_cnt = monthly_tds.completed_payroll_periods if hasattr(monthly_tds, 'completed_payroll_periods') and monthly_tds.completed_payroll_periods else (eval_date.month - 3 if eval_date.month >= 4 else eval_date.month + 9)

            _logger.warning("""[80E_COMPARE_TRACE] CALCULATION_CASE
case=%s
declared_80e=%s
approved_80e=%s
final_80e_deduction=%s
annual_gross_income=%s
total_deductions=%s
taxable_income=%s
tax_before_rebate=%s
rebate=%s
cess=%s
annual_tax_liability=%s
previous_payslip_count=%s
previous_tds=%s
balance_tax=%s
distribution_months=%s
current_month_tds=%s
formula: balance_tax = annual_tax_liability (%s) - previous_tds (%s) = %s
formula: current_tds = balance_tax (%s) / distribution_months (%s) = %s""",
                case_name,
                declared_80e_val,
                sec_80e_val,
                sec_80e_val,
                annual_projection.gross_total_income,
                deduction_calc.total_allowable_deductions,
                taxable_inc.net_taxable_income,
                slab_calc.base_tax_liability,
                rebate_calc.rebate_applied,
                cess_calc.cess_amount,
                cess_calc.total_annual_tax_liability,
                prev_cnt,
                monthly_tds.total_tds_paid_so_far,
                monthly_tds.remaining_annual_tax_liability,
                monthly_tds.remaining_payroll_periods,
                monthly_tds.current_month_tds,
                cess_calc.total_annual_tax_liability, monthly_tds.total_tds_paid_so_far, monthly_tds.remaining_annual_tax_liability,
                monthly_tds.remaining_annual_tax_liability, monthly_tds.remaining_payroll_periods, monthly_tds.current_month_tds
            )

            _logger.warning("""[80E_COMPARE_TRACE] CONTEXT_CONSISTENCY
case=%s
income=%s
tax regime=%s
previous TDS=%s
remaining months=%s
tax calculation method=%s
deduction aggregation=%s""",
                case_name,
                annual_projection.gross_total_income,
                regime_code.upper(),
                monthly_tds.total_tds_paid_so_far,
                monthly_tds.remaining_payroll_periods,
                "IncomeTaxSlabService.calculate_base_tax (Old Regime Slabs)",
                f"DeductionCalculationService (Standard: {deduction_calc.standard_deduction}, VI-A: {deduction_calc.total_chapter_6a})"
            )

            # ── EXTRACT VARIABLES & LOG ALL 15 [TDS_DEBUG_TRACE] STAGES ─────────
            contract = getattr(employee, 'contract_id', False) or (employee.contract_ids[0] if getattr(employee, 'contract_ids', False) else False)
            contract_wage = float(contract.wage or 0.0) if contract else 0.0
            contract_id = contract.id if contract else 'N/A'

            # 1. AT METHOD ENTRY
            _logger.warning("""[TDS_DEBUG_TRACE] ENTER hds_in_compute_tds
employee_id=%s
employee_name=%s
contract_id=%s
date_from=%s
date_to=%s
tax_regime=%s
financial_year=%s
contract_wage=%s""",
                employee.id, employee.name, contract_id,
                getattr(payslip, 'date_from', eval_date), getattr(payslip, 'date_to', eval_date),
                regime_code, fy_name, contract_wage
            )

            # 2. SHOW ANNUAL INCOME INPUTS
            fy_emp_months = max(1, (sal_proj.months_elapsed + sal_proj.months_remaining) if sal_proj else 12)
            _logger.warning("""[TDS_DEBUG_TRACE] INCOME_COMPONENT
code=BASIC
name=Basic Salary
monthly=%s
annual=%s
included=True""", sal_proj.total_basic / float(fy_emp_months) if sal_proj.total_basic else 0.0, sal_proj.total_basic)

            _logger.warning("""[TDS_DEBUG_TRACE] INCOME_COMPONENT
code=HRA
name=House Rent Allowance
monthly=%s
annual=%s
included=True""", sal_proj.total_hra / float(fy_emp_months) if sal_proj.total_hra else 0.0, sal_proj.total_hra)

            _logger.warning("""[TDS_DEBUG_TRACE] INCOME_COMPONENT
code=DA
name=Dearness Allowance
monthly=%s
annual=%s
included=True""", sal_proj.total_da / float(fy_emp_months) if sal_proj.total_da else 0.0, sal_proj.total_da)

            _logger.warning("""[TDS_DEBUG_TRACE] INCOME_COMPONENT
code=ALLOWANCES
name=Other Allowances
monthly=%s
annual=%s
included=True""", sal_proj.total_allowances / float(fy_emp_months) if sal_proj.total_allowances else 0.0, sal_proj.total_allowances)

            if prev_emp.taxable_salary > 0:
                _logger.warning("""[TDS_DEBUG_TRACE] INCOME_COMPONENT
code=PREV_EMP
name=Previous Employer Income
monthly=0.0
annual=%s
included=True""", prev_emp.taxable_salary)

            if oth_inc.total_other_income != 0:
                _logger.warning("""[TDS_DEBUG_TRACE] INCOME_COMPONENT
code=OTHER_INC
name=Income from Other Sources
monthly=0.0
annual=%s
included=True""", oth_inc.total_other_income)

            # 3. SHOW PROJECTION
            current_inc = sal_proj.ytd_basic + sal_proj.ytd_da + sal_proj.ytd_hra + sal_proj.ytd_bonus + sal_proj.ytd_allowances
            projected_inc = sal_proj.projected_basic + sal_proj.projected_da + sal_proj.projected_hra + sal_proj.projected_bonus + sal_proj.projected_allowances
            gti = annual_projection.gross_total_income

            _logger.warning("""[TDS_DEBUG_TRACE] ANNUAL_PROJECTION
months_elapsed=%s
months_remaining=%s
previous_income=%s
current_income=%s
projected_income=%s
annual_gross_income=%s""",
                sal_proj.months_elapsed, sal_proj.months_remaining,
                prev_emp.taxable_salary, current_inc, projected_inc, gti
            )

            # 4. SHOW EXEMPTIONS
            hra_claimed = float(decl_for_log.decl_hra_annual_rent or 0.0) if decl_for_log else 0.0
            hra_allowed = deduction_calc.hra_exemption
            _logger.warning("""[TDS_DEBUG_TRACE] EXEMPTION
name=HRA
claimed=%s
eligible=%s
allowed=%s
deducted=%s""", hra_claimed, hra_allowed, hra_allowed, hra_allowed)

            home_loan_claimed = float(decl_for_log.decl_24b_self_interest or 0.0) if decl_for_log else 0.0
            home_loan_allowed = deduction_calc.home_loan_interest_24b
            _logger.warning("""[TDS_DEBUG_TRACE] EXEMPTION
name=Home Loan Sec 24(b)
claimed=%s
eligible=%s
allowed=%s
deducted=%s""", home_loan_claimed, home_loan_allowed, home_loan_allowed, home_loan_allowed)

            # 5. SHOW DEDUCTIONS
            std_ded_limit = 75000.0 if regime_code == 'new' else 50000.0
            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=Standard Deduction
claimed=%s
eligible=%s
limit=%s
allowed=%s""", deduction_calc.standard_deduction, deduction_calc.standard_deduction, std_ded_limit, deduction_calc.standard_deduction)

            c80_claimed = (
                float(getattr(decl_for_log, 'decl_80c_epf', 0.0) or 0.0) +
                float(getattr(decl_for_log, 'decl_80c_lic', 0.0) or 0.0) +
                float(getattr(decl_for_log, 'decl_80c_elss', 0.0) or 0.0) +
                float(getattr(decl_for_log, 'decl_80c_tuition', 0.0) or 0.0) +
                float(getattr(decl_for_log, 'decl_80c_ppf', 0.0) or 0.0) +
                float(getattr(decl_for_log, 'decl_80c_ssy', 0.0) or 0.0) +
                float(getattr(decl_for_log, 'decl_80c_fd', 0.0) or 0.0) +
                float(getattr(decl_for_log, 'decl_80c_nsc', 0.0) or 0.0) +
                float(getattr(decl_for_log, 'decl_80c_housing_principal', 0.0) or 0.0) +
                float(getattr(decl_for_log, 'decl_80c_other', 0.0) or 0.0)
            ) if decl_for_log else sec_80c_val
            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80C
claimed=%s
eligible=%s
limit=150000
allowed=%s""", c80_claimed, sec_80c_val, sec_80c_val)

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80CCD(1B)
claimed=%s
eligible=%s
limit=50000
allowed=%s""", decl_for_log.decl_80ccd1b_nps if decl_for_log else sec_80ccd1b_val, sec_80ccd1b_val, sec_80ccd1b_val)

            nps2_claimed = float(getattr(decl_for_log, 'decl_80ccd2_employer_nps', 0.0) or (next((l.declared_amount for l in decl_for_log.declaration_line_ids if l.category == '80ccd2'), 0.0) if decl_for_log else 0.0) or 0.0) if decl_for_log else emp_nps_80ccd2
            if nps2_claimed == 0.0:
                nps2_claimed = emp_nps_80ccd2
            emp_type = getattr(employee, 'hds_in_employer_category', getattr(employee, 'employer_type', 'private')) or 'private'
            nps2_pct = self.param_service.get_employer_nps_limit(regime=regime_code, employer_type=emp_type, eval_date=eval_date, as_decimal=True) or (0.14 if regime_code == 'new' else 0.10)
            nps2_limit = round(((sal_proj.total_basic or 0.0) + (sal_proj.total_da or 0.0)) * nps2_pct, 2) if sal_proj else emp_nps_80ccd2
            if nps2_limit == 0.0:
                nps2_limit = emp_nps_80ccd2

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80CCD(2)
claimed=%s
eligible=%s
limit=%s
allowed=%s""", nps2_claimed, emp_nps_80ccd2, nps2_limit, emp_nps_80ccd2)

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80D
claimed=%s
eligible=%s
limit=100000
allowed=%s""", (decl_for_log.decl_80d_self + decl_for_log.decl_80d_parents) if decl_for_log else sec_80d_val, sec_80d_val, sec_80d_val)

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80DD
claimed=%s
eligible=%s
limit=125000
allowed=%s""", sec_80dd_val, sec_80dd_val, sec_80dd_val)

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80TTA/80TTB
claimed=%s
eligible=%s
limit=50000
allowed=%s""", sec_80tta_val, sec_80tta_val, sec_80tta_val)

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80EEA
claimed=%s
eligible=%s
limit=150000
allowed=%s""", sec_80eea_val, sec_80eea_val, sec_80eea_val)

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=57(iia)
claimed=%s
eligible=%s
limit=15000
allowed=%s""", fam_pension_57 * 3.0 if fam_pension_57 > 0 else 0.0, fam_pension_57, fam_pension_57)

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80CCH
claimed=%s
eligible=%s
limit=0
allowed=%s""", decl_80cch_claimed, sec_80cch_val, sec_80cch_val)

            # 80GG deduction extraction for trace
            gg_declared = 0.0
            gg_verified = 0.0
            gg_approved = 0.0
            gg_eligible = sec_80gg_val
            gg_allowed = sec_80gg_val
            if decl_for_log:
                gg_ln = next((l for l in decl_for_log.declaration_line_ids if l.category == '80gg'), None)
                if gg_ln:
                    gg_declared = float(gg_ln.declared_amount or 0.0)
                    gg_verified = float(getattr(gg_ln, 'verified_amount', 0.0) or 0.0)
                    gg_approved = float(getattr(gg_ln, 'tax_firm_approved_amount', 0.0) or getattr(gg_ln, 'approved_amount', 0.0) or 0.0)
                    if decl_for_log.state in ('proof_verified', 'approved') and gg_approved == 0.0:
                        gg_eligible = 0.0
                        gg_allowed = 0.0
                else:
                    gg_declared = float(getattr(decl_for_log, 'decl_80gg_rent', 0.0) or 0.0)
                    if decl_for_log.state in ('proof_verified', 'approved'):
                        gg_approved = float(getattr(decl_for_log, 'decl_80gg_approved_rent', 0.0) or getattr(decl_for_log, 'decl_80gg_approved_amount', 0.0) or 0.0)
                        if gg_approved == 0.0:
                            gg_eligible = 0.0
                            gg_allowed = 0.0
                    else:
                        gg_approved = gg_declared

            _logger.warning("""[TDS_DEBUG_TRACE] DEDUCTION
section=80GG
declared=%s
verified=%s
approved=%s
eligible=%s
allowed=%s""", gg_declared, gg_verified, gg_approved, gg_eligible, gg_allowed)

            # 6. SHOW TAXABLE INCOME CALCULATION
            tot_exemptions = deduction_calc.hra_exemption + deduction_calc.home_loan_interest_24b
            tot_deductions = deduction_calc.total_allowable_deductions
            net_taxable_inc = taxable_inc.net_taxable_income

            _logger.warning("""[TDS_RECALC_TRACE][DEDUCTIONS]
standard_deduction=%s
chapter_6a_deductions=%s
total_allowable_deductions=%s""",
                int(deduction_calc.standard_deduction) if deduction_calc.standard_deduction == int(deduction_calc.standard_deduction) else deduction_calc.standard_deduction,
                int(total_c6a_val) if total_c6a_val == int(total_c6a_val) else total_c6a_val,
                int(tot_deductions) if tot_deductions == int(tot_deductions) else tot_deductions
            )

            _logger.warning("""[TDS_RECALC_TRACE][TAXABLE_INCOME]
gross_total_income=%s
total_deductions=%s
taxable_income=%s""",
                int(gti) if gti == int(gti) else gti,
                int(tot_deductions) if tot_deductions == int(tot_deductions) else tot_deductions,
                int(net_taxable_inc) if net_taxable_inc == int(net_taxable_inc) else net_taxable_inc
            )

            _logger.warning("""[TDS_DEBUG_TRACE] TAXABLE_INCOME_CALCULATION
annual_gross_income=%s
total_exemptions=%s
standard_deduction=%s
total_deductions=%s
taxable_income_before_rounding=%s
taxable_income_after_rounding=%s""",
                gti, tot_exemptions, deduction_calc.standard_deduction, tot_deductions,
                net_taxable_inc, net_taxable_inc
            )

            # 7. SHOW TAX SLAB CALCULATION
            for sb in (slab_breakdown if slab_breakdown else []):
                rate_pct = sb.get('rate', 0.0) * 100 if sb.get('rate', 0.0) <= 1 else sb.get('rate', 0.0)
                _logger.warning("""[TDS_DEBUG_TRACE] TAX_SLAB
lower=%s
upper=%s
taxable_in_slab=%s
rate=%s
tax=%s""",
                    sb.get('lower_limit', 0), sb.get('upper_limit', 0),
                    sb.get('taxable_in_slab', 0.0), rate_pct, sb.get('tax', 0.0)
                )

            # 8. SHOW TAX BEFORE REBATE
            base_tax = slab_calc.base_tax_liability
            _logger.warning("""[TDS_DEBUG_TRACE] TAX_BEFORE_REBATE
taxable_income=%s
tax_before_rebate=%s""", net_taxable_inc, base_tax)

            # 9. SHOW REBATE
            _logger.warning("""[TDS_DEBUG_TRACE] REBATE
rebate_eligible=%s
rebate_amount=%s
tax_after_rebate=%s""",
                rebate_applicable, rebate_calc.rebate_applied, rebate_calc.tax_after_rebate
            )

            # 10. SHOW SURCHARGE
            _logger.warning("""[TDS_DEBUG_TRACE] SURCHARGE
tax_before_surcharge=%s
surcharge_rate=%s
surcharge_amount=%s
tax_after_surcharge=%s""",
                rebate_calc.tax_after_rebate, surcharge_rate_val, surcharge_calc.surcharge_amount, tax_plus_surcharge
            )

            # 11. SHOW CESS
            _logger.warning("""[TDS_DEBUG_TRACE] CESS
cess_base=%s
cess_rate=%s
cess_amount=%s""", tax_plus_surcharge, cess_rate_val, cess_calc.cess_amount)

            # 12. SHOW FINAL ANNUAL TAX LIABILITY
            ann_tax_liab = cess_calc.total_annual_tax_liability

            _logger.warning("""[TDS_RECALC_TRACE][ANNUAL_TAX]
taxable_income=%s
tax_before_cess=%s
cess=%s
annual_tax_liability=%s""",
                int(net_taxable_inc) if net_taxable_inc == int(net_taxable_inc) else net_taxable_inc,
                int(tax_plus_surcharge) if tax_plus_surcharge == int(tax_plus_surcharge) else tax_plus_surcharge,
                int(cess_calc.cess_amount) if cess_calc.cess_amount == int(cess_calc.cess_amount) else cess_calc.cess_amount,
                int(ann_tax_liab) if ann_tax_liab == int(ann_tax_liab) else ann_tax_liab
            )

            _logger.warning("""[TDS_DEBUG_TRACE] FINAL_ANNUAL_TAX
tax_before_cess=%s
cess=%s
total_annual_tax_liability=%s""", tax_plus_surcharge, cess_calc.cess_amount, ann_tax_liab)

            # 13. SHOW MONTHLY TDS CALCULATION
            rem_periods = monthly_tds.remaining_payroll_periods or 1
            rem_liab = monthly_tds.remaining_annual_tax_liability
            raw_mth_tds = rem_liab / rem_periods if rem_periods else 0.0

            eval_m_n = eval_date.month if hasattr(eval_date, 'month') else 4
            eval_fy_i = eval_m_n - 3 if eval_m_n >= 4 else eval_m_n + 9
            m_names_d = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June',
                         7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'}
            curr_m_name = m_names_d.get(eval_m_n, str(eval_m_n))
            c_m_cnt = max(0, eval_fy_i - 1)
            f_m_cnt = max(0, 12 - eval_fy_i)

            _logger.warning("""[TDS_RECALC_TRACE][TDS_DISTRIBUTION]
annual_tax_liability=%s
previous_tds_deducted=%s
remaining_tax=%s
remaining_distribution_months=%s
current_month=%s
current_month_tds=%s""",
                int(ann_tax_liab) if ann_tax_liab == int(ann_tax_liab) else ann_tax_liab,
                int(monthly_tds.total_tds_paid_so_far) if monthly_tds.total_tds_paid_so_far == int(monthly_tds.total_tds_paid_so_far) else monthly_tds.total_tds_paid_so_far,
                int(rem_liab) if rem_liab == int(rem_liab) else rem_liab,
                rem_periods,
                curr_m_name,
                monthly_tds.current_month_tds
            )

            _logger.warning("""[TDS_DEBUG_TRACE][PAYROLL_MONTH_CONTEXT]
completed_payroll_months=%s
current_payroll_month=%s
future_payroll_months=%s
tds_distribution_months=%s""",
                c_m_cnt, curr_m_name, f_m_cnt, rem_periods
            )

            _logger.warning("""[TDS_DEBUG_TRACE] MONTHLY_TDS
annual_tax_liability=%s
months_remaining=%s
previous_tds_deducted=%s
current_month_tds_before_rounding=%s
current_month_tds=%s""",
                ann_tax_liab, rem_periods, monthly_tds.total_tds_paid_so_far,
                raw_mth_tds, monthly_tds.current_month_tds
            )

            # 14. IMPORTANT: TRACE PREVIOUS TDS
            prev_payslip_cnt = sal_proj.months_elapsed - 1 if sal_proj.months_elapsed > 0 else 0
            _logger.warning("""[TDS_DEBUG_TRACE] PREVIOUS_TDS
previous_payslip_count=%s
previous_tds=%s
annual_tax_liability=%s
balance_tax=%s
months_remaining=%s""",
                prev_payslip_cnt, monthly_tds.total_tds_paid_so_far, ann_tax_liab,
                rem_liab, rem_periods
            )

            # 15. TRACE THE EXACT RETURN
            _logger.warning("""[TDS_DEBUG_TRACE] RETURN
total_annual_tax_liability=%s
current_month_tds=%s""", ann_tax_liab, monthly_tds.current_month_tds)

            _logger.warning(detailed_trace)

        # Resolve active declaration record for audit snapshot & debug trace (single cached query with elevated permissions)
        decl = self.env['tds.employee.declaration'].sudo().search([
            ('employee_id', '=', employee.id),
            ('financial_year_id', '=', financial_year_id),
            ('state', '!=', 'rejected')
        ], limit=1)

        # Suppressed automated TDS_SNAPSHOT per user requirement so Audit Trail shows only
        # actual tax declarations made and employee Income Tax tab value changes.


        if debug_enabled:
            decl_rec = decl
            decl_info = f"ID {decl_rec.id} | State: {decl_rec.state}" if decl_rec else "None / No Declaration Found"

            annual_salary_val = float(annual_projection.salary_projection.total_projected_current_salary or 0.0)
            prev_emp_income_val = float(annual_projection.previous_employer_income.taxable_salary or 0.0)
            other_inc_val = float(annual_projection.other_income_aggregation.total_other_income or 0.0)
            gti_val = float(annual_projection.gross_total_income or 0.0)
            total_ded_val = float(deduction_calc.total_allowable_deductions or deduction_calc.total_approved_deductions or 0.0)
            taxable_val = float(taxable_inc.net_taxable_income or 0.0)
            gross_tax_val = float(slab_calc.base_tax_liability or 0.0)
            rebate_val = float(rebate_calc.rebate_applied or 0.0)
            surcharge_val = float(surcharge_calc.surcharge_amount or 0.0)
            cess_val = float(cess_calc.cess_amount or 0.0)
            annual_tax_liability_val = float(cess_calc.total_annual_tax_liability or 0.0)
            rem_months_val = monthly_tds.remaining_payroll_periods
            curr_tds_val = float(monthly_tds.current_month_tds or 0.0)

            # Identify the FIRST zero or unexpected value in the calculation pipeline
            first_zero_msg = "None (All core pipeline values are non-zero)"
            if annual_salary_val == 0:
                first_zero_msg = "Annual Salary (Current Employer Projected Salary is ₹0.00 - verify contract basic salary & allowances)"
            elif gti_val == 0:
                first_zero_msg = "Gross Total Income (GTI is ₹0.00)"
            elif taxable_val == 0:
                first_zero_msg = "Taxable Income (Net Taxable Income is ₹0.00 - deductions equal or exceed GTI)"
            elif gross_tax_val == 0:
                first_zero_msg = "Gross Tax (Base Tax Liability is ₹0.00 - taxable income falls within 0% tax slab)"
            elif annual_tax_liability_val == 0:
                first_zero_msg = "Annual Tax Liability (Final Tax Liability is ₹0.00 - offset by 87A rebate)"
            elif rem_months_val == 0:
                first_zero_msg = "Remaining TDS Months (Configured / calculated remaining payroll periods is 0)"
            elif curr_tds_val == 0:
                first_zero_msg = "Current Month TDS (Current Month TDS is ₹0.00 - YTD TDS already deducted equals or exceeds annual liability)"

            payslip_name = payslip.name if payslip and hasattr(payslip, 'name') else 'N/A'
            date_from_str = payslip.date_from if payslip and hasattr(payslip, 'date_from') else 'N/A'
            date_to_str = payslip.date_to if payslip and hasattr(payslip, 'date_to') else eval_date

            # Configuration-driven redistribution months count (e.g., 3 for final 3 months of FY)
            dist_m = max(1, min(12, int(getattr(financial_year, 'tds_recalculation_distribution_months', 3) or 3)))
            recalc_start_fy_idx = 12 - dist_m + 1

            eval_m_num = eval_date.month if hasattr(eval_date, 'month') else 4
            fy_start = financial_year.start_date if financial_year else False
            if fy_start:
                fy_start_year = fy_start.year
                fy_start_month = fy_start.month
                eval_year = eval_date.year
                eval_month = eval_date.month
                elapsed_months = (eval_year - fy_start_year) * 12 + (eval_month - fy_start_month) + 1
                eval_fy_idx = min(12, max(1, elapsed_months))
            else:
                eval_fy_idx = eval_m_num - 3 if eval_m_num >= 4 else eval_m_num + 9

            is_recalc_active = (eval_fy_idx >= recalc_start_fy_idx)

            month_names_dict = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June',
                                7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'}
            payroll_month_name = month_names_dict.get(eval_m_num, str(eval_m_num))
            start_cal_m = recalc_start_fy_idx + 3 if recalc_start_fy_idx <= 9 else recalc_start_fy_idx - 9
            recalc_month_name = month_names_dict.get(start_cal_m, str(start_cal_m))

            other_agg = annual_projection.other_income_aggregation
            raw_hp_inc = float(getattr(other_agg, 'net_house_property_income_loss', 0.0) or 0.0)
            hp_loss_val = float(abs(raw_hp_inc) if raw_hp_inc < 0 else 0.0)
            hp_limit_val = float(getattr(other_agg, 'hp_loss_limit', 0.0) or 0.0)
            hp_setoff_val = float(getattr(other_agg, 'allowed_hp_loss_set_off', 0.0) or 0.0)
            hp_eff_gti_val = float(getattr(other_agg, 'effective_hp_gti_impact', 0.0) or 0.0)

            hp_sec24b_trace = f"""
========================================================
[SECTION 24(b) & HOUSE PROPERTY DEBUG TRACE]
========================================================
1. Self-Occupied Home Loan:
   Field: decl_24b_self_interest (via HomeLoanDeductionService)
   Section 24(b) - Self-Occupied Home Loan Interest: ₹{deduction_calc.home_loan_interest_24b:,.2f}

2. Let-Out Property:
   Field: let_out_interest_paid (via OtherIncomeAggregationService)
   Section 24(b) - Let-Out Property Interest       : ₹{float(getattr(other_agg, 'let_out_interest', 0.0) or 0.0):,.2f}
   Gross Annual Rent                              : ₹{float(getattr(other_agg, 'gross_let_out_rent', 0.0) or 0.0):,.2f}
   Municipal Taxes Paid                           : ₹{float(getattr(other_agg, 'municipal_taxes', 0.0) or 0.0):,.2f}
   Net Annual Value (NAV)                         : ₹{float(getattr(other_agg, 'nav', 0.0) or 0.0):,.2f}
   30% Section 24(a) Deduction                    : ₹{float(getattr(other_agg, 'property_std_deduction', 0.0) or 0.0):,.2f}
   Raw House Property Income/Loss                 : ₹{raw_hp_inc:,.2f}
   House Property Loss Amount                     : ₹{hp_loss_val:,.2f}
   Tax Regime                                     : {regime_code.upper()}
   Allowed House Property Loss Set-Off            : ₹{hp_setoff_val:,.2f}
   Effective GTI Impact                           : ₹{hp_eff_gti_val:,.2f}
   Other Sources Income                           : ₹{float(getattr(other_agg, 'total_other_sources', 0.0) or 0.0):,.2f}
   Final Other Income Returned to Engine          : ₹{other_inc_val:,.2f}
========================================================
"""

            tds_debug_trace = f"""
========================================================
TDS DEBUG
========================================================
Employee                 : {employee.name} (ID: {employee.id})
Payslip                  : {payslip_name}
Date From                : {date_from_str}
Date To                  : {date_to_str}
Financial Year           : {financial_year.name if financial_year else 'N/A'}
Declaration              : {decl_info}

Payroll Month            : {payroll_month_name}
Recalculation Start Month: {recalc_month_name}
Recalculation Active     : {'YES' if is_recalc_active else 'NO (Normal FY Projection Mode)'}
Distribution Months      : {dist_m}

Annual Salary            : ₹{annual_salary_val:,.2f}
Previous Employer Income : ₹{prev_emp_income_val:,.2f}
Other Income             : ₹{other_inc_val:,.2f}
Gross Total Income       : ₹{gti_val:,.2f}

Total Deductions         : ₹{total_ded_val:,.2f}
Taxable Income           : ₹{taxable_val:,.2f}

Gross Tax                : ₹{gross_tax_val:,.2f}
87A Rebate               : ₹{rebate_val:,.2f}
Surcharge                : ₹{surcharge_val:,.2f}
Cess                     : ₹{cess_val:,.2f}
Annual Tax Liability     : ₹{annual_tax_liability_val:,.2f}

Remaining TDS Months     : {rem_months_val}
Current Month TDS        : ₹{curr_tds_val:,.2f}

--------------------------------------------------------
DIAGNOSTIC PIPELINE CHECK:
First Zero / Incorrect Value : {first_zero_msg}
========================================================
"""
            _logger.warning(hp_sec24b_trace)
            _logger.warning(tds_debug_trace)

        return TdsComputationResult(
            employee_id=employee.id,
            financial_year_id=financial_year_id,
            regime_code=regime_code,
            regime_name=regime_name,
            annual_income_projection=annual_projection,
            deduction_calculation=deduction_calc,
            taxable_income=taxable_inc,
            income_tax_slab=slab_calc,
            rebate_engine=rebate_calc,
            surcharge_engine=surcharge_calc,
            health_education_cess=cess_calc,
            monthly_tds_distribution=monthly_tds,
            calculation_run_id=calc_run_id,
            previous_annual_tax=tax_before_proof
        )


