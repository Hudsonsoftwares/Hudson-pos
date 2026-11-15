# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, tools

from ..models.sale_order import RENTAL_STATUS


class RentalReport(models.Model):
    _name = 'rental.report'
    _description = 'Rental Analysis Report'
    _auto = False
    _order = 'date_order desc'

    name = fields.Char(string='Order Reference', readonly=True)
    order_id = fields.Many2one('sale.order', string='Order', readonly=True)
    date_order = fields.Datetime(string='Order Date', readonly=True)
    pickup_date = fields.Datetime(string='Pickup Date', readonly=True)
    return_date = fields.Datetime(string='Return Date', readonly=True)
    state = fields.Selection(RENTAL_STATUS, string='Status', readonly=True)

    partner_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', readonly=True)
    categ_id = fields.Many2one('product.category', string='Product Category', readonly=True)

    quantity = fields.Float(string='Quantity', readonly=True)
    qty_delivered = fields.Float(string='Picked-up', readonly=True)
    qty_returned = fields.Float(string='Returned', readonly=True)
    duration_days = fields.Float(string='Duration (Days)', readonly=True)

    price_total = fields.Float(string='Total', readonly=True)
    amount_untaxed = fields.Float(string='Untaxed Amount', readonly=True)

    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    user_id = fields.Many2one('res.users', string='Salesperson', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    sol.id AS id,
                    so.name AS name,
                    so.id AS order_id,
                    so.date_order AS date_order,
                    so.rental_start_date AS pickup_date,
                    so.rental_end_date AS return_date,
                    so.rental_status AS state,
                    so.partner_id AS partner_id,
                    so.user_id AS user_id,
                    so.company_id AS company_id,
                    sol.product_id AS product_id,
                    pt.id AS product_tmpl_id,
                    pt.categ_id AS categ_id,
                    sol.product_uom_qty AS quantity,
                    sol.qty_delivered AS qty_delivered,
                    sol.qty_returned AS qty_returned,
                    sol.rental_duration AS duration_days,
                    sol.price_total AS price_total,
                    sol.price_subtotal AS amount_untaxed
                FROM sale_order_line sol
                JOIN sale_order so ON so.id = sol.order_id
                JOIN product_product pp ON pp.id = sol.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                WHERE sol.is_rental AND so.state != 'cancel'
            )
        """ % self._table)
