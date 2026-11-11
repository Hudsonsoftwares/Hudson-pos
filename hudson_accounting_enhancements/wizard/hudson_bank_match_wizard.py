from odoo import models, fields, api

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
        if 'statement_line_id' in res:
            st_line = self.env['account.bank.statement.line'].browse(res['statement_line_id'])
            
            domain = [
                ('account_id.reconcile', '=', True),
                ('reconciled', '=', False),
                ('move_id.state', '=', 'posted'),
                ('company_id', '=', st_line.company_id.id)
            ]
            move_lines = self.env['account.move.line'].search(domain)
            
            # Sort logic: 
            # 1. Partner matches (+10)
            # 2. Amount matches (+5)
            def get_score(ml):
                score = 0
                if st_line.partner_id and ml.partner_id == st_line.partner_id:
                    score += 10
                if abs(ml.amount_residual) == abs(st_line.amount):
                    score += 5
                return score
            
            # Sort by score descending, then by date descending
            sorted_lines = sorted(move_lines, key=lambda ml: (get_score(ml), ml.date), reverse=True)
            res['move_line_ids'] = [(6, 0, [ml.id for ml in sorted_lines])]
            
        return res

    def action_validate(self):
        self.ensure_one()
        # In a real implementation, this would reconcile the selected move_lines with the statement line.
        # For this UI clone, we simulate success and return.
        self.statement_line_id.is_reconciled = True
        return {'type': 'ir.actions.act_window_close'}
