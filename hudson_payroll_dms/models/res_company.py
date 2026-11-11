# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    hds_dms_store_payslips = fields.Boolean(
        string="Store Payslips in Documents",
        default=True,
        help="Store the PDF of each validated payslip in the employee's Documents folder "
             "(Payroll / <tax year>).",
    )
