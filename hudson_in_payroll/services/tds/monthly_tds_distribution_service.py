import os
import logging
from odoo import fields
from odoo.exceptions import ValidationError
from ..base import BaseStatutoryService
from .previous_employer_tds_service import PreviousEmployerTdsService
from .current_financial_year_tds_service import CurrentFinancialYearTdsService
from .payroll_period_service import PayrollPeriodService

_logger = logging.getLogger(__name__)

_logger.warning("""[TDS_DEBUG_TRACE][MODULE_LOADED]
file_path=%s
module_name=%s""", os.path.abspath(__file__), __name__)


class MonthlyTDSDistributionResult:
    """
    Data Transfer Object (DTO) holding monthly TDS distribution & current payslip withholding details.
    """
    def __init__(self, total_annual_tax_liability, ytd_tds_deducted, prev_employer_tds,
                 total_tds_paid_so_far, remaining_annual_tax_liability, remaining_payroll_periods,
                 current_month_tds):
        self.total_annual_tax_liability = total_annual_tax_liability
        self.ytd_tds_deducted = ytd_tds_deducted
        self.prev_employer_tds = prev_employer_tds
        self.total_tds_paid_so_far = total_tds_paid_so_far
        self.remaining_annual_tax_liability = remaining_annual_tax_liability
        self.remaining_payroll_periods = remaining_payroll_periods
        self.current_month_tds = current_month_tds


