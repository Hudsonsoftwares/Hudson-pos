# -*- coding: utf-8 -*-
from odoo import fields, models


class HrPayrollDashboardWarning(models.Model):
    """Configuration model for Payroll Dashboard Warnings matching standard Odoo Enterprise style."""
    _name = 'hr.payroll.dashboard.warning'
    _description = 'Payroll Dashboard Warning'
    _order = 'sequence, id'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    color = fields.Char(string='Warning Color', default='#ef4444')
    active = fields.Boolean(string='Active', default=True)
