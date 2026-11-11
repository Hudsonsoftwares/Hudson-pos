from datetime import datetime, time
from odoo import fields# pyrefly: ignore [missing-import]
from odoo.tools.translate import _# pyrefly: ignore [missing-import]
import logging

_logger = logging.getLogger(__name__)


class LeaveEncashmentCalculationData:
    """
    Data Transfer Object (DTO) containing all collected and prepared input data
    required for Leave Encashment Calculation. Pure data container passed to LeaveEncashmentCalculator.
    """

    def __init__(
        self,
        employee_id=None,
        company_id=None,
        contract_id=None,
        last_working_day=None,
        wage_base=0.0,
        basic_wage=0.0,
        da_amount=0.0,
        month_divisor=26.0,
        max_encashable_days=300.0,
        leave_breakdown=None,
        total_eligible_days=0.0
    ):
        self.employee_id = employee_id
        self.company_id = company_id
        self.contract_id = contract_id
        self.last_working_day = last_working_day
        self.wage_base = wage_base
        self.basic_wage = basic_wage
        self.da_amount = da_amount
        self.month_divisor = month_divisor
        self.max_encashable_days = max_encashable_days
        self.leave_breakdown = leave_breakdown or []
        self.total_eligible_days = total_eligible_days

    def to_dict(self):
        """Serialize data object into dictionary for audit logging and diagnostics."""
        return {
            'employee_id': self.employee_id,
            'company_id': self.company_id,
            'contract_id': self.contract_id,
            'last_working_day': str(self.last_working_day) if self.last_working_day else None,
            'wage_base': float(self.wage_base),
            'basic_wage': float(self.basic_wage),
            'da_amount': float(self.da_amount),
            'month_divisor': float(self.month_divisor),
            'max_encashable_days': float(self.max_encashable_days),
            'leave_breakdown': self.leave_breakdown,
            'total_eligible_days': float(self.total_eligible_days),
        }

    def __repr__(self):
        return (
            f"<LeaveEncashmentCalculationData emp_id={self.employee_id} "
            f"lwd='{self.last_working_day}' wage_base={self.wage_base} "
            f"total_eligible_days={self.total_eligible_days} "
            f"div={self.month_divisor} max_days={self.max_encashable_days}>"
        )


