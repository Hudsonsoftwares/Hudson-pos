# -*- coding: utf-8 -*-
from odoo import fields, models

class HudsonAttendanceAnomaly(models.Model):
    _inherit = 'hudson.attendance.anomaly'

    anomaly_type = fields.Selection(selection_add=[
        ('hours_shortfall', 'Hours Shortfall')
    ], ondelete={'hours_shortfall': 'cascade'})
