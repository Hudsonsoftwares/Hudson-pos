# -*- coding: utf-8 -*-
import logging
from datetime import date
# pyrefly: ignore [missing-import]
from odoo import fields
from ..base import BaseStatutoryService
from ..audit.audit_service import StatutoryAuditSession
from ..payroll.work_location_service import PayrollWorkLocationService
from .professional_tax_slab_service import ProfessionalTaxSlabService
from .pt_validator import PTValidator
from .pt_calculator import PTCalculator

from .pt_periodicity_strategy import PTPeriodicityStrategyRegistry

_logger = logging.getLogger(__name__)


class ProfessionalTaxResult:
    """
    Structured Result Container representing the end-to-end Professional Tax calculation result.
    Encapsulates final deduction amount, state, company, slab, override metadata, and validation status.
    """

    def __init__(
        self,
        amount=0.0,
        state=None,
        company=None,
        slab=None,
        override_applied=False,
        override_month=None,
        override_amount=None,
        is_valid=True,
        validation_status="VALID",
        failure_reason="",
        period_liability=0.0
    ):
        self.amount = amount
        self.period_liability = period_liability if period_liability is not None else amount
        self.state = state
        self.company = company
        self.slab = slab
        self.salary_from = getattr(slab, 'salary_from', None) if slab else None
        self.salary_to = getattr(slab, 'salary_to', None) if slab else None
        self.periodicity = getattr(slab, 'periodicity', None) if slab else None
        self.override_applied = override_applied
        self.override_month = override_month
        self.override_amount = override_amount
        self.is_valid = is_valid
        self.validation_status = validation_status
        self.failure_reason = failure_reason

    def to_dict(self):
        """Returns a structured dictionary representation of the orchestrated result."""
        return {
            'amount': self.amount,
            'period_liability': self.period_liability,
            'state_id': self.state.id if self.state else False,
            'state_name': self.state.name if self.state else False,
            'company_id': self.company.id if self.company else False,
            'company_name': self.company.name if self.company else False,
            'salary_from': self.salary_from,
            'salary_to': self.salary_to,
            'periodicity': self.periodicity,
            'override_applied': self.override_applied,
            'override_month': self.override_month,
            'override_amount': self.override_amount,
            'is_valid': self.is_valid,
            'validation_status': self.validation_status,
            'failure_reason': self.failure_reason,
            'slab': self.slab.to_dict() if (self.slab and hasattr(self.slab, 'to_dict')) else False,
        }

    def __repr__(self):
        return (
            f"<ProfessionalTaxResult amount={self.amount} state={self.state.name if self.state else None} "
            f"valid={self.is_valid} status=''{self.validation_status}'' override_applied={self.override_applied}>"
        )


