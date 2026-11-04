# -*- coding: utf-8 -*-

from odoo import models, fields, api

class PosDeliveryPlatform(models.Model):
    _name = 'pos.delivery.platform'
    _description = 'Food Delivery Platform'
    _order = 'sequence, name'

    name = fields.Char(string='Platform Name', required=True)
    code = fields.Char(string='Platform Code', help='Identifier like swiggy, zomato, talabat, ubereats, radyes, careem, noon')
    urbanpiper_channel_code = fields.Char(string='UrbanPiper Channel Code', help='Exact channel identifier used in UrbanPiper payload')
    country_ids = fields.Many2many(
        'res.country',
        'pos_delivery_platform_country_rel',
        'platform_id',
        'country_id',
        string='Operating Countries',
        help='Countries where this delivery platform operates (leave empty for all countries)'
    )
    delivery_type = fields.Selection([
        ('urbanpiper', 'UrbanPiper Aggregator'),
        ('direct', 'Direct Webhook / Custom'),
    ], string='Integration Type', default='urbanpiper')
    active = fields.Boolean(string='Active', default=True)
    sequence = fields.Integer(string='Sequence', default=10)
    color = fields.Integer(string='Color Index', default=0)
    auto_accept = fields.Boolean(
        string='Auto-Accept Orders',
        default=False,
        help='Automatically mark incoming orders from this platform as accepted.'
    )

    @api.model
    def get_platforms_for_country(self, country_id=False):
        """Retrieve active delivery platforms available for a given country."""
        domain = [('active', '=', True)]
        if country_id:
            domain.append('|')
            domain.append(('country_ids', '=', False))
            domain.append(('country_ids', 'in', country_id))
        return self.search(domain)
