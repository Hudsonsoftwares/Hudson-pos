# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # Payslip of the journal item (a pay run's consolidated entry holds the items of all its payslips)
    hds_payslip_id = fields.Many2one('hr.payslip', string='Payslip', index='btree_not_null', ondelete='set null',
                                     copy=False, readonly=True)
