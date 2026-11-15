# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    rental_sale_order_id = fields.Many2one('sale.order', string='Rental Order', readonly=True, index='btree_not_null')
    is_rental = fields.Boolean(string='Is Rental', compute='_compute_is_rental', store=True)

    @api.depends('rental_sale_order_id')
    def _compute_is_rental(self):
        for picking in self:
            picking.is_rental = bool(picking.rental_sale_order_id)

    def action_view_rental_order(self):
        self.ensure_one()
        return {
            'name': 'Rental Order',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': self.rental_sale_order_id.id,
        }
