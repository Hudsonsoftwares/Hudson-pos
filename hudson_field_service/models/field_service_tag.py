# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class FieldServiceTag(models.Model):
    _name = 'field.service.tag'
    _description = 'Field Service Tag'
    _order = 'name'

    name = fields.Char(string='Tag Name', required=True, translate=True)
    color = fields.Integer(string='Color Index')

    _name_uniq = models.Constraint(
        'unique (name)',
        'Tag name already exists!',
    )
