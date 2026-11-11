# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import fields, models


class QualityTag(models.Model):
    _name = 'quality.tag'
    _description = 'Quality Tag'
    _order = 'name'

    name = fields.Char(required=True)
    color = fields.Integer(string='Color Index')
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        "A quality tag with this name already exists.",
    )
