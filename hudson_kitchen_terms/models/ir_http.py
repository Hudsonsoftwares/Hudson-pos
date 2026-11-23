# -*- coding: utf-8 -*-
from odoo import models


class Http(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super().session_info()
        # session_info is built during the page load (plain HTTP request):
        # resolve the active company from the cids cookie.
        company = self.env['kitchen.label']._get_kitchen_company()
        kitchen_mode = bool(company.kitchen_mode)
        result['kitchen_mode'] = kitchen_mode
        result['kitchen_terms'] = {}
        result['kitchen_mrp_app_id'] = False
        if kitchen_mode:
            result['kitchen_terms'] = self.env['kitchen.label'].get_terms_dict(company=company)
            mrp_root = self.env.ref('mrp.menu_mrp_root', raise_if_not_found=False)
            result['kitchen_mrp_app_id'] = mrp_root.id if mrp_root else False
        return result
