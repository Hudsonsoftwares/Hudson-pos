# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class FieldServiceActiveTimer(models.Model):
    _name = 'field.service.active.timer'
    _description = 'Field Service Active Timer'
    _order = 'start_time desc, id desc'

    order_id = fields.Many2one(
        'field.service.order',
        string='Field Service Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='User',
        default=lambda self: self.env.user,
        required=True,
        index=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        compute='_compute_employee_id',
        store=True,
    )
    start_time = fields.Datetime(
        string='Start Time',
        default=fields.Datetime.now,
        required=True,
    )
    current_latitude = fields.Float(string='Latitude', digits=(16, 5))
    current_longitude = fields.Float(string='Longitude', digits=(16, 5))

    @api.depends('user_id')
    def _compute_employee_id(self):
        for record in self:
            record.employee_id = self.env['hr.employee'].search(
                [('user_id', '=', record.user_id.id),
                 ('company_id', '=', record.order_id.company_id.id or self.env.company.id)],
                limit=1,
            )

    order_id_partner_id = fields.Many2one(related='order_id.partner_id', readonly=True)
    order_id_title = fields.Char(related='order_id.title', readonly=True)
    customer_latitude = fields.Float(compute='_compute_customer_location')
    customer_longitude = fields.Float(compute='_compute_customer_location')
    location_radius = fields.Float(compute='_compute_location_radius')

    def _compute_customer_location(self):
        for record in self:
            partner = record.order_id.partner_id
            record.customer_latitude = getattr(partner, 'partner_latitude', 0.0)
            record.customer_longitude = getattr(partner, 'partner_longitude', 0.0)

    def _compute_location_radius(self):
        radius_str = self.env['ir.config_parameter'].sudo().get_param('hudson_field_service.fs_location_radius', '500')
        try:
            radius = float(radius_str)
        except ValueError:
            radius = 100.0
        for record in self:
            record.location_radius = radius

    is_outside_radius = fields.Boolean(compute='_compute_is_outside_radius')

    @api.depends('current_latitude', 'current_longitude')
    def _compute_is_outside_radius(self):
        radius_str = self.env['ir.config_parameter'].sudo().get_param('hudson_field_service.fs_location_radius', '500')
        try:
            radius = float(radius_str)
        except ValueError:
            radius = 100.0

        for record in self:
            record.is_outside_radius = False
            partner = record.order_id.partner_id
            if partner and getattr(partner, 'partner_latitude', False) and getattr(partner, 'partner_longitude', False):
                if record.current_latitude and record.current_longitude:
                    # Using a simple haversine or just a placeholder calculation if _calculate_distance doesn't exist
                    # Since we don't have _calculate_distance on order_id anymore or it was somewhere else, we can use a basic calc:
                    import math
                    lat1, lon1 = math.radians(record.current_latitude), math.radians(record.current_longitude)
                    lat2, lon2 = math.radians(partner.partner_latitude), math.radians(partner.partner_longitude)
                    dlat = lat2 - lat1
                    dlon = lon2 - lon1
                    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
                    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                    dist = 6371000 * c  # distance in meters
                    
                    if dist > radius:
                        record.is_outside_radius = True