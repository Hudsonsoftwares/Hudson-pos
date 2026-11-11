# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from ..base import BaseStatutoryService


class EPFValidator(BaseStatutoryService):
    """Validates employee eligibility and state prerequisites for EPF calculations."""

    def validate_eligibility(self, payslip):
        employee = payslip.employee_id
        if not employee:
            raise UserError("Cannot compute EPF: Payslip has no employee assigned.")
        if employee.hds_in_epf_applicable and employee.hds_in_vpf_type == 'percent' and employee.hds_in_vpf_percent < 0:
            raise UserError(f"Invalid VPF Percentage '{employee.hds_in_vpf_percent}' for employee {employee.name}.")
        if employee.hds_in_epf_applicable and employee.hds_in_vpf_type == 'fixed' and employee.hds_in_vpf_amount < 0:
            raise UserError(f"Invalid VPF Amount '{employee.hds_in_vpf_amount}' for employee {employee.name}.")
