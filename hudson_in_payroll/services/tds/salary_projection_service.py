# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import fields
from ..base import BaseStatutoryService
from .payroll_period_service import PayrollPeriodService
_logger = logging.getLogger(__name__)


class SalaryProjectionResult:
    """
    Data Transfer Object (DTO) holding projected current employer salary details.
    """
    def __init__(self, ytd_basic=0.0, projected_basic=0.0, total_basic=0.0,
                 ytd_da=0.0, projected_da=0.0, total_da=0.0,
                 ytd_hra=0.0, projected_hra=0.0, total_hra=0.0,
                 ytd_bonus=0.0, projected_bonus=0.0, total_bonus=0.0,
                 ytd_allowances=0.0, projected_allowances=0.0, total_allowances=0.0,
                 months_elapsed=0, months_remaining=0, total_projected_current_salary=0.0,
                 ytd_lta=0.0, projected_lta=0.0, total_lta=0.0,
                 ytd_leave_encashment=0.0, projected_leave_encashment=0.0, total_leave_encashment=0.0,
                 ytd_gratuity=0.0, exempt_gratuity=0.0, taxable_gratuity=0.0, total_gratuity=0.0,
                 ytd_exit_leave_encash=0.0, total_exit_leave_encash=0.0,
                 exempt_exit_leave_encash=0.0, taxable_exit_leave_encash=0.0):
        self.ytd_basic = ytd_basic
        self.projected_basic = projected_basic
        self.total_basic = total_basic
        self.ytd_da = ytd_da
        self.projected_da = projected_da
        self.total_da = total_da
        self.ytd_hra = ytd_hra
        self.projected_hra = projected_hra
        self.total_hra = total_hra
        self.ytd_bonus = ytd_bonus
        self.projected_bonus = projected_bonus
        self.total_bonus = total_bonus
        self.ytd_allowances = ytd_allowances
        self.projected_allowances = projected_allowances
        self.total_allowances = total_allowances
        self.months_elapsed = months_elapsed
        self.months_remaining = months_remaining
        self.total_projected_current_salary = total_projected_current_salary
        self.ytd_lta = ytd_lta
        self.projected_lta = projected_lta
        self.total_lta = total_lta
        self.ytd_leave_encashment = ytd_leave_encashment
        self.projected_leave_encashment = projected_leave_encashment
        self.total_leave_encashment = total_leave_encashment
        self.ytd_gratuity = ytd_gratuity
        self.exempt_gratuity = exempt_gratuity
        self.taxable_gratuity = taxable_gratuity
        self.total_gratuity = total_gratuity
        self.ytd_exit_leave_encash = ytd_exit_leave_encash
        self.total_exit_leave_encash = total_exit_leave_encash
        self.exempt_exit_leave_encash = exempt_exit_leave_encash
        self.taxable_exit_leave_encash = taxable_exit_leave_encash


