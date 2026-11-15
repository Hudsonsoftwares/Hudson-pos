# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class FieldServiceTimesheet(models.Model):
    _name = 'field.service.timesheet'
    _description = 'Field Service Timesheet'
    _order = 'date desc, id desc'

    order_id = fields.Many2one(
        'field.service.order',
        string='Field Service Order',
        required=True,
        ondelete='cascade',
        index=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Technician',
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
    date = fields.Date(
        string='Date',
        default=fields.Date.context_today,
        required=True,
    )
    description = fields.Char(string='Description')
    duration = fields.Float(string='Duration (Hours)', required=True, default=0.0)

    # Geolocation
    start_latitude = fields.Float(string='Start Latitude', digits=(16, 5))
    start_longitude = fields.Float(string='Start Longitude', digits=(16, 5))
    stop_latitude = fields.Float(string='Stop Latitude', digits=(16, 5))
    stop_longitude = fields.Float(string='Stop Longitude', digits=(16, 5))

    start_time = fields.Datetime(string='Start Time')
    end_time = fields.Datetime(string='End Time')

    @api.depends('user_id')
    def _compute_employee_id(self):
        for record in self:
            record.employee_id = self.env['hr.employee'].search(
                [('user_id', '=', record.user_id.id),
                 ('company_id', '=', record.order_id.company_id.id or self.env.company.id)],
                limit=1,
            )
