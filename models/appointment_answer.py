# pyrefly: ignore [missing-import]
from odoo import models, fields

class AppointmentAnswer(models.Model):
    _name = 'appointment.answer'
    _description = 'Appointment Answer'
    _rec_name = 'question_id'

    booking_id = fields.Many2one('appointment.booking', string='Booking', required=True, ondelete='cascade')
    question_id = fields.Many2one('appointment.question', string='Question', required=True)
    question_type = fields.Selection(related='question_id.question_type', string='Type')
    
    value_text = fields.Text('Answer')
    appointment_type_id = fields.Many2one('appointment.type', related='booking_id.appointment_type_id', string='Appointment Type', store=True)
