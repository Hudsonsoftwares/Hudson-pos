# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

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
        default="Thank you for coming! Scan the QR code below to fill the survey and share your suggestions.",
    )
    survey_qr_size = fields.Integer(
        string="QR Code Size (mm)",
        default=35,
        help="Size of the Survey QR Code on invoices in millimeters (default: 35 mm).",
    )
