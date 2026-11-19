# -*- coding: utf-8 -*-
# Part of Hudson. See LICENSE file for full copyright and licensing details.

from datetime import datetime, timedelta
import pytz
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

class PosConfig(models.Model):
    _inherit = 'pos.config'

    def _default_booking_appointment_type_id(self):
        """Pure side-effect-free search for default celebration/table booking appointment type.

        Guards against is_event_booking not being present (e.g. when the custom
        appointment module is not yet installed on the target database).
        Uses sudo() to safely evaluate cross-company records without triggering AccessError.
        """
        company = (self.company_id if self and len(self) == 1 and self.company_id else False) or self.env.company
        other_type = self.sudo().env.ref('hudson_pos_booking.appointment_type_event_other', raise_if_not_found=False)
        if other_type and other_type.exists() and (not other_type.company_id or other_type.company_id == company):
            return other_type.id
        AppType = self.env['appointment.type'].sudo()
        comp_domain = ['|', ('company_id', '=', False), ('company_id', '=', company.id)]
        has_event_booking_field = 'is_event_booking' in AppType._fields
        found = AppType.browse()
        if has_event_booking_field:
            try:
                with self.env.cr.savepoint():
                    found = AppType.search([
                        ('booking_target', '=', 'resources'),
                        ('is_event_booking', '=', True),
                        ('event_category', '=', 'other'),
                    ] + comp_domain, limit=1)
                    if not found:
                        found = AppType.search([
                            ('booking_target', '=', 'resources'),
                            ('is_event_booking', '=', True),
                            ('is_published', '=', True),
                        ] + comp_domain, limit=1)
            except Exception:
                found = AppType.browse()
        if not found:
            try:
                with self.env.cr.savepoint():
                    app_type = self.sudo().env.ref('appointment.appointment_type_table_booking', raise_if_not_found=False)
                    if app_type and app_type.exists() and (not app_type.company_id or app_type.company_id == company):
                        return app_type.id
                    found = AppType.search([
                        ('booking_target', '=', 'resources'),
                        ('name', 'ilike', 'Table Booking'),
                    ] + comp_domain, limit=1)
            except Exception:
                found = AppType.browse()
        return found.id if found else False

    def _get_or_create_default_table_booking_type(self):
        """Return default booking appointment type ID, creating 'Celebrate Your Life Events' only if missing."""
        at_id = self._default_booking_appointment_type_id()
        if at_id:
            return at_id
        company = (self.company_id if self and len(self) == 1 and self.company_id else False) or self.env.company
        tz_name = company.partner_id.tz or self.env.user.tz or self.env.context.get('tz') or 'Asia/Calcutta'
        AppType = self.env['appointment.type'].sudo()
        vals = {
            'name': 'Celebrate Your Life Events',
            'booking_target': 'resources',
            'assign_method': 'random',
            'schedule_based_on': 'website',
            'is_published': False,
            'company_id': False,
            'appointment_tz': tz_name,
        }
        if 'is_event_booking' in AppType._fields:
            vals['is_event_booking'] = True
        if 'event_category' in AppType._fields:
            vals['event_category'] = 'other'
        if 'event_emoji' in AppType._fields:
            vals['event_emoji'] = '🎉'
        safe_vals = {k: v for k, v in vals.items() if k in AppType._fields}
        app_type = AppType.create(safe_vals)
        return app_type.id

    def _get_booking_timezone_name(self):
        """Resolve timezone name for POS bookings, checking company partner TZ, appointment type TZ, and user TZ."""
        if self and len(self) == 1:
            tz_name = (
                self.company_id.partner_id.tz
                or self.booking_appointment_type_id.appointment_tz
                or self.env.user.tz
                or self.env.context.get('tz')
            )
            company = self.company_id or self.env.company
        else:
            tz_name = self.env.company.partner_id.tz or self.env.user.tz or self.env.context.get('tz')
            company = self.env.company
        if not tz_name:
            app_type = self.env['appointment.type'].sudo().search([
                ('booking_target', '=', 'resources'),
                '|', ('company_id', '=', False), ('company_id', '=', company.id),
            ], limit=1)
            tz_name = (app_type.appointment_tz if app_type else False) or 'UTC'
        return tz_name

    def _get_booking_timezone(self):
        tz_name = self._get_booking_timezone_name()
        try:
            return pytz.timezone(tz_name)
        except Exception:
            return pytz.UTC

    def _ensure_online_prepaid_payment_method(self):
        """Ensure a dedicated 'Online Prepaid' payment method is attached to this POS config."""
        for cfg in self:
            if not cfg.use_booking:
                continue
            company = cfg.company_id or self.env.company
            pm = self.env['pos.payment.method'].sudo().search([
                ('name', '=', 'Online Prepaid'),
                ('company_id', '=', company.id),
            ], limit=1)
            if not pm:
                bank_journal = self.env['account.journal'].sudo().search([
                    ('type', '=', 'bank'),
                    ('company_id', '=', company.id),
                ], limit=1)
                pm = self.env['pos.payment.method'].sudo().create({
                    'name': 'Online Prepaid',
                    'type': 'bank',
                    'company_id': company.id,
                    'journal_id': bank_journal.id if bank_journal else False,
                })
            if pm and pm not in cfg.payment_method_ids:
                cfg.sudo().write({'payment_method_ids': [(4, pm.id)]})

    def _ensure_pricelist_group(self):
        """Ensure product.group_product_pricelist is implied whenever any POS config uses pricelists."""
        if self.env.context.get('skip_pricelist_group_sync'):
            return
        if not any(cfg.use_pricelist for cfg in self):
            return
        group_pricelist = self.env.ref('product.group_product_pricelist', raise_if_not_found=False)
        group_user = self.env.ref('base.group_user', raise_if_not_found=False)
        if group_pricelist and group_user and group_pricelist not in group_user.sudo().all_implied_ids:
            group_user.sudo()._apply_group(group_pricelist)
            self.env['res.company'].sudo()._activate_or_create_pricelists()

    @api.model_create_multi
    def create(self, vals_list):
        configs = super().create(vals_list)
        preorder_preset = self.env.ref('pos_restaurant.pos_takeout_preset', raise_if_not_found=False)
        if not preorder_preset:
            preorder_preset = self.env['pos.preset'].search([('name', '=', 'Pre-Order Food')], limit=1)
        if preorder_preset:
            for cfg in configs:
                if preorder_preset not in cfg.available_preset_ids:
                    cfg.available_preset_ids = [(4, preorder_preset.id)]
        configs._ensure_online_prepaid_payment_method()
        configs._ensure_pricelist_group()
        if not self.env.context.get('skip_table_sync'):
            floors_to_sync = configs.filtered(lambda c: c.module_pos_restaurant and c.use_booking).mapped('floor_ids')
            if floors_to_sync:
                floors_to_sync.with_context(active_test=False).mapped('table_ids')._sync_appointment_resource()
        return configs

    def write(self, vals):
        sync_trigger_fields = {'floor_ids', 'module_pos_restaurant', 'use_booking', 'booking_appointment_type_id', 'active'}
        need_table_sync = bool(sync_trigger_fields.intersection(vals.keys())) and not self.env.context.get('skip_table_sync')
        old_floors = self.mapped('floor_ids') if need_table_sync else self.env['restaurant.floor']

        res = super().write(vals)
        if 'use_booking' in vals or 'payment_method_ids' in vals:
            self._ensure_online_prepaid_payment_method()
        if vals.get('use_pricelist'):
            self._ensure_pricelist_group()
        if need_table_sync:
            all_floors = old_floors | self.mapped('floor_ids')
            if all_floors:
                all_floors.with_context(active_test=False).mapped('table_ids')._sync_appointment_resource()
        return res

    def open_ui(self):
        self._ensure_online_prepaid_payment_method()
        return super().open_ui()

    use_booking = fields.Boolean(
        string='Enable Table Booking',
        default=False,
        help="Integrate appointment table bookings into the restaurant POS interface."
    )
    booking_appointment_type_id = fields.Many2one(
        'appointment.type',
        string='Table Booking Type',
        domain="[('booking_target', '=', 'resources'), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        check_company=False,
        default=_default_booking_appointment_type_id,
        help="Appointment type used for restaurant table bookings."
    )
    booking_no_show_grace_minutes = fields.Integer(
        string='No-Show Grace Period (Minutes)',
        default=15,
        help="Minutes after a booking's scheduled end time before automatically marking it as No-Show."
    )

    @api.onchange('use_booking')
    def _onchange_use_booking(self):
        if self.use_booking and not self.booking_appointment_type_id:
            self.booking_appointment_type_id = self._get_or_create_default_table_booking_type()

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

        # Time range: today 00:00 to tomorrow 23:59:59 in restaurant timezone
        tz = self._get_booking_timezone()
        now_local = datetime.now(tz)
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = (now_local + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=999999)

        start_utc = start_local.astimezone(pytz.UTC).replace(tzinfo=None)
        end_utc = end_local.astimezone(pytz.UTC).replace(tzinfo=None)

        bookings = self.env['appointment.booking'].search([
            ('company_id', 'in', (self.company_id.id, False)),
            ('resource_ids', 'in', resources.ids),
            ('start_datetime', '<=', end_utc),
            ('end_datetime', '>=', start_utc),
            ('state', '!=', 'cancelled'),
        ], order='start_datetime asc')

        return [b._get_pos_booking_data(self) for b in bookings]

    def _to_utc_dt(self, dt_val):
        """Convert string or datetime to naive UTC datetime based on POS restaurant/user timezone."""
        if not dt_val:
            raise UserError(_("Please specify a valid start date and time for the booking."))
        if isinstance(dt_val, datetime):
            if dt_val.tzinfo:
                return dt_val.astimezone(pytz.UTC).replace(tzinfo=None)
            return dt_val

        tz = self._get_booking_timezone()

        dt_str = str(dt_val).strip()
        if dt_str.endswith('Z'):
            dt_str = dt_str[:-1]
            try:
                return datetime.fromisoformat(dt_str)
            except Exception:
                pass

        dt_str = dt_str.replace('T', ' ')
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
            try:
                dt_naive = datetime.strptime(dt_str, fmt)
                dt_local = tz.localize(dt_naive)
                return dt_local.astimezone(pytz.UTC).replace(tzinfo=None)
            except ValueError:
                continue

        try:
            parsed = fields.Datetime.to_datetime(dt_val)
            if parsed:
                return parsed
        except Exception:
            pass

        raise UserError(_("Invalid date/time format: '%s'.") % dt_val)

    @api.model
    def pos_create_booking(self, config_id, vals):
        """
        Create a booking directly from POS. Allows phone-only walk-ins (no email required)
        and supports choosing any resource-based Event / Celebration Appointment Type.
        """
        config = self.browse(config_id)
        if not config.exists() or not config.use_booking:
            raise UserError(_("Table booking is not enabled for this Point of Sale."))

        raw_type_id = vals.get('appointment_type_id')
        if raw_type_id:
            try:
                type_id = int(raw_type_id)
            except (ValueError, TypeError):
                raise UserError(_("Invalid booking event type selected."))
            appointment_type = self.env['appointment.type'].sudo().browse(type_id)
            if (
                not appointment_type.exists()
                or appointment_type.booking_target != 'resources'
                or (appointment_type.company_id and appointment_type.company_id != config.company_id)
            ):
                raise UserError(_("Selected booking event type is not valid for this Point of Sale."))
        else:
            appointment_type = config.booking_appointment_type_id
            if not appointment_type:
                raise UserError(_("No booking appointment type configured for this Point of Sale."))

        customer_name = (vals.get('customer_name') or '').strip() or _("Walk-in Guest")
        customer_phone = (vals.get('customer_phone') or '').strip()
        customer_email = (vals.get('customer_email') or '').strip() or False
        celebrant_name = (vals.get('celebrant_name') or '').strip() or False
        occasion_title = (vals.get('occasion_title') or '').strip() or False
        occasion_date = False
        if vals.get('occasion_date'):
            raw_occ = vals.get('occasion_date')
            try:
                occasion_date = fields.Date.to_date(raw_occ)
            except Exception:
                pass
            if not occasion_date and hasattr(self.env.get('appointment.answer'), '_parse_date_value'):
                occasion_date = self.env['appointment.answer']._parse_date_value(raw_occ)
            if not occasion_date:
                raise UserError(_("Invalid Special Day date format: '%s'. Please use YYYY-MM-DD.") % raw_occ)

        party_size = max(1, int(vals.get('party_size', 1)))
        table_id = vals.get('table_id')
        if not table_id:
            raise UserError(_("Please select a table for the booking."))

        # Convert given start_datetime to UTC
        start_dt_utc = config._to_utc_dt(vals.get('start_datetime'))
        duration = max(0.25, float(vals.get('duration') or vals.get('duration_hours') or appointment_type.appointment_duration or 1.5))
        end_dt_utc = start_dt_utc + timedelta(hours=duration)

        # Safe Partner matching (phone first for walk-ins, then email), never matching id=1 or company partner
        Partner = self.env['res.partner'].sudo()
        BookingModel = self.env['appointment.booking'].sudo()
        excluded_ids = [1]
        if config.company_id and config.company_id.partner_id:
            excluded_ids.append(config.company_id.partner_id.id)
        comp_scope = [('company_id', 'in', [False, config.company_id.id])]

        def _clean_phone(phone_val):
            if hasattr(BookingModel, '_normalize_phone_digits'):
                return BookingModel._normalize_phone_digits(phone_val)
            import re
            return re.sub(r'\D+', '', str(phone_val or ''))

        partner = Partner.browse()
        if customer_phone:
            phone_domain = [('phone', '=', customer_phone)]
            if 'mobile' in Partner._fields:
                phone_domain = ['|', ('phone', '=', customer_phone), ('mobile', '=', customer_phone)]
            partner = Partner.search([('id', 'not in', excluded_ids)] + comp_scope + phone_domain, limit=1)
            if not partner:
                target_digits = _clean_phone(customer_phone)
                if len(target_digits) >= 7:
                    candidates = Partner.search([
                        ('id', 'not in', excluded_ids),
                        ('phone', '!=', False),
                    ] + comp_scope, order='id desc', limit=200)
                    for cand in candidates:
                        c_digits = _clean_phone(cand.phone)
                        if c_digits and (
                            c_digits == target_digits
                            or c_digits.endswith(target_digits[-10:])
                            or target_digits.endswith(c_digits[-10:])
                        ):
                            partner = cand
                            break
        if not partner and customer_email:
            partner = Partner.search([
                ('id', 'not in', excluded_ids),
                ('email', '=ilike', customer_email),
            ] + comp_scope, limit=1)
        if not partner:
            partner = Partner.create({
                'name': customer_name,
                'phone': customer_phone,
                'email': customer_email,
            })

        table = self.env['restaurant.table'].browse(int(table_id))
        if not table.exists():
            raise UserError(_("Selected table does not exist."))

        all_related = table.get_merged_and_linked_tables()
        total_capacity = sum(all_related.mapped('seats')) or table.seats
        if total_capacity and party_size > total_capacity:
            raise UserError(_("Party size (%s) exceeds total seating capacity (%s).") % (party_size, total_capacity))

        if not table.appointment_resource_id:
            table._sync_appointment_resource()

        if table.appointment_resource_id and appointment_type.booking_target == 'resources':
            owner_types = self.env['appointment.type'].sudo().search([
                ('active', '=', True),
                ('booking_target', '=', 'resources'),
                ('resource_ids', 'in', [table.appointment_resource_id.id]),
            ])
            if owner_types and appointment_type not in owner_types:
                raise UserError(_(
                    "Table %s is reserved exclusively for %s and cannot be booked under %s."
                ) % (table.display_name, ', '.join(owner_types.mapped('name')), appointment_type.name))

        all_resources = all_related.mapped('appointment_resource_id')
        if all_resources:
            # Row lock resources in sorted order to prevent race conditions and deadlocks
            self.env.cr.execute(
                "SELECT id FROM appointment_resource WHERE id IN %s ORDER BY id FOR UPDATE",
                [tuple(sorted(all_resources.ids))]
            )
            conflict_domain = [
                ('company_id', 'in', (config.company_id.id, False)),
                ('resource_ids', 'in', all_resources.ids),
                ('start_datetime', '<', end_dt_utc),
                ('end_datetime', '>', start_dt_utc),
                '|',
                ('state', 'in', ('confirmed', 'checked_in')),
                '&', ('state', '=', 'pending_payment'), ('create_date', '>=', fields.Datetime.subtract(fields.Datetime.now(), minutes=15)),
            ]
            conflict = self.env['appointment.booking'].sudo().search(conflict_domain, limit=1)
            if conflict:
                rel_names = ', '.join(all_related.mapped('display_name'))
                tz = config._get_booking_timezone()
                c_start = conflict.start_datetime.replace(tzinfo=pytz.UTC).astimezone(tz).strftime('%Y-%m-%d %H:%M')
                c_end = conflict.end_datetime.replace(tzinfo=pytz.UTC).astimezone(tz).strftime('%H:%M')
                raise UserError(_(
                    "Double Booking Conflict! Table %s (or a table merged/linked to it) is already booked from %s to %s for %s."
                ) % (rel_names, c_start, c_end, conflict.partner_id.name or _("another guest")))

        assigned_resources = table.appointment_resource_id
        initial_state = vals.get('state') if vals.get('state') in ('confirmed', 'checked_in') else 'confirmed'
        booking_vals = {
            'company_id': config.company_id.id,
            'appointment_type_id': appointment_type.id,
            'partner_id': partner.id,
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'customer_email': customer_email,
            'celebrant_name': celebrant_name,
            'occasion_title': occasion_title,
            'occasion_date': occasion_date,
            'party_size': party_size,
            'start_datetime': start_dt_utc,
            'end_datetime': end_dt_utc,
            'duration': duration,
            'state': initial_state,
            'pos_config_id': config.id,
            'resource_ids': [(6, 0, assigned_resources.ids)] if assigned_resources else [(5, 0, 0)],
            'guest_details': vals.get('notes', ''),
        }
        safe_booking_vals = {k: v for k, v in booking_vals.items() if k in self.env['appointment.booking']._fields}
        booking = self.env['appointment.booking'].sudo().create(safe_booking_vals)
        config.notify_booking_update(booking, action="CREATE")
        return {'appointment.booking': [booking._get_pos_booking_data(config)]}

    @api.model
    def pos_update_booking(self, config_id, booking_id, vals):
        """Update booking status, event type, celebration fields, time, duration, table or customer details from POS."""
        config = self.browse(config_id)
        booking = self.env['appointment.booking'].browse(booking_id)
        if not booking.exists():
            raise UserError(_("Booking not found."))

        new_state = vals.get('state')
        if new_state:
            if new_state == 'checked_in':
                if hasattr(booking, 'action_check_in'):
                    booking.action_check_in()
                else:
                    booking.state = 'checked_in'
            elif new_state == 'checked_out':
                if hasattr(booking, 'action_check_out'):
                    booking.action_check_out()
                else:
                    booking.state = 'checked_out'
            elif new_state == 'no_show':
                if hasattr(booking, 'action_no_show'):
                    booking.action_no_show()
                else:
                    booking.state = 'no_show'
            elif new_state == 'cancelled':
                if hasattr(booking, 'action_cancel'):
                    booking.action_cancel()
                else:
                    booking.state = 'cancelled'
            elif new_state == 'confirmed':
                booking.state = 'confirmed'

        write_vals = {}

        if 'appointment_type_id' in vals and vals['appointment_type_id']:
            try:
                type_id = int(vals['appointment_type_id'])
            except (ValueError, TypeError):
                raise UserError(_("Invalid booking event type selected."))
            new_type = self.env['appointment.type'].sudo().browse(type_id)
            if (
                not new_type.exists()
                or new_type.booking_target != 'resources'
                or (new_type.company_id and new_type.company_id != config.company_id)
            ):
                raise UserError(_("Selected booking event type is not valid for this Point of Sale."))
            write_vals['appointment_type_id'] = new_type.id

        # 1. Start datetime and duration
        start_changed = 'start_datetime' in vals and vals['start_datetime']
        duration_changed = 'duration' in vals or 'duration_hours' in vals

        start_dt_utc = booking.start_datetime
        if start_changed:
            start_dt_utc = config._to_utc_dt(vals['start_datetime'])
            write_vals['start_datetime'] = start_dt_utc

        duration = booking.duration or 1.5
        if duration_changed:
            duration = float(vals.get('duration') or vals.get('duration_hours') or booking.duration or 1.5)
            write_vals['duration'] = duration

        if start_changed or duration_changed:
            end_dt_utc = start_dt_utc + timedelta(hours=duration)
            write_vals['end_datetime'] = end_dt_utc
        else:
            end_dt_utc = booking.end_datetime

        # 2. Table update
        table = False
        if 'table_id' in vals:
            table_id = vals['table_id']
            if table_id:
                table = self.env['restaurant.table'].browse(int(table_id))
                if table.exists() and table.appointment_resource_id:
                    write_vals['resource_ids'] = [(6, 0, [table.appointment_resource_id.id])]
            else:
                write_vals['resource_ids'] = [(5, 0, 0)]
        else:
            if booking.table_ids:
                table = booking.table_ids[0]

        effective_type = self.env['appointment.type'].sudo().browse(write_vals['appointment_type_id']) if 'appointment_type_id' in write_vals else booking.appointment_type_id
        if table and table.exists() and table.appointment_resource_id and effective_type and effective_type.booking_target == 'resources':
            owner_types = self.env['appointment.type'].sudo().search([
                ('active', '=', True),
                ('booking_target', '=', 'resources'),
                ('resource_ids', 'in', [table.appointment_resource_id.id]),
            ])
            if owner_types and effective_type not in owner_types:
                raise UserError(_(
                    "Table %s is reserved exclusively for %s and cannot be booked under %s."
                ) % (table.display_name, ', '.join(owner_types.mapped('name')), effective_type.name))

        # 3. Double Booking Validation
        if table and table.exists() and (start_changed or duration_changed or 'table_id' in vals):
            all_related = table.get_merged_and_linked_tables()
            all_resources = all_related.mapped('appointment_resource_id')
            if all_resources:
                # Row lock resources in sorted order to prevent concurrent double-booking race condition
                self.env.cr.execute(
                    "SELECT id FROM appointment_resource WHERE id IN %s ORDER BY id FOR UPDATE",
                    [tuple(sorted(all_resources.ids))]
                )
                conflict_domain = [
                    ('id', '!=', booking.id),
                    ('company_id', 'in', (config.company_id.id, False)),
                    ('resource_ids', 'in', all_resources.ids),
                    ('start_datetime', '<', end_dt_utc),
                    ('end_datetime', '>', start_dt_utc),
                    '|',
                    ('state', 'in', ('confirmed', 'checked_in')),
                    '&', ('state', '=', 'pending_payment'), ('create_date', '>=', fields.Datetime.subtract(fields.Datetime.now(), minutes=15)),
                ]
                conflict = self.env['appointment.booking'].sudo().search(conflict_domain, limit=1)
                if conflict:
                    rel_names = ', '.join(all_related.mapped('display_name'))
                    tz = config._get_booking_timezone()
                    c_start = conflict.start_datetime.replace(tzinfo=pytz.UTC).astimezone(tz).strftime('%Y-%m-%d %H:%M')
                    c_end = conflict.end_datetime.replace(tzinfo=pytz.UTC).astimezone(tz).strftime('%H:%M')
                    raise UserError(_(
                        "Double Booking Conflict! Table %s (or a table merged/linked to it) is already booked from %s to %s for %s."
                    ) % (rel_names, c_start, c_end, conflict.partner_id.name or _("another guest")))

        if 'party_size' in vals:
            write_vals['party_size'] = int(vals['party_size'])
        if 'notes' in vals:
            write_vals['guest_details'] = vals['notes']
        if 'celebrant_name' in vals:
            write_vals['celebrant_name'] = (vals['celebrant_name'] or '').strip() or False
        if 'occasion_title' in vals:
            write_vals['occasion_title'] = (vals['occasion_title'] or '').strip() or False
        if 'occasion_date' in vals:
            raw_occ = vals['occasion_date']
            if raw_occ:
                parsed_occ = False
                try:
                    parsed_occ = fields.Date.to_date(raw_occ)
                except Exception:
                    pass
                if not parsed_occ and hasattr(self.env.get('appointment.answer'), '_parse_date_value'):
                    parsed_occ = self.env['appointment.answer']._parse_date_value(raw_occ)
                if not parsed_occ:
                    raise UserError(_("Invalid Special Day date format: '%s'. Please use YYYY-MM-DD.") % raw_occ)
                write_vals['occasion_date'] = parsed_occ
            else:
                write_vals['occasion_date'] = False

        # 4. Customer update (update stored booking fields; protect shared partner records)
        if ('customer_name' in vals and vals['customer_name']) or ('customer_phone' in vals) or ('customer_email' in vals):
            c_name = vals.get('customer_name') or booking.customer_name
            c_phone = vals.get('customer_phone') if 'customer_phone' in vals else booking.customer_phone
            c_email = ((vals.get('customer_email') or '').strip() or False) if 'customer_email' in vals else booking.customer_email

            if 'customer_name' in vals and vals['customer_name']:
                write_vals['customer_name'] = vals['customer_name']
            if 'customer_phone' in vals:
                write_vals['customer_phone'] = vals['customer_phone']
            if 'customer_email' in vals:
                write_vals['customer_email'] = c_email

            # Only write to partner if unshared partner (not system/company partner, not shared across other sales/bookings)
            if booking.partner_id and booking.partner_id.id not in (1, config.company_id.partner_id.id):
                other_bookings = self.env['appointment.booking'].search([('partner_id', '=', booking.partner_id.id), ('id', '!=', booking.id)], limit=1)
                other_sales = self.env['sale.order'].search([('partner_id', '=', booking.partner_id.id)], limit=1)
                if not other_bookings and not other_sales:
                    p_vals = {}
                    if 'customer_name' in vals and vals['customer_name']:
                        p_vals['name'] = vals['customer_name']
                    if 'customer_phone' in vals:
                        p_vals['phone'] = vals['customer_phone']
                    if 'customer_email' in vals:
                        p_vals['email'] = c_email
                    booking.partner_id.sudo().write(p_vals)
            elif not booking.partner_id and c_name:
                partner = self.env['res.partner'].sudo().create({
                    'name': c_name,
                    'phone': c_phone or '',
                    'email': c_email,
                })
                write_vals['partner_id'] = partner.id

        if write_vals:
            safe_write = {k: v for k, v in write_vals.items() if k in booking._fields}
            if safe_write:
                booking.write(safe_write)

        config.notify_booking_update(booking, action="UPDATE")
        return {'appointment.booking': [booking._get_pos_booking_data(config)]}

    @api.model
    def pos_release_table(self, config_id, table_id, booking_id=False):
        """Release table from POS, check out booking, and clear draft orders safely."""
        config = self.browse(config_id)
        table = self.env['restaurant.table'].browse(int(table_id))

        booking = False
        if booking_id:
            booking = self.env['appointment.booking'].browse(int(booking_id))
            if booking.exists() and table.exists():
                if table.id not in booking.table_ids.ids and (not table.appointment_resource_id or table.appointment_resource_id not in booking.resource_ids):
                    booking = False
        if not booking and table.exists():
            # If no booking passed, only look for an actively checked_in booking on this table
            # (never auto-checkout an unrelated future confirmed booking).
            domain = [
                ('company_id', 'in', (config.company_id.id, False)),
                ('state', '=', 'checked_in'),
            ]
            if table.appointment_resource_id:
                domain.append('|')
                domain.append(('table_ids', 'in', table.id))
                domain.append(('resource_ids', 'in', table.appointment_resource_id.ids))
            else:
                domain.append(('table_ids', 'in', table.id))
            booking = self.env['appointment.booking'].search(domain, order='start_datetime desc', limit=1)

        if booking and booking.exists() and (booking.state == 'checked_in' or (booking_id and booking.state == 'confirmed')):
            booking.action_check_out()
            config.notify_booking_update(booking, action="UPDATE")

        # Cancel empty draft pos.orders on this table in current session so table is immediately freed
        session = config.current_session_id
        if session and table.exists():
            draft_orders = self.env['pos.order'].search([
                ('session_id', '=', session.id),
                ('table_id', '=', table.id),
                ('state', '=', 'draft'),
            ])
            for d_order in draft_orders:
                if not d_order.lines:
                    try:
                        d_order.write({'state': 'cancel'})
                    except Exception:
                        pass

        return {
            'success': True,
            'table_id': table_id,
            'booking_id': booking.id if booking else False,
        }

