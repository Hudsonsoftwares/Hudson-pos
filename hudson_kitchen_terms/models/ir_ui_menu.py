# -*- coding: utf-8 -*-
from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _visible_menu_ids(self, debug=False):
        visible_ids = super()._visible_menu_ids(debug=debug)
        if self.env.context.get('_in_load_menus'):
            return visible_ids
        try:
            company = self.env['kitchen.label']._get_kitchen_company()
            if not (company.kitchen_mode and company.kitchen_task):
                kitchen_menu = self.env.ref('hudson_kitchen_terms.menu_kitchen_label', raise_if_not_found=False)
                if kitchen_menu and kitchen_menu.id in visible_ids:
                    return visible_ids - {kitchen_menu.id}
        except Exception:
            pass
        return visible_ids

    @api.model
    def load_menus(self, debug):
        menus_dict = super(IrUiMenu, self.with_context(_in_load_menus=True)).load_menus(debug)
        # Menus are fetched by a plain HTTP request: resolve the *active*
        # company (cids cookie), not the user's default company.
        company = self.env['kitchen.label']._get_kitchen_company()
        kitchen_menu = self.env.ref('hudson_kitchen_terms.menu_kitchen_label', raise_if_not_found=False)
        if not (company.kitchen_mode and company.kitchen_task):
            if kitchen_menu and kitchen_menu.id in menus_dict:
                menus_dict = dict(menus_dict)
                parent_menu = kitchen_menu.parent_id
                if parent_menu and parent_menu.id in menus_dict:
                    p_dict = dict(menus_dict[parent_menu.id])
                    p_dict['children'] = [c for c in p_dict.get('children', []) if c != kitchen_menu.id]
                    menus_dict[parent_menu.id] = p_dict
                menus_dict.pop(kitchen_menu.id, None)
            if not company.kitchen_mode:
                return menus_dict
        return self.env['kitchen.label'].apply_terms_to_menus(menus_dict, company=company)
