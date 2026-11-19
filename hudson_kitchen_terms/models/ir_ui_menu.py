# -*- coding: utf-8 -*-
from odoo import api, models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    @api.model
    def load_menus(self, debug):
        menus_dict = super().load_menus(debug)
        if not self.env.company.kitchen_mode:
            return menus_dict
        return self.env['kitchen.label'].apply_terms_to_menus(menus_dict)
