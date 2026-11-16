# -*- encoding: utf-8 -*-
from odoo import fields, models


class EhHrVisitorDrink(models.Model):
    _name = 'eh.hr.visitor.drink'
    _description = 'Visitor Drink'
    _order = 'sequence, name'

    name = fields.Char(string='Name', required=True, translate=True)
    sequence = fields.Integer(default=10)
    image = fields.Binary(string='Image', attachment=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
    )
