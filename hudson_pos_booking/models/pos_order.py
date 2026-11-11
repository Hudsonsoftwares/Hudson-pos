# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models

class PosOrder(models.Model):
    _inherit = 'pos.order'

    booking_id = fields.Many2one(
        'appointment.booking',
        string='Table Booking',
        readonly=True,
        index='btree_not_null',
        help="The appointment booking associated with this POS order."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('booking_id') and vals.get('table_id'):
                order_dt = vals.get('date_order') or fields.Datetime.now()
                # Only link to an actively checked-in booking on this table whose time window contains order_dt
                booking = self.env['appointment.booking'].search([
                    ('table_ids', 'in', [vals['table_id']]),
                    ('state', '=', 'checked_in'),
                    ('start_datetime', '<=', fields.Datetime.add(fields.Datetime.to_datetime(order_dt), minutes=30)),
                    ('end_datetime', '>=', fields.Datetime.to_datetime(order_dt)),
                ], order='start_datetime asc', limit=1)
                if booking:
                    vals['booking_id'] = booking.id
        orders = super().create(vals_list)
        for order in orders:
            if order.booking_id:
                order.booking_id._notify_pos_floor()
        return orders

    def write(self, vals):
        res = super().write(vals)
        for order in self:
            if order.booking_id:
                order.booking_id._notify_pos_floor()
        return res

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()
        for order in self:
            if order.booking_id:
                booking = order.booking_id
                prepaid_str = ""
                if booking.sale_order_id and (booking.prepaid_food_total or booking.food_order_total):
                    prepaid_amount = booking.prepaid_food_total or booking.food_order_total
                    prepaid_str = f" [Pre-ordered dishes pre-paid online via {booking.sale_order_id.name}: {prepaid_amount:.2f}]"
                ref_suffix = f"Booking #{booking.id}{prepaid_str}"
                if vals.get('ref'):
                    vals['ref'] += f" - {ref_suffix}"
                else:
                    vals['ref'] = ref_suffix
                note_line = f"Table Reservation #{booking.id}: {booking.partner_id.name or booking.customer_name}.{prepaid_str}"
                if vals.get('narration'):
                    vals['narration'] += f"\n{note_line}"
                else:
                    vals['narration'] = note_line
        return vals

