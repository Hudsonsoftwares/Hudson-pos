# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrPayslipLine(models.Model):
    """Line items computed for each salary rule on a payslip."""
    _name = 'hr.payslip.line'
    _description = 'Payslip Line'
    _order = 'contract_id, sequence, id'

    name = fields.Char(string='Description', required=True)
    code = fields.Char(string='Code', required=True, index=True)
    sequence = fields.Integer(string='Sequence', default=10, index=True)
    slip_id = fields.Many2one(
        'hr.payslip',
        string='Pay Slip',
        required=True,
        ondelete='cascade',
        index=True
    )
    salary_rule_id = fields.Many2one(
        'hr.salary.rule',
        string='Rule',
        required=True
    )
    category_id = fields.Many2one(
        'hr.salary.rule.category',
        string='Category',
        related='salary_rule_id.category_id',
        store=True,
        readonly=True,
        index=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        index=True
    )
    contract_id = fields.Many2one(
        'hr.version',
        string='Contract',
        required=True,
        index=True
    )
    rate = fields.Float(string='Rate (%)', default=100.0, digits='Payroll Rate')
    amount = fields.Float(string='Amount', default=0.0, digits='Payroll')
    quantity = fields.Float(string='Quantity', default=1.0, digits='Payroll')
    total = fields.Float(
        string='Total',
        compute='_compute_total',
        store=True,
        digits='Payroll'
    )
    appears_on_payslip = fields.Boolean(
        string='Appears on Payslip',
        default=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='slip_id.company_id',
        store=True,
        readonly=True
    )
    payslip_run_id = fields.Many2one(
        'hr.payslip.run',
        string='Pay Run',
        related='slip_id.payslip_run_id',
        store=True,
        readonly=True,
        index=True
    )

    @api.depends('quantity', 'amount', 'rate')
    def _compute_total(self):
        for line in self:
            line.total = float(line.quantity) * line.amount * line.rate / 100.0
