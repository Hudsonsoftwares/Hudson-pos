# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    kitchen_mode = fields.Boolean(
        string="Kitchen Mode",
        default=False,
        help="When enabled, manufacturing terminology will be displayed using restaurant/kitchen terms."
    )

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        enabled = companies.filtered('kitchen_mode')
        if enabled:
            self.env['kitchen.label']._ensure_company_labels(enabled)
        return companies

    def write(self, vals):
        res = super().write(vals)
        if vals.get('kitchen_mode'):
            self.env['kitchen.label']._ensure_company_labels(self.filtered('kitchen_mode'))
        self.env['kitchen.label']._invalidate_terminology_caches()
        return res
