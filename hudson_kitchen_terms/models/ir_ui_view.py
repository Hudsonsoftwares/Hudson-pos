# -*- coding: utf-8 -*-
from odoo import api, models


class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def get_views(self, views, options=None):
        result = super().get_views(views, options=options)
        if not self.env.company.kitchen_mode:
            return result
        return self.env['kitchen.label'].apply_terms_to_views_result(result)
