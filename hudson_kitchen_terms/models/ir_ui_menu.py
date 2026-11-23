# -*- coding: utf-8 -*-
from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def load_menus(self, debug):
        menus_dict = super().load_menus(debug)
        # Menus are fetched by a plain HTTP request: resolve the *active*
        # company (cids cookie), not the user's default company.
        company = self.env['kitchen.label']._get_kitchen_company()
        if not company.kitchen_mode:
            return menus_dict
        return self.env['kitchen.label'].apply_terms_to_menus(menus_dict, company=company)
