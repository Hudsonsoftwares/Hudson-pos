from odoo import models, fields

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    fs_order_id = fields.Many2one(
        'field.service.order',
        string='Field Service Order'
    )
