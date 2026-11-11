from odoo import models, fields


class AccountInvoiceReport(models.Model):
    _inherit = 'account.invoice.report'

    price_subtotal = fields.Monetary(
        string='Untaxed Amount',
        readonly=True,
        currency_field='company_currency_id',
        aggregator='sum',
    )
    price_total = fields.Monetary(
        string='Total',
        readonly=True,
        currency_field='company_currency_id',
        aggregator='sum',
    )
    price_margin = fields.Monetary(
        string='Margin',
        readonly=True,
        currency_field='company_currency_id',
        aggregator='sum',
    )
    inventory_value = fields.Monetary(
        string='Inventory Value',
        readonly=True,
        currency_field='company_currency_id',
        aggregator='sum',
    )