class LeaveEncashmentDataService:
    """
    Enterprise Data Service for Hudson Indian Payroll Leave Encashment Module.
    Single Responsibility: Gather, extract, and prepare all input data required for Leave Encashment calculation.
    Does NOT perform monetary calculation or statutory eligibility validation.
    """

    PARAM_MONTH_DIVISOR = 'hds_in_leave_encashment_month_divisor'
    PARAM_MAX_ENCASHABLE_DAYS = 'hds_in_max_encashable_days'

    def __init__(self, env):
        self.env = env

    def prepare_calculation_data(self, employee, contract=None, last_working_day=None, calc_date=None):
        """
        Gathers all required input data for Leave Encashment calculation and returns a structured DTO.

        :param employee: hr.employee recordset (required)
        :param contract: hr.version recordset (optional)
        :param last_working_day: str or date (optional)
        :param calc_date: str or date (optional)
        :return: LeaveEncashmentCalculationData
        """
        if not employee:
            raise ValueError(_("Employee is required to prepare Leave Encashment calculation data."))

        # 1. Resolve Active Contract
        resolved_contract = contract or self._resolve_active_contract(employee)

        # 2. Resolve Last Working Day
        resolved_lwd = self._resolve_last_working_day(employee, resolved_contract, last_working_day)

        # 3. Retrieve Wage Base (Last-Drawn Basic + DA from Contract)
        salary_info = self._retrieve_wage_base(employee, resolved_contract)

        # 4. Resolve Statutory Rule Parameters (Month Divisor 26 & Max Days 300)
        ref_date = calc_date or resolved_lwd or fields.Date.today()
        params = self._resolve_rule_parameters(ref_date)

        # 5. Extract Eligible Leave Types & Remaining Leave Balances as of Last Working Day
        leave_info = self._retrieve_encashable_leave_data(employee, resolved_lwd)

        # 6. Construct Data Transfer Object
        return LeaveEncashmentCalculationData(
            employee_id=employee.id,
            company_id=employee.company_id.id if employee.company_id else self.env.company.id,
            contract_id=resolved_contract.id if resolved_contract else None,
            last_working_day=resolved_lwd,
            wage_base=salary_info['wage_base'],
            basic_wage=salary_info['basic'],
            da_amount=salary_info['da'],
            month_divisor=params['month_divisor'],
            max_encashable_days=params['max_encashable_days'],
            leave_breakdown=leave_info['leave_breakdown'],
            total_eligible_days=leave_info['total_eligible_days']
        )

    def _resolve_active_contract(self, employee):
        """Finds the active or most relevant contract for the employee."""
        if getattr(employee, 'version_id', False):
            return employee.version_id
        contracts = self.env['hr.version'].search([
            ('employee_id', '=', employee.id)
        ], order='id desc', limit=1)
        if isinstance(contracts, list):
            return contracts[0] if contracts else None
        return contracts if contracts else None

    def _resolve_last_working_day(self, employee, contract=None, explicit_date=None):
        """Resolves last working day with priority: explicit -> departure_date -> contract end -> today."""
        if explicit_date:
            return fields.Date.from_string(explicit_date)
        if getattr(employee, 'departure_date', None):
            return fields.Date.from_string(employee.departure_date)
        if contract and getattr(contract, 'date_end', None):
            return fields.Date.from_string(contract.date_end)
        return fields.Date.today()

    def _retrieve_wage_base(self, employee, contract=None):
        """Retrieves last-drawn Basic Salary and Dearness Allowance (DA) from contract."""
        basic = 0.0
        da = 0.0
        if contract:
            basic = float(getattr(contract, 'basic_salary', 0.0) or getattr(contract, 'wage', 0.0) or 0.0)
            da = float(getattr(contract, 'da', 0.0) or getattr(contract, 'da_amount', 0.0) or 0.0)

        wage_base = basic + da
        return {
            'basic': basic,
            'da': da,
            'wage_base': wage_base,
        }

    def _resolve_rule_parameters(self, calc_date):
        """Resolves rule parameters: Month Divisor (default 26.0) and Max Days (default 300.0)."""
        rule_param_obj = self.env['hr.rule.parameter']

        def _get_param(code, default_val):
            try:
                val = rule_param_obj._get_parameter_value(code, calc_date)
                return float(val)
            except Exception as e:
                _logger.warning("Could not resolve rule parameter '%s' for date %s: %s. Using default %s.",
                                code, calc_date, str(e), default_val)
                return float(default_val)

        return {
            'month_divisor': _get_param(self.PARAM_MONTH_DIVISOR, 26.0),
            'max_encashable_days': _get_param(self.PARAM_MAX_ENCASHABLE_DAYS, 300.0),
        }

    def _retrieve_encashable_leave_data(self, employee, target_date):
        """Retrieves virtual remaining leaves for all leave types configured with include_in_leave_encashment = True."""
        eligible_leave_types = self.env['hr.work.entry.type'].search([
            ('include_in_leave_encashment', '=', True)
        ])
        breakdown = []
        total_days = 0.0

        for lt in eligible_leave_types:
            rem_days = self._retrieve_remaining_leaves(lt, employee, target_date)
            lt_name = lt.name if isinstance(lt.name, str) else str(lt.name)
            breakdown.append({
                'leave_type_id': lt.id,
                'leave_type_name': lt_name,
                'leave_type_code': getattr(lt, 'code', False) or '',
                'remaining_days': float(rem_days),
            })
            total_days += float(rem_days)

        return {
            'leave_breakdown': breakdown,
            'total_eligible_days': total_days,
        }

    def _convert_rem_to_days(self, rem, uom, employee):
        """Converts balance to days if unit of measure is hour."""
        if rem is None:
            return 0.0
        val = float(rem)
        if uom == 'hour':
            hours_per_day = (
                employee.resource_calendar_id.hours_per_day
                if employee and getattr(employee, 'resource_calendar_id', None) and employee.resource_calendar_id.hours_per_day
                else 8.0
            )
            return val / (hours_per_day or 8.0)
        return val

    def _retrieve_remaining_leaves(self, leave_type, employee, target_date):
        """Retrieves virtual remaining leaves as of target_date using Odoo 19/20 native allocation methods."""
        try:
            # Method A: get_allocation_data if callable
            if hasattr(leave_type, 'get_allocation_data'):
                try:
                    alloc_data = leave_type.get_allocation_data(employee, target_date=target_date)
                    if alloc_data and employee in alloc_data:
                        for entry in alloc_data[employee]:
                            if isinstance(entry, (list, tuple)) and len(entry) >= 2 and isinstance(entry[1], dict):
                                dict_data = entry[1]
                                rem = dict_data.get('virtual_remaining_leaves')
                                if rem is None:
                                    rem = dict_data.get('remaining_leaves')
                                if rem is not None:
                                    uom = dict_data.get('unit_of_measure', 'day')
                                    return self._convert_rem_to_days(rem, uom, employee)
                    elif isinstance(alloc_data, dict):
                        rem = alloc_data.get('virtual_remaining_leaves')
                        if rem is None:
                            rem = alloc_data.get('remaining_leaves')
                        if rem is not None:
                            uom = alloc_data.get('unit_of_measure', 'day')
                            return self._convert_rem_to_days(rem, uom, employee)
                    elif isinstance(alloc_data, (int, float)):
                        return float(alloc_data)
                except (TypeError, Exception):
                    pass

            # Method B: get_employees_days with_context(date=target_date)
            if hasattr(leave_type, 'get_employees_days'):
                res = leave_type.with_context(date=target_date).get_employees_days([employee.id])
                if res and employee.id in res:
                    emp_res = res[employee.id]
                    if isinstance(emp_res, dict):
                        v_rem = emp_res.get('virtual_remaining_leaves')
                        rem = v_rem if v_rem is not None else emp_res.get('remaining_leaves')
                        if rem is not None:
                            uom = emp_res.get('unit_of_measure', 'day')
                            return self._convert_rem_to_days(rem, uom, employee)

            # Method C: Direct ORM calculation fallback (handling Odoo 20 work_entry_type_id)
            alloc_model = self.env['hr.leave.allocation']
            leave_model = self.env['hr.leave']
            alloc_field = 'work_entry_type_id' if 'work_entry_type_id' in alloc_model._fields else 'holiday_status_id'
            leave_field = 'work_entry_type_id' if 'work_entry_type_id' in leave_model._fields else 'holiday_status_id'

            # Normalize target_date to end-of-day datetime to ensure leaves taken on target_date are included
            target_d = fields.Date.to_date(target_date) or fields.Date.today()
            target_dt = datetime.combine(target_d, time.max)

            allocations = alloc_model.search([
                ('employee_id', '=', employee.id),
                (alloc_field, '=', leave_type.id),
                ('state', '=', 'validate'),
                '|',
                ('date_from', '=', False),
                ('date_from', '<=', target_d),
                '|',
                ('date_to', '=', False),
                ('date_to', '>=', target_d),
            ])
            total_allocated = sum(allocations.mapped('number_of_days'))

            leaves_taken = leave_model.search([
                ('employee_id', '=', employee.id),
                (leave_field, '=', leave_type.id),
                ('state', '=', 'validate'),
                ('date_from', '<=', target_dt)
            ])
            total_taken = sum(leaves_taken.mapped('number_of_days'))

            return max(0.0, float(total_allocated - total_taken))
        except Exception as e:
            _logger.warning("Failed to compute remaining leaves for leave_type %s: %s", leave_type.id, str(e))
            return 0.0