class SalaryProjectionService(BaseStatutoryService):
    """
    Phase 4 Service: Annual Salary Projection Service.
    Projects an employee's annual taxable earnings from current employer payroll
    by aggregating Year-To-Date (YTD) paid payslips and projecting remaining months in the Financial Year.
    """

    def _get_employee_contract(self, employee):
        if not employee:
            return False
        if hasattr(employee, 'contract_id') and employee.contract_id:
            return employee.contract_id
        if hasattr(employee, 'contract_ids') and employee.contract_ids:
            open_contracts = employee.contract_ids.filtered(lambda c: getattr(c, 'state', False) == 'open')
            if open_contracts:
                return open_contracts[0]
            if len(employee.contract_ids) > 0:
                return employee.contract_ids[0]

        # Dynamically inspect and query contract models ('hr.version' and 'hr.contract')
        for model_name in ('hr.version', 'hr.contract'):
            if model_name in self.env:
                ContractModel = self.env[model_name]
                fields_keys = ContractModel._fields.keys()

                _logger.warning("Target contract model '%s' available fields: %s", model_name, list(fields_keys))

                if 'employee_id' not in fields_keys:
                    continue

                base_domain = [('employee_id', '=', employee.id)]

                # Check state / status filter only if field exists on model
                if 'state' in fields_keys:
                    open_contracts = ContractModel.search(base_domain + [('state', '=', 'open')], limit=1)
                    if open_contracts:
                        return open_contracts
                elif 'status' in fields_keys:
                    open_contracts = ContractModel.search(base_domain + [('status', '=', 'open')], limit=1)
                    if open_contracts:
                        return open_contracts

                # Check active filter only if field exists on model
                if 'active' in fields_keys:
                    active_contracts = ContractModel.search(base_domain + [('active', '=', True)], limit=1)
                    if active_contracts:
                        return active_contracts

                all_contracts = ContractModel.search(base_domain, limit=1)
                if all_contracts:
                    return all_contracts

        return False


    def project_salary(self, employee, financial_year=None, eval_date=None, payslip=None):
        """
        Calculates Year-To-Date (YTD) salary earnings and projects remaining months' earnings.

        :param employee: hr.employee record
        :param financial_year: tds.financial.year record (optional, auto-resolved if None)
        :param eval_date: Date (optional)
        :param payslip: hr.payslip record (optional)
        :return: SalaryProjectionResult
        """
        eval_date = eval_date or fields.Date.today()
        if isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)

        if not financial_year:
            from .tds_parameter_service import TdsParameterService
            financial_year = TdsParameterService(self.env).get_financial_year(eval_date=eval_date)

        fy_start = financial_year.start_date
        fy_end = financial_year.end_date

        # Determine remaining payroll periods dynamically via PayrollPeriodService
        # NOTE:
        # - Projection Months (salary_projection_months) is used ONLY to estimate projected annual income.
        # - Remaining Payroll Periods (remaining_periods) is used ONLY inside MonthlyTDSDistributionService to distribute remaining TDS liability.
        period_svc = PayrollPeriodService(self.env)
        total_fy_months = period_svc.calculate_total_periods_in_fy(employee, financial_year, eval_date=eval_date)
        remaining_periods = period_svc.calculate_remaining_periods(employee, financial_year, eval_date=eval_date)

        # Query paid/confirmed PRIOR payslips for current FY on or before eval_date.
        # Must filter ('date_to', '<=', eval_date) so that future payslips in the FY
        # are NOT included when calculating YTD earnings and remaining projection months.
        payslips = self.env['hr.payslip'].search([
            ('employee_id', '=', employee.id),
            ('date_from', '>=', fy_start),
            ('date_to', '<=', eval_date),
            ('state', 'in', ['done', 'paid'])
        ])

        paid_months_count = len(payslips)

        if eval_date < fy_start:
            fy_start_year = fy_start.year
            fy_start_month = fy_start.month
            eval_fy_idx = 1
            months_elapsed = 0
            months_remaining = total_fy_months
        elif eval_date > fy_end:
            fy_start_year = fy_start.year
            fy_start_month = fy_start.month
            eval_fy_idx = 12
            months_elapsed = total_fy_months
            months_remaining = 0
        else:
            fy_start_year = fy_start.year
            fy_start_month = fy_start.month
            eval_year = eval_date.year
            eval_month = eval_date.month

            joining_date = period_svc._resolve_employee_joining_date(employee)
            if joining_date and joining_date > fy_start:
                join_elapsed = (joining_date.year - fy_start_year) * 12 + (joining_date.month - fy_start_month) + 1
                join_fy_idx = min(12, max(1, join_elapsed))
            else:
                join_fy_idx = 1

            if join_fy_idx == 1 and employee and financial_year:
                from .previous_employer_income_service import PreviousEmployerIncomeService
                prev_svc = PreviousEmployerIncomeService(self.env)
                prev_res = prev_svc.aggregate_previous_employer_income(employee, financial_year)
                if prev_res.has_declaration and (prev_res.taxable_salary > 0 or prev_res.tds_deducted > 0):
                    earliest_slip = self.env['hr.payslip'].search([
                        ('employee_id', '=', employee.id),
                        ('date_from', '>=', fy_start),
                        ('date_to', '<=', fy_end)
                    ], order='date_from asc', limit=1)
                    if earliest_slip and earliest_slip.date_from:
                        s_date = fields.Date.from_string(earliest_slip.date_from)
                        join_elapsed = (s_date.year - fy_start_year) * 12 + (s_date.month - fy_start_month) + 1
                        join_fy_idx = min(12, max(1, join_elapsed))
                    else:
                        elapsed_for_join = (eval_year - fy_start_year) * 12 + (eval_month - fy_start_month) + 1
                        join_fy_idx = min(12, max(1, elapsed_for_join))

            elapsed_months = (eval_year - fy_start_year) * 12 + (eval_month - fy_start_month) + 1
            eval_fy_idx = min(12, max(1, elapsed_months))

            if eval_fy_idx < join_fy_idx:
                months_elapsed = 0
                months_remaining = total_fy_months
            else:
                months_elapsed = eval_fy_idx - join_fy_idx + 1
                months_remaining = max(0, total_fy_months - months_elapsed)

        # Dynamic projection months based on total employment months in FY minus already paid months
        salary_projection_months = max(0, total_fy_months - paid_months_count)

        # For Final Settlement, cap projection months to ensure the exit month is not double-counted:
        # If the settlement payslip is already in confirmed/paid state and captured in paid payslips,
        # remaining projection is 0. Otherwise, project at most 1 month for the exit month up to target_exit_months.
        is_final_settlement = False
        if payslip:
            struct = getattr(payslip, 'struct_id', False)
            struct_code = (getattr(struct, 'code', '') or '').upper() if struct else ''
            struct_name = (getattr(struct, 'name', '') or '').upper() if struct else ''
            if struct and (struct_code in ('FINAL_SETTLEMENT_STRUCT', 'FINAL_SETT', 'FINAL_SETTLEMENT') or 'SETTLEMENT' in struct_code or 'SETTLEMENT' in struct_name or 'FINAL' in struct_name):
                is_final_settlement = True
            elif self.env.context.get('is_final_settlement'):
                is_final_settlement = True
            elif 'final.settlement' in self.env:
                if self.env['final.settlement'].search_count([('payslip_id', '=', payslip.id), ('state', '!=', 'cancel')]):
                    is_final_settlement = True
        elif employee and 'final.settlement' in self.env and eval_date:
            settlement_eval = self.env['final.settlement'].search([
                ('employee_id', '=', employee.id), ('state', '!=', 'cancel'), ('last_working_day', '<=', eval_date)
            ], limit=1)
            is_final_settlement = bool(settlement_eval)

        if is_final_settlement:
            target_exit_months = min(eval_fy_idx, total_fy_months)
            if payslip and payslip.id in payslips.ids:
                salary_projection_months = 0
            else:
                salary_projection_months = max(0, min(1, target_exit_months - paid_months_count))

        ytd_basic = 0.0
        ytd_da = 0.0
        ytd_hra = 0.0
        ytd_bonus = 0.0
        ytd_lta = 0.0
        ytd_allowances = 0.0
        ytd_leave_encashment = 0.0       # In-service leave encashment
        ytd_exit_leave_encash = 0.0      # Exit leave encashment (Settlement)
        ytd_gratuity = 0.0              # Statutory Gratuity
        ytd_attendance_deductions = 0.0  # Tracks real salary reductions from unpaid leave / LOP

        # Explicitly defined summary rule codes and categories to exclude from YTD component aggregation
        EXCLUDED_SUMMARY_CODES = {'GROSS', 'NET', 'PF_WAGE', 'TOTAL', 'ESIC_WAGE', 'EPF_ADMIN', 'EDLI_ADMIN', 'ESI_WAGE'}
        # NOTE: 'DED' is intentionally NOT blanket-excluded here.
        # Attendance-based deductions (SHORT, UNPAID, LOP) carry negative amounts that
        # must reduce YTD earnings. They are handled separately in the loop below.
        EXCLUDED_SUMMARY_CATEGORIES = {'GROSS', 'NET', 'COMP'}

        # Attendance-based deduction codes that represent REAL salary reductions
        # (employee did not work → did not earn). These reduce YTD earnings.
        ATTENDANCE_DEDUCTION_CODES = {
            'SHORT', 'UNPAID', 'LOP', 'LWOP', 'ABSENT',
            'LOP_DED', 'UNPAID_LEAVE', 'SHORTAGE', 'LEAVE_DEDUCTION',
            'ATTENDANCE_DEDUCTION', 'ABS_DED', 'LWP',
        }

        # Statutory deduction codes — deducted from gross but gross was still earned.
        # These must NOT reduce projected earnings.
        STATUTORY_DEDUCTION_CODES = {
            'PF', 'EPF', 'ESI', 'ESIC', 'PT', 'TDS', 'IT',
            'PF_EE', 'ESI_EE', 'PROF_TAX', 'INCOME_TAX',
            'VPF', 'NPS', 'LOAN', 'ADVANCE', 'SALARY_ADVANCE',
        }

        for slip in payslips:
            for line in slip.line_ids:
                code = (line.code or '').upper()
                cat_code = (line.category_id.code or '').upper() if line.category_id else ''
                amt = line.total or 0.0

                # 1. Skip summary/aggregation rules
                if cat_code in EXCLUDED_SUMMARY_CATEGORIES or code in EXCLUDED_SUMMARY_CODES:
                    continue

                # 2. Handle DED category lines with nuance
                if cat_code == 'DED':
                    if code in ATTENDANCE_DEDUCTION_CODES:
                        # Attendance deductions reduce actual earnings
                        # These lines typically carry negative amounts (e.g., -₹1,20,000 for full LOP)
                        ytd_attendance_deductions += abs(amt)
                        _logger.info(
                            "[SALARY_PROJ] Attendance deduction captured: code=%s, amt=%.2f, slip=%s",
                            code, amt, slip.number or slip.id
                        )
                    # Statutory deductions (PF, ESI, PT, TDS) and any other DED codes
                    # are skipped — gross was earned, deductions don't reduce taxable projection
                    continue

                # 3. Accumulate specific earning components
                if code in ('BASIC', 'BASIC_PAY'):
                    ytd_basic += amt
                elif code in ('DA', 'DEARNESS_ALLOWANCE'):
                    ytd_da += amt
                elif code in ('HRA', 'HOUSE_RENT_ALLOWANCE'):
                    ytd_hra += amt
                elif code in ('LTA', 'LEAVE_TRAVEL_ALLOWANCE', 'LEAVE_TRAVEL_ASSISTANCE'):
                    ytd_lta += amt
                elif code in ('BONUS', 'INCENTIVE', 'COMMISSION', 'OVERTIME', 'ARREARS', 'PERF_BONUS', 'RETENTION_BONUS'):
                    ytd_bonus += amt
                elif code in ('LEAVE_ENCASH', 'ENCASHMENT', 'LEAVE_ENCASHMENT'):
                    # In-service leave encashment: 100% taxable as salary
                    ytd_leave_encashment += amt
                elif code in ('EXIT_LEAVE_ENCASH', 'LEAVE_ENCASH_EXIT'):
                    # Exit leave encashment (Settlement): Tracked distinctly
                    # Under Income-tax Act, 2025, exit leave encashment does not receive an automatic unverified ₹25L exemption
                    ytd_exit_leave_encash += amt
                elif code == 'GRATUITY':
                    # Statutory Gratuity: Tracked separately to apply statutory exemption ceiling under Income-tax Act, 2025
                    ytd_gratuity += amt
                elif cat_code in ('ALW', 'ALLOWANCE') or cat_code.startswith('ALW'):
                    ytd_allowances += amt
                else:
                    # Generic fallback for any other earning allowance line
                    ytd_allowances += amt

        # Current in-service and exit leave encashment / gratuity (from in-flight draft payslip or approved request)
        current_leave_encashment = 0.0
        current_exit_leave_encash = 0.0
        current_gratuity = 0.0
        if payslip:
            if not payslips or (payslip.id not in payslips.ids):
                # 0. Active evaluation context (in-flight computation during compute_sheet to prevent stale line_ids lag)
                HrPayslipModel = self.env['hr.payslip']
                eval_ctx = getattr(HrPayslipModel, '_eval_contexts', {}).get(payslip.id) if hasattr(HrPayslipModel, '_eval_contexts') else None
                if eval_ctx:
                    if 'LEAVE_ENCASH' in eval_ctx:
                        current_leave_encashment = float(eval_ctx.get('LEAVE_ENCASH') or 0.0)
                    if 'EXIT_LEAVE_ENCASH' in eval_ctx:
                        current_exit_leave_encash = float(eval_ctx.get('EXIT_LEAVE_ENCASH') or 0.0)
                    if 'GRATUITY' in eval_ctx:
                        current_gratuity = float(eval_ctx.get('GRATUITY') or 0.0)

                if hasattr(payslip, 'line_ids') and payslip.line_ids:
                    # In-service leave encashment lines
                    if current_leave_encashment <= 0.0:
                        le_lines = payslip.line_ids.filtered(lambda l: (l.code or '').upper() in (
                            'LEAVE_ENCASH', 'ENCASHMENT', 'LEAVE_ENCASHMENT'
                        ))
                        if le_lines:
                            current_leave_encashment = sum(float(l.total or 0.0) for l in le_lines)
                    # Exit leave encashment lines
                    if current_exit_leave_encash <= 0.0:
                        exit_lines = payslip.line_ids.filtered(lambda l: (l.code or '').upper() in (
                            'EXIT_LEAVE_ENCASH', 'LEAVE_ENCASH_EXIT'
                        ))
                        if exit_lines:
                            current_exit_leave_encash = sum(float(l.total or 0.0) for l in exit_lines)
                    # Gratuity lines
                    if current_gratuity <= 0.0:
                        grat_lines = payslip.line_ids.filtered(lambda l: (l.code or '').upper() == 'GRATUITY')
                        if grat_lines:
                            current_gratuity = sum(float(l.total or 0.0) for l in grat_lines)
                    if is_final_settlement and (current_gratuity <= 0.0 or current_exit_leave_encash <= 0.0):
                        settlement_rec = False
                        if 'final.settlement' in self.env:
                            settlement_rec = self.env['final.settlement'].search([
                                ('payslip_id', '=', payslip.id),
                                ('state', '!=', 'cancel'),
                            ], limit=1)
                            if not settlement_rec and employee:
                                settlement_rec = self.env['final.settlement'].search([
                                    ('employee_id', '=', employee.id),
                                    ('state', '!=', 'cancel'),
                                ], limit=1)
                        if settlement_rec:
                            if current_gratuity <= 0.0 and settlement_rec.gratuity_gross_amount > 0.0:
                                current_gratuity = float(settlement_rec.gratuity_gross_amount)
                            if current_exit_leave_encash <= 0.0 and settlement_rec.leave_encash_gross_amount > 0.0:
                                current_exit_leave_encash = float(settlement_rec.leave_encash_gross_amount)
                        if current_gratuity <= 0.0 and hasattr(payslip, 'hds_in_compute_gratuity'):
                            try:
                                current_gratuity = float(payslip.hds_in_compute_gratuity() or 0.0)
                            except Exception:
                                pass
                        if current_exit_leave_encash <= 0.0 and hasattr(payslip, 'hds_in_compute_exit_leave_encashment'):
                            try:
                                current_exit_leave_encash = float(payslip.hds_in_compute_exit_leave_encashment() or 0.0)
                            except Exception:
                                pass
                if current_leave_encashment <= 0.0 and hasattr(payslip, 'hds_in_has_approved_leave_encashment') and payslip.hds_in_has_approved_leave_encashment():
                    current_leave_encashment = float(payslip.hds_in_compute_in_service_leave_encashment() or 0.0)
        elif employee and financial_year:
            req_model = self.env.get('hds.leave.encashment.request')
            if req_model:
                domain = [
                    ('employee_id', '=', employee.id),
                    ('state', '=', 'approved'),
                    ('request_date', '>=', fy_start),
                    ('request_date', '<=', eval_date),
                ]
                if payslips:
                    domain.append(('payslip_id', 'not in', payslips.ids))
                pending_reqs = req_model.search(domain)
                if pending_reqs:
                    current_leave_encashment = sum(float(r.projected_amount or r.calculate_payout_amount() or 0.0) for r in pending_reqs)

        if is_final_settlement and employee and (current_gratuity <= 0.0 or current_exit_leave_encash <= 0.0) and 'final.settlement' in self.env:
            settlement_emp = self.env['final.settlement'].search([
                ('employee_id', '=', employee.id),
                ('state', '!=', 'cancel'),
            ], limit=1)
            if settlement_emp:
                if current_gratuity <= 0.0 and settlement_emp.gratuity_gross_amount > 0.0:
                    current_gratuity = float(settlement_emp.gratuity_gross_amount)
                if current_exit_leave_encash <= 0.0 and settlement_emp.leave_encash_gross_amount > 0.0:
                    current_exit_leave_encash = float(settlement_emp.leave_encash_gross_amount)

        projected_leave_encashment = 0.0  # Leave encashment is non-recurring
        total_leave_encashment = ytd_leave_encashment + current_leave_encashment
        total_exit_leave_encash = ytd_exit_leave_encash + current_exit_leave_encash

        # Statutory Gratuity Exemption under Income-tax Act, 2025 / Payment of Gratuity Act, 1972
        # Resolved dynamically from settlement or hr.rule.parameter 'hds_in_gratuity_statutory_ceiling'
        try:
            statutory_gratuity_ceiling = float(self.env['hr.rule.parameter']._get_parameter_value(
                'hds_in_gratuity_statutory_ceiling', eval_date
            ) or 2000000.0)
        except Exception:
            statutory_gratuity_ceiling = 2000000.0

        eligible_gratuity_ceiling = statutory_gratuity_ceiling
        if is_final_settlement and 'final.settlement' in self.env:
            settlement_for_exempt = False
            if payslip:
                settlement_for_exempt = self.env['final.settlement'].search([
                    ('payslip_id', '=', payslip.id),
                    ('state', '!=', 'cancel'),
                ], limit=1)
            if not settlement_for_exempt and employee:
                settlement_for_exempt = self.env['final.settlement'].search([
                    ('employee_id', '=', employee.id),
                    ('state', '!=', 'cancel'),
                ], limit=1)
            if settlement_for_exempt and settlement_for_exempt.gratuity_exemption_amount is not False and settlement_for_exempt.gratuity_exemption_amount is not None:
                eligible_gratuity_ceiling = float(settlement_for_exempt.gratuity_exemption_amount)

        total_gratuity = ytd_gratuity + current_gratuity
        exempt_gratuity = min(total_gratuity, eligible_gratuity_ceiling)
        taxable_gratuity = max(0.0, total_gratuity - exempt_gratuity)
        ytd_taxable_gratuity = max(0.0, ytd_gratuity - eligible_gratuity_ceiling)
        current_taxable_gratuity = max(0.0, taxable_gratuity - ytd_taxable_gratuity)

        # Taxable gratuity is unified into the annual taxable salary projection (Section 192).
        # Standalone TDS_GRATUITY withholding rule is retired in favor of single unified HDS_IN_TDS.

        # Statutory Leave Encashment Exemption under Section 10(10AA) / Income-tax Act, 2025
        # Up to ₹25,00,000 is statutorily exempt for all exit/separation leave encashment (CBDT Notification No. 31/2023).
        eligible_leave_ceiling = 0.0

        settlement_for_leave = False
        if is_final_settlement and 'final.settlement' in self.env:
            if payslip:
                settlement_for_leave = self.env['final.settlement'].search([
                    ('payslip_id', '=', payslip.id),
                    ('state', '!=', 'cancel'),
                ], limit=1)
            if not settlement_for_leave and employee:
                settlement_for_leave = self.env['final.settlement'].search([
                    ('employee_id', '=', employee.id),
                    ('state', '!=', 'cancel'),
                ], limit=1)

        if settlement_for_leave and settlement_for_leave.leave_encash_exemption_amount is not False and settlement_for_leave.leave_encash_exemption_amount is not None and settlement_for_leave.leave_encash_exemption_amount > 0.0:
            eligible_leave_ceiling = float(settlement_for_leave.leave_encash_exemption_amount)
        else:
            try:
                eligible_leave_ceiling = float(self.env['hr.rule.parameter']._get_parameter_value(
                    'hds_in_leave_encashment_statutory_ceiling', eval_date
                ) or self.env['hr.rule.parameter']._get_parameter_value(
                    'HDS_IN_TDS_LEAVE_ENCASHMENT_EXEMPTION_CEILING', eval_date
                ) or 2500000.0)
            except Exception:
                eligible_leave_ceiling = 2500000.0

        exempt_exit_leave_encash = min(total_exit_leave_encash, eligible_leave_ceiling)
        taxable_exit_leave_encash = max(0.0, total_exit_leave_encash - exempt_exit_leave_encash)
        ytd_taxable_exit_leave_encash = max(0.0, ytd_exit_leave_encash - eligible_leave_ceiling)
        current_taxable_exit_leave_encash = max(0.0, taxable_exit_leave_encash - ytd_taxable_exit_leave_encash)

        # Contract / Monthly Wage structure for remaining months projection
        contract = self._get_employee_contract(employee)

        contract_wage = float(contract.wage or 0.0) if contract else 0.0

        contract_basic = float(getattr(contract, 'basic_salary', 0.0) or 0.0) if contract else 0.0
        contract_da = float(getattr(contract, 'da', 0.0) or getattr(contract, 'da_amount', 0.0) or 0.0) if contract else 0.0
        contract_hra = float(getattr(contract, 'hra', 0.0) or getattr(contract, 'hra_amount', 0.0) or 0.0) if contract else 0.0
        contract_lta = float(getattr(contract, 'lta', 0.0) or getattr(contract, 'lta_amount', 0.0) or getattr(contract, 'leave_travel_allowance', 0.0) or 0.0) if contract else 0.0

        contract_other_allowances = 0.0
        if contract:
            contract_other_allowances = sum([
                float(getattr(contract, f, 0.0) or 0.0)
                for f in (
                    'travel_allowance', 'meal_allowance', 'medical_allowance', 'other_allowance',
                    'fixed_allowance', 'performance_bonus', 'retention_bonus',
                    'benefit_phone', 'benefit_internet', 'benefit_meal_vouchers', 'benefit_transport'
                )
            ])

        if contract_basic > 0.0:
            monthly_basic = contract_basic
            monthly_da = contract_da or (ytd_da / months_elapsed if months_elapsed > 0 else 0.0)
            monthly_hra = contract_hra or (ytd_hra / months_elapsed if months_elapsed > 0 else 0.0)
            monthly_lta = contract_lta or (ytd_lta / months_elapsed if months_elapsed > 0 else 0.0)
            monthly_allowances = contract_other_allowances or max(0.0, contract_wage - (monthly_basic + monthly_da + monthly_hra + monthly_lta)) or (ytd_allowances / months_elapsed if months_elapsed > 0 else 0.0)
        else:
            monthly_basic = contract_wage or (ytd_basic / months_elapsed if months_elapsed > 0 else 0.0)
            monthly_da = contract_da or (ytd_da / months_elapsed if months_elapsed > 0 else 0.0)
            monthly_hra = contract_hra or (ytd_hra / months_elapsed if months_elapsed > 0 else 0.0)
            monthly_lta = contract_lta or (ytd_lta / months_elapsed if months_elapsed > 0 else 0.0)
            monthly_allowances = contract_other_allowances or (ytd_allowances / months_elapsed if months_elapsed > 0 else 0.0)

        monthly_gross = monthly_basic + monthly_hra + monthly_da + monthly_lta + monthly_allowances

        projected_basic = monthly_basic * salary_projection_months
        projected_da = monthly_da * salary_projection_months
        projected_hra = monthly_hra * salary_projection_months
        projected_lta = monthly_lta * salary_projection_months
        projected_bonus = 0.0  # Bonuses are non-recurring unless already paid
        projected_allowances = monthly_allowances * salary_projection_months

        total_basic = ytd_basic + projected_basic
        total_da = ytd_da + projected_da
        total_hra = ytd_hra + projected_hra
        total_lta = ytd_lta + projected_lta
        total_bonus = ytd_bonus + projected_bonus
        total_allowances = ytd_allowances + projected_allowances

        total_projected_current_salary = (
            total_basic + total_da + total_hra + total_lta +
            total_bonus + total_allowances + total_leave_encashment +
            taxable_exit_leave_encash + taxable_gratuity
        )

        # Subtract attendance-based deductions from projected salary
        # These represent real salary not earned due to unpaid leave / LOP
        if ytd_attendance_deductions > 0:
            _logger.warning(
                "[SALARY_PROJ] Subtracting YTD attendance deductions: ₹%.2f from projected salary ₹%.2f",
                ytd_attendance_deductions, total_projected_current_salary
            )
            total_projected_current_salary -= ytd_attendance_deductions
            total_projected_current_salary = max(0.0, total_projected_current_salary)

        previous_salary_val = ytd_basic + ytd_da + ytd_hra + ytd_lta + ytd_bonus + ytd_allowances + ytd_leave_encashment + ytd_taxable_exit_leave_encash + ytd_taxable_gratuity - ytd_attendance_deductions
        remaining_projected_val = projected_basic + projected_da + projected_hra + projected_lta + projected_bonus + projected_allowances + current_leave_encashment + current_taxable_exit_leave_encash + current_taxable_gratuity

        _logger.warning("""[FORENSIC_TDS_TRACE]
step=SALARY_PROJECTION
eval_date=%s
eval_month=%s
input=employee_id:%s, fy:%s, paid_payslips_count:%s, contract_monthly_gross:INR %s
output=ytd_salary:INR %s, projected_salary:INR %s, total_annual_projected_salary:INR %s, projection_months_remaining:%s
source_method=SalaryProjectionService.project_salary
branch_used=%s""",
            eval_date,
            eval_date.strftime('%B') if hasattr(eval_date, 'strftime') else 'N/A',
            employee.id if employee else 'N/A',
            financial_year.code if financial_year else 'N/A',
            paid_months_count,
            f"{monthly_gross:,.2f}",
            f"{previous_salary_val:,.2f}",
            f"{remaining_projected_val:,.2f}",
            f"{total_projected_current_salary:,.2f}",
            salary_projection_months,
            f"HISTORICAL_YTD_PLUS_CONTRACT_PROJECTION (YTD Payslips: {paid_months_count}, Remaining Months: {salary_projection_months})"
        )

        eval_date_str = eval_date.strftime('%d-%b-%Y') if hasattr(eval_date, 'strftime') else str(eval_date)
        fy_name = financial_year.code or financial_year.name

        summary_log = f"""
========================================================
SALARY PROJECTION SUMMARY
========================================================
Financial Year             : {fy_name}
Evaluation Date            : {eval_date_str}

Monthly Gross Salary       : ₹{monthly_gross:,.2f}

Calendar Months Elapsed    : {months_elapsed}
Paid Payslip Months        : {paid_months_count}
Projection Months          : {salary_projection_months}
Remaining Payroll Periods  : {remaining_periods}

YTD Attendance Deductions      : ₹{ytd_attendance_deductions:,.2f}
Total Leave Encashment (In-Svc): ₹{total_leave_encashment:,.2f}
Total Leave Encashment (Exit)  : ₹{total_exit_leave_encash:,.2f}
Exempt Leave Encashment (Exit) : ₹{exempt_exit_leave_encash:,.2f}
Taxable Leave Encashment (Exit): ₹{taxable_exit_leave_encash:,.2f}
Total Gratuity (Received)      : ₹{total_gratuity:,.2f}
Exempt Gratuity (Statutory)    : ₹{exempt_gratuity:,.2f}
Taxable Gratuity (Excess)      : ₹{taxable_gratuity:,.2f}
Projected Annual Salary        : ₹{total_projected_current_salary:,.2f}
Projected Annual LTA           : ₹{total_lta:,.2f}
========================================================
"""
        _logger.warning(summary_log)

        return SalaryProjectionResult(
            ytd_basic=ytd_basic,
            projected_basic=projected_basic,
            total_basic=total_basic,
            ytd_da=ytd_da,
            projected_da=projected_da,
            total_da=total_da,
            ytd_hra=ytd_hra,
            projected_hra=projected_hra,
            total_hra=total_hra,
            ytd_bonus=ytd_bonus,
            projected_bonus=projected_bonus,
            total_bonus=total_bonus,
            ytd_allowances=ytd_allowances,
            projected_allowances=projected_allowances,
            total_allowances=total_allowances,
            months_elapsed=months_elapsed,
            months_remaining=salary_projection_months,
            total_projected_current_salary=total_projected_current_salary,
            ytd_lta=ytd_lta,
            projected_lta=projected_lta,
            total_lta=total_lta,
            ytd_leave_encashment=ytd_leave_encashment,
            projected_leave_encashment=projected_leave_encashment,
            total_leave_encashment=total_leave_encashment,
            ytd_gratuity=ytd_gratuity,
            exempt_gratuity=exempt_gratuity,
            taxable_gratuity=taxable_gratuity,
            total_gratuity=total_gratuity,
            ytd_exit_leave_encash=ytd_exit_leave_encash,
            total_exit_leave_encash=total_exit_leave_encash,
            exempt_exit_leave_encash=exempt_exit_leave_encash,
            taxable_exit_leave_encash=taxable_exit_leave_encash
        )
