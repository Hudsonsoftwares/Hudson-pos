# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    booking_id = fields.Many2one(
        'appointment.booking',
        string="Linked Table Booking",
        compute='_compute_booking_id',
        store=True,
        check_company=True,
    )

    @api.depends('invoice_line_ids.sale_line_ids.order_id', 'pos_order_ids.booking_id', 'company_id')
    def _compute_booking_id(self):
        for move in self:
            booking = False
            so_ids = move.invoice_line_ids.sale_line_ids.order_id.ids
            if so_ids:
                booking = self.env['appointment.booking'].search([
                    ('sale_order_id', 'in', so_ids),
                    ('company_id', 'in', [move.company_id.id, False]),
                ], limit=1)
            if not booking and hasattr(move, 'pos_order_ids') and move.pos_order_ids:
                pos_booking = move.pos_order_ids.filtered('booking_id').mapped('booking_id')
                if pos_booking:
                    booking = pos_booking[0]
            move.booking_id = booking

