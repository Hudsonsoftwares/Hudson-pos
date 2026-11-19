# -*- coding: utf-8 -*-
from odoo import models


class Http(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        kitchen_mode = bool(self.env.company.kitchen_mode)
        result['kitchen_mode'] = kitchen_mode
        if kitchen_mode:
            result['kitchen_terms'] = self.env['kitchen.label'].get_terms_dict()
        else:
            result['kitchen_terms'] = {}
        return result
