# pyrefly: ignore [missing-import]
from odoo import models, fields

class AppointmentReminder(models.Model):
    _name = 'appointment.reminder'
    _description = 'Appointment Reminder'

    name = fields.Char('Name', required=True)
    # Replaced by Many2many from appointment.type
    
    reminder_type = fields.Selection([
        ('email', 'Email'),
        ('sms', 'SMS'),
    ], string='Reminder Type', required=True, default='email')
    
    reminder_time = fields.Float('Reminder Time', required=True, help="Hours before the appointment to send the reminder")
