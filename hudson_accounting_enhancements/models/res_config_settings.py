from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hudson_stock_journal_id = fields.Many2one(
        related='company_id.hudson_stock_journal_id', readonly=False,
        string='Inventory Valuation Journal')
    hudson_stock_valuation_account_id = fields.Many2one(
        related='company_id.hudson_stock_valuation_account_id', readonly=False,
        string='Stock Valuation Account')
    hudson_stock_expense_account_id = fields.Many2one(
        related='company_id.hudson_stock_expense_account_id', readonly=False,
        string='Stock Variation Expense Account')
