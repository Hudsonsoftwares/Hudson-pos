# -*- coding: utf-8 -*-
from odoo import fields, models


class HrVersion(models.Model):
    _inherit = 'hr.version'

    journal_id = fields.Many2one(
        'account.journal',
        string='Salary Journal',
        domain="[('type', '=', 'general')]",
        help="Journal used for accounting entries of this employee's payslips"
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        help="Default analytic account for this employee contract"
    )
