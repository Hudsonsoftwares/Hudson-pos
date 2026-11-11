# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    standard_working_days_per_month = fields.Float(
        string='Standard Working Days per Month',
        default=26.0,
        help="Standard working days per month used as a default for contract rate calculations.",
    )
    standard_hours_per_day = fields.Float(
        string='Standard Hours per Day',
        default=8.0,
        help="Standard working hours per day used as a default for contract rate calculations.",
    )
