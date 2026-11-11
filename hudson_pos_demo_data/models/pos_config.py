# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import _, api, models
from .demo_data_loader import load_pos_demo_data, clear_pos_demo_data


class PosConfig(models.Model):
    _inherit = 'pos.config'

    @api.model
    def action_load_pos_demo_data_all(self):
        """Loads complete demo data across all POS configurations."""
        load_pos_demo_data(self.env)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Restaurant & Cafe Demo Data Loaded"),
                'message': _("Full Demo Data (Restaurant & Cafe Shops, 40+ Products, Floor Tables, Recruitment Job Openings, Inventory Stock, and Loyalty Programs) successfully loaded!"),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_load_pos_demo_data(self):
        """Button / Action triggered by user in POS backend to load demo data."""
        self.ensure_one()
        load_pos_demo_data(self.env, [self.id])
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Restaurant & Cafe Demo Data Loaded"),
                'message': _("Full Demo Data (Desserts, Chocolates, Combos, Pricelists, Inventory Stock, and Loyalty & Promotion programs) successfully loaded and linked!"),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    @api.model
    def action_clear_pos_demo_data(self):
        """Button / Action triggered by user to turn off / remove demo data."""
        clear_pos_demo_data(self.env)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Demo Data Turned Off"),
                'message': _("Restaurant & Cafe demo data has been removed and cleaned up. Ready for clean client production use."),
                'type': 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }
