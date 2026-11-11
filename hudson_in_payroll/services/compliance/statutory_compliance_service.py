# -*- coding: utf-8 -*-
from odoo import _
from odoo.exceptions import UserError

class StatutoryComplianceValidationService:
    """
    Service for validating mandatory statutory identifiers (EPF UAN, ESIC IP Number, LWF Number)
    and evaluating employee statutory compliance status before payroll calculations or report exports.
    """

    def __init__(self, env):
        self.env = env

    def validate_employee_epf(self, employee):
        """
        Validates EPF statutory identifier (UAN) for an employee.
        :param employee: hr.employee record
        :return: tuple (is_valid: bool, error_reason: str or False)
        """
        if not getattr(employee, 'hds_in_epf_applicable', False):
            return True, False

        uan = getattr(employee, 'hds_in_uan', False)
        if not uan:
            return False, _("Missing UAN (Universal Account Number)")

        uan_clean = uan.strip()
        if not uan_clean.isdigit():
            return False, _("UAN must contain digits only. Current value: '%s'") % uan
        if len(uan_clean) != 12:
            return False, _("UAN must be exactly 12 digits. Provided length: %d digits") % len(uan_clean)

        return True, False

    def validate_employee_esic(self, employee):
        """
        Validates ESIC statutory identifier (IP Number) for an employee.
        :param employee: hr.employee record
        :return: tuple (is_valid: bool, error_reason: str or False)
        """
        if not getattr(employee, 'hds_in_esic_applicable', False):
            return True, False

        ip_no = (
            getattr(employee, 'hds_in_esic_ip_number', False)
            or getattr(employee, 'hds_in_esic_number', False)
            or getattr(employee, 'esic_number', False)
        )
        if not ip_no or not str(ip_no).strip():
            return False, _("Missing ESIC IP Number")

        return True, False

    def validate_employee_lwf(self, employee):
        """
        Validates LWF statutory identifier for an employee.
        :param employee: hr.employee record
        :return: tuple (is_valid: bool, error_reason: str or False)
        """
        if not getattr(employee, 'hds_in_lwf_applicable', False):
            return True, False

        lwf_no = (
            getattr(employee, 'hds_in_lwf_number', False)
            or getattr(employee, 'registration_number', False)
            or getattr(employee, 'barcode', False)
            or getattr(employee, 'employee_code', False)
            or getattr(employee, 'identification_id', False)
            or str(employee.id)
        )
        if not lwf_no:
            return False, _("Missing LWF Registration / Employee Number")

        return True, False

    def validate_employee_all(self, employee):
        """
        Evaluates overall statutory compliance for an employee across EPF, ESIC, LWF, PAN, and Bank.
        :param employee: hr.employee record
        :return: dict containing detailed status
        """
        epf_valid, epf_err = self.validate_employee_epf(employee)
        esic_valid, esic_err = self.validate_employee_esic(employee)
        lwf_valid, lwf_err = self.validate_employee_lwf(employee)

        pan = getattr(employee, 'hds_in_pan', False) or getattr(employee, 'pan_no', False) or getattr(employee, 'pan', False)
        pan_valid = bool(pan and len(pan.strip()) == 10)

        bank_valid = bool(
            getattr(employee, 'bank_account_id', False)
            or getattr(employee, 'primary_bank_account_id', False)
            or getattr(employee, 'bank_account_ids', False)
            or getattr(getattr(employee, 'work_contact_id', None), 'bank_account_id', False)
            or getattr(getattr(employee, 'address_home_id', None), 'bank_account_id', False)
        )

        all_valid = epf_valid and esic_valid and lwf_valid and pan_valid and bank_valid

        errors = []
        if epf_err:
            errors.append(f"EPF: {epf_err}")
        if esic_err:
            errors.append(f"ESIC: {esic_err}")
        if lwf_err:
            errors.append(f"LWF: {lwf_err}")
        if not pan_valid:
            errors.append("PAN: Missing or invalid 10-char PAN")
        if not bank_valid:
            errors.append("Bank: Missing bank account details")

        return {
            'epf_valid': epf_valid,
            'epf_err': epf_err,
            'esic_valid': esic_valid,
            'esic_err': esic_err,
            'lwf_valid': lwf_valid,
            'lwf_err': lwf_err,
            'pan_valid': pan_valid,
            'bank_valid': bank_valid,
            'is_compliant': all_valid,
            'error_list': errors,
        }

    def validate_scope_compliance(self, employees, statutory_type='epf', report_title='EPF-ECR'):
        """
        Enforces statutory identifier compliance for a group of employees before report generation or payslip processing.
        Raises UserError if any applicable employee has missing/invalid numbers.

        :param employees: hr.employee recordset
        :param statutory_type: 'epf', 'esic', or 'lwf'
        :param report_title: Display title for the error message
        """
        if not employees:
            return

        invalid_details = []

        for emp in employees:
            if statutory_type == 'epf':
                valid, reason = self.validate_employee_epf(emp)
            elif statutory_type == 'esic':
                valid, reason = self.validate_employee_esic(emp)
            elif statutory_type == 'lwf':
                valid, reason = self.validate_employee_lwf(emp)
            else:
                valid, reason = True, False

            if not valid:
                emp_code = getattr(emp, 'registration_number', False) or str(emp.id)
                invalid_details.append(f"• {emp.name} (ID: {emp_code}) — {reason}")

        if invalid_details:
            stat_name = statutory_type.upper()
            msg = _(
                "%(title)s cannot be generated: %(count)d applicable employee(s) have missing or invalid %(stat)s identifiers.\n\n"
                "Affected Employees:\n%(details)s\n\n"
                "Please update the employee profile(s) with valid statutory identifiers before exporting the report."
            ) % {
                'title': report_title,
                'count': len(invalid_details),
                'stat': stat_name,
                'details': "\n".join(invalid_details),
            }
            raise UserError(msg)
