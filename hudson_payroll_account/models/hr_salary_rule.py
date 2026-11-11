# -*- coding: utf-8 -*-
from odoo import fields, models


class HrSalaryRule(models.Model):
    _name = 'hr.salary.rule'
    _inherit = ['hr.salary.rule', 'analytic.mixin']

    account_debit_id = fields.Many2one(
        'account.account',
        string='Debit Account',
        help="Debit account for salary expenses"
    )
    account_credit_id = fields.Many2one(
        'account.account',
        string='Credit Account',
        help="Credit account for salary payable / liabilities"
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        help="Analytic account associated with this salary rule"
    )
    account_tax_id = fields.Many2one(
        'account.tax',
        string='Tax',
        help="Tax account associated with this salary rule"
    )
    split_names = fields.Boolean(
        string='Split on names',
        help="Tick this if this rule should produce a distinct journal item for each employee in the journal entry."
    )
    excluded_from_net = fields.Boolean(
        string='Excluded from Net',
        help="Tick this if this salary rule should be excluded from the net calculation."
    )
    set_employee_on_account_line = fields.Boolean(
        string='Set employee on account line',
        help="Tick this if the rule's journal item should have the employee partner set."
    )
    debit_tax_grid_ids = fields.Many2many(
        'account.account.tag',
        'hr_salary_rule_debit_tax_tag_rel',
        'rule_id',
        'tag_id',
        string='Debit Tax Grids',
        domain="[('applicability', '=', 'taxes')]",
        help="The tax grids to apply on the debit line."
    )
    credit_tax_grid_ids = fields.Many2many(
        'account.account.tag',
        'hr_salary_rule_credit_tax_tag_rel',
        'rule_id',
        'tag_id',
        string='Credit Tax Grids',
        domain="[('applicability', '=', 'taxes')]",
        help="The tax grids to apply on the credit line."
    )
