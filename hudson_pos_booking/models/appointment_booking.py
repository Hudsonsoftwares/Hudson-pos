# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from datetime import datetime, timedelta
import pytz
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class AppointmentBooking(models.Model):
    _name = 'appointment.booking'
    _inherit = ['appointment.booking', 'pos.load.mixin']

    state = fields.Selection(
        selection_add=[('checked_out', 'Completed')],
        ondelete={'checked_out': 'set default'}
    )

    def action_check_out(self):
        now = fields.Datetime.now()
        for booking in self:
            vals = {'state': 'checked_out'}
            if booking.start_datetime:
                if booking.start_datetime >= now:
                    # If checking out early before the scheduled start time,
                    # end time must strictly be later than start time to satisfy date integrity.
                    vals['end_datetime'] = booking.start_datetime + timedelta(minutes=1)
                elif booking.end_datetime and booking.end_datetime > now:
                    vals['end_datetime'] = now
            else:
                vals['end_datetime'] = now
            booking.write(vals)

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        compute='_compute_company_id',
        store=True,
        readonly=False,
        default=lambda self: self.env.company,
        index=True,
    )
    partner_id = fields.Many2one(
        'res.partner',
        check_company=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string="Sales Order",
        check_company=True,
    )
    pos_config_id = fields.Many2one(
        'pos.config',
        string='POS Point of Sale',
        ondelete='set null',
        check_company=True,
        help="POS outlet where this booking was created or served."
    )
    pos_order_ids = fields.One2many(
        'pos.order',
        'booking_id',
        string='POS Orders',
        readonly=True,
        help="Orders placed at the table associated with this booking."
    )
    table_ids = fields.Many2many(
        'restaurant.table',
        string='Restaurant Tables',
        compute='_compute_table_ids',
        store=True,
        check_company=True,
        help="Tables corresponding to the assigned appointment resources."
    )
    table_names = fields.Char(
        string='Reserved Tables',
        compute='_compute_table_names',
    )
    customer_name = fields.Char(
        string='Customer Name',
        compute='_compute_guest_contact_info',
        store=True,
        readonly=False,
        help="Name of the guest who placed the table reservation."
    )
    customer_phone = fields.Char(
        string='Customer Phone',
        compute='_compute_guest_contact_info',
        store=True,
        readonly=False,
    )
    customer_email = fields.Char(
        string='Customer Email',
        compute='_compute_guest_contact_info',
        store=True,
        readonly=False,
    )

    @api.depends('partner_id', 'partner_id.name', 'partner_id.phone', 'partner_id.email')
    def _compute_guest_contact_info(self):
        for b in self:
            if not b.customer_name and b.partner_id:
                if b.partner_id.id != 1 and not b.partner_id.is_company and b.partner_id.name != b.company_id.name:
                    b.customer_name = b.partner_id.name
            if not b.customer_phone and b.partner_id:
                b.customer_phone = b.partner_id.phone or (getattr(b.partner_id, 'mobile', '') if hasattr(b.partner_id, 'mobile') else '')
            if not b.customer_email and b.partner_id:
                b.customer_email = b.partner_id.email

    @api.depends('appointment_type_id.company_id', 'pos_config_id.company_id', 'table_ids.company_id')
    def _compute_company_id(self):
        for b in self:
            if not b.company_id:
                b.company_id = (
                    b.appointment_type_id.company_id
                    or b.pos_config_id.company_id
                    or (b.table_ids and b.table_ids[0].company_id)
                    or self.env.company
                )

    @api.depends('table_ids', 'table_ids.floor_id', 'table_ids.table_number')
    def _compute_table_names(self):
        for b in self:
            if b.table_ids:
                b.table_names = ', '.join(b.table_ids.mapped('display_name'))
            else:
                b.table_names = ''
    allowed_resource_ids = fields.Many2many(
        'appointment.resource',
        compute='_compute_allowed_resource_ids',
        help="Resources allowed for this booking based on appointment type and website booking toggle."
    )
    resource_ids = fields.Many2many(
        domain="[('id', 'in', allowed_resource_ids)]"
    )
    has_food_order = fields.Boolean(
        string='Has Pre-ordered Food',
        compute='_compute_food_order_info',
        help="Indicates if food items have been pre-ordered or ordered for this table booking."
    )
    food_order_total = fields.Float(
        string='Food Order Total',
        compute='_compute_food_order_info',
        help="Total amount of pre-ordered food for this booking."
    )
    prepaid_food_total = fields.Float(
        string='Prepaid Food Total',
        compute='_compute_food_order_info',
        help="Total amount prepaid for food before the booking."
    )
    prepaid_credit_consumed = fields.Float(
        string='Prepaid Credit Consumed',
        compute='_compute_food_order_info',
        help="Amount of prepaid credit consumed by paid POS orders."
    )
    prepaid_credit_remaining = fields.Float(
        string='Prepaid Credit Remaining',
        compute='_compute_food_order_info',
        help="Remaining prepaid credit available for POS orders."
    )
    total_spent = fields.Float(
        string='Total Spent',
        compute='_compute_food_order_info',
        help="Combined total spent on pre-order and in-restaurant POS orders."
    )
    food_order_summary = fields.Char(
        string='Food Order Summary',
        compute='_compute_food_order_info',
        help="Summary of dishes ordered, e.g. 2x Cappuccino, 1x Croissant."
    )
    food_order_details = fields.Json(
        string='Food Order Details',
        compute='_compute_food_order_info',
        help="Structured JSON list of items pre-ordered online."
    )
    preorder_line_ids = fields.One2many(
        'appointment.booking.preorder.line',
        'booking_id',
        string='Pre-Order Food Lines'
    )

    @api.depends(
        'sale_order_id',
        'sale_order_id.amount_total',
        'sale_order_id.order_line',
        'sale_order_id.order_line.product_uom_qty',
        'sale_order_id.order_line.price_total',
        'sale_order_id.order_line.product_id',
        'pos_order_ids',
        'pos_order_ids.lines',
        'pos_order_ids.lines.qty',
        'pos_order_ids.lines.price_subtotal_incl',
        'pos_order_ids.lines.product_id',
        'pos_order_ids.amount_total',
        'pos_order_ids.state',
        'pos_order_ids.payment_ids',
        'pos_order_ids.payment_ids.amount',
        'preorder_line_ids',
        'preorder_line_ids.qty',
        'preorder_line_ids.subtotal',
        'preorder_line_ids.product_id',
        'preorder_line_ids.price_unit',
    )
    def _compute_food_order_info(self):
        for booking in self:
            items = []
            preorder_total = 0.0

            # 1. Authoritative: Pre-order lines directly on booking
            if booking.preorder_line_ids:
                for pre in booking.preorder_line_ids:
                    unit_price = pre.price_unit or (pre.product_id.lst_price or 0.0)
                    line_subtotal = pre.subtotal or (unit_price * (pre.qty or 1.0))
                    preorder_total += line_subtotal
                    disp_name = pre.product_id.display_name
                    if pre.combo_details:
                        disp_name = f"{disp_name} ({pre.combo_details})"
                    items.append({
                        'product_id': pre.product_id.id,
                        'name': disp_name,
                        'qty': pre.qty or 1.0,
                        'price_unit': unit_price,
                        'subtotal': line_subtotal,
                    })
            # 2. Or Sale Order if no direct preorder_line_ids
            elif booking.sale_order_id:
                so = booking.sale_order_id
                preorder_total += so.amount_total
                for line in so.order_line.filtered(lambda l: not l.display_type and l.product_uom_qty > 0):
                    items.append({
                        'product_id': line.product_id.id,
                        'name': line.product_id.display_name or line.name,
                        'qty': line.product_uom_qty,
                        'price_unit': line.price_unit,
                        'subtotal': line.price_total,
                    })

            # 3. Calculate credit consumed by paid POS orders for this booking
            credit_consumed = 0.0
            pos_spent = 0.0
            if booking.pos_order_ids:
                paid_pos = booking.pos_order_ids.filtered(lambda o: o.state in ('paid', 'done', 'invoiced'))
                for o in paid_pos:
                    pos_spent += o.amount_total
                    for p in o.payment_ids:
                        pm_name = (p.payment_method_id.name or '').lower()
                        if 'card' in pm_name or 'online' in pm_name or 'bank' in pm_name or 'customer account' in pm_name:
                            credit_consumed += p.amount

            prepaid_total = round(preorder_total, 2)
            consumed = round(min(credit_consumed, prepaid_total), 2)
            remaining_credit = max(0.0, round(prepaid_total - consumed, 2))

            booking.has_food_order = bool(items)
            booking.food_order_total = prepaid_total
            booking.prepaid_food_total = prepaid_total
            booking.prepaid_credit_consumed = consumed
            booking.prepaid_credit_remaining = remaining_credit
            booking.total_spent = round(preorder_total + pos_spent, 2)
            booking.food_order_details = items

            if items:
                summary_parts = [
                    f"{int(it['qty']) if float(it['qty']).is_integer() else it['qty']}x {it['name']}"
                    for it in items[:3]
                ]
                if len(items) > 3:
                    summary_parts.append(f"+{len(items) - 3} more")
                booking.food_order_summary = ", ".join(summary_parts)
            else:
                booking.food_order_summary = ""

    @api.depends('appointment_type_id', 'company_id')
    def _compute_allowed_resource_ids(self):
        Table = self.env['restaurant.table'].sudo()
        for booking in self:
            if booking.appointment_type_id:
                booking.allowed_resource_ids = booking.appointment_type_id.resource_ids
            else:
                company = (booking.company_id if hasattr(booking, 'company_id') and booking.company_id else False) or self.env.company
                domain = [
                    ('allow_website_booking', '=', True),
                    ('active', '=', True),
                    ('appointment_resource_id', '!=', False)
                ]
                tables = Table.search(domain + [
                    '|', ('company_id', '=', False), ('company_id', '=', company.id)
                ])
                booking.allowed_resource_ids = tables.mapped('appointment_resource_id')

    @api.depends('resource_ids')
    def _compute_table_ids(self):
        for booking in self:
            if booking.resource_ids:
                tables = self.env['restaurant.table'].search([
                    ('appointment_resource_id', 'in', booking.resource_ids.ids)
                ])
                booking.table_ids = [(6, 0, tables.ids)]
            else:
                booking.table_ids = [(5, 0, 0)]

    @api.constrains('resource_ids', 'start_datetime', 'end_datetime', 'state')
    def _check_no_double_booking(self):
        """
        Strictly prevent overlapping/double bookings for the same table
        or any table merged or linked to it.
        """
        for booking in self:
            if booking.state not in ('confirmed', 'checked_in'):
                continue
            if not booking.start_datetime or not booking.end_datetime:
                continue

            # Identify tables associated with this booking
            tables = booking.table_ids
            if not tables and booking.resource_ids:
                tables = self.env['restaurant.table'].sudo().search([
                    ('appointment_resource_id', 'in', booking.resource_ids.ids)
                ])

            comp_domain = [('company_id', 'in', [booking.company_id.id, False])] if booking.company_id else []
            if not tables:
                # If only resources with no restaurant.table linked, check resources directly
                conflicting = self.search(comp_domain + [
                    ('id', '!=', booking.id),
                    ('state', 'in', ('confirmed', 'checked_in')),
                    ('resource_ids', 'in', booking.resource_ids.ids),
                    ('start_datetime', '<', booking.end_datetime),
                    ('end_datetime', '>', booking.start_datetime),
                ], limit=1)
                if conflicting:
                    raise ValidationError(_(
                        "Double Booking Conflict! Resource is already booked from %s to %s."
                    ) % (fields.Datetime.to_string(conflicting[0].start_datetime),
                         fields.Datetime.to_string(conflicting[0].end_datetime)))
                continue

            # Expand to all merged or linked tables
            all_blocked_tables = tables.get_merged_and_linked_tables()
            all_blocked_resources = all_blocked_tables.mapped('appointment_resource_id') | booking.resource_ids

            if all_blocked_resources:
                # Row lock resources in deterministic sorted order to prevent race conditions and deadlocks
                self.env.cr.execute(
                    "SELECT id FROM appointment_resource WHERE id IN %s ORDER BY id FOR UPDATE",
                    [tuple(sorted(all_blocked_resources.ids))]
                )

            conflicting = self.search(comp_domain + [
                ('id', '!=', booking.id),
                ('state', 'in', ('confirmed', 'checked_in')),
                ('resource_ids', 'in', all_blocked_resources.ids),
                ('start_datetime', '<', booking.end_datetime),
                ('end_datetime', '>', booking.start_datetime),
            ], limit=1)

            if conflicting:
                conflict = conflicting[0]
                conflict_table_names = ', '.join((conflict.table_ids or all_blocked_tables.filtered(
                    lambda t: t.appointment_resource_id in conflict.resource_ids
                )).mapped('display_name')) or _("the selected table")
                start_str = fields.Datetime.to_string(conflict.start_datetime)
                end_str = fields.Datetime.to_string(conflict.end_datetime)
                raise ValidationError(_(
                    "Double Booking Conflict! Table %s (or a table merged/linked to it) is already booked "
                    "from %s to %s for %s. Please select a different table or time slot."
                ) % (conflict_table_names, start_str, end_str, conflict.partner_id.name or _("another guest")))

    @api.model
    def load_pos_data_force_loading(self):
        """Always force fresh loading of bookings on POS startup to reflect latest reservation changes."""
        return True

    @api.model
    def _load_pos_data_domain(self, data):
        config = data.get('pos.config')
        if not config or not config.use_booking:
            return [('id', '=', False)]

        resources = config._get_table_appointment_resources()
        tables = config.floor_ids.table_ids

        today = fields.Date.today()
        # Active POS window: today 00:00 to tomorrow 23:59:59 (avoids 44-day N+1 overhead and preserves PII privacy)
        start_dt = datetime.combine(today, datetime.min.time())
        end_dt = datetime.combine(today + timedelta(days=1), datetime.max.time())

        table_cond = []
        if resources:
            table_cond.append(('resource_ids', 'in', resources.ids))
        if tables:
            table_cond.append(('table_ids', 'in', tables.ids))

        if not table_cond:
            return [('id', '=', False)]

        base_domain = [
            ('company_id', 'in', [config.company_id.id, False]),
            ('start_datetime', '<=', end_dt),
            ('end_datetime', '>=', start_dt),
            ('state', '!=', 'cancelled'),
        ]

        if len(table_cond) == 2:
            return ['|'] + table_cond + base_domain
        return table_cond + base_domain

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            'name',
            'company_id',
            'customer_name',
            'customer_phone',
            'customer_email',
            'partner_id',
            'party_size',
            'start_datetime',
            'end_datetime',
            'duration',
            'state',
            'resource_ids',
            'table_ids',
            'pos_config_id',
            'guest_details',
            'write_date',
            'has_food_order',
            'food_order_total',
            'prepaid_food_total',
            'prepaid_credit_remaining',
            'total_spent',
            'food_order_summary',
            'food_order_details',
            'pos_order_ids',
            'sale_order_id',
        ]

    def _get_pos_booking_data(self, config=None):
        """Format booking record into a dictionary suited for the POS OWL frontend."""
        self.ensure_one()
        tz_name = (config and config.company_id.partner_id.tz) or self.env.user.tz or 'UTC'
        tz = pytz.timezone(tz_name)

        start_local = self.start_datetime.replace(tzinfo=pytz.UTC).astimezone(tz)
        end_local = self.end_datetime.replace(tzinfo=pytz.UTC).astimezone(tz)

        disp_name = (
            self.customer_name
            or (self.partner_id.name if self.partner_id and self.partner_id.id != 1 and not self.partner_id.is_company and self.partner_id.name != self.company_id.name else '')
            or self.name
            or _("Walk-in Guest")
        )
        disp_phone = self.customer_phone or (self.partner_id.phone or (getattr(self.partner_id, 'mobile', '') if hasattr(self.partner_id, 'mobile') else '')) or ''
        disp_email = self.customer_email or (self.partner_id.email or '')

        return {
            'id': self.id,
            'name': self.name or '',
            'company_id': self.company_id.id if self.company_id else False,
            'customer_name': disp_name,
            'customer_phone': disp_phone,
            'customer_email': disp_email,
            'partner_id': self.partner_id.id if self.partner_id else False,
            'party_size': self.party_size,
            'duration': self.duration or 1.5,
            'start_datetime': fields.Datetime.to_string(self.start_datetime),
            'end_datetime': fields.Datetime.to_string(self.end_datetime),
            'start_time_str': start_local.strftime('%H:%M'),
            'end_time_str': end_local.strftime('%H:%M'),
            'start_date_str': start_local.strftime('%Y-%m-%d'),
            'state': self.state,
            'table_ids': self.table_ids.ids,
            'table_names': ', '.join(self.table_ids.mapped('display_name')),
            'notes': self.guest_details or '',
            'pos_order_ids': self.pos_order_ids.ids,
            'sale_order_id': self.sale_order_id.id if self.sale_order_id else False,
            'has_food_order': self.has_food_order,
            'food_order_total': self.food_order_total,
            'prepaid_food_total': self.prepaid_food_total,
            'prepaid_credit_remaining': self.prepaid_credit_remaining,
            'total_spent': self.total_spent,
            'food_order_summary': self.food_order_summary or '',
            'food_order_details': self.food_order_details or [],
        }

    @api.model_create_multi
    def create(self, vals_list):
        bookings = super().create(vals_list)
        for booking in bookings:
            booking._notify_pos_floor()
        return bookings

    def write(self, vals):
        res = super().write(vals)
        floor_trigger_fields = {
            'state', 'table_ids', 'resource_ids', 'start_datetime', 'end_datetime',
            'party_size', 'customer_name', 'customer_phone', 'customer_email',
            'guest_details', 'pos_order_ids', 'sale_order_id'
        }
        if set(vals.keys()) & floor_trigger_fields:
            for booking in self:
                booking._notify_pos_floor()
        return res

    def _notify_pos_floor(self):
        """Notify POS configs whose floor tables match this booking."""
        for booking in self:
            if not booking.table_ids:
                continue
            configs = self.env['pos.config'].search([
                ('use_booking', '=', True),
                ('floor_ids.table_ids', 'in', booking.table_ids.ids),
            ])
            for config in configs:
                config.notify_booking_update(booking, action="UPDATE")

    @api.model
    def _cron_mark_no_show(self):
        """
        Scheduled action: Automatically mark confirmed bookings as no-show
        if past end_datetime + grace period.
        Never marks checked-in or cancelled bookings.
        """
        now = fields.Datetime.now()
        configs = self.env['pos.config'].search([('use_booking', '=', True)])
        default_grace = 15

        for config in configs:
            grace = config.booking_no_show_grace_minutes or default_grace
            cutoff = now - timedelta(minutes=grace)
            resources = config._get_table_appointment_resources()
            if not resources:
                continue

            overdue_bookings = self.search([
                ('state', '=', 'confirmed'),
                ('end_datetime', '<', cutoff),
                ('resource_ids', 'in', resources.ids),
                ('pos_order_ids', '=', False),
            ])
            for booking in overdue_bookings:
                booking.action_no_show()
                config.notify_booking_update(booking, action="NO_SHOW")


class AppointmentBookingPreorderLine(models.Model):
    _name = 'appointment.booking.preorder.line'
    _description = 'Booking Food Pre-Order Line'

    booking_id = fields.Many2one('appointment.booking', string='Booking', ondelete='cascade', required=True)
    company_id = fields.Many2one('res.company', related='booking_id.company_id', store=True, index=True, readonly=True)
    product_id = fields.Many2one('product.product', string='Dish / Product', required=True, check_company=True)
    qty = fields.Float(string='Quantity', default=1.0)
    price_unit = fields.Float(string='Unit Price')
    subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal', store=True)
    combo_details = fields.Char(string='Combo Selections')
    note = fields.Char(string='Special Instructions')

    @api.depends('qty', 'price_unit', 'product_id')
    def _compute_subtotal(self):
        for line in self:
            price = line.price_unit or (line.product_id.lst_price if line.product_id else 0.0)
            line.subtotal = round(line.qty * price, 2)


