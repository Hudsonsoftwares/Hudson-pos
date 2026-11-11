# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import _, api, fields, models
from .demo_data_loader import load_pos_demo_data, clear_pos_demo_data


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_demo_data_loaded = fields.Boolean(
        string="POS Demo Data Loaded",
        compute='_compute_pos_demo_data_loaded',
        help="Indicates whether the Restaurant & Cafe demo data is currently populated."
    )

    def _compute_pos_demo_data_loaded(self):
        is_loaded = bool(self.env['ir.model.data'].sudo().search_count([
            ('module', '=', 'hudson_pos_demo_data'),
            ('model', '=', 'product.template'),
        ]))
        for rec in self:
            rec.pos_demo_data_loaded = is_loaded

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'group_product_pricelist' in fields_list:
            res['group_product_pricelist'] = True
        return res

    @api.onchange('group_product_pricelist')
    def _onchange_group_sale_pricelist(self):
        """Suppress the false 'deactivating pricelist' warning dialog when navigating POS Settings."""
        return {}

    def action_load_pos_demo_data(self):
        """Button in POS Settings to load restaurant & cafe demo data."""
        load_pos_demo_data(self.env)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Restaurant & Cafe Demo Data Activated"),
                'message': _("Full Demo Data (Products, Combos, Floor Tables, Kitchen Display, Sample Orders, Recruitment Jobs, and eLearning Courses) successfully loaded!"),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_clear_pos_demo_data(self):
        """Button in POS Settings to turn off / clean demo data."""
        clear_pos_demo_data(self.env)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Demo Data Turned Off"),
                'message': _("Restaurant & Cafe demo data has been cleaned up. The system is in clean state for production."),
                'type': 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_toggle_pos_demo_data(self):
        """Toggle action: Turns ON if OFF, Turns OFF if ON."""
        is_loaded = bool(self.env['ir.model.data'].sudo().search_count([
            ('module', '=', 'hudson_pos_demo_data'),
            ('model', '=', 'product.template'),
        ]))
        if is_loaded:
            return self.action_clear_pos_demo_data()
        else:
            return self.action_load_pos_demo_data()
