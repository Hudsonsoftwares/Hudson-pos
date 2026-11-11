from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    allow_remote_checkin = fields.Boolean(string="Allow Remote Check-In")
