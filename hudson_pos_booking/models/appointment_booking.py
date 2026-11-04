# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from datetime import datetime, timedelta
import pytz
from odoo import api, fields, models, _

class AppointmentBooking(models.Model):
    _name = 'appointment.booking'
    _inherit = ['appointment.booking', 'pos.load.mixin']

    pos_config_id = fields.Many2one(
        'pos.config',
        string='POS Point of Sale',
        ondelete='set null',
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
        help="Tables corresponding to the assigned appointment resources."
    )

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
        if not resources:
            return [('id', '=', False)]

        today = fields.Date.today()
        tomorrow = today + timedelta(days=1)
        start_dt = datetime.combine(today, datetime.min.time())
        end_dt = datetime.combine(tomorrow, datetime.max.time())

        return [
            ('resource_ids', 'in', resources.ids),
            ('start_datetime', '<=', end_dt),
            ('end_datetime', '>=', start_dt),
            ('state', '!=', 'cancelled'),
        ]

    @api.model
    def _load_pos_data_fields(self, config):
        return [
            'name',
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
        ]

    def _get_pos_booking_data(self, config=None):
        """Format booking record into a dictionary suited for the POS OWL frontend."""
        self.ensure_one()
        tz_name = (config and config.company_id.partner_id.tz) or self.env.user.tz or 'UTC'
        tz = pytz.timezone(tz_name)

        start_local = self.start_datetime.replace(tzinfo=pytz.UTC).astimezone(tz)
        end_local = self.end_datetime.replace(tzinfo=pytz.UTC).astimezone(tz)

        return {
            'id': self.id,
            'name': self.name or '',
            'customer_name': self.partner_id.name if self.partner_id else _("Walk-in Guest"),
            'customer_phone': self.partner_id.phone or (getattr(self.partner_id, 'mobile', '') if hasattr(self.partner_id, 'mobile') else '') or '',
            'customer_email': self.partner_id.email or '',
            'party_size': self.party_size,
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
        }

    @api.model_create_multi
    def create(self, vals_list):
        bookings = super().create(vals_list)
        for booking in bookings:
            booking._notify_pos_floor()
        return bookings

    def write(self, vals):
        res = super().write(vals)
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
            ])
            for booking in overdue_bookings:
                booking.action_no_show()
                config.notify_booking_update(booking, action="NO_SHOW")

        # Also sweep any bookings with pos_config_id not caught above
        cutoff_default = now - timedelta(minutes=default_grace)
        other_overdue = self.search([
            ('state', '=', 'confirmed'),
            ('end_datetime', '<', cutoff_default),
            ('pos_config_id', '=', False),
        ])
        for b in other_overdue:
            b.action_no_show()

