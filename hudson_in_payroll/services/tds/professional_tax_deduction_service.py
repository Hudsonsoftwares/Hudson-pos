# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import fields
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class ProfessionalTaxDeductionResult:
    """
    Data Transfer Object (DTO) holding Section 16(iii) Professional Tax deduction details.
    """
    def __init__(self, allowed_pt_deduction=0.0, ytd_paid_pt=0.0, prev_employer_pt=0.0,
                 current_slip_pt=0.0, projected_future_pt=0.0, total_annual_pt=0.0,
                 statutory_cap=2500.0, is_eligible=False, remarks=""):
        self.allowed_pt_deduction = float(allowed_pt_deduction or 0.0)
        self.ytd_paid_pt = float(ytd_paid_pt or 0.0)
        self.prev_employer_pt = float(prev_employer_pt or 0.0)
        self.current_slip_pt = float(current_slip_pt or 0.0)
        self.projected_future_pt = float(projected_future_pt or 0.0)
        self.total_annual_pt = float(total_annual_pt or 0.0)
        self.statutory_cap = float(statutory_cap or 2500.0)
        self.is_eligible = is_eligible
        self.remarks = remarks


class ProfessionalTaxDeductionService(BaseStatutoryService):
    """
    Phase 5 Service: Section 16(iii) Professional Tax Deduction Service.
    Calculates statutory deduction for Professional Tax under Section 16(iii) of the Income-tax Act, 1961.
    - Old Tax Regime: PT actually paid (YTD paid on payslips + Previous Employer PT declared on Form 12B
      + projected remaining months in FY) is deductible from Income under the head 'Salaries',
      capped at the constitutional limit of ₹2,500/year (Article 276(2) of the Constitution of India).
    - New Tax Regime: Disallowed by statute under Section 115BAC (returns ₹0.0).
    """

    def calculate_pt_deduction(self, employee, financial_year, regime_code='old',
                              eval_date=None, gross_payroll_income=0.0,
                              payslip=None, annual_projection=None):
        """
        Master calculation method for Section 16(iii) Professional Tax deduction.

        :param employee: hr.employee record
        :param financial_year: tds.financial.year record
        :param regime_code: str ('old' or 'new')
        :param eval_date: Date (optional)
        :param gross_payroll_income: float (Annual gross salary income)
        :param payslip: hr.payslip record (optional)
        :param annual_projection: AnnualIncomeProjectionResult (optional)
        :return: ProfessionalTaxDeductionResult
        """
        regime = (regime_code or 'new').lower()

        # 0. Statutory Regime Check: Section 115BAC prohibits Section 16(iii) in New Regime
        if regime != 'old':
            _logger.info(
                "[SECTION_16III_PT] Skipped: Section 16(iii) Professional Tax deduction is not permitted under the New Tax Regime (Employee: %s).",
                employee.name if employee else 'N/A'
            )
            return ProfessionalTaxDeductionResult(
                allowed_pt_deduction=0.0,
                is_eligible=False,
                remarks="Section 16(iii) deduction is not permitted under the New Tax Regime (Section 115BAC)."
            )

        if not employee or not financial_year:
            return ProfessionalTaxDeductionResult(
                allowed_pt_deduction=0.0,
                is_eligible=False,
                remarks="Employee or Financial Year record is missing."
            )

        eval_date = eval_date or fields.Date.today()
        if isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)

        company = employee.company_id or self.env.company
        fy_start = financial_year.start_date
        fy_end = financial_year.end_date

        emp_pt_app = getattr(employee, 'hds_in_pt_applicable', True)
        comp_pt_app = getattr(company, 'hds_in_enable_professional_tax', True)

        # 1. Previous Employer PT (Form 12B / Income Declaration)
        prev_emp_pt = 0.0
        if annual_projection and hasattr(annual_projection, 'previous_employer_income') and annual_projection.previous_employer_income:
            prev_emp_pt = float(getattr(annual_projection.previous_employer_income, 'pt_deducted', 0.0) or 0.0)
        else:
            try:
                from .previous_employer_income_service import PreviousEmployerIncomeService
                prev_svc = PreviousEmployerIncomeService(self.env)
                prev_res = prev_svc.aggregate_previous_employer_income(employee, financial_year)
                prev_emp_pt = float(getattr(prev_res, 'pt_deducted', 0.0) or 0.0)
            except Exception as e:
                _logger.debug("Failed aggregating previous employer PT: %s", e)

        # 2. Current Employer Year-To-Date (YTD) Paid PT from prior paid/done payslips in current FY
        slip_domain = [
            ('employee_id', '=', employee.id),
            ('date_from', '>=', fy_start),
            ('date_to', '<=', eval_date),
            ('state', 'in', ['done', 'paid'])
        ]
        if payslip and payslip.id:
            slip_domain.append(('id', '!=', payslip.id))

        paid_slips = self.env['hr.payslip'].search(slip_domain)

        PT_CODES = {'PT', 'PROF_TAX', 'PT_DED', 'PROFESSIONAL_TAX', 'HDS_IN_PT'}
        ytd_pt = 0.0
        for slip in paid_slips:
            slip_pt = 0.0
            for line in slip.line_ids:
                code = (line.code or '').upper()
                cat_code = (line.category_id.code or '').upper() if line.category_id else ''
                if code in PT_CODES or cat_code == 'PT' or (cat_code == 'DED' and 'PT' in code):
                    amt = float(line.total or 0.0)
                    if amt == 0.0 and hasattr(line, 'amount') and line.amount:
                        amt = float(line.amount)
                    slip_pt += abs(amt)
            if slip_pt > 0:
                ytd_pt += slip_pt
            elif hasattr(slip, 'hds_in_pt_amount') and slip.hds_in_pt_amount > 0:
                ytd_pt += float(slip.hds_in_pt_amount)

        # 3. Current Payslip PT
        current_slip_pt = 0.0
        HrPayslipModel = self.env['hr.payslip']
        eval_ctx = getattr(HrPayslipModel, '_eval_contexts', {}).get(payslip.id) if (payslip and hasattr(HrPayslipModel, '_eval_contexts')) else None
        if eval_ctx:
            for code in PT_CODES:
                if code in eval_ctx:
                    amt = abs(float(eval_ctx[code] or 0.0))
                    if amt > 0.0:
                        current_slip_pt = amt
                        break

        if current_slip_pt == 0.0 and payslip:
            for line in payslip.line_ids:
                code = (line.code or '').upper()
                cat_code = (line.category_id.code or '').upper() if line.category_id else ''
                if code in PT_CODES or cat_code == 'PT' or (cat_code == 'DED' and 'PT' in code):
                    amt = float(line.total or 0.0)
                    if amt == 0.0 and hasattr(line, 'amount') and line.amount:
                        amt = float(line.amount)
                    current_slip_pt += abs(amt)
            if current_slip_pt == 0.0 and emp_pt_app and comp_pt_app:
                if hasattr(payslip, 'hds_in_compute_professional_tax'):
                    try:
                        current_slip_pt = abs(float(payslip.hds_in_compute_professional_tax() or 0.0))
                    except Exception as e:
                        _logger.debug("Failed computing current payslip PT via API: %s", e)

        # 4. Projected PT for remaining months in the Financial Year
        from .payroll_period_service import PayrollPeriodService
        period_svc = PayrollPeriodService(self.env)
        total_fy_months = period_svc.calculate_total_periods_in_fy(employee, financial_year, eval_date=eval_date)
        paid_count = len(paid_slips)
        current_count = 1 if payslip else 0
        remaining_months = max(0, total_fy_months - paid_count - current_count)

        projected_pt = 0.0
        if remaining_months > 0 and emp_pt_app and comp_pt_app:
            # Resolve monthly wage for PT slab evaluation
            from .salary_projection_service import SalaryProjectionService
            sal_proj_svc = SalaryProjectionService(self.env)
            contract = sal_proj_svc._get_employee_contract(employee) if hasattr(sal_proj_svc, '_get_employee_contract') else False
            monthly_wage = float(contract.wage or 0.0) if contract else 0.0
            if gross_payroll_income > 0.0:
                avg_monthly_gross = gross_payroll_income / max(1, total_fy_months)
                monthly_wage = max(monthly_wage, avg_monthly_gross)

            if eval_ctx and 'GROSS' in eval_ctx:
                slip_gross = abs(float(eval_ctx['GROSS'] or 0.0))
                if slip_gross > 0.0:
                    monthly_wage = max(monthly_wage, slip_gross)
            elif payslip and hasattr(payslip, 'line_ids'):
                gross_lines = payslip.line_ids.filtered(lambda l: getattr(l.category_id, 'code', '') == 'GROSS')
                if gross_lines:
                    slip_gross = abs(sum(gross_lines.mapped('total')))
                    if slip_gross > 0.0:
                        monthly_wage = max(monthly_wage, slip_gross)

            # Build list of dates for the 12 calendar months of the FY
            fy_month_dates = []
            for m in range(4, 13):
                fy_month_dates.append(fields.Date.from_string(f"{fy_start.year}-{m:02d}-15"))
            for m in range(1, 4):
                fy_month_dates.append(fields.Date.from_string(f"{fy_end.year}-{m:02d}-15"))

            # Determine future months strictly after the current evaluation / payslip month
            if payslip and (payslip.date_to or payslip.date_from):
                ref_d = payslip.date_to or payslip.date_from
                if isinstance(ref_d, str):
                    ref_d = fields.Date.from_string(ref_d)
                curr_fy_idx = (ref_d.year - fy_start.year) * 12 + (ref_d.month - fy_start.month) + 1
                start_idx = min(len(fy_month_dates), max(0, curr_fy_idx))
            elif eval_date:
                curr_fy_idx = (eval_date.year - fy_start.year) * 12 + (eval_date.month - fy_start.month) + 1
                start_idx = min(len(fy_month_dates), max(0, curr_fy_idx if paid_count > 0 else 0))
            else:
                start_idx = min(len(fy_month_dates), paid_count + current_count)

            remaining_dates = fy_month_dates[start_idx:]

            # Domain services for location, period schedules, and slabs
            from ..payroll.work_location_service import PayrollWorkLocationService
            from ..professional_tax.pt_period_config_service import PTPeriodScheduleService
            from ..professional_tax.professional_tax_slab_service import ProfessionalTaxSlabService
            from ..professional_tax.pt_calculator import PTCalculator

            loc_svc = PayrollWorkLocationService(self.env)
            sched_svc = PTPeriodScheduleService(self.env)
            slab_svc = ProfessionalTaxSlabService(self.env)
            calc_svc = PTCalculator(self.env)

            emp_state = loc_svc.get_work_state(employee)

            if emp_state and monthly_wage > 0.0:
                for d in remaining_dates:
                    period_sched = sched_svc.resolve_schedule(emp_state, company=company, eval_date=d)
                    periodicity = period_sched.periodicity if period_sched else slab_svc.resolve_state_periodicity(emp_state, company=company)

                    # Check if this month is an actual deduction month for the state/schedule
                    is_ded_month = True
                    if period_sched:
                        is_ded_month = sched_svc.should_deduct(period_sched, eval_date=d, employee=employee)
                    elif periodicity == 'half_yearly':
                        is_ded_month = (d.month in (9, 3))
                    elif periodicity == 'quarterly':
                        is_ded_month = (d.month in (6, 9, 12, 3))
                    elif periodicity == 'annual':
                        is_ded_month = (d.month == 3)

                    if not is_ded_month:
                        continue

                    # Scale monthly wage to match state periodic slab definitions
                    # (In Odoo master data, half-yearly, quarterly, and annual slabs define thresholds for the full period)
                    period_multiplier = 1.0
                    if periodicity == 'half_yearly':
                        period_multiplier = 6.0
                    elif periodicity == 'quarterly':
                        period_multiplier = 3.0
                    elif periodicity == 'annual':
                        period_multiplier = 12.0

                    eval_slab_wage = monthly_wage * period_multiplier

                    # Lookup matching slab using the employee's periodic wage basis
                    slab_res = slab_svc.get_applicable_slab(
                        employee=employee,
                        salary=eval_slab_wage,
                        eval_date=d,
                        company=company,
                        state=emp_state,
                        periodicity=periodicity
                    )

                    if slab_res and slab_res.slab_record:
                        c_res = calc_svc.calculate(slab=slab_res, eval_date=d)
                        projected_pt += float(c_res.pt_amount or 0.0)
                    elif current_slip_pt > 0.0:
                        projected_pt += current_slip_pt

        annual_pt = prev_emp_pt + ytd_pt + current_slip_pt + projected_pt

        # 5. Statutory Cap: Article 276(2) Constitution of India caps PT at ₹2,500 per annum
        statutory_pt_cap = 2500.0
        allowed_pt = min(annual_pt, statutory_pt_cap)

        _logger.warning("""[SECTION_16III_PT_TRACE]
regime                      : OLD
employee                    : %s
financial_year              : %s
eval_date                   : %s
prev_emp_pt (Form 12B)      : INR %s
ytd_paid_pt                 : INR %s (from %s paid payslips)
current_slip_pt             : INR %s
remaining_projection_months : %s
projected_future_pt         : INR %s
total_annual_pt             : INR %s
statutory_pt_cap (Art 276)  : INR %s
final_allowed_pt_16iii      : INR %s""",
            getattr(employee, 'name', 'N/A'),
            getattr(financial_year, 'name', 'N/A'),
            eval_date,
            f"{prev_emp_pt:,.2f}",
            f"{ytd_pt:,.2f}",
            paid_count,
            f"{current_slip_pt:,.2f}",
            remaining_months,
            f"{projected_pt:,.2f}",
            f"{annual_pt:,.2f}",
            f"{statutory_pt_cap:,.2f}",
            f"{allowed_pt:,.2f}"
        )

        return ProfessionalTaxDeductionResult(
            allowed_pt_deduction=round(allowed_pt, 2),
            ytd_paid_pt=round(ytd_pt, 2),
            prev_employer_pt=round(prev_emp_pt, 2),
            current_slip_pt=round(current_slip_pt, 2),
            projected_future_pt=round(projected_pt, 2),
            total_annual_pt=round(annual_pt, 2),
            statutory_cap=statutory_pt_cap,
            is_eligible=True,
            remarks=f"Section 16(iii) Professional Tax deduction of ₹{allowed_pt:,.2f} approved under Old Tax Regime."
        )
