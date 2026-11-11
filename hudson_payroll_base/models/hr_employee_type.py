# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import api, fields, models


class HrEmployeeType(models.Model):
    """Classification of employee types for payroll and pay run filtering."""
    _inherit = 'hr.employee.type'
    active = fields.Boolean(string='Active', default=True)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # employee_type_id is natively provided by Odoo 20 hr module (related to version_id.employee_type_id)
    bank_account_id = fields.Many2one(
        'res.partner.bank',
        string='Bank Account Number',
        compute='_compute_bank_account_id',
        inverse='_inverse_bank_account_id',
        store=True,
        help="Employee primary bank account from Personal tab for payroll payment transfers and payment advice"
    )

    @api.depends('bank_account_ids', 'primary_bank_account_id')
    def _compute_bank_account_id(self):
        for emp in self:
            primary = getattr(emp, 'primary_bank_account_id', False)
            if not primary and getattr(emp, 'bank_account_ids', False):
                primary = emp.bank_account_ids[0]
            emp.bank_account_id = primary

    def _inverse_bank_account_id(self):
        for emp in self:
            if emp.bank_account_id and emp.bank_account_id not in emp.bank_account_ids:
                emp.bank_account_ids = [(4, emp.bank_account_id.id)]

    @api.depends('bank_account_ids', 'salary_distribution')
    def _compute_primary_bank_account_id(self):
        for employee in self:
            dist = employee.salary_distribution or {}
            if employee.bank_account_ids:
                try:
                    primary_account = min(
                        employee.bank_account_ids,
                        key=lambda acc: dist.get(str(acc.id), {}).get("sequence", float("inf")) if isinstance(dist, dict) else float("inf"),
                    )
                except Exception:
                    primary_account = employee.bank_account_ids[0]
                employee.primary_bank_account_id = primary_account
            else:
                employee.primary_bank_account_id = False
    pay_by_attendance = fields.Boolean(
        string='Pay by Attendance',
        related='version_id.pay_by_attendance',
        readonly=False,
        help="If enabled, attendance adjustments (overtime / shortage) apply to payslips."
    )
    enable_attendance_threshold = fields.Boolean(
        string='Enable Attendance Threshold',
        related='version_id.enable_attendance_threshold',
        readonly=False,
        help="If enabled, when Pay by Attendance is OFF, employee must work at least the minimum threshold days to receive 100% fixed salary."
    )
    min_attendance_threshold_days = fields.Float(
        string='Minimum Attendance Days',
        related='version_id.min_attendance_threshold_days',
        readonly=False,
        help="Minimum days required in the month to qualify for full fixed salary when Pay by Attendance is OFF. If worked days are below this, salary is prorated. If 0 days worked, salary is 0."
    )
    threshold_days_manually_set = fields.Boolean(
        string='Threshold Days Manually Set',
        related='version_id.threshold_days_manually_set',
        readonly=True,
    )
    threshold_enabled_manually_set = fields.Boolean(
        string='Threshold Enabled Manually Set',
        related='version_id.threshold_enabled_manually_set',
        readonly=True,
    )

    def action_reset_to_company_threshold(self):
        for emp in self:
            if emp.version_id:
                emp.version_id.action_reset_to_company_threshold()
