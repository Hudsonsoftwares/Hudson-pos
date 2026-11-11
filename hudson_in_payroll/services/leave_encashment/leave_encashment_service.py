# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import fields
import logging
try:
    from ..base import BaseStatutoryService
    from ..audit.audit_service import StatutoryAuditSession
    from .leave_encashment_validator import LeaveEncashmentValidator
    from .leave_encashment_data_service import LeaveEncashmentDataService
    from .leave_encashment_calculator import LeaveEncashmentCalculator
except (ImportError, ValueError):
    # pyrefly: ignore [missing-import]
    from base_service import BaseStatutoryService
    from leave_encashment_validator import LeaveEncashmentValidator
    from leave_encashment_data_service import LeaveEncashmentDataService
    from leave_encashment_calculator import LeaveEncashmentCalculator
    StatutoryAuditSession = None

_logger = logging.getLogger(__name__)


class LeaveEncashmentService(BaseStatutoryService):
    """
    Orchestration Facade Service for Leave Encashment statutory calculation.
    Coordinates SOA components:
    1. LeaveEncashmentValidator
    2. LeaveEncashmentDataService
    3. LeaveEncashmentCalculator
    4. StatutoryAuditSession
    """

    def __init__(self, env, localdict=None):
        super().__init__(env)
        self.localdict = localdict or {}
        self.validator = LeaveEncashmentValidator(env)
        self.data_service = LeaveEncashmentDataService(env)
        self.calculator = LeaveEncashmentCalculator()

    def _extract_payslip_and_employee(self, payslip=None):
        slip = payslip or self.localdict.get('payslip_record') or self.localdict.get('payslip')
        employee = False
        eval_date = fields.Date.today()
        company = self.env.company

        if slip:
            employee = getattr(slip, 'employee_id', False)
            eval_date = getattr(slip, 'date_to', fields.Date.today()) or fields.Date.today()
            company = getattr(slip, 'company_id', False) or self.env.company
        elif self.localdict.get('employee'):
            employee = self.localdict.get('employee')
            company = getattr(employee, 'company_id', False) or self.env.company

        return slip, employee, eval_date, company

    def compute_leave_encashment(
        self,
        employee=None,
        last_working_day=None,
        contract=None,
        payslip=None,
        calc_date=None
    ):
        """
        Computes Leave Encashment amount via SOA component orchestration.

        :param employee: optional hr.employee recordset (resolved from payslip or localdict if None)
        :param last_working_day: optional str or date (employee last working day)
        :param contract: optional hr.version recordset
        :param payslip: optional hr.payslip recordset
        :param calc_date: optional reference date
        :return: float (payable leave encashment amount)
        """
        if employee and getattr(employee, '_name', '') == 'hr.payslip':
            if not payslip:
                payslip = employee
            employee = payslip.employee_id

        slip, resolved_emp, eval_date, company = self._extract_payslip_and_employee(payslip)
        emp = employee or resolved_emp
        ctr = contract or (getattr(slip, 'contract_id', None) if slip else None) or self.localdict.get('contract')
        ref_date = calc_date or eval_date

        with StatutoryAuditSession(
            self.env,
            slip,
            statutory_module="leave_encashment",
            rule_code="LEAVE_ENCASH",
            calculation_type="final_settlement"
        ) as audit:
            audit.attach_input("employee_id", emp.id if emp else False)
            audit.attach_input("employee_name", emp.name if emp else False)
            audit.attach_input("eval_date", str(ref_date))

            # 1. Statutory & Policy Eligibility Validation
            val_result = self.validator.validate(
                employee=emp,
                last_working_day=last_working_day
            )
            audit.attach_parameter("is_eligible", val_result.is_eligible)
            audit.attach_parameter("validation_reason", val_result.reason)
            audit.attach_parameter("last_working_day", str(val_result.last_working_day) if val_result.last_working_day else None)

            if not val_result.is_eligible:
                audit.log_message(val_result.reason)
                audit.attach_output("final_amount", 0.0)
                return 0.0

            # 2. Gather & Prepare Calculation Data DTO
            calc_data = self.data_service.prepare_calculation_data(
                employee=emp,
                contract=ctr,
                last_working_day=last_working_day or val_result.last_working_day,
                calc_date=ref_date
            )
            audit.attach_parameter("wage_base", calc_data.wage_base)
            audit.attach_parameter("basic_wage", calc_data.basic_wage)
            audit.attach_parameter("da_amount", calc_data.da_amount)
            audit.attach_parameter("month_divisor", calc_data.month_divisor)
            audit.attach_parameter("max_encashable_days", calc_data.max_encashable_days)
            audit.attach_parameter("total_eligible_days", calc_data.total_eligible_days)
            audit.attach_parameter("leave_breakdown", calc_data.leave_breakdown)

            # 3. Perform Pure Calculation
            calc_result = self.calculator.calculate(calc_data)
            audit.attach_output("leave_days_used", calc_result.leave_days_used)
            audit.attach_output("daily_rate_used", calc_result.daily_rate_used)
            audit.attach_output("raw_amount", calc_result.raw_amount)
            audit.attach_output("capped_amount", calc_result.capped_amount)
            audit.attach_output("final_amount", calc_result.final_amount)
            audit.attach_output("is_cap_applied", calc_result.is_cap_applied)
            audit.attach_output("max_encashable_days_used", calc_result.max_encashable_days_used)

            return calc_result.final_amount

    def compute_in_service_encashment(self, payslip=None):
        """
        Computes In-Service Leave Encashment payable on a regular monthly payslip.
        Processes approved transaction requests (hds.leave.encashment.request)
        for the employee overlapping the payslip period.

        :param payslip: hr.payslip recordset
        :return: float (payable leave encashment amount)
        """
        # pyrefly: ignore [missing-import]
        from odoo.tools.float_utils import float_round
        slip, resolved_emp, eval_date, company = self._extract_payslip_and_employee(payslip)
        emp = resolved_emp
        if not slip or not emp or not company:
            return 0.0

        if not getattr(company, 'hds_in_enable_leave_encashment', False):
            return 0.0

        requests = self.env['hds.leave.encashment.request'].search([
            ('employee_id', '=', emp.id),
            ('state', '=', 'approved'),
            ('request_date', '<=', slip.date_to),
            ('payslip_id', 'in', (False, slip.id)),
        ])
        if not requests:
            return 0.0

        ctr = getattr(slip, 'contract_id', None) or (emp.version_id if hasattr(emp, 'version_id') else None)
        if not ctr:
            contracts = self.env['hr.version'].search([
                ('employee_id', '=', emp.id)
            ], order='id desc', limit=1)
            ctr = contracts[0] if isinstance(contracts, list) else (contracts if contracts else None)

        total_amount = 0.0
        req_audit_details = []

        with StatutoryAuditSession(
            self.env,
            slip,
            statutory_module="leave_encashment",
            rule_code="LEAVE_ENCASH",
            calculation_type="in_service_encashment"
        ) as audit:
            audit.attach_input("employee_id", emp.id)
            audit.attach_input("employee_name", emp.name)
            audit.attach_input("payslip_id", slip.id)
            audit.attach_input("date_from", str(slip.date_from))
            audit.attach_input("date_to", str(slip.date_to))
            audit.attach_input("request_count", len(requests))

            for req in requests:
                amt = req.calculate_payout_amount(contract=ctr)
                total_amount += amt
                # Link request to this payslip in draft
                if req.payslip_id != slip:
                    req.write({'payslip_id': slip.id})

                req_audit_details.append({
                    'request_id': req.id,
                    'request_name': req.name,
                    'leave_type': req.leave_type_id.name,
                    'requested_days': req.requested_days,
                    'policy_name': req.policy_id.name,
                    'formula_basis': req.policy_id.calculation_basis,
                    'amount': amt,
                })

            audit.attach_parameter("encashment_requests", req_audit_details)
            audit.attach_output("final_amount", total_amount)

        return float_round(total_amount, precision_digits=2)
