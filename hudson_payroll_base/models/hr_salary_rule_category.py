# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class HrSalaryRuleCategory(models.Model):
    """Salary Rule Category for grouping rules and computing subtotals."""
    _name = 'hr.salary.rule.category'
    _description = 'Salary Rule Category'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    code = fields.Char(string='Code', required=True, index=True)
    parent_id = fields.Many2one(
        'hr.salary.rule.category',
        string='Parent',
        index=True,
        ondelete='cascade'
    )
    children_ids = fields.One2many(
        'hr.salary.rule.category',
        'parent_id',
        string='Children'
    )
    sequence = fields.Integer(string='Sequence', default=10, index=True)
    note = fields.Text(string='Description')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=False,
        help="If set, this rule category will only be available to the specified company. If empty, it is shared across all companies."
    )

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)', 'The code of the salary rule category must be unique per company!'),
    ]

    @api.constrains('parent_id')
    def _check_parent_id(self):
        if self._has_cycle('parent_id'):
            raise ValidationError(_('Error! You cannot create recursive salary rule categories.'))
