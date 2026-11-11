from odoo import models, fields

class AccountMultiLedger(models.Model):
    _name = "account.multi.ledger"
    _description = "Multi Ledger Configuration"
    _order = "name"
    _check_company_auto = True

    name = fields.Char(string="Ledger Name", required=True)
    journal_ids = fields.Many2many(
        'account.journal', 
        string="Included Journals", 
        check_company=True,
        help="Journals that are included in this ledger. When this ledger is selected in reports, only entries from these journals will be considered."
    )
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
