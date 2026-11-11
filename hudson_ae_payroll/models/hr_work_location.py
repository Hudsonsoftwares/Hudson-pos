# -*- coding: utf-8 -*-
from odoo import fields, models


class HrWorkLocation(models.Model):
    _inherit = 'hr.work.location'

    uae_emirate_id = fields.Many2one(
        'uae.emirate',
        string='UAE Emirate',
        help='The UAE Emirate in which this physical work location or office is located.'
    )
