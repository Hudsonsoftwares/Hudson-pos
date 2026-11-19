from odoo import models, fields


class HudsonSetAccountWizard(models.TransientModel):
    _name = 'hudson.set.account.wizard'
    _description = 'Set Account Wizard'

    statement_line_id = fields.Many2one('account.bank.statement.line', string='Statement Line')
    account_id = fields.Many2one('account.account', string='Account', required=True)

    def action_apply(self):
        self.ensure_one()
        if self.statement_line_id:
            # books the open amount of the transaction on the account (real journal items, the suspense
            # account is cleared), see `account.bank.statement.line._hudson_set_account`
            self.statement_line_id.hudson_account_id = self.account_id
        return {'type': 'ir.actions.act_window_close'}
