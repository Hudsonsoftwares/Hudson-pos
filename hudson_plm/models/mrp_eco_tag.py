# -*- coding: utf-8 -*-
from odoo import models, fields

class MrpEcoTag(models.Model):
    _name = 'mrp.eco.tag'
    _description = 'ECO Tag'

    name = fields.Char('Name', required=True)
    color = fields.Integer('Color Index')
