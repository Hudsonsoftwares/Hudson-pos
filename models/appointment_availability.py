# pyrefly: ignore [missing-import]
from odoo import models, fields

class AppointmentAvailability(models.Model):
    _name = 'appointment.availability'
    _description = 'Appointment Availability'

    appointment_type_id = fields.Many2one('appointment.type', string='Appointment Type', required=True, ondelete='cascade')
    day_of_week = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], string='Day of Week', required=True)
    
    start_time = fields.Float('Start Time', required=True)
    end_time = fields.Float('End Time', required=True)
