# -*- coding: utf-8 -*-
from odoo import models

from .kitchen_trace import kitchen_trace


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
        result['kitchen_mrp_app_ids'] = []
        if kitchen_mode:
            result['kitchen_terms'] = self.env['kitchen.label'].get_terms_dict(company=company)
            mrp_root = self.env.ref('mrp.menu_mrp_root', raise_if_not_found=False)
            shopfloor_menu = self.env.ref('hudson_shopfloor.menu_hudson_shopfloor', raise_if_not_found=False)
            app_ids = [mrp_root.id] if mrp_root else []
            if shopfloor_menu:
                app_ids.append(shopfloor_menu.id)
            result['kitchen_mrp_app_ids'] = app_ids
            result['kitchen_mrp_app_id'] = mrp_root.id if mrp_root else False
        kitchen_trace(self.env, 'session_info', company=company,
                      session_kitchen_mode=kitchen_mode,
                      session_current_company=(result.get('user_companies') or {}).get('current_company'),
                      kitchen_terms_count=len(result['kitchen_terms']))
        return result
