# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kitchen_mode = fields.Boolean(
        string="Use restaurant/kitchen terminology",
        related='company_id.kitchen_mode',
        readonly=False,
        help="When enabled, manufacturing terminology will be displayed using restaurant/kitchen terms."
    )

    def set_values(self):
        super().set_values()
        self.env['kitchen.label']._invalidate_terminology_caches()
