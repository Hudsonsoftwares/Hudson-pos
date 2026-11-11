from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    hudson_stock_journal_id = fields.Many2one('account.journal', string='Inventory Valuation Journal', check_company=True)
    hudson_stock_valuation_account_id = fields.Many2one('account.account', string='Stock Valuation Account', check_company=True)
    hudson_stock_expense_account_id = fields.Many2one('account.account', string='Stock Variation Expense Account', check_company=True)
