# -*- coding: utf-8 -*-
# pyrefly: ignore [missing-import]
from odoo import models


class MailActivitySchedule(models.TransientModel):
    _inherit = 'mail.activity.schedule'

    def action_schedule_plan(self):
        """When launched from a pay run's Select Employees dialog, just close the wizard
        instead of reloading / jumping to the Employees list, so the user stays on the pay run."""
        res = super().action_schedule_plan()
        if self.env.context.get('hudson_payrun_launch_plan'):
            return {'type': 'ir.actions.act_window_close'}
        return res
