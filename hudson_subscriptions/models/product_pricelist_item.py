# -*- coding: utf-8 -*-
from odoo import fields, models

class ProductPricelistItem(models.Model):
    _inherit = 'product.pricelist.item'

    subscription_plan_id = fields.Many2one('sale.subscription.plan', string='Plan')
    packaging_id = fields.Many2one('uom.uom', string='Packaging')
