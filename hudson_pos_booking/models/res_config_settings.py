# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    pos_use_booking = fields.Boolean(related='pos_config_id.use_booking', readonly=False)
    pos_booking_appointment_type_id = fields.Many2one(
        'appointment.type',
        related='pos_config_id.booking_appointment_type_id',
        readonly=False,
        check_company=False,
    )
    pos_booking_no_show_grace_minutes = fields.Integer(
        related='pos_config_id.booking_no_show_grace_minutes', readonly=False
    )

    show_survey_qr = fields.Boolean(
        related='company_id.show_survey_qr',
        readonly=False,
        string="Show Survey QR Code on Invoice",
    )
    survey_url = fields.Char(
        related='company_id.survey_url',
        readonly=False,
        string="Survey URL",
    )
    survey_message = fields.Text(
        related='company_id.survey_message',
        readonly=False,
        string="Survey Message",
    )
    survey_qr_size = fields.Integer(
        related='company_id.survey_qr_size',
        readonly=False,
        string="QR Code Size (mm)",
    )

    @api.onchange('pos_use_booking')
    def _onchange_pos_use_booking(self):
        if self.pos_use_booking and not self.pos_booking_appointment_type_id:
            config = self.pos_config_id or self.env['pos.config']
            self.pos_booking_appointment_type_id = config._get_or_create_default_table_booking_type()

    @api.onchange('group_product_pricelist')
    def _onchange_group_sale_pricelist(self):
        if not self.group_product_pricelist:
            had_group_pl = bool(
                self.default_get(['group_product_pricelist']).get('group_product_pricelist')
            )
            if not had_group_pl:
                return {}
        return super()._onchange_group_sale_pricelist()

    @api.model_create_multi
    def create(self, vals_list):
        had_group_pl = None
        for vals in vals_list:
            if not vals.get('group_product_pricelist') and vals.get('pos_config_id'):
                if had_group_pl is None:
                    had_group_pl = bool(
                        self.default_get(['group_product_pricelist']).get('group_product_pricelist')
                    )
                if not had_group_pl and self.env['pos.config'].sudo().search_count([('use_pricelist', '=', True)]):
                    vals['group_product_pricelist'] = True
        return super().create(vals_list)

