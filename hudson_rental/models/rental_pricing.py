# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class RentalPricing(models.Model):
    _name = 'rental.pricing'
    _description = 'Rental Pricing Configuration'
    _order = 'product_tmpl_id, duration_unit, duration'

    name = fields.Char(string='Description', compute='_compute_name', store=True)
    product_tmpl_id = fields.Many2one('product.template', string='Product', required=True, ondelete='cascade')
    duration = fields.Float(string='Duration', required=True, default=1.0)
    duration_unit = fields.Selection([
        ('hour', 'Hour(s)'),
        ('day', 'Day(s)'),
        ('week', 'Week(s)'),
        ('month', 'Month(s)'),
    ], string='Unit', required=True, default='day')
    price = fields.Float(string='Price', required=True, digits='Product Price')
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                   default=lambda self: self.env.company.currency_id)
    active = fields.Boolean(default=True)

    @api.depends('duration', 'duration_unit', 'price')
    def _compute_name(self):
        for record in self:
            unit_label = dict(self._fields['duration_unit'].selection).get(record.duration_unit, '')
            record.name = f"{record.duration} {unit_label} - {record.price}"

    @api.constrains('duration', 'price')
    def _check_positive_values(self):
        for record in self:
            if record.duration <= 0:
                raise ValidationError(_('Duration must be positive'))
            if record.price < 0:
                raise ValidationError(_('Price cannot be negative'))

    @api.constrains('product_tmpl_id', 'duration', 'duration_unit')
    def _check_unique_pricing(self):
        for record in self:
            existing = self.search([
                ('product_tmpl_id', '=', record.product_tmpl_id.id),
                ('duration', '=', record.duration),
                ('duration_unit', '=', record.duration_unit),
                ('id', '!=', record.id)
            ])
            if existing:
                raise ValidationError(_('A pricing rule for this duration already exists'))

    def get_price_per_day(self):
        """Convert pricing to daily rate for comparison"""
        self.ensure_one()
        duration_in_days = self.duration
        if self.duration_unit == 'hour':
            duration_in_days = self.duration / 24.0
        elif self.duration_unit == 'week':
            duration_in_days = self.duration * 7.0
        elif self.duration_unit == 'month':
            duration_in_days = self.duration * 30.0
        
        return self.price / duration_in_days if duration_in_days > 0 else 0.0
