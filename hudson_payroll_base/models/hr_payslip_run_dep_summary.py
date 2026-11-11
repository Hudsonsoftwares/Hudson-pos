# -*- coding: utf-8 -*-
from odoo import api, fields, models


class HrPayslipRunDepSummary(models.Model):
    """Department summary snapshot generated per pay run for management visibility."""
    _name = 'hr.payslip.run.dep.summary'
    _description = 'Pay Run Department Summary'
    _order = 'department_id'

    payslip_run_id = fields.Many2one(
        'hr.payslip.run',
        string='Pay Run',
        required=True,
        ondelete='cascade',
        index=True
    )
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        ondelete='set null'
    )
    department_name = fields.Char(
        string='Department Name',
        compute='_compute_department_name',
        store=True
    )
    employee_count = fields.Integer(
        string='Payslip Count',
        default=0
    )
    gross_total = fields.Float(
        string='Total Gross Pay',
        digits='Payroll',
        default=0.0
    )
    net_total = fields.Float(
        string='Total Net Pay',
        digits='Payroll',
        default=0.0
    )

    @api.depends('department_id')
    def _compute_department_name(self):
        for record in self:
            record.department_name = record.department_id.display_name if record.department_id else 'Unassigned / General'
