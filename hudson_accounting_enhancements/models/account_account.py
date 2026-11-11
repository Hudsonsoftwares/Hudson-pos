from odoo import models, fields

class AccountAccount(models.Model):
    _inherit = 'account.account'

    hudson_deferred_account_id = fields.Many2one(
        'account.account',
        string="Deferred Counterpart Account",
        help="If set, this account will be used to generate Deferred Revenues or Deferred Expenses for invoice lines that span across multiple dates."
    )
