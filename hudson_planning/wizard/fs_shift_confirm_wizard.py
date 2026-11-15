# Part of Hudson Community. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

class FsShiftConfirmWizard(models.TransientModel):
    _name = 'fs.shift.confirm.wizard'
    _description = 'Confirm Shift Generation Warning'

    warning_message = fields.Text(string="Warning Message", readonly=True)
    apply_wizard_id = fields.Many2one('fs.shift.template.apply.wizard', string="Apply Wizard")

    def action_proceed(self):
        self.ensure_one()
        if self.apply_wizard_id:
            # Call the generate method on the original wizard, passing force=True
            return self.apply_wizard_id.with_context(force_generate=True).action_apply()
        return {'type': 'ir.actions.act_window_close'}