class MonthlyTDSDistributionService(BaseStatutoryService):
    """
    Phase 10 Service: Monthly TDS Distribution Engine Service.
    Distributes net remaining annual tax liability dynamically across remaining payroll periods in the Financial Year.
    Considers YTD TDS deducted on current employer payslips and previous employer TDS from Form 12B.
    Formula:
    1. Total TDS Paid So Far = YTD Current Employer TDS + Previous Employer TDS
    2. Remaining Liability = max(0.0, Total Annual Tax Liability - Total TDS Paid So Far)
    3. Current Month TDS = Remaining Liability / Remaining Payroll Periods (including current period)
    """

    def calculate_monthly_tds(self, employee, financial_year, total_annual_tax_liability, eval_date=None, payslip=None):
        """
        Calculates monthly TDS withholding for the current payslip evaluation period.

        :param employee: hr.employee record
        :param financial_year: tds.financial.year record
        :param total_annual_tax_liability: float (Total projected annual tax liability after cess)
        :param eval_date: Date (optional)
        :param payslip: hr.payslip record (optional)
        :return: MonthlyTDSDistributionResult
        """
        _logger.warning("""[TDS_DEBUG_TRACE][DISTRIBUTION_SERVICE_ENTER_REAL]
module_file=%s
method=calculate_monthly_tds
employee_id=%s
payslip_id=%s
current_month=%s""",
            os.path.abspath(__file__),
            employee.id if employee else 'N/A',
            payslip.id if payslip else 'N/A',
            eval_date if eval_date else 'N/A'
        )
        _logger.warning("""[TDS_DEBUG_TRACE][DISTRIBUTION_SERVICE_ENTER]
file_path=%s
employee_id=%s
payslip_id=%s
current_month=%s
annual_tax=%s
ytd_tds=N/A
balance_tax=N/A
distribution_months=N/A""",
            os.path.abspath(__file__),
            employee.id if employee else 'N/A',
            payslip.id if payslip else 'N/A',
            eval_date if eval_date else 'N/A',
            total_annual_tax_liability
        )
        _logger.warning("Entering MonthlyTDSDistributionService.calculate_monthly_tds for employee '%s' (Total Annual Tax Liability: %s, Eval Date: %s)", getattr(employee, 'name', 'Unknown'), total_annual_tax_liability, eval_date)

        try:
            if not employee:
                raise ValidationError("Monthly TDS Distribution Error: Employee record is required.")
            if not financial_year:
                raise ValidationError("Monthly TDS Distribution Error: Financial Year record is required.")
            if total_annual_tax_liability is None:
                raise ValidationError("Monthly TDS Distribution Error: Final Annual Tax Liability is required.")

            eval_date = eval_date or fields.Date.today()

            # 1. Resolve Previous Employer TDS via PreviousEmployerTdsService
            prev_tds_svc = PreviousEmployerTdsService(self.env)
            prev_employer_tds = prev_tds_svc.get_previous_employer_tds(employee, financial_year)

            # 2. Resolve Current Financial Year YTD TDS via CurrentFinancialYearTdsService (prior completed payslips before current eval month)
            ytd_tds_svc = CurrentFinancialYearTdsService(self.env)
            ytd_tds_deducted = ytd_tds_svc.get_ytd_tds_deducted(employee, financial_year, eval_date=eval_date)

            # 3. Resolve Remaining Payroll Periods via PayrollPeriodService
            period_svc = PayrollPeriodService(self.env)
            remaining_periods = period_svc.calculate_remaining_periods(employee, financial_year, eval_date=eval_date, payslip=payslip)

            # 4. Determine Remaining Annual Liability (with Zero Floor)
            total_tds_paid_so_far = ytd_tds_deducted + prev_employer_tds
            remaining_annual_tax = max(0.0, total_annual_tax_liability - total_tds_paid_so_far)

            eval_m_num = eval_date.month if hasattr(eval_date, 'month') else 4
            eval_fy_idx = eval_m_num - 3 if eval_m_num >= 4 else eval_m_num + 9
            month_names_dict = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June',
                                7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'}
            payroll_month_name = month_names_dict.get(eval_m_num, str(eval_m_num))

            linked_payslip = False
            if eval_date:
                linked_payslip = self.env['hr.payslip'].search([
                    ('employee_id', '=', employee.id),
                    ('date_from', '<=', eval_date),
                    ('date_to', '>=', eval_date)
                ], limit=1)
            payslip_id_ent = str(linked_payslip.id) if linked_payslip else 'N/A'

            _logger.warning("""[TDS_DEBUG_TRACE][DISTRIBUTION_SERVICE_ENTER]
employee_id=%s
payslip_id=%s
current_month=%s
annual_tax=%s
ytd_tds=%s
balance_tax=%s
distribution_months=%s""",
                employee.id if employee else 'N/A', payslip_id_ent, payroll_month_name,
                total_annual_tax_liability, total_tds_paid_so_far, remaining_annual_tax, remaining_periods
            )

            # Search for existing persisted TDS recalculation schedule for this employee & FY
            schedule_model = self.env['tds.recalculation.schedule']
            sched = schedule_model.search([
                ('employee_id', '=', employee.id),
                ('financial_year_id', '=', financial_year.id),
                ('status', '=', 'distribution_active')
            ], limit=1)

            if sched:
                _logger.warning("""[TDS_DEBUG_TRACE][SCHEDULE_LIFECYCLE]
schedule_id=%s
operation=READ
annual_tax=%s
ytd_tds=%s
remaining_tax=%s
distribution_months=%s
january_tds=%s
february_tds=%s
march_tds=%s
status=%s
source_method=MonthlyTDSDistributionService.calculate_monthly_tds (READ)
payslip_id=%s
eval_date=%s""",
                    sched.id, sched.recalculated_annual_tax, sched.ytd_tds_at_recalculation,
                    sched.remaining_tax_liability, sched.distribution_months, sched.january_tds,
                    sched.february_tds, sched.march_tds, sched.status,
                    payslip_id_ent, eval_date
                )
                decl_for_sched = self.env['tds.employee.declaration'].sudo().search([
                    ('employee_id', '=', employee.id),
                    ('financial_year_id', '=', financial_year.id)
                ], limit=1)
                stored_80e = float(getattr(decl_for_sched, 'decl_80e_interest', 0.0) or 0.0) if decl_for_sched else 'N/A'
                _logger.warning("""[80E_BUG_TRACE] SCHEDULE_READ
schedule_id=%s
stored_annual_tax=%s
stored_january_tds=%s
stored_80e_if_available=%s
read_source=%s
caller/method=%s""",
                    sched.id, sched.recalculated_annual_tax, sched.january_tds,
                    stored_80e, 'tds.recalculation.schedule (distribution_active search)',
                    'MonthlyTDSDistributionService.calculate_monthly_tds'
                )

            decl = self.env['tds.employee.declaration'].sudo().search([
                ('employee_id', '=', employee.id),
                ('financial_year_id', '=', financial_year.id)
            ], limit=1)

            # Resolve 1-based FY Month Index and Configuration-driven Redistribution Period
            fy_start = financial_year.start_date
            if fy_start:
                fy_start_year = fy_start.year
                fy_start_month = fy_start.month
                eval_year = eval_date.year
                eval_month = eval_date.month
                elapsed_months = (eval_year - fy_start_year) * 12 + (eval_month - fy_start_month) + 1
                eval_fy_idx = min(12, max(1, elapsed_months))
            else:
                eval_m_num = eval_date.month if hasattr(eval_date, 'month') else 4
                eval_fy_idx = eval_m_num - 3 if eval_m_num >= 4 else eval_m_num + 9

            # Configuration-driven redistribution months count (e.g., 3 for final 3 months of FY)
            dist_m = max(1, min(12, int(getattr(financial_year, 'tds_recalculation_distribution_months', 3) or 3)))

            # Dynamically derive the start FY month index of the redistribution period (final dist_m of FY)
            recalc_start_fy_idx = 12 - dist_m + 1

            # Redistribution Phase active check: current month has reached or passed the redistribution start FY index
            is_recalc_active = (eval_fy_idx >= recalc_start_fy_idx)

            eval_m_num = eval_date.month if hasattr(eval_date, 'month') else 4
            month_names_dict = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June',
                                7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'}
            payroll_month_name = month_names_dict.get(eval_m_num, str(eval_m_num))
            start_cal_m = recalc_start_fy_idx + 3 if recalc_start_fy_idx <= 9 else recalc_start_fy_idx - 9
            recalc_start_month_name = month_names_dict.get(start_cal_m, str(start_cal_m))

            # Determine employee-specific total periods in FY based on joining date
            period_svc = PayrollPeriodService(self.env)
            emp_total_fy_periods = period_svc.calculate_total_periods_in_fy(employee, financial_year, eval_date=eval_date)

            tds_months = int(getattr(financial_year, 'tds_month_division', 0) or 0)
            if tds_months <= 0:
                # Check employee's dynamic month division based on joining date
                tds_months = int(getattr(employee, 'hds_in_tds_month_division', 0) or 0)
                if tds_months <= 0:
                    tds_months = emp_total_fy_periods

            joining_date = period_svc._resolve_employee_joining_date(employee)
            if joining_date and fy_start and joining_date > fy_start:
                join_elapsed = (joining_date.year - fy_start_year) * 12 + (joining_date.month - fy_start_month) + 1
                emp_join_idx = min(12, max(1, join_elapsed))
            else:
                emp_join_idx = 1

            completed_m_cnt = max(0, eval_fy_idx - emp_join_idx)
            future_m_cnt = max(0, remaining_periods - 1)
            dist_m_cnt = remaining_periods

            _logger.warning("""[TDS_DEBUG_TRACE][PAYROLL_MONTH_CONTEXT]
completed_payroll_months=%s
current_payroll_month=%s
future_payroll_months=%s
tds_distribution_months=%s""",
                completed_m_cnt, payroll_month_name, future_m_cnt, dist_m_cnt
            )

            recalc_already_completed = bool(sched)
            recalc_executed = "NO"
            allocation_source = "NORMAL_PROJECTION"
            jan_alloc = 0.0
            feb_alloc = 0.0
            mar_alloc = 0.0
            rec_annual_tax = total_annual_tax_liability
            rec_ytd_tds = total_tds_paid_so_far
            rec_rem_tax = remaining_annual_tax
            stored_annual_tax = float(sched.recalculated_annual_tax or 0.0) if sched else total_annual_tax_liability

            if not is_recalc_active:
                # Dynamic monthly amortization under Section 192 (Remaining Annual Liability / Remaining Payroll Periods)
                current_dist_m = remaining_periods
                fresh_m_tds = round(remaining_annual_tax / float(current_dist_m), 2) if current_dist_m > 0 else remaining_annual_tax
                current_month_tds = fresh_m_tds
                allocation_source = "DYNAMIC_MONTHLY_AMORTIZATION"
                schedule_reused = False
                stored_dist_m = remaining_periods
                stored_m_tds = current_month_tds
                decision_reason = f"Dynamic monthly amortization under Section 192 (FY Index {eval_fy_idx} < Redistribution Start {recalc_start_fy_idx}): Remaining Tax ₹{remaining_annual_tax:,.2f} / {remaining_periods} remaining periods."
            else:
                # Redistribution phase: Dynamically use remaining redistribution months in FY as divisor
                current_dist_m = remaining_periods

                # Fresh monthly TDS allocation for current month based on remaining liability / remaining redistribution months
                fresh_m_tds = round(remaining_annual_tax / float(current_dist_m), 2) if current_dist_m > 0 else remaining_annual_tax

                _logger.warning("""[80E_BUG_TRACE] DISTRIBUTION_BEFORE_WRITE
annual_tax=%s
previous_tds=%s
balance_tax=%s
distribution_months=%s
january_allocation=%s""",
                    total_annual_tax_liability,
                    total_tds_paid_so_far,
                    remaining_annual_tax,
                    current_dist_m,
                    fresh_m_tds
                )

                if sched:
                    stored_annual_tax = float(sched.recalculated_annual_tax or 0.0)
                    current_annual_tax = float(total_annual_tax_liability or 0.0)
                    stored_dist_m = int(sched.distribution_months or dist_m)

                    month_field_map = {
                        1: 'january_tds', 2: 'february_tds', 3: 'march_tds', 4: 'april_tds',
                        5: 'may_tds', 6: 'june_tds', 7: 'july_tds', 8: 'august_tds',
                        9: 'september_tds', 10: 'october_tds', 11: 'november_tds', 12: 'december_tds'
                    }
                    stored_field = month_field_map.get(eval_m_num, 'january_tds')
                    stored_m_tds = float(getattr(sched, stored_field, 0.0) or 0.0)

                    # Validate whether stored allocation matches current fresh calculation context
                    is_same_tax = abs(stored_annual_tax - current_annual_tax) < 0.01
                    is_same_m_tds = abs(stored_m_tds - fresh_m_tds) < 0.01

                    struct_code = (getattr(payslip.struct_id, 'code', '') or '').upper() if payslip and payslip.struct_id else ''
                    struct_name = (getattr(payslip.struct_id, 'name', '') or '').upper() if payslip and payslip.struct_id else ''
                    is_settlement_slip = bool(
                        payslip and (
                            struct_code in ('FINAL_SETTLEMENT_STRUCT', 'FINAL_SETT', 'FINAL_SETTLEMENT')
                            or 'SETTLEMENT' in struct_code
                            or 'SETTLEMENT' in struct_name
                            or 'FINAL' in struct_name
                            or self.env.context.get('is_final_settlement')
                            or ('final.settlement' in self.env and (
                                self.env['final.settlement'].search_count([('payslip_id', '=', payslip.id), ('state', '!=', 'cancel')])
                            ))
                        )
                    )
                    if not is_settlement_slip and employee and 'final.settlement' in self.env and eval_date:
                        is_settlement_slip = bool(self.env['final.settlement'].search_count([
                            ('employee_id', '=', employee.id), ('state', '!=', 'cancel'), ('last_working_day', '<=', eval_date)
                        ]))
                    schedule_reused = (not is_settlement_slip) and is_same_tax and is_same_m_tds

                    if schedule_reused:
                        current_month_tds = stored_m_tds
                        rec_annual_tax = stored_annual_tax
                        rec_ytd_tds = float(sched.ytd_tds_at_recalculation or 0.0)
                        rec_rem_tax = float(sched.remaining_tax_liability or 0.0)
                        decision_reason = f"Stored allocation for {payroll_month_name} matches fresh calculation context."
                    else:
                        current_month_tds = fresh_m_tds
                        rec_annual_tax = current_annual_tax
                        rec_ytd_tds = total_tds_paid_so_far
                        rec_rem_tax = remaining_annual_tax
                        decision_reason = f"Stored distribution context is stale/invalid for {payroll_month_name} (Stored: ₹{stored_m_tds:,.2f} vs Fresh: ₹{fresh_m_tds:,.2f}). Updated schedule ID={sched.id}."

                        # Update stored schedule with fresh allocation values
                        jan_val = fresh_m_tds if eval_m_num == 1 else float(sched.january_tds or fresh_m_tds)
                        feb_val = fresh_m_tds if eval_m_num == 2 else float(sched.february_tds or fresh_m_tds)
                        mar_val = fresh_m_tds if eval_m_num == 3 else float(sched.march_tds or fresh_m_tds)

                        _logger.warning("""[80E_BUG_TRACE] SCHEDULE_WRITE
schedule_id=%s
old_annual_tax=%s
new_annual_tax=%s
old_january_tds=%s
new_january_tds=%s
write_source=%s
caller/method=%s""",
                            sched.id,
                            stored_annual_tax,
                            rec_annual_tax,
                            stored_m_tds,
                            jan_val,
                            'MonthlyTDSDistributionService.calculate_monthly_tds (UPDATE)',
                            'MonthlyTDSDistributionService.calculate_monthly_tds'
                        )

                        sched.write({
                            'declaration_id': decl.id if decl else False,
                            'recalculation_from_month': str(eval_m_num),
                            'distribution_months': current_dist_m,
                            'recalculation_date': eval_date,
                            'recalculated_annual_tax': rec_annual_tax,
                            'ytd_tds_at_recalculation': rec_ytd_tds,
                            'remaining_tax_liability': rec_rem_tax,
                            'january_tds': jan_val,
                            'february_tds': feb_val,
                            'march_tds': mar_val,
                        })
                else:
                    # Create fresh TDS recalculation schedule record
                    current_month_tds = fresh_m_tds
                    stored_dist_m = current_dist_m
                    stored_m_tds = fresh_m_tds
                    schedule_reused = False
                    rec_annual_tax = total_annual_tax_liability
                    rec_ytd_tds = total_tds_paid_so_far
                    rec_rem_tax = remaining_annual_tax
                    decision_reason = f"Created new recalculation schedule for {payroll_month_name}."

                    sched = schedule_model.create({
                        'employee_id': employee.id,
                        'financial_year_id': financial_year.id,
                        'declaration_id': decl.id if decl else False,
                        'recalculation_from_month': str(eval_m_num),
                        'distribution_months': current_dist_m,
                        'recalculation_date': eval_date,
                        'recalculated_annual_tax': rec_annual_tax,
                        'ytd_tds_at_recalculation': rec_ytd_tds,
                        'remaining_tax_liability': rec_rem_tax,
                        'january_tds': fresh_m_tds,
                        'february_tds': fresh_m_tds,
                        'march_tds': fresh_m_tds,
                        'status': 'distribution_active',
                    })

                    _logger.warning("""[80E_BUG_TRACE] SCHEDULE_WRITE
schedule_id=%s
old_annual_tax=None
new_annual_tax=%s
old_january_tds=None
new_january_tds=%s
write_source=%s
caller/method=%s""",
                        sched.id,
                        rec_annual_tax,
                        fresh_m_tds,
                        'MonthlyTDSDistributionService.calculate_monthly_tds (CREATE)',
                        'MonthlyTDSDistributionService.calculate_monthly_tds'
                    )

            _logger.warning("""[TDS_DEBUG_TRACE][DISTRIBUTION_DECISION]
current_month=%s
current_distribution_months=%s
stored_distribution_months=%s
previous_tds=%s
remaining_tax=%s
fresh_monthly_tds=%s
stored_monthly_tds=%s
schedule_reused=%s
final_monthly_tds=%s
decision_reason=%s""",
                payroll_month_name,
                dist_m_cnt if not is_recalc_active else (eval_m_num - 3 if eval_m_num >= 4 else (3 if eval_m_num == 1 else (2 if eval_m_num == 2 else 1))),
                stored_dist_m if sched else 0,
                total_tds_paid_so_far,
                remaining_annual_tax,
                fresh_m_tds,
                stored_m_tds if sched else 0.0,
                schedule_reused,
                current_month_tds,
                decision_reason
            )

            _logger.warning("""[TDS_RECALC_TRACE][TDS_DISTRIBUTION]
annual_tax_liability=%s
previous_tds_deducted=%s
remaining_tax=%s
remaining_distribution_months=%s
current_month=%s
current_month_tds=%s""",
                int(total_annual_tax_liability) if total_annual_tax_liability == int(total_annual_tax_liability) else total_annual_tax_liability,
                int(total_tds_paid_so_far) if total_tds_paid_so_far == int(total_tds_paid_so_far) else total_tds_paid_so_far,
                int(remaining_annual_tax) if remaining_annual_tax == int(remaining_annual_tax) else remaining_annual_tax,
                current_dist_m,
                payroll_month_name,
                current_month_tds
            )

            if sched:
                stored_annual_tax = float(sched.recalculated_annual_tax or 0.0)
                current_annual_tax = float(total_annual_tax_liability or 0.0)
                _logger.warning("""[TDS_RECALC_TRACE][OLD_VS_NEW]
previous_annual_tax=%s
recalculated_annual_tax=%s
previous_tds_deducted=%s
additional_tax_to_recover=%s""",
                    int(stored_annual_tax) if stored_annual_tax == int(stored_annual_tax) else stored_annual_tax,
                    int(current_annual_tax) if current_annual_tax == int(current_annual_tax) else current_annual_tax,
                    int(total_tds_paid_so_far) if total_tds_paid_so_far == int(total_tds_paid_so_far) else total_tds_paid_so_far,
                    int(max(0.0, current_annual_tax - stored_annual_tax)) if max(0.0, current_annual_tax - stored_annual_tax) == int(max(0.0, current_annual_tax - stored_annual_tax)) else max(0.0, current_annual_tax - stored_annual_tax)
                )

            _logger.warning("""[80E_AUDIT] RECALCULATION_DISTRIBUTION
previous_tds=%s
balance_tax=%s
distribution_months=%s
current_month_tds=%s""",
                total_tds_paid_so_far,
                remaining_annual_tax,
                current_dist_m,
                current_month_tds
            )

            calc_m_tds = rec_rem_tax / dist_m if dist_m > 0 else rec_rem_tax
            src_method = "MonthlyTDSDistributionService.calculate_monthly_tds (STORED_DISTRIBUTION)" if (sched and recalc_already_completed) else "MonthlyTDSDistributionService.calculate_monthly_tds (JANUARY_RECALCULATION)"
            src_reason = f"Read stored jan_alloc={jan_alloc} from tds.recalculation.schedule ID={sched.id} (status={sched.status})" if (sched and recalc_already_completed) else f"Calculated fresh jan_alloc={jan_alloc} from rec_rem_tax={rec_rem_tax} / dist_m={dist_m}"

            final_dist_source = "STORED_JANUARY_ALLOCATION" if (sched and recalc_already_completed and eval_m_num == 1) else allocation_source
            fresh_recalc_req = not bool(sched and recalc_already_completed)

            _logger.warning("""[TDS_DEBUG_TRACE][DISTRIBUTION_LIFECYCLE]
current_month=%s
schedule_exists=%s
schedule_id=%s
schedule_status=%s
fresh_recalculation_required=%s
ytd_before_current_payslip=%s
current_payslip_tds=%s
final_distribution_source=%s
final_monthly_tds=%s""",
                payroll_month_name, bool(sched), sched.id if sched else 'N/A',
                sched.status if sched else 'no_schedule', fresh_recalc_req,
                ytd_tds_deducted, current_month_tds, final_dist_source, current_month_tds
            )

            calc_run_id = self.env.context.get('tds_calc_run_id', 'N/A')
            tax_diff = float(total_annual_tax_liability or 0.0) - float(stored_annual_tax or 0.0)
            schedule_status_str = "REUSED" if (sched and schedule_reused) else "RECALCULATED"

            _logger.warning("""[TDS_DISTRIBUTION_CALCULATION_POINT]
calculation_run_id=%s
employee_id=%s
employee_name=%s
evaluation_date=%s
financial_year=%s
previous_annual_tax=%s
recalculated_annual_tax=%s
tax_difference=%s
ytd_tds=%s
remaining_tax=%s
remaining_months=%s
old_monthly_tds=%s
fresh_monthly_tds=%s
schedule_reused_recalculated=%s""",
                calc_run_id,
                employee.id,
                employee.name,
                eval_date,
                financial_year.name if financial_year else 'N/A',
                f"INR {stored_annual_tax:,.2f}",
                f"INR {total_annual_tax_liability:,.2f}",
                f"INR {tax_diff:,.2f}",
                f"INR {total_tds_paid_so_far:,.2f}",
                f"INR {remaining_annual_tax:,.2f}",
                current_dist_m,
                f"INR {stored_m_tds:,.2f}",
                f"INR {fresh_m_tds:,.2f}",
                schedule_status_str
            )

            _logger.warning("""[TDS_DISTRIBUTION_TRACE]
calculation_run_id=%s
previous_annual_tax=%s
recalculated_annual_tax=%s
ytd_tds=%s
remaining_tax=%s
remaining_months=%s
old_monthly_tds=%s
new_monthly_tds=%s
schedule_reused_recalculated=%s""",
                calc_run_id,
                f"INR {stored_annual_tax:,.2f}",
                f"INR {total_annual_tax_liability:,.2f}",
                f"INR {total_tds_paid_so_far:,.2f}",
                f"INR {remaining_annual_tax:,.2f}",
                current_dist_m,
                f"INR {stored_m_tds:,.2f}",
                f"INR {fresh_m_tds:,.2f}",
                schedule_status_str
            )

            _logger.warning("""[80E_BUG_TRACE] JAN_FINAL_OVERRIDE
value_before_override=%s
value_after_override=%s
override_source=%s
schedule_id=%s
stored_january_allocation=%s""",
                39000.0 / dist_m if dist_m else 13000.0,
                current_month_tds,
                allocation_source,
                sched.id if sched else 'N/A',
                stored_m_tds if sched else 0.0
            )

            _logger.warning("""[TDS_DEBUG_TRACE][TDS_FINAL_VALUE_FLOW]
balance_tax=%s
months_remaining=%s
calculated_monthly_tds=%s
value_before_rounding=%s
value_after_rounding=%s
value_after_adjustment=%s
final_current_month_tds=%s
source_method=%s
source_reason=%s""",
                rec_rem_tax, dist_m, calc_m_tds,
                calc_m_tds, current_month_tds, current_month_tds,
                current_month_tds, src_method, src_reason
            )

            decl_rec_log = self.env['tds.employee.declaration'].search([
                ('employee_id', '=', employee.id),
                ('financial_year_id', '=', financial_year.id)
            ], limit=1) if financial_year else False
            decl_id_log = str(decl_rec_log.id) if decl_rec_log else 'N/A'

            linked_payslip_log = False
            if eval_date:
                linked_payslip_log = self.env['hr.payslip'].search([
                    ('employee_id', '=', employee.id),
                    ('date_from', '<=', eval_date),
                    ('date_to', '>=', eval_date)
                ], limit=1)
            payslip_id_log = str(linked_payslip_log.id) if linked_payslip_log else 'N/A'

            decision_trace_msg = f"""[TDS_DEBUG_TRACE]
Employee: {employee.name if employee else 'N/A'}
Payslip ID: {payslip_id_log}
Payroll Month: {payroll_month_name}
Financial Year: {financial_year.name if financial_year else 'N/A'}
Declaration ID: {decl_id_log}

========================================================
TDS RECALCULATION DECISION TRACE
========================================================
Employee                            : {employee.name} (ID: {employee.id})
Financial Year                      : {financial_year.name if financial_year else 'N/A'}
Current Payroll Month               : {payroll_month_name}
Configured Recalculation From Month : {recalc_start_month_name}
Configured Distribution Months      : {dist_m}
Recalculation Already Completed     : {'YES' if recalc_already_completed else 'NO'}
Recalculation Execution             : {recalc_executed}
Distribution Execution              : {'ACTIVE' if is_recalc_active else 'INACTIVE'}

Annual Tax At Recalculation         : ₹{rec_annual_tax:,.2f}
YTD TDS At Recalculation            : ₹{rec_ytd_tds:,.2f}
Remaining Liability                 : ₹{rec_rem_tax:,.2f}
Original Distribution Months        : {dist_m}
January Allocation                  : ₹{jan_alloc:,.2f}
February Allocation                 : ₹{feb_alloc:,.2f}
March Allocation                    : ₹{mar_alloc:,.2f}
Current Month Allocation            : ₹{current_month_tds:,.2f}
Allocation Source                   : {allocation_source}
========================================================
"""
            _logger.warning(decision_trace_msg)

            # Log detailed declaration lifecycle trace
            decl = self.env['tds.employee.declaration'].search([
                ('employee_id', '=', employee.id),
                ('financial_year_id', '=', financial_year.id)
            ], limit=1)

            if decl:
                from .tds_declaration_lifecycle_logger import TdsDeclarationLifecycleLogger
                lifecycle_logger = TdsDeclarationLifecycleLogger(self.env)
                for line in decl.declaration_line_ids:
                    lifecycle_logger.log_amount_reconciliation_trace(
                        employee_name=employee.name if employee else 'N/A',
                        employee_id=employee.id if employee else 'N/A',
                        financial_year_name=financial_year.name if financial_year else 'N/A',
                        declaration_id=decl.id,
                        declaration_state=decl.state,
                        section_code=line.section_code or line.category,
                        source_type="DECLARATION_LINE",
                        declared_amount=line.declared_amount,
                        eligible_amount=line.eligible_amount,
                        verified_amount=line.verified_amount,
                        approved_amount=line.approved_amount,
                        usable_amount=line.usable_amount,
                        ytd_tds=ytd_tds_deducted,
                        annual_tax=total_annual_tax_liability,
                        remaining_tax=remaining_annual_tax,
                        remaining_periods=remaining_periods,
                        current_month_tds=current_month_tds,
                        service_method="MonthlyTDSDistributionService.calculate_monthly_tds"
                    )

            _logger.warning("""[TDS_DEBUG_TRACE][DISTRIBUTION_DECISION]
current_month=%s
current_distribution_months=%s
stored_distribution_months=%s
previous_tds=%s
remaining_tax=%s
fresh_monthly_tds=%s
stored_monthly_tds=%s
schedule_reused=%s
final_monthly_tds=%s
decision_reason=%s""",
                payroll_month_name,
                current_dist_m,
                stored_dist_m if sched else 0,
                total_tds_paid_so_far,
                remaining_annual_tax,
                fresh_m_tds,
                stored_m_tds if sched else 0.0,
                schedule_reused,
                current_month_tds,
                decision_reason
            )

            _logger.warning("""[FORENSIC_TDS_TRACE]
step=MONTHLY_TDS_DISTRIBUTION
eval_date=%s
eval_month=%s
input=annual_tax_liability:INR %s, total_tds_paid_so_far:INR %s (YTD:INR %s, PrevEmp:INR %s), eval_fy_idx:%s
output=remaining_tax_liability:INR %s, remaining_payroll_periods:%s, current_month_tds:INR %s
source_method=MonthlyTDSDistributionService.calculate_monthly_tds
branch_used=%s""",
                eval_date,
                payroll_month_name,
                f"{total_annual_tax_liability:,.2f}",
                f"{total_tds_paid_so_far:,.2f}",
                f"{ytd_tds_deducted:,.2f}",
                f"{prev_employer_tds:,.2f}",
                eval_fy_idx,
                f"{remaining_annual_tax:,.2f}",
                remaining_periods,
                f"{current_month_tds:,.2f}",
                f"{'REDISTRIBUTION_PHASE_DIVISOR' if is_recalc_active else 'DYNAMIC_MONTHLY_AMORTIZATION_DIVISOR'} (Divisor Used: {remaining_periods}, Active Schedule Reused: {schedule_reused})"
            )

            return MonthlyTDSDistributionResult(
                total_annual_tax_liability=total_annual_tax_liability,
                ytd_tds_deducted=ytd_tds_deducted,
                prev_employer_tds=prev_employer_tds,
                total_tds_paid_so_far=total_tds_paid_so_far,
                remaining_annual_tax_liability=remaining_annual_tax,
                remaining_payroll_periods=remaining_periods,
                current_month_tds=current_month_tds
            )
        except Exception as exc:
            _logger.warning("Exception inside MonthlyTDSDistributionService.calculate_monthly_tds: %s", exc, exc_info=True)
            raise
