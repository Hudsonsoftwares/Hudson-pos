# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, models

class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.model
    def _load_pos_data_models(self, config):
        """Append appointment.booking to the loaded POS data models when booking is enabled."""
        models_list = super()._load_pos_data_models(config)
        if config.use_booking and 'appointment.booking' not in models_list:
            models_list.append('appointment.booking')
        return models_list

