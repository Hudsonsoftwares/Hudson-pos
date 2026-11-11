# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import fields, models

class QualityDevice(models.Model):
    _name = 'quality.device'
    _description = 'Quality Device'

    name = fields.Char(string='Name', required=True)

class QualityOboxDevice(models.Model):
    _name = 'quality.obox.device'
    _description = 'Quality Obox Device'

    name = fields.Char(string='Name', required=True)
