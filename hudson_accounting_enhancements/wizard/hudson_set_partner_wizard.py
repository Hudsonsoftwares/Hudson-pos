from odoo import models, fields, api

class HudsonSetPartnerWizard(models.TransientModel):
    _name = 'hudson.set.partner.wizard'
    _description = 'Set Partner Wizard'

    statement_line_id = fields.Many2one('account.bank.statement.line', string='Statement Line')
    partner_id = fields.Many2one('res.partner', string='Partner', required=True)

    def action_apply(self):
        self.ensure_one()
        if self.statement_line_id:
            self.statement_line_id.partner_id = self.partner_id
        return {'type': 'ir.actions.act_window_close'}
