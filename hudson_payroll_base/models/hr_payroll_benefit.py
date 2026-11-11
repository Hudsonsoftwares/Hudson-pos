# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class HrPayrollBenefit(models.Model):
    _name = 'hr.payroll.benefit'
    _description = 'Payroll Benefit'
    _order = 'sequence, name'

    name = fields.Char(
        string='Name',
        required=True,
        help="Name of the benefit, e.g. Meal Vouchers, Phone Subscription."
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help="If the active field is set to False, it will allow you to hide the benefit without removing it."
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    benefit_type = fields.Selection([
        ('monthly_in_kind', 'Monthly Benefit in Kind'),
        ('monthly_net', 'Monthly Benefit in Net'),
        ('monthly_cash', 'Monthly Benefit in Cash'),
        ('yearly_cash', 'Yearly Benefits in Cash'),
        ('non_financial', 'Non Financial Benefits'),
    ], string='Benefit Type', required=True, default='monthly_in_kind',
       help="Categorization of the benefit type according to payroll computation.")

    benefit_source = fields.Selection([
        ('employee', 'Employee Record'),
        ('manual', 'Manual Entry'),
        ('computed', 'Computed / Rule'),
    ], string='Benefit Source', default='employee',
       help="Source from which the benefit amount is retrieved.")

    employee_field_id = fields.Many2one(
        'ir.model.fields',
        string='Employee Record Related Field',
        domain="[('model', 'in', ['hr.version', 'hr.employee', 'hr.contract'])]",
        help="Field on the employee version/contract record that stores the benefit amount."
    )
    cost_field_id = fields.Many2one(
        'ir.model.fields',
        string='Cost Field',
        domain="[('model', 'in', ['hr.version', 'hr.employee', 'hr.contract'])]",
        help="Field storing the employer cost for this benefit."
    )
    structure_type_id = fields.Many2one(
        'hr.payroll.structure.type',
        string='Salary Structure Type',
        help="Salary Structure Type this benefit applies to."
    )
    related_views = fields.Char(
        string='Related Views',
        help="Views where this benefit is displayed or referenced."
    )
    salary_rule_ids = fields.Many2many(
        'hr.salary.rule',
        'hr_payroll_benefit_salary_rule_rel',
        'benefit_id',
        'rule_id',
        string='Related Salary Rules',
        help="Salary rules linked to compute or deduct this benefit."
    )
    description = fields.Text(
        string='Description',
        help="Additional information or policy details regarding this benefit."
    )
