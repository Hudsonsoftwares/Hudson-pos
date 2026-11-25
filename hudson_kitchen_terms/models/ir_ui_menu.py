# -*- coding: utf-8 -*-
from odoo import api, models

from .kitchen_trace import kitchen_trace


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    # --- diagnostics: catch whoever saves a menu without a name -------------
    # Always on (does not need the trace switch): it only fires in the broken
    # case and records the full call stack in Settings > Technical > Logging.
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                kitchen_trace(self.env, 'ir.ui.menu CREATE WITHOUT NAME', level='ERROR',
                              stack=True, force=True, vals=vals)
        return super().create(vals_list)

    def write(self, vals):
        if 'name' in vals and not vals.get('name'):
            kitchen_trace(self.env, 'ir.ui.menu WRITE EMPTY NAME', level='ERROR', stack=True, force=True,
                          menus=[(m.id, m.display_name) for m in self], vals=vals)
        elif vals:
            kitchen_trace(self.env, 'ir.ui.menu write', stack=True,
                          menus=[(m.id, m.display_name) for m in self], vals=vals)
        return super().write(vals)

    def _visible_menu_ids(self, debug=False):
        visible_ids = super()._visible_menu_ids(debug=debug)
        if self.env.context.get('_in_load_menus'):
            return visible_ids
        try:
            company = self.env['kitchen.label']._get_kitchen_company()
            if not (company.kitchen_mode and company.kitchen_task):
                kitchen_menu = self.env.ref('hudson_kitchen_terms.menu_kitchen_label', raise_if_not_found=False)
                if kitchen_menu and kitchen_menu.id in visible_ids:
                    kitchen_trace(self.env, 'visible_menu_ids', company=company,
                                  kitchen_labels_menu='HIDDEN')
                    return visible_ids - {kitchen_menu.id}
            kitchen_trace(self.env, 'visible_menu_ids', company=company,
                          kitchen_labels_menu='kept')
        except Exception:
            kitchen_trace(self.env, 'visible_menu_ids FAILED', level='ERROR', exc=True)
        return visible_ids

    @api.model
    def load_menus(self, debug):
        menus_dict = super(IrUiMenu, self.with_context(_in_load_menus=True)).load_menus(debug)
        # Menus are fetched by a plain HTTP request: resolve the *active*
        # company (cids cookie), not the user's default company.
        company = self.env['kitchen.label']._get_kitchen_company()
        kitchen_menu = self.env.ref('hudson_kitchen_terms.menu_kitchen_label', raise_if_not_found=False)
        mrp_root = self.env.ref('mrp.menu_mrp_root', raise_if_not_found=False)
        kitchen_trace(
            self.env, 'load_menus start', company=company,
            debug=debug,
            mrp_app_in_menus=bool(mrp_root and mrp_root.id in menus_dict),
            kitchen_labels_in_menus=bool(kitchen_menu and kitchen_menu.id in menus_dict),
            menu_count=len(menus_dict),
        )
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
                kitchen_trace(self.env, 'load_menus end (no kitchen mode, names untouched)', company=company,
                              kitchen_labels_in_menus=bool(kitchen_menu and kitchen_menu.id in menus_dict))
                return menus_dict
        try:
            result = self.env['kitchen.label'].apply_terms_to_menus(menus_dict, company=company)
        except Exception:
            kitchen_trace(self.env, 'load_menus apply_terms FAILED', level='ERROR', company=company, exc=True)
            raise
        renamed = {
            menus_dict[mid].get('name'): result[mid].get('name')
            for mid in result
            if mid in menus_dict and isinstance(result[mid], dict) and isinstance(menus_dict[mid], dict)
            and result[mid].get('name') != menus_dict[mid].get('name')
        }
        kitchen_trace(self.env, 'load_menus end (kitchen terms applied)', company=company,
                      kitchen_labels_in_menus=bool(kitchen_menu and kitchen_menu.id in result),
                      renamed=renamed)
        return result
