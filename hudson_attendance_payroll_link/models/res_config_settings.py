# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    standard_working_days_per_month = fields.Float(
        related='company_id.standard_working_days_per_month',
        readonly=False,
        string='Standard Working Days per Month'
    )
    standard_hours_per_day = fields.Float(
        related='company_id.standard_hours_per_day',
        readonly=False,
        string='Standard Hours per Day'
    )
    # Note: Overtime rates are now configured via Standard Odoo 19 Overtime Rulesets.
    # Go to: Attendances → Configuration → Overtime Rulesets
