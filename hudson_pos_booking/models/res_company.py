# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    def _auto_init(self):
        res = super()._auto_init()
        columns = [
            ('show_survey_qr', 'BOOLEAN DEFAULT FALSE'),
            ('survey_url', 'VARCHAR'),
            ('survey_message', 'TEXT'),
            ('survey_qr_size', 'INTEGER DEFAULT 35'),
        ]
        for col, col_def in columns:
            self.env.cr.execute(f"ALTER TABLE res_company ADD COLUMN IF NOT EXISTS {col} {col_def};")
        return res

    show_survey_qr = fields.Boolean(
        string="Show Survey QR Code on Invoice",
        default=False,
    )
    survey_url = fields.Char(
        string="Survey URL",
        help="URL encoded into the Survey QR code on customer invoices.",
    )
    survey_message = fields.Text(
        string="Survey Message",
        default="Thank you for coming! Scan the Customer Survey QR code to share your feedback and suggestions.",
    )
    survey_qr_size = fields.Integer(
        string="QR Code Size (mm)",
        default=35,
        help="Size of the Survey QR Code on invoices in millimeters (default: 35 mm).",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        for f in ('show_survey_qr', 'survey_url', 'survey_message', 'survey_qr_size'):
            if f not in params:
                params.append(f)
        return params

