# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_use_booking = fields.Boolean(related='pos_config_id.use_booking', readonly=False)
    pos_booking_appointment_type_id = fields.Many2one(
        related='pos_config_id.booking_appointment_type_id', readonly=False
    )
    pos_booking_no_show_grace_minutes = fields.Integer(
        related='pos_config_id.booking_no_show_grace_minutes', readonly=False
    )

