# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from datetime import datetime, timedelta
import pytz
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class PosConfig(models.Model):
    _inherit = 'pos.config'

    use_booking = fields.Boolean(
        string='Enable Table Booking',
        default=False,
        help="Integrate appointment table bookings into the restaurant POS interface."
    )
    booking_appointment_type_id = fields.Many2one(
        'appointment.type',
        string='Table Booking Type',
        domain="[('booking_target', '=', 'resources')]",
        help="Appointment type used for restaurant table bookings."
    )
    booking_no_show_grace_minutes = fields.Integer(
        string='No-Show Grace Period (Minutes)',
        default=15,
        help="Minutes after a booking's scheduled end time before automatically marking it as No-Show."
    )

    def _get_table_appointment_resources(self):
        """Return appointment.resource records mapped to this pos.config's floor tables."""
        self.ensure_one()
        tables = self.floor_ids.table_ids.filtered(lambda t: t.active and t.appointment_resource_id)
        return tables.mapped('appointment_resource_id')

    def notify_booking_update(self, booking, action="UPDATE"):
        """Broadcast bus notification to connected POS clients for floor refresh."""
        for config in self:
            if not config.use_booking:
                continue
            config._notify('BOOKING_UPDATE', {
                'action': action,
                'booking_id': booking.id,
                'booking_data': booking._get_pos_booking_data(config),
                'table_ids': booking.table_ids.ids,
            })

    def get_bookings_for_floor(self):
        """Fetch bookings for today and tomorrow for all tables in this POS configuration."""
        self.ensure_one()
        if not self.use_booking:
            return []

        resources = self._get_table_appointment_resources()
        if not resources:
            return []

        # Time range: today 00:00 to tomorrow 23:59:59 in company timezone
        tz_name = self.env.user.tz or self.company_id.partner_id.tz or 'UTC'
        tz = pytz.timezone(tz_name)
        now_local = datetime.now(tz)
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = (now_local + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)

        start_utc = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        end_utc = end_local.astimezone(pytz.UTC).replace(tzinfo=None)

        bookings = self.env['appointment.booking'].search([
            ('resource_ids', 'in', resources.ids),
            ('start_datetime', '<=', end_utc),
            ('end_datetime', '>=', start_utc),
            ('state', '!=', 'cancelled'),
        ], order='start_datetime asc')

        return [b._get_pos_booking_data(self) for b in bookings]

    @api.model
    def pos_create_booking(self, config_id, vals):
        """
        Create a booking directly from POS. Allows phone-only walk-ins (no email required).
        Reuses appointment.type availability & assignment methods.
        """
        config = self.browse(config_id)
        if not config.exists() or not config.use_booking:
            raise UserError(_("Table booking is not enabled for this Point of Sale."))

        appointment_type = config.booking_appointment_type_id
        if not appointment_type:
            raise UserError(_("No booking appointment type configured for this Point of Sale."))

        customer_name = vals.get('customer_name') or _("Walk-in Guest")
        customer_phone = vals.get('customer_phone') or ''
        customer_email = vals.get('customer_email') or False
        party_size = int(vals.get('party_size', 1))
        table_id = vals.get('table_id')

        # Convert given start_datetime to UTC
        start_dt_str = vals.get('start_datetime')
        if not start_dt_str:
            start_dt_utc = fields.Datetime.now()
        else:
            # Assume passed as ISO string or YYYY-MM-DD HH:MM:SS
            try:
                start_dt_utc = fields.Datetime.to_datetime(start_dt_str)
            except Exception:
                start_dt_utc = fields.Datetime.now()

        duration = float(vals.get('duration') or appointment_type.appointment_duration or 1.0)
        end_dt_utc = start_dt_utc + timedelta(hours=duration)

        # Partner: find by phone or email, or create
        Partner = self.env['res.partner'].sudo()
        partner = False
        if customer_phone:
            domain = [('phone', '=', customer_phone)]
            if 'mobile' in Partner._fields:
                domain = ['|', ('phone', '=', customer_phone), ('mobile', '=', customer_phone)]
            partner = Partner.search(domain, limit=1)
        if not partner and customer_email:
            partner = Partner.search([('email', '=', customer_email)], limit=1)
        if not partner:
            partner = Partner.create({
                'name': customer_name,
                'phone': customer_phone,
                'email': customer_email,
            })

        requested_res_id = False
        if table_id:
            table = self.env['restaurant.table'].browse(table_id)
            if table.appointment_resource_id:
                requested_res_id = table.appointment_resource_id.id

        assigned_resources = appointment_type._assign_resources(
            start_dt_utc, end_dt_utc, party_size=party_size,
            requested_resource_id=requested_res_id
        )

        if not assigned_resources:
            raise UserError(_("No table resources available for this party size and time slot."))

        initial_state = vals.get('state', 'confirmed')
        booking_vals = {
            'appointment_type_id': appointment_type.id,
            'partner_id': partner.id,
            'party_size': party_size,
            'start_datetime': start_dt_utc,
            'end_datetime': end_dt_utc,
            'duration': duration,
            'state': initial_state,
            'pos_config_id': config.id,
            'resource_ids': [(6, 0, assigned_resources.ids)],
            'guest_details': vals.get('notes', ''),
        }
        booking = self.env['appointment.booking'].sudo().create(booking_vals)
        config.notify_booking_update(booking, action="CREATE")
        return booking._get_pos_booking_data(config)

    @api.model
    def pos_update_booking(self, config_id, booking_id, vals):
        """Update booking status or details from POS."""
        config = self.browse(config_id)
        booking = self.env['appointment.booking'].browse(booking_id)
        if not booking.exists():
            raise UserError(_("Booking not found."))

        new_state = vals.get('state')
        if new_state:
            if new_state == 'checked_in':
                booking.action_check_in()
            elif new_state == 'no_show':
                booking.action_no_show()
            elif new_state == 'cancelled':
                booking.action_cancel()
            elif new_state == 'confirmed':
                booking.state = 'confirmed'

        write_vals = {}
        if 'party_size' in vals:
            write_vals['party_size'] = int(vals['party_size'])
        if 'table_id' in vals and vals['table_id']:
            table = self.env['restaurant.table'].browse(vals['table_id'])
            if table.appointment_resource_id:
                write_vals['resource_ids'] = [(6, 0, [table.appointment_resource_id.id])]
        if 'notes' in vals:
            write_vals['guest_details'] = vals['notes']

        if write_vals:
            booking.write(write_vals)

        config.notify_booking_update(booking, action="UPDATE")
        return booking._get_pos_booking_data(config)

