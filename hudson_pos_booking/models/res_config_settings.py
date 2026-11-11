# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_use_booking = fields.Boolean(related='pos_config_id.use_booking', readonly=False)
    pos_booking_appointment_type_id = fields.Many2one(
        related='pos_config_id.booking_appointment_type_id', readonly=False
    )
    pos_booking_no_show_grace_minutes = fields.Integer(
        related='pos_config_id.booking_no_show_grace_minutes', readonly=False
    )

    @api.onchange('pos_use_booking')
    def _onchange_pos_use_booking(self):
        if self.pos_use_booking and not self.pos_booking_appointment_type_id:
            config = self.pos_config_id or self.env['pos.config']
            self.pos_booking_appointment_type_id = config._get_or_create_default_table_booking_type()