class ProfessionalTaxService(BaseStatutoryService):
    """
    Domain Facade and Thin Orchestration Service for Indian Professional Tax (PT).
    Coordinates sub-services in strict SOA order:
    1. Context Extraction (Payslip / Localdict / Explicit parameters)
    2. Company Configuration Check (res.company PT settings)
    3. Work Location Resolution (PayrollWorkLocationService)
    4. Periodicity & Strategy Resolution (PTPeriodicityStrategyRegistry)
    5. Wage Aggregation (PayrollWageAggregationService / Strategy)
    6. PT Slab Resolution (ProfessionalTaxSlabService)
    7. Eligibility & Deduction Schedule Validation (PTValidator)
    8. PT Amount Calculation (PTCalculator)
    9. Statutory Audit Session Integration (Audit Readiness)
    """

    def __init__(self, env, localdict=None):
        super().__init__(env)
        self.localdict = localdict or {}
        self.location_service = PayrollWorkLocationService(env)
        self.slab_service = ProfessionalTaxSlabService(env)
        from .pt_period_config_service import PTPeriodScheduleService
        self.sched_service = PTPeriodScheduleService(env)
        self.validator = PTValidator(env)
        self.calculator = PTCalculator(env)

    def _extract_context(self, payslip=None, employee=None, salary=0.0, eval_date=None, company=None, gender=None, localdict=None):
        """
        Extracts execution parameters from explicit arguments or payslip/localdict context.
        """
        dict_ctx = localdict if localdict is not None else self.localdict
        slip = payslip or dict_ctx.get('payslip_record') or dict_ctx.get('payslip') or dict_ctx.get('ps')

        target_emp = employee
        if not target_emp and slip:
            target_emp = getattr(slip, 'employee_id', False)
        if not target_emp:
            target_emp = dict_ctx.get('employee')

        target_date = eval_date
        if not target_date and slip:
            target_date = getattr(slip, 'date_to', False) or getattr(slip, 'date_from', False)
        if not target_date:
            target_date = dict_ctx.get('eval_date') or fields.Date.today()
        if isinstance(target_date, str):
            target_date = fields.Date.from_string(target_date)

        target_company = company
        if not target_company and slip:
            target_company = getattr(slip, 'company_id', False)
        if not target_company and target_emp:
            target_company = getattr(target_emp, 'company_id', False)
        if not target_company:
            target_company = dict_ctx.get('company') or self.env.company

        target_salary = salary
        if not target_salary and dict_ctx:
            categories = dict_ctx.get('categories')
            gross_val = 0.0
            if categories:
                gross_val = (
                    getattr(categories, 'GROSS_PT', 0.0) or
                    getattr(categories, 'PT_BASE', 0.0) or
                    getattr(categories, 'GROSS', 0.0) or 0.0
                )
            if not gross_val:
                gross_val = dict_ctx.get('gross_salary') or dict_ctx.get('salary') or 0.0
            if not gross_val and target_emp and getattr(target_emp, 'contract_id', False):
                gross_val = getattr(target_emp.contract_id, 'wage', 0.0) or 0.0

            # Deduct attendance shortage (SHORT) and unpaid leave (UNPAID) to obtain attendance-earned wages
            rules_obj = dict_ctx.get('rules')
            short_ded = abs(float(
                dict_ctx.get('SHORT') or
                getattr(getattr(rules_obj, 'SHORT', None), 'total', 0.0) or
                0.0
            ))
            unpaid_ded = abs(float(
                dict_ctx.get('UNPAID') or
                getattr(getattr(rules_obj, 'UNPAID', None), 'total', 0.0) or
                0.0
            ))

            if short_ded <= 0.0:
                worked_days = dict_ctx.get('worked_days')
                contract = dict_ctx.get('contract') or (slip.contract_id if slip else False)
                if worked_days and contract and hasattr(worked_days, 'SHORTAGE') and worked_days.SHORTAGE and getattr(contract, 'pay_by_attendance', False):
                    short_hrs = float(getattr(worked_days.SHORTAGE, 'number_of_hours', 0.0) or 0.0)
                    if short_hrs > 0.0 and hasattr(contract, 'get_period_shortage_rate'):
                        rate = abs(contract.get_period_shortage_rate(slip.date_from if slip else False, slip.date_to if slip else False))
                        short_ded = min(short_hrs * rate, gross_val)

            if unpaid_ded <= 0.0:
                worked_days = dict_ctx.get('worked_days')
                contract = dict_ctx.get('contract') or (slip.contract_id if slip else False)
                if worked_days and contract and hasattr(worked_days, 'UNPAID') and worked_days.UNPAID and not getattr(contract, 'pay_by_attendance', False) and not getattr(contract, 'enable_attendance_threshold', True):
                    unpaid_hrs = float(getattr(worked_days.UNPAID, 'number_of_hours', 0.0) or 0.0)
                    unpaid_days = float(getattr(worked_days.UNPAID, 'number_of_days', 0.0) or 0.0)
                    if unpaid_hrs > 0.0 and hasattr(contract, 'get_period_shortage_rate'):
                        rate = abs(contract.get_period_shortage_rate(slip.date_from if slip else False, slip.date_to if slip else False))
                        unpaid_ded = min(unpaid_hrs * rate, gross_val)
                    elif unpaid_days > 0.0 and hasattr(contract, 'get_period_day_rate'):
                        rate = abs(contract.get_period_day_rate(slip.date_from if slip else False, slip.date_to if slip else False))
                        unpaid_ded = min(unpaid_days * rate, gross_val)

            if short_ded <= 0.0 and slip and slip.line_ids:
                s_lines = slip.line_ids.filtered(lambda l: l.code == 'SHORT')
                if s_lines:
                    short_ded = abs(sum(s_lines.mapped('total')))
            if unpaid_ded <= 0.0 and slip and slip.line_ids:
                u_lines = slip.line_ids.filtered(lambda l: l.code == 'UNPAID')
                if u_lines:
                    unpaid_ded = abs(sum(u_lines.mapped('total')))

            total_loss = short_ded + unpaid_ded
            if gross_val > 0.0 and total_loss > 0.0:
                target_salary = max(0.0, round(gross_val - total_loss, 2))
            else:
                target_salary = gross_val

        if not target_salary and target_emp and getattr(target_emp, 'contract_id', False):
            target_salary = getattr(target_emp.contract_id, 'wage', 0.0) or 0.0

        try:
            target_salary = float(target_salary or 0.0)
        except (TypeError, ValueError):
            target_salary = 0.0

        if slip and hasattr(slip, '_get_earned_wage_ratio') and target_salary > 0.0:
            ratio = slip._get_earned_wage_ratio(localdict=dict_ctx)
            if ratio <= 0.0:
                target_salary = 0.0
            elif ratio < 1.0 and abs(target_salary - (gross_val if 'gross_val' in locals() else target_salary)) < 0.01:
                target_salary = max(0.0, round(target_salary * ratio, 2))

        target_gender = gender
        if not target_gender and target_emp:
            target_gender = self.slab_service.resolve_employee_gender(target_emp)

        return slip, target_emp, target_salary, target_date, target_company, target_gender

    def get_fy_pt_already_deducted(self, employee, eval_date, current_slip=None) -> float:
        """
        Calculates cumulative Professional Tax already deducted for the employee
        in the current Indian Financial Year (April 1 to March 31) up to eval_date.
        Excludes the current payslip to avoid duplicate counting.
        """
        if not employee or not eval_date:
            return 0.0

        if isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)
        if not eval_date:
            eval_date = fields.Date.today()

        fy_start = date(eval_date.year, 4, 1) if eval_date.month >= 4 else date(eval_date.year - 1, 4, 1)

        domain = [
            ('employee_id', '=', employee.id),
            ('state', 'in', ('verify', 'done', 'paid')),
            ('date_from', '>=', fy_start),
            ('date_from', '<=', eval_date),
        ]
        curr_id = getattr(current_slip, 'id', False)
        if current_slip and isinstance(curr_id, int):
            domain.append(('id', '!=', curr_id))

        slips = self.env['hr.payslip'].search(domain)
        if not slips:
            return 0.0

        total_pt = 0.0
        for s in slips:
            for line in s.line_ids:
                if line.code in ('PT', 'HDS_IN_PT') or getattr(line.category_id, 'code', '') == 'PT':
                    total_pt += abs(line.total or 0.0)

        return float(total_pt)

    def compute_pt(self, payslip=None, employee=None, salary=0.0, eval_date=None, company=None, gender=None, localdict=None, state=None, is_simulation=False):
        """
        Orchestrates end-to-end Professional Tax computation via SOA components and periodicity strategies.

        :param payslip: hr.payslip recordset or None
        :param employee: hr.employee recordset or None
        :param salary: float (monthly gross/taxable salary override)
        :param eval_date: datetime.date or str or None
        :param company: res.company recordset or None
        :param gender: str or None
        :param localdict: dict or None (payslip execution context)
        :param state: res.country.state recordset or None (optional override)
        :param is_simulation: bool (True when simulating for salary revision/preview without deducting prior payslips)
        :return: ProfessionalTaxResult instance
        """
        slip, emp, sal, date_eval, comp, gdr = self._extract_context(
            payslip=payslip, employee=employee, salary=salary,
            eval_date=eval_date, company=company, gender=gender, localdict=localdict
        )

        # 0. Employee PT Applicability Check
        if emp and hasattr(emp, 'hds_in_pt_applicable') and not emp.hds_in_pt_applicable:
            _logger.info("Professional Tax (PT) is disabled for employee '%s'", emp.name)
            return ProfessionalTaxResult(
                amount=0.0,
                state=state,
                company=comp,
                is_valid=False,
                validation_status='DISABLED_EMPLOYEE',
                failure_reason=f"Professional Tax (PT) is disabled for employee '{emp.name}'."
            )

        with StatutoryAuditSession(self.env, slip, statutory_module="pt", rule_code="PT", calculation_type="employee_deduction") as audit:
            audit.attach_input("employee_id", emp.id if emp else False)
            audit.attach_input("employee_name", emp.name if emp else False)
            audit.attach_input("eval_date", str(date_eval))
            audit.attach_input("single_month_salary", sal)
            audit.attach_input("company_id", comp.id if comp else False)

            # 0b. Zero Earned Wage Guard (not applied in simulation mode)
            if not is_simulation and sal <= 0.0:
                audit.attach_parameter("validation_status", "ZERO_WAGE")
                audit.attach_output("pt_deduction", 0.0)
                audit.log_message("Zero earned wage in current payroll.")
                _logger.debug("Professional Tax zero wage for employee '%s'", emp.name if emp else 'Unknown')
                return ProfessionalTaxResult(
                    amount=0.0,
                    state=state,
                    company=comp,
                    slab=False,
                    is_valid=False,
                    validation_status='ZERO_WAGE',
                    failure_reason="Zero earned wage in current payroll.",
                    period_liability=0.0
                )

            # 1. Location Service State Resolution
            state = state or self.location_service.get_work_state(emp)
            audit.attach_parameter("resolved_state", state.name if state else False)

            # 2. Period Schedule & Strategy Resolution (Decoupled from slabs)
            period_sched = self.sched_service.resolve_schedule(state, company=comp, eval_date=date_eval)
            periodicity = period_sched.periodicity if period_sched else self.slab_service.resolve_state_periodicity(state, company=comp)
            strategy = PTPeriodicityStrategyRegistry.get_strategy(periodicity)
            audit.attach_parameter("periodicity", periodicity)
            if period_sched:
                audit.attach_parameter("period_schedule_id", period_sched.id)
                audit.attach_parameter("deduction_strategy", period_sched.deduction_strategy)

            # Minimum Service Days Guard (e.g. Kerala 60-day rule)
            if period_sched and getattr(period_sched, 'min_service_days', 0) > 0 and emp:
                meets_min, s_days, min_days = self.sched_service.check_min_service_days(period_sched, emp, eval_date=date_eval)
                audit.attach_parameter("service_days", s_days)
                audit.attach_parameter("min_service_days", min_days)
                if not meets_min:
                    reason = f"Employee appointment days ({s_days}) in period window below minimum required ({min_days} days)."
                    audit.attach_parameter("validation_status", "BELOW_MIN_SERVICE_DAYS")
                    audit.attach_output("pt_deduction", 0.0)
                    audit.log_message(reason)
                    _logger.debug("PT Below min service days for '%s': %s < %s", emp.name, s_days, min_days)
                    return ProfessionalTaxResult(
                        amount=0.0,
                        state=state,
                        company=comp,
                        slab=False,
                        is_valid=False,
                        validation_status='BELOW_MIN_SERVICE_DAYS',
                        failure_reason=reason,
                        period_liability=0.0
                    )

            # 3. Wage Aggregation Basis Resolution (Monthly vs Half-Yearly vs Quarterly)
            salary_basis = strategy.calculate_wage_basis(
                self.env, emp, date_eval, current_slip=slip, current_slip_gross=sal, company=comp, period_schedule=period_sched, is_simulation=is_simulation
            )
            audit.attach_input("salary_basis", salary_basis)

            # 4. Validator Eligibility & Deduction Schedule Check
            val_result = self.validator.validate(
                employee=emp, salary=salary_basis, eval_date=date_eval, company=comp, state=state, gender=gdr, periodicity=periodicity, strategy=strategy, period_schedule=period_sched
            )
            audit.attach_parameter("validation_status", val_result.validation_status)
            audit.attach_parameter("is_valid", val_result.is_valid)
            audit.attach_parameter("failure_reason", val_result.failure_reason)

            slab_rec = val_result.matched_slab.slab_record if (val_result and val_result.matched_slab) else None
            if period_sched:
                audit.attach_parameter("deduction_strategy", period_sched.deduction_strategy)
                audit.attach_parameter("deduction_month", period_sched.deduction_month or False)

            if not val_result.is_valid:
                audit.log_message(val_result.failure_reason)
                return ProfessionalTaxResult(
                    amount=0.0,
                    state=state or val_result.resolved_state,
                    company=comp,
                    slab=val_result.matched_slab,
                    is_valid=False,
                    validation_status=val_result.validation_status,
                    failure_reason=val_result.failure_reason
                )

            # 5. Calculator Amount Computation & Strategy Recovery
            calc_result = self.calculator.calculate(slab=val_result.matched_slab, eval_date=date_eval)
            period_liability = calc_result.pt_amount

            final_deduction = strategy.calculate_payroll_deduction(
                self.env,
                employee=emp,
                period_liability=period_liability,
                eval_date=date_eval,
                current_slip=slip,
                period_schedule=period_sched,
                is_simulation=is_simulation
            )
            _logger.debug("Statutory PT Liability: %s | Current Payroll Deduction: %s", period_liability, final_deduction)

            # 5b. Constitutional Statutory Cap Guard (Article 276(2) Constitution of India: Max ₹2,500/year)
            if not is_simulation and emp and final_deduction > 0.0:
                ytd_pt = self.get_fy_pt_already_deducted(emp, date_eval, current_slip=slip)
                statutory_cap = 2500.0
                available_cap = max(0.0, statutory_cap - ytd_pt)
                if final_deduction > available_cap:
                    shortfall = round(final_deduction - available_cap, 2)
                    audit.attach_parameter("pt_capped_annual_ceiling", True)
                    audit.attach_parameter("pt_annual_cap_shortfall", shortfall)
                    audit.attach_parameter("original_pt_deduction_before_annual_cap", final_deduction)
                    audit.log_message(
                        f"PT deduction capped from ₹{final_deduction} to ₹{available_cap} "
                        f"by Article 276(2) Constitution of India statutory annual ceiling of ₹2,500 (YTD Paid: ₹{ytd_pt})."
                    )
                    _logger.info(
                        "Employee '%s' PT deduction capped from ₹%s to ₹%s by Article 276(2) annual ceiling of ₹2,500 (YTD Paid: ₹%s)",
                        emp.name, final_deduction, available_cap, ytd_pt
                    )
                    final_deduction = available_cap

            # 6. Net Pay Guard: PT capped at GROSS + DED (categories in localdict)
            # Skipped when is_simulation or categories are missing
            if not is_simulation and localdict and 'categories' in localdict:
                cats = localdict.get('categories')
                gross_amt = 0.0
                ded_amt = 0.0
                if cats:
                    gross_amt = getattr(cats, 'GROSS', 0.0) if hasattr(cats, 'GROSS') else (cats.get('GROSS', 0.0) if isinstance(cats, dict) else 0.0)
                    ded_amt = getattr(cats, 'DED', 0.0) if hasattr(cats, 'DED') else (cats.get('DED', 0.0) if isinstance(cats, dict) else 0.0)
                try:
                    gross_amt = float(gross_amt or 0.0)
                    ded_amt = float(ded_amt or 0.0)
                except (ValueError, TypeError):
                    gross_amt, ded_amt = 0.0, 0.0

                # Note: In Odoo payroll localdict DED is typically negative; ensure safe subtraction regardless of sign
                net_available = max(0.0, round(gross_amt - abs(ded_amt), 2)) if ded_amt > 0 else max(0.0, round(gross_amt + ded_amt, 2))
                audit.attach_parameter("guard_gross", gross_amt)
                audit.attach_parameter("guard_ded", ded_amt)
                audit.attach_parameter("guard_net_available", net_available)

                if final_deduction > net_available:
                    shortfall = round(final_deduction - net_available, 2)
                    audit.attach_parameter("pt_capped", True)
                    audit.attach_parameter("pt_shortfall", shortfall)
                    audit.attach_parameter("original_pt_deduction", final_deduction)
                    audit.log_message(f"PT deduction capped at net available pay ({net_available}). Shortfall: {shortfall}")
                    _logger.debug("PT deduction capped from %s to %s (net available: %s)", final_deduction, net_available, net_available)
                    final_deduction = net_available

            audit.attach_parameter("period_liability", period_liability)
            audit.attach_parameter("normal_amount", calc_result.normal_amount)
            audit.attach_parameter("override_applied", calc_result.override_applied)
            audit.attach_parameter("override_month", calc_result.override_month)
            audit.attach_parameter("override_amount", calc_result.override_amount)
            audit.attach_output("pt_deduction", final_deduction)

            if final_deduction <= 0.0 and period_sched and not self.sched_service.should_deduct(period_sched, eval_date=date_eval, employee=emp):
                reason = "Non-deduction month for periodic schedule; waiting for period end."
                audit.attach_parameter("validation_status", "WAITING_FOR_PERIOD_END")
                audit.attach_output("pt_deduction", 0.0)
                audit.log_message(reason)
                return ProfessionalTaxResult(
                    amount=0.0,
                    state=val_result.resolved_state or state,
                    company=comp,
                    slab=val_result.matched_slab,
                    override_applied=calc_result.override_applied,
                    override_month=calc_result.override_month,
                    override_amount=calc_result.override_amount,
                    is_valid=False,
                    validation_status='WAITING_FOR_PERIOD_END',
                    failure_reason=reason,
                    period_liability=period_liability
                )

            return ProfessionalTaxResult(
                amount=final_deduction,
                state=val_result.resolved_state or state,
                company=comp,
                slab=val_result.matched_slab,
                override_applied=calc_result.override_applied,
                override_month=calc_result.override_month,
                override_amount=calc_result.override_amount,
                is_valid=True,
                validation_status='VALID',
                failure_reason="Professional Tax deduction calculated successfully.",
                period_liability=period_liability
            )

    def compute_pt_amount(self, payslip=None, employee=None, salary=0.0, eval_date=None, company=None, gender=None, localdict=None):
        """
        Helper method returning float deduction amount for direct salary rule consumption.
        """
        res = self.compute_pt(
            payslip=payslip, employee=employee, salary=salary,
            eval_date=eval_date, company=company, gender=gender, localdict=localdict
        )
        return res.amount

    def compute_pt_reconciliation_for_exit(self, employee, last_working_day=None):
        """
        Calculates statutory Professional Tax reconciliation on employee exit / final settlement.
        Follows state statutory acts:
        1. For monthly states: computes PT due on exit month earned wage, minus any PT deducted on exit month slips.
        2. For half-yearly states (Kerala, Tamil Nadu, etc.): computes statutory slab liability on cumulative
           gross earned in the current half-year, minus PT already deducted in preceding payslips of that half-year.
        Returns dict with keys:
            'pt_net_payable': float,
            'period_liability': float,
            'pt_already_deducted': float,
            'state_name': str,
            'description': str
        """
        if not employee:
            return {'pt_net_payable': 0.0, 'period_liability': 0.0, 'pt_already_deducted': 0.0, 'description': ''}

        lwd = last_working_day or fields.Date.today()
        if isinstance(lwd, str):
            lwd = fields.Date.from_string(lwd)

        pt_res = self.compute_pt(
            employee=employee,
            eval_date=lwd,
            company=employee.company_id,
            is_simulation=True
        )

        period_liability = float(getattr(pt_res, 'period_liability', 0.0) or pt_res.amount or 0.0)
        already_deducted = self.get_fy_pt_already_deducted(employee, lwd)

        net_payable = max(0.0, round(period_liability - already_deducted, 2)) if period_liability > 0.0 else 0.0
        state_name = pt_res.state.name if pt_res.state else 'Unknown'

        desc = f"Statutory PT reconciliation for {state_name}: Period liability {period_liability:.2f} less prior deductions {already_deducted:.2f}."

        return {
            'pt_net_payable': net_payable,
            'period_liability': period_liability,
            'pt_already_deducted': already_deducted,
            'state_name': state_name,
            'description': desc,
        }

