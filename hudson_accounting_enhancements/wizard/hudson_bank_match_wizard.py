from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HudsonBankMatchWizard(models.TransientModel):
    _name = 'hudson.bank.match.wizard'
    _description = 'Bank Matching Suggestions Wizard'

    statement_line_id = fields.Many2one('account.bank.statement.line', string='Statement Line')
    partner_id = fields.Many2one(related='statement_line_id.partner_id')
    amount = fields.Monetary(related='statement_line_id.amount', currency_field='currency_id')
    currency_id = fields.Many2one(related='statement_line_id.currency_id')

    move_line_ids = fields.Many2many(
        'account.move.line',
        string='Available Matches',
        domain="[('account_id.reconcile', '=', True), ('reconciled', '=', False), ('move_id.state', '=', 'posted')]"
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if res.get('statement_line_id') and 'move_line_ids' in fields_list:
            st_line = self.env['account.bank.statement.line'].browse(res['statement_line_id'])
            # Only what the reconciliation engine suggests is preselected (the items of the partner, or
            # written on the label, of the right amount in the currency of the transaction): "Validate"
            # matches every selected item.
            if not st_line.is_reconciled:
                suggestion = st_line._om_suggested_proposal()
                res['move_line_ids'] = [(6, 0, [match['aml_id'] for match in suggestion.get('matches', [])])]
        return res

    def action_validate(self):
        """ Reconcile the transaction with the selected journal items: the counterparts are written in its
        journal entry instead of the suspense account and reconciled with the selected items. """
        self.ensure_one()
        st_line = self.statement_line_id
        if not st_line:
            raise UserError(_("There is no transaction to match."))
        if not self.move_line_ids:
            raise UserError(_("Select the journal items to match with the transaction."))
        st_line.action_hudson_reconcile_items(self.move_line_ids.ids)
        return {'type': 'ir.actions.act_window_close'}
