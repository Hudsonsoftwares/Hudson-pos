# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import fields
# pyrefly: ignore [missing-import]
from odoo.exceptions import ValidationError
from ..base import BaseStatutoryService

from .tds_parameter_service import TdsParameterService
from .salary_projection_service import SalaryProjectionService
from .previous_employer_income_service import PreviousEmployerIncomeService, PreviousEmployerIncomeResult
from .other_income_aggregation_service import OtherIncomeAggregationService
from .regime_routing_service import RegimeRoutingService

_logger = logging.getLogger(__name__)


class AnnualIncomeProjectionResult:
    """
    Data Transfer Object (DTO) holding the complete result of Phase 4 Annual Income Projection
    and Tax Regime Resolution orchestration.
    """
    def __init__(self, employee_id, financial_year_id, regime_code, regime_name,
                 salary_projection, previous_employer_income, other_income_aggregation,
                 projected_annual_salary, gross_total_income, regime_context,
                 sec_17_2_vii_perquisite=0.0, total_annual_employer_epf=0.0,
                 actual_employer_nps=0.0, combined_employer_contribution=0.0,
                 combined_ceiling=750000.0):
        self.employee_id = employee_id
        self.financial_year_id = financial_year_id
        self.regime_code = regime_code
        self.regime_name = regime_name
        self.salary_projection = salary_projection
        self.previous_employer_income = previous_employer_income
        self.other_income_aggregation = other_income_aggregation
        self.projected_annual_salary = projected_annual_salary
        self.gross_total_income = gross_total_income
        self.regime_context = regime_context
        self.sec_17_2_vii_perquisite = sec_17_2_vii_perquisite
        self.total_annual_employer_epf = total_annual_employer_epf
        self.actual_employer_nps = actual_employer_nps
        self.combined_employer_contribution = combined_employer_contribution
        self.combined_ceiling = combined_ceiling

    @property
    def current_employer_salary(self):
        """Current employer projected annual salary."""
        return self.salary_projection.total_projected_current_salary if self.salary_projection else 0.0


