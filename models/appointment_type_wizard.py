# pyrefly: ignore [missing-import]
from odoo import models

class AppointmentTypeWizard(models.TransientModel):
    _name = 'appointment.type.wizard'
    _description = 'Appointment Type Wizard'

    def action_preset_meeting(self):
        return self.env['appointment.type'].action_preset_meeting()

    def action_preset_video(self):
        return self.env['appointment.type'].action_preset_video()

    def action_preset_table(self):
        return self.env['appointment.type'].action_preset_table()

    def action_preset_resource(self):
        return self.env['appointment.type'].action_preset_resource()
