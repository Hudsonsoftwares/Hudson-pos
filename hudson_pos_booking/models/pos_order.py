# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

import base64
import io
import logging
import qrcode
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

class PosOrder(models.Model):
    _inherit = 'pos.order'

    booking_id = fields.Many2one(
        'appointment.booking',
        string='Table Booking',
        readonly=True,
        index='btree_not_null',
        help="The appointment booking associated with this POS order."
    )

    @api.model
    def _get_physically_merged_tables(self, table):
        """Return recordset containing table, its merged parent chain, and all merged descendants."""
        Table = self.env['restaurant.table'].sudo().with_context(active_test=False)
        if not table or not table.exists():
            return Table.browse()
        curr = table
        visited = {curr.id}
        while curr.parent_id and curr.parent_id.id not in visited:
            visited.add(curr.parent_id.id)
            curr = curr.parent_id
        root = curr
        merged = root
        frontier = root
        while frontier:
            children = Table.search([
                ('parent_id', 'in', frontier.ids),
                ('id', 'not in', merged.ids),
            ])
            merged |= children
            frontier = children
        return merged

    @api.model
    def _search_checked_in_bookings_on_tables(self, tables, company_id=None, order_dt=None):
        """Find actively checked_in bookings for the given table recordset (never future confirmed bookings)."""
        Booking = self.env['appointment.booking'].sudo()
        if not tables:
            return Booking.browse()
        base_domain = [('state', '=', 'checked_in')]
        if company_id:
            base_domain.append(('company_id', 'in', (company_id, False)))
        res_ids = tables.mapped('appointment_resource_id').ids
        if res_ids:
            table_domain = ['|', ('table_ids', 'in', tables.ids), ('resource_ids', 'in', res_ids)]
        else:
            table_domain = [('table_ids', 'in', tables.ids)]
        if order_dt:
            dt = fields.Datetime.to_datetime(order_dt)
            matched = Booking.search(
                base_domain + table_domain + [
                    ('start_datetime', '<=', fields.Datetime.add(dt, minutes=30)),
                    ('end_datetime', '>=', dt),
                ],
                order='start_datetime asc, id asc',
            )
            if matched:
                return matched
        return Booking.search(base_domain + table_domain, order='start_datetime desc, id desc')

    @api.model_create_multi
    def create(self, vals_list):
        Booking = self.env['appointment.booking'].sudo()
        for vals in vals_list:
            if vals.get('booking_id'):
                if not Booking.browse(vals['booking_id']).exists():
                    vals['booking_id'] = False
            if not vals.get('booking_id') and vals.get('table_id') and not vals.get('is_refund'):
                table = self.env['restaurant.table'].sudo().browse(vals['table_id'])
                merged_tables = self._get_physically_merged_tables(table)
                order_dt = vals.get('date_order') or fields.Datetime.now()
                company_id = vals.get('company_id')
                if not company_id and vals.get('session_id'):
                    company_id = self.env['pos.session'].sudo().browse(vals['session_id']).company_id.id
                if not company_id and table.exists():
                    company_id = table.company_id.id
                booking = self._search_checked_in_bookings_on_tables(
                    merged_tables,
                    company_id=company_id,
                    order_dt=order_dt,
                )[:1]
                if booking:
                    vals['booking_id'] = booking.id
        orders = super().create(vals_list)
        if not self.env.context.get('skip_booking_floor_notify'):
            for order in orders:
                if order.booking_id:
                    order.booking_id._notify_pos_floor()
        return orders

    def write(self, vals):
        Booking = self.env['appointment.booking'].sudo()
        if vals.get('booking_id'):
            if not Booking.browse(vals['booking_id']).exists():
                vals = dict(vals, booking_id=False)
        res = super().write(vals)
        if vals.get('table_id') and 'booking_id' not in vals:
            for order in self:
                if not order.booking_id and not order.is_refund and order.state == 'draft' and order.table_id:
                    merged_tables = self._get_physically_merged_tables(order.table_id)
                    booking = self._search_checked_in_bookings_on_tables(
                        merged_tables,
                        company_id=order.company_id.id or order.config_id.company_id.id,
                        order_dt=order.date_order,
                    )[:1]
                    if booking:
                        order.with_context(skip_booking_floor_notify=True).write({'booking_id': booking.id})
        if not self.env.context.get('skip_booking_floor_notify'):
            if set(vals.keys()) & {'booking_id', 'table_id', 'state', 'lines', 'amount_total'}:
                for order in self:
                    if order.booking_id:
                        order.booking_id._notify_pos_floor()
        return res

    def _auto_release_table_on_payment(self):
        """Automatically release tables and check out active bookings once POS payment is validated."""
        Booking = self.env['appointment.booking'].sudo()
        PosOrder = self.env['pos.order'].sudo()
        for order in self:
            if order.state not in ('paid', 'done', 'invoiced') or order.is_refund:
                continue
            if not order.booking_id and not (order.table_id and order.config_id.use_booking):
                continue

            merged_tables = (
                self._get_physically_merged_tables(order.table_id)
                if order.table_id
                else self.env['restaurant.table'].browse()
            )

            # Wait if another non-empty draft split order is still open on the same physical table(s)
            if order.session_id and merged_tables:
                other_drafts = PosOrder.search([
                    ('id', '!=', order.id),
                    ('session_id', '=', order.session_id.id),
                    ('table_id', 'in', merged_tables.ids),
                    ('state', '=', 'draft'),
                ])
                non_empty_drafts = other_drafts.filtered(lambda o: bool(o.lines))
                if non_empty_drafts:
                    continue
                empty_drafts = other_drafts - non_empty_drafts
                if empty_drafts:
                    empty_drafts.write({'state': 'cancel'})
                    if order.config_id and order.config_id.current_session_id:
                        order.config_id.notify_synchronisation(
                            order.config_id.current_session_id.id,
                            self.env.context.get('device_identifier', 0),
                        )

            # Also guard if this booking itself has another open draft order with lines
            if order.booking_id:
                other_booking_drafts = PosOrder.search([
                    ('id', '!=', order.id),
                    ('booking_id', '=', order.booking_id.id),
                    ('state', '=', 'draft'),
                ])
                non_empty_b_drafts = other_booking_drafts.filtered(lambda o: bool(o.lines))
                if non_empty_b_drafts:
                    continue
                empty_b_drafts = other_booking_drafts - non_empty_b_drafts
                if empty_b_drafts:
                    empty_b_drafts.write({'state': 'cancel'})

            bookings_to_checkout = Booking.browse()
            if order.booking_id and order.booking_id.state in ('confirmed', 'checked_in'):
                bookings_to_checkout |= order.booking_id

            if merged_tables and (order.config_id.use_booking or order.booking_id):
                checked_in = self._search_checked_in_bookings_on_tables(
                    merged_tables,
                    company_id=order.company_id.id or order.config_id.company_id.id,
                )
                if not order.booking_id and checked_in:
                    order.sudo().with_context(skip_booking_floor_notify=True).write({
                        'booking_id': checked_in[0].id,
                    })
                bookings_to_checkout |= checked_in

            bookings_to_checkout = bookings_to_checkout.filtered(
                lambda b: b.state in ('confirmed', 'checked_in')
            )
            if bookings_to_checkout:
                bookings_to_checkout.action_check_out()

    def action_pos_order_paid(self):
        res = super().action_pos_order_paid()
        if not self.env.context.get('skip_booking_auto_release'):
            self._auto_release_table_on_payment()
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

    def _get_survey_qr_code(self):
        """Generate base64 data URI PNG QR code for the company's configured survey URL."""
        self.ensure_one()
        company = self.company_id or self.env.company
        if not getattr(company, 'show_survey_qr', False) or not getattr(company, 'survey_url', False):
            return False
        url = (company.survey_url or '').strip()
        if not url:
            return False
        try:
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=1,
            )
            qr.add_data(url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            qr_b64 = base64.b64encode(buffer.getvalue()).decode()
            return f"data:image/png;base64,{qr_b64}"
        except Exception as e:
            _logger.warning("Failed to generate survey QR code for POS order %s: %s", self.name or self.id, e)
            return False

    def order_receipt_generate_data(self, basic_receipt=False):
        data = super().order_receipt_generate_data(basic_receipt=basic_receipt)
        data.setdefault('conditions', {})['show_survey_qr'] = False
        data.setdefault('image', {})['survey_qr_code'] = False
        data.setdefault('extra_data', {})['survey_message'] = ""
        data.setdefault('extra_data', {})['survey_qr_size'] = 32

        company = self.company_id or self.env.company
        if getattr(company, 'show_survey_qr', False) and getattr(company, 'survey_url', False):
            qr_code = self._get_survey_qr_code()
            if qr_code:
                data['image']['survey_qr_code'] = qr_code
                data['conditions']['show_survey_qr'] = True
                data['extra_data']['survey_message'] = company.survey_message or "Thank you for coming! Scan the QR code below to fill the survey and share your suggestions."
                data['extra_data']['survey_qr_size'] = company.survey_qr_size or 32
        return data