class AnnualIncomeProjectionService(BaseStatutoryService):
    """
    Phase 4 Master Orchestration Service: Annual Income Projection & Tax Regime Resolution Engine.
    Orchestrates:
    1. Financial Year Resolution (via TdsParameterService)
    2. Employee Tax Regime Selection Resolution ('old' vs 'new')
    3. Annual Current Salary Projection (via SalaryProjectionService)
    4. Previous Employer Income Aggregation (via PreviousEmployerIncomeService)
    5. Non-Payroll Other Income Aggregation (via OtherIncomeAggregationService)
    6. Gross Total Income (GTI) Aggregation
    7. Regime Context Routing Pipeline (via RegimeRoutingService)
    """

    def resolve_employee_regime(self, employee, financial_year):
        """
        Resolves the employee's selected Tax Regime for the specified Financial Year.
        Selected regime is retrieved from the authoritative tds.employee.tax.regime record,
        with fallback to tds.employee.declaration header if master record is absent.
        """
        company = employee.company_id or self.env.company
        policy = getattr(company, 'hds_in_default_tax_regime', 'flexible')

        decl_rec = self.env['tds.employee.declaration'].sudo().search([
            ('employee_id', '=', employee.id),
            ('financial_year_id', '=', financial_year.id)
        ], limit=1)
        ui_regime = decl_rec.tax_regime_id.code if (decl_rec and decl_rec.tax_regime_id) else 'None'

        regime_rec = self.env['tds.employee.tax.regime'].sudo().search([
            ('employee_id', '=', employee.id),
            ('financial_year_id', '=', financial_year.id)
        ], limit=1)

        found_master = bool(regime_rec and regime_rec.regime_id)
        regime_rec_id = regime_rec.id if found_master else 'None'
        
        reason_default = "N/A"
        if policy == 'new':
            resolved_code = 'new'
            default_regime = self.env['tds.tax.regime'].search([('code', '=', 'new')], limit=1)
            resolved_name = default_regime.name if default_regime else 'New Tax Regime Income-tax Act, 2025 — Section 202(1)'
            reason_default = "Company TDS configuration mandates New Tax Regime Income-tax Act, 2025 — Section 202(1) for all employees."
        elif policy == 'old':
            resolved_code = 'old'
            default_regime = self.env['tds.tax.regime'].search([('code', '=', 'old')], limit=1)
            resolved_name = default_regime.name if default_regime else 'Old Tax Regime'
            reason_default = "Company TDS configuration mandates Old Tax Regime for all employees."
        elif found_master:
            resolved_code = regime_rec.regime_id.code.lower()
            resolved_name = regime_rec.regime_id.name
        elif decl_rec and decl_rec.tax_regime_id:
            # Fallback to UI declaration header regime choice if master record absent
            resolved_code = decl_rec.tax_regime_id.code.lower()
            resolved_name = decl_rec.tax_regime_id.name
            reason_default = "Fallback to Declaration Header regime choice because tds.employee.tax.regime master record was un-synchronized."
        else:
            default_regime = self.env['tds.tax.regime'].search([('code', '=', 'new')], limit=1)
            resolved_code = 'new'
            resolved_name = default_regime.name if default_regime else 'New Tax Regime Income-tax Act, 2025 — Section 202(1)'
            reason_default = "No tds.employee.tax.regime master record OR tds.employee.declaration header choice found for (employee_id, financial_year_id); applying Income-tax Act, 2025 Section 202(1) statutory default."

        _logger.info(
            "\n==================================================\n"
            "REGIME RESOLUTION TRACE\n"
            "==================================================\n"
            "Employee ID                           : %s (%s)\n"
            "Financial Year                        : %s (ID: %s)\n"
            "Declaration ID                        : %s\n"
            "UI Selected Regime                    : %s\n"
            "tds.employee.tax.regime record found? : %s\n"
            "Regime Record ID                      : %s\n"
            "Resolved Regime Code                  : %s\n"
            "Reason for defaulting to NEW          : %s\n"
            "==================================================",
            employee.id if employee else 'N/A', employee.name if employee else 'N/A',
            financial_year.name if financial_year else 'N/A', financial_year.id if financial_year else 'N/A',
            decl_rec.id if decl_rec else 'None',
            ui_regime,
            found_master,
            regime_rec_id,
            resolved_code.upper(),
            reason_default
        )

        return resolved_code, resolved_name

    def _extract_payslip_employer_epf(self, slip):
        """
        Extracts the total monthly employer EPF contribution from a payslip.
        Avoids double-counting total and breakdown lines (e.g. EMPLOYER_EPF vs EPS + EPF_SHARE).
        Prioritizes the active transient evaluation context (_eval_contexts) during
        active compute_sheet execution to avoid reading stale line_ids from a prior run.
        """
        if not slip:
            return 0.0

        TOTAL_CODES = ('EMPLOYER_EPF', 'EPF_ER', 'ER_PF', 'EMPLOYER_EPF_TOTAL')
        PART_CODES = ('EPF_SHARE', 'EPS')

        # 0. Active evaluation context (in-flight computation during compute_sheet)
        HrPayslipModel = self.env['hr.payslip']
        eval_ctx = getattr(HrPayslipModel, '_eval_contexts', {}).get(slip.id) if hasattr(HrPayslipModel, '_eval_contexts') else None
        if eval_ctx:
            for code in TOTAL_CODES:
                if code in eval_ctx:
                    amt = abs(float(eval_ctx[code] or 0.0))
                    if amt > 0.0:
                        return amt
            part_sum = 0.0
            for code in PART_CODES:
                if code in eval_ctx:
                    part_sum += abs(float(eval_ctx[code] or 0.0))
            if part_sum > 0.0:
                return part_sum

        # 1. First priority: Direct total employer EPF rule code
        for line in slip.line_ids:
            if (line.code or '').upper() in TOTAL_CODES:
                amt = float(line.total or 0.0)
                if amt == 0.0 and hasattr(line, 'amount') and line.amount:
                    amt = float(line.amount)
                if abs(amt) > 0.0:
                    return abs(amt)

        # 2. Second priority: If no aggregate total line, sum sub-components (EPS + EPF_SHARE)
        part_sum = 0.0
        for line in slip.line_ids:
            if (line.code or '').upper() in PART_CODES:
                amt = float(line.total or 0.0)
                if amt == 0.0 and hasattr(line, 'amount') and line.amount:
                    amt = float(line.amount)
                part_sum += abs(amt)
        if part_sum > 0.0:
            return part_sum

        # 3. Third priority: Payslip header field if set
        if hasattr(slip, 'hds_in_employer_epf') and slip.hds_in_employer_epf > 0.0:
            return float(slip.hds_in_employer_epf)

        return 0.0

    def project_annual_income(self, employee, eval_date=None, payslip=None):
        """
        Master orchestration method for Phase 4 Annual Income Projection.

        :param employee: hr.employee record
        :param eval_date: Date (optional evaluation date)
        :return: AnnualIncomeProjectionResult
        """
        if not employee:
            raise ValidationError("Annual Income Projection Error: Employee record is required.")

        eval_date = eval_date or fields.Date.today()
        tds_param_svc = TdsParameterService(self.env)

        # 1. Resolve Financial Year (raises ValidationError if unconfigured)
        financial_year = tds_param_svc.get_financial_year(eval_date=eval_date)
        if not financial_year:
            raise ValidationError(f"Annual Income Projection Error: No active Financial Year found for date {eval_date}.")

        # 2. Resolve Employee Selected Tax Regime
        regime_code, regime_name = self.resolve_employee_regime(employee, financial_year)

        # 3. Project Current Employer Salary via PayrollIncomeProjectionService / SalaryProjectionService
        salary_svc = SalaryProjectionService(self.env)
        salary_proj = salary_svc.project_salary(employee, financial_year, eval_date=eval_date, payslip=payslip)

        # 4. Aggregate Previous Employer Income
        prev_emp_svc = PreviousEmployerIncomeService(self.env)
        prev_emp_inc = prev_emp_svc.aggregate_previous_employer_income(employee, financial_year)

        _logger.warning(
            "[ANNUAL_PROJ] prev_emp_inc | taxable_salary=%s | tds_deducted=%s | has_declaration=%s",
            prev_emp_inc.taxable_salary, prev_emp_inc.tds_deducted, prev_emp_inc.has_declaration
        )

        # Safety net: if the service returned 0 / no declaration, do one final direct read
        # from tds.employee.income.declaration so the value is NEVER silently dropped from GTI.
        if not prev_emp_inc.has_declaration or prev_emp_inc.taxable_salary == 0.0:
            _direct = self.env['tds.employee.income.declaration'].sudo().search([
                ('employee_id', '=', employee.id),
                ('financial_year_id', '=', financial_year.id),
            ], limit=1)
            if _direct and (_direct.prev_employer_taxable_gross or _direct.prev_employer_tds):
                _logger.warning(
                    "[ANNUAL_PROJ] Safety fallback: direct inc_decl found | "
                    "prev_gross=%s | tds=%s",
                    float(_direct.prev_employer_taxable_gross or 0.0),
                    float(_direct.prev_employer_tds or 0.0)
                )
                prev_emp_inc = PreviousEmployerIncomeResult(
                    taxable_salary=float(_direct.prev_employer_taxable_gross or 0.0),
                    tds_deducted=float(_direct.prev_employer_tds or 0.0),
                    pt_deducted=float(_direct.prev_employer_pt or 0.0),
                    pf_contributed=float(_direct.prev_employer_pf or 0.0),
                    has_declaration=True
                )

        # 5. Aggregate Other Non-Payroll Income (Regime-aware HP loss set-off)
        other_inc_svc = OtherIncomeAggregationService(self.env)
        other_inc_agg = other_inc_svc.aggregate_other_income(employee, financial_year, regime_code=regime_code, eval_date=eval_date)

        # 6. Aggregate Projected Annual Salary & Gross Total Income (GTI)
        current_employer_income = salary_proj.total_projected_current_salary
        prev_emp_income = prev_emp_inc.taxable_salary
        other_income_val = other_inc_agg.total_other_income

        _logger.warning(
            "[ANNUAL_PROJ] GTI | current_employer=%.2f | prev_employer=%.2f | other=%.2f",
            current_employer_income, prev_emp_income, other_income_val
        )

        projected_annual_salary = current_employer_income + prev_emp_income
        gross_total_income = projected_annual_salary + other_income_val

        # ── 6b. Section 17(2)(vii): Employer Contribution Perquisite ─────────────
        # Under Section 17(2)(vii), when an employer's combined annual contributions
        # to EPF + NPS + Approved Superannuation Fund exceed ₹7,50,000 (configurable
        # via HDS_IN_TDS_EMPLOYER_CONTRIBUTION_LIMIT), the excess is a taxable perquisite
        # added to Gross Salary and Gross Total Income (GTI).

        fy_start = financial_year.start_date
        fy_end = financial_year.end_date

        # 1. Aggregate Year-To-Date (YTD) employer EPF from payslips
        fy_payslips = self.env['hr.payslip'].search([
            ('employee_id', '=', employee.id),
            ('date_from', '>=', fy_start),
            ('date_to', '<=', eval_date),
            ('state', 'in', ['done', 'paid']),
        ])
        ytd_employer_epf = sum(self._extract_payslip_employer_epf(slip) for slip in fy_payslips)

        # 2. Project remaining months employer EPF
        paid_months_count = len(fy_payslips)
        from .payroll_period_service import PayrollPeriodService
        period_svc = PayrollPeriodService(self.env)
        total_fy_periods = period_svc.calculate_total_periods_in_fy(employee, financial_year, eval_date=eval_date) if (employee and financial_year) else 12
        total_fy_months = int(total_fy_periods or 12)
        remaining_projection_months = max(0, total_fy_months - paid_months_count)
        projected_employer_epf = 0.0

        if paid_months_count > 0:
            monthly_avg_epf = ytd_employer_epf / paid_months_count
            projected_employer_epf = monthly_avg_epf * remaining_projection_months
        elif getattr(employee, 'hds_in_epf_applicable', False):
            # Check passed payslip or draft payslip in current run if available
            draft_slip = payslip or self.env['hr.payslip'].search([
                ('employee_id', '=', employee.id),
                ('date_from', '>=', fy_start),
                ('date_to', '<=', fy_end),
                ('state', '=', 'draft'),
            ], limit=1)
            monthly_est = self._extract_payslip_employer_epf(draft_slip)

            if monthly_est <= 0.0:
                contract = salary_svc._get_employee_contract(employee) if hasattr(salary_svc, '_get_employee_contract') else False
                contract_basic = float(getattr(contract, 'basic_salary', 0.0) or getattr(contract, 'wage', 0.0) or 0.0) if contract else 0.0
                contract_da = float(getattr(contract, 'da', 0.0) or getattr(contract, 'da_amount', 0.0) or 0.0) if contract else 0.0
                actual_wage = contract_basic + contract_da
                basis = getattr(employee, 'hds_in_pf_employer_basis', False) or getattr(employee, 'hds_in_pf_contribution_basis', 'statutory_ceiling')
                pf_ceiling = tds_param_svc.get_parameter('PF_WAGE_CEILING', eval_date=eval_date, default_val=25000.0) or 25000.0
                if getattr(employee, 'hds_in_is_international_worker', False) or basis in ('actual_pf_wage', 'actual_basic'):
                    wage_base = actual_wage
                else:
                    wage_base = min(actual_wage, pf_ceiling)
                monthly_est = round(wage_base * 0.12, 2)

            projected_employer_epf = monthly_est * remaining_projection_months

        total_annual_employer_epf = ytd_employer_epf + projected_employer_epf

        # 3. Retrieve actual declared Employer NPS contribution
        decl_for_perq = self.env['tds.employee.declaration'].sudo().search([
            ('employee_id', '=', employee.id),
            ('financial_year_id', '=', financial_year.id),
        ], limit=1)
        actual_employer_nps = 0.0
        if decl_for_perq:
            nps_lines = [l for l in decl_for_perq.declaration_line_ids if l.category == '80ccd2' and getattr(l, 'active', True)]
            if nps_lines:
                actual_employer_nps = sum(float(l.declared_amount or 0.0) for l in nps_lines)
            if actual_employer_nps == 0.0:
                actual_employer_nps = float(getattr(decl_for_perq, 'decl_80ccd2_employer_nps', 0.0) or 0.0)

        # 4. Resolve statutory aggregate ceiling via TdsParameterService
        combined_ceiling = tds_param_svc.get_combined_employer_contribution_limit(eval_date=eval_date) or 750000.0

        # 5. Calculate Section 17(2)(vii) perquisite
        combined_employer_contribution = total_annual_employer_epf + actual_employer_nps
        sec_17_2_vii_perquisite = max(0.0, round(combined_employer_contribution - combined_ceiling, 2))

        # 6. Add taxable perquisite to Gross Salary and GTI
        if sec_17_2_vii_perquisite > 0.0:
            projected_annual_salary += sec_17_2_vii_perquisite
            gross_total_income += sec_17_2_vii_perquisite
            _logger.warning(
                "[SEC17_2_VII] Employee '%s' (FY %s): Employer EPF=₹%.2f + Actual NPS=₹%.2f = Combined ₹%.2f > Ceiling ₹%.2f → Taxable Perquisite ₹%.2f added to GTI",
                employee.name, financial_year.name, total_annual_employer_epf, actual_employer_nps,
                combined_employer_contribution, combined_ceiling, sec_17_2_vii_perquisite
            )

        summary_log = f"""
========================================================
ANNUAL INCOME PROJECTION SERVICE
========================================================
Regime Code               : {regime_code.upper()} ({regime_name})
Current Employer Salary   : ₹{current_employer_income:,.2f}
Previous Employer Income  : ₹{prev_emp_income:,.2f}
Employer EPF (Annual)     : ₹{total_annual_employer_epf:,.2f}
Employer NPS (Actual)     : ₹{actual_employer_nps:,.2f}
Combined Employer Contrib : ₹{combined_employer_contribution:,.2f}
Sec 17(2)(vii) Ceiling    : ₹{combined_ceiling:,.2f}
Sec 17(2)(vii) Perquisite : ₹{sec_17_2_vii_perquisite:,.2f}
Projected Annual Salary   : ₹{projected_annual_salary:,.2f}
Other Sources Income      : ₹{other_inc_agg.total_other_sources:,.2f}
Raw HP Net Income/Loss    : ₹{other_inc_agg.net_house_property_income_loss:,.2f}
Applicable HP Loss Limit  : ₹{other_inc_agg.hp_loss_limit:,.2f}
Allowed HP Loss Set-Off   : ₹{other_inc_agg.allowed_hp_loss_set_off:,.2f}
Effective HP Impact on GTI: ₹{other_inc_agg.effective_hp_gti_impact:,.2f}
Total Other Income        : ₹{other_income_val:,.2f}
Gross Total Income (GTI)  : ₹{gross_total_income:,.2f}

Formula:
Projected Annual Salary = Current Employer Salary + Previous Employer Income + Sec 17(2)(vii) Perquisite
Other Income = Other Sources + Effective HP Impact
GTI = Projected Annual Salary + Other Income
========================================================
"""
        _logger.warning(summary_log)

        # 7. Prepare Regime Routing Calculation Context Pipeline
        routing_svc = RegimeRoutingService(self.env)
        regime_context = routing_svc.prepare_regime_context(
            employee=employee,
            financial_year=financial_year,
            regime_code=regime_code,
            gross_total_income=gross_total_income,
            eval_date=eval_date,
            gross_salary_income=projected_annual_salary
        )

        return AnnualIncomeProjectionResult(
            employee_id=employee.id,
            financial_year_id=financial_year.id,
            regime_code=regime_code,
            regime_name=regime_name,
            salary_projection=salary_proj,
            previous_employer_income=prev_emp_inc,
            other_income_aggregation=other_inc_agg,
            projected_annual_salary=projected_annual_salary,
            gross_total_income=gross_total_income,
            regime_context=regime_context,
            sec_17_2_vii_perquisite=sec_17_2_vii_perquisite,
            total_annual_employer_epf=total_annual_employer_epf,
            actual_employer_nps=actual_employer_nps,
            combined_employer_contribution=combined_employer_contribution,
            combined_ceiling=combined_ceiling
        )
