# -*- coding: utf-8 -*-
from odoo import api, fields, models

class HudsonAttendanceRegularization(models.Model):
    _inherit = 'hudson.attendance.regularization'

    corrected_check_in = fields.Datetime(
        string='Corrected Check-in',
        required=False,
        tracking=True,
    )

    def action_apply(self):
        for reg in self:
            if not reg.corrected_check_in and reg.orig_check_in:
                reg.corrected_check_in = reg.orig_check_in
            if not reg.corrected_check_out and reg.orig_check_out:
                reg.corrected_check_out = reg.orig_check_out
        return super(HudsonAttendanceRegularization, self).action_apply()
