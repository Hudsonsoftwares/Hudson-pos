# pyrefly: ignore [missing-import]
from odoo import models, fields, api

class AppointmentResource(models.Model):
    _name = 'appointment.resource'
    _description = 'Appointment Resource'
    _inherit = ['image.mixin']
    
    name = fields.Char('Resource Name', required=True)
    active = fields.Boolean(default=True)
    capacity = fields.Integer('Capacity', default=1)
    
    shareable = fields.Boolean('Shareable', help="Can be shared with other appointments")
    linked_resource_id = fields.Many2one('appointment.resource', string="Linked Resource", help="Does not combine")
    timezone = fields.Selection('_tz_get', string='Timezone', default=lambda self: self.env.user.tz or 'UTC')
    description = fields.Html('Description')
    opening_hours_id = fields.Many2one('resource.calendar', string='Opening Hours', 
                                       default=lambda self: self.env.company.resource_calendar_id)
    
    appointment_type_ids = fields.Many2many('appointment.type', string='Appointment Types')

    @api.model
    def _tz_get(self):
        import pytz
        return [(x, x) for x in pytz.all_timezones]

    @api.depends('name', 'capacity')
    def _compute_display_name(self):
        for resource in self:
            name = resource.name or ''
            if name and resource.capacity:
                if 'table' in name.lower():
                    resource.display_name = f"{name} (🪑 {resource.capacity})"
                else:
                    resource.display_name = f"{name} ({resource.capacity})"
            else:
                resource.display_name = name
