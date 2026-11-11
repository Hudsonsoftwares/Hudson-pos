# pyrefly: ignore [missing-import]
from odoo import models, fields

class AppointmentClosingDay(models.Model):
    _name = 'appointment.closing.day'
    _description = 'Appointment Closing Day'

    closing_type = fields.Selection([
        ('appointments', 'Appointments'),
        ('resources', 'Resources'),
        ('users', 'Users')
    ], string='Closing Type', default='appointments', required=True)
    
    name = fields.Char('Reason', required=True)
    start_datetime = fields.Datetime('Start Date', required=True)
    end_datetime = fields.Datetime('End Date', required=True)
    
    appointment_type_ids = fields.Many2many('appointment.type', string='Appointments')
    resource_id = fields.Many2one('appointment.resource', string='Resource')
    user_id = fields.Many2one('res.users', string='User')

    def action_save(self):
        return {'type': 'ir.actions.act_window_close'}
