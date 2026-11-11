# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tools.translate import _
import logging

_logger = logging.getLogger(__name__)


class LeaveEncashmentValidationResult:
    """
    Structured data container representing Leave Encashment Eligibility Validation Result.
    Provides complete transparency for audit logging, reporting, and statutory debugging.
    """

    def __init__(
        self,
        is_eligible=False,
        reason="",
        encashable_leave_types=None,
        last_working_day=None
    ):
        self.is_eligible = is_eligible
        self.reason = reason
        self.encashable_leave_types = encashable_leave_types or self._empty_recordset()
        self.last_working_day = last_working_day

    def _empty_recordset(self):
        """Returns empty list when no leave types are set."""
        return []

    def to_dict(self):
        """Serialize validation result into dictionary for audit trail / JSON logging."""
        leave_types_list = []
        if self.encashable_leave_types:
            for lt in self.encashable_leave_types:
                lt_name = lt.name if isinstance(lt.name, str) else str(lt.name)
                leave_types_list.append({
                    'id': lt.id,
                    'name': lt_name,
                    'code': getattr(lt, 'code', False) or '',
                })
        return {
            'is_eligible': self.is_eligible,
            'reason': self.reason,
            'encashable_leave_types': leave_types_list,
            'last_working_day': str(self.last_working_day) if self.last_working_day else None,
        }

    def __repr__(self):
        count = len(self.encashable_leave_types) if self.encashable_leave_types else 0
        return (
            f"<LeaveEncashmentValidationResult eligible={self.is_eligible} "
            f"encashable_leave_types={count} last_working_day='{self.last_working_day}' "
            f"reason='{self.reason}'>"
        )


class LeaveEncashmentValidator:
    """
    Enterprise Leave Encashment Eligibility Validator for Hudson Indian Payroll.
    Single Responsibility: Validate statutory and company policy eligibility
    for Leave Encashment before calculation occurs.
    """

    def __init__(self, env):
        self.env = env

    def validate(self, employee, last_working_day=None):
        """
        Main entry point to perform Leave Encashment validation.

        Checks:
        1. Employee exists.
        2. Company Leave Encashment is enabled.
        3. Last working day is provided (or resolved from employee departure date).
        4. At least one existing hr.leave.type is configured with include_in_leave_encashment = True.

        :param employee: hr.employee recordset (required)
        :param last_working_day: str or date (optional, employee last working day)
        :return: LeaveEncashmentValidationResult
        """
        # Check 1: Employee Exists
        if not employee:
            return LeaveEncashmentValidationResult(
                is_eligible=False,
                reason=_("No employee provided for Leave Encashment validation.")
            )

        company = employee.company_id or self.env.company

        # Check 2: Company Configuration Enablement Check
        if not company or not getattr(company, 'hds_in_enable_leave_encashment', False):
            return LeaveEncashmentValidationResult(
                is_eligible=False,
                reason=_("Leave Encashment is disabled for company '%s'.") % (company.name if company else 'Unknown')
            )

        # Check 3: Last Working Day Provided or Resolvable
        resolved_lwd = self._resolve_last_working_day(employee, last_working_day)
        if not resolved_lwd:
            return LeaveEncashmentValidationResult(
                is_eligible=False,
                reason=_("Last working day cannot be determined for Leave Encashment validation.")
            )

        # Check 4: Configured Encashable Leave Types Check
        encashable_leave_types = self.env['hr.work.entry.type'].search([
            ('include_in_leave_encashment', '=', True)
        ])
        if not encashable_leave_types:
            return LeaveEncashmentValidationResult(
                is_eligible=False,
                last_working_day=resolved_lwd,
                reason=_("No leave types are configured for Leave Encashment ('Include in Leave Encashment' is not checked on any leave type).")
            )

        # All Checks Passed
        return LeaveEncashmentValidationResult(
            is_eligible=True,
            reason=_("Eligible for Leave Encashment."),
            encashable_leave_types=encashable_leave_types,
            last_working_day=resolved_lwd
        )

    def _resolve_last_working_day(self, employee, explicit_date=None):
        """Resolves employee last working day from explicit argument or employee departure date."""
        if explicit_date:
            return fields.Date.from_string(explicit_date)
        if getattr(employee, 'departure_date', None):
            return fields.Date.from_string(employee.departure_date)
        return None
