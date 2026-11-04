# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

class PosOrder(models.Model):
    _inherit = 'pos.order'

    booking_id = fields.Many2one(
        'appointment.booking',
        string='Table Booking',
        readonly=True,
        index='btree_not_null',
        help="The appointment booking associated with this POS order."
    )

    @api.model
    def _load_pos_data_fields(self, config):
        fields_list = super()._load_pos_data_fields(config)
        if 'booking_id' not in fields_list:
            fields_list.append('booking_id')
        return fields_list

