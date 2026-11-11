# -*- coding: utf-8 -*-
from odoo import fields, models


class HrSalaryRuleSection(models.Model):
    """Salary Rule Sections organize salary rules and input lines in salary structures."""
    _name = 'hr.salary.rule.section'
    _description = 'Salary Rule Section'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)
    struct_ids = fields.Many2many(
        'hr.payroll.structure',
        'hr_salary_rule_section_structure_rel',
        'section_id',
        'struct_id',
        string='Available in Salary Structure'
    )
    rule_ids = fields.One2many(
        'hr.salary.rule',
        'section_id',
        string='Salary Rules'
    )
    description = fields.Text(string='Description')
