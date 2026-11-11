from odoo import models, fields, api

class HudsonSetAccountWizard(models.TransientModel):
    _name = 'hudson.set.account.wizard'
    _description = 'Set Account Wizard'

    statement_line_id = fields.Many2one('account.bank.statement.line', string='Statement Line')
    account_id = fields.Many2one('account.account', string='Account', required=True)

    def action_apply(self):
        self.ensure_one()
        if self.statement_line_id:
            # Reconcile the line with the given account.
            # In a full implementation, this creates a suspense line and reconciles.
            # For this UI clone, we can just trigger native reconciliation logic if available,
            # or store it in hudson_account_id to simulate it.
            self.statement_line_id.hudson_account_id = self.account_id
        return {'type': 'ir.actions.act_window_close'}
