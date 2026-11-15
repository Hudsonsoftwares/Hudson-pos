# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Rental orders are now sales orders (like Odoo's Rental app). Move the former
    ``rental.order`` records onto sales orders; the old tables are dropped by the upgrade."""
    env = api.Environment(cr, SUPERUSER_ID, {'mail_notrack': True, 'tracking_disable': True})

    # The rental period now lives on the order (website carts only had it on the lines)
    cr.execute("""
        UPDATE sale_order so
           SET rental_start_date = sub.start_date, rental_end_date = sub.end_date
          FROM (SELECT order_id, MIN(rental_start_date) AS start_date, MAX(rental_end_date) AS end_date
                  FROM sale_order_line
                 WHERE rental_start_date IS NOT NULL AND rental_end_date IS NOT NULL
              GROUP BY order_id) sub
         WHERE so.id = sub.order_id AND so.rental_start_date IS NULL
    """)

    cr.execute("SELECT to_regclass('rental_order'), to_regclass('account_tax_rental_order_line_rel')")
    has_rental_orders, has_tax_rel = cr.fetchone()
    if has_rental_orders:
        _migrate_rental_orders(env, bool(has_tax_rel))

    # Line copies of the order's rental period, and the duration they give
    cr.execute("""
        UPDATE sale_order_line sol
           SET rental_start_date = so.rental_start_date,
               rental_end_date = so.rental_end_date,
               rental_duration = COALESCE(EXTRACT(EPOCH FROM so.rental_end_date - so.rental_start_date) / 86400.0, 0)
          FROM sale_order so
         WHERE so.id = sol.order_id
    """)

    orders = env['sale.order'].search([('order_line.is_rental', '=', True)])
    orders._compute_is_rental_order()
    orders._compute_rental_status()
    env.flush_all()


def _migrate_rental_orders(env, has_tax_rel):
    cr = env.cr
    SaleOrder = env['sale.order']
    cr.execute("""
        SELECT id, name, partner_id, pickup_date, return_date, state, sale_order_id,
               user_id, company_id, note, date_order
          FROM rental_order
      ORDER BY id
    """)
    for (rid, rname, partner_id, pickup, ret, state, sale_id, user_id, company_id, note, date_order) in cr.fetchall():
        cr.execute("""
            SELECT id, product_id, name, quantity, product_uom, price_unit
              FROM rental_order_line WHERE order_id = %s ORDER BY sequence, id
        """, [rid])
        rental_lines = cr.fetchall()

        order = SaleOrder.browse(sale_id).exists() if sale_id else SaleOrder
        if order and order.order_line.filtered('is_rental'):
            # Website rentals already have their products on the sales order
            cr.execute("UPDATE sale_order SET rental_start_date = %s, rental_end_date = %s WHERE id = %s",
                       [pickup, ret, order.id])
            order.invalidate_recordset(['rental_start_date', 'rental_end_date'])
        else:
            line_vals = []
            for (line_id, product_id, name, qty, uom_id, price_unit) in rental_lines:
                taxes = []
                if has_tax_rel:
                    cr.execute("SELECT account_tax_id FROM account_tax_rental_order_line_rel"
                               " WHERE rental_order_line_id = %s", [line_id])
                    taxes = [r[0] for r in cr.fetchall()]
                line_vals.append((0, 0, {
                    'product_id': product_id,
                    'name': name,
                    'product_uom_qty': qty,
                    'product_uom_id': uom_id,
                    'price_unit': price_unit,
                    'tax_ids': [(6, 0, taxes)],
                }))
            vals = {
                'rental_start_date': pickup,
                'rental_end_date': ret,
                'note': note,
            }
            if order:
                # Period first, then lines: the lines keep their own price and description
                order.write(vals)
                order.write({'order_line': line_vals})
            else:
                order = SaleOrder.create({
                    **vals,
                    'partner_id': partner_id,
                    'user_id': user_id,
                    'company_id': company_id,
                    'date_order': date_order,
                    'order_line': line_vals,
                })

        if state == 'cancel':
            if order.state != 'cancel':
                order._action_cancel()
        elif state != 'draft' and order.state in ('draft', 'sent'):
            order.action_confirm()

        lines = order.order_line.filtered('is_rental')
        if state == 'picked_up':
            for line in lines:
                line.qty_delivered = line.product_uom_qty
        elif state in ('returned', 'done'):
            for line in lines:
                line.qty_delivered = line.qty_returned = line.product_uom_qty

        cr.execute("SELECT 1 FROM information_schema.columns"
                   " WHERE table_name = 'stock_picking' AND column_name = 'rental_order_id'")
        if cr.fetchone():
            cr.execute("UPDATE stock_picking SET rental_sale_order_id = %s WHERE rental_order_id = %s",
                       [order.id, rid])

        order.message_post(body=env._('Migrated from rental order %s.', rname))
        _logger.info("hudson_rental: rental order %s migrated to sales order %s", rname, order.name)
