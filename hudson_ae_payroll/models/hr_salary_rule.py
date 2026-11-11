# -*- coding: utf-8 -*-
from odoo import fields, models


class HrSalaryRule(models.Model):
    _inherit = 'hr.salary.rule'

    hds_ae_include_in_gpssa_base = fields.Boolean(
        string="Include in GPSSA Contribution Base",
        default=False,
        help="If enabled, this salary rule amount is included in the contributory wage base for UAE GPSSA pension calculations."
    )
