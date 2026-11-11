# -*- coding: utf-8 -*-
from odoo import fields, models


class HdsHrSnapshot(models.Model):
    _name = 'hds.hr.snapshot'
    _description = 'HR Snapshot'
    _order = 'snapshot_date desc, id desc'

    payslip_id = fields.Many2one(
        'hr.payslip',
        string='Payslip',
        required=True,
        ondelete='cascade',
        index=True,
        help="Linked payslip for which this snapshot was frozen."
    )
    payroll_period = fields.Char(
        string='Payroll Period',
        help="MM/YYYY formatted period of the payslip."
    )
    snapshot_date = fields.Datetime(
        string='Snapshot Date',
        default=fields.Datetime.now,
        required=True,
        help="Timestamp when the HR snapshot was created."
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        ondelete='set null',
        help="Identity link to the live employee record."
    )
    employee_code = fields.Char(
        string='Employee Code',
        help="Employee identification number / code at confirmation time."
    )
    department = fields.Char(
        string='Department',
        help="Employee department name at confirmation time."
    )
    designation = fields.Char(
        string='Designation',
        help="Employee job position / designation title at confirmation time."
    )
    manager = fields.Char(
        string='Manager',
        help="Employee direct manager name at confirmation time."
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        help="Company associated with this snapshot."
    )
    branch = fields.Char(
        string='Branch',
        help="Employee branch name at confirmation time."
    )
    joining_date = fields.Date(
        string='Joining Date',
        help="Employee joining date at confirmation time."
    )
    employment_type = fields.Char(
        string='Employment Type',
        help="Employee employment type label at confirmation time."
    )
    contract_id = fields.Many2one(
        'hr.version',
        string='Contract',
        ondelete='set null',
        help="Identity link to the employment contract."
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        help="Currency of monetary amounts."
    )
    wage = fields.Monetary(
        string='Wage',
        currency_field='currency_id',
        help="Total contract wage rate at confirmation time."
    )
    basic_salary = fields.Monetary(
        string='Basic Salary',
        currency_field='currency_id',
        help="Basic salary component at confirmation time."
    )
    hra = fields.Monetary(
        string='HRA',
        currency_field='currency_id',
        help="House rent allowance at confirmation time."
    )
    da = fields.Monetary(
        string='DA',
        currency_field='currency_id',
        help="Dearness allowance at confirmation time."
    )
    travel_allowance = fields.Monetary(
        string='Travel Allowance',
        currency_field='currency_id',
        help="Travel allowance at confirmation time."
    )
    pf_wage_basis = fields.Char(
        string='PF Wage Basis',
        help="Indian PF contribution basis label at confirmation time."
    )
    uan = fields.Char(
        string='UAN',
        help="Universal Account Number (EPFO) at confirmation time."
    )
    pf_member_id = fields.Char(
        string='PF Member ID',
        help="PF Member Account Number at confirmation time."
    )
    epf_applicable = fields.Boolean(
        string='EPF Applicable',
        help="Whether EPF was applicable at confirmation time."
    )
    eps_applicable = fields.Boolean(
        string='EPS Applicable',
        help="Whether EPS was applicable at confirmation time."
    )
    working_days = fields.Float(
        string='Working Days',
        digits=(16, 2),
        help="Total working days on the payslip."
    )
    paid_days = fields.Float(
        string='Paid Days',
        digits=(16, 2),
        help="Paid working days (WORK100) on the payslip."
    )
    lop_days = fields.Float(
        string='LOP Days',
        digits=(16, 2),
        help="Loss of Pay / Unpaid days (UNPAID) on the payslip."
    )
