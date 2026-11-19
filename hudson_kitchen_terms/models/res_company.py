# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    kitchen_mode = fields.Boolean(
        string="Kitchen Mode",
        default=False,
        help="When enabled, manufacturing terminology will be displayed using restaurant/kitchen terms."
    )
